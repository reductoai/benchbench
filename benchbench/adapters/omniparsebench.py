"""OmniParseBench native adapter: Datalab's `unit_tests` scorer at a pinned commit, run unmodified.

The scorer lives in its own environment (its dependencies are not BenchBench's), so `score` runs
`omniparsebench_runner.py` under that environment's Python:
  OPB_SCORER_DIR   checkout of github.com/datalab-to/omni_parse_bench at SCORER_COMMIT (default ~/opb/scorer)
  OPB_PYTHON       its interpreter (default $OPB_SCORER_DIR/.venv/bin/python)

Outputs given to the scorer, per page:
  html    the parse's markdown through `omni_parse_bench.markdown.to_html`, the converter the benchmark
          applies to every markdown-returning vendor;
  blocks  the stored raw API response through the benchmark's own provider code (`layout_blocks`) where that
          vendor has an adapter there. Datalab's preset asks for markdown only, so its blocks come from one
          extra call per image with the benchmark's own Datalab request (`output_format=chunks`), stored in
          native_blocks/ by reports/omniparsebench/datalab_blocks.py. Pulse and Cohere have no box reader in
          the scorer, so their layout tests are `unsupported` and, as the benchmark does for html-only
          systems, they get no three-family headline. Each row's `warnings` says which.
Row `score` is the mean of the text and tables family rates on the page (comparable across all presets);
`subscores.three_family` adds layout where supported. The pooled headline comes from lines.jsonl.
A failed parse gets no outputs, so all its tests fail (the scorer's own rule for a failed page).
The ground truth is pass/fail tests, not a page transcript, so there is no `gt` markdown for probes:
probes run on each preset's parse (`--probe-base all`).
"""

import json
import os
import subprocess
from pathlib import Path

from ..storage import read_jsonl

SCORER_COMMIT = "74629e1597259105ed13ae62aded01ece65b3290"
HF_REPO = "datalab-to/omni_parse_bench"
HF_REVISION = "d70182b9f901d1660a27e60bf6be6d6e6ea83013"
RUNNER = Path(__file__).with_name("omniparsebench_runner.py")


def _scorer_dir() -> Path:
    return Path(os.environ.get("OPB_SCORER_DIR", Path.home() / "opb" / "scorer"))


def _python() -> str:
    return os.environ.get("OPB_PYTHON", str(_scorer_dir() / ".venv" / "bin" / "python"))


def _check_commit() -> None:
    head = subprocess.run(
        ["git", "-C", str(_scorer_dir()), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "-C", str(_scorer_dir()), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if head != SCORER_COMMIT or dirty:
        raise SystemExit(
            f"omniparsebench scorer must be {SCORER_COMMIT}, unmodified; found {head} dirty={bool(dirty)}"
        )


def _stem(page_id: str) -> str:
    return Path(page_id).stem


def gold_path(page: dict) -> Path:
    from huggingface_hub import hf_hub_download

    args = dict(repo_type="dataset", revision=HF_REVISION, token=os.environ.get("HF_TOKEN"))
    name = f"gold/{_stem(page['page_id'])}.json"
    try:
        return Path(hf_hub_download(HF_REPO, name, local_files_only=True, **args))
    except Exception:
        return Path(hf_hub_download(HF_REPO, name, **args))


def export(run, cond, preset, pages, out_dir) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        {
            "page_key": p["page_key"],
            "page_id": _stem(p["page_id"]),
            "gold": str(gold_path(p)),
            "parse": str(run.parse(cond, preset, p["page_key"]).resolve()),
            "preset": preset,
            "blocks_file": (
                str((run.root / "native_blocks" / cond / preset / f"{p['page_key']}.json").resolve())
                if preset == "datalab_accurate"
                else None
            ),
        }
        for p in pages
    ]
    (out_dir / "jobs.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))


def score(run, cond, preset, pages, out_dir) -> list[dict]:
    _check_commit()
    out_dir = Path(out_dir)
    subprocess.run(
        [_python(), str(RUNNER), str(out_dir / "jobs.jsonl"), str(out_dir)],
        check=True,
        cwd=str(_scorer_dir()),
    )
    rows = read_jsonl(out_dir / "rows.jsonl")
    for r in rows:
        r["scorer_commit"] = SCORER_COMMIT
    return rows


def gt_markdown(page) -> None:
    return None
