"""IDP Leaderboard, IDP Core TABLE part: GriTS-Con per page via the leaderboard's own evaluate.py + docext.

The leaderboard asks a VLM for JSON or HTML and passes the raw reply to _parse_table_response, which reads
HTML (<table>) or JSON. Parsers return Markdown, often with pipe tables, which that function reads as an
empty table. Headline score ("native"): pipe tables converted to HTML first (recorded in warnings).
Subscore "as_is": the Markdown passed unchanged, which shows the format penalty a raw parse would get.
Only the first table counts (docext metrics/tables.py uses tables[0]). Score = 100 x GriTS-Con.
When the upstream code raises building the prediction (e.g. a multi-row header read as a pandas MultiIndex),
evaluate.py drops the page from the mean; here it scores 0 so pages stay paired, flagged upstream_dropped.
"""

import html
import json
import os
import subprocess
from pathlib import Path

from ..catalog import load_catalog
from ..datasets import parquet_row
from ..probes import PIPE_TABLE, TABLE_HTML, pipe_table_to_html
from ..storage import read_json, write_jsonl

HOME = Path.home() / "work"
BENCH_DIR = Path(os.environ.get("IDP_BENCH_DIR", HOME / "idp-leaderboard-benchmarks"))
SCORER_PY = os.environ.get("IDP_SCORER_PYTHON", str(HOME / "idp-scorer-venv" / "bin" / "python"))
SCORER = Path(__file__).with_name("idp_leaderboard_scorer.py")


def _bench() -> dict:
    return load_catalog()["idp_leaderboard"]


def _commit() -> str:
    b = _bench()
    return f"idp-leaderboard-benchmarks@{b['harness_commit'][:12]}+docext@{b['scorer_commit'][:12]}"


def gt_markdown(page: dict) -> str | None:
    """Ground truth as one HTML table; the header row holds the column names, as drawn on the page."""
    cols = json.loads(parquet_row(_bench(), page["file"])["annotation"])
    names = list(cols)
    # Row keys can skip numbers (27 sparse pages); keep their order, as pandas does.
    keys = sorted({k for v in cols.values() for k in v}, key=int)

    def cell(tag, v):
        return f"<{tag}>{html.escape('' if v is None else str(v))}</{tag}>"

    rows = ["<tr>" + "".join(cell("th", c) for c in names) + "</tr>"]
    for k in keys:
        rows.append("<tr>" + "".join(cell("td", cols[c].get(k)) for c in names) + "</tr>")
    return "<table>" + "".join(rows) + "</table>\n"


def convert(md: str) -> tuple[str, list[str]]:
    """Pipe tables -> HTML so the leaderboard parser can read them. HTML tables pass unchanged."""
    warnings = []
    n_pipe = len(PIPE_TABLE.findall(md))
    if n_pipe:
        md = PIPE_TABLE.sub(lambda m: pipe_table_to_html(m.group(0)), md)
        warnings.append(f"converted {n_pipe} pipe table(s) to HTML")
    n_tables = len(TABLE_HTML.findall(md))
    if n_tables == 0:
        warnings.append("no table found")
    elif n_tables > 1:
        warnings.append(f"{n_tables} tables; scorer uses the first")
    return md, warnings


def export(run, cond, preset, pages, out_dir) -> None:
    rows = []
    for p in pages:
        parse = read_json(run.parse(cond, preset, p["page_key"]))
        if not parse or not parse.get("ok"):
            continue
        md = parse.get("markdown") or ""
        conv, warnings = convert(md)
        rows.append(
            {
                "page_key": p["page_key"],
                "dataset": "nanonets_" + p["stratum"],
                "annotation": parquet_row(_bench(), p["file"])["annotation"],
                "responses": {"native": conv, "as_is": md},
                "warnings": warnings,
            }
        )
    write_jsonl(Path(out_dir) / "in.jsonl", rows)


def score(run, cond, preset, pages, out_dir) -> list[dict]:
    out_dir = Path(out_dir).resolve()
    inp, out = out_dir / "in.jsonl", out_dir / "out.jsonl"
    rows = [json.loads(x) for x in inp.read_text().splitlines() if x.strip()]
    if not rows:
        return []
    proc = subprocess.run(
        [SCORER_PY, str(SCORER), str(inp), str(out)],
        cwd=BENCH_DIR,
        env={**os.environ, "PYTHONPATH": str(BENCH_DIR)},
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        raise RuntimeError(f"IDP scorer failed: {proc.stderr[-2000:]}")
    scored = {r["page_key"]: r for r in map(json.loads, out.read_text().splitlines())}
    res = []
    for r in rows:
        s = scored[r["page_key"]]
        err = s.get("errors", {})
        warnings = list(r["warnings"])
        crash = err.get("native", "").startswith("scoring")
        if crash:
            warnings.append(
                f"upstream GriTS crashes on this page, scored 0 (evaluate.py has no handler): {err['native']}"
            )
        elif "native" in err:
            warnings.append(
                f"upstream scorer error, scored 0 (the leaderboard drops this page): {err['native']}"
            )
        res.append(
            {
                "page_key": r["page_key"],
                "score": 100 * (s["scores"]["native"] or 0.0),
                "subscores": {
                    "as_is": 100 * (s["scores"]["as_is"] or 0.0),
                    "upstream_dropped": "native" in err and not crash,
                    "upstream_crash": crash,
                    "dataset": r["dataset"],
                    "pred_shape": s["pred_shape"]["native"],
                    "gt_shape": s["gt_shape"],
                },
                "scorer_commit": _commit(),
                "warnings": warnings,
            }
        )
    return res
