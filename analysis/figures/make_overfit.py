"""BenchBench overfit view: one row per benchmark, who built it, and how each parser moves between
standard settings and the shakeup.
python3 analysis/figures/make_overfit.py writes 07_overfit_by_benchmark.svg and @2x.png next to this file.
Ranks and tilt losses come from data.py (results.csv); builders from the benchmark catalog."""

import data as D
import make_figures as M
import yaml
from make_figures import FAINT, INK, INK2, MUTED, PLUM, PLUM_TINT, REDUCTO, RULE, TL, TRACK, T, tw, wrap

NAME = "07_overfit_by_benchmark"
PAD, LABEL_W, CELL, GAP_BLOCK, ROW = 64, 300, 62, 48, 44
SHORT = {"Azure Document Intelligence": "Azure DI"}


def short(p):
    n = D.vendor_names()[p]
    return SHORT.get(n, n)


def builders():
    catalog = yaml.safe_load((D.ROOT / "benchbench/catalog.yaml").read_text())
    by_id = {b["id"]: b for b in catalog["benchmarks"]}
    return {b: (by_id[b]["builder"], by_id[b].get("home_preset")) for b in D.benchmarks()}


def mix(a, b, t):
    a, b = [int(a[i : i + 2], 16) for i in (1, 3, 5)], [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b, strict=False))


def build():
    bs, ps, vn, n = D.benchmarks(), D.presets(), D.vendor_names(), len(D.benchmarks())
    own = builders()
    W = PAD * 2 + LABEL_W + 2 * len(ps) * CELL + GAP_BLOCK
    homes = [(b, p) for b, (_, p) in own.items() if p]
    home_txt = "; ".join(
        f"{vn[p]} {D.row(b, p)['native_rank']} to {D.row(b, p)['gpt_clean_rank']} on {D.bench_names()[b]}"
        for b, p in homes
    )
    up = sum(D.row(b, REDUCTO)["gpt_clean_rank"] < D.row(b, REDUCTO)["native_rank"] for b in bs)
    least, most = {p: 0 for p in ps}, {p: 0 for p in ps}
    for b in bs:
        d = {p: D.row(b, p)["gpt_tilt_delta"] for p in ps}
        least[max(d, key=d.get)] += 1
        most[min(d, key=d.get)] += 1
    lb, mb = max(least, key=least.get), max(most, key=most.get)
    fig = M.Fig(
        NAME,
        W,
        "BenchBench: does each benchmark's ranking survive a shakeup?",
        "One row per benchmark, with who built it. Left: each parser's rank under the benchmark's own scorer, then under the GPT judge "  # noqa: E501
        "(all eight parses of a page scored side by side, vendor names hidden, on a judge prompt Reducto wrote). "  # noqa: E501
        "Right: how much GPT score each parser loses when the same pages are tilted 2 to 4 degrees. ",
        pad=PAD,
    )
    y = fig.top
    xa = PAD + LABEL_W
    xb = xa + len(ps) * CELL + GAP_BLOCK
    blocks = [
        (
            xa,
            "Grader shakeup: rank under own scorer to GPT judge",
            [
                f"Builders' own parsers: {home_txt}.",
                f"GPT ranks Reducto above its native rank on {up} of {n}; the judge prompt is Reducto's own home field.",  # noqa: E501
            ],
        ),
        (
            xb,
            "Input shakeup: GPT score lost on tilted pages (0 to 10)",
            [
                f"{vn[lb]} loses least on {least[lb]} of {n}, Reducto on {least[REDUCTO]}; {vn[mb]} loses most on {most[mb]} of {n}.",  # noqa: E501
                "Point estimates, one GPT repeat; we do not claim Reducto is the most tilt-stable.",
            ],
        ),
    ]
    for x, head, takes in blocks:
        fig.add(T(x, y, head, 15, INK, weight=500))
        bw = len(ps) * CELL - 4
        lines = [line for t in takes for line in wrap(t, 12, bw)]
        fig.add(TL(x, y + 22, lines, 12, 16, fill=MUTED))
    y += (
        22 + 16 * max(sum(len(wrap(t, 12, len(ps) * CELL - 4)) for t in takes) for _, _, takes in blocks) + 18
    )
    for x0 in (xa, xb):
        for i, p in enumerate(ps):
            cx = x0 + i * CELL + CELL / 2
            lines = wrap(short(p), 11.5, CELL - 4)
            fig.add(
                TL(
                    cx,
                    y + (14 if len(lines) == 1 else 0),
                    lines,
                    11.5,
                    14,
                    fill=PLUM if p == REDUCTO else INK2,
                    anchor="middle",
                    weight=500 if p == REDUCTO else 400,
                )
            )
    y += 30
    fig.add(T(PAD, y - 8, "Benchmark (builder)", 11, FAINT, mono=True))
    top = y
    for k, b in enumerate(bs):
        yy = y + k * ROW
        if k:
            fig.add(f'<line x1="{PAD}" x2="{W - PAD}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{RULE}"/>')
        builder, bp = own[b]
        fig.add(T(PAD, yy + 19, D.bench_names()[b], 14, INK, weight=500))
        sub = f"{builder}, own parser in study" if bp else builder
        fig.add(
            T(
                PAD,
                yy + 35,
                wrap(sub, 11, LABEL_W - 16)[0],
                11,
                PLUM if bp == REDUCTO else (INK2 if bp else MUTED),
            )
        )
        for i, p in enumerate(ps):
            r = D.row(b, p)
            # rank cell
            x = xa + i * CELL + 3
            nat, gpt = r["native_rank"], r["gpt_clean_rank"]
            fill = INK2 if nat == 1 else (PLUM_TINT if p == REDUCTO else TRACK)
            col = "#ffffff" if nat == 1 else (PLUM if p == REDUCTO else INK)
            fig.add(
                f'<rect x="{x:.1f}" y="{yy + 6:.1f}" width="{CELL - 6}" height="{ROW - 12}" rx="3" fill="{fill}"/>'  # noqa: E501
            )
            if bp == p:
                fig.add(
                    f'<rect x="{x - 2:.1f}" y="{yy + 4:.1f}" width="{CELL - 2}" height="{ROW - 8}" rx="4" fill="none" stroke="{PLUM if p == REDUCTO else INK}" stroke-width="2"/>'  # noqa: E501
                )
            fig.add(
                T(
                    x + (CELL - 6) / 2,
                    yy + ROW / 2 + 5,
                    f"{nat} \u2192 {gpt}",
                    13,
                    col,
                    mono=True,
                    anchor="middle",
                    weight=500 if gpt == 1 else 400,
                )
            )
            # tilt cell
            x = xb + i * CELL + 3
            loss = -r["gpt_tilt_delta"]
            t = max(0.0, min(loss / 1.5, 1.0))
            fill = mix("#f5f5f5", "#404040", t) if p != REDUCTO else mix("#f2e0ec", "#4b163d", t)
            col = "#ffffff" if t > 0.5 else (PLUM if p == REDUCTO else INK)
            fig.add(
                f'<rect x="{x:.1f}" y="{yy + 6:.1f}" width="{CELL - 6}" height="{ROW - 12}" rx="3" fill="{fill}"/>'  # noqa: E501
            )
            if bp == p:
                fig.add(
                    f'<rect x="{x - 2:.1f}" y="{yy + 4:.1f}" width="{CELL - 2}" height="{ROW - 8}" rx="4" fill="none" stroke="{PLUM if p == REDUCTO else INK}" stroke-width="2"/>'  # noqa: E501
                )
            fig.add(
                T(
                    x + (CELL - 6) / 2,
                    yy + ROW / 2 + 5,
                    f"{r['gpt_tilt_delta']:+.2f}",
                    12.5,
                    col,
                    mono=True,
                    anchor="middle",
                )
            )
    y = top + n * ROW + 24
    lx = PAD
    items = [
        (
            lambda cx, cy: f'<rect x="{cx - 13}" y="{cy - 8}" width="26" height="16" rx="3" fill="{INK2}"/>',
            "first under the benchmark's own scorer",
        ),
        (
            lambda cx, cy: (
                f'<rect x="{cx - 13}" y="{cy - 8}" width="26" height="16" rx="3" fill="none" stroke="{INK}" stroke-width="2"/>'  # noqa: E501
            ),
            "builder's own parser on its own benchmark",
        ),
        (
            lambda cx, cy: (
                f'<text x="{cx}" y="{cy + 4}" font-family="{M.esc(M.MONO)}" font-size="12" font-weight="500" fill="{INK}" text-anchor="middle">\u2192 1</text>'  # noqa: E501
            ),
            "bold: first under GPT (a point estimate, not a claim)",
        ),
        (
            lambda cx, cy: f'<rect x="{cx - 13}" y="{cy - 8}" width="26" height="16" rx="3" fill="#404040"/>',
            "darker: larger tilt loss",
        ),
    ]
    for sym, lab in items:
        fig.add(sym(lx + 13, y - 4))
        fig.add(T(lx + 34, y, lab, 12.5, INK2))
        lx += 34 + tw(lab, 12.5) + 36
    y += 30
    notes = [
        "Ranks are point estimates. An order is confirmed only where both GPT and Gemini separate a pair at 95% (Holm over 28 pairs); "  # noqa: E501
        "many adjacent ranks here are not separated. Gemini gives the same first place as GPT on most benchmarks; IDP Leaderboard "  # noqa: E501
        "(LlamaParse first under every grader) and MDPBench (top three not ordered) are where Reducto is not first.",  # noqa: E501
        "Native scores use each benchmark's headline metric on image input, so they are not the published leaderboard numbers. Only three builders "  # noqa: E501
        "have a parser in this study, so no home-field statement is made about the others. Native scores on tilted pages: native_under_tilt.md.",  # noqa: E501
        "Tilt: 2% white margin, then a 2 to 4 degree rotation. "  # noqa: E501
        "Each tilted parse is scored by GPT against the clean page image.",
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
