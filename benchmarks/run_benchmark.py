"""Run the CVRPTW benchmark grid: greedy NN baseline vs CP-SAT ILP vs routing-library reference.

Usage:
    python benchmarks/run_benchmark.py --config benchmarks/config.yaml
    python benchmarks/run_benchmark.py --config benchmarks/config.yaml --analyze-only
    python benchmarks/run_benchmark.py --verify results/solutions.jsonl --csv results/benchmark.csv

All logic lives in :mod:`route_opt.bench` (shared with ``route-opt benchmark``).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from route_opt.bench import analyze, load_config, run_benchmark, verify_solutions


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="benchmarks/config.yaml", help="YAML grid/time-limit config")
    ap.add_argument("--analyze-only", action="store_true", help="re-create summary + plots from the CSV")
    ap.add_argument("--verify", metavar="SOLUTIONS_JSONL", help="re-validate stored solutions and exit")
    ap.add_argument("--csv", help="benchmark.csv to cross-check distances against (with --verify)")
    args = ap.parse_args()

    if args.verify:
        n = verify_solutions(args.verify, args.csv)
        print(f"verified {n} stored solutions: all feasible" + (", distances match CSV" if args.csv else ""))
        return
    cfg = load_config(args.config)
    if args.analyze_only:
        out = Path(cfg["output_dir"])
        analyze(pd.read_csv(out / "benchmark.csv"), out)
        return
    run_benchmark(cfg)


if __name__ == "__main__":
    main()
