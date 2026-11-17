"""Runs under the OmniParseBench scorer's own Python (see omniparsebench.py). Not imported by BenchBench.

usage: python omniparsebench_runner.py JOBS_JSONL OUT_DIR
Writes OUT_DIR/rows.jsonl (one native row per page) and OUT_DIR/lines.jsonl (one line per test, as
`unit_tests.lines` gives them, for the benchmark's pooled headline).
"""

import json
import sys
from pathlib import Path

from omni_parse_bench import data, markdown, vocab
from omni_parse_bench.harness import errors
from omni_parse_bench.harness.providers import azure, extend, llamaparse, mistral, reducto
from omni_parse_bench.scorers import unit_tests
from omni_parse_bench.scorers.unit_tests import compare
from omni_parse_bench.scorers.unit_tests import tests as gold_tests


def _azure_di(raw: dict) -> list[dict]:
    """Azure Document Intelligence prebuilt-layout (what Parse Judge calls) in the shape the benchmark's
    Azure Content Understanding adapter reads: same paragraphs, tables and figures, `boundingRegions` as
    `D(page,polygon)` sources and the first span as `span`."""
    a = raw["analyzeResult"]

    def src(x: dict) -> str:
        r = (x.get("boundingRegions") or [{}])[0]
        return f"D({r.get('pageNumber', 0)},{','.join(str(v) for v in r.get('polygon') or [])})"

    def one(x: dict) -> dict:
        return x | {"source": src(x), "span": (x.get("spans") or [{}])[0]}

    content = {
        "pages": a.get("pages") or [],
        "paragraphs": [one(p) for p in a.get("paragraphs") or []],
        "tables": [one(t) for t in a.get("tables") or []],
        "figures": [one(f) for f in a.get("figures") or []],
    }
    return azure.layout_blocks(content)


def _reducto(raw: dict) -> list[dict]:
    chunks = (raw.get("result") or {}).get("chunks") or []
    return reducto.layout_blocks([b for c in chunks for b in c.get("blocks") or []])


def _extend(raw: dict) -> list[dict]:
    out = raw.get("output") or {}
    pages = (out.get("metadata") or {}).get("pages") or []
    turned = next((x.get("rotationApplied") or 0 for x in pages if x.get("number", 1) == 1), 0)
    return extend.layout_blocks([b for c in out.get("chunks") or [] for b in c.get("blocks") or []], turned)


def _mistral(raw: dict) -> list[dict]:
    return mistral.layout_blocks(raw["pages"][0])


def _llamaparse(raw: dict) -> list[dict] | None:
    items = [p for p in (raw.get("items") or {}).get("pages") or [] if p.get("page_number", 1) == 1]
    return llamaparse.layout_blocks(items[0]) if items else None


BLOCKS = {
    "reducto_r1": ("reducto.layout_blocks", _reducto),
    "extend_performance_agentic": ("extend.layout_blocks", _extend),
    "mistral_ocr_4_1": ("mistral.layout_blocks", _mistral),
    "azure_layout_high_res": ("azure.layout_blocks on Document Intelligence output reshaped", _azure_di),
    "llamaparse_agentic_plus": ("llamaparse.layout_blocks", _llamaparse),
}
BLOCKS["azure_layout_high_res_formulas"] = BLOCKS["azure_layout_high_res"]
BLOCKS["extend_performance_agentic_formulas"] = BLOCKS["extend_performance_agentic"]


def prediction(job: dict) -> tuple[dict, list[str]]:
    p = json.loads(Path(job["parse"]).read_text()) if Path(job["parse"]).exists() else None
    if not p or not p.get("ok"):
        return {}, ["parse failed or missing: every test fails"]
    raw, preset = p.get("raw"), job["preset"]
    md, warns = p.get("markdown") or "", []
    if p.get("base_preset", preset).startswith("azure_layout_high_res"):
        # The scorer's Azure reader unwraps Azure's page header, footer and number comments (azure.parse).
        md = azure.PAGE_MARKER.sub(lambda m: m[1], md)
        warns.append("page header/footer/number comments unwrapped as azure.parse does")
    pred = {"html": markdown.to_html(md)}
    if job.get("blocks_file"):
        b = Path(job["blocks_file"])
        got = json.loads(b.read_text()) if b.exists() else {}
        if got.get("ok"):
            pred["blocks"] = got["blocks"]
            warns.append("blocks via datalab.blocks on a separate output_format=chunks call")
        else:
            warns.append(f"no blocks: datalab chunks call failed: {str(got.get('error'))[:200]}")
        return pred, warns
    if preset not in BLOCKS:
        warns.append("unsupported: the scorer has no box reader for this vendor (no layout headline)")
        return pred, warns
    if not isinstance(raw, dict):
        warns.append("no blocks: raw response missing (layout tests fail)")
        return pred, warns
    if preset.startswith("llamaparse") and raw.get("items") is None:
        # The preset does not request expand=items, the only place LlamaParse returns boxes.
        warns.append("unsupported: this preset's response has no item boxes (no layout headline)")
        return pred, warns
    how, fn = BLOCKS[preset]
    try:
        got = fn(raw)
    except (errors.SystemFailed, KeyError, IndexError, TypeError, ValueError) as e:
        got = None
        warns.append(f"no blocks: {how} failed: {str(e)[:200]}")
    if got is None:
        if not warns:
            warns.append("no blocks: raw response holds no boxes (layout tests fail)")
    else:
        pred["blocks"] = got
        warns.append(f"blocks via {how}")
    return pred, warns


def manifest() -> dict[str, dict]:
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        "datalab-to/omni_parse_bench",
        "manifest.parquet",
        repo_type="dataset",
        revision="d70182b9f901d1660a27e60bf6be6d6e6ea83013",
    )
    return {r["page_id"]: r for r in pq.read_table(path).to_pylist()}


def main(jobs_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    rows_by_id = manifest()
    rows, lines = [], []
    for line in Path(jobs_path).read_text().splitlines():
        job = json.loads(line)
        tests = gold_tests.read(job["gold"])
        m = rows_by_id[job["page_id"]]
        page = data.Page(job["page_id"], m["document"], m["suite"], Path(job["parse"]), Path(job["gold"]), ())
        pred, warns = prediction(job)
        ls = unit_tests.lines(compare.score(pred, tests), tests, page)
        for x in ls:
            x["page_key"], x["preset"] = job["page_key"], job["preset"]
            x["layout_supported"] = not any(w.startswith("unsupported") for w in warns)
        lines += ls
        fam: dict[str, list[int]] = {}
        for x in ls:
            c = fam.setdefault(vocab.FAMILIES[x["test_type"]], [0, 0])
            c[0] += x["result"] == "pass"
            c[1] += 1
        unsupported = any(w.startswith("unsupported") for w in warns)
        if unsupported:
            fam.pop("layout", None)
        rates = {f: k / n for f, (k, n) in fam.items()}
        tt = [rates[f] for f in ("text", "tables") if f in rates]
        rows.append(
            {
                "page_key": job["page_key"],
                "score": 100 * sum(tt) / len(tt) if tt else None,
                "subscores": {
                    **{f: 100 * r for f, r in rates.items()},
                    "text_tables": 100 * sum(tt) / len(tt) if tt else None,
                    "three_family": None if unsupported else 100 * sum(rates.values()) / len(rates),
                    "layout_supported": not unsupported,
                    "counts": {f: {"passed": k, "tests": n} for f, (k, n) in fam.items()},
                    "has_blocks": "blocks" in pred,
                },
                "warnings": warns,
            }
        )
    (out / "rows.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    (out / "lines.jsonl").write_text(
        "".join(
            json.dumps({k: v for k, v in x.items() if k not in ("args", "settings")}, ensure_ascii=False)
            + "\n"
            for x in lines
        )
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
