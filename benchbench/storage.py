"""Append-safe, content-addressed run layout.

runs/<run>/
  run.json                       study config (seed, dpi, presets, judge, conditions, pinned commits)
  pages.jsonl                    sampled pages: benchmark, page_id, source, page_index, strata, gt_ref
  images/<cond>/<page_key>.png   exact bytes sent to providers and the judge (+ .json with params, sha256)
  parses/<cond>/<preset>/<page_key>.json   provider output, raw response, latency, cost, errors
  judge/<cond>/<judge_tag>/<page_key>.json blind judge verdicts per preset
  native/<cond>/<preset>/scores.jsonl      native benchmark scores per page (written by native adapters)
An artefact is written once via a temp file + rename; reruns skip artefacts that exist and are ok.
"""

import json
import os
import re
import threading
from pathlib import Path


def page_key(benchmark: str, page_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", page_id)[:150]
    return f"{benchmark}__{safe}"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def done(path: Path) -> bool:
    obj = read_json(path)
    return bool(obj) and obj.get("ok", False)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    os.replace(tmp, path)


class Run:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()  # the TS bridge runs in bridge/, so image paths must be absolute

    @property
    def config(self) -> dict:
        return read_json(self.root / "run.json") or {}

    def pages(self) -> list[dict]:
        return read_jsonl(self.root / "pages.jsonl")

    def image(self, cond: str, key: str) -> Path:
        return self.root / "images" / cond / f"{key}.png"

    def image_meta(self, cond: str, key: str) -> Path:
        return self.root / "images" / cond / f"{key}.json"

    def parse(self, cond: str, preset: str, key: str) -> Path:
        return self.root / "parses" / cond / preset / f"{key}.json"

    def judge(self, cond: str, tag: str, key: str) -> Path:
        return self.root / "judge" / cond / tag / f"{key}.json"

    def native(self, cond: str, preset: str) -> Path:
        return self.root / "native" / cond / preset / "scores.jsonl"
