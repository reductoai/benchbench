"""Native-scorer change under synthetic perturbation, one panel per benchmark.
Run: python3 analysis/figures/make_native_augment.py. Reads ../native_under_augment_rerun.csv (stored
native scores with the 2026-11-11 reruns applied)."""

import csv
import math

import data as D
import make_figures
from make_figures import (
    FAINT,
    INK,
    INK2,
    MUTED,
    REDUCTO,
    RULE,
    TRACK,
    VENDOR_COLOR,
    Fig,
    T,
    legend,
    marker,
    render_png,
    size,
)

OUT = D.SYN / "figures"

make_figures.SOURCE = "Source: results/native_under_augment_rerun.csv (stored native scores plus the native_rerun_20261111 local reruns)."  # noqa: E501

CONDS = [("tilt_2_4", "Tilt 2-4 degrees"), ("scan", "Scan"), ("perspective", "Perspective")]
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


def step(span):
    for s in (0.5, 1, 2, 2.5, 5, 10, 20):
        if span / s <= 6:
            return s
    return 50


def main():
    rows = list(csv.DictReader(open(D.SYN / "native_under_augment_rerun.csv")))
    R = {(r["benchmark"], r["condition"], r["preset"]): r for r in rows}
    metric = {r["benchmark"]: r["native_metric"] for r in rows}
    vn, presets = D.vendor_names(), D.presets()
    fig = Fig(
        "10_native_under_augment",
        1600,
        "Native scores move when the page is perturbed",
        "Change in each benchmark's own scorer (native points, perturbed minus clean) when the same pages are tilted 2-4 degrees, "  # noqa: E501
        "scanned or put in perspective. Point estimates, no intervals. Right column: native rank on clean, then tilt / scan / perspective.",  # noqa: E501
    )
    cols, gapx, gapy = 4, 24, 24
    pw = (fig.w - 2 * fig.pad - gapx * (cols - 1)) / cols
    rh, head = 30, 62
    ph = head + rh * len(presets) + 44
    ax0_off, ax1_off = 104, 66
    flips = 0
    for i, b in enumerate(ORDER):
        x0 = fig.pad + (i % cols) * (pw + gapx)
        y0 = fig.top + 40 + (i // cols) * (ph + gapy)
        vals = [float(R[(b, c, p)]["native_delta"]) for c, _ in CONDS for p in presets]
        s = step(max(vals + [0]) - min(vals + [0]))
        lo, hi = math.floor(min(vals + [0]) / s) * s, max(s, math.ceil(max(vals + [0]) / s) * s)
        a0, a1 = x0 + ax0_off, x0 + pw - ax1_off

        def X(v, a0=a0, a1=a1, lo=lo, hi=hi):
            return a0 + (v - lo) / (hi - lo) * (a1 - a0)

        fig.add(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{pw:.1f}" height="{ph:.1f}" rx="6" fill="#ffffff" stroke="{RULE}"/>'  # noqa: E501
        )
        fig.add(T(x0 + 16, y0 + 28, D.bench_names()[b], 16, INK, weight=500))
        fig.add(T(x0 + 16, y0 + 45, metric[b], 10, MUTED))
        first = {c: min(presets, key=lambda p: int(R[(b, c, p)]["native_pert_rank"])) for c, _ in CONDS}
        c_first = min(presets, key=lambda p: int(R[(b, "tilt_2_4", p)]["native_clean_rank"]))
        moved = [c for c, _ in CONDS if first[c] != c_first]
        flips += bool(moved)
        if moved:
            fig.add(T(x0 + pw - 16, y0 + 28, "1st place changes", 10, "#a0444c", anchor="end", weight=500))
        ybot = y0 + head + rh * len(presets)
        t = lo
        while t <= hi + 1e-9:
            fig.add(
                f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0 + head - 6}" y2="{ybot}" stroke="{TRACK if abs(t) > 1e-9 else FAINT}"/>'  # noqa: E501
            )
            lab = f"{t:+g}" if t else "0"
            fig.add(T(X(t), ybot + 16, lab, 10, FAINT, mono=True, anchor="middle"))
            t += s
        for k, p in enumerate(sorted(presets, key=lambda p: int(R[(b, "tilt_2_4", p)]["native_clean_rank"]))):
            yc = y0 + head + k * rh + rh / 2
            col = VENDOR_COLOR[p]
            fig.add(
                T(
                    x0 + 16,
                    yc + 4,
                    vn[p],
                    12.5,
                    INK if p == REDUCTO else INK2,
                    weight=500 if p == REDUCTO else 400,
                )
            )
            for j, (c, _) in enumerate(CONDS):
                fig.add(marker(j, X(float(R[(b, c, p)]["native_delta"])), yc + (j - 1) * 7, col))
            cr = R[(b, "tilt_2_4", p)]["native_clean_rank"]
            pr = [R[(b, c, p)]["native_pert_rank"] for c, _ in CONDS]
            ch = any(r != cr for r in pr)
            fig.add(
                T(
                    x0 + pw - 14,
                    yc + 4,
                    f"{cr}: {'/'.join(pr)}",
                    10.5,
                    INK if ch else FAINT,
                    mono=True,
                    anchor="end",
                    weight=500 if ch else 400,
                )
            )
    rows_n = math.ceil(len(ORDER) / cols)
    legend(
        fig,
        fig.top + 10,
        [(lab, lambda cx, cy, j=j: marker(j, cx, cy, INK2)) for j, (_, lab) in enumerate(CONDS)],
    )
    y = fig.top + 40 + rows_n * (ph + gapy) + 14
    return fig.finish(
        y,
        [
            f"First place under the native scorer changes in at least one perturbed condition on {flips} of 12 benchmarks. "  # noqa: E501
            "Each panel has its own x scale, because native metrics differ. Rows are sorted by clean native rank. "  # noqa: E501
            "Scores are from native_under_augment_rerun.csv: the 2026-11-11 rerun of each native scorer on the current parses where a cell was rerun, else the stored score (inputs identical). They are aggregated as each benchmark's headline (page mean over pages scored in both "  # noqa: E501
            "conditions; suite, pass-rate or official overall where the benchmark defines one). No intervals or paired tests: changes under about "  # noqa: E501
            "2 points may be noise.",
        ],
    ), flips


if __name__ == "__main__":
    svg, flips = main()
    (OUT / "10_native_under_augment.svg").write_text(svg)
    w, h = size(svg)
    render_png(svg, w, h, OUT / "10_native_under_augment@2x.png")
    print("wrote", w, h, "flips", flips)
