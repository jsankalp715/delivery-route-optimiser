"""Guards against drift between results/ and the README (skipped if no benchmark has been run)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from route_opt.bench import add_derived_columns, summarize, verify_solutions

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
pytestmark = pytest.mark.skipif(not (RESULTS / "benchmark.csv").exists(), reason="no benchmark results")


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return add_derived_columns(pd.read_csv(RESULTS / "benchmark.csv"))


def test_summary_json_matches_csv(df: pd.DataFrame) -> None:
    stored = json.loads((RESULTS / "summary.json").read_text())
    fresh = json.loads(json.dumps(summarize(df)))
    assert _close(stored, fresh)


def _close(a: object, b: object) -> bool:
    if isinstance(a, dict):
        assert set(a) == set(b), set(a) ^ set(b)
        return all(_close(a[k], b[k]) for k in a)
    if isinstance(a, float):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-12, nan_ok=True)
        return True
    assert a == b
    return True


def test_readme_headline_numbers_match_csv(df: pd.DataFrame) -> None:
    readme = (ROOT / "README.md").read_text()
    assert "[[" not in readme, "unfilled placeholder in README"
    overall = df["reduction_vs_baseline"].mean()
    big = df.loc[df["n"] >= 50, "reduction_vs_baseline"].mean()
    for value in (overall, big):
        assert f"{100 * value:.1f}%" in readme


def test_benchmark_invariants(df: pd.DataFrame) -> None:
    assert (df["ilp_dist"] <= df["baseline_dist"] + 1e-9).all()
    assert df["ilp_status"].isin(["OPTIMAL", "FEASIBLE"]).all()
    assert (df.loc[df["ilp_status"] == "OPTIMAL", "ilp_gap"] == 0).all()
    assert (df["ilp_lower_bound"] <= df["ilp_dist"] + 1e-6).all()


def test_stored_solutions_are_valid_and_match_csv() -> None:
    n = verify_solutions(RESULTS / "solutions.jsonl", RESULTS / "benchmark.csv")
    assert n == 4 * len(pd.read_csv(RESULTS / "benchmark.csv"))
