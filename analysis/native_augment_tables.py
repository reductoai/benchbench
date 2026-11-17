"""Print the markdown tables for native_under_augment.md from native_under_augment_rerun.csv."""

import csv
import os
from pathlib import Path

ORDER = [
    "dp_bench",
    "score_bench",
    "olmocr_bench",
    "omniparsebench",
    "ocrflux_bench",
    "idp_leaderboard",
    "mdpbench",
    "rd_tablebench",
    "puredocbench",
    "omnidocbench",
    "real5_omnidocbench",
]
NAMES = dict(
    dp_bench="DP-Bench",
    score_bench="SCORE-Bench",
    olmocr_bench="olmOCR-Bench",
    omniparsebench="OmniParseBench",
    ocrflux_bench="OCRFlux-bench",
    idp_leaderboard="IDP Leaderboard",
    mdpbench="MDPBench",
    rd_tablebench="RD-TableBench",
    puredocbench="PureDocBench",
    omnidocbench="OmniDocBench",
    real5_omnidocbench="Real5-OmniDocBench",
)
CONDS = [("tilt_2_4", "Tilt"), ("scan", "Scan"), ("perspective", "Perspective")]
rows = list(
    csv.DictReader(
        open(
            Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[1] / "results"))
            / "native_under_augment_rerun.csv"
        )
    )
)
R = {(r["benchmark"], r["condition"], r["preset"]): r for r in rows}
presets = list(dict.fromkeys(r["preset"] for r in rows))
vn = {r["preset"]: r["vendor"] for r in rows}

print("### First place, clean and perturbed\n")
print("| Benchmark | Clean | Tilt | Scan | Perspective |\n|---|---|---|---|---|")
for b in ORDER:

    def first(c, col, b=b):
        return next(vn[p] for p in presets if R[(b, c, p)][col] == "1")

    clean = first("tilt_2_4", "native_clean_rank")
    cells = [first(c, "native_pert_rank") for c, _ in CONDS]
    print(f"| {NAMES[b]} | {clean} | " + " | ".join(f"**{x}**" if x != clean else x for x in cells) + " |")

for c, lab in CONDS:
    print(f"\n### Native change under {lab.lower()} (perturbed minus clean, native points)\n")
    print("| Benchmark | " + " | ".join(vn[p] for p in presets) + " |\n|---|" + "---|" * len(presets))
    for b in ORDER:
        print(
            f"| {NAMES[b]} | "
            + " | ".join(f"{float(R[(b, c, p)]['native_delta']):+.1f}" for p in presets)
            + " |"
        )

print("\n### Reducto native rank (clean / tilt / scan / perspective)\n")
print("| Benchmark | Reducto rank |\n|---|---|")
for b in ORDER:
    print(
        f"| {NAMES[b]} | {R[(b, 'tilt_2_4', 'reducto_r1')]['native_clean_rank']} / "
        + " / ".join(R[(b, c, "reducto_r1")]["native_pert_rank"] for c, _ in CONDS)
        + " |"
    )
