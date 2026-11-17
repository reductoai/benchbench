"""Cohort-specific headlines, using unrounded scores and competition ranks."""

import json
import math
import os
import statistics
from fractions import Fraction
from pathlib import Path

ROOT = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[1] / "results"))


def summarize(data, size=12):
    if size != 12:
        raise ValueError("Cohort must be 12")
    benchmarks = data["benchmarks"]
    if len(benchmarks) != size or any(len(b["vendors"]) != 8 for b in benchmarks):
        raise ValueError("Incomplete benchmark/vendor cohort")
    output = {"benchmarks": [b["id"] for b in benchmarks], "parser_benchmark_pairs": size * 8}
    leads = {}
    for b in benchmarks:
        scores = sorted((v["native_clean"] for v in b["vendors"]), reverse=True)
        leads[b["id"]] = {
            "lead_pct": 100 * (scores[0] - scores[1]) / scores[0],
            "median_loss_pct": statistics.median(
                100 * (1 - v["native_tilt"] / v["native_clean"]) for v in b["vendors"]
            ),
            "lead_points": scores[0] - scores[1],
            "median_loss_points": statistics.median(
                v["native_clean"] - v["native_tilt"] for v in b["vendors"]
            ),
        }
    output["native_leads"] = leads
    output["leads_smaller_pct"] = sum(x["lead_pct"] < x["median_loss_pct"] for x in leads.values())
    output["leads_smaller_points"] = sum(x["lead_points"] < x["median_loss_points"] for x in leads.values())
    for metric in ("native", "gpt"):
        winners = {}
        for condition in ("clean", "tilt"):
            key = metric + "_" + condition
            winners[condition] = {
                b["id"]: sorted(
                    v["vendor"] for v in b["vendors"] if v[key] == max(x[key] for x in b["vendors"])
                )
                for b in benchmarks
            }
            sums = {
                v["vendor"]: sum(
                    1
                    + sum(
                        x[key] > next(y[key] for y in b["vendors"] if y["vendor"] == v["vendor"])
                        for x in b["vendors"]
                    )
                    for b in benchmarks
                )
                for v in benchmarks[0]["vendors"]
            }
            means = {v: Fraction(total, size) for v, total in sums.items()}
            output[key] = {
                "wins": {v: sum(v in w for w in winners[condition].values()) for v in sums},
                "average_ranks": {
                    v: {
                        "mean": float(mean),
                        "rank_sum": sums[v],
                        "rank": 1 + sum(other < mean for other in means.values()),
                    }
                    for v, mean in means.items()
                },
            }
        changed = [b for b in winners["clean"] if winners["clean"][b] != winners["tilt"][b]]
        drops = [
            100 * (1 - v[metric + "_tilt"] / v[metric + "_clean"]) for b in benchmarks for v in b["vendors"]
        ]
        positions = [
            v
            for v in output[metric + "_clean"]["average_ranks"]
            if output[metric + "_clean"]["average_ranks"][v]["rank"]
            != output[metric + "_tilt"]["average_ranks"][v]["rank"]
        ]
        output[metric] = {
            "winner_changes": changed,
            "median_drop_pct": statistics.median(drops),
            "provider_position_changes": positions,
        }
    return output


def repeat_check(data, runs):
    tags = [f"gpt-6.1-sol-medium-r{i}" for i in (0, 1)]
    checks = []
    for benchmark in data["benchmarks"]:
        presets = {v["preset"] for v in benchmark["vendors"]}
        repeats = []
        for tag in tags:
            pages = {}
            for path in (Path(runs) / benchmark["id"] / "judge" / "clean" / tag).glob("*.json"):
                if path.name.endswith(".raw.json"):
                    continue
                verdict = json.loads(path.read_text())
                if not verdict.get("ok"):
                    continue
                scores = {v["presetId"]: float(v["score"]) for v in verdict["verdicts"]}
                if set(scores) == presets and all(math.isfinite(v) for v in scores.values()):
                    pages[verdict["page_key"]] = scores
            repeats.append(pages)
        shared = sorted(repeats[0].keys() & repeats[1].keys())
        if not shared or not presets:
            raise ValueError(f"Incomplete repeat cohort: {benchmark['id']}")
        tops = []
        for pages in repeats:
            means = {p: math.fsum(pages[k][p] for k in shared) / len(shared) for p in presets}
            tops.append(sorted(p for p, score in means.items() if score == max(means.values())))
        checks.append(
            {
                "id": benchmark["id"],
                "pages": len(shared),
                "r0_pages": len(repeats[0]),
                "r1_pages": len(repeats[1]),
                "winners": tops,
            }
        )
    if not checks:
        raise ValueError("Incomplete repeat cohort")
    return {"tags": tags, "benchmarks": checks}


def main():
    data = json.loads((ROOT / "data.json").read_text())
    report = summarize(data)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
