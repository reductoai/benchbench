"""DP-Bench (Upstage) native scorer adapter.

Scorer: the dataset repo's own `evaluate.py` + `src/` at the pinned revision, run unmodified as a subprocess
(`--mode all`, its defaults: NID ignores figure/table/chart, `--filter-by-gt-area`, min match 0.1).

Per-page `score` is NID x 100 (the benchmark's element-text metric; the scorer's corpus NID is the mean of
these). Table metrics are per page in `subscores` (TEDS / TEDS-S of matched tables, table counts) and per
run in `official.json` (the scorer's Table F1, TEDS, TEDS-S).

Conversion (the scorer wants Upstage-style elements; every parse here is markdown). One rule for all presets:
1. HTML tables and pipe tables become `table` elements (`content.html`); pipe tables are converted with the
   harness's `pipe_table_to_html`.
2. Every other blank-line block becomes one `paragraph` element (`heading1` if it starts with `#`) with
   markdown syntax removed: image references (alt text included), link targets, heading marks, bold and
   italic marks, list bullets, `$$`/`\\[ \\]` math delimiters, remaining HTML tags and entities. Azure's
   `<!-- PageHeader="..." -->`, `PageFooter` and `PageNumber` comments are kept as their text (it is what the
   parser read); other HTML comments are dropped.
3. A block the parser itself marks as a figure (`<figure ...>...</figure>`, which Azure, Extend and Pulse
   write) becomes one `figure` element, tables inside it included. The scorer ignores figure elements, as it
   would for an Upstage-style parser that labels a figure. A `<figcaption>` inside it (Azure) is printed
   caption text, so it stays a `paragraph` before the figure element. Image references are dropped (rule 2).
4. Coordinates are zero boxes (markdown has none), as in Upstage's own LlamaParse script for tables. So the
   scorer's GT-area filter cannot drop figure or chart text that a parser writes WITHOUT figure markup
   (plain description paragraphs, chart data tables): that text counts as insertions in NID and as extra
   predicted tables in Table F1.
Failed parses are left out of the prediction file (the scorer reports them as missing) and get no row.
"""

import html as html_lib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ..probes import PIPE_TABLE, TABLE_HTML, pipe_table_to_html, strip_emphasis
from ..storage import read_json

REPO = "upstage/dp-bench"
REVISION = "24702c61a2fb13325534be664653bc6e60250d13"
CACHE = (
    Path(os.environ.get("BENCHBENCH_CACHE", Path.home() / ".cache" / "benchbench")) / "dp_bench" / REVISION
)
WARNINGS = [
    "markdown converted to Upstage elements (adapters/dp_bench.py); zero coordinates, so GT-area filtering "
    "of figure/chart text is inactive for every preset"
]

AZURE_COMMENT = re.compile(r'<!--\s*Page(?:Header|Footer|Number)="(.*?)"\s*-->', re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
BULLET = re.compile(r"^\s*[-*+]\s+", re.M)
TAG = re.compile(r"<[^>]+>")
FIGURE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.S | re.I)
FIGURE_TOKEN = "\x00FIGURE{}\x00"
FIGCAPTION = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.S | re.I)
TABLE_TOKEN = "\x00TABLE{}\x00"


def scorer_dir() -> Path:
    if not (CACHE / "evaluate.py").exists():
        from huggingface_hub import snapshot_download

        snapshot_download(
            REPO,
            repo_type="dataset",
            revision=REVISION,
            allow_patterns=["evaluate.py", "src/*", "dataset/reference.json", "requirements.txt"],
            local_dir=str(CACHE),
        )
    return CACHE


def reference() -> dict:
    return json.loads((scorer_dir() / "dataset" / "reference.json").read_text())


def _gt_key(page: dict) -> str:
    return Path(page["file"]).name


def _plain(block: str) -> str:
    t = IMAGE.sub("", block)
    t = LINK.sub(r"\1", t)
    t = HEADING.sub("", t)
    t, _ = strip_emphasis(t, None)
    t = BULLET.sub("", t)
    t = t.replace("$$", "").replace("\\[", "").replace("\\]", "")
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = TAG.sub("", t)
    return html_lib.unescape(t).strip()


def md_to_elements(md: str) -> list[dict]:
    md = AZURE_COMMENT.sub(lambda m: "\n\n" + html_lib.unescape(m.group(1)) + "\n\n", md)
    md = COMMENT.sub("", md)
    tables: list[str] = []
    figures: list[str] = []

    def keep_figure(block: str) -> str:
        figures.append(FIGCAPTION.sub("", block))
        caps = "\n\n".join(FIGCAPTION.findall(block))
        return "\n\n" + caps + "\n\n" + FIGURE_TOKEN.format(len(figures) - 1) + "\n\n"

    md = FIGURE.sub(lambda m: keep_figure(m.group(0)), md)

    def keep(table_html: str) -> str:
        tables.append(table_html)
        return "\n\n" + TABLE_TOKEN.format(len(tables) - 1) + "\n\n"

    md = TABLE_HTML.sub(lambda m: keep(m.group(0)), md)
    md = PIPE_TABLE.sub(lambda m: keep(pipe_table_to_html(m.group(0))), md)
    elements = []
    for block in re.split(r"\n\s*\n", md):
        if not block.strip():
            continue
        m = re.fullmatch(r"\s*\x00TABLE(\d+)\x00\s*", block)
        fig = re.fullmatch(r"\s*\x00FIGURE(\d+)\x00\s*", block)
        if m:
            cat, text, tab = "table", "", tables[int(m.group(1))]
        elif fig:
            cat, text, tab = "figure", " ".join(TAG.sub(" ", figures[int(fig.group(1))]).split()), ""
        else:
            cat = "heading1" if HEADING.match(block) else "paragraph"
            text, tab = _plain(block), ""
            if not text:
                continue
        elements.append(
            {
                "coordinates": [{"x": 0, "y": 0}] * 4,
                "category": cat,
                "id": len(elements),
                "page": 1,
                "content": {"text": text, "html": tab, "markdown": ""},
            }
        )
    return elements


def gt_markdown(page: dict) -> str | None:
    doc = reference().get(_gt_key(page))
    if doc is None:
        return None
    parts = []
    for e in doc["elements"]:
        cat, c = e["category"].lower(), e["content"]
        if cat in ("figure", "chart"):
            continue  # pictures; the scorer ignores their text
        if cat == "table":
            parts.append(f"<table>{c['html']}</table>")
        elif cat == "equation":
            parts.append(f"$$\n{c['text']}\n$$")
        elif cat == "heading1":
            parts.append(f"# {c['text']}")
        elif c["text"].strip():
            parts.append(c["text"])
    return "\n\n".join(parts) + "\n"


def export(run, cond, preset, pages, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = reference()
    keys = [_gt_key(p) for p in pages]
    (out_dir / "reference.json").write_text(json.dumps({k: ref[k] for k in keys}, ensure_ascii=False))
    pred, missing = {}, []
    for p in pages:
        d = read_json(run.parse(cond, preset, p["page_key"]))
        if not d or not d.get("ok"):
            missing.append(p["page_key"])
            continue
        pred[_gt_key(p)] = {"elements": md_to_elements(d.get("markdown") or "")}
    (out_dir / "pred.json").write_text(json.dumps(pred, ensure_ascii=False))
    (out_dir / "missing.json").write_text(json.dumps(missing))


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    if not json.loads((out_dir / "pred.json").read_text()):
        return []
    proc = subprocess.run(
        [
            sys.executable,
            "evaluate.py",
            "--ref-path",
            str(out_dir / "reference.json"),
            "--pred-path",
            str(out_dir / "pred.json"),
            "--mode",
            "all",
            "--max-workers",
            "8",
        ],
        cwd=scorer_dir(),
        capture_output=True,
        text=True,
    )
    (out_dir / "scorer.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"dp_bench scorer failed for {cond}/{preset}: {proc.stderr[-2000:]}")
    ev = json.loads((out_dir / "pred.eval.json").read_text())
    official = {
        "nid": ev["layout"]["nid_score"],
        **{k: ev["table"][k] for k in ("table_f1_score", "teds_score", "teds_s_score")},
        "data_statistics": ev["data_statistics"],
        "scorer_commit": REVISION,
    }
    (out_dir / "official.json").write_text(json.dumps(official, indent=1))
    by_key = {_gt_key(p): p["page_key"] for p in pages}
    rows = []
    for k, r in ev["per_image_results"].items():
        t = r.get("table", {})
        m = t.get("matched_tables", [])
        rows.append(
            {
                "page_key": by_key[k],
                "score": 100.0 * r["layout"]["nid_score"],
                "subscores": {
                    "nid": r["layout"]["nid_score"],
                    "teds": sum(x["teds_score"] for x in m) / len(m) if m else None,
                    "teds_s": sum(x["teds_s_score"] for x in m) / len(m) if m else None,
                    "n_gt_tables": t.get("n_gt_tables", 0),
                    "n_pred_tables": t.get("n_pred_tables", 0),
                    "n_matched_tables": t.get("n_matched_tables", 0),
                },
                "scorer_commit": REVISION,
                "warnings": WARNINGS,
            }
        )
    return rows
