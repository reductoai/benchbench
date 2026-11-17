"""olmOCR-Bench and OmniDocBench only: four benchmark comparison figures (2026-11).
python3 analysis/figures/make_two_bench.py  ->  two_bench/<name>.svg and <name>@2x.png
Numbers come from data.py (results.csv) and, for the hyphen rescore,
reports/olmocr_bench/native_hyjoin.json on runs/olmocr_bench. Grey first, Reducto is the one plum accent."""

import json
import os
from pathlib import Path

import data as D
from make_figures import Fig, T, legend, render_png, size

OUT = D.SYN / "figures/two_bench"
G50, G100, G200, G300, G400, G500, G600, G700, G900 = (
    "#fafafa",
    "#f5f5f5",
    "#e5e5e5",
    "#d4d4d4",
    "#a3a3a3",
    "#737373",
    "#525252",
    "#404040",
    "#171717",
)
PLUM, PLUM6, PLUM2, PLUM1 = "#4b163d", "#8a3d76", "#e3bdd6", "#f2e0ec"
R1 = "reducto_r1"
BENCHES = ["olmocr_bench", "omnidocbench"]
NATIVE_LABEL = {
    "olmocr_bench": "Native: suite pass rate (%)",
    "omnidocbench": "Native: official overall (500-page sample)",
}
GRADERS = [
    ("native_clean", "native_rank", None),
    ("gpt_clean", "gpt_clean_rank", "GPT judge, 0-10"),
    ("gemini_own_clean", "gemini_own_rank", "Gemini judge, 0-10"),
]


def name(b):
    return D.bench_names()[b]


def vn(p):
    return D.vendor_names()[p]


def card(fig, x, y, w, h):
    fig.add(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="#ffffff" stroke="{G200}"/>'  # noqa: E501
    )


def chip(x, y, rank, hi):
    fill, stroke, col = (
        (PLUM, PLUM, "#ffffff")
        if hi and rank == 1
        else (("#ffffff", PLUM, PLUM) if hi else ("#ffffff", G300, G600))
    )
    return (
        f'<rect x="{x - 10:.1f}" y="{y - 10:.1f}" width="20" height="20" rx="4" fill="{fill}" stroke="{stroke}"/>'  # noqa: E501
        + T(x, y + 4.5, rank, 11.5, col, mono=True, anchor="middle")
    )


def nice_range(vals, step):
    lo, hi = min(vals), max(vals)
    lo = step * int(lo // step)
    hi = step * (int(hi // step) + 1)
    return lo, hi


def fig_scores():
    """Per benchmark: one row per parser (sorted by GPT), three dot strips: native, GPT, Gemini."""
    fig = Fig(
        "01_scores_three_graders",
        1600,
        "Three graders on the same 500 pages",
        "Each benchmark's own scorer, a GPT judge and a Gemini judge score the same clean parses. Rows are sorted by the GPT judge. "  # noqa: E501
        "The chip is the rank under that grader; Reducto r-1 is the plum row.",
    )
    y = fig.top + 8
    lab_w, strip_gap = 150, 40
    for b in BENCHES:
        rows = sorted(D.presets(), key=lambda p: -D.row(b, p)["gpt_clean"])
        rh, head = 38, 74
        h = head + rh * len(rows) + 54
        x0, w = fig.pad, fig.w - 2 * fig.pad
        card(fig, x0, y, w, h)
        fig.add(T(x0 + 24, y + 34, name(b), 20, G900, weight=500))
        c = D.claims()[b]
        note = (
            "Reducto claimed over all 7 (both judges, 95%, Holm)"
            if len(c["claimed"]) == 7
            else f"Reducto claimed over {len(c['claimed'])} of 7; not over "
            + ", ".join(vn(p) for p in c["not_claimed"])
        )
        fig.add(T(x0 + w - 24, y + 34, note, 13, G500, anchor="end"))
        sx0 = x0 + 24 + lab_w
        sw = (x0 + w - 24 - sx0 - strip_gap * 2) / 3
        for gi, (key, rkey, label) in enumerate(GRADERS):
            a0 = sx0 + gi * (sw + strip_gap) + 34
            a1 = a0 + sw - 34 - 48
            vals = [D.row(b, p)[key] for p in rows]
            lo, hi = nice_range(vals, 5 if key == "native_clean" else 1)

            def X(v, a0=a0, a1=a1, lo=lo, hi=hi):
                return a0 + (v - lo) / (hi - lo) * (a1 - a0)

            fig.add(
                T(
                    a0 - 34,
                    y + 62,
                    (label or NATIVE_LABEL[b]).upper() if False else (label or NATIVE_LABEL[b]),
                    12,
                    G500,
                    mono=True,
                )
            )
            ybot = y + head + rh * len(rows)
            step = 5 if key == "native_clean" else 1
            t = lo
            while t <= hi + 1e-9:
                fig.add(
                    f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y + head - 4}" y2="{ybot}" stroke="{G100 if t not in (lo,) else G200}"/>'  # noqa: E501
                )
                fig.add(T(X(t), ybot + 18, f"{t:g}", 10.5, G400, mono=True, anchor="middle"))
                t += step
            for k, p in enumerate(rows):
                yc = y + head + k * rh + rh / 2
                r = D.row(b, p)
                hi_ = p == R1
                if k % 2 == 0:
                    pass
                fig.add(
                    f'<line x1="{a0:.1f}" x2="{X(r[key]):.1f}" y1="{yc:.1f}" y2="{yc:.1f}" stroke="{PLUM2 if hi_ else G200}" stroke-width="{3 if hi_ else 2}" stroke-linecap="round"/>'  # noqa: E501
                )
                fig.add(
                    f'<circle cx="{X(r[key]):.1f}" cy="{yc:.1f}" r="{7 if hi_ else 5.5}" fill="{PLUM if hi_ else G400}"/>'  # noqa: E501
                )
                fmt = f"{r[key]:.1f}" if key == "native_clean" else f"{r[key]:.2f}"
                fig.add(
                    T(
                        X(r[key]) + 12,
                        yc + 4.5,
                        fmt,
                        12.5,
                        PLUM if hi_ else G600,
                        mono=True,
                        weight=500 if hi_ else 400,
                    )
                )
                fig.add(chip(a0 - 20, yc, r[rkey], hi_))
        for k, p in enumerate(rows):
            yc = y + head + k * rh + rh / 2
            hi_ = p == R1
            fig.add(T(x0 + 24, yc + 5, vn(p), 14.5, PLUM if hi_ else G700, weight=500 if hi_ else 400))
        y += h + 24
    return fig.finish(
        y,
        [
            "Native scores are in each benchmark's own units; judge scores are the mean 0-10 score on clean pages (GPT: 2 repeats; Gemini: 2 passes in its own label order). "  # noqa: E501
            "Ranks are point estimates. A claim that Reducto beats a parser needs both judges to separate them (95%, Holm).",  # noqa: E501
        ],
    )


def fig_ranks():
    """Slope chart: rank under native, GPT, Gemini."""
    fig = Fig(
        "02_rank_by_grader",
        1600,
        "Native scorers and judges disagree on Reducto",
        "Rank of each parser (1 is best) under the benchmark's own scorer, the GPT judge and the Gemini judge, same pages and parses. "  # noqa: E501
        f"Reducto r-1 is {D.row('olmocr_bench', R1)['native_rank']}th on olmOCR-Bench's native scorer and "
        f"{D.row('omnidocbench', R1)['native_rank']}nd on OmniDocBench's; both judges put it 1st on both.",
    )
    y0 = fig.top + 10
    gap = 40
    pw = (fig.w - 2 * fig.pad - gap) / 2
    rh, head = 46, 84
    ph = head + rh * 8 + 40
    cols = [("native_rank", "Native"), ("gpt_clean_rank", "GPT judge"), ("gemini_own_rank", "Gemini judge")]
    for i, b in enumerate(BENCHES):
        x0 = fig.pad + i * (pw + gap)
        card(fig, x0, y0, pw, ph)
        fig.add(T(x0 + 24, y0 + 34, name(b), 20, G900, weight=500))
        cx = [x0 + 200 + j * (pw - 400) / 2 for j in range(3)]

        def Y(r):
            return y0 + head + (r - 1) * rh + rh / 2

        for j, (_, lab) in enumerate(cols):
            fig.add(T(cx[j], y0 + 66, lab, 12, G500, mono=True, anchor="middle"))
            fig.add(
                f'<line x1="{cx[j]:.1f}" x2="{cx[j]:.1f}" y1="{Y(1) - 12:.1f}" y2="{Y(8) + 12:.1f}" stroke="{G200}"/>'  # noqa: E501
            )
        order = sorted(D.presets(), key=lambda p: p == R1)
        for p in order:
            r = D.row(b, p)
            hi_ = p == R1
            rk = [r[k] for k, _ in cols]
            col = PLUM if hi_ else G300
            pts = " ".join(f"{cx[j]:.1f},{Y(rk[j]):.1f}" for j in range(3))
            fig.add(
                f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="{3.5 if hi_ else 1.6}" stroke-linejoin="round"/>'  # noqa: E501
            )
            for j in range(3):
                fig.add(
                    f'<circle cx="{cx[j]:.1f}" cy="{Y(rk[j]):.1f}" r="{7 if hi_ else 5}" fill="{PLUM if hi_ else "#ffffff"}" stroke="{col if hi_ else G400}" stroke-width="1.5"/>'  # noqa: E501
                )
            fig.add(
                T(
                    cx[0] - 18,
                    Y(rk[0]) + 4.5,
                    f"{vn(p)}  {rk[0]}",
                    13.5,
                    PLUM if hi_ else G600,
                    anchor="end",
                    weight=500 if hi_ else 400,
                )
            )
            fig.add(
                T(
                    cx[2] + 18,
                    Y(rk[2]) + 4.5,
                    f"{rk[2]}  {vn(p)}",
                    13.5,
                    PLUM if hi_ else G600,
                    weight=500 if hi_ else 400,
                )
            )
    y = y0 + ph + 20
    return fig.finish(
        y,
        [
            "Ranks are point estimates; neighbouring native scores are often not statistically separated. Judge scores are mean 0-10 on clean pages. "  # noqa: E501
            "Disagreement between the two kinds of grader does not show which one is right.",
            "Much of Reducto's olmOCR native gap is format: see the hyphen rescore figure.",
        ],
    )


def fig_tilt():
    fig = Fig(
        "03_tilt_loss",
        1600,
        "What a 2-4 degree tilt costs each parser",
        "Change in GPT judge score when the same 500 pages are rotated 2-4 degrees, tilted minus clean, with 90% intervals. "  # noqa: E501
        "Closer to 0 is better.",
    )
    y0 = fig.top + 10
    gap = 40
    pw = (fig.w - 2 * fig.pad - gap) / 2
    rh, head = 40, 70
    ph = head + rh * 8 + 50
    vals = [v for b in BENCHES for p in D.presets() for v in D.ci(D.row(b, p)["gpt_tilt_delta_ci90"])]
    lo = min(-1.5, min(vals))
    lo = -0.25 * int(-lo / 0.25 + 0.999)
    for i, b in enumerate(BENCHES):
        x0 = fig.pad + i * (pw + gap)
        card(fig, x0, y0, pw, ph)
        fig.add(T(x0 + 24, y0 + 34, name(b), 20, G900, weight=500))
        a0, a1 = x0 + 170, x0 + pw - 90

        def X(v, a0=a0, a1=a1):
            return a0 + (v - lo) / (0 - lo) * (a1 - a0)

        ybot = y0 + head + rh * 8
        t = lo
        while t <= 1e-9:
            fig.add(
                f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0 + head - 6}" y2="{ybot}" stroke="{G300 if abs(t) < 1e-9 else G100}"/>'  # noqa: E501
            )
            fig.add(
                T(
                    X(t),
                    ybot + 18,
                    "0" if abs(t) < 1e-9 else f"{t:+.2f}".rstrip("0").rstrip("."),
                    10.5,
                    G400,
                    mono=True,
                    anchor="middle",
                )
            )
            t += 0.25
        rows = sorted(D.presets(), key=lambda p: -D.row(b, p)["gpt_tilt_delta"])
        for k, p in enumerate(rows):
            r = D.row(b, p)
            yc = y0 + head + k * rh + rh / 2
            hi_ = p == R1
            d, (line, u) = r["gpt_tilt_delta"], D.ci(r["gpt_tilt_delta_ci90"])
            fig.add(T(x0 + 24, yc + 5, vn(p), 14.5, PLUM if hi_ else G700, weight=500 if hi_ else 400))
            fig.add(
                f'<rect x="{X(d):.1f}" y="{yc - 9:.1f}" width="{X(0) - X(d):.1f}" height="18" rx="3" fill="{PLUM if hi_ else G300}"/>'  # noqa: E501
            )
            fig.add(
                f'<line x1="{X(line):.1f}" x2="{X(min(u, 0.0)) if u <= 0 else X(u):.1f}" y1="{yc:.1f}" y2="{yc:.1f}" stroke="{PLUM2 if hi_ else G600}" stroke-width="1.5"/>'  # noqa: E501
            )
            for e in (line, u):
                fig.add(
                    f'<line x1="{X(e):.1f}" x2="{X(e):.1f}" y1="{yc - 5:.1f}" y2="{yc + 5:.1f}" stroke="{PLUM2 if hi_ else G600}" stroke-width="1.5"/>'  # noqa: E501
                )
            fig.add(
                T(
                    X(0) + 10,
                    yc + 4.5,
                    f"{d:+.2f}",
                    12.5,
                    PLUM if hi_ else G600,
                    mono=True,
                    weight=500 if hi_ else 400,
                )
            )
    y = y0 + ph + 20
    return fig.finish(
        y,
        [
            "Synthetic tilt, one GPT repeat per page. Intervals are per parser (page bootstrap) and do not test the difference between two parsers, "  # noqa: E501
            "so overlapping bars do not say which parser is more robust. On olmOCR-Bench, Reducto and Mistral OCR lose about the same.",  # noqa: E501
        ],
    )


def fig_hyphen():
    src = os.environ.get("HYJOIN_JSON")
    h = (
        json.loads(Path(src).read_text())
        if src
        else json.loads(D.git_show("runs/olmocr_bench", "reports/olmocr_bench/native_hyjoin.json"))
    )
    P = D.presets()
    rows = sorted(P, key=lambda p: -h[p]["hyjoin"])
    r1 = h[R1]
    fig = Fig(
        "04_olmocr_hyphen_rule",
        1600,
        "olmOCR-Bench with line-end hyphens joined",
        f"Same 500 pages, same pinned scorer. The only change: a word split by a hyphen at a line end is joined when the next line "  # noqa: E501
        f"starts lowercase ('in-' / 'tensity' becomes 'intensity'), as in the adjusted scoring. Reducto r-1 goes from "  # noqa: E501
        f"{r1['official']:.1f} ({ordinal(r1['official_rank'])}) to {r1['hyjoin']:.1f} ({ordinal(r1['hyjoin_rank'])}).",  # noqa: E501
    )
    y0 = fig.top + 10
    x0, w = fig.pad, fig.w - 2 * fig.pad
    rh, head = 44, 76
    ph = head + rh * len(rows) + 50
    card(fig, x0, y0, w, ph)
    vals = [v for p in P for v in (h[p]["official"], h[p]["hyjoin"])]
    lo, hi = nice_range(vals, 5)
    a0, a1 = x0 + 220, x0 + w - 480

    def X(v):
        return a0 + (v - lo) / (hi - lo) * (a1 - a0)

    ybot = y0 + head + rh * len(rows)
    t = lo
    while t <= hi + 1e-9:
        fig.add(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0 + head - 6}" y2="{ybot}" stroke="{G100}"/>')
        fig.add(T(X(t), ybot + 18, f"{t:g}", 10.5, G400, mono=True, anchor="middle"))
        t += 5
    cx = [x0 + w - 410, x0 + w - 270, x0 + w - 110]
    for j, lab in enumerate(["Official", "Hyphens joined", "Tests fixed / broken"]):
        fig.add(T(cx[j], y0 + 58, lab, 12, G500, mono=True, anchor="middle"))
    fig.add(T(a0, y0 + 58, "Suite pass rate (%)", 12, G500, mono=True))
    for k, p in enumerate(rows):
        r = h[p]
        yc = y0 + head + k * rh + rh / 2
        hi_ = p == R1
        fig.add(T(x0 + 24, yc + 5, vn(p), 14.5, PLUM if hi_ else G700, weight=500 if hi_ else 400))
        fig.add(
            f'<line x1="{X(r["official"]):.1f}" x2="{X(r["hyjoin"]):.1f}" y1="{yc:.1f}" y2="{yc:.1f}" stroke="{PLUM2 if hi_ else G300}" stroke-width="4" stroke-linecap="round"/>'  # noqa: E501
        )
        fig.add(
            f'<circle cx="{X(r["official"]):.1f}" cy="{yc:.1f}" r="6" fill="#ffffff" stroke="{PLUM if hi_ else G500}" stroke-width="1.6"/>'  # noqa: E501
        )
        fig.add(
            f'<circle cx="{X(r["hyjoin"]):.1f}" cy="{yc:.1f}" r="{7 if hi_ else 5.5}" fill="{PLUM if hi_ else G500}"/>'  # noqa: E501
        )
        fig.add(T(cx[0] - 6, yc + 4.5, f"{r['official']:.1f}", 12.5, G600, mono=True, anchor="end"))
        fig.add(chip(cx[0] + 18, yc, r["official_rank"], hi_))
        fig.add(
            T(
                cx[1] - 6,
                yc + 4.5,
                f"{r['hyjoin']:.1f}",
                12.5,
                PLUM if hi_ else G600,
                mono=True,
                anchor="end",
                weight=500 if hi_ else 400,
            )
        )
        fig.add(chip(cx[1] + 18, yc, r["hyjoin_rank"], hi_))
        fig.add(
            T(
                cx[2],
                yc + 4.5,
                f"{r['tests_fixed']} / {r['tests_broken']}",
                12.5,
                G600,
                mono=True,
                anchor="middle",
            )
        )
    legend(
        fig,
        fig.top + 2,
        [
            (
                "Official score",
                lambda cx_, cy: (
                    f'<circle cx="{cx_}" cy="{cy}" r="5" fill="#ffffff" stroke="{G500}" stroke-width="1.6"/>'
                ),
            ),
            ("Hyphens joined", lambda cx_, cy: f'<circle cx="{cx_}" cy="{cy}" r="5" fill="{G500}"/>'),
        ],
        x=fig.w - fig.pad - 330,
    )
    y = y0 + ph + 20
    d = r1["delta_ci90"]
    beat = []
    for p in P:
        if p != R1 and h[p]["hyjoin"] > r1["hyjoin"]:
            c = h[p]["reducto_minus_hyjoin_ci90"]
            beat.append(
                f"{vn(p)} ({'separated' if c[1] < 0 else 'not separated'}, Reducto minus {vn(p)} {c[0]:+.1f} to {c[1]:+.1f})"  # noqa: E501
            )
    return fig.finish(
        y,
        [
            f"Not an official score: a post-processing step applied after the fact to every parser's output, chosen after seeing Reducto's failures. "  # noqa: E501
            f"It also joins true compound words split at a line end ('long-' / 'term'). Reducto keeps printed line-end hyphens far more than the others "  # noqa: E501
            f"({h['_pages_changed'][R1]} of 500 pages changed; Azure DI {h['_pages_changed']['azure_layout_high_res_formulas']}; every other parser 7 or fewer).",  # noqa: E501
            f"Reducto change {r1['delta']:+.1f} points (90% page bootstrap {d[0]:+.1f} to {d[1]:+.1f}). Still ahead of Reducto after the rule: "  # noqa: E501
            + ("; ".join(beat) if beat else "none")
            + ". Inline tags are untouched here; the olmOCR report's two-rewrite check (hyphens and tags) gives "  # noqa: E501
            f"{r1['fmtnorm']:.1f} ({ordinal(r1['fmtnorm_rank'])}).",
            "These are BenchBench clean parses (500-page sample), not the full-set r-1 / r-1 mini runs, so the numbers differ.",  # noqa: E501
        ],
    )


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def main():
    import sys

    OUT.mkdir(exist_ok=True)
    figs = {
        "01_scores_three_graders": fig_scores,
        "02_rank_by_grader": fig_ranks,
        "03_tilt_loss": fig_tilt,
        "04_olmocr_hyphen_rule": fig_hyphen,
    }
    only = sys.argv[1:]
    for n, fn in figs.items():
        if only and n not in only:
            continue
        svg = fn().replace('id="', 'id="')
        (OUT / f"{n}.svg").write_text(svg)
        w, hh = size(svg)
        render_png(svg, w, hh, OUT / f"{n}@2x.png")
        print("wrote", n, w, hh)


if __name__ == "__main__":
    main()
