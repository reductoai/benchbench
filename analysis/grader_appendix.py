"""Build refreshed judge comparisons and paired 90% bootstrap intervals. No API calls."""

import json
import os
from pathlib import Path

import numpy as np
from ablation_summary import (
    CONDITIONS,
    PRIMARY,
    TAGS,
    analyze,
    load_pages,
    markdown,
    primary_pages,
    write_csv,
)
from headlines import repeat_check

ROOT = Path(__file__).resolve().parents[1]


def bootstrap(clean, tilt=None, draws=2000, seed=0):
    clean = np.asarray(clean, dtype=float)
    if clean.ndim != 2 or not len(clean) or not np.isfinite(clean).all():
        raise ValueError("Expected a nonempty finite page-by-preset matrix")
    if tilt is not None:
        tilt = np.asarray(tilt, dtype=float)
        if tilt.shape != clean.shape or not np.isfinite(tilt).all() or (clean <= 0).any():
            raise ValueError("Paired matrices must have equal shapes and positive clean scores")
    rng = np.random.default_rng(seed)
    samples = []
    for start in range(0, draws, 100):
        indices = rng.integers(0, len(clean), (min(100, draws - start), len(clean)))
        means = clean[indices].mean(axis=1)
        samples.append(100 * (tilt[indices].mean(axis=1) / means - 1) if tilt is not None else means)
    values = np.concatenate(samples)
    return np.quantile(values, [0.05, 0.95], axis=0), values


def matrix(pages, keys, presets):
    return np.array([[pages[k][p] for p in presets] for k in keys])


def aggregate(cells):
    rows = []
    for judge in TAGS:
        for condition in CONDITIONS:
            selected = [r for r in cells if r["judge"] == judge and r["condition"] == condition]
            rows.append(
                {
                    "judge": judge,
                    "condition": condition,
                    "benchmarks": len(selected),
                    "same_winner": sum(r["same_winner"] for r in selected),
                    "reducto_first": sum(r["reducto_first"] for r in selected),
                    "matched_pages": sum(r["matched_pages"] for r in selected),
                    "sol_pages": sum(r["sol_pages"] for r in selected),
                    "failed_pages": sum(r["failed_pages"] for r in selected),
                    "non_reducto_winners": "; ".join(
                        f"{r['benchmark_name']}: {r['winner']}" for r in selected if not r["reducto_first"]
                    ),
                }
            )
    return rows


def build(runs, data):
    cells, scores, failures, issues = analyze(runs, data, list(TAGS))
    if issues or any(r["status"] == "PARTIAL" or not r["matched_pages"] for r in cells):
        raise ValueError("All judge cells must be finalized, valid and nonempty")
    indexed_cells = {(r["judge"], r["benchmark"], r["condition"]): r for r in cells}
    indexed_scores = {(r["judge"], r["benchmark"], r["condition"], r["preset"]): r for r in scores}
    drops = []
    for bench in data["benchmarks"]:
        bid = bench["id"]
        presets = [v["preset"] for v in bench["vendors"]]
        groups, references = {}, {}
        for condition in CONDITIONS:
            base = runs / bid / "judge" / condition
            r0, _, _ = load_pages(base, PRIMARY, presets)
            r1, _, _ = (
                load_pages(base, "gpt-6.1-sol-medium-r1", presets) if condition == "clean" else ({}, {}, {})
            )
            references[condition] = primary_pages(r0, r1, presets, condition)
            for judge, tag in TAGS.items():
                pages, _, _ = load_pages(base, tag, presets)
                groups[judge, condition] = pages
                keys = sorted(pages.keys() & references[condition].keys())
                values = matrix(pages, keys, presets)
                intervals, samples = bootstrap(values)
                cell = indexed_cells[judge, bid, condition]
                red = presets.index("reducto_r1")
                cell["p_reducto_top"] = float((samples[:, red] >= samples.max(axis=1)).mean())
                for index, preset in enumerate(presets):
                    indexed_scores[judge, bid, condition, preset].update(
                        lo_score=float(intervals[0, index]),
                        hi_score=float(intervals[1, index]),
                    )
        for judge in ["sol", *TAGS]:
            clean = references["clean"] if judge == "sol" else groups[judge, "clean"]
            tilt = references["tilt_2_4"] if judge == "sol" else groups[judge, "tilt_2_4"]
            keys = sorted(
                clean.keys() & tilt.keys() & references["clean"].keys() & references["tilt_2_4"].keys()
            )
            if not keys:
                raise ValueError(f"No paired clean/tilt pages: {judge}/{bid}")
            c, t = matrix(clean, keys, presets), matrix(tilt, keys, presets)
            intervals, _ = bootstrap(c, t)
            point = 100 * (t.mean(axis=0) / c.mean(axis=0) - 1)
            for index, preset in enumerate(presets):
                drops.append(
                    {
                        "judge": judge,
                        "benchmark": bid,
                        "preset": preset,
                        "pages": len(keys),
                        "drop_pct": float(point[index]),
                        "lo_pct": float(intervals[0, index]),
                        "hi_pct": float(intervals[1, index]),
                    }
                )
    return cells, scores, failures, drops


def main():
    results = Path(os.environ.get("BENCHBENCH_RESULTS", ROOT / "results"))
    runs = Path(os.environ.get("BENCHBENCH_RUNS", results / "runs"))
    data = json.loads((results / "data.json").read_text())
    cells, scores, failures, drops = build(runs, data)
    checks = repeat_check(data, runs)
    summary = aggregate(cells)
    out = results / "appendix"
    out.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (
        ("cells", cells, []),
        ("scores", scores, []),
        ("drops", drops, []),
        ("summary", summary, []),
        ("failed-pages", failures, ["judge", "condition", "benchmark", "page", "in_sol_r0", "error"]),
    ):
        write_csv(out / f"{name}.csv", rows, fields)
    (out / "repeat-check.json").write_text(json.dumps(checks, indent=2) + "\n")
    report = markdown(cells, list(TAGS), len(data["benchmarks"]), data["refresh"]["run"])
    report += (
        "\nScore and relative-change intervals are 90% percentile intervals from 2,000 page "
        "bootstrap resamples (seed 0). Clean/tilt changes resample matched page pairs together "
        "and use `100 * (tilt / clean - 1)`; negative values indicate a loss. "
        "`p_reducto_top` is the fraction of score bootstrap samples in which Reducto is tied for first.\n"
    )
    (out / "README.md").write_text(report)
    primary_intervals = [
        {
            "benchmark": r["benchmark"],
            "preset": r["preset"],
            "metric": "gpt" if r["judge"] == "sol" else "min",
            **{k: r[k] for k in ("pages", "drop_pct", "lo_pct", "hi_pct")},
        }
        for r in drops
        if r["judge"] in ("sol", "minimal")
    ]
    write_csv(results / "drop_ci.csv", primary_intervals, [])
    minimal = [
        {
            "benchmark": r["benchmark"],
            "preset": r["preset"],
            "field": "min_clean" if r["condition"] == "clean" else "min_tilt",
            "score": r["mean_pair_score"],
            "pages": r["matched_pages"],
        }
        for r in scores
        if r["judge"] == "minimal"
    ]
    write_csv(results / "pair_minimal.csv", minimal, [])
    data["refresh"].update(
        historical="Gemini 3.1, scan and perspective predate this refresh.",
        judge_ablations=summary,
        repeat_check=checks,
        confidence_intervals={
            "level": 0.90,
            "draws": 2000,
            "seed": 0,
            "method": "Paired page bootstrap; percentile intervals; relative change = 100*(tilt/clean-1).",
            "reference": "Sol clean per-page r0+r1 average; tilt r0.",
            "scope": "Primary PAIR and five refreshed judge variants; matched complete pages.",
        },
    )
    lookup = {(r["benchmark"], r["preset"], r["field"]): r["score"] for r in minimal}
    for bench in data["benchmarks"]:
        for vendor in bench["vendors"]:
            for field in ("min_clean", "min_tilt"):
                vendor[field] = lookup[bench["id"], vendor["preset"], field]
    (results / "data.json").write_text(json.dumps(data, indent=1) + "\n")
    print(
        f"Refreshed {len(cells)} cells, {len(scores)} score intervals, {len(drops)} paired-change intervals"
    )
    print(
        f"Repeat checks: {len(checks['benchmarks'])} benchmarks; "
        f"{sum(b['pages'] for b in checks['benchmarks'])} matched pages"
    )


if __name__ == "__main__":
    main()
