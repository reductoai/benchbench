"""BenchBench results at a glance: one summary graphic in the style of artificialanalysis.ai bar charts.
python3 analysis/figures/make_at_a_glance.py writes 06_results_at_a_glance.svg and @2x.png next to this file.
Every number comes from data.py (results.csv, benchmark reports and the Real5 report)."""

import statistics

import data as D
import make_figures as M
from make_figures import FAINT, INK, INK2, MUTED, PLUM, PLUM_TINT, REDUCTO, RULE, TL, TRACK, T, tw, wrap

NAME = "06_results_at_a_glance"
W, PAD, GAP = 1760, 64, 24
CARD, GREY_BAR, GREY_SOFT = "#ffffff", "#a3a3a3", "#e5e5e5"
GRADERS = [
    ("native_rank", "Benchmark's own scorer"),
    ("gpt_clean_rank", "GPT judge"),
    ("gemini_own_rank", "Gemini judge"),
]


def card(fig, x, y, w, h):
    fig.add(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="{CARD}" stroke="{RULE}"/>'  # noqa: E501
    )


def first_places(key):
    return {p: sum(D.row(b, p)[key] == 1 for b in D.benchmarks()) for p in D.presets()}


def short(p):
    return D.vendor_names()[p].replace("Azure Document Intelligence", "Azure DI")


def leaders_line(counts):
    vn = D.vendor_names()
    top = sorted((p for p in counts if counts[p]), key=lambda p: -counts[p])
    return ", ".join(f"{vn[p]} {counts[p]}" for p in top)


def hero_panel(fig, x, y, w, h, key, label):
    n = len(D.benchmarks())
    counts = first_places(key)
    r = counts[REDUCTO]
    take = (
        f"Reducto has the top score on none of the {n}."
        if r == 0
        else f"Reducto has the highest clean mean on {r} of {n}."
    )
    count_panel(fig, x, y, w, h, counts, label, take, "Top score: " + leaders_line(counts), r > 0)


def count_panel(fig, x, y, w, h, counts, label, take, sub, plum_take, fmt=str, desc=True):
    n = len(D.benchmarks())
    order = sorted(D.presets(), key=lambda p: ((-1 if desc else 1) * counts[p], D.presets().index(p)))
    card(fig, x, y, w, h)
    fig.add(T(x + 20, y + 34, label, 18, INK, weight=500))
    fig.add(T(x + 20, y + 58, take, 13.5, PLUM if plum_take else INK2))
    fig.add(T(x + 20, y + 78, sub, 12, MUTED))
    base, top = y + h - 58, y + 116
    scale = (base - top) / (n if fmt is str else max(counts.values()))
    slot = (w - 40) / len(order)
    bw = slot * 0.58
    fig.add(
        f'<line x1="{x + 20:.1f}" x2="{x + w - 20:.1f}" y1="{base:.1f}" y2="{base:.1f}" stroke="{RULE}"/>'
    )
    for i, p in enumerate(order):
        cx = x + 20 + slot * (i + 0.5)
        v = counts[p]
        bh = max(v * scale, 2)
        col = PLUM if p == REDUCTO else GREY_BAR
        fig.add(
            f'<rect x="{cx - bw / 2:.1f}" y="{base - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{col}"/>'  # noqa: E501
        )
        fig.add(
            T(
                cx,
                base - bh - 8,
                fmt(v),
                14 if fmt is str else 12.5,
                PLUM if p == REDUCTO else INK,
                mono=True,
                anchor="middle",
                weight=500 if p == REDUCTO else 400,
            )
        )
        lines = wrap(short(p), 11, slot - 4)
        fig.add(
            TL(
                cx,
                base + 18,
                lines,
                11,
                14,
                fill=PLUM if p == REDUCTO else INK2,
                anchor="middle",
                weight=500 if p == REDUCTO else 400,
            )
        )


def tilt_row(fig, y, hw, hh):
    bs, n, vn = D.benchmarks(), len(D.benchmarks()), D.vendor_names()
    top = first_places("gpt_tilt_rank")
    least = {p: 0 for p in D.presets()}
    most = {p: 0 for p in D.presets()}
    for b in bs:
        d = {p: D.row(b, p)["gpt_tilt_delta"] for p in D.presets()}
        least[max(d, key=d.get)] += 1
        most[min(d, key=d.get)] += 1
    med = {p: -statistics.median(D.row(b, p)["gpt_tilt_delta"] for b in bs) for p in D.presets()}
    lb, mb = max(least, key=least.get), max(most, key=most.get)
    count_panel(
        fig,
        PAD,
        y,
        hw,
        hh,
        top,
        "Top GPT score on tilted pages",
        f"Reducto has the highest tilted-page mean on {top[REDUCTO]} of {n}.",
        "Mostly its clean lead carried over. Top score: " + leaders_line(top),
        True,
    )
    count_panel(
        fig,
        PAD + hw + GAP,
        y,
        hw,
        hh,
        least,
        "Smallest loss from tilt",
        f"{vn[lb]} loses least on {least[lb]} of {n}; Reducto on {least[REDUCTO]}.",
        "Point estimates. We do not claim Reducto is the most tilt-stable.",
        False,
    )
    count_panel(
        fig,
        PAD + 2 * (hw + GAP),
        y,
        hw,
        hh,
        med,
        f"Median tilt loss across {n} runs",
        f"{vn[mb]} has the largest tilt loss on {most[mb]} of {n}.",
        "GPT score lost on tilted pages (0 to 10 scale), smallest first.",
        False,
        fmt=lambda v: f"{v:.2f}",
        desc=False,
    )


def bench_panel(fig, x, y, w, h, b):
    rows = sorted(D.presets(), key=lambda p: D.row(b, p)["gpt_clean_rank"])
    loose = M.unordered_set(b)
    card(fig, x, y, w, h)
    fig.add(T(x + 16, y + 28, D.bench_names()[b], 15, INK, weight=500))
    fig.add(T(x + w - 16, y + 28, "native rank", 10.5, FAINT, mono=True, anchor="end"))
    name_w, score_w, nat_w = 84, 34, 30
    x0 = x + 16 + name_w
    bar_max = w - 32 - name_w - score_w - nat_w - 8
    rh, y0 = 21, y + 50
    for i, p in enumerate(rows):
        r, yy = D.row(b, p), y0 + i * rh
        is_r = p == REDUCTO
        fig.add(T(x + 16, yy + 11, short(p), 12, PLUM if is_r else INK2, weight=500 if is_r else 400))
        fig.add(f'<rect x="{x0:.1f}" y="{yy:.1f}" width="{bar_max:.1f}" height="14" rx="2" fill="{TRACK}"/>')
        bw = bar_max * r["gpt_clean"] / 10
        if p in loose:
            fill, stroke = (PLUM_TINT, PLUM) if is_r else (GREY_SOFT, GREY_BAR)
            fig.add(
                f'<rect x="{x0 + 0.5:.1f}" y="{yy + 0.5:.1f}" width="{bw - 1:.1f}" height="13" rx="2" fill="{fill}" stroke="{stroke}" stroke-dasharray="3 2"/>'  # noqa: E501
            )
        else:
            fig.add(
                f'<rect x="{x0:.1f}" y="{yy:.1f}" width="{bw:.1f}" height="14" rx="2" fill="{PLUM if is_r else GREY_BAR}"/>'  # noqa: E501
            )
        fig.add(
            T(
                x0 + bar_max + 6,
                yy + 11,
                f"{r['gpt_clean']:.2f}",
                11.5,
                PLUM if is_r else INK,
                mono=True,
                weight=500 if is_r else 400,
            )
        )
        fig.add(
            T(x + w - 16, yy + 11, r["native_rank"], 11.5, PLUM if is_r else MUTED, mono=True, anchor="end")
        )
    note = wrap(M.claim_note(b), 11.5, w - 32, mono=True)
    fig.add(TL(x + 16, y0 + len(rows) * rh + 18, note, 11.5, 15, fill=INK2, mono=True))


def build():
    n, _vn = len(D.benchmarks()), D.vendor_names()
    cl = D.claims()
    all7 = [b for b in D.benchmarks() if len(cl[b]["claimed"]) == len(D.presets()) - 1]
    six = [
        b for b in D.benchmarks() if len(cl[b]["claimed"]) == len(D.presets()) - 2 and not cl[b]["unordered"]
    ]
    not_first = [b for b in D.benchmarks() if D.row(b, REDUCTO)["gpt_clean_rank"] != 1]
    none_conf = [b for b in D.benchmarks() if "posthoc_over" in cl[b]]
    bn = D.bench_names()
    gpt_first = first_places("gpt_clean_rank")[REDUCTO]
    fig = M.Fig(
        NAME,
        W,
        "BenchBench: who wins depends on who grades",
        f"8 commercial parsers on {n} public parsing benchmarks, clean pages unless marked as rotated. "
        "Two LLM judges (GPT and Gemini) score all eight parses of a page side by side with vendor names hidden, on a judge prompt "  # noqa: E501
        "Reducto wrote. The benchmarks' own scorers split first place among four other vendors; both judges put Reducto first on most benchmarks. ",  # noqa: E501
        pad=PAD,
    )
    y = fig.top
    fig.add(T(PAD, y, f"Benchmarks where each parser has the top score, of {n}", 13, MUTED, mono=True))
    y += 16
    hw, hh = (W - 2 * PAD - 2 * GAP) / 3, 290
    for i, (key, label) in enumerate(GRADERS):
        hero_panel(fig, PAD + i * (hw + GAP), y, hw, hh, key, label)
    y += hh + 44
    fig.add(
        T(
            PAD,
            y,
            "GPT judge score per benchmark, clean pages (0 to 10), with each parser's native rank",
            13,
            MUTED,
            mono=True,
        )
    )
    lx = W - PAD
    lab = "order against Reducto (or inside the group) not claimed"
    fig.add(T(lx, y, lab, 12, MUTED, anchor="end"))
    lx -= tw(lab, 12) + 34
    fig.add(
        f'<rect x="{lx:.1f}" y="{y - 11:.1f}" width="26" height="12" rx="2" fill="{GREY_SOFT}" stroke="{GREY_BAR}" stroke-dasharray="3 2"/>'  # noqa: E501
    )
    y += 16
    cols, pw = 4, (W - 2 * PAD - 3 * GAP) / 4
    ph = (
        50
        + 8 * 21
        + 22
        + 15 * max(len(wrap(M.claim_note(b), 11.5, pw - 32, mono=True)) for b in D.benchmarks())
    )
    for k, b in enumerate(D.benchmarks()):
        r, c = divmod(k, cols)
        bench_panel(fig, PAD + c * (pw + GAP), y + r * (ph + GAP), pw, ph, b)
    rows = -(-n // cols)
    y += rows * ph + (rows - 1) * GAP + 44
    fig.add(T(PAD, y, "Rotated pages: the same pages tilted 2 to 4 degrees, GPT judge", 13, MUTED, mono=True))
    y += 16
    tilt_row(fig, y, hw, hh)
    y += hh + 36

    def names(bs):
        return ", ".join(bn[b] for b in bs[:-1]) + (" and " if len(bs) > 1 else "") + bn[bs[-1]]

    nat = [D.row(b, REDUCTO)["native_rank"] for b in D.benchmarks()]
    rest = [r for r in nat if r != 2]
    notes = [
        f"Top score is a point estimate, not a claim. Claims need both judges to separate a pair at 95% (paired page bootstrap, Holm over 28 pairs). "  # noqa: E501
        f"Reducto is claimed over all 7 others on {len(all7)} benchmarks ({names(all7)}) and over 6 of 7 on {len(six)}. "  # noqa: E501
        f"It is not first on {names(not_first)}; on {names(none_conf)} no pair is confirmed under the complete-coverage rule.",  # noqa: E501
        f"Real5's clean pages are OmniDocBench pages under the same scorer, so {gpt_first} of {n} is {gpt_first - 1} of {n - 1} distinct benchmarks. "  # noqa: E501
        f"Under the benchmarks' own scorers Reducto is 2nd on {nat.count(2)} benchmarks and {min(rest)}rd to {max(rest)}th on the other {len(rest)}. "  # noqa: E501
        "Native scores use the benchmark's headline metric on image input, "
        "so they are not the published leaderboard numbers.",
        "Judges: GPT-6.1 Sol (primary, image detail high, about 165 DPI on a letter page) and Gemini 3.1 Pro in its own label order, prompt compare-v4. "  # noqa: E501
        "The prompt rewards figure descriptions, which Reducto writes by default. "
        "Samples: full sets up to 300 pages, else 500 pages drawn with one seed (20261107) for every benchmark.",  # noqa: E501
        "Tilt: 2% white margin, then a 2 to 4 degree rotation; "  # noqa: E501
        "one GPT repeat. "
        "On Real5's real captures Reducto has the highest GPT score in every condition, but its loss is 2nd or 3rd smallest on each.",  # noqa: E501
    ]
    return fig.finish(y, notes)


def main():
    svg = build()
    (M.OUT / f"{NAME}.svg").write_text(svg)
    w, h = M.size(svg)
    M.render_png(svg, w, h, M.OUT / f"{NAME}@2x.png")
    print("wrote", NAME, w, h)


if __name__ == "__main__":
    main()
