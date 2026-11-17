import csv
import json
import os
from pathlib import Path

W = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[2] / "results"))
B = [
    "dp_bench",
    "score_bench",
    "olmocr_bench",
    "omniparsebench",
    "ocrflux_bench",
    "idp_leaderboard",
    "mdpbench",
    "rd_tablebench",
    "puredocbench",
    "omnidocbench",
    "parsebench2",
]
REPO = W
old = (
    {(r["benchmark"], r["preset"]): r for r in csv.DictReader(open(W / "checks/harness_extract.csv"))}
    if (W / "checks/harness_extract.csv").exists()
    else {}
)
rows = []
for b in B:
    d = next((x for x in (REPO / "reports" / b, W / "reports" / b) if (x / "summary.json").exists()), None)
    if d is None:  # report not checked out here: keep the rows extracted earlier
        rows += [r for k, r in old.items() if k[0] == b]
        continue
    g = json.load(open(d / "summary.json"))
    go = json.load(open(d / "gemini-own" / "summary.json"))
    if "compare" in go:
        gj = next(iter(go["compare"]["judges"].values()))
    else:
        gj = {
            "tag": go["judge"],
            "pages": go["conditions"]["clean"]["pages"],
            "judge": go["conditions"]["clean"]["judge"],
        }
    for p in g["presets"]:
        r = {
            "benchmark": b,
            "preset": p,
            "pages_clean": g["conditions"]["clean"]["pages"],
            "gpt_tag": g["judge"],
            "gemini_tag": gj.get("tag"),
            "gemini_pages": gj.get("pages"),
        }
        for c in ("clean", "tilt_2_4", "scan", "perspective"):
            cj = g["conditions"].get(c, {}).get("judge", {}).get(p)
            if cj:
                r[f"gpt_{c}"] = round(cj["mean"], 3)
                r[f"gpt_{c}_rank"] = cj["rank"]
            dl = g["conditions"].get(c, {}).get("delta_vs_clean", {}) if c != "clean" else {}
            if isinstance(dl, dict) and p in dl:
                x = dl[p]
                r[f"gpt_{c}_delta"] = round(x.get("mean", x.get("delta")), 3) if isinstance(x, dict) else x
                if isinstance(x, dict) and "ci90" in x:
                    r[f"gpt_{c}_delta_ci90"] = "{:.2f}..{:.2f}".format(*tuple(x["ci90"]))
        gm = gj["judge"].get(p)
        r["gemini_own_clean"] = round(gm["mean"], 3) if gm else None
        r["gemini_own_rank"] = gm["rank"] if gm else None
        r["native_harness"] = (
            g["native"].get(p, {}).get("clean")
            if isinstance(g["native"].get(p), dict)
            else g["native"].get(p)
        )
        rows.append(r)
    print(b, g["conditions"]["clean"]["pages"], gj.get("tag"), gj.get("pages"))
keys = sorted({k for r in rows for k in r}, key=lambda k: (k not in ("benchmark", "preset"), k))
w = csv.DictWriter(open(W / "checks/harness_extract.csv", "w"), fieldnames=keys)
w.writeheader()
w.writerows(rows)
