"""Summaries per benchmark: native score, blind judge score, judge under each perturbation.

Primary analysis: a page enters a condition only when every preset parsed it and the judge scored every
preset; failed parses are counted from the parse files and their pages dropped. The secondary analysis
(failed parse judged as empty, `judge --allow-failed`) is reported next to it when that run exists.
Holm corrections are per family (one benchmark x condition x judge), never across benchmarks: statements
across benchmarks ("wins on k of 12") are descriptive. Stage 3 deltas are per page, perturbed minus the
mean of the clean repeats (the clean score the table prints), and rest on the primary judge only.
"""

import json
from pathlib import Path

import numpy as np

from . import stats
from .storage import Run, read_json, read_jsonl, write_json


def judge_matrix(
    run: Run, cond: str, tag: str, presets: list[str], keys: list[str]
) -> tuple[np.ndarray, dict]:
    """Scores (pages x presets) and per-cell non-figure error counts from one judge tag."""
    m = np.full((len(keys), len(presets)), np.nan)
    high, low = np.zeros_like(m), np.zeros_like(m)
    models: set = set()
    for i, k in enumerate(keys):
        j = read_json(run.judge(cond, tag, k))
        if not j or not j.get("ok"):
            continue
        models.update(j.get("answered_models") or [j.get("requested_model", tag)])
        by = {v["presetId"]: v for v in j["verdicts"]}
        for c, s in enumerate(presets):
            if s in by:
                m[i, c] = by[s]["score"]
                sev = [e["severity"] for e in by[s].get("errors", []) if e["severity"] != "figure_error"]
                high[i, c], low[i, c] = sev.count("high"), sev.count("low")
    if len(models) > 1:
        raise SystemExit(f"{cond}/{tag}: verdicts from more than one judge model {sorted(models)}; rejudge")
    return m, {"high": high, "low": low, "models": sorted(models)}


def parse_failed(run: Run, cond: str, presets: list[str], keys: list[str]) -> np.ndarray:
    """True where the parse file exists and is not ok (missing parses are not failures)."""
    f = np.zeros((len(keys), len(presets)), dtype=bool)
    for i, k in enumerate(keys):
        for c, s in enumerate(presets):
            v = read_json(run.parse(cond, s, k))
            f[i, c] = v is not None and not v.get("ok") and not v.get("harness_error")
    return f


def _mean_repeats(mats: list[np.ndarray]) -> np.ndarray:
    st = np.stack(mats)
    out = np.nanmean(np.where(np.isnan(st).all(0, keepdims=True), 0, st), 0)
    out[np.isnan(st).all(0)] = np.nan
    return out


def _usage(run: Run, cond: str, presets: list[str], keys: list[str]) -> dict:
    out = {}
    for s in presets:
        lat, cost, price, fail, harness, size_ok, size_fail = [], [], None, 0, 0, [], []
        for k in keys:
            v = read_json(run.parse(cond, s, k))
            if not v:
                continue
            meta = read_json(run.image_meta(cond, k)) or {}
            size = meta.get("bytes")
            if v.get("harness_error"):
                harness += 1
                continue
            if not v.get("ok"):
                fail += 1
                size_fail.append(size)
                continue
            size_ok.append(size)
            lat.append(v.get("latencyMs") or np.nan)
            if v.get("reportedCost") is not None:
                cost.append(float(v["reportedCost"]) if not isinstance(v["reportedCost"], dict) else np.nan)
            price = v.get("listPriceUsdPerPage", price)
        lat_a = np.array(lat, dtype=float)
        mb = lambda xs: float(np.mean([x for x in xs if x]) / 1e6) if any(xs) else None  # noqa: E731
        out[s] = {
            "failed": fail,
            "harness_errors": harness,
            "image_mb_ok": mb(size_ok),
            "image_mb_failed": mb(size_fail),
            "latency_p50_s": float(np.nanmedian(lat_a) / 1000) if len(lat_a) else None,
            "latency_p95_s": float(np.nanquantile(lat_a, 0.95) / 1000) if len(lat_a) else None,
            "list_usd_per_page": price,
            "reported_usd_mean": float(np.nanmean(cost)) if cost and not np.isnan(cost).all() else None,
        }
    return out


def native_matrix(run: Run, cond: str, presets: list[str], keys: list[str]) -> np.ndarray:
    m = np.full((len(keys), len(presets)), np.nan)
    idx = {k: i for i, k in enumerate(keys)}
    for c, s in enumerate(presets):
        for r in read_jsonl(run.native(cond, s)):
            if r["page_key"] in idx and r.get("score") is not None:
                m[idx[r["page_key"]], c] = r["score"]
    return m


def _complete(*ms: np.ndarray) -> np.ndarray:
    ok = np.ones(ms[0].shape[0], dtype=bool)
    for m in ms:
        ok &= ~np.isnan(m).any(1)
    return ok


def summarize(
    run: Run,
    benchmark: str,
    presets: list[str],
    conditions: list[str],
    tags: list[str],
    out_dir: Path | None = None,
    compare: dict[str, list[str]] | None = None,
    secondary_tag: str | None = None,
) -> dict:
    """tags: one primary judge tag per clean repeat (same model and prompt); clean scores are the mean
    of the repeats, perturbed conditions use repeat 0. compare: name -> clean tags of another judge (one per
    repeat, averaged); a pair claim holds only if every compare judge agrees."""
    keys = [p["page_key"] for p in run.pages() if p["benchmark"] == benchmark]
    out_dir = out_dir or run.root / "reports" / benchmark
    reps = [judge_matrix(run, "clean", t, presets, keys) for t in tags]
    fail_clean = parse_failed(run, "clean", presets, keys)
    clean = _mean_repeats([r[0] for r in reps])
    clean[fail_clean.any(1)] = np.nan
    models = sorted({m for r in reps for m in r[1]["models"]})
    native = native_matrix(run, "clean", presets, keys)
    res: dict = {
        "benchmark": benchmark,
        "presets": presets,
        "judge": tags[0],
        "judge_repeats": len(tags),
        "judge_models": models,
        "pages_sampled": len(keys),
        "conditions": {},
    }
    ceiling = None
    if len(tags) > 1:
        r0, r1 = reps[0][0], reps[1][0]
        both = _complete(r0, r1) & ~fail_clean.any(1)
        ceiling = stats.pair_agreement(r0[both], r1[both]) if both.sum() >= 2 else None
    if ceiling:
        res["judge_repeat_agreement"] = ceiling
        res["judge_repeat_consistency"] = {
            **stats.judge_consistency(r0[both], r1[both]),
            "icc1_by_preset": dict(zip(presets, stats.icc1_by_preset(r0[both], r1[both]), strict=True)),
        }
    both = _complete(native, clean)
    if both.sum() >= 2:
        a = stats.pair_agreement(native[both], clean[both])
        if ceiling:
            r0, r1 = reps[0][0], reps[1][0]
            four = both & _complete(r0, r1)
            if four.sum() >= 2:
                gap = stats.agreement_gap(native[four], clean[four], r0[four], r1[four])
                a["ceiling_gap"] = gap
                a["verdict"] = gap["label"]
        res["native_vs_judge"] = a
        res["native"] = _per_preset(native[both], presets)
        res["native_pages"] = int(both.sum())
    for cond in conditions:
        if cond == "clean":
            m, fail = clean, fail_clean
            high, low = reps[0][1]["high"], reps[0][1]["low"]
        else:
            m, mm = judge_matrix(run, cond, tags[0], presets, keys)
            fail = parse_failed(run, cond, presets, keys)
            m[fail.any(1)] = np.nan
            high, low = mm["high"], mm["low"]
        ok = _complete(m, clean)
        block = {
            "pages": int(ok.sum()),
            **_per_preset_block(m[ok], presets),
            "failed_parses": {s: int(fail[:, c].sum()) for c, s in enumerate(presets)},
            "pages_dropped_for_failure": int(fail.any(1).sum()),
            "errors": {
                s: {
                    "high": int(high[ok, c].sum()),
                    "low": int(low[ok, c].sum()),
                    "pages_no_error": int(((high[ok, c] + low[ok, c]) == 0).sum()),
                    "pages": int(ok.sum()),
                }
                for c, s in enumerate(presets)
            },
            "usage": _usage(run, cond, presets, keys),
        }
        if cond != "clean":
            block["clean_same_pages"] = _per_preset(clean[ok], presets)
            block["delta_vs_clean"] = {
                s: stats.paired_delta(clean[ok, c], m[ok, c], seed=c) for c, s in enumerate(presets)
            }
        if secondary_tag:
            m2, _ = judge_matrix(run, cond, secondary_tag, presets, keys)
            ok2 = _complete(m2)
            if ok2.any():
                block["secondary_failed_as_empty"] = {
                    "pages": int(ok2.sum()),
                    **_per_preset_block(m2[ok2], presets),
                }
        res["conditions"][cond] = block
    if compare:
        res["compare"] = _compare(
            run, presets, keys, clean, fail_clean, compare, res["conditions"].get("clean"), conditions
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "summary.json", res)
    (out_dir / "summary.md").write_text(to_markdown(res))
    if not res["conditions"].get("clean", {}).get("pages"):
        print(f"{benchmark}: no complete clean pages; charts skipped")
        return res
    try:
        from .charts import maxx_chart, rank_slope

        maxx_chart(res, out_dir / "maxx.png")
        rank_slope(res, out_dir / "ranks.png")
    except Exception as e:  # charts are a convenience; summary.json is the record
        print(f"chart skipped: {e}")
    return res


def _compare(run, presets, keys, clean, fail, compare, clean_block, conditions) -> dict:
    """A clean pair claim is confirmed only if every compare judge scored every primary clean page and also
    separates the pair, in the same direction, after its own Holm correction. A missing judge confirms
    nothing."""
    out: dict = {"judges": {}, "claims": []}
    if "clean" not in conditions:
        return out
    n_primary = int(_complete(clean).sum())
    sig = [r for r in (clean_block or {}).get("pairwise", []) if r["significant"]]
    status = {(r["a"], r["b"]): [] for r in sig}
    for name, tags in compare.items():
        tags = [tags] if isinstance(tags, str) else list(tags)
        mats = [judge_matrix(run, "clean", t, presets, keys) for t in tags]
        m = _mean_repeats([x[0] for x in mats])
        mm = {"models": sorted({x for _, d in mats for x in d["models"]})}
        tag = tags[0] if len(tags) == 1 else tags
        m[fail.any(1)] = np.nan
        ok = _complete(m, clean)
        out["judges"][name] = {"tag": tag, "pages": int(ok.sum()), "primary_pages": n_primary}
        if int(ok.sum()) < n_primary or not ok.any():
            for r in sig:
                status[(r["a"], r["b"])].append(f"not {name} (scored {int(ok.sum())}/{n_primary} pages)")
            continue
        pw = {
            (r["a"], r["b"]): r
            for r in stats.pairwise_deltas(m[ok], presets, idx=stats.boot_idx(int(ok.sum())))
        }
        out["judges"][name] |= {
            "models": mm["models"],
            "agreement_with_primary": stats.pair_agreement(clean[ok], m[ok]),
            "judge": _per_preset(m[ok], presets),
        }
        for r in sig:
            o = pw.get((r["a"], r["b"]))
            agree = bool(o and o["significant"] and np.sign(o["delta"]) == np.sign(r["delta"]))
            status[(r["a"], r["b"])].append(name if agree else f"not {name}")
    for r in sig:
        better, worse = (r["a"], r["b"]) if r["delta"] > 0 else (r["b"], r["a"])
        st = status[(r["a"], r["b"])]
        confirmed = bool(compare) and len(st) == len(compare) and all(not x.startswith("not ") for x in st)
        out["claims"].append({"better": better, "worse": worse, "confirmed": confirmed, "by": st})
    return out


def _per_preset_block(m: np.ndarray, presets: list[str]) -> dict:
    idx = stats.boot_idx(len(m)) if len(m) else None
    return {
        "judge": _per_preset(m, presets, idx),
        "pairwise": stats.pairwise_deltas(m, presets, idx=idx) if len(m) else [],
    }


def _per_preset(m: np.ndarray, presets: list[str], idx: np.ndarray | None = None) -> dict:
    if len(m) == 0:
        return {}
    idx = stats.boot_idx(len(m)) if idx is None else idx
    means = m.mean(0)
    r = stats.ranks(means)
    ri = stats.rank_interval(m, idx=idx)
    wr = stats.win_rate(m)
    return {
        s: {
            "mean": float(means[c]),
            "ci90": list(stats.bootstrap_mean(m[:, c], idx=idx)[1:]),
            "rank": int(r[c]),
            "rank_ci95": list(ri[c]),
            "win_rate": float(wr[c]),
            "p10": float(np.quantile(m[:, c], 0.1)),
        }
        for c, s in enumerate(presets)
    }


def to_markdown(res: dict) -> str:
    lines = [
        f"# {res['benchmark']}: native vs blind judge vs perturbed",
        "",
        f"Judge: `{res['judge']}` (models {res['judge_models']}, "
        f"{res['judge_repeats']} clean repeats averaged). "
        f"Pages sampled: {res['pages_sampled']}. Primary analysis drops pages with any failed parse.",
        "",
    ]
    conds = list(res["conditions"])
    head = "| preset | native (rank) | " + " | ".join(f"{c} judge (rank)" for c in conds) + " |"
    lines += [head, "|" + "---|" * (2 + len(conds))]
    for s in res["presets"]:
        nat = res.get("native", {}).get(s)
        row = [s, f"{nat['mean']:.1f} ({nat['rank']})" if nat else "n/a"]
        for c in conds:
            j = res["conditions"][c]["judge"].get(s)
            d = res["conditions"][c].get("delta_vs_clean", {}).get(s)
            cell = f"{j['mean']:.2f} ({j['rank']})" if j else "n/a"
            if d and d["n"]:
                cell += f" Δ {d['delta']:+.2f} [{d['ci90'][0]:+.2f}, {d['ci90'][1]:+.2f}]"
            row.append(cell)
        lines.append("| " + " | ".join(row) + " |")
    lines += [
        "",
        "| condition | pages | dropped (failed parse) | failed parses by preset |",
        "|---|---|---|---|",
    ]
    for c, v in res["conditions"].items():
        f = {s: n for s, n in v["failed_parses"].items() if n}
        lines.append(
            f"| {c} | {v['pages']} | {v['pages_dropped_for_failure']} | {json.dumps(f) if f else 'none'} |"
        )
    if "native_vs_judge" in res:
        a = res["native_vs_judge"]
        lines += [
            "",
            f"Native per-page mean-vs-judge pair agreement: {a['agreement']:.2f} "
            f"(90% CI {a['ci90'][0]:.2f}-{a['ci90'][1]:.2f}, {a['pairs']} pairs)"
            + (
                f"; ceiling minus native {a['ceiling_gap']['gap']:+.2f} (90% CI "
                f"{a['ceiling_gap']['ci90'][0]:+.2f} to {a['ceiling_gap']['ci90'][1]:+.2f}): {a['verdict']}."
                if "verdict" in a
                else "."
            ),
        ]
    if "judge_repeat_agreement" in res:
        a, c = res["judge_repeat_agreement"], res["judge_repeat_consistency"]
        icc = [v for v in c["icc1_by_preset"].values() if v == v]
        lines.append(
            f"Judge repeat-vs-repeat agreement (noise ceiling): {a['agreement']:.2f} "
            f"(90% CI {a['ci90'][0]:.2f}-{a['ci90'][1]:.2f}); per-preset ICC(1,1) median "
            f"{np.median(icc) if icc else float('nan'):.2f}."
        )
    lines.append("")
    for c, v in res["conditions"].items():
        sig = [
            f"{r['a']} > {r['b']}" if r["delta"] > 0 else f"{r['b']} > {r['a']}"
            for r in v["pairwise"]
            if r["significant"]
        ]
        lines.append(f"{c}: pairs separated at 95% (Holm within this condition): {', '.join(sig) or 'none'}.")
        if "secondary_failed_as_empty" in v:
            sec = v["secondary_failed_as_empty"]
            means = ", ".join(f"{s} {x['mean']:.2f} ({x['rank']})" for s, x in sec["judge"].items())
            lines.append(f"  secondary (failed parse judged as empty, {sec['pages']} pages): {means}.")
    if "compare" in res:
        lines += ["", "Other judges on clean:"]
        for name, j in res["compare"]["judges"].items():
            tag = ", ".join(j["tag"]) if isinstance(j["tag"], list) else j["tag"]
            if j["pages"] < j["primary_pages"] or "agreement_with_primary" not in j:
                lines.append(
                    f"- {name} (`{tag}`): scored {j['pages']}/{j['primary_pages']} pages; confirms nothing."
                )
            else:
                a = j["agreement_with_primary"]
                lines.append(
                    f"- {name} (`{tag}`, {j['pages']} pages): "
                    f"pair agreement with primary {a['agreement']:.2f}."
                )
        ok = [f"{c['better']} > {c['worse']}" for c in res["compare"]["claims"] if c["confirmed"]]
        bad = [f"{c['better']} > {c['worse']}" for c in res["compare"]["claims"] if not c["confirmed"]]
        lines.append(f"Clean claims confirmed by every judge: {', '.join(ok) or 'none'}.")
        lines.append(f"Disputed (do not claim): {', '.join(bad) or 'none'}.")
    return "\n".join(lines) + "\n"


def disagreements(run: Run, benchmark: str, presets: list[str], tag: str, n: int = 20) -> Path:
    """Write the n clean pages where native scorer and judge order the presets most differently, as a CSV
    for a person to fill in (who was right). Needs native scores and the primary judge on clean."""
    import csv

    keys = [p["page_key"] for p in run.pages() if p["benchmark"] == benchmark]
    nat = native_matrix(run, "clean", presets, keys)
    jm, _ = judge_matrix(run, "clean", tag, presets, keys)
    rows = []
    for i, k in enumerate(keys):
        if np.isnan(nat[i]).any() or np.isnan(jm[i]).any():
            continue
        a, b = stats._rank(-nat[i]), stats._rank(-jm[i])
        rows.append((float(np.abs(a - b).sum()), k, i))
    rows.sort(reverse=True)
    out = run.root / "reports" / benchmark / "disagreements.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page_key", "image", "rank_gap", "native", "judge", "who_was_right", "notes"])
        for gap, k, i in rows[:n]:
            w.writerow(
                [
                    k,
                    str(run.image("clean", k)),
                    gap,
                    json.dumps(dict(zip(presets, nat[i].round(1).tolist(), strict=True))),
                    json.dumps(dict(zip(presets, jm[i].tolist(), strict=True))),
                    "",
                    "",
                ]
            )
    return out


def homefield(runs: list[Path]) -> dict:
    """Builder's own preset: its native rank on its own benchmark vs its median native rank elsewhere, and
    the same for the clean judge rank. Only builders with a `home_preset` in the catalog are scored."""
    from .catalog import load_catalog

    cat = load_catalog()
    reports = {}
    for r in runs:
        for f in (r / "reports").glob("*/summary.json"):
            reports[f.parent.name] = json.loads(f.read_text())
    out = {}
    for b, rep in reports.items():
        home = cat.get(b, {}).get("home_preset")
        if not home or home not in rep["presets"]:
            continue
        row = {"preset": home}
        for kind, get in (
            ("native", lambda x: x.get("native", {})),
            ("judge", lambda x: x["conditions"].get("clean", {}).get("judge", {})),
        ):
            own = get(rep).get(home, {}).get("rank")
            away = [get(o)[home]["rank"] for ob, o in reports.items() if ob != b and home in get(o)]
            row[kind] = {"home_rank": own, "away_median_rank": float(np.median(away)) if away else None}
        out[b] = row
    return out
