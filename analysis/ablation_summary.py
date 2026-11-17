"""Matched-page ablations against Sol clean r0+r1 and tilt r0. No API calls."""

import argparse
import csv
import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = {
    "argon": "gemini-4-argon-medium-r0-own*",
    "astra": "gpt-6-astra-medium-r0-own",
    "fable": "claude-fable-5-2-medium-r0-own*",
    "terse": "terse-gpt-6.1-sol-medium-r0",
    "minimal": "minimal-gpt-6.1-sol-medium-r0",
}
PRIMARY = "gpt-6.1-sol-medium-r0"
CONDITIONS = ("clean", "tilt_2_4")


def load_pages(base, pattern, presets):
    directories = sorted(p for p in base.glob(pattern) if p.is_dir())
    if len(directories) > 1:
        raise ValueError(f"Ambiguous judge tag: {base}/{pattern}: {directories}")
    good, failed, invalid = {}, {}, {}
    paths = sorted(directories[0].glob("*.json")) if directories else []
    if directories:
        for manifest in sorted(directories[0].glob("final-retry/*/manifest.json")):
            records = json.loads(manifest.read_text())["retried_pages"]
            paths.extend(manifest.parent / Path(row["verdict_key"]).name for row in records)
    for path in paths:
        if path.name.endswith(".raw.json"):
            continue
        for collection in (good, failed, invalid):
            collection.pop(path.stem, None)
        try:
            value = json.loads(path.read_text())
            if value.get("ok") is False:
                failed[path.stem] = str(value.get("error", "ok:false"))
                continue
            if value.get("ok") is not True:
                raise ValueError("missing or non-boolean ok")
            verdicts = value["verdicts"]
            scores = {v["presetId"]: float(v["score"]) for v in verdicts}
            if len(scores) != len(verdicts) or not set(presets).issubset(scores):
                raise ValueError("duplicate or incomplete presets")
            if not all(math.isfinite(scores[p]) for p in presets):
                raise ValueError("nonfinite score")
            good[path.stem] = {p: scores[p] for p in presets}
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            invalid[path.stem] = str(error)
    return good, failed, invalid


def primary_pages(r0, r1, presets, condition):
    if condition != "clean":
        return r0
    return {k: {p: (r0[k][p] + r1[k][p]) / 2 for p in presets} for k in r0.keys() & r1.keys()}


def mean_scores(pages, keys, presets):
    return {p: math.fsum(pages[k][p] for k in keys) / len(keys) for p in presets}


def winners(scores):
    return sorted(p for p, score in scores.items() if score == max(scores.values()))


def ranks(values):
    return [
        1 + sum(v > value for v in values) + (sum(v == value for v in values) - 1) / 2 for value in values
    ]


def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    ma, mb = math.fsum(ra) / len(ra), math.fsum(rb) / len(rb)
    va = math.fsum((v - ma) ** 2 for v in ra)
    vb = math.fsum((v - mb) ** 2 for v in rb)
    return (
        math.fsum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True)) / math.sqrt(va * vb)
        if va and vb
        else None
    )


def analyze(runs, data, judges):
    cells, scores, failures, issues = [], [], [], []
    for bench in data["benchmarks"]:
        presets = [v["preset"] for v in bench["vendors"]]
        names = {v["preset"]: v["vendor"] for v in bench["vendors"]}
        for condition in CONDITIONS:
            base = runs / bench["id"] / "judge" / condition
            r0, _, invalid0 = load_pages(base, PRIMARY, presets)
            r1, _, invalid1 = (
                load_pages(base, "gpt-6.1-sol-medium-r1", presets) if condition == "clean" else ({}, {}, {})
            )
            reference = primary_pages(r0, r1, presets, condition)
            for source, invalid in [("sol_r0", invalid0), ("sol_r1", invalid1)]:
                issues.extend(
                    {
                        "judge": source,
                        "benchmark": bench["id"],
                        "condition": condition,
                        "page": page,
                        "error": error,
                    }
                    for page, error in invalid.items()
                )
            for judge in judges:
                candidate, failed, invalid = load_pages(base, TAGS[judge], presets)
                keys = sorted(candidate.keys() & reference.keys())
                missing = r0.keys() - candidate.keys() - failed.keys() - invalid.keys()
                processed = (candidate.keys() | failed.keys()) & r0.keys()
                finished = bool(r0) and len(processed) == len(r0) and len(reference) == len(r0)
                status = (
                    ("complete_with_failures" if failed.keys() & r0.keys() else "complete")
                    if finished
                    else "PARTIAL"
                )
                row = {
                    "judge": judge,
                    "condition": condition,
                    "benchmark": bench["id"],
                    "benchmark_name": bench["name"],
                    "status": status,
                    "sol_r0_pages": len(r0),
                    "sol_pages": len(reference),
                    "judge_complete_pages": len(candidate.keys() & r0.keys()),
                    "matched_pages": len(keys),
                    "coverage_pct": 100 * len(keys) / len(reference) if reference else None,
                    "failed_pages": len(failed.keys() & r0.keys()),
                    "missing_pages": len(missing),
                    "invalid_pages": len(invalid.keys() & r0.keys()),
                    "winner": "",
                    "sol_winner": "",
                    "same_winner": None,
                    "reducto_first": None,
                    "reducto_rank": None,
                    "spearman": None,
                }
                if keys:
                    jm, sm = (
                        mean_scores(candidate, keys, presets),
                        mean_scores(reference, keys, presets),
                    )
                    jt, st = winners(jm), winners(sm)
                    row.update(
                        winner=" + ".join(names[p] for p in jt),
                        sol_winner=" + ".join(names[p] for p in st),
                        same_winner=int(jt == st),
                        reducto_first=int("reducto_r1" in jt),
                        reducto_rank=1 + sum(v > jm["reducto_r1"] for v in jm.values()),
                        spearman=spearman([jm[p] for p in presets], [sm[p] for p in presets]),
                    )
                    scores.extend(
                        {
                            "judge": judge,
                            "condition": condition,
                            "benchmark": bench["id"],
                            "preset": p,
                            "vendor": names[p],
                            "matched_pages": len(keys),
                            "mean_pair_score": jm[p],
                            "sol_mean_pair_score": sm[p],
                        }
                        for p in presets
                    )
                cells.append(row)
                failures.extend(
                    {
                        "judge": judge,
                        "condition": condition,
                        "benchmark": bench["id"],
                        "page": page,
                        "in_sol_r0": int(page in r0),
                        "error": error,
                    }
                    for page, error in sorted(failed.items())
                )
                issues.extend(
                    {
                        "judge": judge,
                        "condition": condition,
                        "benchmark": bench["id"],
                        "page": page,
                        "error": error,
                    }
                    for page, error in sorted(invalid.items())
                )
    return cells, scores, failures, issues


def markdown(cells, judges, total, timestamp):
    lines = [
        f"# Refreshed ablations — snapshot {timestamp}",
        "",
        "Sol clean: per-page r0+r1 average on complete repeat intersections; tilt: r0. "
        "Both sides use exactly the same matched pages. Ties count as first; "
        "same-winner requires identical winner sets. Reducto rank uses competition ranks; "
        "Spearman uses average tie ranks.",
        "",
    ]
    if any(r["status"] == "PARTIAL" for r in cells):
        lines += [
            f"**PARTIAL rows are provisional. x/{total} counts observed benchmarks only, "
            "not missing benchmarks as losses. Even an evaluated benchmark may have partial page coverage.**",
            "",
        ]
    lines += [
        "| Judge | Condition | Status | Evaluated | Fully covered | Same winner | "
        "Reducto first | Matched/Sol pages | ok:false | Non-Reducto winners |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for judge in judges:
        for condition in CONDITIONS:
            rows = [r for r in cells if r["judge"] == judge and r["condition"] == condition]
            evaluated = [r for r in rows if r["matched_pages"]]
            status = (
                "PARTIAL"
                if any(r["status"] == "PARTIAL" for r in rows)
                else ("complete_with_failures" if any(r["failed_pages"] for r in rows) else "complete")
            )
            nonred = "; ".join(
                f"{r['benchmark_name']}: {r['winner']}"
                + (" [failed pages excluded]" if r["failed_pages"] else "")
                for r in evaluated
                if not r["reducto_first"]
            ) or ("None observed" if status == "PARTIAL" else "None")
            values = [
                judge,
                condition,
                status,
                f"{len(evaluated)}/{total}",
                f"{sum(r['matched_pages'] == r['sol_pages'] and r['sol_pages'] > 0 for r in rows)}/{total}",
                f"{sum(r['same_winner'] for r in evaluated)}/{total}",
                f"{sum(r['reducto_first'] for r in evaluated)}/{total}",
                f"{sum(r['matched_pages'] for r in rows)}/{sum(r['sol_pages'] for r in rows)}",
                str(sum(r["failed_pages"] for r in rows)),
                nonred,
            ]
            lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs", type=Path, default=Path(os.environ.get("BENCHBENCH_RUNS", ROOT / "results/runs"))
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("BENCHBENCH_RESULTS", ROOT / "results")) / "data.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.environ.get("BENCHBENCH_RESULTS", ROOT / "results")) / "ablation-summary",
    )
    parser.add_argument("--judges", nargs="+", choices=list(TAGS), default=list(TAGS))
    args = parser.parse_args()
    data = json.loads(args.data.read_text())
    timestamp = datetime.now(UTC).isoformat()
    cells, scores, failures, issues = analyze(args.runs, data, args.judges)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "summary.csv", cells, [])
    write_csv(
        args.out / "scores.csv",
        scores,
        [
            "judge",
            "condition",
            "benchmark",
            "preset",
            "vendor",
            "matched_pages",
            "mean_pair_score",
            "sol_mean_pair_score",
        ],
    )
    write_csv(
        args.out / "failed-pages.csv",
        failures,
        ["judge", "condition", "benchmark", "page", "in_sol_r0", "error"],
    )
    write_csv(
        args.out / "read-issues.csv",
        issues,
        ["judge", "condition", "benchmark", "page", "error"],
    )
    report = markdown(cells, args.judges, len(data["benchmarks"]), timestamp)
    (args.out / "summary.md").write_text(report)
    (args.out / "metadata.json").write_text(
        json.dumps(
            {
                "snapshot_started_utc": timestamp,
                "runs": str(args.runs),
                "data": str(args.data),
                "judges": args.judges,
                "reference": "clean complete r0/r1 intersection averaged per page; tilt r0",
                "live_snapshot": any(r["status"] == "PARTIAL" for r in cells),
            },
            indent=2,
        )
        + "\n"
    )
    print(report)
    print(
        f"Wrote {len(cells)} cells, {len(scores)} preset means, "
        f"{len(failures)} ok:false pages, {len(issues)} read issues to {args.out}"
    )


if __name__ == "__main__":
    main()
