"""Parse benchmark runs concurrently using credentials from the environment."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchbench import pipeline
from benchbench.storage import Run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--benchmarks", nargs="+", required=True)
    parser.add_argument("--presets", nargs="+", default=["datalab_accurate"])
    parser.add_argument("--conditions", nargs="+", default=["clean", "tilt_2_4"])
    parser.add_argument("--parallel", type=int, default=12)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    def worker(benchmark):
        pipeline.parse_all(Run(args.runs / benchmark), args.presets, args.conditions, workers=args.workers)

    with ThreadPoolExecutor(args.parallel) as pool:
        list(pool.map(worker, args.benchmarks))


if __name__ == "__main__":
    main()
