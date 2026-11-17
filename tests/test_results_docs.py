import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def generator(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "analysis"))
    return importlib.import_module("make_results_md")


def test_result_document_is_current(generator):
    results = ROOT / "results"
    data = json.loads((results / "data.json").read_text())
    assert generator.render(data).encode() == (ROOT / "docs/RESULTS.md").read_bytes()


def test_result_document_rejects_empty_cohort(generator):
    with pytest.raises(ValueError, match="Incomplete"):
        generator.render({"benchmarks": []})


def test_repeat_winners_require_all_presets(generator):
    with pytest.raises(ValueError, match="Incomplete"):
        generator.repeat_winners({"benchmarks": []}, ["example"])


def test_winners_keep_ties(generator):
    assert generator.winners([{"vendor": "B", "x": 2}, {"vendor": "A", "x": 2}], "x") == ["A", "B"]


def test_percentage_headlines(generator):
    data = json.loads((ROOT / "results/data.json").read_text())
    summary = generator.summarize(data)
    assert summary["parser_benchmark_pairs"] == 96
    assert summary["leads_smaller_pct"] == 9
    assert summary["leads_smaller_points"] == 8
    assert summary["native_leads"]["idp_leaderboard"]["lead_pct"] == pytest.approx(11.7688, abs=0.0001)
    assert summary["native_leads"]["idp_leaderboard"]["median_loss_pct"] == pytest.approx(13.4375, abs=0.0001)
