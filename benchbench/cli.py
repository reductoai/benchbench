"""benchbench CLI. Typical run (one benchmark, one run directory):

benchbench sample   runs/score_bench --benchmark score_bench --n 500 --seed 20261107
benchbench render   runs/score_bench
benchbench perturb  runs/score_bench --conditions tilt_2_4 scan
benchbench estimate runs/score_bench --presets reducto_r1 llamaparse_agentic_plus --conditions clean tilt_2_4
benchbench parse    runs/score_bench --presets ... --conditions clean tilt_2_4
benchbench judge    runs/score_bench --presets ... --conditions clean --repeats 2
benchbench judge    runs/score_bench --presets ... --conditions tilt_2_4
benchbench judge    runs/score_bench --presets ... --conditions clean tilt_2_4 --prompt neutral
benchbench native   runs/score_bench --benchmark score_bench --presets ...
benchbench report   runs/score_bench --benchmark score_bench --presets ... --conditions clean tilt_2_4
"""

import argparse
import json
from pathlib import Path

from . import bridge, pipeline
from .augment import CONDITIONS
from .catalog import load_catalog
from .storage import Run

DEFAULT_JUDGE = "gpt-6.1-sol"
SECOND_JUDGE = "gemini-3.1-pro-preview"
SECOND_JUDGE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
# USD per million (input, output) tokens, published list prices checked 2026-11-07.
TOKEN_PRICES = {"gpt-6.1-sol": (2.00, 10.00), "gemini-3.1-pro-preview": (2.00, 12.00)}
# Fallback per call when a run has no judge verdicts yet: 8-preset page, ~16k input + ~1.5k output tokens.
JUDGE_USD_PER_CALL = 0.05


def report_subdir(a) -> str:
    """Where `report` writes. `--label` also selects the primary judge tags; `--out-label` only moves the
    output (e.g. a compare-judge variant of the primary report)."""
    if a.out_label is not None:
        return a.out_label
    return a.label or ("strip-style" if a.strip_style else "")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(
        prog="benchbench", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, **kw):
        p = sub.add_parser(name, **kw)
        if name != "catalog":
            p.add_argument("run", type=Path)
        return p

    cmd("catalog")
    p = sub.add_parser("host", help="validate user-provisioned S3-compatible page-image hosting")
    p.add_argument("--env-file", type=Path, default=Path.home() / ".benchbench-host.env")
    p = cmd("sample")
    p.add_argument("--benchmark", nargs="+", required=True)
    p.add_argument("--n", type=int)
    p.add_argument("--seed", type=int, default=20261107)
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--notes", default="")
    p = cmd("render")
    p.add_argument("--workers", type=int, default=32)
    p = cmd("perturb")
    p.add_argument(
        "--conditions", nargs="+", required=True, choices=list(CONDITIONS) + list(pipeline.REAL5_CONDITIONS)
    )
    for name in ("estimate", "parse", "judge", "report", "disagreements"):
        p = cmd(name)
        p.add_argument("--presets", nargs="+", required=True)
        p.add_argument("--conditions", nargs="+", default=["clean"])
        p.add_argument(
            "--workers",
            type=int,
            default=96,
            help="parse: pool size across vendors (per vendor: BENCHBENCH_PER_PRESET)",
        )
        p.add_argument(
            "--judge",
            default=DEFAULT_JUDGE,
            help="one judge model per run (no fallbacks); 'fake' for dry runs",
        )
        p.add_argument(
            "--prompt",
            default="parsejudge",
            choices=["parsejudge", "parsejudge-upstream", "neutral", "minimal", "terse"],
            help="parsejudge (primary) = Parse Judge compare-v4 minus the PDF link-layer URL clause; "
            "parsejudge-upstream = compare-v4 as published; neutral = error-count check (secondary); minimal = page + parses, 'which parse is better?', 1-10; terse = compare-v4 output schema, one-sentence prompt",  # noqa: E501
        )
        p.add_argument(
            "--judge-image",
            default="clean",
            choices=["clean", "condition"],
            help="judge each parse against the clean page (default) or the perturbed page it was made from",
        )
        p.add_argument(
            "--allow-failed", action="store_true", help="judge failed parses as empty text (secondary)"
        )
        p.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
        p.add_argument("--repeats", type=int, default=1)
        p.add_argument(
            "--judge-base-url", default="https://api.openai.com/v1", help="any OpenAI-compatible API"
        )
        p.add_argument("--judge-key-env", default="OPENAI_API_KEY", help="env var holding the judge API key")
        p.add_argument("--benchmark")
        p.add_argument("--strip-style", action="store_true", help="strip comments, image refs, spans, ids")
        p.add_argument("--label", default="", help="suffix for a separate judge run (e.g. probes)")
        p.add_argument(
            "--out-label",
            default=None,
            help="report: subdirectory of reports/<benchmark>/ to write to, judge tags unchanged "
            "(default: --label, or strip-style)",
        )
        p.add_argument(
            "--image-detail",
            default=bridge.IMAGE_DETAIL,
            choices=["high", "original", "auto", "low"],
            help="OpenAI image detail (default high, the study setting); others judge into a separate tag",
        )
        p.add_argument(
            "--gemini-media-resolution",
            default=bridge.GEMINI_MEDIA_RESOLUTION,
            choices=["", *(f"MEDIA_RESOLUTION_{x}" for x in ("LOW", "MEDIUM", "HIGH", "ULTRA_HIGH"))],
            help="Gemini per-image level via the native API (default: compatible endpoint, study setting)",
        )
        p.add_argument(
            "--label-order",
            default="shared",
            choices=["shared", "own"],
            help="shared (default, study setting): label order seeded on page, condition, repeat; "
            "own: also on the judge model, into a separate -own tag",
        )
        p.add_argument(
            "--compare-label-order",
            default="shared",
            choices=["shared", "own"],
            help="report: label order of the --compare judges",
        )
        p.add_argument(
            "--compare-repeats",
            type=int,
            default=1,
            help="report: clean repeats averaged per --compare judge",
        )
        p.add_argument(
            "--compare",
            nargs="*",
            default=[],
            metavar="PROMPT:MODEL[@BASE_URL]",
            help="report: other clean judges a pair claim must agree with, e.g. neutral:gpt-6.1-sol "
            f"parsejudge:{SECOND_JUDGE}@{SECOND_JUDGE_URL}",
        )
        p.add_argument("--secondary", action="store_true", help="report: add the --allow-failed run")
        p.add_argument("--n", type=int, default=20, help="disagreements: pages to export")
        p.add_argument(
            "--extra-clean-judges", type=int, default=5, help="estimate: clean-only judge runs beyond primary"
        )
    p = cmd("homefield")
    p.add_argument("runs", nargs="+", type=Path, help="run directories with reports")
    p = cmd("native")
    p.add_argument("--benchmark", required=True)
    p.add_argument("--presets", nargs="+", required=True)
    p.add_argument("--conditions", nargs="+", default=["clean"])
    p.add_argument(
        "--probes",
        nargs="*",
        default=[],
        help="score probe-<name>-gt (probe applied to ground truth); needs the adapter's gt_markdown",
    )
    p.add_argument(
        "--probe-base",
        default="gt",
        help="'gt' (default, parser-neutral) or 'all' to also probe every preset and report the median",
    )
    cmd("status")
    p = cmd("upload-s3")
    p.add_argument("--benchmark", required=True)
    p.add_argument("--bucket", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "host":
        print(json.dumps(pipeline.make_host(a.env_file), indent=1))
        return
    if a.cmd == "catalog":
        for b in load_catalog().values():
            print(
                f"{b['id']:20} tier {b.get('tier')} {b.get('data', ''):10.10} pages {b.get('pages', '?'):>6} "
                f"{b.get('builder', '')}"
            )
        return
    run = Run(a.run)
    if a.cmd == "sample":
        pipeline.init_run(a.run, a.benchmark, a.n, a.seed, a.dpi, a.notes)
    elif a.cmd == "render":
        pipeline.render_all(run, a.workers)
    elif a.cmd == "perturb":
        pipeline.perturb_all(run, a.conditions, workers=32)
    elif a.cmd == "estimate":
        print(json.dumps(estimate(run, a.presets, a.conditions, a.repeats, a.extra_clean_judges), indent=1))
    elif a.cmd == "parse":
        pipeline.parse_all(run, a.presets, a.conditions, a.workers)
    elif a.cmd == "judge":
        pipeline.judge_all(
            run,
            a.presets,
            a.conditions,
            a.judge,
            a.effort,
            a.repeats,
            a.workers,
            a.judge_base_url,
            a.judge_key_env,
            a.prompt,
            a.judge_image,
            a.allow_failed,
            a.strip_style,
            a.label,
            a.image_detail,
            a.gemini_media_resolution,
            a.label_order,
        )
    elif a.cmd == "native":
        from . import native

        presets = list(a.presets)
        for cond in a.conditions:
            bases = ["gt"] + (presets if a.probe_base == "all" else [])
            presets_c = list(presets)
            if a.probes:
                for base in bases:
                    presets_c += native.make_probe_parses(run, cond, base, a.probes)
            native.score(run, a.benchmark, cond, presets_c)
    elif a.cmd == "report":
        from .report import summarize

        benches = [a.benchmark] if a.benchmark else sorted({p["benchmark"] for p in run.pages()})
        for b in benches:
            tag = lambda r, **kw: pipeline.judge_tag(  # noqa: E731
                a.judge,
                a.effort,
                r,
                a.prompt,
                a.judge_image,
                kw.get("failed", False),
                a.judge_base_url,
                a.strip_style,
                a.label,
                a.image_detail,
                a.gemini_media_resolution,
                a.label_order,
            )
            compare = {}
            for spec in a.compare:
                prompt, _, rest = spec.partition(":")
                model, _, url = rest.partition("@")
                compare[spec] = [
                    pipeline.judge_tag(
                        model,
                        a.effort,
                        r,
                        prompt,
                        base_url=url or pipeline.DEFAULT_BASE_URL,
                        label_order=a.compare_label_order,
                    )
                    for r in range(a.compare_repeats)
                ]
            out = run.root / "reports" / b / report_subdir(a)
            summarize(
                run,
                b,
                a.presets,
                a.conditions,
                [tag(r) for r in range(a.repeats)],
                out_dir=out,
                compare=compare,
                secondary_tag=tag(0, failed=True) if a.secondary else None,
            )
            print((out / "summary.md").read_text())
    elif a.cmd == "disagreements":
        from .report import disagreements

        tag = pipeline.judge_tag(a.judge, a.effort, 0, a.prompt, base_url=a.judge_base_url)
        print(disagreements(run, a.benchmark, a.presets, tag, a.n))
    elif a.cmd == "homefield":
        from .report import homefield

        print(json.dumps(homefield(a.runs), indent=1))
    elif a.cmd == "upload-s3":
        print(json.dumps(pipeline.upload_s3(run, a.benchmark, a.bucket), indent=1))
    elif a.cmd == "status":
        print(json.dumps(pipeline.status(run), indent=1))


def estimate(run: Run, presets: list[str], conditions: list[str], repeats: int, extra_clean: int = 5) -> dict:
    """Plan cost: parses for every condition; primary judge on every condition plus extra clean repeats;
    `extra_clean` additional clean-only judge runs (default 5)."""
    price = _list_prices()
    n = len(run.pages())
    parse = {s: round(n * len(conditions) * price.get(s, 0.0), 2) for s in presets}
    per_call, measured = _judge_cost_per_call(run)
    calls = n * (len(conditions) + max(0, repeats - 1) + extra_clean)
    judge = round(calls * per_call, 2)
    return {
        "pages": n,
        "conditions": conditions,
        "parse_usd": parse,
        "judge_calls": calls,
        "judge_usd_per_call": round(per_call, 4),
        "judge_cost_measured_on_calls": measured,
        "judge_usd": judge,
        "total_usd": round(sum(parse.values()) + judge, 2),
        "unknown_price": [s for s in presets if s not in price],
    }


def _judge_cost_per_call(run: Run) -> tuple[float, int]:
    """Mean cost of the judge calls already in this run, from recorded token usage and TOKEN_PRICES."""
    costs = []
    for f in (run.root / "judge").rglob("*.json") if (run.root / "judge").exists() else []:
        if "attempts" in f.parts or f.name.endswith(".raw.json"):
            continue
        v = json.loads(f.read_text())
        if not isinstance(v, dict) or not v.get("ok"):
            continue
        for u in v.get("usage") or []:
            pin, pout = TOKEN_PRICES.get(u.get("model"), (None, None))
            tok = u.get("usage") or {}
            if pin is not None and tok:
                costs.append(
                    (tok.get("prompt_tokens", 0) * pin + tok.get("completion_tokens", 0) * pout) / 1e6
                )
    return (sum(costs) / len(costs), len(costs)) if costs else (JUDGE_USD_PER_CALL, 0)


def _list_prices() -> dict[str, float]:
    from .bridge import call

    return {p["id"]: p["listPriceUsdPerPage"] for p in call({"op": "presets"})["presets"]}


if __name__ == "__main__":
    main()
