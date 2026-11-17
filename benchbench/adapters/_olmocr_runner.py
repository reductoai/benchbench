"""Run olmOCR-bench unit tests (pinned olmocr checkout, unmodified) on exported markdown.

Invoked by adapters/olmocr_bench.py with an interpreter that has `olmocr[bench]` installed:
  python _olmocr_runner.py TESTS_JSONL MD_DIR OUT_JSON
TESTS_JSONL rows are the benchmark's own test dicts plus "_suite" (source JSONL stem). MD_DIR holds
<pdf without .pdf>_pg<page>_repeat1.md files. Writes one result per test.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from olmocr.bench.tests import load_single_test


def main(tests_path: str, md_dir: str, out_path: str) -> None:
    rows = [json.loads(line) for line in open(tests_path) if line.strip()]
    tests = []
    for r in rows:
        suite = r.pop("_suite")
        tests.append((suite, load_single_test(r)))

    def run(item):
        suite, t = item
        md_path = os.path.join(md_dir, f"{os.path.splitext(t.pdf)[0]}_pg{t.page}_repeat1.md")
        if not os.path.exists(md_path):
            return {"id": t.id, "pdf": t.pdf, "suite": suite, "type": t.type, "passed": None, "why": "no md"}
        md = open(md_path, encoding="utf-8").read()
        try:
            ok, why = t.run(md)
        except Exception as e:  # the benchmark counts a crashing test as failed
            ok, why = False, f"error: {e}"
        return {
            "id": t.id,
            "pdf": t.pdf,
            "suite": suite,
            "type": t.type,
            "passed": bool(ok),
            "why": why[:300],
        }

    with ThreadPoolExecutor(max_workers=min(os.cpu_count() or 1, 64)) as ex:
        out = list(ex.map(run, tests))
    json.dump(out, open(out_path, "w"))


if __name__ == "__main__":
    main(*sys.argv[1:4])
