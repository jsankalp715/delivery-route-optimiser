"""Command-line interface: ``route-opt {generate,solve,compare,validate,benchmark}``.

Examples::

    route-opt generate --n 50 --type RC --seed 1 --out data/inst.json
    route-opt solve --instance data/inst.json --method ilp --time-limit 60 --plot out.png
    route-opt compare --instance data/inst.json
    route-opt benchmark --config benchmarks/config.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.generator import (
    CAPACITY_LEVELS,
    LAYOUTS,
    TW_WIDTH,
    generate_instance,
    load_instance,
    save_instance,
)
from route_opt.ilp import VEHICLE_OBJECTIVES, solve_ilp
from route_opt.model import SCALE, Instance, Solution, make_solution
from route_opt.reference_solver import solve_reference
from route_opt.validate import validate

METHODS = ("greedy", "greedy-tonn", "ilp", "reference")


def _solve(inst: Instance, method: str, args: argparse.Namespace) -> Solution:
    if method == "greedy":
        return greedy_nearest_neighbour(inst)
    if method == "greedy-tonn":
        return greedy_nearest_neighbour(inst, metric="time-oriented")
    if method == "ilp":
        return solve_ilp(
            inst,
            time_limit=args.time_limit,
            num_workers=args.workers,
            vehicle_objective=args.vehicle_objective,
            warm_start=not args.no_warm_start,
            log=args.log,
        )
    if method == "reference":
        return solve_reference(inst, time_limit=args.ref_time_limit)
    raise ValueError(method)


def _describe(inst: Instance, sol: Solution, valid: bool) -> str:
    lines = [
        f"instance      {inst.name}  (n={inst.n}, Q={inst.vehicle_capacity}, fleet={inst.num_vehicles})",
        f"method        {sol.method}",
        f"status        {sol.status}" + (f"  (gap {100 * sol.gap:.2f}%)" if sol.gap is not None else ""),
        f"distance      {sol.total_distance:.2f}"
        + (f"  (proven lower bound {sol.lower_bound:.2f})" if sol.lower_bound is not None else ""),
        f"vehicles      {sol.vehicles_used}",
        f"solve time    {sol.solve_time:.2f}s",
        f"validator     {'OK' if valid else 'FAILED'}",
        "routes:",
    ]
    for k, (route, starts) in enumerate(zip(sol.routes, sol.start_times, strict=True), start=1):
        stops = " ".join(f"{c}@{s / SCALE:.0f}" for c, s in zip(route, starts, strict=True))
        load = sum(inst.demand[c] for c in route)
        lines.append(f"  #{k:<2d} load {load:>4}/{inst.vehicle_capacity}: 0 -> {stops} -> 0")
    return "\n".join(lines)


def cmd_generate(args: argparse.Namespace) -> int:
    inst = generate_instance(args.n, args.type, args.seed, tw=args.tw, capacity=args.capacity)
    save_instance(inst, args.out)
    print(
        f"wrote {args.out}: {inst.name} "
        f"(n={inst.n}, horizon={inst.depot.due_time:g}, fleet={inst.num_vehicles})"
    )
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    inst = load_instance(args.instance)
    sol = _solve(inst, args.method, args)
    rep = validate(inst, sol)
    print(_describe(inst, sol, rep.ok))
    if not rep.ok:
        print("\n".join(rep.errors), file=sys.stderr)
    if args.out:
        Path(args.out).write_text(json.dumps(sol.to_dict(), indent=1))
        print(f"solution written to {args.out}")
    if args.plot:
        from route_opt.plotting import plot_routes

        plot_routes(inst, [sol], args.plot)
        print(f"plot written to {args.plot}")
    return 0 if rep.ok else 1


def cmd_compare(args: argparse.Namespace) -> int:
    inst = load_instance(args.instance)
    sols = [_solve(inst, m, args) for m in METHODS]
    base = sols[0].total_distance
    print(f"{inst.name}: n={inst.n}, Q={inst.vehicle_capacity}, fleet={inst.num_vehicles}\n")
    header = (
        f"{'method':<12} {'distance':>10} {'vs greedy':>10} {'vehicles':>9} {'status':>10} "
        f"{'gap':>7} {'time(s)':>8} {'valid':>6}"
    )
    print(header)
    print("-" * len(header))
    ok_all = True
    for s in sols:
        ok = validate(inst, s).ok
        ok_all &= ok
        gap = f"{100 * s.gap:.1f}%" if s.gap is not None else "-"
        red = f"{-100 * (base - s.total_distance) / base:+.1f}%"
        print(
            f"{s.method:<12} {s.total_distance:>10.2f} {red:>10} {s.vehicles_used:>9} {s.status:>10} "
            f"{gap:>7} {s.solve_time:>8.2f} {'yes' if ok else 'NO':>6}"
        )
    if args.plot:
        from route_opt.plotting import plot_routes

        plot_routes(inst, [sols[0], sols[2]], args.plot)
        print(f"\nplot (greedy vs ILP) written to {args.plot}")
    return 0 if ok_all else 1


def cmd_validate(args: argparse.Namespace) -> int:
    inst = load_instance(args.instance)
    data = json.loads(Path(args.solution).read_text())
    sol = make_solution(inst, [r["stops"] for r in data["routes"]], data.get("method", "external"))
    sol.total_distance_scaled = round(float(data["total_distance"]) * SCALE)
    rep = validate(inst, sol)
    print("OK" if rep.ok else "INVALID:\n  " + "\n  ".join(rep.errors))
    return 0 if rep.ok else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    import pandas as pd

    from route_opt.bench import analyze, load_config, run_benchmark

    cfg = load_config(args.config)
    if args.analyze_only:
        out = Path(cfg["output_dir"])
        analyze(pd.read_csv(out / "benchmark.csv"), out)
    else:
        run_benchmark(cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="route-opt", description="CVRPTW delivery route optimizer")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="generate a Solomon-style instance (JSON)")
    g.add_argument("--n", type=int, default=50, help="number of customers")
    g.add_argument("--type", choices=LAYOUTS, default="R", help="C=clustered, R=random, RC=mixed")
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--tw", choices=tuple(TW_WIDTH), default="tight", help="time-window width regime")
    g.add_argument("--capacity", choices=tuple(CAPACITY_LEVELS), default="medium")
    g.add_argument("--out", required=True, help="output .json path")
    g.set_defaults(func=cmd_generate)

    def solver_options(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--instance", required=True, help=".json instance or Solomon .txt file")
        sp.add_argument(
            "--time-limit", type=float, default=None, help="ILP limit in s (default 1.2 s/customer)"
        )
        sp.add_argument("--ref-time-limit", type=float, default=None, help="reference solver limit in s")
        sp.add_argument("--workers", type=int, default=None, help="CP-SAT workers (default: all cores)")
        sp.add_argument(
            "--vehicle-objective",
            choices=VEHICLE_OBJECTIVES,
            default="none",
            help="none = distance only; secondary = distance then vehicles; primary = vehicles then distance",
        )
        sp.add_argument("--no-warm-start", action="store_true", help="do not hint the greedy solution")
        sp.add_argument("--log", action="store_true", help="print the CP-SAT search log")
        sp.add_argument("--plot", help="write a route map (.png)")

    s = sub.add_parser("solve", help="solve one instance with one method")
    solver_options(s)
    s.add_argument("--method", choices=METHODS, default="ilp")
    s.add_argument("--out", help="write the solution as JSON")
    s.set_defaults(func=cmd_solve)

    c = sub.add_parser("compare", help="run every method on one instance and print a table")
    solver_options(c)
    c.set_defaults(func=cmd_compare)

    v = sub.add_parser("validate", help="validate a solution JSON written by 'solve --out'")
    v.add_argument("--instance", required=True)
    v.add_argument("--solution", required=True)
    v.set_defaults(func=cmd_validate)

    b = sub.add_parser("benchmark", help="run the benchmark grid from a YAML config")
    b.add_argument("--config", default="benchmarks/config.yaml")
    b.add_argument("--analyze-only", action="store_true", help="only rebuild summary + plots from the CSV")
    b.set_defaults(func=cmd_benchmark)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
