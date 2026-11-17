"""List, sample and fetch benchmark pages from their pinned Hugging Face revisions."""

import json
import os
import re
import tarfile
import zipfile
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download

from .catalog import match_files, stratum
from .seeding import derive_seed

CACHE = Path(os.environ.get("BENCHBENCH_CACHE", Path.home() / ".cache" / "benchbench"))


def _api() -> HfApi:
    return HfApi(token=os.environ.get("HF_TOKEN"))


def _extract_parquet(bench: dict) -> Path:
    """Write each parquet row's image to <source name>/<row>.<ext> and its other columns to <row>.json."""
    import hashlib
    import io
    import json

    import pyarrow.parquet as pq
    from PIL import Image

    spec = bench["page_files"]
    key = hashlib.sha256(json.dumps(spec["parquet"], sort_keys=True).encode()).hexdigest()[:16]
    out = CACHE / "extracted" / bench["id"] / key
    marker = out / ".done"
    if marker.exists():
        return out
    col = spec.get("image_column", "image")
    for src in spec["parquet"]:
        local = hf_hub_download(src["hf_repo"], src["file"], repo_type="dataset", revision=src["hf_revision"])
        d = out / src["name"]
        d.mkdir(parents=True, exist_ok=True)
        for i, row in enumerate(pq.read_table(local).to_pylist()):
            img = row.pop(col)
            data = img["bytes"] if isinstance(img, dict) else img
            ext = {"PNG": "png", "JPEG": "jpg"}[Image.open(io.BytesIO(data)).format]
            (d / f"{i}.{ext}").write_bytes(data)
            (d / f"{i}.json").write_text(json.dumps(row, ensure_ascii=False, default=str))
    marker.touch()
    return out


def parquet_row(bench: dict, file: str) -> dict:
    """Non-image columns of the parquet row a page came from."""
    import json

    return json.loads((_extract_parquet(bench) / re.sub(r"\.\w+$", ".json", file)).read_text())


def _extract(bench: dict) -> Path:
    """Download and unpack an archive once per revision; return the unpack directory."""
    if "parquet" in bench["page_files"]:
        return _extract_parquet(bench)
    pattern = bench["page_files"]["archive"]
    files = _api().list_repo_files(bench["hf_repo"], repo_type="dataset", revision=bench["hf_revision"])
    archives = match_files(files, pattern)
    if not archives:
        raise FileNotFoundError(f"{bench['id']}: no archive matches {pattern}")
    out = CACHE / "extracted" / bench["id"] / bench["hf_revision"]
    marker = out / ".done"
    if not marker.exists():
        out.mkdir(parents=True, exist_ok=True)
        for name in archives:
            local = hf_hub_download(
                bench["hf_repo"], name, repo_type="dataset", revision=bench["hf_revision"]
            )
            if name.endswith(".zip"):
                with zipfile.ZipFile(local) as z:
                    z.extractall(out)
            else:
                with tarfile.open(local) as t:
                    t.extractall(out, filter="data")
        marker.touch()
    return out


def list_pages(bench: dict) -> list[str]:
    spec = bench.get("page_files") or {}
    if not (bench.get("hf_repo") or spec.get("parquet")) or "TODO" in str(spec.get("glob", "TODO")):
        raise NotImplementedError(
            f"{bench['id']}: page source is not verified yet; fill page_files in catalog.yaml"
        )
    if "local_env" in spec:
        root = local_root(bench)
        files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    elif "archive" in spec or "parquet" in spec:
        root = _extract(bench)
        files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    else:
        files = _api().list_repo_files(bench["hf_repo"], repo_type="dataset", revision=bench["hf_revision"])
    files = match_files(files, spec["glob"])
    if "only_list" in spec:
        keep = {
            ln.strip()
            for ln in (Path(__file__).parent / spec["only_list"]).read_text().splitlines()
            if ln.strip() and not ln.startswith("#")
        }
        files = [f for f in files if f in keep]
    return files


def local_root(bench: dict) -> Path:
    """Benchmarks whose pages ship only as split archive parts (e.g. PureDocBench): the release is
    reconstructed and checked against its published SHA-256 once (RUNBOOK), and an env var names the root."""
    var = bench["page_files"]["local_env"]
    if not os.environ.get(var):
        raise SystemExit(f"{bench['id']}: set {var} to the reconstructed release (see catalog notes)")
    root = Path(os.environ[var]).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"{bench['id']}: {var}={root} is not a directory")
    return root


def _stem(f: str) -> str:
    return re.sub(r"\.(jpe?g|png|pdf)$", "", f.split("/")[-1], flags=re.I)


def pair_captures(files: list[str], pair_files: list[str], folder_rx: str) -> dict[str, dict]:
    """Real5-style benchmarks: join each capture to the original page of the paired benchmark by file stem.
    Returns stem -> {"original": file, "captures": {condition: file}}; unmatched stems are dropped."""
    originals: dict[str, str] = {}
    for f in pair_files:
        if _stem(f) in originals:
            raise RuntimeError(f"duplicate original stem {_stem(f)}: {originals[_stem(f)]}, {f}")
        originals[_stem(f)] = f
    out: dict[str, dict] = {}
    for f in files:
        m = re.match(folder_rx, f)
        if not m or _stem(f) not in originals:
            continue
        cond = "real_" + m.group(1).lower().replace("-", "_")
        caps = out.setdefault(_stem(f), {"original": originals[_stem(f)], "captures": {}})["captures"]
        if cond in caps:
            raise RuntimeError(f"duplicate {cond} capture for {_stem(f)}")
        caps[cond] = f
    return out


def sample_pages(bench: dict, n: int | None, seed: int) -> list[dict]:
    """Stratified, seeded sample. Allocation is proportional per stratum, at least one page each.

    A benchmark with `pair_with` is sampled by original page: `clean` is the paired benchmark's page and
    every capture of it becomes a condition, so all captures of a sampled page come together."""
    if bench.get("pair_with"):
        return _sample_paired(bench, n, seed)
    files = list_pages(bench)
    return _stratified(bench, files, n, seed)


def _sample_paired(bench: dict, n: int | None, seed: int) -> list[dict]:
    from .catalog import load_catalog

    spec = bench["pair_with"]
    other = load_catalog()[spec["benchmark"]]
    pairs = pair_captures(list_pages(bench), list_pages(other), spec["folder"])
    expected = spec.get("captures_per_page")
    if expected and any(len(v["captures"]) != expected for v in pairs.values()):
        raise RuntimeError(f"{bench['id']}: some pages lack {expected} captures")
    rows = _stratified({**other, "id": bench["id"]}, sorted(v["original"] for v in pairs.values()), n, seed)
    by_original = {v["original"]: v for v in pairs.values()}
    for r in rows:
        r["captures"] = {
            c: {"file": f, "hf_repo": bench["hf_repo"], "hf_revision": bench["hf_revision"], "archive": False}
            for c, f in sorted(by_original[r["file"]]["captures"].items())
        }
        r["paired_benchmark"] = other["id"]
    return rows


def _strata_map(bench: dict) -> dict[str, str] | None:
    """Strata from a ground-truth file when the path does not hold them: `strata_map: {file, key, field}`
    maps a row's `key` (a file basename) to its `field` (for example OCRFlux's `language`)."""
    spec = (bench.get("page_files") or {}).get("strata_map")
    if not spec:
        return None
    local = hf_hub_download(
        bench["hf_repo"], spec["file"], repo_type="dataset", revision=bench["hf_revision"]
    )
    rows = [json.loads(ln) for ln in Path(local).read_text().splitlines() if ln.strip()]
    return {r[spec["key"]]: str(r[spec["field"]]) for r in rows}


def _csv_strata(bench: dict) -> dict[str, str]:
    """Stratum per file stem from a CSV shipped with the benchmark (page_files.strata_csv)."""
    import csv

    spec = bench["page_files"]["strata_csv"]
    with open(_extract(bench) / spec["file"], newline="") as f:
        return {_stem(r[spec["key"]]): r[spec["value"]] for r in csv.DictReader(f)}


def _stratified(bench: dict, files: list[str], n: int | None, seed: int) -> list[dict]:
    regex = (bench.get("page_files") or {}).get("strata")
    by_name = _strata_map(bench)
    by_csv = _csv_strata(bench) if "strata_csv" in (bench.get("page_files") or {}) else None
    by_stratum: dict[str, list[str]] = {}
    for f in files:
        if by_name is not None:
            s = by_name.get(f.split("/")[-1], "other")
        elif by_csv is not None:
            s = by_csv.get(_stem(f), "other")
        else:
            s = stratum(f, regex)
        by_stratum.setdefault(s, []).append(f)
    for group in by_stratum.values():
        group.sort(key=lambda f: derive_seed(seed, bench["id"], f))
    total = len(files)
    if n is None or n >= total:
        chosen = {s: g for s, g in by_stratum.items()}
    else:
        quota = {s: max(1, round(n * len(g) / total)) for s, g in by_stratum.items()}
        while sum(quota.values()) > n:
            biggest = max(quota, key=lambda s: quota[s])
            quota[biggest] -= 1
        while sum(quota.values()) < n:
            room = [s for s in quota if quota[s] < len(by_stratum[s])]
            quota[max(room, key=lambda s: len(by_stratum[s]) - quota[s])] += 1
        chosen = {s: g[: quota[s]] for s, g in by_stratum.items()}
    spec = bench.get("page_files") or {}
    sources = {src["name"]: src for src in spec.get("parquet", [])}
    local = spec.get("local_env")
    rows = []
    for s, group in sorted(chosen.items()):
        for f in group:
            src = sources.get(f.split("/")[0], {})
            rows.append(
                {
                    "benchmark": bench["id"],
                    "page_id": f,
                    "file": f,
                    "page_index": 0,
                    "stratum": s,
                    "hf_repo": src.get("hf_repo", bench.get("hf_repo")),
                    "hf_revision": src.get("hf_revision", bench.get("hf_revision")),
                    "archive": "archive" in spec or "parquet" in spec,
                    **({"local_env": local} if local else {}),
                }
            )
    return sorted(rows, key=lambda r: r["page_id"])


def fetch(page: dict, bench: dict) -> Path:
    if page.get("archive"):
        return _extract(bench) / page["file"]
    if page.get("local_env"):
        return local_root(bench) / page["file"]
    if page.get("local_path"):
        return Path(page["local_path"])
    return Path(
        hf_hub_download(page["hf_repo"], page["file"], repo_type="dataset", revision=page["hf_revision"])
    )
