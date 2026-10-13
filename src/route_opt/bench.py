"""Benchmark harness: greedy nearest neighbour vs the CP-SAT ILP (vs the routing-library reference).

The idea
--------
For every instance of a ``sizes x layouts x seeds`` grid we run

1. the greedy nearest-neighbour baseline (plus Solomon's time-oriented NN as a sensitivity check);
2. the OR-Tools routing library with guided local search, as an independent reference;
3. the CP-SAT ILP with a fixed wall-clock time limit, warm-started from the greedy solution.

Every solution must pass :func:`route_opt.validate.validate`; the run aborts otherwise.

Phase 1 (steps 1-2, single-threaded) runs in a process pool. Phase 2 (the ILP) runs one instance at a
time so that CP-SAT gets every core, and rows are appended to ``_partial.jsonl`` as they finish, so
an interrupted run can be resumed. Outputs in ``output_dir``: ``benchmark.csv``, ``summary.md``,
``summary.json``, ``solutions.jsonl`` (all routes, re-checkable with ``verify_solutions``) and the
plots.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.generator import generate_instance
from route_opt.ilp import solve_ilp
from route_opt.model import Instance, Solution, make_solution
from route_opt.reference_solver import solve_reference
from route_opt.validate import validate

DEFAULT_CONFIG: dict[str, Any] = {
    "name": "benchmark",
    "sizes": [20, 30, 50, 75],
    "types": ["C", "R", "RC"],
    "seeds": [1, 2, 3, 4, 5, 6, 7, 8],
    "tw_cycle": ["tight", "loose"],
    "capacity": "medium",
    "ilp": {"time_limit": {20: 20, 30: 30, 50: 60, 75: 75}, "num_workers": 0, "vehicle_objective": "none"},
    "reference": {"time_limit_per_customer": 0.2},
    "phase1_processes": 0,
    "output_dir": "results",
}


# --------------------------------------------------------------------------------- config
def load_config(path: str | Path | None) -> dict[str, Any]:
    """Read a YAML config and fill in defaults."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy (int keys become str)
    if path is not None:
        user = yaml.safe_load(Path(path).read_text()) or {}
        for key, value in user.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    return cfg


def ilp_time_limit(cfg: dict[str, Any], n: int) -> float:
    tl = cfg["ilp"]["time_limit"]
    if isinstance(tl, dict):
        table = {int(k): float(v) for k, v in tl.items()}
        if n in table:
            return table[n]
        return float(round(1.2 * n, 1))  # same rule as the CLI default
    return float(tl)


def instance_specs(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the grid. Seed k gets time-window regime ``tw_cycle[(k - 1) % len(tw_cycle)]``."""
    cycle = cfg["tw_cycle"]
    specs = []
    for n in cfg["sizes"]:
        for layout in cfg["types"]:
            for seed in cfg["seeds"]:
                specs.append(
                    {
                        "n": int(n),
                        "layout": layout,
                        "seed": int(seed),
                        "tw": cycle[(int(seed) - 1) % len(cycle)],
                        "capacity": cfg["capacity"],
                        "tw_mode": cfg.get("tw_mode", "planted"),
                    }
                )
    return specs


def build_instance(spec: dict[str, Any]) -> Instance:
    return generate_instance(
        spec["n"],
        spec["layout"],
        spec["seed"],
        tw=spec["tw"],
        capacity=spec["capacity"],
        tw_mode=spec.get("tw_mode", "planted"),
    )


def _check(inst: Instance, sol: Solution) -> None:
    rep = validate(inst, sol)
    if not rep.ok:
        raise AssertionError(f"{inst.name}/{sol.method} failed validation: {rep.errors}")


# ---------------------------------------------------------------------------------- phases
def _phase1(args: tuple[dict[str, Any], float]) -> dict[str, Any]:
    """Greedy, time-oriented greedy and routing-library reference for one instance."""
    spec, ref_per_customer = args
    inst = build_instance(spec)
    greedy = greedy_nearest_neighbour(inst)
    tonn = greedy_nearest_neighbour(inst, metric="time-oriented")
    ref = solve_reference(inst, time_limit=max(2.0, ref_per_customer * inst.n))
    planted = make_solution(inst, inst.metadata["reference_routes"], "planted")
    for sol in (greedy, tonn, ref, planted):
        _check(inst, sol)
    return {
        "instance": inst.name,
        "n": inst.n,
        "type": spec["layout"],
        "tw": spec["tw"],
        "capacity": spec["capacity"],
        "seed": spec["seed"],
        "fleet": inst.num_vehicles,
        "horizon": inst.depot.due_time,
        "baseline_dist": greedy.total_distance,
        "baseline_veh": greedy.vehicles_used,
        "baseline_time": greedy.solve_time,
        "tonn_dist": tonn.total_distance,
        "tonn_veh": tonn.vehicles_used,
        "ref_dist": ref.total_distance,
        "ref_veh": ref.vehicles_used,
        "ref_time_limit": ref.info["time_limit_s"],
        "ref_time": ref.solve_time,
        "planted_dist": planted.total_distance,
        "_routes": {"greedy": greedy.routes, "greedy_tonn": tonn.routes, "reference": ref.routes},
    }


def _phase2(spec: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """CP-SAT ILP for one instance, with every core."""
    inst = build_instance(spec)
    tl = ilp_time_limit(cfg, inst.n)
    sol = solve_ilp(
        inst,
        time_limit=tl,
        num_workers=int(cfg["ilp"].get("num_workers") or 0) or None,
        vehicle_objective=cfg["ilp"].get("vehicle_objective", "none"),
    )
    _check(inst, sol)
    trace = sol.info.get("progress") or []
    return {
        "instance": inst.name,
        "ilp_dist": sol.total_distance,
        "ilp_veh": sol.vehicles_used,
        "ilp_status": sol.status,
        "ilp_gap": sol.gap,
        "ilp_lower_bound": sol.lower_bound,
        "ilp_time_limit": tl,
        "ilp_time": sol.solve_time,
        "ilp_time_to_best": trace[-1][0] if trace else None,
        "ilp_num_solutions": len(trace),
        "ilp_arcs_kept": sol.info["arcs_kept"],
        "ilp_arcs_full": sol.info["arcs_full"],
        "ilp_num_vars": sol.info["num_variables"],
        "ilp_num_constraints": sol.info["num_constraints"],
        "ilp_workers": sol.info["num_workers"],
        "_routes": {"ilp": sol.routes},
    }


def run_benchmark(cfg: dict[str, Any], analyze_after: bool = True) -> pd.DataFrame:
    """Run the full grid and write all outputs. Resumes from ``_partial.jsonl`` if present."""
    out = Path(cfg["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    specs = instance_specs(cfg)
    t_start = time.perf_counter()
    procs = int(cfg.get("phase1_processes") or 0) or (os.cpu_count() or 1)
    print(f"[bench] {len(specs)} instances, phase 1 on {procs} processes", flush=True)

    with ProcessPoolExecutor(max_workers=procs) as pool:
        per_cust = float(cfg["reference"]["time_limit_per_customer"])
        phase1 = list(pool.map(_phase1, [(s, per_cust) for s in specs]))
    print(f"[bench] phase 1 done in {time.perf_counter() - t_start:.0f}s", flush=True)

    partial = out / "_partial.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if partial.exists():
        for line in partial.read_text().splitlines():
            row = json.loads(line)
            done[row["instance"]] = row
        print(f"[bench] resuming: {len(done)} ILP results already in {partial}", flush=True)

    t2 = time.perf_counter()
    for k, (spec, p1) in enumerate(zip(specs, phase1, strict=True), start=1):
        if p1["instance"] in done:
            continue
        r = _phase2(spec, cfg)
        done[r["instance"]] = r
        with partial.open("a") as fh:
            fh.write(json.dumps(r) + "\n")
        red = (p1["baseline_dist"] - r["ilp_dist"]) / p1["baseline_dist"]
        elapsed = time.perf_counter() - t2
        print(
            f"[ILP {k:3d}/{len(specs)}] {r['instance']:24s} greedy {p1['baseline_dist']:8.2f} -> "
            f"ilp {r['ilp_dist']:8.2f} ({-100 * red:+.1f}%)  ref {p1['ref_dist']:8.2f}  "
            f"{r['ilp_status']:8s} gap {100 * (r['ilp_gap'] or 0):5.1f}%  {r['ilp_time']:5.1f}s  "
            f"[{elapsed / 60:.1f} min]",
            flush=True,
        )

    rows, sols = [], []
    for p1 in phase1:
        r = done[p1["instance"]]
        row = {k: v for k, v in p1.items() if not k.startswith("_")}
        row.update({k: v for k, v in r.items() if not k.startswith("_") and k != "instance"})
        rows.append(row)
        sols.append({"instance": p1["instance"], "routes": {**p1["_routes"], **r["_routes"]}})
    df = add_derived_columns(pd.DataFrame(rows))
    df.to_csv(out / "benchmark.csv", index=False, float_format="%.10g")
    with (out / "solutions.jsonl").open("w") as fh:
        for spec, s in zip(specs, sols, strict=True):
            fh.write(json.dumps({**s, "spec": spec}) + "\n")
    (out / "config_used.json").write_text(json.dumps(cfg, indent=2))
    print(
        f"[bench] wrote {out / 'benchmark.csv'} ({len(df)} rows) "
        f"in {(time.perf_counter() - t_start) / 60:.1f} min"
    )
    if analyze_after:
        analyze(df, out)
    return df


# -------------------------------------------------------------------------------- analysis
def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["reduction_vs_baseline"] = (df["baseline_dist"] - df["ilp_dist"]) / df["baseline_dist"]
    df["reduction_vs_tonn"] = (df["tonn_dist"] - df["ilp_dist"]) / df["tonn_dist"]
    df["ref_reduction_vs_baseline"] = (df["baseline_dist"] - df["ref_dist"]) / df["baseline_dist"]
    df["ilp_vs_ref"] = (df["ilp_dist"] - df["ref_dist"]) / df["ref_dist"]
    return df


def describe(values: pd.Series) -> dict[str, float]:
    """mean / median / min / max / sample std / count of a series (as plain floats)."""
    v = values.dropna().astype(float)
    return {
        "mean": float(v.mean()),
        "median": float(v.median()),
        "min": float(v.min()),
        "max": float(v.max()),
        "std": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
        "count": int(len(v)),
    }


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    """All headline statistics, computed directly from the benchmark rows."""
    col = "reduction_vs_baseline"
    big = df[df["n"] >= 50]
    summary: dict[str, Any] = {
        "instances": len(df),
        "reduction_vs_baseline": {
            "overall": describe(df[col]),
            "n_ge_50": describe(big[col]),
            "by_size": {str(k): describe(g[col]) for k, g in df.groupby("n")},
            "by_type": {str(k): describe(g[col]) for k, g in df.groupby("type")},
            "by_tw": {str(k): describe(g[col]) for k, g in df.groupby("tw")},
            "by_size_tw": {f"{n}-{tw}": describe(g[col]) for (n, tw), g in df.groupby(["n", "tw"])},
        },
        "reduction_vs_tonn": {
            "overall": describe(df["reduction_vs_tonn"]),
            "n_ge_50": describe(big["reduction_vs_tonn"]),
        },
        "ref_reduction_vs_baseline": {
            "overall": describe(df["ref_reduction_vs_baseline"]),
            "n_ge_50": describe(big["ref_reduction_vs_baseline"]),
        },
        "ilp_vs_ref": {
            "overall": describe(df["ilp_vs_ref"]),
            "by_size": {str(k): describe(g["ilp_vs_ref"]) for k, g in df.groupby("n")},
            "ilp_better_or_equal": int((df["ilp_dist"] <= df["ref_dist"] + 1e-9).sum()),
        },
        "ilp_status_by_size": {
            str(k): {str(s): int(c) for s, c in g["ilp_status"].value_counts().items()}
            for k, g in df.groupby("n")
        },
        "ilp_gap": {
            "overall": describe(df["ilp_gap"]),
            "by_size": {str(k): describe(g["ilp_gap"]) for k, g in df.groupby("n")},
            "n_ge_50": describe(big["ilp_gap"]),
        },
        "ilp_time": {str(k): describe(g["ilp_time"]) for k, g in df.groupby("n")},
        "ilp_time_limit": {str(k): float(g["ilp_time_limit"].iloc[0]) for k, g in df.groupby("n")},
        "vehicles": {m: describe(df[f"{m}_veh"]) for m in ("baseline", "tonn", "ilp", "ref")},
        "ilp_never_worse_than_baseline": bool((df["ilp_dist"] <= df["baseline_dist"] + 1e-9).all()),
    }
    return summary


def _fmt_row(label: str, d: dict[str, float], pct: bool = True) -> str:
    f = (lambda v: f"{100 * v:.1f}%") if pct else (lambda v: f"{v:.2f}")
    cells = [label, str(d["count"]), *(f(d[k]) for k in ("mean", "median", "min", "max", "std"))]
    return "| " + " | ".join(cells) + " |"


def summary_markdown(s: dict[str, Any]) -> str:
    head = "| group | instances | mean | median | min | max | std |\n|---|---:|---:|---:|---:|---:|---:|"
    r = s["reduction_vs_baseline"]
    lines = ["## Distance reduction of the ILP vs greedy nearest neighbour", "", head]
    lines.append(_fmt_row("**all**", r["overall"]))
    lines.append(_fmt_row("**n >= 50**", r["n_ge_50"]))
    lines += [_fmt_row(f"n = {k}", v) for k, v in r["by_size"].items()]
    lines += [_fmt_row(f"type {k}", v) for k, v in r["by_type"].items()]
    lines += [_fmt_row(f"{k} windows", v) for k, v in r["by_tw"].items()]
    lines += [
        _fmt_row(f"n = {k.split('-')[0]}, {k.split('-')[1]} windows", v) for k, v in r["by_size_tw"].items()
    ]
    lines += ["", "## Sensitivity and cross-checks", "", head]
    lines.append(_fmt_row("ILP vs time-oriented NN (stronger greedy)", s["reduction_vs_tonn"]["overall"]))
    lines.append(_fmt_row("ILP vs time-oriented NN, n >= 50", s["reduction_vs_tonn"]["n_ge_50"]))
    lines.append(_fmt_row("Routing-library reference vs greedy", s["ref_reduction_vs_baseline"]["overall"]))
    lines.append(_fmt_row("ILP distance relative to reference (+ = ILP longer)", s["ilp_vs_ref"]["overall"]))
    lines += [_fmt_row(f"ILP vs reference, n = {k}", v) for k, v in s["ilp_vs_ref"]["by_size"].items()]
    lines += ["", "## ILP optimality gap (proven, at the time limit)", "", head]
    lines.append(_fmt_row("all", s["ilp_gap"]["overall"]))
    lines += [_fmt_row(f"n = {k}", v) for k, v in s["ilp_gap"]["by_size"].items()]
    lines += [
        "",
        "## ILP status and solve time",
        "",
        "| n | time limit (s) | status counts | mean time (s) | max time (s) |",
        "|---:|---:|---|---:|---:|",
    ]
    for k, st in s["ilp_status_by_size"].items():
        t = s["ilp_time"][k]
        counts = ", ".join(f"{a}: {b}" for a, b in sorted(st.items()))
        lines.append(f"| {k} | {s['ilp_time_limit'][k]:g} | {counts} | {t['mean']:.1f} | {t['max']:.1f} |")
    lines += ["", "## Vehicles used", "", head]
    for m, d in s["vehicles"].items():
        lines.append(_fmt_row(m, d, pct=False))
    lines += [
        "",
        f"ILP never worse than baseline: **{s['ilp_never_worse_than_baseline']}**; "
        f"ILP <= reference on {s['ilp_vs_ref']['ilp_better_or_equal']}/{s['instances']} instances.",
    ]
    return "\n".join(lines) + "\n"


def analyze(df: pd.DataFrame, out: str | Path) -> dict[str, Any]:
    """Write summary.md / summary.json and all plots for a finished benchmark."""
    out = Path(out)
    s = summarize(df)
    (out / "summary.json").write_text(json.dumps(s, indent=2))
    (out / "summary.md").write_text(summary_markdown(s))
    try:
        from route_opt import plotting

        plotting.benchmark_plots(df, out)
    except Exception as exc:  # plots are a convenience; never lose the numbers because of them
        print(f"[bench] plotting failed: {exc!r}")
    print(summary_markdown(s))
    return s


def verify_solutions(path: str | Path, csv_path: str | Path | None = None) -> int:
    """Re-generate every instance in ``solutions.jsonl``, re-validate every stored route set and
    (optionally) check that recomputed distances match ``benchmark.csv``. Returns #solutions checked.
    """
    df = pd.read_csv(csv_path).set_index("instance") if csv_path else None
    col = {"greedy": "baseline_dist", "greedy_tonn": "tonn_dist", "reference": "ref_dist", "ilp": "ilp_dist"}
    checked = 0
    for line in Path(path).read_text().splitlines():
        rec = json.loads(line)
        inst = build_instance(rec["spec"])
        assert inst.name == rec["instance"], (inst.name, rec["instance"])
        for method, routes in rec["routes"].items():
            sol = make_solution(inst, routes, method)
            rep = validate(inst, sol)
            assert rep.ok, (inst.name, method, rep.errors)
            if df is not None:
                expected = float(df.loc[inst.name, col[method]])
                assert np.isclose(sol.total_distance, expected, atol=1e-6), (inst.name, method)
            checked += 1
    return checked
