import json
import os
import sys
from pathlib import Path

from benchbench.catalog import load_catalog
from benchbench.datasets import sample_pages

wt = Path(os.environ.get("BENCHBENCH_RESULTS", Path(__file__).resolve().parents[2] / "results"))
bench = sys.argv[1]
d = wt / "samples" / bench
pj = next(p for p in d.rglob("pages.jsonl"))
rj = json.load(open(pj.parent / "run.json"))
pre = [json.loads(line) for line in open(pj)]
cat = load_catalog()
b = cat[bench]
rows = sample_pages(b, rj.get("sample_n"), rj["seed"])
a = [r["page_id"] for r in pre]
c = [r["page_id"] for r in rows]
print(
    json.dumps(
        {
            "bench": bench,
            "seed": rj["seed"],
            "n": rj.get("sample_n"),
            "prereg": len(a),
            "resampled": len(c),
            "identical_ids": a == c,
            "same_set": set(a) == set(c),
            "hf_revision": b.get("hf_revision"),
        }
    )
)
