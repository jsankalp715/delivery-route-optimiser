"""Static matplotlib figures for single solutions and for the benchmark.

Colours come from a validated colour-blind-safe categorical palette (first three slots,
checked all-pairs); every multi-series chart also uses distinct marker shapes and a legend, so
identity never relies on colour alone. Text stays in neutral ink.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import itertools

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from route_opt.model import Instance, Solution

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
METHOD_COLOR = {"ilp": BLUE, "greedy": ORANGE, "reference": AQUA, "greedy-tonn": INK_2}
METHOD_LABEL = {
    "ilp": "CP-SAT ILP",
    "greedy": "Greedy nearest neighbour",
    "reference": "Routing-library reference",
    "greedy-tonn": "Time-oriented NN",
}
TYPE_STYLE = {"C": (BLUE, "o"), "R": (ORANGE, "s"), "RC": (AQUA, "^")}
TW_STYLE = {"tight": (BLUE, "o"), "loose": (ORANGE, "s")}


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_2,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "xtick.color": INK_2,
            "ytick.color": INK_2,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.frameon": False,
            "legend.fontsize": 8,
            "font.size": 9,
        }
    )


# ------------------------------------------------------------------------------ route maps
def plot_routes(
    instance: Instance,
    solutions: list[Solution],
    path: str | Path,
    label_windows: bool = True,
) -> None:
    """Draw one panel per solution (side by side, shared axes). Customers are labelled
    ``id [ready-due]`` so the time-window structure is visible."""
    _style()
    k = len(solutions)
    fig, axes = plt.subplots(1, k, figsize=(7.2 * k, 7.0), sharex=True, sharey=True, squeeze=False)
    xy = instance.coords
    for ax, sol in zip(axes[0], solutions, strict=True):
        color = METHOD_COLOR.get(sol.method, BLUE)
        for route in sol.routes:
            path_nodes = [0, *route, 0]
            for a, b in itertools.pairwise(path_nodes):
                ax.annotate(
                    "",
                    xy=xy[b],
                    xytext=xy[a],
                    arrowprops={
                        "arrowstyle": "-|>",
                        "color": color,
                        "lw": 1.2,
                        "mutation_scale": 7,
                        "shrinkA": 3,
                        "shrinkB": 3,
                    },
                )
        ax.scatter(xy[1:, 0], xy[1:, 1], s=22, color=INK_2, zorder=3, edgecolors=SURFACE, linewidths=1.0)
        ax.scatter([xy[0, 0]], [xy[0, 1]], s=90, marker="s", color=INK, zorder=4, edgecolors=SURFACE)
        ax.annotate("depot", xy[0], xytext=(6, -10), textcoords="offset points", fontsize=8, color=INK)
        if label_windows:
            for c in instance.customers:
                ax.annotate(
                    f"{c.id} [{c.ready_time:g}-{c.due_time:g}]",
                    (c.x, c.y),
                    xytext=(3, 3),
                    textcoords="offset points",
                    fontsize=5.5,
                    color=INK_2,
                )
        title = METHOD_LABEL.get(sol.method, sol.method)
        extra = f", {sol.status}" if sol.method == "ilp" else ""
        ax.set_title(
            f"{title}\ndistance {sol.total_distance:.1f} · {sol.vehicles_used} vehicles{extra}",
            loc="left",
        )
        ax.set_aspect("equal")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
    fig.suptitle(
        f"{instance.name} — labels: customer id [time window]",
        x=0.01,
        ha="left",
        fontsize=10,
        color=INK_2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------------- benchmark plots
def _jitter(n: int, width: float, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(-width, width, size=n)


def plot_reduction_by_size(df: pd.DataFrame, path: str | Path) -> None:
    """Box plot of the per-instance distance reduction for each size, points coloured by layout."""
    _style()
    rng = np.random.default_rng(0)
    sizes = sorted(df["n"].unique())
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    data = [100 * df.loc[df["n"] == n, "reduction_vs_baseline"].to_numpy() for n in sizes]
    ax.boxplot(
        data,
        positions=range(len(sizes)),
        widths=0.5,
        showfliers=False,
        medianprops={"color": INK, "linewidth": 1.5},
        boxprops={"color": INK_2, "linewidth": 1.0},
        whiskerprops={"color": INK_2, "linewidth": 1.0},
        capprops={"color": INK_2, "linewidth": 1.0},
    )
    offsets = {"C": -0.12, "R": 0.0, "RC": 0.12}
    for typ, (color, marker) in TYPE_STYLE.items():
        for i, n in enumerate(sizes):
            sub = df[(df["n"] == n) & (df["type"] == typ)]
            ax.scatter(
                i + offsets[typ] + _jitter(len(sub), 0.04, rng),
                100 * sub["reduction_vs_baseline"],
                s=26,
                color=color,
                marker=marker,
                edgecolors=SURFACE,
                linewidths=0.8,
                zorder=3,
                label=f"type {typ}" if i == 0 else None,
            )
    ax.axhline(25, color=INK_2, linestyle="--", linewidth=1)
    ax.annotate(
        "25% reference line",
        (len(sizes) - 0.5, 25),
        xytext=(0, 4),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=INK_2,
    )
    ax.set_xticks(range(len(sizes)), [f"n = {n}" for n in sizes])
    ax.set_ylabel("distance reduction vs greedy NN (%)")
    ax.set_title("ILP distance reduction per instance, by number of stops", loc="left", pad=22)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3, borderaxespad=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_baseline_vs_ilp(df: pd.DataFrame, path: str | Path) -> None:
    """Scatter of greedy distance (x) vs ILP distance (y) per instance."""
    _style()
    fig, ax = plt.subplots(figsize=(6.0, 5.6))
    hi = float(df["baseline_dist"].max()) * 1.05
    xs = np.array([0, hi])
    ax.plot(xs, xs, color=INK_2, linewidth=1, linestyle="-", label="y = x (no improvement)")
    ax.plot(xs, 0.75 * xs, color=INK_2, linewidth=1, linestyle="--", label="y = 0.75x (25% shorter)")
    for tw, (color, marker) in TW_STYLE.items():
        sub = df[df["tw"] == tw]
        ax.scatter(
            sub["baseline_dist"],
            sub["ilp_dist"],
            s=26,
            color=color,
            marker=marker,
            edgecolors=SURFACE,
            linewidths=0.8,
            label=f"{tw} windows",
            zorder=3,
        )
    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xlabel("greedy nearest-neighbour distance")
    ax.set_ylabel("ILP distance (best found within time limit)")
    ax.set_title("Per-instance distance: greedy vs ILP", loc="left")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_solve_time(df: pd.DataFrame, path: str | Path) -> None:
    """Left: ILP wall time vs n (filled = proven optimal, hollow = time limit hit).
    Right: proven optimality gap vs n. Two panels instead of a dual axis."""
    _style()
    rng = np.random.default_rng(1)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.0, 4.2))
    opt = df["ilp_status"] == "OPTIMAL"
    x = df["n"] + _jitter(len(df), 1.2, rng)
    ax1.scatter(
        x[opt],
        df.loc[opt, "ilp_time"],
        s=26,
        color=BLUE,
        marker="o",
        edgecolors=SURFACE,
        linewidths=0.8,
        label="proven optimal",
        zorder=3,
    )
    ax1.scatter(
        x[~opt],
        df.loc[~opt, "ilp_time"],
        s=26,
        facecolors="none",
        edgecolors=ORANGE,
        marker="s",
        linewidths=1.2,
        label="time limit reached (feasible)",
        zorder=3,
    )
    limits = df.groupby("n")["ilp_time_limit"].first()
    ax1.plot(limits.index, limits.to_numpy(), color=INK_2, linestyle="--", linewidth=1, label="time limit")
    ax1.set_xlabel("customers (n)")
    ax1.set_ylabel("ILP wall-clock time (s)")
    ax1.set_title("ILP solve time vs size", loc="left")
    ax1.legend(loc="upper left")
    ax2.scatter(
        x, 100 * df["ilp_gap"], s=26, color=BLUE, marker="o", edgecolors=SURFACE, linewidths=0.8, zorder=3
    )
    ax2.set_ylim(-0.5, max(1.0, 100 * float(df["ilp_gap"].max()) * 1.1))
    ax2.set_xlabel("customers (n)")
    ax2.set_ylabel("proven optimality gap at stop (%)")
    ax2.set_title("Gap between best solution and lower bound", loc="left")
    for ax in (ax1, ax2):
        ax.set_xticks(sorted(df["n"].unique()))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def median_instance(df: pd.DataFrame, n: int = 50) -> str:
    """Instance whose reduction is the median among size ``n`` (picked by rule, not by eye)."""
    sub = df[df["n"] == n].sort_values("reduction_vs_baseline").reset_index(drop=True)
    return str(sub.loc[(len(sub) - 1) // 2, "instance"])


def benchmark_plots(df: pd.DataFrame, out: str | Path) -> None:
    """Write all benchmark figures into ``out``."""
    import json

    from route_opt.bench import build_instance
    from route_opt.model import make_solution

    out = Path(out)
    plot_reduction_by_size(df, out / "reduction_by_size.png")
    plot_baseline_vs_ilp(df, out / "baseline_vs_ilp.png")
    plot_solve_time(df, out / "solve_time_vs_n.png")
    sol_file = out / "solutions.jsonl"
    if sol_file.exists() and (df["n"] == 50).any():
        name = median_instance(df, 50)
        for line in sol_file.read_text().splitlines():
            rec = json.loads(line)
            if rec["instance"] == name:
                inst = build_instance(rec["spec"])
                sols = [make_solution(inst, rec["routes"][m], m) for m in ("greedy", "ilp")]
                sols[1].status = str(df.loc[df["instance"] == name, "ilp_status"].iloc[0])
                plot_routes(inst, sols, out / "route_map_50.png")
                break
