"""Write pair_minimal.csv: minimal-prompt PAIR means per benchmark, preset and condition.

Input: BenchBench run dirs (RUNS, default results/runs) with judge/<cond>/minimal-gpt-6.1-sol-medium-r*/ from
`benchbench judge --prompt minimal`. Mean of the 1-10 score over the pages judged in that condition.
"""

import csv
import json
import os
import pathlib
from statistics import mean

root = pathlib.Path(
    os.environ.get("BENCHBENCH_RESULTS", pathlib.Path(__file__).resolve().parents[1] / "results")
)
DATA = json.loads((root / "data.json").read_text())["benchmarks"]
NAMES = [b["id"] for b in DATA]
PRESETS = [v["preset"] for v in DATA[0]["vendors"]]
RUNS = pathlib.Path(
    os.environ.get("BENCHBENCH_RUNS", str(pathlib.Path(__file__).resolve().parents[1] / "results/runs"))
).expanduser()
TAG = "minimal-gpt-6.1-sol-medium-r"
rows = []
for b in NAMES:
    for cond, key in (("clean", "min_clean"), ("tilt_2_4", "min_tilt")):
        scores = {p: [] for p in PRESETS}
        pages = 0
        for d in sorted((RUNS / b / "judge" / cond).glob(TAG + "*")):
            for f in d.glob("*.json"):
                if f.name.endswith(".raw.json"):
                    continue
                v = json.loads(f.read_text())
                if not v.get("ok"):
                    continue
                pages += 1
                for x in v["verdicts"]:
                    scores[x["presetId"]].append(x["score"])
        for p in PRESETS:
            if scores[p]:
                rows.append(
                    {
                        "benchmark": b,
                        "preset": p,
                        "field": key,
                        "score": round(mean(scores[p]), 3),
                        "pages": pages,
                    }
                )
with open(root / "pair_minimal.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, ["benchmark", "preset", "field", "score", "pages"])
    w.writeheader()
    w.writerows(rows)
