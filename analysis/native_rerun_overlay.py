"""Overlay the 2026-11-11 native reruns on native_under_augment.csv.
Reads rerun CSVs (benchmark,condition,preset,stored,rerun,...) from argv[1]; where a rerun headline exists it
replaces the stored one (each cell on its own; a cell not rerun had inputs byte-identical to the stored
run), then deltas and ranks are recomputed. Writes native_under_augment_rerun.csv."""

import csv
import glob
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[1] / "results"))
rer, npages = {}, {}
for f in glob.glob(f"{sys.argv[1]}/native_rerun_*.csv"):
    for r in csv.DictReader(open(f)):
        try:
            rer[(r["benchmark"], r["condition"], r["preset"])] = float(r["rerun"])
            npages[(r["benchmark"], r["condition"], r["preset"])] = int(r["pages_scored_rerun"])
        except (ValueError, KeyError):
            pass
rows = list(csv.DictReader(open(HERE / "native_under_augment.csv")))
for r in rows:
    b, c, p = r["benchmark"], r["condition"], r["preset"]
    r["source"] = "stored"
    hit = [k for k in ((b, "clean", p), (b, c, p)) if k in rer]
    if (b, "clean", p) in rer:
        r["native_clean"] = f"{rer[(b, 'clean', p)]:.4f}"
    if (b, c, p) in rer:
        r["native_pert"] = f"{rer[(b, c, p)]:.4f}"
    r["source"] = (
        "rerun"
        if len(hit) == 2
        else "rerun clean"
        if (b, "clean", p) in rer
        else "rerun perturbed"
        if hit
        else "stored"
    )
    if (b, c, p) in npages and r["pages_both"] and int(r["pages_both"]) != npages[(b, c, p)]:
        print("page set differs", b, c, p, r["pages_both"], npages[(b, c, p)])
    r["native_delta"] = f"{float(r['native_pert']) - float(r['native_clean']):.4f}"
groups = defaultdict(list)
for r in rows:
    groups[(r["benchmark"], r["condition"])].append(r)
for g in groups.values():
    for key, col in (("native_clean", "native_clean_rank"), ("native_pert", "native_pert_rank")):
        vals = sorted((float(r[key]) for r in g), reverse=True)
        for r in g:
            r[col] = str(1 + sum(v > float(r[key]) for v in vals))
        tied = [v for v in set(vals) if vals.count(v) > 1]
        if tied:
            print("tie", g[0]["benchmark"], g[0]["condition"], key, tied)
with open(HERE / "native_under_augment_rerun.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("rerun cells", sum(r["source"] == "rerun" for r in rows), "of", len(rows))
