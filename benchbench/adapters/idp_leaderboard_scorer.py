"""Run inside the IDP scorer environment (pinned idp-leaderboard-benchmarks + docext), not the benchbench
venv.

argv: <in.jsonl> <out.jsonl>. In rows {"page_key", "dataset", "annotation", "responses": {name: str}}.
Out rows {"page_key", "scores": {name: float}, "pred_shape": {name: [rows, cols]}, "gt_shape"}.
GT is built as docext NanonetsTableBench._load_data builds it; predictions go through the leaderboard's own
_build_prediction and _score_predictions (benchmarks/idp/evaluate.py), unmodified.
"""

import json
import os
import sys
from io import StringIO
from multiprocessing import Pool

import pandas as pd
from benchmarks.idp.evaluate import _build_prediction, _score_predictions
from docext.benchmark.vlm_datasets.ds import BenchmarkData, ExtractionType, Table


def _one(line: str) -> str:
    r = json.loads(line)
    label = pd.read_json(StringIO(r["annotation"]), orient="records")
    gt = BenchmarkData(
        image_paths=[f"{r['page_key']}.png"],
        extraction_type=ExtractionType.TABLE,
        tables=[Table(table=label, columns=label.columns.tolist())],
    )
    scores, shapes, errors = {}, {}, {}
    for name, resp in r["responses"].items():
        try:
            pred = _build_prediction(gt, resp, "TABLE")
        except Exception as e:  # upstream evaluate.py catches this and drops the page from the mean
            scores[name], shapes[name], errors[name] = None, None, f"{type(e).__name__}: {str(e)[:300]}"
            continue
        shapes[name] = list(pred.pred.tables[0].table.shape) if pred.pred.tables else None
        try:
            scores[name] = float(_score_predictions([pred], "TABLE", r["dataset"]))
        except Exception as e:  # GriTS raises on some HTML (e.g. no cells); upstream has no handler here
            scores[name], errors[name] = None, f"scoring {type(e).__name__}: {str(e)[:300]}"
    row = {
        "page_key": r["page_key"],
        "scores": scores,
        "pred_shape": shapes,
        "gt_shape": list(label.shape),
        "errors": errors,
    }
    return json.dumps(row)


def main(inp: str, out: str) -> None:
    with open(inp) as f:
        lines = [x for x in f if x.strip()]
    with Pool(int(os.environ.get("IDP_SCORER_PROCS", os.cpu_count() or 4))) as pool:
        res = pool.map(_one, lines, chunksize=1)
    with open(out, "w") as w:
        w.write("".join(x + "\n" for x in res))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
