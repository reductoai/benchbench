"""ParseBench-2 (LlamaIndex) native scorer adapter.

Scorer: `parse_bench.cli evaluation run --next=<subset>` from run-llama/ParseBench at SCORER_COMMIT (2.0.0,
the ParseBench-2 scorers), unmodified, in its own environment (PARSEBENCH2_PYTHON, default
~/ParseBench2/.venv/bin/python). It runs once per subset folder against that folder's `<page>.test.json`
files at the pinned dataset revision, as `parse-bench run --dataset parsebench-2` does. Each page's headline
metric is the one its subset feeds in parse_bench.evaluation.next_score.NEXT_DIMENSIONS:

- headings, strikeout, underline: formatting_v2 (dimension Formatting)
- tables, complex_table_headers, financial_tables, insurance_filing_tables, dense_tables: table_next (Tables)
- forms, fillable_forms: forms_v2 (Forms)
- layout: layout_grounding_pass_rate (Layout); text: text_next (Text); charts: chart_next (Charts)

Per-page `score` is 100 x that metric. `official.json` holds each dimension as the NEXT_DIMENSIONS weighted
mean of the subsets present in the sample (weights renormalized over present subsets; the sample has only
the subsets with cases new in ParseBench-2, so Text and Charts are absent and the upstream six-dimension
score is not formed) and the mean of the present dimensions without Layout.

No conversion: the 2.0.0 table scorer reads Markdown pipe tables and HTML tables (table_next.py), so the
markdown is scored as the vendor returned it. Layout grounding needs element boxes, which a markdown parse
does not have, so layout pages get `score` None (metric kept in subscores) and Layout is left out of the
headline mean. Failed parses get no result file and no row.
"""

import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from ..storage import read_json

DATA_REPO = "llamaindex/ParseBench-2"
DATA_REVISION = "880b2204948071f464cc0b06bfb1b8f1021b1c7c"
SCORER_REPO = Path(os.environ.get("PARSEBENCH2_DIR", Path.home() / "ParseBench2"))
SCORER_COMMIT = "31a9ff1dec96f900869b785d8504d18f5035ebf8"
PYTHON = os.environ.get("PARSEBENCH2_PYTHON", str(SCORER_REPO / ".venv" / "bin" / "python"))
CACHE = Path(os.environ.get("BENCHBENCH_CACHE", Path.home() / ".cache" / "benchbench")) / "parsebench2"
SLOTS = {  # subset -> (dimension, metric, weight), from next_score.NEXT_DIMENSIONS at SCORER_COMMIT
    "text": ("Text", "text_next", 1.0),
    "headings": ("Formatting", "formatting_v2", 1 / 8),
    "strikeout": ("Formatting", "formatting_v2", 1 / 16),
    "underline": ("Formatting", "formatting_v2", 1 / 16),
    "tables": ("Tables", "table_next", 1 / 2),
    "complex_table_headers": ("Tables", "table_next", 1 / 8),
    "financial_tables": ("Tables", "table_next", 1 / 8),
    "insurance_filing_tables": ("Tables", "table_next", 1 / 8),
    "dense_tables": ("Tables", "table_next", 1 / 8),
    "charts": ("Charts", "chart_next", 1.0),
    "layout": ("Layout", "layout_grounding_pass_rate", 1.0),
    "forms": ("Forms", "forms_v2", 7 / 8),
    "fillable_forms": ("Forms", "forms_v2", 1 / 8),
}
WARN_LAYOUT = (
    "Layout grounding needs element boxes; markdown parses have none. No native score for layout pages "
    "(metric kept in subscores)."
)


def check_scorer() -> None:
    head = subprocess.run(
        ["git", "-C", str(SCORER_REPO), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != SCORER_COMMIT:
        raise SystemExit(f"ParseBench scorer at {head or 'missing'}, need {SCORER_COMMIT} in {SCORER_REPO}")
    dirty = subprocess.run(
        ["git", "-C", str(SCORER_REPO), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"ParseBench scorer tree in {SCORER_REPO} has local edits")


def _subset(page: dict) -> str:
    return page["file"].split("/")[0]


def _stem(page: dict) -> str:
    return Path(page["file"]).stem


def _test_id(page: dict) -> str:
    return f"{_subset(page)}/{_stem(page)}"


def gt_dir(pages: list[dict]) -> Path:
    """One folder per subset with copies of the sampled page files and their `.test.json` (pinned rev)."""
    from huggingface_hub import hf_hub_download

    from ..catalog import load_catalog
    from ..datasets import fetch

    files = sorted({p["file"] for p in pages})
    digest = hashlib.sha256("\n".join(files).encode()).hexdigest()[:12]
    d = CACHE / f"gt-{DATA_REVISION[:12]}-{len(files)}-{digest}"
    if (d / ".done").exists():
        return d
    bench = load_catalog()["parsebench2"]
    for p in pages:
        link = d / p["file"]
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.exists():
            shutil.copyfile(fetch(p, bench), link)  # the loader skips symlinks to suffixless HF blobs
        tj = d / _subset(p) / f"{_stem(p)}.test.json"
        if not tj.exists():
            src = hf_hub_download(DATA_REPO, f"{_subset(p)}/{_stem(p)}.test.json", repo_type="dataset",
                                  revision=DATA_REVISION)  # fmt: skip
            shutil.copyfile(src, tj)
    (d / ".done").write_text("ok")
    return d


def gt_markdown(page: dict) -> str | None:
    """`expected_markdown` from the page's `.test.json`, where the subset ships one."""
    from huggingface_hub import hf_hub_download

    src = hf_hub_download(DATA_REPO, f"{_subset(page)}/{_stem(page)}.test.json", repo_type="dataset",
                          revision=DATA_REVISION)  # fmt: skip
    return json.loads(Path(src).read_text()).get("expected_markdown") or None


def export(run, cond, preset, pages, out_dir: Path) -> None:
    check_scorer()
    out_dir.mkdir(parents=True, exist_ok=True)
    results = out_dir / "results"
    now = datetime.now(UTC).isoformat()
    missing = []
    for p in pages:
        sub = results / _subset(p)
        target = sub / f"{_stem(p)}.result.json"
        if target.exists():
            target.unlink()
        d = read_json(run.parse(cond, preset, p["page_key"]))
        if not d or not d.get("ok"):
            missing.append(p["page_key"])
            continue
        md = d.get("markdown") or ""
        tid = _test_id(p)
        sub.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "request": {"example_id": tid, "source_file_path": p["file"], "product_type": "parse"},
                    "pipeline_name": preset,
                    "product_type": "parse",
                    "raw_output": {},
                    "output": {
                        "task_type": "parse",
                        "example_id": tid,
                        "pipeline_name": preset,
                        "pages": [{"page_index": 0, "markdown": md}],
                        "markdown": md,
                    },
                    "started_at": now,
                    "completed_at": now,
                    "latency_in_ms": int(d.get("latencyMs") or 0),
                },
                ensure_ascii=False,
            )
        )
    for sub in {_subset(p) for p in pages}:
        (results / sub).mkdir(parents=True, exist_ok=True)
        meta = {"pipeline_name": preset, "product_type": "parse"}
        (results / sub / "_metadata.json").write_text(json.dumps(meta))
    (out_dir / "missing.json").write_text(json.dumps(missing))


def _evaluate(results: Path, gt: Path, subset: str, report_dir: Path) -> dict:
    cmd = [PYTHON, "-m", "parse_bench.cli", "evaluation", "run", str(results), "-t", str(gt), "-r",
           str(report_dir), f"--next={subset}", "--force", "True", "--export_csv", "False",
           "--export_rule_csv", "False", "--export_markdown", "False", "--export_html", "False"]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=SCORER_REPO)
    (report_dir.parent / f"scorer-{subset}.log").write_text(proc.stdout[-20000:] + proc.stderr[-20000:])
    rep = report_dir / "_evaluation_report.json"
    if proc.returncode or not rep.exists():
        raise RuntimeError(f"parsebench2 scorer failed for {subset}: {(proc.stdout + proc.stderr)[-2000:]}")
    return json.loads(rep.read_text())


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    gt = gt_dir(pages)
    subsets = sorted({_subset(p) for p in pages})
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)

    def one(s: str) -> dict:
        if not any((out_dir / "results" / s).glob("*.result.json")):
            return {}
        return _evaluate(out_dir / "results" / s, gt / s, s, out_dir / "reports" / s)

    with ThreadPoolExecutor(4) as ex:
        reps = dict(zip(subsets, ex.map(one, subsets), strict=True))
    per: dict[tuple[str, str], dict] = {}
    for s, rep in reps.items():
        for r in rep.get("per_example_results") or []:
            per[(s, r["test_id"])] = {
                "metrics": {m["metric_name"]: m["value"] for m in r.get("metrics") or []},
                "success": r.get("success"),
                "error": r.get("error"),
            }
    missing = set(json.loads((out_dir / "missing.json").read_text()))
    n_by_subset = {s: sum(_subset(p) == s for p in pages) for s in subsets}
    rows, by_subset = [], {s: [] for s in subsets}
    for p in pages:
        s = _subset(p)
        dim, metric, _ = SLOTS[s]
        if p["page_key"] in missing:
            by_subset[s].append(0.0)  # the scorer's own convention: a failed parse is blank output
            continue
        res = per.get((s, _test_id(p)), {})
        m = res.get("metrics", {})
        v = m.get(metric)
        by_subset[s].append(0.0 if v is None else float(v))
        rows.append(
            {
                "page_key": p["page_key"],
                "score": None if s == "layout" or v is None else 100.0 * float(v),
                "subscores": {
                    "subset": s,
                    "dimension": dim,
                    "headline": v,
                    "error": res.get("error"),
                    **{k: x for k, x in m.items() if isinstance(x, (int, float))},
                },
                "scorer_commit": SCORER_COMMIT,
                "warnings": [WARN_LAYOUT] if s == "layout" else [],
            }
        )
    dims: dict[str, dict] = {}
    for s, vals in by_subset.items():
        dim, metric, w = SLOTS[s]
        e = dims.setdefault(dim, {"num": 0.0, "w": 0.0, "subsets": {}})
        mean = 100.0 * sum(vals) / len(vals) if vals else None
        e["subsets"][s] = {"metric": metric, "score": mean, "pages": n_by_subset[s], "weight": w}
        if mean is not None:
            e["num"] += w * mean
            e["w"] += w
    official = {"scorer_commit": SCORER_COMMIT, "data_revision": DATA_REVISION, "dimensions": {}}
    for dim, e in dims.items():
        mean = e["num"] / e["w"] if e["w"] else None
        official["dimensions"][dim] = {"score": mean, "subsets": e["subsets"]}
    head = [v["score"] for k, v in official["dimensions"].items() if k != "Layout" and v["score"] is not None]
    official["overall_no_layout"] = sum(head) / len(head) if head else None
    official["overall_dimensions"] = sorted(k for k in official["dimensions"] if k != "Layout")
    (out_dir / "official.json").write_text(json.dumps(official, indent=1))
    return rows
