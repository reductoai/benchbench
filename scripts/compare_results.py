"""Aggregate a local clean/tilt run using the final study's scoring rules."""

import argparse
import csv
import json
import os
import statistics
from pathlib import Path

import numpy as np

from benchbench import report, stats
from benchbench.storage import Run, read_jsonl

ROOT = Path(os.environ.get("BENCHBENCH_RUNS", Path(__file__).resolve().parents[1] / "results/runs"))
PRESETS = [
    "reducto_r1",
    "llamaparse_agentic_plus",
    "datalab_accurate",
    "extend_performance_agentic_formulas",
    "mistral_ocr_4_1",
    "azure_layout_high_res_formulas",
    "pulse_ultra_2",
    "cohere_parse_v5",
]
DATALAB = "datalab_accurate"


def native_score(bench, cond):
    run = Run(ROOT / bench)
    rows = read_jsonl(run.native(cond, DATALAB))
    assert rows, f"{bench}/{cond}: no native rows"
    work = run.root / "native_work" / cond / DATALAB / bench
    if bench == "olmocr_bench":
        totals = {}
        for row in rows:
            for _, suite, _, passed, _ in row["subscores"]["results"]:
                a = totals.setdefault(suite, [0, 0])
                a[0] += int(passed)
                a[1] += 1
        return statistics.mean(100 * a / n for a, n in totals.values())
    if bench == "omniparsebench":
        totals = {}
        for line in read_jsonl(work / "lines.jsonl"):
            family = {"present": "text", "order": "text", "repeat": "text", "table_cell": "tables"}.get(
                line["test_type"]
            )
            if family is None:
                continue
            a = totals.setdefault(family, [0, 0])
            a[0] += line["result"] == "pass"
            a[1] += 1
        assert totals, "OmniParseBench: no text/table tests"
        return statistics.mean(100 * a / n for a, n in totals.values())
    if bench == "parsebench2":
        return json.loads((work / "official.json").read_text())["overall_no_layout"]
    if bench in ("omnidocbench", "real5_omnidocbench"):
        return json.loads((run.native(cond, DATALAB).parent / "official.json").read_text())["overall"]
    if bench == "puredocbench":

        def mean(key):
            return statistics.mean(r["subscores"][key] for r in rows if key in r["subscores"])

        return (100 * (1 - mean("text_edit")) + mean("formula_cdm") + mean("table_teds")) / 3
    return statistics.mean(r["score"] for r in rows if r.get("score") is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for benchmark in args.benchmarks:
        run = Run(ROOT / benchmark)
        keys = [p["page_key"] for p in run.pages()]
        matrices = {}
        for condition, repeats in (("clean", (0, 1)), ("tilt_2_4", (0,))):
            matrix = report._mean_repeats(
                [
                    report.judge_matrix(run, condition, f"gpt-6.1-sol-medium-r{r}", PRESETS, keys)[0]
                    for r in repeats
                ]
            )
            matrix[report.parse_failed(run, condition, PRESETS, keys).any(1)] = np.nan
            matrices[condition] = matrix
        for condition, matrix in matrices.items():
            mask = (
                report._complete(matrix, matrices["clean"])
                if condition != "clean"
                else report._complete(matrix)
            )
            if not mask.any():
                raise ValueError(f"{benchmark}/{condition}: no complete pages")
            means = matrix[mask].mean(0)
            ranks = stats.ranks(means)
            for i, preset in enumerate(PRESETS):
                rows.append(
                    dict(
                        benchmark=benchmark,
                        condition=condition,
                        preset=preset,
                        pair=float(means[i]),
                        rank=int(ranks[i]),
                        pages=int(mask.sum()),
                        native=native_score(benchmark, condition) if preset == DATALAB else "",
                    )
                )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"COMPARISON COMPLETE: {len(args.benchmarks)} benchmarks; {len(rows)} rows")


if __name__ == "__main__":
    main()
