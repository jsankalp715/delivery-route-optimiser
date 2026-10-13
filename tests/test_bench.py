from __future__ import annotations

from pathlib import Path

import pandas as pd

from route_opt.bench import instance_specs, load_config, run_benchmark, verify_solutions


def test_micro_benchmark_end_to_end(tmp_path: Path) -> None:
    cfg = load_config(None)
    cfg.update(
        {
            "sizes": [6, 9],
            "types": ["R", "C"],
            "seeds": [1, 2],
            "phase1_processes": 2,
            "output_dir": str(tmp_path),
        }
    )
    cfg["ilp"].update({"time_limit": {6: 3, 9: 3}, "num_workers": 2})
    cfg["reference"]["time_limit_per_customer"] = 0.05
    df = run_benchmark(cfg)

    assert len(df) == len(instance_specs(cfg)) == 8
    assert set(df["tw"]) == {"tight", "loose"}  # seeds alternate regimes
    assert (df["ilp_dist"] <= df["baseline_dist"] + 1e-9).all()
    assert df["reduction_vs_baseline"].between(0, 1).all()
    csv = tmp_path / "benchmark.csv"
    assert pd.read_csv(csv).shape[0] == 8
    for name in (
        "summary.md",
        "summary.json",
        "reduction_by_size.png",
        "baseline_vs_ilp.png",
        "solve_time_vs_n.png",
    ):
        assert (tmp_path / name).exists(), name
    assert verify_solutions(tmp_path / "solutions.jsonl", csv) == 8 * 4
