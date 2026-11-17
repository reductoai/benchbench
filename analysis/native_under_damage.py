"""Native scores on damaged pages: each benchmark's own headline metric, clean vs tilt_2_4, scan and
perspective.

python3 analysis/native_under_damage.py   writes native_under_damage.csv next to this file.
Extends native_under_tilt.py to all three synthetic damages. No scoring and no API calls: it collects the
native
scores already computed during each benchmark run, with the same aggregation as each benchmark's clean
headline.
"damaged" is the tilt (2-4 degree) headline; scan and perspective deltas are kept as columns.
Delta convention: damaged minus clean, negative means the parser lost score."""

import csv
import json
import os
import re
import statistics
from pathlib import Path

HERE = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[1] / "results"))
REPO = HERE.parent.parent
RUNS = Path(os.environ.get("BENCHBENCH_RUNS", HERE / "runs"))
CONDS = ["tilt_2_4", "scan", "perspective"]
DAMAGED = "tilt_2_4"  # tilt does the most damage: the worst of the three for most parsers
PAGE_MEAN = {"dp_bench", "score_bench", "ocrflux_bench", "idp_leaderboard", "rd_tablebench", "mdpbench"}
# SCORE-Bench Datalab: the stored native scores were stale; these are the re-run values
# (clean 80.29, tilt +0.0, scan +0.2, perspective +0.5), see scorer_findings.md.
OVERRIDE = {
    ("score_bench", "datalab_accurate"): {
        "clean": 80.29,
        "tilt_2_4": 80.29,
        "scan": 80.49,
        "perspective": 80.79,
    }
}

R = list(csv.DictReader(open(HERE / "results.csv")))
BENCH = list(dict.fromkeys(r["benchmark"] for r in R))
VN = {
    "reducto_r1": "Reducto",
    "llamaparse_agentic_plus": "LlamaParse",
    "datalab_accurate": "Datalab",
    "extend_performance_agentic_formulas": "Extend",
    "mistral_ocr_4_1": "Mistral OCR",
    "azure_layout_high_res_formulas": "Azure DI",
    "pulse_ultra_2": "Pulse",
    "cohere_parse_v5": "Cohere",
}


def show(b, path):
    return (HERE / "reports" / b / path).read_text()


def s3file(b, cond, preset, name):
    return RUNS / b / "native" / cond / preset / name


def page_scores(b, cond, preset):
    rows = map(json.loads, open(s3file(b, cond, preset, "scores.jsonl")))
    return {r["page_key"]: r["score"] for r in rows if r.get("score") is not None}


def md_table(text, header_start):
    lines = text.splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith(header_start))
    head = [c.strip() for c in lines[i].strip("|").split("|")]
    out = []
    for line in lines[i + 2 :]:
        if not line.startswith("|"):
            break
        out.append(dict(zip(head, [c.strip() for c in line.strip("|").split("|")], strict=False)))
    return out


def num(s):
    return float(re.search(r"[-+]?\d+(\.\d+)?", s.replace("**", "")).group())


def collect(b, presets):
    """{preset: {cond: (clean, damaged)}}, clean and damaged on the same aggregation."""
    out = {p: {} for p in presets}
    if b in PAGE_MEAN:
        for p in presets:
            c = page_scores(b, "clean", p)
            for k in CONDS:
                t = page_scores(b, k, p)
                keys = sorted(set(c) & set(t))
                out[p][k] = (statistics.mean(c[x] for x in keys), statistics.mean(t[x] for x in keys))
    elif b == "olmocr_bench":
        d = json.loads(show(b, "native_summary.json"))["final"]
        for p in presets:
            for k in CONDS:
                out[p][k] = (d["clean"][p]["overall"], d[k][p]["overall"])
    elif b == "omniparsebench":
        for r in md_table(show(b, "native_extra.md"), "| preset | clean | tilt_2_4 |"):
            if r["preset"] in presets:
                c = num(r["clean"])
                for k in CONDS:
                    out[r["preset"]][k] = (c, c + num(r[k]))
    elif b == "puredocbench":
        d = json.loads(show(b, "official_native.json"))
        for p in presets:
            for k in CONDS:
                out[p][k] = (d["clean"][p]["overall"], d[k][p]["overall"])
    elif b == "omnidocbench":
        d = json.loads(show(b, "analysis.json"))["official"]
        for p in presets:
            for k in CONDS:
                out[p][k] = (d[f"clean/{p}"]["overall"], d[f"{k}/{p}"]["overall"])
    elif b == "real5_omnidocbench":
        for p in presets:
            c = json.load(open(s3file(b, "clean", p, "official.json")))["overall"]
            for k in CONDS:
                out[p][k] = (c, json.load(open(s3file(b, k, p, "official.json")))["overall"])
    for (ob, op), v in OVERRIDE.items():
        if ob == b and op in out:
            out[op] = {k: (v["clean"], v[k]) for k in CONDS}
    return out


def ranks(v):
    order = sorted(v, key=lambda p: -v[p])
    return {p: order.index(p) + 1 for p in v}


rows = []
for b in BENCH:
    rr = {r["preset"]: r for r in R if r["benchmark"] == b}
    got = collect(b, list(rr))
    clean = {p: statistics.mean(got[p][k][0] for k in CONDS) for p in rr}
    dmg = {p: clean[p] + got[p][DAMAGED][1] - got[p][DAMAGED][0] for p in rr}
    rc, rd = ranks(clean), ranks(dmg)
    for p, r in rr.items():
        assert abs(clean[p] - float(r["native_clean"])) < 0.3, (b, p, clean[p], r["native_clean"])
        row = dict(
            benchmark=b,
            vendor=VN[p],
            preset=p,
            native_metric=r["native_metric"],
            native_clean=round(clean[p], 2),
        )
        for k in CONDS:
            row[f"delta_{k}"] = round(got[p][k][1] - got[p][k][0], 2)
        row.update(
            native_damaged=round(dmg[p], 2),
            delta_damaged=round(dmg[p] - clean[p], 2),
            clean_rank=rc[p],
            damaged_rank=rd[p],
        )
        rows.append(row)

with open(HERE / "native_under_damage.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("wrote", HERE / "native_under_damage.csv", len(rows))
