"""OCRFlux-bench-single native scorer: chatdoc-com/OCRFlux `eval/eval_page_to_markdown.py` at SCORER_COMMIT.

Per page EDS = 1 - nltk.edit_distance(pred, gt) / max(len(pred), len(gt)) on the raw markdown; the
benchmark's headline is the unweighted mean (reported x100 here). A missing prediction is scored as ""
(the scorer's `pred_data.get(filename, '')`), so a failed parse scores 0.

nltk.edit_distance is pure Python (about 7 s per page pair here). Scores use rapidfuzz's Levenshtein
distance, the same unit-cost distance; every clean `score` call also runs the pinned scorer's own
`evaluate` on a seeded 1% of its pages and stops if any score differs. nltk is pinned to 3.9.1: later
releases refuse inputs over 2,000 characters, which would crash the scorer on about half of these pages.

`subscores.eds_html_tables` is the documented conversion: pipe tables turned into HTML tables (the ground
truth writes every table as HTML) before scoring. The primary native score is "as returned".
"""

import importlib.util
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import cache
from pathlib import Path

from huggingface_hub import hf_hub_download
from rapidfuzz.distance import Levenshtein

from ..datasets import CACHE
from ..probes import to_html_tables
from ..seeding import derive_seed
from ..storage import read_json

SCORER_REPO = "https://github.com/chatdoc-com/OCRFlux"
SCORER_COMMIT = "c1b315aa4c8309f8dc436a5d90fc4977bcf0d865"
HF_REPO, HF_REVISION = "ChatDOC/OCRFlux-bench-single", "2ef2080038c7ce9696e34d2b59a7e81c3eb0c600"
CHECK_SHARE = 0.01


def scorer_dir() -> Path:
    root = CACHE / f"OCRFlux-{SCORER_COMMIT[:7]}"
    if not root.exists():
        subprocess.run(["git", "clone", "-q", SCORER_REPO, str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", SCORER_COMMIT], check=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.stdout.strip() != SCORER_COMMIT:
        raise RuntimeError(f"{root} is at {head.stdout.strip()}, not the pinned {SCORER_COMMIT}")
    return root


def pinned_evaluate():
    """The scorer's own `evaluate(pred, gt)` from the pinned checkout, unmodified."""
    root = scorer_dir()
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("ocrflux_eval", root / "eval" / "eval_page_to_markdown.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.evaluate


def eds(pred: str, gt: str) -> float:
    return 1.0 - Levenshtein.distance(pred, gt) / max(len(pred), len(gt))


@cache
def _gt() -> dict[str, dict]:
    path = hf_hub_download(HF_REPO, "data.jsonl", repo_type="dataset", revision=HF_REVISION)
    return {r["pdf_name"]: r for r in map(json.loads, Path(path).read_text().splitlines())}


def _name(page: dict) -> str:
    return page["file"].split("/")[-1]


def gt_markdown(page: dict) -> str | None:
    row = _gt().get(_name(page))
    return row["markdown"] if row else None


def _pred(run, cond: str, preset: str, page: dict) -> tuple[str, bool]:
    v = read_json(run.parse(cond, preset, page["page_key"]))
    ok = bool(v and v.get("ok"))
    return ((v.get("markdown") or "") if ok else ""), ok


def export(run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> None:
    """The scorer's input layout: <workspace>/results/*.jsonl rows {orig_path, document_text}, plus a
    ground-truth file restricted to the sampled pages (rows as in data.jsonl)."""
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    with (out_dir / "results" / f"{preset}.jsonl").open("w") as f:
        for p in pages:
            md, ok = _pred(run, cond, preset, p)
            if ok:
                f.write(json.dumps({"orig_path": p["file"], "document_text": md}, ensure_ascii=False) + "\n")
    with (out_dir / "gt.jsonl").open("w") as f:
        for p in pages:
            f.write(json.dumps(_gt()[_name(p)], ensure_ascii=False) + "\n")


def _check(args: tuple[str, str]) -> float:
    return pinned_evaluate()(*args)


def score(run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> list[dict]:
    rows, checks = [], []
    for p in pages:
        gt_row = _gt()[_name(p)]
        pred, ok = _pred(run, cond, preset, p)
        conv, info = to_html_tables(pred, None)
        s = eds(pred, gt_row["markdown"])
        warnings = [] if ok else ["no parse: scored as empty, as the scorer does for a missing prediction"]
        draw = derive_seed("ocrflux-check", preset, p["page_key"]) % 10_000
        if cond == "clean" and draw < CHECK_SHARE * 10_000:
            checks.append((len(rows), pred, gt_row["markdown"]))
        rows.append(
            {
                "page_key": p["page_key"],
                "score": 100 * s,
                "subscores": {
                    "eds": s,
                    "eds_html_tables": eds(conv, gt_row["markdown"]),
                    "pipe_tables_converted": info["converted"],
                    "language": gt_row["language"],
                    "parse_ok": ok,
                    "pred_chars": len(pred),
                    "gt_chars": len(gt_row["markdown"]),
                },
                "scorer_commit": SCORER_COMMIT,
                "warnings": warnings,
            }
        )
    with ProcessPoolExecutor(max_workers=8) as ex:
        ref = list(ex.map(_check, [(a, b) for _, a, b in checks]))
    for (i, _, _), r in zip(checks, ref, strict=True):
        if abs(rows[i]["subscores"]["eds"] - r) > 1e-12:
            raise RuntimeError(f"{rows[i]['page_key']}: rapidfuzz EDS {rows[i]['subscores']['eds']} != {r}")
        rows[i]["warnings"].append("checked against the pinned scorer's evaluate()")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "check.json").write_text(json.dumps({"checked": len(checks), "mismatches": 0}))
    return rows
