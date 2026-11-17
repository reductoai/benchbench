"""Regenerate data.json.

Inputs: results.csv and per-page ParseBench-2 native scores under BENCHBENCH_RUNS. Optional:
native_rotated_corrected.csv (benchmark,preset,native_tilt
and optionally native_clean) replaces the Native + Rotated scores for the benchmarks it lists.
pair_minimal.csv (from pair_minimal.py) adds the minimal-prompt PAIR scores, min_clean and min_tilt.
"""

import csv
import json
import os
import pathlib
from statistics import mean

from headlines import repeat_check

root = pathlib.Path(
    os.environ.get("BENCHBENCH_RESULTS", pathlib.Path(__file__).resolve().parents[1] / "results")
)
PM = root
PB2 = pathlib.Path(os.environ.get("BENCHBENCH_RUNS", root / "runs")) / "parsebench2/native"
NAMES = {
    "dp_bench": "DP-Bench",
    "score_bench": "SCORE-Bench",
    "olmocr_bench": "olmOCR-Bench",
    "omniparsebench": "OmniParseBench",
    "ocrflux_bench": "OCRFlux-bench",
    "idp_leaderboard": "IDP Leaderboard",
    "mdpbench": "MDPBench",
    "rd_tablebench": "RD-TableBench",
    "puredocbench": "PureDocBench",
    "omnidocbench": "OmniDocBench",
    "real5_omnidocbench": "Real5-OmniDocBench",
    "parsebench2": "ParseBench-2",
}
BUILDER = {
    "omniparsebench": "Datalab",
    "parsebench2": "LlamaParse",
    "rd_tablebench": "Reducto",
}
PRESETS = [
    "reducto_r1",
    "llamaparse_agentic_plus",
    "datalab_accurate",
    "extend_performance_agentic_formulas",
    "mistral_ocr_4_1",
    "azure_layout_high_res_formulas",
    "pulse_ultra_2",
    "cohere_parse_v5",
]
PERTS = [("tilt_2_4", "tilt"), ("scan", "scan"), ("perspective", "perspective")]

baseline_path = root / "data.json"
if baseline_path.exists():
    data = json.loads(baseline_path.read_text())
    results = {(r["benchmark"], r["preset"]): r for r in csv.DictReader((PM / "results.csv").open())}
    augmented = {
        (r["benchmark"], r["preset"]): r
        for r in csv.DictReader((PM / "native_under_augment_rerun.csv").open())
        if r["condition"] == "tilt_2_4"
    }
    for benchmark in data["benchmarks"]:
        benchmark["pages"] = int(
            results[(benchmark["id"], benchmark["vendors"][0]["preset"])]["pages_judged_clean"]
        )
        for vendor in benchmark["vendors"]:
            key = (benchmark["id"], vendor["preset"])
            row = results[key]
            vendor["gpt_clean"] = float(row["gpt_clean"])
            vendor["gpt_tilt"] = float(row["gpt_tilt"])
            if vendor["preset"] == "datalab_accurate" or benchmark["id"] == "mdpbench":
                vendor["native_clean"] = float(row["native_clean"])
            if vendor["preset"] == "datalab_accurate":
                vendor["native_tilt"] = float(augmented[key]["native_pert"])
            vendor.pop("ci", None)
    repeats = data.get("refresh", {}).get("repeat_check")
    if os.environ.get("BENCHBENCH_RUNS"):
        repeats = repeat_check(data, os.environ["BENCHBENCH_RUNS"])
    data["refresh"] = {
        **data.get("refresh", {}),
        "run": "20261116T220719Z",
        "datalab": "Chandra 2.7, November 2026 API, accurate mode, captions on",
        "primary": "All eight vendors rejudged; GPT-6.1 Sol PAIR; clean r0+r1, tilt r0",
        "historical": "Gemini 3.1, scan and perspective predate this refresh.",
    }
    if repeats is not None:
        data["refresh"]["repeat_check"] = repeats
    (root / "data.json").write_text(json.dumps(data, indent=1) + "\n")
    raise SystemExit(0)


def num(x):
    return float(x) if x not in ("", None) else None


def pb2_scores(cond):
    pages = {}
    for p in PRESETS:
        for line in open(PB2 / cond / p / "scores.jsonl"):
            r = json.loads(line)
            if r.get("score") is not None:
                pages.setdefault(r["page_key"], {})[p] = r["score"]
    return {k: v for k, v in pages.items() if len(v) == len(PRESETS)}


res = list(csv.DictReader(open(PM / "results.csv")))
aug = list(csv.DictReader(open(PM / "native_under_augment_rerun.csv")))
pb2_clean = pb2_scores("clean")
pb2_pert = {}
for cond, _ in PERTS:
    t = pb2_scores(cond)
    keys = [k for k in pb2_clean if k in t]
    pb2_pert[cond] = {p: mean(t[k][p] for k in keys) for p in PRESETS}
corrected = {}
cpath = root / "native_rotated_corrected.csv"
if cpath.exists():
    for r in csv.DictReader(open(cpath)):
        corrected[(r["benchmark"], r["preset"])] = r

minimal = {}
mpath = root / "pair_minimal.csv"
if mpath.exists():
    for r in csv.DictReader(open(mpath)):
        minimal[(r["benchmark"], r["preset"], r["field"])] = float(r["score"])


out = []
for b, name in NAMES.items():
    rows = {r["preset"]: r for r in res if r["benchmark"] == b}
    vendors = []
    for p in PRESETS:
        r = rows[p]
        v = {
            "preset": p,
            "vendor": r["vendor"],
            "gpt_clean": num(r["gpt_clean"]),
            "gemini_clean": num(r["gemini_own_clean"]),
            "gpt_tilt": num(r["gpt_tilt"]),
            "gpt_scan": num(r["gpt_scan"]),
            "gpt_perspective": num(r["gpt_perspective"]),
        }
        if b == "parsebench2":
            v["native_clean"] = round(mean(s[p] for s in pb2_clean.values()), 3)
            for cond, k in PERTS:
                v["native_" + k] = round(pb2_pert[cond][p], 3)
        else:
            a = {x["condition"]: x for x in aug if x["benchmark"] == b and x["preset"] == p}
            v["native_clean"] = round(num(a["tilt_2_4"]["native_clean"]), 3)
            for cond, k in PERTS:
                v["native_" + k] = round(num(a[cond]["native_pert"]), 3)
        for k in ("min_clean", "min_tilt"):
            v[k] = minimal.get((b, p, k))
        c = corrected.get((b, p))
        if c:
            v["native_tilt"] = round(float(c["native_tilt"]), 3)
            if c.get("native_clean"):
                v["native_clean"] = round(float(c["native_clean"]), 3)
        if b == "mdpbench":
            v["native_clean"] = num(r["native_clean"])
        vendors.append(v)
    first = rows[PRESETS[0]]
    out.append(
        {
            "id": b,
            "name": name,
            "metric": first["native_metric"],
            "pages": int(first["pages_judged_clean"]),
            "builder_vendor": BUILDER.get(b),
            "rotated_corrected": any((b, p) in corrected for p in PRESETS),
            "vendors": vendors,
        }
    )

(root / "data.json").write_text(json.dumps({"benchmarks": out}, indent=1))
