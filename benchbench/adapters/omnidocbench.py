"""Native scorer: OmniDocBench end2end evaluation (opendatalab/OmniDocBench), unmodified, at SCORER_COMMIT.

Used for omnidocbench and real5_omnidocbench (Real5 captures are photos of OmniDocBench originals and share
their ground truth). The scorer reads one <image stem>.md per page plus the ground-truth JSON; we pass the
ground truth restricted to the sampled pages so unsampled pages are not counted as misses.

Per-page score (0-100) = mean of the components present on the page, following the benchmark's Overall
formula ((1 - text edit distance) * 100 + table TEDS + formula CDM) / 3: text uses the scorer's per-page
length-weighted edit distance, tables and formulas the mean TEDS / CDM over that page's elements. The
scorer's own pooled Overall per preset is kept in official.json next to scores.jsonl.
"""

import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

import yaml

from ..storage import read_json, write_json

SCORER_REPO = "https://github.com/opendatalab/OmniDocBench"
SCORER_COMMIT = "0604d9843f1dfa3a292bd5f253ae83a1ba47cd24"
GT_REPO = "opendatalab/OmniDocBench"
GT_REVISION = "aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec"
DOCKER_IMAGE = "ghcr.io/zeng-weijun/omnidocbench-eval:repro-ubuntu2204"
SCORER_DIR = Path(os.environ.get("OMNIDOCBENCH_DIR", Path.home() / "work" / "OmniDocBench"))
WORKERS = int(os.environ.get("OMNIDOCBENCH_WORKERS", "4"))

_GT: dict | None = None


def _gt() -> dict:
    global _GT
    if _GT is None:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(GT_REPO, "OmniDocBench.json", repo_type="dataset", revision=GT_REVISION)
        samples = json.load(open(path, encoding="utf-8"))
        _GT = {os.path.basename(s["page_info"]["image_path"]): s for s in samples}
    return _GT


def _name(page: dict) -> str:
    return os.path.basename(page["file"])


def _check_scorer() -> None:
    head = subprocess.run(["git", "-C", str(SCORER_DIR), "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(
        ["git", "-C", str(SCORER_DIR), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
    )
    if head.stdout.strip() != SCORER_COMMIT or dirty.stdout.strip():
        raise SystemExit(f"{SCORER_DIR} must be a clean checkout of {SCORER_REPO} at {SCORER_COMMIT}")


def export(run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> None:
    pred = out_dir / "pred"
    if pred.exists():
        shutil.rmtree(pred)
    pred.mkdir(parents=True)
    gt = _gt()
    status = {}
    for p in pages:
        parse = read_json(run.parse(cond, preset, p["page_key"]))
        ok = bool(parse) and bool(parse.get("ok"))
        status[p["page_key"]] = "ok" if ok else ("failed" if parse else "missing")
        # A failed or missing parse is scored as an empty page, as the benchmark would score a model that
        # returned nothing. The report's paired comparisons drop these pages anyway.
        md = (parse.get("markdown") or "") if ok else ""
        (pred / (_name(p)[:-4] + ".md")).write_text(md, encoding="utf-8")
    gt_pages = json.dumps([gt[_name(p)] for p in pages], ensure_ascii=False)
    (out_dir / "gt.json").write_text(gt_pages, encoding="utf-8")
    write_json(out_dir / "export_status.json", status)
    cfg = {
        "end2end_eval": {
            "metrics": {
                "text_block": {"metric": ["Edit_dist"]},
                "display_formula": {"metric": ["Edit_dist", "CDM"], "cdm_workers": WORKERS},
                "table": {"metric": ["TEDS", "Edit_dist"], "teds_workers": WORKERS},
                "reading_order": {"metric": ["Edit_dist"]},
            },
            "dataset": {
                "dataset_name": "end2end_dataset",
                "ground_truth": {"data_path": "./gt.json"},
                "prediction": {"data_path": "./pred"},
                "match_method": "quick_match",
                "match_workers": WORKERS,
                "quick_match_truncated_timeout_sec": 300,
                "match_timeout_sec": 420,
                "timeout_fallback_max_chunk_span": 10,
                "timeout_fallback_order_penalty": 0.10,
            },
        }
    }
    (out_dir / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _run_scorer(out_dir: Path) -> None:
    _check_scorer()
    res = out_dir / "result"
    if res.exists():
        shutil.rmtree(res)
    runner = os.environ.get("OMNIDOCBENCH_RUNNER", "docker")
    env = {"CDM_SAVE_VIS": "0"}
    if runner == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "HOME=/tmp",
            *sum((["-e", f"{k}={v}"] for k, v in env.items()), []),
            "-v",
            f"{SCORER_DIR}:/scorer:ro",
            "-v",
            f"{out_dir.resolve()}:/work",
            "-w",
            "/work",
            "--entrypoint",
            "python",
            DOCKER_IMAGE,
            "/scorer/pdf_validation.py",
            "--config",
            "config.yaml",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
    else:
        py = str(SCORER_DIR / ".venv" / "bin" / "python")
        cmd = [py, str(SCORER_DIR / "pdf_validation.py"), "--config", "config.yaml"]
        proc = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True, env=os.environ | env)
    (out_dir / "scorer.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"OmniDocBench scorer failed in {out_dir}; see scorer.log: {proc.stderr[-500:]}")


def _page_of(img_id: str) -> str:
    if img_id.endswith((".jpg", ".png")):
        return img_id
    return "_".join(img_id.split("_")[:-1])


def _load(res: Path, element: str) -> list[dict]:
    f = res / f"pred_quick_match_{element}_result.json"
    return json.load(open(f, encoding="utf-8")) if f.exists() else []


def score(run, cond: str, preset: str, pages: list[dict], out_dir: Path) -> list[dict]:
    _run_scorer(out_dir)
    res = out_dir / "result"
    text = defaultdict(lambda: [0.0, 0])  # page -> [sum(ed * len), sum(len)], as the scorer's page split
    for s in _load(res, "text_block"):
        ed = (s.get("metric") or {}).get("Edit_dist")
        if ed is None:
            continue
        gt = s.get("norm_gt") or s.get("gt") or ""
        pr = s.get("norm_pred") or s.get("pred") or ""
        n = max(len(gt), len(pr))
        t = text[_page_of(s["img_id"])]
        t[0] += ed * n
        t[1] += n
    teds, cdm = defaultdict(list), defaultdict(list)
    for s in _load(res, "table"):
        v = (s.get("metric") or {}).get("TEDS")
        if v is not None:
            teds[_page_of(s["img_id"])].append(v)
    for s in _load(res, "display_formula"):
        v = (s.get("metric") or {}).get("CDM")
        if v is not None:
            cdm[_page_of(s["img_id"])].append(v)
    status = read_json(out_dir / "export_status.json")
    official = json.load(open(res / "pred_quick_match_metric_result.json", encoding="utf-8"))
    write_json(run.native(cond, preset).parent / "official.json", _official(official))
    rows = []
    for p in pages:
        name = _name(p)
        sub, warn = {}, []
        t = text.get(name)
        if t and t[1] > 0:
            sub["text_edit"] = t[0] / t[1]
            sub["text"] = (1 - sub["text_edit"]) * 100
        if teds.get(name):
            sub["table_teds"] = 100 * sum(teds[name]) / len(teds[name])
        if cdm.get(name):
            sub["formula_cdm"] = 100 * sum(cdm[name]) / len(cdm[name])
        parts = [sub[k] for k in ("text", "table_teds", "formula_cdm") if k in sub]
        if status.get(p["page_key"]) != "ok":
            warn.append(f"parse {status.get(p['page_key'])}: scored as empty markdown")
        if not parts:
            warn.append("no scorable text, table or formula on page")
        rows.append(
            {
                "page_key": p["page_key"],
                "score": sum(parts) / len(parts) if parts else None,
                "subscores": sub,
                "scorer_commit": SCORER_COMMIT,
                "warnings": warn,
            }
        )
    return rows


def _official(m: dict) -> dict:
    def g(el, metric, key):
        return (((m.get(el) or {}).get("all") or {}).get(metric) or {}).get(key)

    out = {
        "scorer_commit": SCORER_COMMIT,
        "raw_all": {k: (v or {}).get("all") for k, v in m.items() if isinstance(v, dict) and "all" in v},
    }
    text_ed = g("text_block", "Edit_dist", "ALL_page_avg")
    teds = g("table", "TEDS", "all")
    cdm = g("display_formula", "CDM", "all")
    out.update({"text_edit": text_ed, "table_teds": teds, "formula_cdm": cdm})
    if None not in (text_ed, teds, cdm):
        out["overall"] = ((1 - text_ed) * 100 + teds * 100 + cdm * 100) / 3
    return out


_SEP = "\n\n"


def _norm(text: str) -> str:
    text = re.sub(r"_{4,}", "____", text)
    text = re.sub(r" {4,}", "    ", text)
    text = re.sub(r"([^a-zA-Z0-9])\1{10,}", r"\1\1\1\1", text)
    return text.replace("/t", "\t").replace("/n", "\n")


def gt_markdown(page: dict) -> str | None:
    """Ground truth as markdown, following the benchmark's tools/json2md.py: annotations in reading order,
    truncated blocks merged, titles as '# ', tables as HTML, formulas as LaTeX, figures omitted. json2md drops
    blocks with order 0 (a falsy check) and we keep them, since the scorer counts them. json2md uses
    langid to decide how to join truncated English lines; we join ASCII lines with a space (or without one
    after a trailing hyphen) and others directly, which matches it for English and Chinese text."""
    s = _gt().get(_name(page))
    if s is None:
        return None
    annos = [x for x in s["layout_dets"] if x.get("order") is not None]
    groups: list[list] = []
    for r in (s.get("extra") or {}).get("relation", []):
        if r.get("relation_type") != "truncated":
            continue
        a, b = r["source_anno_id"], r["target_anno_id"]
        for g in groups:
            if a in g or b in g:
                g.extend([a, b])
                break
        else:
            groups.append([a, b])
    merged_ids = {i for g in groups for i in g}
    by_id = {x["anno_id"]: x for x in annos}
    items = [x for x in annos if x["anno_id"] not in merged_ids]
    for g in groups:
        blocks = sorted({i: by_id[i] for i in g if i in by_id}.values(), key=lambda x: x["order"])
        if not blocks:
            continue
        text = ""
        for b in blocks:
            line = b.get("text") or ""
            if line.isascii() and line:
                text = text[:-1] + line if line.endswith("-") and text else text + " " + line
            else:
                text += line
        items.append({**blocks[0], "text": text})
    out = []
    for x in sorted(items, key=lambda x: x["order"]):
        cat = x["category_type"]
        if cat == "figure":
            continue
        if cat == "table":
            out.append(x.get("html") or "")
        elif x.get("text"):
            out.append("# " + _norm(x["text"].strip("#").strip()) if cat == "title" else _norm(x["text"]))
        elif x.get("html"):
            out.append(x["html"])
        elif x.get("latex"):
            out.append(x["latex"])
    return _SEP.join(out) + _SEP if out else ""
