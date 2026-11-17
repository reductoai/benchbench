import csv
import os
from pathlib import Path

RESULTS = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[2] / "results"))
MDP = {
    r["preset"]: float(r["native_clean"])
    for r in csv.DictReader((RESULTS / "native_rotated_corrected.csv").open())
    if r["benchmark"] == "mdpbench"
}

V = {
    "reducto_r1": "Reducto",
    "llamaparse_agentic_plus": "LlamaParse",
    "datalab_accurate": "Datalab",
    "extend_performance_agentic_formulas": "Extend",
    "mistral_ocr_4_1": "Mistral OCR",
    "azure_layout_high_res_formulas": "Azure DI",
    "pulse_ultra_2": "Pulse",
    "cohere_parse_v5": "Cohere",
}
ORDER = [
    "reducto_r1",
    "llamaparse_agentic_plus",
    "datalab_accurate",
    "extend_performance_agentic_formulas",
    "mistral_ocr_4_1",
    "azure_layout_high_res_formulas",
    "pulse_ultra_2",
    "cohere_parse_v5",
]
# native headline as reported in each benchmark's final report (order = O)
NAT = {
    "dp_bench": (
        "NID (official adapter)",
        [89.2, 89.5, 83.9, 92.3, 97.0, 93.3, 94.8, 97.6],
        "reports/dp_bench/README.md 3.1",
    ),
    "score_bench": (
        "CCT",
        [83.1, 85.4, 76.8, 74.8, 87.5, 83.7, 68.4, 84.4],
        "reports/score_bench/README.md 3.1",
    ),
    "olmocr_bench": (
        "suite pass rate",
        [71.3, 75.1, 75.6, 64.1, 73.2, 62.5, 73.1, 73.4],
        "reports/olmocr_bench/report.md 2",
    ),
    "omniparsebench": (
        "text+tables pass rate",
        [87.7, 90.2, 90.7, 76.0, 86.4, 70.3, 82.2, 79.2],
        "reports/omniparsebench/summary.md Headline",
    ),
    "ocrflux_bench": (
        "edit similarity, as returned",
        [84.4, 80.5, 59.2, 74.6, 89.4, 79.4, 81.3, 83.3],
        "reports/ocrflux_bench/summary.md F",
    ),
    "idp_leaderboard": (
        "GriTS-Con, paired (failed pages = 0)",
        [83.6, 96.1, 83.0, 84.8, 67.6, 61.8, 63.5, 83.1],
        "reports/idp_leaderboard/report.md 3.1",
    ),
    "mdpbench": (
        "page mean (text/CDM/TEDS)",
        [MDP[p] for p in ORDER],
        "native_rotated_corrected.csv",
    ),
    "rd_tablebench": (
        "table similarity (pipe tables converted)",
        [88.69, 88.95, 82.0, 86.0, 87.78, 79.8, 68.8, 84.5],
        "reports/rd_tablebench/summary.md Stage 1",
    ),
    "puredocbench": (
        "official overall",
        [79.40, 79.56, 74.41, 75.46, 64.89, 71.40, 76.88, 72.65],
        "reports/puredocbench/README.md 3.1",
    ),
    "omnidocbench": (
        "official overall (500-page sample)",
        [89.5, 87.5, 86.3, 87.0, 90.0, 85.4, 88.3, 86.1],
        "reports/omnidocbench/README.md 3.1",
    ),
    "parsebench2": (
        "6-dimension mean (2.0.0 scorers)",
        [87.9, 91.2, 78.5, 79.9, 74.5, 66.0, 70.4, 73.4],
        "reports/parsebench2/summary.md",
    ),
}
# Gemini own-order means as printed in reports where harness file differs in rounding only
h = list(
    csv.DictReader(
        open(
            Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[2] / "results"))
            / "checks/harness_extract.csv"
        )
    )
)


def rank(vals):
    s = sorted(vals, reverse=True)
    return [s.index(v) + 1 for v in vals]


out = []
for b, (metric, vals, src) in NAT.items():
    nr = rank(vals)
    for i, p in enumerate(ORDER):
        r = next(x for x in h if x["benchmark"] == b and x["preset"] == p)
        out.append(
            {
                "benchmark": b,
                "vendor": V[p],
                "preset": p,
                "native_metric": metric,
                "native_clean": vals[i],
                "native_rank": nr[i],
                "gpt_clean": r["gpt_clean"],
                "gpt_clean_rank": r["gpt_clean_rank"],
                "gemini_own_clean": r["gemini_own_clean"],
                "gemini_own_rank": r["gemini_own_rank"],
                "gpt_tilt": r.get("gpt_tilt_2_4"),
                "gpt_tilt_rank": r.get("gpt_tilt_2_4_rank"),
                "gpt_tilt_delta": r.get("gpt_tilt_2_4_delta"),
                "gpt_tilt_delta_ci90": r.get("gpt_tilt_2_4_delta_ci90"),
                "gpt_scan": r.get("gpt_scan"),
                "gpt_scan_delta": r.get("gpt_scan_delta"),
                "gpt_perspective": r.get("gpt_perspective"),
                "gpt_perspective_delta": r.get("gpt_perspective_delta"),
                "pages_judged_clean": r["pages_clean"],
                "native_source": src,
            }
        )
w = csv.DictWriter(
    open(
        Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[2] / "results"))
        / "results.csv",
        "w",
    ),
    fieldnames=list(out[0].keys()),
)
w.writeheader()
w.writerows(out)
# summaries
for key in ("native_rank", "gpt_clean_rank", "gemini_own_rank", "gpt_tilt_rank"):
    print(key)
    for p in ORDER:
        rs = [int(float(x[key])) for x in out if x["preset"] == p]
        print(f"  {V[p]:<12}", rs, "median", sorted(rs)[len(rs) // 2], "firsts", rs.count(1))
