"""PureDocBench native scorer: the maintainers' platform-aligned path.

1. PureDocBench `export_omnidocbench` (github.com/zhihengli-casia/PureDocBench, pinned below) writes gt.json
   and one Markdown file per page for the sampled pages.
2. OmniDocBench `pdf_validation.py` (pinned below, the evaluator in the maintainers' 2026-10-27 rescore
   record) scores them with quick_match: TextEdit, FormulaCDM, TableTEDS, ROEdit. It runs in the
   OmniDocBench repro Docker image (TeX Live 2025, ImageMagick 7, Ghostscript) with the pinned checkout
   mounted, so CDM works.

Aggregates follow the leaderboard: TextEdit = page mean of length-weighted edit distance; CDM and TEDS =
page means over pages whose GT has formulas / tables (a GT page with no matched sample counts 0);
Overall = [100 x (1 - TextEdit) + CDM + TEDS] / 3. Per-page `score` (for pair statistics) is the mean of
the components the page has, on 0-100. Failed parses are scored as empty Markdown, as the benchmark does
for missing predictions, and flagged in `warnings`.

Env: PUREDOCBENCH_ROOT (directory holding puredocbench-v1.0/), PUREDOCBENCH_SCORER_DIR,
OMNIDOCBENCH_DIR, optional OMNIDOCBENCH_IMAGE.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from ..storage import read_json

SCORER_COMMIT = "4e9d64d"  # zhihengli-casia/PureDocBench
EVALUATOR_COMMIT = "f133a71e9e91c3621c7ce8994200a7b394a06eb3"  # opendatalab/OmniDocBench
IMAGE = os.environ.get("OMNIDOCBENCH_IMAGE", "ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204")
RELEASE = "puredocbench-v1.0"
METRICS = {
    "text_block": {"metric": ["Edit_dist"]},
    "display_formula": {"metric": ["Edit_dist", "CDM"]},
    "table": {"metric": ["TEDS", "Edit_dist"]},
    "reading_order": {"metric": ["Edit_dist"]},
}


def _dir(var: str) -> Path:
    if not os.environ.get(var):
        raise SystemExit(f"puredocbench adapter: set {var}")
    return Path(os.environ[var]).expanduser().resolve()


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _check_pins() -> tuple[Path, Path]:
    scorer, omni = _dir("PUREDOCBENCH_SCORER_DIR"), _dir("OMNIDOCBENCH_DIR")
    if not _head(scorer).startswith(SCORER_COMMIT):
        raise SystemExit(f"{scorer} is not at PureDocBench {SCORER_COMMIT}")
    if _head(omni) != EVALUATOR_COMMIT:
        raise SystemExit(f"{omni} is not at OmniDocBench {EVALUATOR_COMMIT}")
    dirty = subprocess.run(
        ["git", "-C", str(omni), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty:
        raise SystemExit(f"{omni} has local edits to tracked files; the scorer must be unmodified")
    return scorer, omni


def _release() -> Path:
    return _dir("PUREDOCBENCH_ROOT") / RELEASE


def _manifest_rows(release: Path) -> dict[str, dict]:
    scorer = _dir("PUREDOCBENCH_SCORER_DIR")
    with (scorer / "manifests" / "release_manifest_candidate_1475.csv").open(encoding="utf-8") as f:
        return {r["clean_rel"]: r for r in csv.DictReader(f)}


def _clean_rel(page: dict) -> str:
    prefix = f"{RELEASE}/images/clean/"
    if not page["file"].startswith(prefix):
        raise ValueError(f"unexpected page file {page['file']}")
    return page["file"][len(prefix) :]


def gt_markdown(page: dict) -> str | None:
    """GT as Markdown in annotation order (anno_id order equals the GT reading order on every page):
    titles as headings, formulas as their $$ LaTeX, tables as their HTML, everything else as text."""
    row = _manifest_rows(_release())[_clean_rel(page)]
    gt = json.loads((_release() / "gt" / row["gt_rel"]).read_text(encoding="utf-8"))
    parts = []
    for item in sorted(gt["layout_dets"], key=lambda x: x.get("anno_id") or 0):
        cat = item.get("category_type")
        if cat == "table":
            body = item.get("html") or ""
        elif cat == "equation_isolated":
            body = item.get("latex") or ""
        else:
            body = item.get("text") or ""
            if body and cat == "title":
                body = "# " + body
        if body.strip():
            parts.append(body.strip())
    return "\n\n".join(parts) + "\n"


def export(run, cond, preset, pages, out_dir: Path) -> None:
    scorer, _ = _check_pins()
    sys.path.insert(0, str(scorer))
    from puredocbench.omnidocbench import export_omnidocbench

    rows = _manifest_rows(_release())
    if out_dir.exists():
        shutil.rmtree(out_dir)
    pred_dir = out_dir / "md"
    pred_dir.mkdir(parents=True)
    warnings = {}
    sub = []
    for p in pages:
        rel = _clean_rel(p)
        sub.append(rows[rel])
        parse = read_json(run.parse(cond, preset, p["page_key"])) or {}
        md = (parse.get("markdown") or "") if parse.get("ok") else ""
        if not parse.get("ok"):
            warnings[p["page_key"]] = ["parse failed or missing: scored as empty markdown"]
        target = pred_dir / Path(rel).with_suffix(".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(md, encoding="utf-8")
    manifest = out_dir / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(sub[0].keys()))
        w.writeheader()
        w.writerows(sub)
    info = export_omnidocbench(
        release_root=_release(),
        manifest_path=manifest,
        pred_dir=pred_dir,
        out_dir=out_dir / "omni",
        track="clean",
        strict=True,
        match_workers=8,
    )
    repairs = _repair_gt(out_dir / "omni" / "gt.json")
    for p in pages:
        for r in repairs.get(Path(_clean_rel(p)).name, []):
            warnings.setdefault(p["page_key"], []).append(f"GT repair: {r}")
    (out_dir / "export.json").write_text(
        json.dumps({**info, "warnings": warnings, "gt_repairs": repairs}, ensure_ascii=False)
    )


def _repair_gt(path: Path) -> dict:
    """GT 2026-10-07 types two table annotations as `title` with `html` and no `text`
    (utility_bill_004 and utility_bill_017). The pinned evaluator then raises KeyError('text') and exits 0
    with no results. Type them as `table`, which is what their content is. Also add an empty
    `page_attribute` where GT lacks it (else KeyError at load). Nothing else changes."""
    gt = json.loads(path.read_text(encoding="utf-8"))
    repairs = {}
    for page in gt:
        if "page_attribute" not in page["page_info"]:
            # Three quotation pages lack it; the evaluator only uses it for grouping, so {} changes no score.
            page["page_info"]["page_attribute"] = {}
            repairs.setdefault(Path(page["page_info"]["image_path"]).name, []).append(
                {"field": "page_info.page_attribute", "from": None, "to": {}}
            )
        for item in page["layout_dets"]:
            if item.get("category_type") != "table" and "text" not in item and item.get("html"):
                if item.get("category_type") in ("equation_isolated", "figure"):
                    continue
                repairs.setdefault(Path(page["page_info"]["image_path"]).name, []).append(
                    {"anno_id": item.get("anno_id"), "from": item["category_type"], "to": "table"}
                )
                item["category_type"] = "table"
    if repairs:
        path.write_text(json.dumps(gt, ensure_ascii=False), encoding="utf-8")
    return repairs


def _img_name(img_id: str) -> str:
    # Same rule as OmniDocBench get_page_split.
    return img_id if img_id.endswith((".jpg", ".png")) else "_".join(img_id.split("_")[:-1])


def score(run, cond, preset, pages, out_dir: Path) -> list[dict]:
    _, omni = _check_pins()
    work = out_dir / "omni"
    cfg = {
        "end2end_eval": {
            "metrics": METRICS,
            "dataset": {
                "dataset_name": "end2end_dataset",
                "ground_truth": {"data_path": "/job/gt.json"},
                "prediction": {"data_path": "/job/predictions"},
                "match_method": "quick_match",
                "match_workers": 8,
            },
        }
    }
    import yaml

    (work / "job.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    res = work / "result"
    shutil.rmtree(res, ignore_errors=True)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-e",
        "PYTHONPATH=/omni",
        "-v",
        f"{omni}:/omni:ro",
        "-v",
        f"{work.resolve()}:/job",
        "-w",
        "/job",
        "--entrypoint",
        "bash",
        IMAGE,
        "-lc",
        "python /omni/pdf_validation.py --config /job/job.yaml",
    ]
    log = work / "evaluator.log"
    native = os.environ.get("OMNIDOCBENCH_RUNNER") == "native"
    if native:
        cfg["end2end_eval"]["dataset"]["ground_truth"]["data_path"] = str(work / "gt.json")
        cfg["end2end_eval"]["dataset"]["prediction"]["data_path"] = str(work / "predictions")
        (work / "job.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
        cmd = [
            os.environ["PUREDOCBENCH_EVAL_PYTHON"],
            str(omni / "pdf_validation.py"),
            "--config",
            str(work / "job.yaml"),
        ]
    with log.open("w") as f:
        done = subprocess.run(cmd, cwd=work if native else None, stdout=f, stderr=subprocess.STDOUT)
    # The evaluator calls sys.exit() with status 0 on a matching exception, so check the outputs too.
    if done.returncode != 0 or not (res / "predictions_quick_match_metric_result.json").exists():
        raise RuntimeError(f"evaluator failed ({done.returncode}, no metric_result); see {log}")
    return _rows(pages, work, json.loads((out_dir / "export.json").read_text())["warnings"])


def _rows(pages, work: Path, warnings: dict) -> list[dict]:
    res = work / "result"
    name = "predictions_quick_match"

    def samples(element):
        f = res / f"{name}_{element}_result.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    edit_num, upper = defaultdict(float), defaultdict(float)
    for s in samples("text_block"):
        if "Edit_num" in s:
            edit_num[_img_name(s["img_id"])] += s["Edit_num"]
            upper[_img_name(s["img_id"])] += s["upper_len"]
    by_page = {"CDM": defaultdict(list), "TEDS": defaultdict(list), "RO": defaultdict(list)}
    for s in samples("display_formula"):
        if "CDM" in (s.get("metric") or {}):
            by_page["CDM"][_img_name(s["img_id"])].append(s["metric"]["CDM"])
    for s in samples("table"):
        if "TEDS" in (s.get("metric") or {}):
            by_page["TEDS"][_img_name(s["img_id"])].append(s["metric"]["TEDS"])
    for s in samples("reading_order"):
        if "Edit_dist" in (s.get("metric") or {}):
            by_page["RO"][_img_name(s["img_id"])].append(s["metric"]["Edit_dist"])

    gt = json.loads((work / "gt.json").read_text(encoding="utf-8"))
    has = {}
    for g in gt:
        cats = {d.get("category_type") for d in g["layout_dets"]}
        has[Path(g["page_info"]["image_path"]).name] = {
            "formula": "equation_isolated" in cats,
            "table": "table" in cats,
        }
    out = []
    for p in pages:
        img = Path(_clean_rel(p)).name
        sub = {}
        if upper[img] > 0:
            sub["text_edit"] = edit_num[img] / upper[img]
        if has[img]["formula"]:
            v = by_page["CDM"].get(img)
            sub["formula_cdm"] = 100 * sum(v) / len(v) if v else 0.0
        if has[img]["table"]:
            v = by_page["TEDS"].get(img)
            sub["table_teds"] = 100 * sum(v) / len(v) if v else 0.0
        if by_page["RO"].get(img):
            sub["reading_edit"] = sum(by_page["RO"][img]) / len(by_page["RO"][img])
        parts = [100 * (1 - sub["text_edit"])] if "text_edit" in sub else []
        parts += [sub[k] for k in ("formula_cdm", "table_teds") if k in sub]
        out.append(
            {
                "page_key": p["page_key"],
                "score": sum(parts) / len(parts) if parts else None,
                "subscores": sub,
                "scorer_commit": f"puredocbench@{SCORER_COMMIT}+omnidocbench@{EVALUATOR_COMMIT[:12]}",
                "warnings": warnings.get(p["page_key"], []),
            }
        )
    return out


def aggregate(rows: list[dict]) -> dict:
    """Leaderboard-style track numbers from per-page rows."""

    def mean(key):
        v = [r["subscores"][key] for r in rows if key in r["subscores"]]
        return (sum(v) / len(v), len(v)) if v else (None, 0)

    te, nt = mean("text_edit")
    cdm, nf = mean("formula_cdm")
    teds, ntab = mean("table_teds")
    ro, nro = mean("reading_edit")
    overall = None if None in (te, cdm, teds) else (100 * (1 - te) + cdm + teds) / 3
    return {
        "overall": overall,
        "text_edit": te,
        "formula_cdm": cdm,
        "table_teds": teds,
        "reading_edit": ro,
        "pages": {"text": nt, "formula": nf, "table": ntab, "reading_order": nro},
    }
