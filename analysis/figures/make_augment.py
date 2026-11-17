"""Native score before vs after damage (08) and pages where damage costs the most (09).

python3 analysis/figures/make_augment.py
Reads ../native_under_damage.csv (from native_under_damage.py) and the page images and parses in augment/.
"""

import base64
import csv
import io

import data as D
from make_figures import BG, FAINT, INK, INK2, MUTED, OUT, PLUM, RULE, T, render_png, size
from PIL import Image

CSV = D.SYN / "native_under_damage.csv"
AUG = OUT / "augment"
LOSS, GAIN = "#b8483b", "#3f6f9a"
NOISE = 1.0
BENCH = {
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
}
SOURCE = "Source: results/native_under_damage.csv. Damaged = the same pages tilted 2-4°."


def svg(w, h, body):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="{w}" height="{h}" fill="{BG}"/>{body}</svg>'  # noqa: E501


def before_after():
    rows = list(csv.DictReader(open(CSV)))
    by = {}
    for r in rows:
        by.setdefault(r["benchmark"], []).append(r)
    W, cols, pw, ph, gx, gy, top, left = 1280, 4, 290, 236, 20, 28, 150, 40
    flips = sum(
        1
        for rr in by.values()
        if next(r for r in rr if r["clean_rank"] == "1")["vendor"]
        != next(r for r in rr if r["damaged_rank"] == "1")["vendor"]
    )
    big = sum(1 for r in rows if float(r["delta_damaged"]) <= -2)
    out = [
        T(left, 52, f"A 2-4° tilt changes first place on {flips} of {len(by)} benchmarks", 28, weight=500),
        T(
            left,
            82,
            f"Native score on clean pages (open dot) and on the same pages tilted (filled dot). {big} of {len(rows)} parser-benchmark pairs drop 2+ points.",  # noqa: E501
            15,
            MUTED,
        ),
    ]
    lx = left
    for col, lab in ((LOSS, "lost 1+ point"), (GAIN, "gained 1+ point"), (FAINT, "within 1 point")):
        out.append(f'<circle cx="{lx + 5}" cy="112" r="5" fill="{col}"/>')
        out.append(T(lx + 16, 117, lab, 13, INK2))
        lx += 30 + len(lab) * 7.5
    nrows = (len(BENCH) + cols - 1) // cols
    for i, b in enumerate(BENCH):
        rr = sorted(by[b], key=lambda r: int(r["clean_rank"]))
        x0, y0 = left + (i % cols) * (pw + gx), top + (i // cols) * (ph + gy)
        vals = [float(r[k]) for r in rr for k in ("native_clean", "native_damaged")]
        lo, hi = 5 * int(min(vals) // 5), 5 * int(-(-max(vals) // 5))
        ax0, ax1 = x0 + 92, x0 + pw - 40

        def X(v, ax0=ax0, ax1=ax1, lo=lo, hi=hi):
            return ax0 + (v - lo) / (hi - lo) * (ax1 - ax0)

        c1 = rr[0]["vendor"]
        d1 = next(r for r in rr if r["damaged_rank"] == "1")["vendor"]
        out.append(T(x0, y0 + 14, BENCH[b], 15, weight=500))
        if c1 != d1:
            out.append(T(x0 + pw, y0 + 14, "1st place changes", 11, PLUM, anchor="end", weight=500))
        out.append(T(x0, y0 + 30, rr[0]["native_metric"], 10.5, FAINT, mono=True))
        ry0 = y0 + 50
        for j, r in enumerate(rr):
            y = ry0 + j * 20
            c, d = float(r["native_clean"]), float(r["native_damaged"])
            dd = d - c
            col = LOSS if dd <= -NOISE else GAIN if dd >= NOISE else FAINT
            reducto = r["preset"] == "reducto_r1"
            out.append(f'<line x1="{ax0}" x2="{ax1}" y1="{y}" y2="{y}" stroke="{RULE}" stroke-width="1"/>')
            out.append(
                T(x0, y + 4, r["vendor"], 12, PLUM if reducto else INK2, weight=500 if reducto else 400)
            )
            out.append(
                f'<line x1="{X(c):.1f}" x2="{X(d):.1f}" y1="{y}" y2="{y}" stroke="{col}" stroke-width="3" stroke-linecap="round"/>'  # noqa: E501
            )
            out.append(
                f'<circle cx="{X(c):.1f}" cy="{y}" r="4.2" fill="{BG}" stroke="{col if col != FAINT else MUTED}" stroke-width="1.5"/>'  # noqa: E501
            )
            out.append(f'<circle cx="{X(d):.1f}" cy="{y}" r="4.2" fill="{col if col != FAINT else MUTED}"/>')
            if abs(dd) >= NOISE:
                out.append(T(ax1 + 8, y + 4, f"{dd:+.0f}", 11, col, mono=True))
        yb = ry0 + len(rr) * 20 - 6
        for v in (lo, (lo + hi) / 2, hi):
            out.append(T(X(v), yb + 10, f"{v:g}", 10, FAINT, mono=True, anchor="middle"))
    H = top + nrows * (ph + gy) + 30
    out.append(T(left, H - 30, SOURCE, 11, FAINT))
    out.append(
        T(
            left,
            H - 14,
            "Scales differ by panel. Changes under 1 point are within run-to-run noise. The study was written by Reducto.",  # noqa: E501
            11,
            FAINT,
        )
    )
    return svg(W, H, "".join(out))


def thumb(path, w, h):
    im = Image.open(path).convert("RGB")
    im.thumbnail((w * 2, h * 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return im.size[0] / 2, im.size[1] / 2, base64.b64encode(buf.getvalue()).decode()


CASES = [
    dict(
        vendor="LlamaParse",
        bench="idp_leaderboard",
        page="idp_leaderboard__small_sparse_unstructured_table_17.jpg",
        cond="tilt_2_4",
        damage="Tilted 2-4°",
        clean=100,
        damaged=0,
        note="Read the tilted table as a list of columns, so no cell lands in its row.",
    ),
    dict(
        vendor="Reducto",
        bench="idp_leaderboard",
        page="idp_leaderboard__small_sparse_unstructured_table_27.jpg",
        cond="tilt_2_4",
        damage="Tilted 2-4°",
        clean=100,
        damaged=0,
        note="Same failure: every value kept, the table lost.",
    ),
    dict(
        vendor="Cohere",
        bench="ocrflux_bench",
        page="ocrflux_bench__pdfs_2549456_46.pdf",
        cond="tilt_2_4",
        damage="Tilted 2-4°",
        clean=91.7,
        damaged=3.1,
        note="Repeated one clause over and over instead of reading the page.",
    ),
]


def gallery():
    W, left, top, cw, gap, th = 1280, 40, 120, 384, 24, 300
    out = [
        T(left, 52, "A small tilt can zero a page", 28, weight=500),
        T(
            left,
            82,
            "Pages where one parser's native score collapsed under tilt. Left: the page it scored on clean. Right: the tilted copy.",  # noqa: E501
            15,
            MUTED,
        ),
    ]
    for i, c in enumerate(CASES):
        x0 = left + i * (cw + gap)
        out.append(
            f'<rect x="{x0}" y="{top}" width="{cw}" height="{th + 150}" fill="#ffffff" stroke="{RULE}" rx="6"/>'  # noqa: E501
        )
        out.append(
            T(
                x0 + 16,
                top + 28,
                f"{c['vendor']} on {BENCH[c['bench']]}",
                15,
                PLUM if c["vendor"] == "Reducto" else INK,
                weight=500,
            )
        )
        iw = (cw - 48) / 2
        for k, (cond, lab, score) in enumerate(
            (("clean", "Clean", c["clean"]), (c["cond"], c["damage"], c["damaged"]))
        ):
            tw_, th_, b64 = thumb(AUG / f"{c['bench']}.{cond}.{c['page']}.png", iw, th - 70)
            ix = x0 + 16 + k * (iw + 16)
            iy = top + 46
            out.append(
                f'<rect x="{ix}" y="{iy}" width="{iw}" height="{th - 70}" fill="{BG}" stroke="{RULE}"/>'
            )
            out.append(
                f'<image x="{ix + (iw - tw_) / 2:.1f}" y="{iy + (th - 70 - th_) / 2:.1f}" width="{tw_:.1f}" height="{th_:.1f}" href="data:image/jpeg;base64,{b64}"/>'  # noqa: E501
            )
            out.append(T(ix, iy + th - 46, lab, 12, MUTED))
            out.append(T(ix, iy + th - 18, f"{score:g}", 26, INK if k == 0 else LOSS, mono=True))
        ny = top + th + 50
        words, line, lines = c["note"].split(), "", []
        for wd in words:
            if len(line + " " + wd) * 7.4 > cw - 32:
                lines.append(line)
                line = wd
            else:
                line = (line + " " + wd).strip()
        lines.append(line)
        for j, ln in enumerate(lines):
            out.append(T(x0 + 16, ny + 30 + j * 19, ln, 14, INK2))
    H = top + th + 150 + 56
    out.append(
        T(
            left,
            H - 30,
            "Native score (0-100) for that page from the benchmark's own scorer. IDP Leaderboard tables are synthetic; OCRFlux-bench page is a Chinese filing.",  # noqa: E501
            11,
            FAINT,
        )
    )
    out.append(
        T(
            left,
            H - 14,
            "Source: Bench Bench runs, local native and parse records. The study was written by Reducto.",
            11,
            FAINT,
        )
    )
    return svg(W, H, "".join(out))


def main():
    for name, fn in (("08_native_before_after", before_after), ("09_damage_examples", gallery)):
        s = fn()
        (OUT / f"{name}.svg").write_text(s)
        render_png(s, *size(s), OUT / f"{name}@2x.png")
        print("wrote", name)


if __name__ == "__main__":
    main()
