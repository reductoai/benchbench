import csv
import importlib
import json
import math
import runpy
import shutil
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def analysis_modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "analysis"))
    global A, G
    A = importlib.import_module("ablation_summary")
    G = importlib.import_module("grader_appendix")


PRESETS = ["reducto_r1", "other"]
DATA = {
    "benchmarks": [
        {
            "id": "bench",
            "name": "Bench",
            "vendors": [{"preset": p, "vendor": p} for p in PRESETS],
        }
    ]
}


def put(root, condition, tag, page, scores=None, ok=True):
    path = root / "bench" / "judge" / condition / tag / (page + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "ok": ok,
        "error": "content_filter",
        "verdicts": [{"presetId": p, "score": s} for p, s in zip(PRESETS, scores or [], strict=False)],
    }
    path.write_text(json.dumps(value))
    return path


def test_clean_averages_repeats_only_on_matched_pages_and_tilt_uses_r0(tmp_path):
    for condition in A.CONDITIONS:
        put(tmp_path, condition, A.PRIMARY, "shared", [10, 2])
        put(tmp_path, condition, A.PRIMARY, "unmatched", [10, 1])
        put(tmp_path, condition, A.TAGS["minimal"], "shared", [3, 6])
    put(tmp_path, "clean", "gpt-6.1-sol-medium-r1", "shared", [0, 10])
    cells, scores, failures, issues = A.analyze(tmp_path, DATA, ["minimal"])
    clean, tilt = cells
    assert clean["sol_pages"] == 1 and clean["sol_r0_pages"] == 2
    assert clean["winner"] == clean["sol_winner"] == "other"
    assert clean["same_winner"] == 1 and clean["reducto_rank"] == 2
    assert clean["spearman"] == 1
    assert [s["sol_mean_pair_score"] for s in scores[:2]] == [5, 6]
    assert tilt["sol_winner"] == "reducto_r1" and tilt["spearman"] == -1
    assert not failures and not issues


def test_empty_and_failed_pages_never_count_as_losses_or_successes(tmp_path):
    put(tmp_path, "clean", A.PRIMARY, "page", [8, 5])
    put(tmp_path, "clean", "gpt-6.1-sol-medium-r1", "page", [8, 5])
    put(tmp_path, "clean", A.TAGS["minimal"], "page", ok=False)
    cells, scores, failures, issues = A.analyze(tmp_path, DATA, ["minimal"])
    assert cells[0]["status"] == "complete_with_failures"
    assert cells[0]["same_winner"] is None and cells[0]["matched_pages"] == 0
    assert cells[0]["failed_pages"] == 1 and cells[0]["missing_pages"] == 0
    assert cells[1]["status"] == "PARTIAL"
    assert len(failures) == 1 and not scores and not issues
    assert "0/1" in A.markdown(cells, ["minimal"], 1, "now")


def test_invalid_partial_raw_nonfinite_and_ambiguous_tags(tmp_path):
    base = tmp_path / "bench" / "judge" / "clean"
    path = put(tmp_path, "clean", A.TAGS["minimal"], "invalid", [1, 2])
    path.write_text("{")
    put(tmp_path, "clean", A.TAGS["minimal"], "incomplete", [1])
    put(tmp_path, "clean", A.TAGS["minimal"], "nan", [math.nan, 2])
    raw = path.with_name("ignored.raw.json")
    raw.write_text("{}")
    good, failed, invalid = A.load_pages(base, A.TAGS["minimal"], PRESETS)
    assert not good and not failed and len(invalid) == 3
    (base / "gemini-4-argon-medium-r0-own-a").mkdir()
    (base / "gemini-4-argon-medium-r0-own-b").mkdir()
    with pytest.raises(ValueError, match="Ambiguous"):
        A.load_pages(base, A.TAGS["argon"], PRESETS)


def test_ties_and_constant_spearman():
    assert A.ranks([5, 5, 1]) == [1.5, 1.5, 3]
    assert A.winners({"a": 5, "b": 5}) == ["a", "b"]
    assert A.spearman([1, 1], [2, 1]) is None
    assert A.spearman([3, 3, 1], [2, 2, 1]) == pytest.approx(1)


def test_manifested_retries_replace_canonical_verdicts(tmp_path):
    base = tmp_path / "bench/judge/clean"
    tag = A.TAGS["minimal"]
    put(tmp_path, "clean", tag, "page", ok=False)
    snapshot = base / tag / "final-retry/20261117T100000Z"
    snapshot.mkdir(parents=True)
    retry = snapshot / "page.json"
    retry.write_text(
        json.dumps(
            {
                "ok": True,
                "verdicts": [{"presetId": p, "score": 8} for p in PRESETS],
            }
        )
    )
    manifest = {"retried_pages": [{"verdict_key": "prefix/page.json"}]}
    (snapshot / "manifest.json").write_text(json.dumps(manifest))
    good, failed, invalid = A.load_pages(base, tag, PRESETS)
    assert set(good) == {"page"} and not failed and not invalid
    newer = base / tag / "final-retry/20261117T110000Z"
    newer.mkdir()
    (newer / "page.json").write_text(json.dumps({"ok": False, "error": "content_filter"}))
    (newer / "manifest.json").write_text(json.dumps(manifest))
    good, failed, invalid = A.load_pages(base, tag, PRESETS)
    assert not good and failed == {"page": "content_filter"} and not invalid
    (newer / "page.json").unlink()
    good, failed, invalid = A.load_pages(base, tag, PRESETS)
    assert not good and not failed and "page" in invalid


def test_bootstrap_is_paired_reproducible_and_handles_ties():
    clean = np.array([[2, 2], [4, 4], [6, 6]])
    intervals, means = G.bootstrap(clean)
    repeated, _ = G.bootstrap(clean)
    np.testing.assert_array_equal(intervals, repeated)
    np.testing.assert_array_equal(means[:, 0], means[:, 1])
    intervals, samples = G.bootstrap(clean, 2 * clean)
    np.testing.assert_allclose(intervals, 100)
    np.testing.assert_allclose(samples, 100)


@pytest.mark.parametrize(
    "clean,tilt",
    [
        ([], None),
        ([[float("nan")]], None),
        ([[1]], [[1, 2]]),
        ([[0]], [[1]]),
        ([[1]], [[float("inf")]]),
    ],
)
def test_bootstrap_rejects_invalid_inputs(clean, tilt):
    with pytest.raises(ValueError):
        G.bootstrap(clean, tilt)


def test_appendix_refuses_unfinished_sweeps(tmp_path):
    with pytest.raises(ValueError, match="finalized"):
        G.build(tmp_path, DATA)


def test_appendix_bootstraps_all_five_judges_on_matched_pages(tmp_path):
    for condition in A.CONDITIONS:
        values = [8, 6] if condition == "clean" else [4, 3]
        put(tmp_path, condition, A.PRIMARY, "page", values)
        for tag in A.TAGS.values():
            put(tmp_path, condition, tag.replace("*", "-test"), "page", values)
    put(tmp_path, "clean", "gpt-6.1-sol-medium-r1", "page", [8, 6])
    cells, scores, failures, drops = G.build(tmp_path, DATA)
    assert len(cells) == 10 and len(scores) == 20 and len(drops) == 12
    assert not failures and all(r["p_reducto_top"] == 1 for r in cells)
    for row in drops:
        assert row["drop_pct"] == row["lo_pct"] == row["hi_pct"] == -50
    summary = G.aggregate(cells)
    assert len(summary) == 10 and all(r["same_winner"] == 1 for r in summary)


def test_saved_appendix_has_only_refreshed_judges_and_intervals():
    root = Path(__file__).resolve().parents[1] / "results"
    with (root / "appendix/cells.csv").open() as stream:
        cells = list(csv.DictReader(stream))
    assert len(cells) == 120 and {r["judge"] for r in cells} == set(A.TAGS)
    assert all(r["status"] != "PARTIAL" and int(r["matched_pages"]) > 0 for r in cells)
    with (root / "appendix/drops.csv").open() as stream:
        drops = list(csv.DictReader(stream))
    assert len(drops) == 576 and {r["judge"] for r in drops} == {"sol", *A.TAGS}
    assert all(math.isfinite(float(r["lo_pct"])) and float(r["lo_pct"]) <= float(r["hi_pct"]) for r in drops)
    with (root / "drop_ci.csv").open() as stream:
        primary = list(csv.DictReader(stream))
    assert len(primary) == 192 and {r["metric"] for r in primary} == {"gpt", "min"}
    data = json.loads((root / "data.json").read_text())
    assert data["refresh"]["confidence_intervals"]["draws"] == 2000
    assert json.loads((root / "appendix/repeat-check.json").read_text()) == data["refresh"]["repeat_check"]


def test_build_data_preserves_refreshed_judge_metadata(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    for name in ("data.json", "results.csv", "native_under_augment_rerun.csv"):
        shutil.copyfile(root / "results" / name, tmp_path / name)
    before = json.loads((tmp_path / "data.json").read_text())
    monkeypatch.setenv("BENCHBENCH_RESULTS", str(tmp_path))
    monkeypatch.delenv("BENCHBENCH_RUNS", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(root / "analysis/build_data.py"))
    assert exit_info.value.code == 0
    after = json.loads((tmp_path / "data.json").read_text())
    for field in ("judge_ablations", "confidence_intervals", "repeat_check"):
        assert after["refresh"][field] == before["refresh"][field]
