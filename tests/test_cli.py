from __future__ import annotations

import json
from pathlib import Path

import pytest

from route_opt.cli import main


def test_generate_solve_compare_validate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inst = tmp_path / "inst.json"
    assert main(["generate", "--n", "12", "--type", "RC", "--seed", "1", "--out", str(inst)]) == 0
    assert inst.exists()

    sol = tmp_path / "sol.json"
    plot = tmp_path / "routes.png"
    args = ["solve", "--instance", str(inst), "--method", "ilp", "--time-limit", "5", "--workers", "1"]
    assert main([*args, "--out", str(sol), "--plot", str(plot)]) == 0
    out = capsys.readouterr().out
    assert "validator     OK" in out and "OPTIMAL" in out
    assert plot.stat().st_size > 10_000
    assert json.loads(sol.read_text())["method"] == "ilp"

    assert main(["validate", "--instance", str(inst), "--solution", str(sol)]) == 0
    assert capsys.readouterr().out.strip() == "OK"

    assert main(["solve", "--instance", str(inst), "--method", "greedy"]) == 0
    assert (
        main(
            [
                "compare",
                "--instance",
                str(inst),
                "--time-limit",
                "5",
                "--ref-time-limit",
                "1",
                "--workers",
                "1",
            ]
        )
        == 0
    )
    table = capsys.readouterr().out
    for method in ("greedy", "greedy-tonn", "ilp", "reference"):
        assert method in table


def test_validate_rejects_tampered_solution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inst = tmp_path / "inst.json"
    main(["generate", "--n", "8", "--seed", "2", "--out", str(inst)])
    sol = tmp_path / "sol.json"
    main(["solve", "--instance", str(inst), "--method", "greedy", "--out", str(sol)])
    data = json.loads(sol.read_text())
    data["routes"][0]["stops"] = data["routes"][0]["stops"][1:]  # drop a customer
    sol.write_text(json.dumps(data))
    capsys.readouterr()
    assert main(["validate", "--instance", str(inst), "--solution", str(sol)]) == 1
    assert "INVALID" in capsys.readouterr().out


def test_solve_reads_solomon_format(capsys: pytest.CaptureFixture[str]) -> None:
    path = Path(__file__).resolve().parents[1] / "data" / "demo_parcels_12_solomon.txt"
    assert (
        main(["solve", "--instance", str(path), "--method", "ilp", "--time-limit", "5", "--workers", "1"])
        == 0
    )
    assert "OPTIMAL" in capsys.readouterr().out
