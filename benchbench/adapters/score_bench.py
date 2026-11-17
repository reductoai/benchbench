"""SCORE-Bench native adapter (Unstructured, unstructured-eval-metrics at SCORER_COMMIT).

Headline: CCT (clean concatenated text fidelity) x 100, computed by the pinned scorer, unmodified.

The scorer reads plain text, Unstructured plain text, or Unstructured element JSON; parsers return markdown.
Documented conversion (`md_to_elements`): split markdown into blocks; HTML and pipe tables become Table
elements whose text is the cell text in reading order and whose metadata.text_as_html is the table
(pipe tables go through probes.pipe_table_to_html); headings become Title, list items ListItem, the rest
NarrativeText; markdown syntax (#, *, _, `, links, image tags, HTML tags, comments) is removed from text.
The conversion only removes syntax; it never adds words. `cct_as_returned` scores the raw markdown string
as plain text so the effect of the conversion is visible.

Subscores: cct_as_returned, cct_adjusted, tokens_found, tokens_added, and on pages with table ground truth
tables_overall / tables_detection_f / tables_content_acc (scorer's html-vs-text table metric).
Pages where the parse failed are scored as an empty output and flagged with warning "parse_failed".
"""

import html as _html
import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from ..probes import TABLE_HTML, _cells, pipe_table_to_html
from ..storage import read_json

HF_REPO = "unstructuredio/SCORE-Bench"
HF_REVISION = "15dc068f6f9adcfbfd84dbddfdf2a2c9c11bf0c0"
SCORER_REPO = "https://github.com/Unstructured-IO/unstructured-eval-metrics"
SCORER_COMMIT = "b148439dd428bb10d7f2bb80c7386ea08cbd7447"
UEM_DIR = Path(os.environ.get("SCORE_UEM_DIR", Path.home() / "uem"))
WORKERS = int(os.environ.get("SCORE_NATIVE_WORKERS", "32"))

_PIPE_BLOCK = re.compile(r"^\s*\|.*\|\s*$")


@lru_cache(maxsize=1)
def _gt_dir() -> Path:
    from huggingface_hub import snapshot_download
    from huggingface_hub.utils import disable_progress_bars

    disable_progress_bars()

    return Path(
        snapshot_download(
            HF_REPO, repo_type="dataset", revision=HF_REVISION, allow_patterns=["content-gt/*", "table-gt/*"]
        )
    )


def _src_name(page: dict) -> str:
    return Path(page["file"]).name


def gt_paths(page: dict) -> tuple[Path, Path]:
    g, name = _gt_dir(), _src_name(page)
    return (
        g / "content-gt" / f"{name}__uns-plaintext-v1.0.0__0x0001__0.txt",
        g / "table-gt" / f"{name}__uns-table-json-v1.0.0__0x0002__0.json",
    )


def _strip_inline(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"(\*\*|__|~~|`+)", "", text)
    text = re.sub(r"(?<![\w*])[*_](?=\S)(.+?)(?<=\S)[*_](?![\w*])", r"\1", text)
    return _html.unescape(text).strip()


def _table_element(table_html: str) -> dict:
    rows = [_cells(r) for r in re.findall(r"<tr\b.*?</tr>", table_html, re.S | re.I)]
    text = "\n".join(" ".join(c for c, _, _ in r) for r in rows if r)
    return {"type": "Table", "text": text, "metadata": {"text_as_html": table_html}}


def md_to_elements(md: str) -> list[dict]:
    out: list[dict] = []
    parts = re.split(r"(<table\b.*?</table>)", md, flags=re.S | re.I)
    for part in parts:
        if TABLE_HTML.fullmatch(part or ""):
            out.append(_table_element(part))
            continue
        lines = (part or "").splitlines()
        i = 0
        para: list[str] = []

        def flush(para=para):
            t = _strip_inline("\n".join(para))
            if t:
                out.append({"type": "NarrativeText", "text": t})
            para.clear()

        while i < len(lines):
            ln = lines[i]
            if _PIPE_BLOCK.match(ln):
                flush()
                block = []
                while i < len(lines) and _PIPE_BLOCK.match(lines[i]):
                    block.append(lines[i])
                    i += 1
                out.append(_table_element(pipe_table_to_html("\n".join(block))))
                continue
            if not ln.strip() or re.match(r"^\s*(```|~~~|-{3,}\s*$|\*{3,}\s*$)", ln):
                flush()
            elif m := re.match(r"^\s{0,3}#{1,6}\s+(.*)$", ln):
                flush()
                t = _strip_inline(m.group(1).rstrip("#"))
                if t:
                    out.append({"type": "Title", "text": t})
            elif m := re.match(r"^\s*(?:[-*+•]|\d+[.)])\s+(.*)$", ln):
                flush()
                t = _strip_inline(m.group(1))
                if t:
                    out.append({"type": "ListItem", "text": t})
            else:
                para.append(re.sub(r"^\s*>\s?", "", ln))
            i += 1
        flush()
    return out


def _gt_table_html(cells: list[dict]) -> str:
    rows: dict[int, list[dict]] = {}
    for c in cells:
        rows.setdefault(c["y"], []).append(c)
    parts = ["<table>"]
    for y in sorted(rows):
        tds = []
        for c in sorted(rows[y], key=lambda c: c["x"]):
            attrs = (f' colspan="{c["w"]}"' if c["w"] > 1 else "") + (
                f' rowspan="{c["h"]}"' if c["h"] > 1 else ""
            )
            tds.append(f"<td{attrs}>{_html.escape(c['content'] or '')}</td>")
        parts.append("<tr>" + "".join(tds) + "</tr>")
    return "".join(parts + ["</table>"])


_TAG = re.compile(r"^-+ Unstructured (.*) (Begin|End)$")


def _gt_blocks(text: str) -> list[tuple[str, str]]:
    """(type, text) runs from Unstructured plain text; text belongs to the innermost open element."""
    blocks, stack, buf = [], [], []

    def flush():
        t = "\n".join(buf).strip()
        if t:
            blocks.append((stack[-1] if stack else "Text", t))
        buf.clear()

    for ln in text.splitlines():
        if "Unstructured Plain Text Format" in ln:
            continue
        m = _TAG.match(ln.strip().lstrip("\ufeff"))
        if m:
            flush()
            if m.group(2) == "Begin":
                stack.append(m.group(1))
            elif stack:
                stack.pop()
        else:
            buf.append(ln.lstrip("\ufeff"))
    flush()
    return blocks


def gt_markdown(page: dict) -> str | None:
    """Ground truth as markdown: Title -> '# ', Table -> HTML from table-gt cells when their order matches the
    annotated text, else the annotated text verbatim."""
    content, tables = gt_paths(page)
    if not content.exists():
        return None
    gt_tables = [t["text"] for t in json.loads(tables.read_text())] if tables.exists() else []
    out, seen_table = [], 0
    for typ, t in _gt_blocks(content.read_text(encoding="utf-8-sig")):
        if typ == "Title":
            out.append("# " + " ".join(t.split()))
        elif typ == "Table" and seen_table < len(gt_tables):
            # Use the cell JSON as an HTML table only when its row-major text equals the annotated reading
            # order; otherwise keep the annotated text so the gt ceiling is not lowered by our rendering.
            table = gt_tables[seen_table]
            seen_table += 1
            cells = sorted(table, key=lambda c: (c["y"], c["x"]))
            same = " ".join(c["content"] or "" for c in cells).split() == t.split()
            out.append(_gt_table_html(table) if same else t)
        else:
            out.append(t)
    return "\n\n".join(out) + "\n"


def export(run, cond, preset, pages, out_dir: Path) -> None:
    (out_dir / "conv").mkdir(parents=True, exist_ok=True)
    (out_dir / "asis").mkdir(parents=True, exist_ok=True)
    manifest = []
    for p in pages:
        d = read_json(run.parse(cond, preset, p["page_key"]))
        ok = bool(d and d.get("ok"))
        md = d.get("markdown", "") if ok else ""
        name = _src_name(p)
        conv, asis = out_dir / "conv" / f"{name}.json", out_dir / "asis" / f"{name}.txt"
        conv.write_text(json.dumps(md_to_elements(md), ensure_ascii=False))
        asis.write_text(md)
        content, tables = gt_paths(p)
        manifest.append(
            {
                "page_key": p["page_key"],
                "ok": ok,
                "conv": str(conv),
                "asis": str(asis),
                "gt": str(content),
                "gt_table": str(tables) if tables.exists() else None,
            }
        )
    (out_dir / "manifest.json").write_text(json.dumps(manifest))


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    py = UEM_DIR / ".venv" / "bin" / "python"
    head = subprocess.run(
        ["git", "-C", str(UEM_DIR), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != SCORER_COMMIT:
        raise SystemExit(f"scorer at {UEM_DIR} is {head}, expected {SCORER_COMMIT}")
    helper = Path(__file__).with_name("_score_bench_runner.py")
    res = subprocess.run(
        [str(py), str(helper), str(out_dir / "manifest.json"), str(WORKERS)],
        env={**os.environ, "PYTHONPATH": str(UEM_DIR / "src")},
        capture_output=True,
        text=True,
    )
    if res.returncode:
        sys.stderr.write(res.stderr[-4000:])
        raise SystemExit(f"score_bench scorer failed for {cond}/{preset}")
    rows = []
    for r in json.loads((out_dir / "scores.json").read_text()):
        warn = ["markdown converted to Unstructured elements (adapters/score_bench.py md_to_elements)"]
        if not r.pop("ok"):
            warn.append("parse_failed: scored as empty output")
        if r.get("error"):
            warn.append("scorer_error: " + r.pop("error"))
        rows.append(
            {
                "page_key": r.pop("page_key"),
                "score": r.pop("score"),
                "subscores": r,
                "scorer_commit": SCORER_COMMIT,
                "warnings": warn,
            }
        )
    return rows
