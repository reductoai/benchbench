"""Blog-style charts. Bars = perturbed judge score, hatched = drop from clean, dot = clean."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PALETTE = {
    "reducto": "#5B3DF5",
    "llamaparse": "#E8590C",
    "datalab": "#2F9E44",
    "extend": "#1C7ED6",
    "mistral": "#F59F00",
    "azure": "#0B7285",
    "aws": "#FF922B",
    "pulse": "#C2255C",
    "cohere": "#7048E8",
}


def color(preset: str) -> str:
    return next((c for k, c in PALETTE.items() if preset.startswith(k)), "#868E96")


def maxx_chart(res: dict, path, cond: str | None = None) -> None:
    conds = [c for c in res["conditions"] if c != "clean"]
    cond = cond or (conds[0] if conds else "clean")
    # Both values come from the same (paired) pages so the hatched "lost" area is a true paired loss.
    pert = res["conditions"][cond]["judge"]
    clean = res["conditions"][cond].get("clean_same_pages") or res["conditions"]["clean"]["judge"]
    presets = sorted(res["presets"], key=lambda s: -pert.get(s, {}).get("mean", 0))
    fig, ax = plt.subplots(figsize=(1.3 * len(presets) + 2, 4.2), dpi=200)
    for i, s in enumerate(presets):
        c, p = clean[s]["mean"], pert[s]["mean"]
        ax.bar(i, p, color=color(s), width=0.62)
        if c > p:
            ax.bar(
                i, c - p, bottom=p, color="white", edgecolor=color(s), hatch="////", width=0.62, linewidth=0
            )
        ax.text(i, p - 0.25, f"{p:.2f}", ha="center", va="top", color="white", fontsize=8, fontweight="bold")
        ax.plot([i - 0.31, i + 0.31], [c, c], color="black", linewidth=1.6)
    ax.set_xticks(range(len(presets)), [s.replace("_", " ") for s in presets], fontsize=8, rotation=20)
    lo = min(pert[s]["mean"] for s in presets)
    ax.set_ylim(max(0, lo - 1.5), 10)
    ax.set_ylabel("blind judge score (1-10)")
    ax.set_title(f"{res['benchmark']}: clean (line) vs {cond} (bar); hatched = lost", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def rank_slope(res: dict, path) -> None:
    cols = (["native"] if "native" in res else []) + list(res["conditions"])
    get = {"native": res.get("native", {})} | {c: v["judge"] for c, v in res["conditions"].items()}
    fig, ax = plt.subplots(figsize=(1.8 * len(cols) + 2, 4), dpi=200)
    for s in res["presets"]:
        ys = [get[c].get(s, {}).get("rank") for c in cols]
        if None in ys:
            continue
        ax.plot(range(len(cols)), ys, marker="o", color=color(s), linewidth=2)
        ax.text(len(cols) - 1 + 0.08, ys[-1], s.replace("_", " "), va="center", fontsize=8, color=color(s))
    ax.set_xticks(range(len(cols)), cols)
    ax.invert_yaxis()
    ax.set_ylabel("rank")
    ax.set_title(f"{res['benchmark']}: rank by scoring method", fontsize=10, loc="left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
