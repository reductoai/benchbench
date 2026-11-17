"""Native scores on tilted pages: each benchmark's own headline metric, clean vs tilt_2_4, per parser.

python3 analysis/native_under_tilt.py   writes native_under_tilt.csv next to this file.
No new scoring and no API calls: the native scorers already ran on the tilt_2_4 parses during each benchmark
run (RUNBOOK section 2, `benchbench native ... --conditions clean tilt_2_4 scan perspective`). This script
only
collects those scores with the same aggregation as each benchmark's clean headline.
Inputs: results.csv (clean headline, ranks, GPT tilt delta); the per-benchmark run branches origin/runs/<b>
(report files); results/runs/<b>/native/{clean,tilt_2_4}/ (per-page scores).
Delta convention matches gpt_tilt_delta: tilted minus clean, negative means the parser lost score."""

import csv
import json
import os
import re
import statistics
from pathlib import Path

HERE = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[1] / "results"))
REPO = HERE.parent.parent
RUNS = Path(os.environ.get("BENCHBENCH_RUNS", HERE / "runs"))
COND = "tilt_2_4"
PAGE_MEAN = {"dp_bench", "score_bench", "ocrflux_bench", "idp_leaderboard", "rd_tablebench", "mdpbench"}

R = list(csv.DictReader(open(HERE / "results.csv")))
BENCH = list(dict.fromkeys(r["benchmark"] for r in R))


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
    """Return {preset: (clean, tilt, pages, method)} with clean and tilt on the same aggregation."""
    out = {}
    if b in PAGE_MEAN:
        for p in presets:
            c, t = page_scores(b, "clean", p), page_scores(b, COND, p)
            keys = sorted(set(c) & set(t))
            out[p] = (
                statistics.mean(c[k] for k in keys),
                statistics.mean(t[k] for k in keys),
                len(keys),
                "page mean of the native score, pages scored in both conditions",
            )
    elif b == "olmocr_bench":
        d = json.loads(show(b, "native_summary.json"))["final"]
        for p in presets:
            out[p] = (
                d["clean"][p]["overall"],
                d[COND][p]["overall"],
                d[COND][p].get("pages"),
                "suite pass rate (reports/olmocr_bench/native_summary.json)",
            )
    elif b == "omniparsebench":
        rows = md_table(show(b, "native_extra.md"), "| preset | clean | tilt_2_4 |")
        for r in rows:
            if r["preset"] in presets:
                c = num(r["clean"])
                out[r["preset"]] = (
                    c,
                    c + num(r["tilt_2_4"]),
                    None,
                    "text+tables pass rate (reports/omniparsebench/native_extra.md, 1 decimal)",
                )
    elif b == "puredocbench":
        d = json.loads(show(b, "official_native.json"))
        for p in presets:
            out[p] = (
                d["clean"][p]["overall"],
                d[COND][p]["overall"],
                None,
                "official overall (reports/puredocbench/official_native.json)",
            )
    elif b == "omnidocbench":
        d = json.loads(show(b, "analysis.json"))["official"]
        for p in presets:
            out[p] = (
                d[f"clean/{p}"]["overall"],
                d[f"{COND}/{p}"]["overall"],
                None,
                "official overall (reports/omnidocbench/analysis.json)",
            )
    elif b == "real5_omnidocbench":
        for p in presets:
            c, t = (json.load(open(s3file(b, k, p, "official.json")))["overall"] for k in ("clean", COND))
            out[p] = (c, t, None, "official overall (native/<cond>/<preset>/official.json in S3)")
    return out


def ranks(v):
    order = sorted(v, key=lambda p: -v[p])
    return {p: order.index(p) + 1 for p in v}


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

rows = []
for b in BENCH:
    rr = {r["preset"]: r for r in R if r["benchmark"] == b}
    got = collect(b, list(rr))
    assert set(got) == set(rr), (b, set(rr) - set(got))
    nc = {p: got[p][0] for p in rr}
    nt = {p: got[p][1] for p in rr}
    rc, rt = ranks(nc), ranks(nt)
    for p, r in rr.items():
        c, t, n, method = got[p]
        assert abs(c - float(r["native_clean"])) < 0.25, (b, p, c, r["native_clean"])
        rows.append(
            dict(
                benchmark=b,
                vendor=VN[p],
                preset=p,
                native_metric=r["native_metric"],
                native_clean_csv=r["native_clean"],
                native_clean=round(c, 2),
                native_tilt=round(t, 2),
                native_tilt_delta=round(t - c, 2),
                native_clean_rank=rc[p],
                native_tilt_rank=rt[p],
                native_rank_csv=r["native_rank"],
                gpt_clean_rank=r["gpt_clean_rank"],
                gpt_tilt_rank=r["gpt_tilt_rank"],
                gpt_tilt_delta=r["gpt_tilt_delta"],
                pages_both=n if n is not None else "",
                method=method,
            )
        )

with open(HERE / "native_under_tilt.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("wrote", HERE / "native_under_tilt.csv", len(rows))
