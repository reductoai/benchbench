"""Find earliest invocation from local parse and attempt records."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

root = Path(os.environ.get("BENCHBENCH_RUNS", Path(__file__).resolve().parents[2] / "results/runs"))
benchmark = sys.argv[1]
records = []
for folder in ("parses", "attempts"):
    for path in (root / benchmark / folder).rglob("*.json"):
        value = json.loads(path.read_text())
        if value.get("finished"):
            start = datetime.fromisoformat(value["finished"]) - timedelta(
                milliseconds=value.get("latencyMs", 0)
            )
            records.append((start.isoformat(), str(path.relative_to(root))))
print(
    json.dumps(
        {
            "bench": benchmark,
            "with_finished": len(records),
            "earliest_start": min(records) if records else None,
        }
    )
)
