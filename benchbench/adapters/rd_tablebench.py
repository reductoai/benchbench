"""RD-TableBench native scorer (reductoai/rd-tablebench, pinned; scorer code is imported, not edited).

The benchmark scores one table per page: rd-tablebench/parsing.py takes the largest HTML table (by string
length) from each vendor's output, convert.html_to_numpy expands rowspan/colspan, and
grading.table_similarity aligns it with the ground truth (0-1). Our parses are markdown, so:

- "as returned" (subscore `as_returned`): only HTML <table> blocks in the parse are candidates.
- "after documented conversion" (`score`, primary): markdown pipe tables are converted to HTML first
  (probes.pipe_table_to_html), then the largest candidate is scored.
A parse with no table scores 0 (warning `no_table`); a failed parse has score None.
Scores are similarity x 100.
"""

import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..datasets import CACHE, _extract, _stem
from ..probes import PIPE_TABLE, TABLE_HTML, pipe_table_to_html
from ..storage import read_json, write_json

SCORER_REPO = "https://github.com/reductoai/rd-tablebench"
SCORER_COMMIT = "1cae108e6395ddc8389af17385f9769519070558"


def scorer_dir() -> Path:
    root = Path(os.environ.get("RD_TABLEBENCH_DIR", CACHE / f"rd-tablebench-{SCORER_COMMIT[:12]}"))
    if not root.exists():
        subprocess.run(["git", "clone", "-q", SCORER_REPO, str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", SCORER_COMMIT], check=True)
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "grading.py", "convert.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if head != SCORER_COMMIT or dirty:
        raise RuntimeError(f"{root} is at {head} (dirty={bool(dirty)}); need clean {SCORER_COMMIT}")
    return root


def _load(name: str):
    path = scorer_dir() / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"rd_tablebench_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _gt_path(page: dict) -> Path:
    from ..catalog import load_catalog

    root = _extract(load_catalog()["rd_tablebench"])
    return root / "rd-tablebench" / "groundtruth" / f"{_stem(page['file'])}.html"


def gt_markdown(page: dict) -> str | None:
    p = _gt_path(page)
    return p.read_text() if p.exists() else None


def candidate_tables(md: str) -> tuple[list[str], list[str]]:
    """(HTML tables as returned, pipe tables converted to HTML)."""
    html = TABLE_HTML.findall(md)
    pipes = [pipe_table_to_html(m.group(0)) for m in PIPE_TABLE.finditer(TABLE_HTML.sub("", md))]
    return html, pipes


def largest(tables: list[str]) -> str | None:
    return max(tables, key=len) if tables else None


def export(run, cond, preset, pages, out_dir: Path) -> None:
    for p in pages:
        parse = read_json(run.parse(cond, preset, p["page_key"]))
        md = (parse or {}).get("markdown") or "" if (parse or {}).get("ok") else None
        html, pipes = candidate_tables(md or "")
        write_json(
            out_dir / f"{p['page_key']}.json",
            {
                "page_key": p["page_key"],
                "parse_ok": md is not None,
                "gt": str(_gt_path(p)),
                "as_returned": largest(html),
                "converted": largest(html + pipes),
                "n_html_tables": len(html),
                "n_pipe_tables": len(pipes),
            },
        )


_SCORER = None


def _similarity(gt_html: str, pred_html: str | None) -> tuple[float, str | None]:
    global _SCORER
    if _SCORER is None:
        _SCORER = (_load("convert").html_to_numpy, _load("grading").table_similarity)
    to_np, sim = _SCORER
    if not pred_html:
        return 0.0, "no_table"
    try:
        pred = to_np(pred_html)
        if pred.size == 0:
            return 0.0, "empty_table"
        return float(sim(to_np(gt_html), pred)), None
    except Exception as e:  # the scorer itself raised on this table: score 0 and record it
        return 0.0, f"scorer_error: {type(e).__name__}: {str(e)[:120]}"


def _score_file(path: str) -> dict:
    e = json.loads(Path(path).read_text())
    gt = Path(e["gt"]).read_text()
    conv, w1 = _similarity(gt, e["converted"])
    raw, w2 = _similarity(gt, e["as_returned"]) if e["as_returned"] != e["converted"] else (conv, w1)
    warnings = [w for w in {w1, w2} if w]
    if not e["parse_ok"]:
        warnings.append("parse_failed")
    if e["as_returned"] != e["converted"]:
        warnings.append(f"converted_pipe_table (html {e['n_html_tables']}, pipe {e['n_pipe_tables']})")
    return {
        "page_key": e["page_key"],
        # A failed parse has no native score in the primary analysis (same rule as the judge).
        "score": 100 * conv if e["parse_ok"] else None,
        "subscores": {"as_returned": 100 * raw, "after_conversion": 100 * conv},
        "parse_ok": e["parse_ok"],
        "scorer_commit": SCORER_COMMIT,
        "warnings": sorted(warnings),
    }


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    scorer_dir()
    files = [str(out_dir / f"{p['page_key']}.json") for p in pages]
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        return list(ex.map(_score_file, files, chunksize=4))
