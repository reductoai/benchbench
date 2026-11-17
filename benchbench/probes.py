"""Benchmark sanity probes (after Datalab's five checks). Each probe rewrites a parse so that a fair scorer
should score it the same (format-only probes) or clearly lower (error probes). Run the native scorer on probe
outputs: a big drop on a format-only probe means the benchmark is grading format, not reading.
"""

import html
import random
import re

from .seeding import rng

TABLE_HTML = re.compile(r"<table\b.*?</table>", re.S | re.I)
PIPE_TABLE = re.compile(r"(?:^\|.*\|[ \t]*(?:\n|\Z))+", re.M)


def _cells(row_html: str) -> list[tuple[str, int, int]]:
    out = []
    for m in re.finditer(r"<t([hd])\b([^>]*)>(.*?)</t[hd]>", row_html, re.S | re.I):
        attrs = m.group(2)
        cs = int((re.search(r'colspan="?(\d+)', attrs) or [0, 1])[1])
        rs = int((re.search(r'rowspan="?(\d+)', attrs) or [0, 1])[1])
        text = re.sub(r"<[^>]+>", " ", m.group(3))
        out.append((" ".join(html.unescape(text).split()), cs, rs))
    return out


def html_table_to_pipe(table: str) -> str | None:
    """Simple HTML table -> GitHub pipe table. None if cells are merged (pipe tables cannot hold them)."""
    rows = [_cells(r) for r in re.findall(r"<tr\b.*?</tr>", table, re.S | re.I)]
    rows = [r for r in rows if r]
    if not rows or any(cs > 1 or rs > 1 for r in rows for _, cs, rs in r):
        return None
    width = max(len(r) for r in rows)
    lines = []
    for i, r in enumerate(rows):
        vals = [c.replace("|", "\\|") for c, _, _ in r] + [""] * (width - len(r))
        lines.append("| " + " | ".join(vals) + " |")
        if i == 0:
            lines.append("|" + "---|" * width)
    return "\n".join(lines) + "\n"


INLINE_TAG = re.compile(r"(</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>)")


def _cell_html(text: str) -> str:
    """Escapes text but keeps inline tags a parser put in the cell (`<i>`, `<br>`), so the probe changes
    only the table format, never the cell content."""
    return "".join(
        t if INLINE_TAG.fullmatch(t) else html.escape(t, quote=False) for t in INLINE_TAG.split(text)
    )


def pipe_table_to_html(block: str) -> str:
    rows = [ln.strip().strip("|").split("|") for ln in block.strip().splitlines()]
    rows = [r for r in rows if not all(re.fullmatch(r"\s*:?-{2,}:?\s*", c) for c in r)]
    parts = ["<table>"]
    for i, r in enumerate(rows):
        tag = "th" if i == 0 else "td"
        parts.append("<tr>" + "".join(f"<{tag}>{_cell_html(c.strip())}</{tag}>" for c in r) + "</tr>")
    parts.append("</table>")
    return "".join(parts) + "\n"


def to_pipe_tables(md: str, r: random.Random) -> tuple[str, dict]:
    converted, kept = 0, 0

    def sub(m):
        nonlocal converted, kept
        pipe = html_table_to_pipe(m.group(0))
        if pipe is None:
            kept += 1
            return m.group(0)
        converted += 1
        return pipe

    return TABLE_HTML.sub(sub, md), {"converted": converted, "kept_merged": kept}


def to_html_tables(md: str, r: random.Random) -> tuple[str, dict]:
    n = len(PIPE_TABLE.findall(md))
    return PIPE_TABLE.sub(lambda m: pipe_table_to_html(m.group(0)), md), {"converted": n}


def pretty_html(md: str, r: random.Random) -> tuple[str, dict]:
    def sub(m):
        t = re.sub(r">\s*<", ">\n<", m.group(0))
        t = re.sub(r"\n<(t[dh])", r"\n    <\1", t)
        return re.sub(r"\n<tr", "\n  <tr", t)

    return TABLE_HTML.sub(sub, md), {}


def code_fence(md: str, r: random.Random) -> tuple[str, dict]:
    return f"```markdown\n{md}\n```\n", {}


def strip_emphasis(md: str, r: random.Random) -> tuple[str, dict]:
    md = re.sub(r"(\*\*|__)(.+?)\1", r"\2", md)
    md = re.sub(r"(?<![\w*])\*(?![\s*])([^*\n]+?)(?<![\s*])\*(?![\w*])", r"\1", md)
    md = re.sub(r"(?<![\w_])_(?![\s_])([^_\n]+?)(?<![\s_])_(?![\w_])", r"\1", md)
    return md, {}


def digits_5pct(md: str, r: random.Random) -> tuple[str, dict]:
    """Error probe: change 5% of digits. Every fair scorer must drop."""
    chars = list(md)
    in_tag = set()
    for m in re.finditer(r"<[^<>]*>", md):  # leave colspan="2" etc. alone: change content, not structure
        in_tag.update(range(m.start(), m.end()))
    idx = [i for i, c in enumerate(chars) if c.isdigit() and i not in in_tag]
    picked = r.sample(idx, k=max(1, round(len(idx) * 0.05))) if idx else []
    for i in picked:
        chars[i] = r.choice([d for d in "0123456789" if d != chars[i]])
    return "".join(chars), {"digits": len(idx), "changed": len(picked)}


def shuffle_paragraphs(md: str, r: random.Random) -> tuple[str, dict]:
    """Error probe: same text, wrong reading order."""
    paras = [p for p in re.split(r"\n\s*\n", md) if p.strip()]
    r.shuffle(paras)
    return "\n\n".join(paras) + "\n", {"paragraphs": len(paras)}


def empty(md: str, r: random.Random) -> tuple[str, dict]:
    """Error probe: missing page. The scorer must score it zero or report it, never skip it."""
    return "", {}


PROBES = {
    "pipe_tables": (to_pipe_tables, "format"),
    "html_tables": (to_html_tables, "format"),
    "pretty_html": (pretty_html, "format"),
    "code_fence": (code_fence, "format"),
    "strip_emphasis": (strip_emphasis, "format"),
    "digits_5pct": (digits_5pct, "error"),
    "shuffle_paragraphs": (shuffle_paragraphs, "error"),
    "empty": (empty, "error"),
}


def apply_probe(name: str, md: str, seed_parts: tuple) -> tuple[str, dict]:
    fn, kind = PROBES[name]
    out, info = fn(md, rng(*seed_parts, name))
    return out, {"probe": name, "kind": kind, **info}
