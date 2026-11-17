"""Load figure inputs from saved results, comparison tables and benchmark summaries."""

import csv
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYN = Path(os.environ.get("BENCHBENCH_RESULTS", ROOT / "results"))
REAL5 = "real5_omnidocbench"
PENDING = REAL5


def git_show(ref, path):
    candidate = SYN / path
    if "/prereg/" in path or "/preregistration/" in path:
        parts = Path(path).parts
        candidate = SYN / "samples" / parts[1] / parts[-1]
    return candidate.read_text()


def git_time(ref, path):
    return json.loads((SYN / "checks/sample_commit_times.json").read_text())[Path(path).parts[1]]


@lru_cache
def results():
    rows = list(csv.DictReader(open(SYN / "results.csv")))
    for r in rows:
        r["native_clean_str"] = r["native_clean"]
        for k, v in list(r.items()):
            if k in (
                "benchmark",
                "vendor",
                "preset",
                "native_metric",
                "native_source",
                "gpt_tilt_delta_ci90",
                "native_clean_str",
            ):
                continue
            r[k] = float(v) if "." in v else int(v)
    if real5_final() and not any(r["benchmark"] == REAL5 for r in rows):
        rows += real5_rows(rows)
    return rows


@lru_cache
def real5_final():
    try:
        json.loads(git_show(f"runs/{REAL5}", f"reports/{REAL5}/summary.json"))
        return True
    except FileNotFoundError:
        return False


def pending():
    return [] if real5_final() else [REAL5]


def rank_desc(vals):
    order = sorted(vals, key=lambda k: -vals[k])
    return {k: order.index(k) + 1 for k in vals}


@lru_cache
def real5_report(name):
    return json.loads(git_show(f"runs/{REAL5}", f"reports/{REAL5}/{name}"))


def real5_rows(rows):
    """Real5 rows in results.csv's shape, built from its final report: official native overall on clean pages,
    GPT clean, and own-order Gemini on the 499 pages both judges scored (common_pages.json, report 3.1)."""
    s, cp = real5_report("summary.json"), real5_report("common_pages.json")
    off = real5_report("analysis.json")["official"]
    ps = [r["preset"] for r in rows if r["benchmark"] == rows[0]["benchmark"]]
    nat = {p: off[f"clean/{p}"]["overall"] for p in ps}
    nr, gr = rank_desc(nat), rank_desc(cp["gemini_own_mean"])
    metric = next(r["native_metric"] for r in rows if r["benchmark"] == "omnidocbench")
    out = []
    for r0 in (r for r in rows if r["benchmark"] == rows[0]["benchmark"]):
        p = r0["preset"]
        j, t = s["conditions"]["clean"]["judge"][p], s["conditions"]["tilt_2_4"]["delta_vs_clean"][p]
        out.append(
            {
                "benchmark": REAL5,
                "vendor": r0["vendor"],
                "preset": p,
                "native_metric": metric,
                "native_clean": nat[p],
                "native_clean_str": f"{nat[p]:.1f}",
                "native_rank": nr[p],
                "gpt_clean": j["mean"],
                "gpt_clean_rank": j["rank"],
                "gemini_own_clean": cp["gemini_own_mean"][p],
                "gemini_own_rank": gr[p],
                "gpt_tilt": j["mean"] + t["delta"],
                "gpt_tilt_delta": t["delta"],
                "pages_judged_clean": cp["pages"],
                "native_source": f"runs/{REAL5}:reports/{REAL5}/analysis.json",
            }
        )
    return out


def ordered(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


@lru_cache
def benchmarks():
    return ordered(r["benchmark"] for r in results())


@lru_cache
def presets():
    return ordered(r["preset"] for r in results())


@lru_cache
def vendor_names():
    return {r["preset"]: r["vendor"] for r in results()}


@lru_cache
def bench_names():
    data = json.loads((SYN / "data.json").read_text())
    return {b["id"]: b["name"] for b in data["benchmarks"]}


def row(b, p):
    return next(r for r in results() if r["benchmark"] == b and r["preset"] == p)


@lru_cache
def summary(b):
    return json.loads(git_show(f"runs/{b}", f"reports/{b}/summary.json"))


@lru_cache
def gemini_summary(b):
    return json.loads(git_show(f"runs/{b}", f"reports/{b}/gemini-own/summary.json"))


def gemini_judge(b):
    """Own-order Gemini clean judge, chosen the way checks/extract.py chooses it."""
    if b == REAL5:
        return {
            r["preset"]: {"mean": r["gemini_own_clean"], "rank": r["gemini_own_rank"], "rank_ci95": None}
            for r in results()
            if r["benchmark"] == REAL5
        }
    go = gemini_summary(b)
    if "compare" in go:
        return next(iter(go["compare"]["judges"].values()))["judge"]
    return go["conditions"]["clean"]["judge"]


def gemini_agreement(b):
    """Pair agreement of GPT vs own-order Gemini. Where the gemini-own summary has no comparison block,
    it is recomputed from the two judges' clean means and has no interval."""
    if b == REAL5:
        return real5_report("common_pages.json")["agreement"]
    go = gemini_summary(b)
    if "compare" in go:
        return next(iter(go["compare"]["judges"].values()))["agreement_with_primary"]
    g, m = summary(b)["conditions"]["clean"]["judge"], gemini_judge(b)
    pairs = [(x, y) for i, x in enumerate(presets()) for y in presets()[i + 1 :]]
    same = sum((g[x]["mean"] - g[y]["mean"]) * (m[x]["mean"] - m[y]["mean"]) > 0 for x, y in pairs)
    return {"agreement": same / len(pairs), "ci90": None, "pairs": len(pairs)}


@lru_cache
def claims():
    """Read confirmed pairs from each saved benchmark report."""
    out = {}
    for b in benchmarks():
        others = [p for p in presets() if p != "reducto_r1"]
        confirmed = {
            c["worse"]
            for c in summary(b).get("compare", {}).get("claims", [])
            if c["better"] == "reducto_r1" and c["confirmed"]
        }
        leaders = [
            {p for p in presets() if row(b, p)[key] == 1}
            for key in ("native_rank", "gpt_clean_rank", "gemini_own_rank")
        ]
        shared = set.intersection(*leaders)
        out[b] = {
            "claimed": [p for p in others if p in confirmed],
            "not_claimed": [p for p in others if p not in confirmed],
            "leader": next(iter(shared)) if len(shared) == 1 else None,
            "unordered": [],
        }
    if real5_final():
        out[REAL5] = real5_claims()
    return out


def real5_claims():
    """Read complete-coverage claims and the separate 499-page common-page comparison."""
    s = real5_report("summary.json")
    assert not any(c["confirmed"] for c in s["compare"]["claims"])
    post = [
        c.split(" > ")[1]
        for c in real5_report("common_pages.json")["confirmed"]
        if c.startswith("reducto_r1 > ")
    ]
    return {"claimed": [], "not_claimed": [], "leader": None, "unordered": [], "posthoc_over": post}


@lru_cache
def provenance():
    return json.loads((SYN / "checks" / "provenance.json").read_text())


def prereg_dir(b):
    for d in ("prereg", "preregistration"):
        try:
            git_show(f"runs/{b}", f"reports/{b}/{d}/run.json")
            return d
        except FileNotFoundError:
            continue
    raise FileNotFoundError(b)


@lru_cache
def timeline(b):
    d = prereg_dir(b)
    run = json.loads(git_show(f"runs/{b}", f"reports/{b}/{d}/run.json"))
    fc = provenance()["first_call"].get(b)
    extra = Path(__file__).parent / f"{b}_first_call.json"
    if fc is None and extra.exists():
        fc = json.loads(extra.read_text())
    rs = provenance()["resample"].get(b, {})
    return {
        "drawn": run["created"],
        "committed": git_time(f"runs/{b}", f"reports/{b}/{d}/pages.jsonl"),
        "first_call": fc["earliest_start"][0] if fc else None,
        "seed": int(run["seed"]),
        "pages": len((SYN / "samples" / b / "pages.jsonl").read_text().splitlines()),
        "resampled": rs.get("resampled"),
        "same_set": rs.get("same_set"),
        "records": fc and fc["vendor_records"],
        "records_no_finish": fc and fc["n_missing"],
    }


def seed_commit():
    value = json.loads((SYN / "checks/seed_provenance.json").read_text())
    return value["source_commit"], value["created"]


def ci(s):
    lo, hi = s.split("..")
    return float(lo), float(hi)


def check_against_report():
    """Return differences between primary CSV scores and the current snapshot."""
    data = json.loads((SYN / "data.json").read_text())
    errors = []
    for b in data["benchmarks"]:
        for v in b["vendors"]:
            saved = row(b["id"], v["preset"])
            for key in ("gpt_clean", "gpt_tilt"):
                if abs(saved[key] - v[key]) > 1e-9:
                    errors.append((b["id"], v["preset"], key, saved[key], v[key]))
    return errors


if __name__ == "__main__":
    print(bench_names())
    for b, c in claims().items():
        print(b, {k: [vendor_names()[p] for p in v] if isinstance(v, list) else v for k, v in c.items()})
    print(seed_commit())
    errs = check_against_report()
    print("mismatches:", errs or "none")
