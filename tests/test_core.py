import json
import os

import numpy as np
from PIL import Image, ImageDraw

from benchbench import probes, stats
from benchbench.augment import CONDITIONS, perturb, png_bytes
from benchbench.catalog import load_catalog, match_files, stratum


def page():
    img = Image.new("RGB", (400, 520), "white")
    ImageDraw.Draw(img).text((20, 20), "Total 1,234.56", fill="black")
    return img


def test_perturbations_are_deterministic_and_per_page():
    for cond in CONDITIONS:
        a, pa = perturb(page(), cond, 1, "b", "p1")
        b, pb = perturb(page(), cond, 1, "b", "p1")
        assert png_bytes(a) == png_bytes(b) and pa == pb
    _, p1 = perturb(page(), "tilt_2_4", 1, "b", "p1")
    _, p2 = perturb(page(), "tilt_2_4", 1, "b", "p2")
    assert p1["angle_deg"] != p2["angle_deg"]
    assert 2 <= abs(p1["angle_deg"]) <= 4


def test_catalog_loads_and_globs():
    cat = load_catalog()
    assert {"parsebench2", "olmocr_bench", "omnidocbench", "dp_bench", "rd_tablebench"} <= set(cat)
    files = ["docs/table/a.pdf", "docs/chart/b.pdf", "docs/layout/c.jpg", "README.md"]
    assert match_files(files, "docs/**/*.pdf") == ["docs/chart/b.pdf", "docs/table/a.pdf"]
    assert match_files(files, "docs/**/*.{pdf,jpg}") == [
        "docs/chart/b.pdf",
        "docs/layout/c.jpg",
        "docs/table/a.pdf",
    ]
    assert stratum("docs/table/a.pdf", "docs/([^/]+)/") == "table"


def test_table_probes_round_trip():
    md = "Intro\n\n<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>\n"
    pipe, info = probes.apply_probe("pipe_tables", md, (0,))
    assert info["converted"] == 1 and "| a | b |" in pipe
    back, _ = probes.apply_probe("html_tables", pipe, (0,))
    assert "<td>1</td><td>2</td>" in back
    merged = '<table><tr><td colspan="2">x</td></tr></table>'
    assert probes.apply_probe("pipe_tables", merged, (0,))[1]["kept_merged"] == 1


def test_digit_probe_changes_digits_only():
    md = "Revenue 1234567890 and 9876543210 total 55555"
    out, info = probes.apply_probe("digits_5pct", md, (1,))
    assert info["changed"] >= 1 and out != md and len(out) == len(md)
    assert [c for c in out if not c.isdigit()] == [c for c in md if not c.isdigit()]


def test_stats():
    a = np.array([8.0, 9, 7, 8, 9, 10])
    b = a - 1
    d = stats.paired_delta(a, b)
    assert abs(d["delta"] + 1) < 1e-9 and d["worse"] == 1.0
    m = np.array([[9, 5], [8, 6], [10, 4.0]])
    assert stats.pair_agreement(m, m)["agreement"] == 1.0
    assert stats.pair_agreement(m, m[:, ::-1])["agreement"] == 0.0
    assert list(stats.win_rate(m)) == [1.0, 0.0]


def test_ranks_share_ties():
    assert list(stats.ranks(np.array([9.0, 8.5, 8.5, 7.0]))) == [1, 2, 2, 4]


def test_scan_png_stays_small():
    big = Image.new("RGB", (1700, 2200), "white")
    ImageDraw.Draw(big).text((100, 100), "Total 1,234.56 " * 20, fill="black")
    scanned, info = perturb(big, "scan", 1, "b", "p1")
    assert scanned.mode == "L" and info["noise"] == "luminance"
    # Noise is incompressible; the guard is that one plane is written, not three (review M2: 8.6 MB).
    assert len(png_bytes(scanned)) < 3_000_000


def test_pairwise_holm_and_tied_spearman():
    g = np.random.default_rng(0)
    base = g.integers(4, 9, 200).astype(float)
    m = np.stack([base + 1.5, base, base + g.normal(0, 0.01, 200)], 1)
    rows = stats.pairwise_deltas(m, ["a", "b", "c"])
    by = {(r["a"], r["b"]): r for r in rows}
    assert by[("a", "b")]["significant"] and not by[("b", "c")]["significant"]
    assert all(r["p_holm"] >= r["p"] for r in rows)
    x = np.array([1.0, 1, 1, 2, 2, 3])
    assert stats.judge_consistency(x, x.copy())["spearman"] == 1.0


def test_neutral_judge_labels_and_score():
    from benchbench import neutral_judge as nj

    a = nj.blind_labels("p1", ["reducto_r1", "llamaparse", "mistral"])
    b = nj.blind_labels("p2", ["reducto_r1", "llamaparse", "mistral"])
    assert sorted(a.values()) == sorted(b.values()) and len(set(a)) == 3
    assert nj.score_from_counts({}) == 10
    assert nj.score_from_counts({"word": 1}) > nj.score_from_counts({"cell": 1}) > 1
    assert nj.score_from_counts({"word": 10_000}) == 1


def test_probes_leave_structure_and_italics():
    md, info = probes.digits_5pct(
        '<td colspan="2">1234567890123456789012</td>', __import__("random").Random(0)
    )
    assert 'colspan="2"' in md and info["changed"] == 1
    out, _ = probes.strip_emphasis("a **b** *c* _d_ snake_case", __import__("random").Random(0))
    assert out == "a b c d snake_case"


def _reference_ci(d, b=4000, seed=1):
    g = np.random.default_rng(seed)
    boots = d[g.integers(0, len(d), (b, len(d)))].mean(1)
    return np.quantile(boots, [0.025, 0.975])


def test_pairwise_bootstrap_with_missing_pages_matches_reference():
    # Review N2: first 100 pages delta +1, next 100 delta -0.5, then 100 pages missing for one preset.
    a = np.r_[np.full(100, 6.0), np.full(100, 5.0), np.full(100, np.nan)]
    b = np.r_[np.full(100, 5.0), np.full(100, 5.5), np.full(100, 5.0)]
    a[::7] += 0.3
    row = stats.pairwise_deltas(np.stack([a, b], 1), ["a", "b"])[0]
    d = (a - b)[~np.isnan(a - b)]
    ref = _reference_ci(d)
    assert row["n"] == 200 and abs(row["delta"] - d.mean()) < 1e-12
    assert abs(row["ci95"][0] - ref[0]) < 0.03 and abs(row["ci95"][1] - ref[1]) < 0.03
    far = np.stack([np.full(50, 9.0), np.full(50, 1.0)], 1)
    assert stats.pairwise_deltas(far, ["a", "b"], b=999)[0]["p"] == 2 / 1000


def test_shared_resample_and_icc():
    g = np.random.default_rng(0)
    m = g.normal(7, 1, (120, 3))
    idx = stats.boot_idx(120)
    assert len(stats.rank_interval(m, idx=idx)) == 3
    rows = stats.pairwise_deltas(m, ["a", "b", "c"], idx=idx)
    assert all(r["n"] == 120 for r in rows)
    x = g.integers(1, 11, (80, 4)).astype(float)
    assert stats.icc1(x, x) > 0.99 and stats.icc1(x, g.permutation(x.ravel()).reshape(x.shape)) < 0.3


def test_judge_tag_separates_configs():
    from benchbench.pipeline import judge_tag

    tags = {
        judge_tag("m", "medium", 0),
        judge_tag("m", "medium", 0, image="condition"),
        judge_tag("m", "medium", 0, allow_failed=True),
        judge_tag("m", "medium", 0, base_url="https://other.example/v1"),
        judge_tag("m", "medium", 0, strip_style=True),
        judge_tag("m", "medium", 0, label="probes"),
        judge_tag("m", "medium", 0, prompt="neutral"),
        judge_tag("m", "medium", 0, image_detail="original"),
        judge_tag("m", "medium", 0, gemini_resolution="MEDIA_RESOLUTION_ULTRA_HIGH"),
    }
    assert len(tags) == 9 and judge_tag("m", "medium", 0) == "m-medium-r0"


def test_strip_style():
    from benchbench.pipeline import strip_style

    md = '<!-- page 1 --><span id="x1">Total</span> ![fig](a.png) <td class="c" data-bbox="1">2</td>'
    assert strip_style(md) == "Total  <td>2</td>"


def test_real5_pairing():
    from benchbench.datasets import pair_captures

    files = [f"Real5-OmniDocBench-{c}/PPT_1_page_003.png" for c in ("Skew", "Screen-Photography")]
    files.append("Real5-OmniDocBench-Skew/orphan.png")
    out = pair_captures(files, ["images/PPT_1_page_003.png"], "^Real5-OmniDocBench-([^/]+)/")
    assert list(out) == ["PPT_1_page_003"]
    assert set(out["PPT_1_page_003"]["captures"]) == {"real_skew", "real_screen_photography"}


def test_dry_run_counts_failures(tmp_path):
    """End to end on synthetic pages with fake parsers and judge: failed parses are counted and dropped."""
    from benchbench import pipeline
    from benchbench.report import summarize
    from benchbench.storage import Run, page_key, write_bytes, write_jsonl

    run = Run(tmp_path)
    rows = []
    for i in range(40):
        pid = f"p{i}"
        rows.append({"benchmark": "b", "page_id": pid, "page_key": page_key("b", pid)})
        write_bytes(run.image("clean", rows[-1]["page_key"]), png_bytes(page()))
    write_jsonl(tmp_path / "pages.jsonl", rows)
    (tmp_path / "run.json").write_text('{"seed": 1, "dpi": 200}')
    presets = ["fake_ocr", "fake_empty", "fake_fail"]
    pipeline.parse_all(run, presets, ["clean"], workers=2)
    pipeline.judge_all(run, presets, ["clean"], "fake", repeats=2, workers=2)
    pipeline.judge_all(run, presets, ["clean"], "fake", workers=2, allow_failed=True)
    tags = [pipeline.judge_tag("fake", "medium", r) for r in range(2)]
    res = summarize(
        run,
        "b",
        presets,
        ["clean"],
        tags,
        secondary_tag=pipeline.judge_tag("fake", "medium", 0, allow_failed=True),
    )
    c = res["conditions"]["clean"]
    n_fail = c["failed_parses"]["fake_fail"]
    assert n_fail > 0 and c["pages_dropped_for_failure"] == n_fail and c["pages"] == 40 - n_fail
    assert c["errors"]["fake_ocr"]["pages"] == c["pages"]
    assert c["secondary_failed_as_empty"]["pages"] == 40


def test_claim_rule_needs_every_compare_judge(tmp_path):
    """Review 3 #1: a compare judge that never ran must not confirm anything."""
    from benchbench import pipeline
    from benchbench.report import summarize
    from benchbench.storage import Run, page_key, write_bytes, write_json, write_jsonl

    run = Run(tmp_path)
    rows = [{"benchmark": "b", "page_id": f"p{i}", "page_key": page_key("b", f"p{i}")} for i in range(30)]
    write_jsonl(tmp_path / "pages.jsonl", rows)
    (tmp_path / "run.json").write_text('{"seed": 1, "dpi": 200}')
    presets = ["good", "bad"]
    for r in rows:
        write_bytes(run.image("clean", r["page_key"]), png_bytes(page()))
        for s in presets:
            write_json(run.parse("clean", s, r["page_key"]), {"ok": True, "markdown": s})
        for tag in ("m-medium-r0", "other-medium-r0", "other-medium-r1"):
            write_json(
                run.judge("clean", tag, r["page_key"]),
                {
                    "ok": True,
                    "answered_models": [tag[:1]],
                    "verdicts": [{"presetId": "good", "score": 9}, {"presetId": "bad", "score": 3}],
                },
            )
    both = {"other": "other-medium-r0", "ghost": "never-ran"}
    res = summarize(run, "b", presets, ["clean"], ["m-medium-r0"], compare=both)
    assert res["compare"]["claims"] and not any(c["confirmed"] for c in res["compare"]["claims"])
    res = summarize(run, "b", presets, ["clean"], ["m-medium-r0"], compare={"other": "other-medium-r0"})
    assert all(c["confirmed"] for c in res["compare"]["claims"])
    two = {"other": ["other-medium-r0", "other-medium-r1"]}
    res = summarize(run, "b", presets, ["clean"], ["m-medium-r0"], compare=two, out_dir=tmp_path / "rep")
    assert res["compare"]["judges"]["other"]["tag"] == two["other"]
    assert all(c["confirmed"] for c in res["compare"]["claims"])
    assert "other-medium-r0, other-medium-r1" in (tmp_path / "rep" / "summary.md").read_text()
    assert pipeline._FETCH_ERROR.search("failed to download image: failed to send GET request")
    assert not pipeline._FETCH_ERROR.search("HTTP 413: payload too large")


def test_dp_bench_md_to_elements():
    from benchbench.adapters.dp_bench import md_to_elements

    md = (
        '<!-- PageHeader="Chapter 2" -->\n<!-- Figure -->\n# Title **bold**\n\n'
        "![img-0.jpeg](img-0.jpeg)\n\n- item one\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "<table><tr><td>x</td></tr></table>\n"
    )
    els = md_to_elements(md)
    assert [e["category"] for e in els] == ["paragraph", "heading1", "paragraph", "table", "table"]
    assert [e["content"]["text"] for e in els[:3]] == ["Chapter 2", "Title bold", "item one"]
    assert "<td>1</td>" in els[3]["content"]["html"] and els[4]["content"]["html"].startswith("<table>")


def test_csv_strata(tmp_path, monkeypatch):
    from benchbench import datasets

    (tmp_path / "s.csv").write_text("pdf_path,language\na.pdf,en\nb.pdf,de\nc.pdf,en\n")
    monkeypatch.setattr(datasets, "_extract", lambda bench: tmp_path)
    bench = {
        "id": "t",
        "hf_repo": "x/y",
        "hf_revision": "r",
        "page_files": {
            "archive": "*.zip",
            "strata_csv": {"file": "s.csv", "key": "pdf_path", "value": "language"},
        },
    }
    rows = datasets._stratified(bench, ["img/a.jpg", "img/b.jpg", "img/c.jpg", "img/d.jpg"], None, 1)
    assert {r["file"]: r["stratum"] for r in rows} == {
        "img/a.jpg": "en",
        "img/b.jpg": "de",
        "img/c.jpg": "en",
        "img/d.jpg": "other",
    }


def test_rd_tablebench_table_candidates():
    from benchbench.adapters import rd_tablebench as A

    md = "x\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n<table><tr><td>z</td></tr></table>\n"
    html, pipes = A.candidate_tables(md)
    assert html == ["<table><tr><td>z</td></tr></table>"]
    assert len(pipes) == 1 and "<td>1</td><td>2</td>" in pipes[0]
    assert A.largest(html + pipes) == pipes[0]
    assert A.largest([]) is None


def test_host_env_loads_or_fails(tmp_path, monkeypatch):
    import pytest

    from benchbench import pipeline

    for k in pipeline.HOST_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BENCHBENCH_HOST_ENV", str(tmp_path / "none.env"))
    with pytest.raises(SystemExit):
        pipeline.load_host_env()
    env = tmp_path / "h.env"
    env.write_text("".join(f"export {k}=v{i}\n" for i, k in enumerate(pipeline.HOST_ENV)))
    monkeypatch.setenv("BENCHBENCH_HOST_ENV", str(env))
    pipeline.load_host_env()
    assert [__import__("os").environ[k] for k in pipeline.HOST_ENV] == ["v0", "v1", "v2"]


def test_html_tables_probe_keeps_inline_tags():
    md = "| Country | Note |\n|---|---|\n| <i>Norway</i> | a < b & <b>c</b><br/> |\n"
    out, _ = probes.apply_probe("html_tables", md, (0,))
    assert "<td><i>Norway</i></td>" in out and "<td>a &lt; b &amp; <b>c</b><br/></td>" in out


def test_pipe_table_at_end_of_text_keeps_last_row():
    from benchbench.probes import PIPE_TABLE, pipe_table_to_html

    md = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    html = PIPE_TABLE.sub(lambda m: pipe_table_to_html(m.group(0)), md)
    assert "<td>3</td><td>4</td>" in html and "|" not in html


def test_label_order_shared_and_own():
    from benchbench import neutral_judge
    from benchbench.pipeline import blind_id, judge_tag, label_order_map

    presets = [f"s{i}" for i in range(8)]
    assert blind_id("k", "clean", 1, "gpt") == "k|clean|r1" == blind_id("k", "clean", 1, "gemini")
    own = {blind_id(f"k{i}", "clean", 0, m, "own") for i in range(20) for m in ("gpt", "gemini")}
    assert len(own) == 40

    def orders(model):
        return [
            list(label_order_map(blind_id(f"k{i}", "clean", 0, model, "own"), presets).values())
            for i in range(20)
        ]

    assert sum(a != b for a, b in zip(orders("gpt"), orders("gemini"), strict=True)) >= 18
    m = label_order_map("k|clean|r0", presets)
    assert list(m) == [f"parse_{c}" for c in "abcdefgh"] and sorted(m.values()) == presets
    assert list(neutral_judge.blind_labels("k|clean|r0", presets).values()) == list(m.values())
    assert judge_tag("g", "medium", 1, label_order="own") == "g-medium-r1-own"
    assert judge_tag("g", "medium", 1) == "g-medium-r1"


def test_label_order_own_judges_into_own_tag(tmp_path):
    from benchbench import pipeline
    from benchbench.storage import Run, page_key, read_json, write_bytes, write_jsonl

    run = Run(tmp_path)
    rows = [{"benchmark": "b", "page_id": f"p{i}", "page_key": page_key("b", f"p{i}")} for i in range(4)]
    write_jsonl(tmp_path / "pages.jsonl", rows)
    (tmp_path / "run.json").write_text('{"seed": 1, "dpi": 200}')
    for r in rows:
        write_bytes(run.image("clean", r["page_key"]), png_bytes(page()))
    presets = ["fake_ocr", "fake_empty"]
    pipeline.parse_all(run, presets, ["clean"], workers=2)
    pipeline.judge_all(run, presets, ["clean"], "fake", workers=2)
    shared = read_json(run.judge("clean", "fake-medium-r0", rows[0]["page_key"]))
    assert "label_order" not in shared["config"] and shared["blind_id"] == f"{rows[0]['page_key']}|clean|r0"
    pipeline.judge_all(run, presets, ["clean"], "fake", workers=2, label_order="own")
    out = run.judge("clean", "fake-medium-r0-own", rows[0]["page_key"])
    v, raw = read_json(out), read_json(out.with_name(f"{out.stem}.raw.json"))
    assert v["config"]["label_order"] == "own" and v["blind_id"].endswith("|fake")
    assert raw["blind_id"] == v["blind_id"] and sorted(raw["label_order"].values()) == sorted(presets)
    assert read_json(run.judge("clean", "fake-medium-r0", rows[0]["page_key"])) == shared


def test_stage3_delta_uses_clean_mean(tmp_path):
    from benchbench.report import summarize
    from benchbench.storage import Run, page_key, write_json, write_jsonl

    run = Run(tmp_path)
    rows = [{"benchmark": "b", "page_id": f"p{i}", "page_key": page_key("b", f"p{i}")} for i in range(20)]
    write_jsonl(tmp_path / "pages.jsonl", rows)
    (tmp_path / "run.json").write_text('{"seed": 1, "dpi": 200}')
    presets = ["x", "y"]

    def verdict(cond, tag, k, sx, sy):
        write_json(
            run.judge(cond, tag, k),
            {
                "ok": True,
                "answered_models": ["m"],
                "verdicts": [{"presetId": "x", "score": sx}, {"presetId": "y", "score": sy}],
            },
        )

    for i, r in enumerate(rows):
        k = r["page_key"]
        for cond in ("clean", "tilt"):
            for s in presets:
                write_json(run.parse(cond, s, k), {"ok": True, "markdown": s})
        verdict("clean", "m-medium-r0", k, 8, 4 + i % 3)
        verdict("clean", "m-medium-r1", k, 6, 5)
        verdict("tilt", "m-medium-r0", k, 5, 5)
    res = summarize(run, "b", presets, ["clean", "tilt"], ["m-medium-r0", "m-medium-r1"])
    t = res["conditions"]["tilt"]
    assert abs(t["delta_vs_clean"]["x"]["delta"] - (5 - 7)) < 1e-9
    for s in presets:
        printed = t["judge"][s]["mean"] - t["clean_same_pages"][s]["mean"]
        assert abs(t["delta_vs_clean"][s]["delta"] - printed) < 1e-9


def test_report_out_label_keeps_primary_tags(tmp_path):
    """--out-label moves only the report; --label would also change the primary judge tags."""
    from benchbench import cli, pipeline
    from benchbench.storage import Run, page_key, write_bytes, write_jsonl

    run = Run(tmp_path)
    rows = [{"benchmark": "b", "page_id": f"p{i}", "page_key": page_key("b", f"p{i}")} for i in range(6)]
    write_jsonl(tmp_path / "pages.jsonl", rows)
    (tmp_path / "run.json").write_text('{"seed": 1, "dpi": 200}')
    for r in rows:
        write_bytes(run.image("clean", r["page_key"]), png_bytes(page()))
    presets = ["fake_ocr", "fake_empty"]
    pipeline.parse_all(run, presets, ["clean"], workers=2)
    pipeline.judge_all(run, presets, ["clean"], "fake", workers=2)
    pipeline.judge_all(run, presets, ["clean"], "fake", workers=2, label_order="own")
    base = ["report", str(tmp_path), "--benchmark", "b", "--presets", *presets, "--conditions", "clean"]
    cmp = ["--judge", "fake", "--compare", "parsejudge:fake", "--compare-label-order", "own"]
    cli.main([*base, *cmp, "--out-label", "gemini-own"])
    res = json.loads((tmp_path / "reports" / "b" / "gemini-own" / "summary.json").read_text())
    assert res["conditions"]["clean"]["pages"] == 6
    assert res["compare"]["judges"]["parsejudge:fake"]["pages"] == 6
    assert not (tmp_path / "reports" / "b" / "summary.json").exists()


def test_write_if_changed_is_atomic_and_skips_unchanged(tmp_path, monkeypatch):

    from benchbench import bridge

    f = tmp_path / "judge.benchbench-png.ts"
    assert bridge.write_if_changed(f, b"v1")
    ino = f.stat().st_ino
    assert not bridge.write_if_changed(f, b"v1")
    assert f.stat().st_ino == ino
    replaced = []
    real = os.replace
    monkeypatch.setattr(bridge.os, "replace", lambda a, b: (replaced.append(b), real(a, b)))
    assert bridge.write_if_changed(f, b"v2")
    assert f.read_bytes() == b"v2" and replaced == [f]
    assert [p.name for p in tmp_path.iterdir()] == [f.name]
