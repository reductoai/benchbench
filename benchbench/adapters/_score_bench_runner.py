"""Runs inside the unstructured-eval-metrics venv (PYTHONPATH=<uem>/src). Calls the scorer's public
by-filename functions unmodified; writes scores.json next to the manifest."""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from scoring.cct_adjustment import score_cct_adjustment_by_filename
from scoring.content_scoring import (
    score_cct_by_filename,
    score_tokens_added_by_filename,
    score_tokens_found_by_filename,
)
from scoring.table_scoring import score_tables_by_filename


def one(m: dict) -> dict:
    row = {"page_key": m["page_key"], "ok": m["ok"]}
    try:
        cct = score_cct_by_filename(m["conv"], m["gt"])
        row["score"] = round(100 * cct, 4)
        row["cct"] = cct
        row["cct_as_returned"] = score_cct_by_filename(m["asis"], m["gt"], sample_format="plain_text_v1")
        row["cct_adjusted"] = score_cct_adjustment_by_filename(m["conv"], m["gt"])
        row["tokens_found"] = score_tokens_found_by_filename(m["conv"], m["gt"])
        row["tokens_added"] = score_tokens_added_by_filename(m["conv"], m["gt"])
        if m["gt_table"]:
            t = score_tables_by_filename(
                m["conv"], m["gt_table"], sample_format="html", ground_truth_format="text"
            )
            t = t.scores
            row["tables_overall"] = t.overall
            row["tables_detection_f"] = t.detection_f
            row["tables_content_acc"] = t.cell_level_content_acc
    except Exception as e:  # noqa: BLE001
        row.setdefault("score", 0.0)
        row["error"] = f"{type(e).__name__}: {e}"[:300]
    return row


if __name__ == "__main__":
    manifest = Path(sys.argv[1])
    items = json.loads(manifest.read_text())
    with ProcessPoolExecutor(int(sys.argv[2])) as ex:
        rows = list(ex.map(one, items, chunksize=4))
    (manifest.parent / "scores.json").write_text(json.dumps(rows))
