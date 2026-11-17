"""Run a command with native-env.json paths expanded relative to BENCHBENCH_RUNS.

Usage: python scripts/native_env.py benchbench native RUN --benchmark NAME ...
Install scorer dependencies in the separate environments named by native-env.json.
The adapter docstrings and catalog record each upstream repository and pinned revision.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    here = Path(__file__).resolve().parent
    os.environ.setdefault("BENCHBENCH_RUNS", str(here.parent / "results/runs"))
    env = {k: os.path.expandvars(v) for k, v in json.loads((here / "native-env.json").read_text()).items()}
    env["BENCHBENCH_NATIVE_PYTHON"] = str(here / "native_python.sh")
    if not sys.argv[1:]:
        raise SystemExit(__doc__)
    raise SystemExit(subprocess.call(sys.argv[1:], env={**os.environ, **env}))


if __name__ == "__main__":
    main()
