"""Paired statistics over pages. Every interval resamples pages (the unit of sampling), never parses."""

import itertools

import numpy as np

B = 2000


def boot_idx(n: int, seed: int = 0, b: int = B) -> np.ndarray:
    """One page resample (b x n) shared by means, ranks and pairwise tests on the same matrix."""
    return np.random.default_rng(seed).integers(0, n, (b, n))


def bootstrap_mean(
    x: np.ndarray, seed: int = 0, b: int = B, idx: np.ndarray | None = None
) -> tuple[float, float, float]:
    if idx is not None and not np.isnan(x).any():
        means = x[idx].mean(axis=1)
        return float(x.mean()), float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return (float("nan"),) * 3
    g = np.random.default_rng(seed)
    means = x[g.integers(0, len(x), (b, len(x)))].mean(axis=1)
    return float(x.mean()), float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def paired_delta(a: np.ndarray, b_: np.ndarray, seed: int = 0) -> dict:
    """Mean of b - a over pages present in both, with 90% CI and the share of pages that got worse/better."""
    mask = ~np.isnan(a) & ~np.isnan(b_)
    d = b_[mask] - a[mask]
    mean, lo, hi = bootstrap_mean(d, seed)
    return {
        "delta": mean,
        "ci90": [lo, hi],
        "n": int(mask.sum()),
        "worse": float((d < 0).mean()) if len(d) else float("nan"),
        "better": float((d > 0).mean()) if len(d) else float("nan"),
    }


def win_rate(m: np.ndarray) -> np.ndarray:
    """m: pages x presets. Share of pages where a preset has the top score (ties count for everyone tied)."""
    top = np.nanmax(m, axis=1, keepdims=True)
    return np.nanmean((m == top).astype(float), axis=0)


def ranks(means: np.ndarray) -> np.ndarray:
    """Competition ranks: tied means share the best rank (1, 2, 2, 4)."""
    return np.array([1 + int((means > m).sum()) for m in means])


def pair_agreement(m_a: np.ndarray, m_b: np.ndarray, seed: int = 0, b: int = B) -> dict:
    """Datalab's agreement: share of preset pairs that two scoring methods put in the same order.
    m_a, m_b: pages x presets on the same pages. CI resamples pages."""
    k = m_a.shape[1]
    pairs = list(itertools.combinations(range(k), 2))

    def agree(idx):
        a, c = np.nanmean(m_a[idx], 0), np.nanmean(m_b[idx], 0)
        return np.mean([np.sign(a[i] - a[j]) == np.sign(c[i] - c[j]) for i, j in pairs])

    n = m_a.shape[0]
    full = agree(np.arange(n))
    g = np.random.default_rng(seed)
    boots = [agree(g.integers(0, n, n)) for _ in range(b)]
    return {
        "agreement": float(full),
        "ci90": [float(np.quantile(boots, 0.05)), float(np.quantile(boots, 0.95))],
        "pairs": len(pairs),
    }


def agreement_gap(
    native: np.ndarray, clean: np.ndarray, r0: np.ndarray, r1: np.ndarray, seed: int = 0, b: int = B
) -> dict:
    """Judge noise ceiling minus native-vs-judge agreement, with a paired page bootstrap (all four matrices
    on the same pages). Positive: native agrees with the judge less than the judge agrees with itself."""
    k = native.shape[1]
    pairs = list(itertools.combinations(range(k), 2))

    def agree(x, y):
        a, c = x.mean(0), y.mean(0)
        return np.mean([np.sign(a[i] - a[j]) == np.sign(c[i] - c[j]) for i, j in pairs])

    n = native.shape[0]
    g = np.random.default_rng(seed)
    gaps = []
    for _ in range(b):
        i = g.integers(0, n, n)
        gaps.append(agree(r0[i], r1[i]) - agree(native[i], clean[i]))
    gap = agree(r0, r1) - agree(native, clean)
    lo, hi = float(np.quantile(gaps, 0.05)), float(np.quantile(gaps, 0.95))
    label = (
        "below the judge noise ceiling"
        if lo > 0
        else "above the judge noise ceiling"
        if hi < 0
        else "within judge noise"
    )
    return {"gap": float(gap), "ci90": [lo, hi], "label": label}


def rank_interval(
    m: np.ndarray, seed: int = 0, b: int = B, idx: np.ndarray | None = None, level: float = 0.95
) -> list[tuple[int, int]]:
    """Rank interval at `level` (95%, the same level as the pairwise tests). m must have no NaNs."""
    if np.isnan(m).any():
        raise ValueError("rank_interval needs a complete pages x presets matrix")
    idx = boot_idx(m.shape[0], seed, b) if idx is None else idx
    rs = np.array([ranks(m[row].mean(0)) for row in idx])
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return [
        (int(np.quantile(rs[:, j], lo, method="lower")), int(np.quantile(rs[:, j], hi, method="higher")))
        for j in range(m.shape[1])
    ]


def icc1_by_preset(r0: np.ndarray, r1: np.ndarray) -> list[float]:
    """ICC(1,1) per preset column, so variance between presets does not inflate it."""
    return [icc1(r0[:, [c]], r1[:, [c]]) for c in range(r0.shape[1])]


def icc1(r0: np.ndarray, r1: np.ndarray) -> float:
    """One-way ICC(1,1) between two judge repeats over (page, preset) cells present in both."""
    mask = ~np.isnan(r0) & ~np.isnan(r1)
    x = np.stack([r0[mask], r1[mask]], 1)
    n = len(x)
    if n < 3:
        return float("nan")
    msb = 2 * ((x.mean(1) - x.mean()) ** 2).sum() / (n - 1)
    msw = ((x - x.mean(1, keepdims=True)) ** 2).sum() / n
    return float((msb - msw) / (msb + msw)) if msb + msw else float("nan")


def judge_consistency(r0: np.ndarray, r1: np.ndarray) -> dict:
    """Two judge repeats (or two judge models) on the same pages x presets."""
    mask = ~np.isnan(r0) & ~np.isnan(r1)
    a, c = r0[mask], r1[mask]
    return {
        "mean_abs_diff": float(np.abs(a - c).mean()) if len(a) else float("nan"),
        "exact": float((a == c).mean()) if len(a) else float("nan"),
        "spearman": float(np.corrcoef(_rank(a), _rank(c))[0, 1]) if len(a) > 2 else float("nan"),
        "n": int(len(a)),
    }


def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks: tied values share the mean of their positions (scores are integers 1-10)."""
    order = x.argsort(kind="stable")
    r = np.empty(len(x))
    r[order] = np.arange(len(x), dtype=float)
    for v in np.unique(x):
        r[x == v] = r[x == v].mean()
    return r


def pairwise_deltas(
    m: np.ndarray,
    presets: list[str],
    alpha: float = 0.05,
    seed: int = 0,
    b: int = B,
    idx: np.ndarray | None = None,
) -> list:
    """Paired bootstrap of the mean score difference for every preset pair, with Holm-adjusted
    significance at `alpha` within this family (one benchmark x condition x judge). Pages missing for
    either preset are dropped per pair and resampled on that pair's valid set; a complete matrix uses
    the shared resample `idx`. Two-sided p = 2 * (1 + #boots on the far side of 0) / (b + 1)."""
    rows = []
    complete = not np.isnan(m).any()
    for i, j in itertools.combinations(range(len(presets)), 2):
        d = m[:, i] - m[:, j]
        if complete and idx is not None:
            boots = d[idx].mean(1)
        else:
            d = d[~np.isnan(d)]
            if len(d) == 0:
                continue
            g = np.random.default_rng([seed, i, j])
            boots = d[g.integers(0, len(d), (b, len(d)))].mean(1)
        nb = len(boots)
        p = 2 * min((1 + (boots <= 0).sum()) / (nb + 1), (1 + (boots >= 0).sum()) / (nb + 1))
        rows.append(
            {
                "a": presets[i],
                "b": presets[j],
                "delta": float(d.mean()),
                "ci95": [float(np.quantile(boots, 0.025)), float(np.quantile(boots, 0.975))],
                "p": float(min(1.0, p)),
                "n": int(len(d)),
            }
        )
    order = sorted(range(len(rows)), key=lambda k: rows[k]["p"])
    running = 0.0
    for rank, k in enumerate(order):
        running = max(running, min(1.0, (len(rows) - rank) * rows[k]["p"]))
        rows[k]["p_holm"] = running
        rows[k]["significant"] = running < alpha
    return rows
