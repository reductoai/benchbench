import hashlib
import json
import os
import tarfile
from pathlib import Path

from huggingface_hub import hf_hub_download

root = Path(os.environ.get("BENCHBENCH_RUNS", Path(__file__).resolve().parents[1] / "results/runs"))
args = dict(
    repo_id="zhihengli-casia/puredocbench",
    repo_type="dataset",
    revision="4665b40a3333f7643bad7c8675a9062b482511ad",
    token=os.environ.get("HF_TOKEN"),
)
archive = Path(hf_hub_download(filename="gt/puredocbench_gt_latest.tar.gz", **args))
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
assert sha == "4340c7120be012fe324ce13832c92869dd5eae7d384c473d335a7bed934ab534"
release = root / "puredoc-release" / "puredocbench-v1.0"
release.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive) as t:
    for member in t.getmembers():
        target = (release / member.name).resolve()
        assert target.is_relative_to(release.resolve())
        assert member.isfile() or member.isdir()
    t.extractall(release, filter="data")
(root / "puredoc-gt-provenance.json").write_text(
    json.dumps(
        dict(
            dataset=args["repo_id"],
            revision=args["revision"],
            archive="gt/puredocbench_gt_latest.tar.gz",
            sha256=sha,
        ),
        indent=2,
    )
)
print("PureDocBench pinned GT restored:", sha)
