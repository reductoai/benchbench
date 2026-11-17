import csv
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def headlines(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "analysis"))
    return importlib.import_module("headlines")


@pytest.fixture
def cohort():
    return {"benchmarks": [{"id": "example", "vendors": [{"preset": "a"}, {"preset": "b"}]}]}


def verdict(runs, repeat, page, scores, ok=True):
    directory = runs / "example/judge/clean" / f"gpt-6.1-sol-medium-r{repeat}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{page}.json").write_text(
        json.dumps(
            {
                "ok": ok,
                "page_key": page,
                "verdicts": [{"presetId": p, "score": score} for p, score in scores.items()],
            }
        )
    )


def test_repeat_check_matches_complete_pages(headlines, cohort, tmp_path):
    for repeat in (0, 1):
        verdict(tmp_path, repeat, "shared", {"a": 9, "b": 8})
        verdict(tmp_path, repeat, "failed", {"a": 0, "b": 10}, ok=False)
        verdict(tmp_path, repeat, "incomplete", {"b": 10})
        verdict(tmp_path, repeat, "request.raw", {"a": 0, "b": 10})
    verdict(tmp_path, 0, "only-r0", {"a": 0, "b": 10})
    check = headlines.repeat_check(cohort, tmp_path)
    assert check["benchmarks"] == [
        {"id": "example", "pages": 1, "r0_pages": 2, "r1_pages": 1, "winners": [["a"], ["a"]]}
    ]


def test_repeat_check_keeps_ties(headlines, cohort, tmp_path):
    for repeat in (0, 1):
        verdict(tmp_path, repeat, "shared", {"b": 9, "a": 9})
    assert headlines.repeat_check(cohort, tmp_path)["benchmarks"][0]["winners"] == [
        ["a", "b"],
        ["a", "b"],
    ]


def test_repeat_check_rejects_empty_cohort(headlines, tmp_path):
    with pytest.raises(ValueError, match="Incomplete repeat cohort"):
        headlines.repeat_check({"benchmarks": []}, tmp_path)


def test_repeat_check_rejects_missing_repeat(headlines, cohort, tmp_path):
    verdict(tmp_path, 0, "shared", {"a": 9, "b": 8})
    with pytest.raises(ValueError, match="Incomplete repeat cohort: example"):
        headlines.repeat_check(cohort, tmp_path)


def test_refreshed_snapshot_excludes_historical_intervals():
    data = json.loads((ROOT / "results/data.json").read_text())
    assert all("ci" not in v for b in data["benchmarks"] for v in b["vendors"])
    checks = data["refresh"]["repeat_check"]["benchmarks"]
    assert {b["id"] for b in checks} == {b["id"] for b in data["benchmarks"]}
    assert all(b["pages"] == b["r0_pages"] == b["r1_pages"] > 0 for b in checks)


def test_mdp_native_means_have_one_source():
    data = json.loads((ROOT / "results/data.json").read_text())
    values = {
        v["preset"]: v["native_clean"]
        for b in data["benchmarks"]
        if b["id"] == "mdpbench"
        for v in b["vendors"]
    }
    for name in ("results.csv", "native_rotated_corrected.csv"):
        with (ROOT / "results" / name).open() as f:
            actual = {
                r["preset"]: float(r["native_clean"])
                for r in csv.DictReader(f)
                if r["benchmark"] == "mdpbench"
            }
        assert actual == values
