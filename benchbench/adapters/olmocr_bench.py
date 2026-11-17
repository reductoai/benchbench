"""Native scorer adapter for olmOCR-bench (allenai/olmocr, olmocr/bench).

The scorer is a set of pass/fail unit tests per PDF page (`bench_data/*.jsonl`): text present / absent,
reading order, table cell neighbours, math (KaTeX-rendered comparison) and a baseline sanity test that
`benchmark.py` adds to every PDF without one. We run the pinned scorer's own test classes, unmodified, on
each parse in a separate interpreter that has `olmocr[bench]` installed (OLMOCR_PYTHON, OLMOCR_DIR).

Per-page score: share of that page's tests that pass, 0-100. One repeat per page, so each test passes or
fails outright (benchmark.py's majority rule over repeats reduces to this). `benchmark_aggregate()` gives
benchmark.py's headline: the mean of per-JSONL-file pass rates (plus the "baseline" group).
"""

import json
import os
import subprocess
from functools import cache
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

from huggingface_hub import hf_hub_download

from ..storage import Run, read_json

SCORER_REPO = "https://github.com/allenai/olmocr"
SCORER_COMMIT = "f7cfe4c22098b154c76b6ec950d1c0a464eecf8d"
HF_REPO, HF_REVISION = "allenai/olmOCR-bench", "54a96a6fb6a2"
SUITES = (
    "arxiv_math",
    "headers_footers",
    "long_tiny_text",
    "multi_column",
    "old_scans",
    "old_scans_math",
    "table_tests",
)
RUNNER = Path(__file__).with_name("_olmocr_runner.py")


def _pdf(page: dict) -> str:
    return page["file"].removeprefix("bench_data/pdfs/")


@cache
def all_tests() -> dict[str, list[dict]]:
    """pdf (relative to bench_data/pdfs) -> its test dicts, each tagged with `_suite`. Adds the baseline test
    benchmark.py adds to every PDF that has none."""
    by_pdf: dict[str, list[dict]] = {}
    for suite in SUITES:
        path = hf_hub_download(
            HF_REPO, f"bench_data/{suite}.jsonl", repo_type="dataset", revision=HF_REVISION
        )
        for line in open(path):
            if line.strip():
                t = json.loads(line)
                by_pdf.setdefault(t["pdf"], []).append({**t, "_suite": suite})
    for pdf, tests in by_pdf.items():
        if not any(t["type"] == "baseline" for t in tests):
            tests.append(
                {"id": f"{pdf}_baseline", "pdf": pdf, "page": 1, "type": "baseline", "_suite": "baseline"}
            )
    return by_pdf


def _md_path(out_dir: Path, pdf: str) -> Path:
    return out_dir / "md" / f"{os.path.splitext(pdf)[0]}_pg1_repeat1.md"


def export(run: Run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> None:
    """Write one `<pdf>_pg1_repeat1.md` per ok parse (benchmark.py's candidate layout) and the page tests."""
    rows = []
    for p in pages:
        pdf = _pdf(p)
        path = _md_path(out_dir, pdf)
        if path.exists():
            path.unlink()
        parse = read_json(run.parse(cond, preset, p["page_key"]))
        if parse and parse.get("ok"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(parse.get("markdown") or "", encoding="utf-8")
        rows += all_tests().get(pdf, [])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def _python() -> str:
    return os.environ.get("OLMOCR_PYTHON", str(Path.home() / "olmocr-venv" / "bin" / "python"))


@cache
def _check_scorer() -> str:
    d = os.environ.get("OLMOCR_DIR", str(Path.home() / "repos" / "olmocr"))
    head = subprocess.run(
        ["git", "-C", d, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", d, "status", "--porcelain", "olmocr/bench"], capture_output=True, text=True
    )
    if head != SCORER_COMMIT or dirty.stdout.strip():
        raise SystemExit(
            f"olmocr checkout {d} is at {head or '?'} "
            f"(dirty={bool(dirty.stdout.strip())}); need {SCORER_COMMIT}"
        )
    imported = subprocess.run(
        [_python(), "-c", "import olmocr.bench.tests as t; print(t.__file__)"], capture_output=True, text=True
    ).stdout.strip()
    if not imported.startswith(d):
        raise SystemExit(f"{_python()} imports olmocr from {imported}, not {d}")
    return head


def score(run: Run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> list[dict]:
    commit = _check_scorer()
    res_path = out_dir / "results.json"
    subprocess.run(
        [_python(), str(RUNNER), str(out_dir / "tests.jsonl"), str(out_dir / "md"), str(res_path)], check=True
    )
    by_pdf: dict[str, list[dict]] = {}
    for r in json.loads(res_path.read_text()):
        by_pdf.setdefault(r["pdf"], []).append(r)
    rows = []
    for p in pages:
        results = by_pdf.get(_pdf(p), [])
        if not results or any(r["passed"] is None for r in results):
            continue  # failed parse: no native score (primary analysis drops the page)
        passed = sum(r["passed"] for r in results)
        suites: dict[str, list[int]] = {}
        for r in results:
            suites.setdefault(r["suite"], [0, 0])
            suites[r["suite"]][0] += int(r["passed"])
            suites[r["suite"]][1] += 1
        rows.append(
            {
                "page_key": p["page_key"],
                "score": 100.0 * passed / len(results),
                "subscores": {
                    "tests": len(results),
                    "passed": passed,
                    "by_suite": suites,
                    "by_type": _by(results, "type"),
                    "results": [
                        [r["id"], r["suite"], r["type"], r["passed"], r["why"][:160]] for r in results
                    ],
                },
                "scorer_commit": commit,
                "warnings": [],
            }
        )
    return rows


def _by(results: list[dict], key: str) -> dict:
    out: dict[str, list[int]] = {}
    for r in results:
        out.setdefault(r[key], [0, 0])
        out[r[key]][0] += int(r["passed"])
        out[r[key]][1] += 1
    return out


def benchmark_aggregate(rows: list[dict]) -> dict:
    """benchmark.py's headline over the given page rows: mean over JSONL files of each file's pass rate."""
    per: dict[str, list[int]] = {}
    for row in rows:
        for _id, suite, _type, passed, _why in row["subscores"]["results"]:
            per.setdefault(suite, [0, 0])
            per[suite][0] += int(passed)
            per[suite][1] += 1
    rates = {s: 100.0 * a / b for s, (a, b) in per.items() if b}
    return {
        "overall": sum(rates.values()) / len(rates) if rates else None,
        "by_suite": rates,
        "tests": {s: b for s, (a, b) in per.items()},
    }


def gt_markdown(page: dict) -> str | None:
    """Ground truth written as a parse: every `present` text, `order` texts in a consistent order, each `math`
    test as a display equation, and one small HTML table per `table` test with its stated neighbours and
    headings. Nothing an `absent` test forbids is written."""
    tests = all_tests().get(_pdf(page), [])
    if not tests:
        return None
    graph: dict[str, set[str]] = {}
    texts: list[str] = []
    for t in tests:
        if t["type"] == "present":
            texts.append(t["text"])
        elif t["type"] == "order":
            texts += [t["before"], t["after"]]
            graph.setdefault(t["after"], set()).add(t["before"])
    for x in texts:
        graph.setdefault(x, set())
    try:
        ordered = list(TopologicalSorter(graph).static_order())
    except CycleError:
        ordered = list(dict.fromkeys(texts))
    parts = [x for x in ordered if not any(x != y and x in y for y in ordered)]
    for t in tests:
        if t["type"] == "math":
            parts.append(f"\\[{t['math']}\\]")
        elif t["type"] == "table":
            parts.append(_table(t))
    # Pages tested only for absent headers/footers have no recorded body; a blank page would fail the
    # baseline test, so the probe writes a neutral line.
    return "\n\n".join(parts or ["Body text."]) + "\n"


def _table(t: dict) -> str:
    """A minimal HTML table that satisfies one table test: header row (top_heading), up, the cell row with
    left_heading/left/cell/right, down."""
    import html as h

    cols = (
        (["lh"] if t.get("left_heading") else [])
        + (["l"] if t.get("left") else [])
        + ["c"]
        + (["r"] if t.get("right") else [])
    )
    ci = cols.index("c")

    def row(cells: dict[int, str], tag: str = "td", first_th: bool = False) -> str:
        out = []
        for i in range(len(cols)):
            tg = "th" if tag == "th" or (first_th and i == 0) else "td"
            out.append(f"<{tg}>{h.escape(cells.get(i, ''))}</{tg}>")
        return "<tr>" + "".join(out) + "</tr>"

    rows = []
    if t.get("top_heading"):
        rows.append(row({ci: t["top_heading"]}, "th"))
    if t.get("up"):
        rows.append(row({ci: t["up"]}))
    main = {ci: t["cell"]}
    if t.get("left"):
        main[cols.index("l")] = t["left"]
    if t.get("right"):
        main[cols.index("r")] = t["right"]
    if t.get("left_heading"):
        main[0] = t["left_heading"]
    rows.append(row(main, first_th=bool(t.get("left_heading"))))
    if t.get("down"):
        rows.append(row({ci: t["down"]}))
    return "<table>" + "".join(rows) + "</table>"
