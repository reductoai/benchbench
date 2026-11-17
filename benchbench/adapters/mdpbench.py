"""MDPBench (HUST + Kingsoft) native scorer adapter.

Scorer: `Yuliang-Liu/MultimodalOCR` at the pinned commit, `MDPBench/pdf_validation.py` with the repo's own
`configs/end2end.yaml` settings (text Edit_dist, display formula Edit_dist + CDM, table TEDS + Edit_dist,
reading order Edit_dist, `quick_match`), run unmodified as a subprocess on a ground-truth file cut to the
sampled pages. The per-page numbers then come from the repo's `tools/calculate_scores.py` loaders and its
`compute_present_tasks_overall` (the published page score): mean over the element types present on the page
of (1 - text edit distance), formula CDM, and table TEDS, clipped to [0, 1]. `score` is that page score x 100.
Pages with no text, formula or table in the ground truth have no page score upstream; they get no row.

Input: every preset's markdown is written unchanged to `<image stem>.md`, as the benchmark's own model
scripts do. The scorer does its own cleanup (images, fences, HTML/pipe/LaTeX tables, `$$` math).
Failed parses get no file (the scorer prints "No prediction" and leaves the page out) and no row.

Setup: a checkout of the scorer at SCORER_COMMIT (env MDPBENCH_SCORER_DIR, default under the benchbench
cache) and a Python with `MDPBench/requirements.txt` (env MDPBENCH_PYTHON). CDM also needs `xelatex`
with xeCJK and the "Source Han Sans SC" font, ImageMagick with PDF read allowed and a `magick` command,
and node. CDM scores a formula 0 when its render fails, so `gt` probe CDM near 1 is the check.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from ..storage import read_json

REPO = "Delores-Lin/MDPBench"
REVISION = "252df132fe1b418dbd5830515ef4b5a06fa7164f"
SCORER_REPO = "https://github.com/Yuliang-Liu/MultimodalOCR"
SCORER_COMMIT = "6ddb0a570419ce7ccb6913cf1c5ed84930320e7e"
CACHE = Path(os.environ.get("BENCHBENCH_CACHE", Path.home() / ".cache" / "benchbench")) / "mdpbench"
WARNINGS = [
    "markdown passed unchanged to the MDPBench end2end scorer (quick_match); page score = present-task mean"
]

TEXT_CATS = {
    "text_block",
    "title",
    "code_txt",
    "code_txt_caption",
    "reference",
    "equation_caption",
    "figure_caption",
    "figure_footnote",
    "table_caption",
    "table_footnote",
    "code_algorithm",
    "code_algorithm_caption",
    "header",
    "footer",
    "page_footnote",
    "page_number",
}

PER_PAGE = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from tools.calculate_scores import (load_text_scores_and_counts, load_formula_scores_and_counts,
    load_table_scores_and_counts, compute_present_tasks_overall)
import pandas as pd
folder = Path(sys.argv[2]); prefix = folder.name
text_s, n_text = load_text_scores_and_counts(result_folder=folder, ocr_prefix=prefix, split_tag="All")
formula_s, n_formula = load_formula_scores_and_counts(result_folder=folder, ocr_prefix=prefix, split_tag="All")
table_s, n_table = load_table_scores_and_counts(result_folder=folder, ocr_prefix=prefix, split_tag="All", metric="TEDS")
frames = [f for f in (text_s, n_text.to_frame(), formula_s, n_formula.to_frame(), table_s, n_table.to_frame()) if len(f)]
pages = pd.concat(frames, axis=1) if frames else pd.DataFrame()
out = {}
if len(pages):
    pages = compute_present_tasks_overall(pages, empty_policy="nan")
    for k, r in pages.iterrows():
        out[k] = {c: (None if pd.isna(r[c]) else float(r[c])) for c in pages.columns}
order = {}
p = folder / f"{prefix}_reading_order_result.json"
if p.exists():
    for it in json.loads(p.read_text()):
        order[it["img_id"]] = it.get("edit")
json.dump({"pages": out, "reading_order_edit": order}, open(sys.argv[3], "w"))
"""  # noqa: E501


def scorer_dir() -> Path:
    d = Path(os.environ.get("MDPBENCH_SCORER_DIR", CACHE / f"MultimodalOCR-{SCORER_COMMIT[:12]}"))
    if not (d / "MDPBench" / "pdf_validation.py").exists():
        subprocess.run(["git", "clone", SCORER_REPO, str(d)], check=True)
        subprocess.run(["git", "-C", str(d), "checkout", SCORER_COMMIT], check=True)
    head = subprocess.run(
        ["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != SCORER_COMMIT:
        raise RuntimeError(f"MDPBench scorer at {d} is {head}, want {SCORER_COMMIT}")
    return d / "MDPBench"


def python() -> str:
    return os.environ.get("MDPBENCH_PYTHON", sys.executable)


_GT: dict | None = None


def ground_truth() -> dict:
    global _GT
    if _GT is None:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(REPO, "MDPBench_public.json", repo_type="dataset", revision=REVISION)
        _GT = {s["page_info"]["image_path"]: s for s in json.loads(Path(path).read_text())}
    return _GT


def _gt_key(page: dict) -> str:
    return Path(page["file"]).name


def _stem(page: dict) -> str:
    return Path(_gt_key(page)).stem


def is_digital(stem: str) -> bool:
    # The scorer's own rule (dataset/end2end_dataset.py): a digital original has exactly three name parts.
    return len([p for p in stem.split("_") if p]) == 3


def gt_markdown(page: dict) -> str | None:
    s = ground_truth().get(_gt_key(page))
    if s is None:
        return None
    by_id = {d["anno_id"]: d for d in s["layout_dets"]}
    # Truncated blocks are one paragraph split across boxes; the scorer joins them, so the GT text does too.
    nxt, joined = {}, set()
    for r in s.get("extra", {}).get("relation", []):
        if r["relation_type"] == "truncated":
            nxt[r["source_anno_id"]] = r["target_anno_id"]
            joined.add(r["target_anno_id"])
    parts = []
    for d in sorted(s["layout_dets"], key=lambda d: d.get("order") if d.get("order") is not None else 10**9):
        cat = d["category_type"]
        if d["anno_id"] in joined:
            continue
        if cat == "table" and d.get("html"):
            parts.append(d["html"].strip())
        elif cat == "equation_isolated" and d.get("latex"):
            t = d["latex"].strip()
            parts.append(t if t.startswith("$$") else f"$$\n{t}\n$$")
        elif cat in TEXT_CATS:
            text, cur, seen = d.get("text") or "", d["anno_id"], {d["anno_id"]}
            while cur in nxt and nxt[cur] in by_id and nxt[cur] not in seen:
                cur = nxt[cur]
                seen.add(cur)
                text += by_id[cur].get("text") or ""
            if text.strip():
                parts.append(("# " if cat == "title" else "") + text.strip())
    return "\n\n".join(parts) + "\n"


def export(run, cond, preset, pages, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    gt = ground_truth()
    (out_dir / "gt.json").write_text(json.dumps([gt[_gt_key(p)] for p in pages], ensure_ascii=False))
    pred = out_dir / "pred"
    if pred.exists():
        for f in pred.iterdir():
            f.unlink()
    pred.mkdir(exist_ok=True)
    missing = []
    for p in pages:
        d = read_json(run.parse(cond, preset, p["page_key"]))
        if not d or not d.get("ok"):
            missing.append(p["page_key"])
            continue
        (pred / f"{_stem(p)}.md").write_text(d.get("markdown") or "", encoding="utf-8")
    (out_dir / "missing.json").write_text(json.dumps(missing))
    cfg = json.loads((Path(__file__).with_name("mdpbench_end2end.json")).read_text())
    cfg["end2end_eval"]["dataset"]["ground_truth"]["data_path"] = str(out_dir / "gt.json")
    cfg["end2end_eval"]["dataset"]["prediction"]["data_path"] = str(pred)
    (out_dir / "end2end.json").write_text(json.dumps(cfg, indent=1))


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    if not any((out_dir / "pred").iterdir()):
        return []
    sd = scorer_dir()
    proc = subprocess.run(
        [python(), str(sd / "pdf_validation.py"), "--config", str(out_dir / "end2end.json")],
        cwd=out_dir,
        capture_output=True,
        text=True,
    )
    (out_dir / "scorer.log").write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f"mdpbench scorer failed for {cond}/{preset}: {proc.stderr[-2000:]}")
    folder = out_dir / "result" / "pred_result"
    official = subprocess.run(
        [python(), str(sd / "tools" / "calculate_scores.py"), "--result_folder", str(folder)],
        cwd=sd,
        capture_output=True,
        text=True,
    )
    (out_dir / "official.txt").write_text(official.stdout + official.stderr)
    per_page = out_dir / "per_page.json"
    proc = subprocess.run(
        [python(), "-c", PER_PAGE, str(sd), str(folder), str(per_page)], capture_output=True, text=True
    )
    if proc.returncode:
        raise RuntimeError(f"mdpbench per-page extraction failed for {cond}/{preset}: {proc.stderr[-2000:]}")
    res = json.loads(per_page.read_text())
    # The scorer's per-page tables strip every image extension ("x.JPG.JPG" -> "x"); match both forms.
    by_stem = {}
    for p in pages:
        by_stem[_stem(p)] = p["page_key"]
        by_stem[re.sub(r"(\.(jpe?g|png))+$", "", _gt_key(p), flags=re.I)] = p["page_key"]
    rows = []
    for stem, r in res["pages"].items():
        if stem not in by_stem or r.get("overall_i_scheme2") is None:
            continue
        rows.append(
            {
                "page_key": by_stem[stem],
                "score": 100.0 * r["overall_i_scheme2"],
                "subscores": {
                    "text": r.get("s_text"),
                    "formula_cdm": r.get("s_formula"),
                    "table_teds": r.get("s_table"),
                    "n_text": r.get("n_text"),
                    "n_formula": r.get("n_formula"),
                    "n_table": r.get("n_table"),
                    "reading_order_edit": res["reading_order_edit"].get(stem),
                    "digital": is_digital(stem),
                },
                "scorer_commit": SCORER_COMMIT,
                "warnings": WARNINGS,
            }
        )
    return rows
