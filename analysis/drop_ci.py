"""Write drop_ci.csv: 90% paired-bootstrap interval of each parser's clean-to-rotated change, in % of clean.

RUNS (default results/runs) holds BenchBench run dirs with judge/<cond>/<tag>/*.json and
native/<cond>/<preset>/scores.jsonl.
Pages are resampled (2000 draws, seed 0) among pages scored in both conditions; the interval is the bootstrap
spread placed around the change shown on the page. Native intervals only where the native score is a page
mean.
"""

import csv
import json
import os
import pathlib

import numpy as np

root = pathlib.Path(
    os.environ.get("BENCHBENCH_RESULTS", pathlib.Path(__file__).resolve().parents[1] / "results")
)
DATA = json.loads((root / "data.json").read_text())["benchmarks"]
RUNS = pathlib.Path(
    os.environ.get("BENCHBENCH_RUNS", str(pathlib.Path(__file__).resolve().parents[1] / "results/runs"))
).expanduser()
PAGE_MEAN = {
    "dp_bench",
    "score_bench",
    "ocrflux_bench",
    "idp_leaderboard",
    "mdpbench",
    "rd_tablebench",
    "parsebench2",
}
JUDGES = {"gpt": ["gpt-6.1-sol-medium-r0", "gpt-6.1-sol-medium-r1"], "min": ["minimal-gpt-6.1-sol-medium-r0"]}


def judge_pages(b, cond, tags):
    out = {}
    for t in tags:
        d = RUNS / b / "judge" / cond / t
        for f in d.glob("*.json") if d.exists() else []:
            if f.name.endswith(".raw.json"):
                continue
            v = json.loads(f.read_text())
            if v.get("ok"):
                for x in v["verdicts"]:
                    out.setdefault(x["presetId"], {}).setdefault(f.stem, []).append(x["score"])
    return {p: {k: sum(s) / len(s) for k, s in pg.items()} for p, pg in out.items()}


def native_pages(b, cond, p):
    f = RUNS / b / "native" / cond / p / "scores.jsonl"
    if not f.exists():
        return {}
    return {r["page_key"]: r["score"] for r in map(json.loads, open(f)) if r.get("score") is not None}


def interval(c, t, rng):
    keys = [k for k in c if k in t]
    if len(keys) < 20:
        return None
    d = np.array([t[k] - c[k] for k in keys])
    boots = d[rng.integers(0, len(d), (2000, len(d)))].mean(1)
    lo, hi = np.quantile(boots, [0.05, 0.95])
    return lo - d.mean(), hi - d.mean()


rows = []
previous = {
    (r["benchmark"], r["preset"], r["metric"]): r for r in csv.DictReader((root / "drop_ci.csv").open())
}
for b in DATA:
    j = {
        m: (judge_pages(b["id"], "clean", tags), judge_pages(b["id"], "tilt_2_4", tags))
        for m, tags in JUDGES.items()
    }
    for v in b["vendors"]:
        p = v["preset"]
        for m in ("native", "gpt", "min"):
            if m == "min" or (m == "native" and p != "datalab_accurate"):
                if (b["id"], p, m) in previous:
                    rows.append(previous[b["id"], p, m])
                continue
            c0, c1 = v.get(m + "_clean"), v.get(m + "_tilt")
            if c0 is None or c1 is None:
                continue
            if m == "native":
                iv = (
                    interval(
                        native_pages(b["id"], "clean", p),
                        native_pages(b["id"], "tilt_2_4", p),
                        np.random.default_rng(0),
                    )
                    if b["id"] in PAGE_MEAN
                    else None
                )
            else:
                iv = interval(j[m][0].get(p, {}), j[m][1].get(p, {}), np.random.default_rng(0))
            delta = c1 - c0
            row = {
                "benchmark": b["id"],
                "preset": p,
                "metric": m,
                "drop_pct": round(100 * delta / c0, 3),
                "lo_pct": "",
                "hi_pct": "",
            }
            if iv:
                row["lo_pct"] = round(100 * (delta + iv[0]) / c0, 3)
                row["hi_pct"] = round(100 * (delta + iv[1]) / c0, 3)
            rows.append(row)
with open(root / "drop_ci.csv", "w", newline="") as fh:
    ending = "\r\n" if b"\r\n" in (root / "drop_ci.csv").read_bytes() else "\n"
    w = csv.DictWriter(fh, list(rows[0]), lineterminator=ending)
    w.writeheader()
    w.writerows(rows)
