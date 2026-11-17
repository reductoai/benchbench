"""BenchBench blog figures. Run from anywhere inside the repo: python3 analysis/figures/make_figures.py
Writes <name>.svg and <name>@2x.png for each figure plus contact_sheet.png next to this file.
Every number comes from data.py (results.csv, checks/provenance.json, saved comparison tables and the
runs/<benchmark> summaries). PNGs are rendered with headless Chrome using the design-system fonts."""

import html
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import data as D

OUT = Path(os.environ.get("BENCHBENCH_FIGURES", D.SYN / "figures"))
FONT_DIR = Path(os.environ.get("BENCHBENCH_FONT_DIR", D.SYN / "fonts"))

BG, INK, INK2, MUTED, FAINT, RULE, TRACK = (
    "#fafafa",
    "#171717",
    "#404040",
    "#737373",
    "#a3a3a3",
    "#e5e5e5",
    "#f0f0f0",
)
PLUM, PLUM_SOFT, PLUM_TINT = "#4b163d", "#be7dac", "#f2e0ec"
SANS = "Roobert, 'Helvetica Neue', Arial, sans-serif"
MONO = "'Berkeley Mono', 'SFMono-Regular', Menlo, monospace"
VENDOR_COLOR = {
    "reducto_r1": PLUM,
    "llamaparse_agentic_plus": "#5b6fa6",
    "datalab_accurate": "#6b5444",
    "extend_performance_agentic_formulas": "#6aa57a",
    "mistral_ocr_4_1": "#c08a3e",
    "azure_layout_high_res_formulas": "#3f8f9a",
    "pulse_ultra_2": "#b8704f",
    "cohere_parse_v5": "#a0444c",
}
REDUCTO = "reducto_r1"
SOURCE = "Source: results/results.csv and each benchmark's summary.json."
DISCLOSE = "The judge prompt and this study were written by Reducto."


def esc(t):
    return html.escape(str(t), quote=True)


def tw(text, size, mono=False):
    return len(str(text)) * size * (0.6 if mono else 0.52)


def wrap(text, size, width, mono=False):
    lines, cur = [], ""
    for word in str(text).split():
        trial = f"{cur} {word}".strip()
        if cur and tw(trial, size, mono) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def T(x, y, text, size=14, fill=INK, mono=False, anchor="start", weight=400, ls=None, extra=""):
    fam = MONO if mono else SANS
    spacing = (
        f' letter-spacing="{ls}"'
        if ls is not None
        else (' letter-spacing="0.04em"' if mono and str(text).isupper() else "")
    )
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{esc(fam)}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}"{spacing} {extra}>{esc(text)}</text>'
    )


def TL(x, y, lines, size, lh, **kw):
    return "".join(T(x, y + i * lh, line, size, **kw) for i, line in enumerate(lines))


class Fig:
    def __init__(self, name, width, title, subtitle, pad=64):
        self.name, self.w, self.pad, self.parts = name, width, pad, []
        self.add(T(pad, 76, title, 34, INK, weight=500, ls="-0.01em"))
        sub = wrap(subtitle, 16, width - 2 * pad - 80)
        self.add(TL(pad, 108, sub, 16, 24, fill=MUTED))
        self.top = 108 + 24 * len(sub) + 28

    def add(self, s):
        self.parts.append(s)

    def finish(self, y, notes):
        self.add(
            f'<line x1="{self.pad}" x2="{self.w - self.pad}" y1="{y:.1f}" y2="{y:.1f}" stroke="{RULE}"/>'
        )
        y += 26
        for n in notes + [DISCLOSE, SOURCE]:
            ls = wrap(n, 12.5, self.w - 2 * self.pad)
            self.add(TL(self.pad, y, ls, 12.5, 18, fill=MUTED))
            y += 18 * len(ls) + 4
        self.h = math.ceil(y + 36)
        body = "".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">'  # noqa: E501
            f'<rect width="{self.w}" height="{self.h}" fill="{BG}"/>{body}</svg>'
        )


def legend(fig, y, items, x=None):
    x = fig.pad if x is None else x
    for label, sym in items:
        fig.add(sym(x + 6, y - 5))
        fig.add(T(x + 18, y, label, 14, INK2))
        x += 18 + tw(label, 14) + 30
    return x


def vendor_legend(fig, y):
    items = [
        (
            D.vendor_names()[p],
            lambda cx, cy, p=p: f'<circle cx="{cx}" cy="{cy}" r="6" fill="{VENDOR_COLOR[p]}"/>',
        )
        for p in D.presets()
    ]
    return legend(fig, y, items)


def pending_panel(fig, x, y, w, h, what):
    name = D.bench_names()[D.PENDING]
    fig.add(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="none" stroke="{FAINT}" stroke-dasharray="4 4"/>'  # noqa: E501
    )
    cy = y + h / 2
    nl = wrap(name.replace("-", "- "), 14, w - 20)
    nl = [line.replace("- ", "-") for line in nl]
    fig.add(TL(x + w / 2, cy - 10 - 18 * (len(nl) - 1), nl, 14, 18, fill=MUTED, anchor="middle", weight=500))
    fig.add(
        TL(
            x + w / 2,
            cy + 12,
            wrap(what, 12, w - 24, mono=True),
            12,
            17,
            fill=FAINT,
            mono=True,
            anchor="middle",
        )
    )


def claim_note(b, short=False):
    c, vn = D.claims()[b], D.vendor_names()
    if "posthoc_over" in c and short:
        return "No pair confirmed (complete-coverage rule)"
    if "posthoc_over" in c:
        return (
            f"No pair confirmed with complete coverage. On 499 shared pages, both judges separate Reducto from "  # noqa: E501
            f"{len(c['posthoc_over'])} of 7 (shared-page subset)"
        )
    if c["leader"]:
        return f"{vn[c['leader']]} first under every grader"
    if c["unordered"]:
        return "Top three not ordered: " + ", ".join(vn[p] for p in c["unordered"])
    if c["not_claimed"]:
        return "Not claimed: Reducto over " + ", ".join(vn[p] for p in c["not_claimed"])
    if len(c["claimed"]) == len(D.presets()) - 1:
        return "Reducto claimed over all 7"
    return "No Reducto pair claimed"


def unordered_set(b):
    c = D.claims()[b]
    if not c["claimed"]:
        return set(D.presets()) - {c["leader"]}
    return set(c["unordered"]) or ({REDUCTO, *c["not_claimed"]} if c["not_claimed"] else set())


# 1. Hero: native rank vs GPT judge rank


def num(n):
    return "none" if n == 0 else str(n)


def hero():
    bs = D.benchmarks()
    fig = Fig(
        "01_native_vs_judge_rank",
        1600,
        "Same parses, two kinds of grader",
        f"Rank of each parser on {len(bs)} public benchmarks under the benchmark's own scorer (left end of each line) "  # noqa: E501
        "and under a GPT judge that scores the same outputs with vendor names hidden (right end). "
        f"Native scorers put Reducto first on {num(sum(D.row(b, REDUCTO)['native_rank'] == 1 for b in bs))} of the {len(bs)}; the judge puts it first on "  # noqa: E501
        f"{sum(D.row(b, REDUCTO)['gpt_clean_rank'] == 1 for b in bs)} (on clean pages, 9 of 11 distinct benchmarks: Real5's clean pages are OmniDocBench pages).",  # noqa: E501
    )
    left, right, top = fig.pad + 70, fig.w - fig.pad, fig.top + 34
    ncol = len(bs) + len(D.pending())
    gap = 14
    cw = (right - left - gap * (ncol - 1)) / ncol
    rh, ranks = 44, len(D.presets())

    def ys(r):
        return top + 20 + (r - 1) * rh

    bottom = ys(ranks) + 20
    for r in range(1, ranks + 1):
        fig.add(T(left - 18, ys(r) + 5, r, 13, FAINT, mono=True, anchor="end"))
    fig.add(T(fig.pad, top - 4, "RANK", 11, FAINT, mono=True))
    for i, b in enumerate(bs + D.pending()):
        x0 = left + i * (cw + gap)
        if b in D.pending():
            pending_panel(
                fig,
                x0,
                top - 24,
                cw,
                bottom - top + 146,
                "real captures, run in progress; panel added when its report is final",
            )
            continue
        xn, xj = x0 + 16, x0 + cw - 24
        fig.add(
            f'<rect x="{x0:.1f}" y="{top - 24:.1f}" width="{cw:.1f}" height="{bottom - top + 146:.1f}" rx="6" fill="#ffffff" stroke="{RULE}"/>'  # noqa: E501
        )
        for r in range(1, ranks + 1):
            fig.add(f'<line x1="{xn}" x2="{xj}" y1="{ys(r)}" y2="{ys(r)}" stroke="{TRACK}"/>')
        fig.add(T(xn, top - 6, "NATIVE", 9.5, FAINT, mono=True, anchor="middle"))
        fig.add(T(xj, top - 6, "JUDGE", 9.5, FAINT, mono=True, anchor="middle"))
        js = D.summary(b)["conditions"]["clean"]["judge"]
        un = unordered_set(b)
        for p in un:
            fig.add(
                f'<circle cx="{xj}" cy="{ys(D.row(b, p)["gpt_clean_rank"])}" r="11" fill="none" stroke="{PLUM_SOFT}" stroke-width="1.4" stroke-dasharray="3 2.5"/>'  # noqa: E501
            )
        order = [p for p in D.presets() if p != REDUCTO] + [REDUCTO]
        for p in order:
            r = D.row(b, p)
            lo, hi = js[p]["rank_ci95"]
            if hi > lo:
                fig.add(
                    f'<line x1="{xj + 13:.1f}" x2="{xj + 13:.1f}" y1="{ys(lo):.1f}" y2="{ys(hi):.1f}" stroke="{VENDOR_COLOR[p]}" stroke-opacity="0.45" stroke-width="2" stroke-linecap="round"/>'  # noqa: E501
                )
        for p in order:
            r, col = D.row(b, p), VENDOR_COLOR[p]
            hot = p == REDUCTO
            yn, yj = ys(r["native_rank"]), ys(r["gpt_clean_rank"])
            fig.add(
                f'<line x1="{xn}" y1="{yn}" x2="{xj}" y2="{yj}" stroke="{col}" stroke-width="{3 if hot else 1.6}" stroke-opacity="{1 if hot else 0.7}"/>'  # noqa: E501
            )
            fig.add(
                f'<circle cx="{xn}" cy="{yn}" r="{6 if hot else 4.5}" fill="{BG}" stroke="{col}" stroke-width="{2.2 if hot else 1.6}"/>'  # noqa: E501
            )
            fig.add(f'<circle cx="{xj}" cy="{yj}" r="{6.5 if hot else 4.5}" fill="{col}"/>')
        fig.add(
            TL(x0 + 10, bottom + 12, wrap(D.bench_names()[b], 13.5, cw - 16), 13.5, 17, fill=INK, weight=500)
        )
        fig.add(
            TL(
                x0 + 10,
                bottom + 50,
                wrap(claim_note(b, short=True), 10.5, cw - 18, mono=True),
                10.5,
                14,
                fill=MUTED,
                mono=True,
            )
        )
    y = bottom + 158
    vendor_legend(fig, y)
    y += 32
    legend(
        fig,
        y,
        [
            (
                "Native scorer rank (open)",
                lambda cx, cy: (
                    f'<circle cx="{cx}" cy="{cy}" r="5" fill="{BG}" stroke="{INK2}" stroke-width="1.6"/>'
                ),
            ),
            ("Judge rank (filled)", lambda cx, cy: f'<circle cx="{cx}" cy="{cy}" r="5" fill="{INK2}"/>'),
            (
                "Judge rank 95% interval",
                lambda cx, cy: (
                    f'<line x1="{cx}" x2="{cx}" y1="{cy - 7}" y2="{cy + 7}" stroke="{INK2}" stroke-opacity="0.45" stroke-width="2" stroke-linecap="round"/>'  # noqa: E501
                ),
            ),
            (
                "Dashed ring: order between ringed parsers not claimed",
                lambda cx, cy: (
                    f'<circle cx="{cx}" cy="{cy}" r="8" fill="none" stroke="{PLUM_SOFT}" stroke-width="1.4" stroke-dasharray="3 2.5"/>'  # noqa: E501
                ),
            ),
        ],
    )
    return fig.finish(
        y + 26,
        [
            "Judge: GPT, two repeats, clean pages. A claim that one parser beats another needs both GPT and an own-order Gemini judge to separate them "  # noqa: E501
            "(95%, Holm); the column notes list the unconfirmed pairs. Native ranks are point-estimate orders of the official headline "  # noqa: E501
            "metric and neighbouring native scores are often not statistically separated. The two methods disagree more than judge noise explains; "  # noqa: E501
            "this does not show which one is right.",
        ],
    )


# 2. Small multiples: three graders per benchmark


def grid():
    bs = D.benchmarks()
    fig = Fig(
        "02_three_graders_by_benchmark",
        1600,
        "Three graders, benchmark by benchmark",
        "Rank of each parser under the benchmark's native scorer, the GPT judge and the own-order Gemini judge, "  # noqa: E501
        "with the score each grader gave. Dashed chips mark parsers whose pairwise order is unconfirmed.",  # noqa: E501
    )
    cols, gapx, gapy = 4, 24, 24
    pw = (fig.w - 2 * fig.pad - gapx * (cols - 1)) / cols
    rh, head = 30, 74
    ph = head + rh * len(D.presets()) + 62
    for i, b in enumerate(bs + D.pending()):
        x0 = fig.pad + (i % cols) * (pw + gapx)
        y0 = fig.top + (i // cols) * (ph + gapy)
        if b in D.pending():
            pending_panel(
                fig, x0, y0, pw, ph, "real captures, run in progress; panel added when its report is final"
            )
            continue
        fig.add(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{pw:.1f}" height="{ph:.1f}" rx="6" fill="#ffffff" stroke="{RULE}"/>'  # noqa: E501
        )
        fig.add(T(x0 + 16, y0 + 28, D.bench_names()[b], 16, INK, weight=500))
        metric = D.row(b, REDUCTO)["native_metric"]
        fig.add(T(x0 + 16, y0 + 46, "Native: " + metric, 11, MUTED))
        cx = [x0 + 128, x0 + 128 + (pw - 140) / 3, x0 + 128 + 2 * (pw - 140) / 3]
        for c, lab in zip(cx, ("NATIVE", "GPT", "GEMINI"), strict=False):
            fig.add(T(c, y0 + head - 8, lab, 9.5, FAINT, mono=True))
        un = unordered_set(b)
        gj, mj = D.summary(b)["conditions"]["clean"]["judge"], D.gemini_judge(b)
        for k, p in enumerate(D.presets()):
            r = D.row(b, p)
            y = y0 + head + k * rh + 16
            hot = p == REDUCTO
            fig.add(f'<circle cx="{x0 + 20}" cy="{y - 4}" r="4" fill="{VENDOR_COLOR[p]}"/>')
            fig.add(
                T(x0 + 30, y, D.vendor_names()[p], 12.5, INK if hot else INK2, weight=500 if hot else 400)
            )
            cells = [
                (r["native_rank"], r["native_clean_str"], None, False),
                (r["gpt_clean_rank"], f"{gj[p]['mean']:.2f}", gj[p]["rank_ci95"], p in un),
                (r["gemini_own_rank"], f"{mj[p]['mean']:.2f}", mj[p]["rank_ci95"], p in un),
            ]
            for c, (rank, score, rci, dashed) in zip(cx, cells, strict=False):
                first = rank == 1
                fill = (PLUM if hot else INK2) if first else ("#ffffff")
                stroke = PLUM if hot else (INK2 if first else "#cfcfcf")
                dash = ' stroke-dasharray="3 2"' if dashed else ""
                if dashed:
                    stroke = PLUM_SOFT
                fig.add(
                    f'<rect x="{c:.1f}" y="{y - 15:.1f}" width="24" height="20" rx="4" fill="{fill}" stroke="{stroke}"{dash}/>'  # noqa: E501
                )
                fig.add(
                    T(
                        c + 12,
                        y - 1,
                        rank,
                        12,
                        "#ffffff" if first else (PLUM if hot else INK2),
                        mono=True,
                        anchor="middle",
                        weight=500,
                    )
                )
                fig.add(T(c + 30, y - 1, score, 11, MUTED, mono=True))
                if rci and rci[1] > rci[0]:
                    fig.add(T(c + 30, y + 10, f"{rci[0]}-{rci[1]}", 8.5, FAINT, mono=True))
        fig.add(
            TL(
                x0 + 16,
                y0 + ph - 34,
                wrap(claim_note(b), 11, pw - 32, mono=True),
                11,
                15,
                fill=MUTED,
                mono=True,
            )
        )
    rows = math.ceil((len(bs) + len(D.pending())) / cols)
    y = fig.top + rows * (ph + gapy) + 14
    return fig.finish(
        y,
        [
            "Each chip is a rank (1 is best, filled when first). Next to it: the native headline score in the benchmark's own units, or the judge's mean "  # noqa: E501
            "0-10 score on clean pages; the small range under a judge score is that rank's 95% interval where it is wider than one place. "  # noqa: E501
            "Native scores are the official aggregates; their ranks are point estimates. Gemini is less repeatable than GPT, so a missing Gemini "  # noqa: E501
            "separation is partly a lack of power.",
        ],
    )


# 3. Perturbation loss


def perturbation():
    bs = D.benchmarks()
    conds = [("tilt_2_4", "Tilt 2-4 degrees"), ("scan", "Scan"), ("perspective", "Perspective")]
    real = [
        ("real_illumination", "illumination"),
        ("real_scanning", "scan"),
        ("real_screen_photography", "screen"),
        ("real_skew", "skew"),
        ("real_warping", "warp"),
    ]

    def conds_of(b):
        return real if b == D.REAL5 else conds

    fig = Fig(
        "03_perturbation_loss",
        1600,
        "What a perturbed page costs each parser",
        "Change in GPT judge score when the same pages are tilted, scanned or put in perspective (Real5: really photographed or scanned), perturbed minus clean (0-10 scale), "  # noqa: E501
        "with 90% intervals. Most parsers lose something; the intervals are per parser and do not test differences between parsers.",  # noqa: E501
    )
    vals = [
        v
        for b in bs
        for c, _ in conds_of(b)
        for p in D.presets()
        for v in D.summary(b)["conditions"][c]["delta_vs_clean"][p]["ci90"]
    ]
    lo, hi = math.floor(min(vals) * 2) / 2, max(0.5, math.ceil(max(vals) * 2) / 2)
    cols, gapx, gapy = 4, 24, 24
    pw = (fig.w - 2 * fig.pad - gapx * (cols - 1)) / cols
    rh, head = 30, 56
    ph = head + rh * len(D.presets()) + 44
    ax0_off, ax1_off = 112, 16
    for i, b in enumerate(bs + D.pending()):
        x0 = fig.pad + (i % cols) * (pw + gapx)
        y0 = fig.top + 40 + (i // cols) * (ph + gapy)
        if b in D.pending():
            pending_panel(
                fig, x0, y0, pw, ph, "real captures: the primary perturbation check, run in progress"
            )
            continue
        a0, a1 = x0 + ax0_off, x0 + pw - ax1_off

        def X(v, a0=a0, a1=a1):
            return a0 + (v - lo) / (hi - lo) * (a1 - a0)

        fig.add(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{pw:.1f}" height="{ph:.1f}" rx="6" fill="#ffffff" stroke="{RULE}"/>'  # noqa: E501
        )
        fig.add(T(x0 + 16, y0 + 28, D.bench_names()[b], 16, INK, weight=500))
        if b == D.REAL5:
            fig.add(
                T(
                    x0 + 16,
                    y0 + 45,
                    "Real captures, top to bottom: " + ", ".join(line for _, line in real),
                    9.5,
                    MUTED,
                )
            )
        ybot = y0 + head + rh * len(D.presets())
        t = lo
        while t <= hi + 1e-9:
            fig.add(
                f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{y0 + head - 6}" y2="{ybot}" stroke="{TRACK if abs(t) > 1e-9 else FAINT}"/>'  # noqa: E501
            )
            fig.add(T(X(t), ybot + 16, f"{t:+.1f}" if t else "0", 10, FAINT, mono=True, anchor="middle"))
            t += 0.5
        for k, p in enumerate(D.presets()):
            yc = y0 + head + k * rh + rh / 2
            col = VENDOR_COLOR[p]
            fig.add(
                T(
                    x0 + 16,
                    yc + 4,
                    D.vendor_names()[p],
                    12.5,
                    INK if p == REDUCTO else INK2,
                    weight=500 if p == REDUCTO else 400,
                )
            )
            cs = conds_of(b)
            for j, (c, _) in enumerate(cs):
                d = D.summary(b)["conditions"][c]["delta_vs_clean"][p]
                yy = yc + (j - (len(cs) - 1) / 2) * (7 if len(cs) == 3 else 4.6)
                rc = len(cs) != 3
                fig.add(
                    f'<line x1="{X(d["ci90"][0]):.1f}" x2="{X(d["ci90"][1]):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{col}" stroke-opacity="{0.8 if j == 0 or rc else 0.45}" stroke-width="{1.4}"/>'  # noqa: E501
                )
                fig.add(marker(3 if rc else j, X(d["delta"]), yy, col))
    rows = math.ceil((len(bs) + len(D.pending())) / cols)
    legend(
        fig,
        fig.top + 10,
        [(lab, lambda cx, cy, j=j: marker(j, cx, cy, INK2)) for j, (_, lab) in enumerate(conds)]
        + ([("Real capture (Real5 panel)", lambda cx, cy: marker(3, cx, cy, INK2))] if D.REAL5 in bs else [])
        + [
            (
                "90% interval",
                lambda cx, cy: (
                    f'<line x1="{cx - 8}" x2="{cx + 8}" y1="{cy}" y2="{cy}" stroke="{INK2}" stroke-width="2"/>'  # noqa: E501
                ),
            )
        ],
    )
    y = fig.top + 40 + rows * (ph + gapy) + 14
    tl = [b for b in bs if D.summary(b)["conditions"].get("tilt_2_4")]
    mistral_tilt = f"{sum(D.summary(b)['conditions']['tilt_2_4']['delta_vs_clean']['mistral_ocr_4_1']['delta'] > D.summary(b)['conditions']['tilt_2_4']['delta_vs_clean'][REDUCTO]['delta'] for b in tl)} of {len(tl)}"  # noqa: E501
    return fig.finish(
        y,
        [
            "Tilt, scan and perspective are synthetic, one GPT repeat each. Separate or overlapping intervals here do not say which parser is more robust. This figure does not support a claim that any parser "  # noqa: E501
            f"is the most tilt-stable: by point estimate Mistral OCR loses less than Reducto under tilt on {mistral_tilt}. "  # noqa: E501
            + (
                "The Real5 panel shows its five real captures instead (one GPT run; change against the mean of that page's two clean runs; "  # noqa: E501
                "Reducto's size of loss depends on the judge, report 3.5); its synthetic conditions are in its report."  # noqa: E501
                if D.REAL5 in bs
                else "Real captures (Real5) are the primary check."
            ),
        ],
    )


def marker(j, x, y, col):
    if j == 3:
        return f'<path d="M{x:.1f},{y - 3.6:.1f} L{x + 3.6:.1f},{y:.1f} L{x:.1f},{y + 3.6:.1f} L{x - 3.6:.1f},{y:.1f} Z" fill="{col}"/>'  # noqa: E501
    if j == 0:
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.2" fill="{col}"/>'
    if j == 1:
        return f'<rect x="{x - 3.4:.1f}" y="{y - 3.4:.1f}" width="6.8" height="6.8" fill="#ffffff" stroke="{col}" stroke-width="1.5"/>'  # noqa: E501
    return f'<path d="M{x:.1f},{y - 4.2:.1f} L{x + 4.2:.1f},{y + 3:.1f} L{x - 4.2:.1f},{y + 3:.1f} Z" fill="#ffffff" stroke="{col}" stroke-width="1.5"/>'  # noqa: E501


# 4. Judge agreement


def agreement():
    bs = D.benchmarks()
    fig = Fig(
        "04_grader_agreement",
        1400,
        "How often two graders order a pair the same way",
        "Share of the 28 parser pairs that two rankings put in the same order, with 90% intervals. On every benchmark the native scorer "  # noqa: E501
        "agrees with the GPT judge less often than the judge agrees with its own repeat.",
    )
    left, right = fig.pad + 170, fig.w - fig.pad - 20
    rh, top = 40, fig.top + 60
    amin = 0.2

    def X(v):
        return left + (v - amin) / (1 - amin) * (right - left)

    series = [
        ("Native per-page mean vs GPT judge", PLUM, lambda b: D.summary(b)["native_vs_judge"], "dot"),
        ("GPT vs own-order Gemini", "#5b6fa6", lambda b: D.gemini_agreement(b), "diamond"),
        (
            "GPT repeat vs repeat (noise ceiling)",
            INK2,
            lambda b: D.summary(b)["judge_repeat_agreement"],
            "ring",
        ),
    ]
    legend(
        fig,
        fig.top + 10,
        [(lab, lambda cx, cy, s=s, c=c: sym(s, cx, cy, c)) for lab, c, _, s in series]
        + [
            (
                "90% interval",
                lambda cx, cy: (
                    f'<line x1="{cx - 8}" x2="{cx + 8}" y1="{cy}" y2="{cy}" stroke="{INK2}" stroke-opacity="0.5" stroke-width="2"/>'  # noqa: E501
                ),
            )
        ],
    )
    rows = bs + D.pending()
    ybot = top + rh * (len(rows) + (0 if D.pending() else 1))
    fig.add(T(right + 16, top - 16, "NATIVE", 9.5, FAINT, mono=True))
    for t in [i / 10 for i in range(2, 11, 1)]:
        fig.add(
            f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{top - 10}" y2="{ybot - rh + 10}" stroke="{TRACK}"/>'
        )
        if t * 10 % 2 == 0:
            fig.add(T(X(t), ybot - rh + 30, f"{t:.1f}", 11, FAINT, mono=True, anchor="middle"))
    for k, b in enumerate(rows):
        yc = top + k * rh + rh / 2 - 10
        if b in D.pending():
            fig.add(
                f'<rect x="{fig.pad}" y="{ybot + 18:.1f}" width="{fig.w - 2 * fig.pad}" height="36" rx="6" fill="none" stroke="{FAINT}" stroke-dasharray="4 4"/>'  # noqa: E501
            )
            fig.add(
                T(
                    fig.pad + 16,
                    ybot + 41,
                    D.bench_names()[b]
                    + ": real captures, run in progress; row added when its report is final",
                    12.5,
                    MUTED,
                )
            )
            continue
        fig.add(T(fig.pad, yc + 5, D.bench_names()[b], 14, INK))
        pts = [f(b) for _, _, f, _ in series]
        fig.add(
            f'<line x1="{X(pts[0]["agreement"]):.1f}" x2="{X(pts[2]["agreement"]):.1f}" y1="{yc}" y2="{yc}" stroke="{PLUM_TINT}" stroke-width="8" stroke-linecap="round"/>'  # noqa: E501
        )
        for j, ((_, col, _, s), pt) in enumerate(zip(series, pts, strict=False)):
            yy = yc + (j - 1) * 6
            if pt.get("ci90"):
                fig.add(
                    f'<line x1="{X(pt["ci90"][0]):.1f}" x2="{X(pt["ci90"][1]):.1f}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{col}" stroke-opacity="0.5" stroke-width="2"/>'  # noqa: E501
                )
            fig.add(sym(s, X(pt["agreement"]), yy, col))
        fig.add(T(right + 16, yc + 4, f"{pts[0]['agreement']:.2f}", 11, PLUM, mono=True))
    no_ci = [D.bench_names()[b] for b in bs if not D.gemini_agreement(b).get("ci90")]
    return fig.finish(
        ybot + 80,
        [
            "Agreement compares the order of each of the 28 pairs of parsers under two rankings; pairs are not independent, so the intervals are "  # noqa: E501
            "descriptive. The native ranking here is the harness's per-page native mean, which can differ from the official aggregate. "  # noqa: E501
            "Both judges use the same Reducto-written prompt, so GPT-Gemini agreement shows the two models read that prompt alike; it does not validate the prompt. "  # noqa: E501
            + (
                f"No interval is reported for GPT vs Gemini on {', '.join(no_ci)}; the value is recomputed from the two judges' clean means. "  # noqa: E501
                if no_ci
                else ""
            )
            + (
                f"{D.bench_names()[D.REAL5]} GPT vs Gemini covers the {D.real5_report('common_pages.json')['pages']} pages both judges scored."  # noqa: E501
                if D.REAL5 in bs
                else ""
            ),
        ],
    )


def sym(kind, x, y, col):
    if kind == "dot":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{col}"/>'
    if kind == "diamond":
        return f'<path d="M{x:.1f},{y - 6:.1f} L{x + 6:.1f},{y:.1f} L{x:.1f},{y + 6:.1f} L{x - 6:.1f},{y:.1f} Z" fill="{col}"/>'  # noqa: E501
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{BG}" stroke="{col}" stroke-width="2"/>'


# 5. Sampling provenance


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def provenance():
    rows = D.benchmarks() + D.pending()
    tl = {b: D.timeline(b) for b in rows}
    sha, seed_when = D.seed_commit()
    seeds = {tl[b]["seed"] for b in rows}
    assert len(seeds) == 1
    seed = seeds.pop()
    fig = Fig(
        "05_sampling_provenance",
        1600,
        "Sampling provenance",
        f"Saved sampling timestamps and available resampling checks for seed {seed}. Unavailable entries are shown as a dash.",  # noqa: E501
    )
    left, right = fig.pad + 170, fig.w - fig.pad - 430
    rh, top = 38, fig.top + 70
    times = [ts(tl[b][k]) for b in rows for k in ("drawn", "committed", "first_call") if tl[b][k]]
    t0 = min(times).replace(second=0, microsecond=0) - timedelta(minutes=2)
    t1 = max(times) + timedelta(minutes=3)
    span = (t1 - t0).total_seconds()

    def X(t):
        return (
            left + (ts(t) - t0).total_seconds() / span * (right - left)
            if isinstance(t, str)
            else left + (t - t0).total_seconds() / span * (right - left)
        )

    ybot = top + rh * len(rows)
    tick = t0.replace(minute=t0.minute // 10 * 10) + timedelta(minutes=10)
    while tick < t1:
        fig.add(f'<line x1="{X(tick):.1f}" x2="{X(tick):.1f}" y1="{top - 12}" y2="{ybot}" stroke="{TRACK}"/>')
        fig.add(T(X(tick), ybot + 18, tick.strftime("%H:%M"), 11, FAINT, mono=True, anchor="middle"))
        tick += timedelta(minutes=10)
    fig.add(
        T(right, ybot + 36, f"UTC, {ts(seed_when).strftime('%Y-%m-%d')}", 11, FAINT, mono=True, anchor="end")
    )
    first = min(ts(tl[b]["drawn"]) for b in rows)
    gap = int((first - ts(seed_when)).total_seconds() // 60)
    fig.add(
        f'<line x1="{left - 14}" x2="{left - 14}" y1="{top - 30}" y2="{ybot}" stroke="{PLUM}" stroke-dasharray="3 3"/>'  # noqa: E501
    )
    fig.add(
        T(
            left - 8,
            top - 20,
            f"seed {seed} fixed in harness commit {sha} at {ts(seed_when).strftime('%H:%M')}, {gap} min before the first sample",  # noqa: E501
            11,
            PLUM,
            mono=True,
        )
    )
    syms = [
        (
            "Sample drawn",
            lambda cx, cy: (
                f'<circle cx="{cx}" cy="{cy}" r="4.5" fill="{BG}" stroke="{INK2}" stroke-width="1.6"/>'
            ),
        ),
        (
            "Page list committed",
            lambda cx, cy: f'<rect x="{cx - 4.5}" y="{cy - 4.5}" width="9" height="9" fill="{INK2}"/>',
        ),
        ("First vendor parse call", lambda cx, cy: f'<circle cx="{cx}" cy="{cy}" r="5.5" fill="{PLUM}"/>'),
    ]
    legend(fig, fig.top + 10, syms)
    cols = [
        ("PAGES", right + 80),
        ("RECOMPUTED", right + 190),
        ("SAME SET", right + 270),
        ("TIMED CALLS", right + 410),
    ]
    for lab, cx in cols:
        fig.add(T(cx, top - 20, lab, 10, FAINT, mono=True, anchor="end" if lab != "SAME SET" else "middle"))
    for k, b in enumerate(rows):
        r, yc = tl[b], top + k * rh + rh / 2 - 6
        fig.add(
            f'<line x1="{fig.pad}" x2="{fig.w - fig.pad}" y1="{yc + rh / 2:.1f}" y2="{yc + rh / 2:.1f}" stroke="{TRACK}"/>'  # noqa: E501
        )
        fig.add(T(fig.pad, yc + 5, D.bench_names()[b], 14, INK if b not in D.pending() else MUTED))
        xd, xc = X(r["drawn"]), X(r["committed"])
        end = X(r["first_call"]) if r["first_call"] else xc + 70
        fig.add(
            f'<line x1="{xd:.1f}" x2="{xc:.1f}" y1="{yc}" y2="{yc}" stroke="{FAINT}" stroke-width="1.5"/>'
        )
        dash = "" if r["first_call"] else ' stroke-dasharray="3 3"'
        fig.add(
            f'<line x1="{xc:.1f}" x2="{end:.1f}" y1="{yc}" y2="{yc}" stroke="{PLUM_SOFT}" stroke-width="3"{dash}/>'  # noqa: E501
        )
        fig.add(syms[0][1](f"{xd:.1f}", f"{yc:.1f}"))
        fig.add(syms[1][1](xc, yc))
        if r["first_call"]:
            fig.add(syms[2][1](f"{end:.1f}", f"{yc:.1f}"))
            lead = ts(r["first_call"]) - ts(r["committed"])
            m, s = divmod(int(lead.total_seconds()), 60)
            fig.add(T(end + 10, yc + 4, f"+{m}m {s:02d}s" if m else f"+{s}s", 11, PLUM, mono=True))
        else:
            fig.add(T(end + 8, yc + 4, "timing unavailable", 11, MUTED, mono=True))
        fig.add(T(cols[0][1], yc + 4, r["pages"], 12, INK2, mono=True, anchor="end"))
        fig.add(
            T(
                cols[1][1],
                yc + 4,
                r["resampled"] if r["resampled"] is not None else "-",
                12,
                INK2,
                mono=True,
                anchor="end",
            )
        )  # noqa: E501
        fig.add(
            T(
                cols[2][1],
                yc + 4,
                "-" if r["same_set"] is None else "yes" if r["same_set"] else "no",
                12,
                INK2 if r["same_set"] else "#a0444c",
                mono=True,
                anchor="middle",
            )
        )
        timed = (
            f"{math.floor(100 * (r['records'] - r['records_no_finish']) / r['records'])}%"
            if r["records"]
            else "-"
        )
        fig.add(T(cols[3][1], yc + 4, timed, 12, INK2, mono=True, anchor="end"))
    return fig.finish(
        ybot + 56,
        [
            "The plum segment is the time between committing the page list and the earliest vendor parse call (earliest finish time minus latency over every "  # noqa: E501
            "vendor record in S3). Timed calls is the share of vendor records that carry a finish time; the rest are skipped. All times come from the "  # noqa: E501
            "study's machines and git. One 20-page DP-Bench cost pilot preceded the study.",  # noqa: E501
        ],
    )


# Rendering


def font_css():
    faces = [
        ("Roobert", "Roobert-Regular.otf", 400),
        ("Roobert", "Roobert-Medium.otf", 500),
        ("Berkeley Mono", "BerkeleyMono-Regular.otf", 400),
    ]
    return "".join(
        f"@font-face{{font-family:'{f}';src:url('file://{FONT_DIR / n}');font-weight:{w};}}"
        for f, n, w in faces
    )


def chrome():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    shells = sorted(
        Path.home().glob(".cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell")
    )
    if shells:
        return str(shells[-1])
    for c in ("chromium", "google-chrome", "chrome"):
        if shutil.which(c):
            return shutil.which(c)
    sys.exit("headless Chrome not found")


def render_png(svg, w, h, out):
    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "p.html"
        page.write_text(
            f"<!doctype html><html><head><style>{font_css()}html,body{{margin:0;background:{BG}}}</style></head><body>{svg}</body></html>"  # noqa: E501
        )
        subprocess.run(
            [
                chrome(),
                "--disable-gpu",
                "--hide-scrollbars",
                "--allow-file-access-from-files",
                "--force-device-scale-factor=2",
                f"--window-size={w},{h}",
                "--virtual-time-budget=3000",
                f"--screenshot={out}",
                f"file://{page}",
            ],
            check=True,
            capture_output=True,
        )


def size(svg):
    head = svg[: svg.index(">")]

    def get(k):
        return int(float(head.split(f'{k}="')[1].split('"')[0]))

    return get("width"), get("height")


def contact_sheet(names):
    cards = "".join(
        f'<figure><img src="file://{OUT / (n + "@2x.png")}"><figcaption>{n}.svg / {n}@2x.png</figcaption></figure>'  # noqa: E501
        for n in names
    )
    css = (
        f"{font_css()}body{{margin:0;padding:48px;background:#f0f0f0;font-family:Roobert,sans-serif;width:2400px}}"
        "h1{font-weight:500;font-size:34px;margin:0 0 8px}p{color:#737373;margin:0 0 32px;font-size:16px}"
        ".g{display:grid;grid-template-columns:1fr 1fr;gap:32px}figure{margin:0;background:#fff;border:1px solid #e5e5e5;border-radius:6px;padding:16px}"  # noqa: E501
        "img{width:100%;display:block}figcaption{font-family:'Berkeley Mono',monospace;font-size:13px;color:#737373;margin-top:10px}"  # noqa: E501
    )
    doc = f"<!doctype html><html><head><style>{css}</style></head><body><h1>BenchBench blog figures</h1><p>Contact sheet, generated by make_figures.py.</p><div class='g'>{cards}</div></body></html>"  # noqa: E501
    with tempfile.TemporaryDirectory() as td:
        page = Path(td) / "c.html"
        page.write_text(doc)
        subprocess.run(
            [
                chrome(),
                "--disable-gpu",
                "--hide-scrollbars",
                "--allow-file-access-from-files",
                "--force-device-scale-factor=1",
                "--window-size=2496,3600",
                "--virtual-time-budget=5000",
                f"--screenshot={OUT / 'contact_sheet.png'}",
                f"file://{page}",
            ],
            check=True,
            capture_output=True,
        )


def main():
    errs = D.check_against_report()
    for e in errs:
        print("Snapshot differs from primary CSV:", e)
    figs = {
        "01_native_vs_judge_rank": hero,
        "02_three_graders_by_benchmark": grid,
        "03_perturbation_loss": perturbation,
        "04_grader_agreement": agreement,
        "05_sampling_provenance": provenance,
    }
    for name, fn in figs.items():
        svg = fn()
        (OUT / f"{name}.svg").write_text(svg)
        w, h = size(svg)
        render_png(svg, w, h, OUT / f"{name}@2x.png")
        print("wrote", name, w, h)
    if "--no-sheet" not in sys.argv:
        contact_sheet(list(figs))


if __name__ == "__main__":
    main()
