import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from benchbench import pipeline
from benchbench.catalog import load_catalog

PUBLIC = (
    "dp_bench idp_leaderboard mdpbench ocrflux_bench olmocr_bench omnidocbench "
    "omniparsebench parsebench2 puredocbench rd_tablebench real5_omnidocbench score_bench"
).split()
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("benchmark", PUBLIC)
def test_public_adapter_and_sample(benchmark):
    adapter = importlib.import_module(f"benchbench.adapters.{benchmark}")
    assert callable(adapter.export) and callable(adapter.score)
    assert benchmark in load_catalog()
    sample = ROOT / "results/samples" / benchmark
    assert json.loads((sample / "run.json").read_text())["seed"] == 20261107
    assert all(
        json.loads(line)["benchmark"] == benchmark
        for line in (sample / "pages.jsonl").read_text().splitlines()
    )


def test_host_uses_configurable_s3(monkeypatch):
    import boto3

    seen = {}
    for key in pipeline.HOST_ENV:
        monkeypatch.setenv(key, "example")
    monkeypatch.setenv("BENCHBENCH_S3_ENDPOINT_URL", "https://storage.example.test")
    monkeypatch.setenv("BENCHBENCH_S3_REGION", "example-region")

    def client(service, **kwargs):
        seen.update(kwargs)
        assert service == "s3"
        return object()

    monkeypatch.setattr(boto3, "client", client)
    _, bucket = pipeline._new_s3_host()
    assert bucket == "example"
    assert seen["endpoint_url"] == "https://storage.example.test"
    assert seen["region_name"] == "example-region"


def test_host_validation_propagates_bucket_errors(tmp_path, monkeypatch):
    class Client:
        def head_bucket(self, **kwargs):
            raise RuntimeError("bucket unavailable")

    monkeypatch.setattr(pipeline, "load_host_env", lambda: None)
    monkeypatch.setattr(pipeline, "_s3_host", lambda: (Client(), "example"))
    with pytest.raises(RuntimeError, match="bucket unavailable"):
        pipeline.make_host(tmp_path / "host.env")


def test_timeline_without_resampling_record(monkeypatch):
    spec = importlib.util.spec_from_file_location("figure_data", ROOT / "analysis/figures/data.py")
    data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(data)

    monkeypatch.setattr(data, "provenance", lambda: {"resample": {}, "first_call": {}})
    data.timeline.cache_clear()
    try:
        timeline = data.timeline("parsebench2")
        assert timeline["pages"] == 500
        assert timeline["resampled"] is None
        assert timeline["same_set"] is None
        assert timeline["first_call"] is None
    finally:
        data.timeline.cache_clear()
