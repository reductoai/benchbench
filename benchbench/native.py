"""Stage 1: the benchmark's own scorer.

A native adapter lives in benchbench/adapters/<benchmark_id>.py and defines:
  export(run, cond, preset, pages, out_dir) -> None   write predictions in the layout the scorer expects
  score(run, cond, preset, pages, out_dir) -> list[dict]  run the pinned scorer; one row per page:
      {"page_key", "score" (0-100), "subscores": {...}, "scorer_commit", "warnings": [...]}
  gt_markdown(page) -> str | None   needed for probes; probes are applied to ground truth by default
Rules: pin the scorer commit; do not edit scorer code; if the scorer needs a format the parse lacks,
record the conversion in `warnings`. Probe scores go under preset "probe-<name>-<base>" (base "gt").
"""

import importlib

from .probes import PROBES, apply_probe
from .storage import Run, read_json, write_json, write_jsonl


def adapter(benchmark: str):
    try:
        return importlib.import_module(f"benchbench.adapters.{benchmark}")
    except ModuleNotFoundError as e:
        raise SystemExit(f"no native adapter for {benchmark}; add benchbench/adapters/{benchmark}.py") from e


def make_probe_parses(run: Run, cond: str, base: str, probes: list[str]) -> list[str]:
    """Write probe parses next to real ones so native scoring and judging treat them alike.

    base="gt" (default) applies each probe to the benchmark's own ground truth, so the probe result does not
    depend on any vendor's output style. Preset "gt" is the ground truth itself (the scorer's ceiling).
    Any other base applies the probe to that preset's parse; run it for every preset and report the median.
    """
    names = []
    if base == "gt":
        names.append("gt")
        for p in run.pages():
            out = run.parse(cond, "gt", p["page_key"])
            if not out.exists():
                gt = adapter(p["benchmark"]).gt_markdown(p)
                write_json(out, {"ok": gt is not None, "markdown": gt or "", "probe": {"probe": "gt"}})
    for name in probes:
        if name not in PROBES:
            raise SystemExit(f"unknown probe {name}")
        preset = f"probe-{name}-{base}"
        names.append(preset)
        for p in run.pages():
            out = run.parse(cond, preset, p["page_key"])
            if out.exists():
                continue
            src = read_json(run.parse(cond, base, p["page_key"]))
            if not src or not src.get("ok"):
                continue
            md, info = apply_probe(name, src["markdown"], (run.config["seed"], p["page_key"], cond))
            info["changed"] = md != src["markdown"]
            write_json(out, {"ok": True, "markdown": md, "probe": info, "base_preset": base})
    return names


def score(run: Run, benchmark: str, cond: str, presets: list[str]) -> None:
    mod = adapter(benchmark)
    pages = [p for p in run.pages() if p["benchmark"] == benchmark]
    for preset in presets:
        out_dir = run.root / "native_work" / cond / preset / benchmark
        mod.export(run, cond, preset, pages, out_dir)
        rows = mod.score(run, cond, preset, pages, out_dir)
        existing = {r["page_key"]: r for r in _rows(run, cond, preset)}
        existing.update({r["page_key"]: r for r in rows})
        write_jsonl(run.native(cond, preset), sorted(existing.values(), key=lambda r: r["page_key"]))


def _rows(run: Run, cond: str, preset: str) -> list[dict]:
    from .storage import read_jsonl

    return read_jsonl(run.native(cond, preset))
