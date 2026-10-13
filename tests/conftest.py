from __future__ import annotations

import sys
from pathlib import Path

import pytest

from route_opt.generator import generate_instance
from route_opt.model import Customer, Depot, Instance

sys.path.insert(0, str(Path(__file__).parent))  # make tests/brute_force.py importable

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def line_instance() -> Instance:
    """Three customers on a line east of the depot; obvious optimum = one out-and-back route."""
    return Instance(
        name="line",
        depot=Depot(0.0, 0.0, 0.0, 100.0),
        customers=[
            Customer(1, 10.0, 0.0, 5, 0.0, 100.0, 1.0),
            Customer(2, 20.0, 0.0, 5, 0.0, 100.0, 1.0),
            Customer(3, 30.0, 0.0, 5, 0.0, 100.0, 1.0),
        ],
        vehicle_capacity=20,
        num_vehicles=3,
    )


@pytest.fixture
def small_instance() -> Instance:
    return generate_instance(12, "RC", seed=7, tw="tight")
