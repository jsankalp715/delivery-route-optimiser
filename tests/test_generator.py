from __future__ import annotations

import itertools

import pytest

from route_opt.generator import (
    CAPACITY_LEVELS,
    DEMAND_RANGE,
    LAYOUTS,
    TW_WIDTH,
    generate_instance,
    instance_to_dict,
)
from route_opt.ilp import time_bounds
from route_opt.model import make_solution
from route_opt.validate import validate


def test_same_arguments_give_identical_instances() -> None:
    a = generate_instance(30, "RC", seed=5, tw="tight", capacity="tight")
    b = generate_instance(30, "RC", seed=5, tw="tight", capacity="tight")
    assert instance_to_dict(a) == instance_to_dict(b)
    assert (a.dist == b.dist).all()


def test_different_seeds_differ() -> None:
    a = generate_instance(30, "R", seed=1)
    b = generate_instance(30, "R", seed=2)
    assert instance_to_dict(a)["customers"] != instance_to_dict(b)["customers"]


def test_geometry_does_not_depend_on_window_regime() -> None:
    """Paired design: same seed -> same coordinates/demands for tight and loose windows."""
    a = generate_instance(25, "C", seed=3, tw="tight")
    b = generate_instance(25, "C", seed=3, tw="loose")
    assert [(c.x, c.y, c.demand) for c in a.customers] == [(c.x, c.y, c.demand) for c in b.customers]


@pytest.mark.parametrize(
    ("layout", "tw", "capacity"), list(itertools.product(LAYOUTS, TW_WIDTH, CAPACITY_LEVELS))
)
def test_reference_plan_is_feasible(layout: str, tw: str, capacity: str) -> None:
    """Feasibility by construction: the planted reference plan passes the validator."""
    for n, seed in [(5, 1), (20, 2), (50, 3), (100, 4)]:
        inst = generate_instance(n, layout, seed, tw=tw, capacity=capacity)
        plan = inst.metadata["reference_routes"]
        rep = validate(inst, make_solution(inst, plan, "planted"))
        assert rep.ok, (inst.name, rep.errors)
        assert len(plan) <= inst.num_vehicles
        time_bounds(inst)  # every customer individually servable (raises otherwise)


def test_value_ranges() -> None:
    inst = generate_instance(60, "RC", seed=11, tw="loose")
    for c in inst.customers:
        assert 0.0 <= c.x <= 100.0 and 0.0 <= c.y <= 100.0
        assert DEMAND_RANGE[0] <= c.demand <= DEMAND_RANGE[1]
        assert 0.0 <= c.ready_time <= c.due_time <= inst.depot.due_time
    assert inst.vehicle_capacity == CAPACITY_LEVELS["medium"]


def test_tight_windows_are_narrower_than_loose() -> None:
    def mean_width(tw: str) -> float:
        inst = generate_instance(50, "R", seed=9, tw=tw)
        return sum(c.due_time - c.ready_time for c in inst.customers) / inst.n / inst.depot.due_time

    assert mean_width("tight") < mean_width("loose")


def test_clustered_layout_is_more_compact_than_random() -> None:
    """Average nearest-neighbour distance is much smaller for C than for R."""

    def mean_nn(layout: str) -> float:
        d = generate_instance(60, layout, seed=4).dist[1:, 1:].astype(float)
        d[d == 0] = 1e18
        for i in range(len(d)):
            d[i, i] = 1e18
        return float(d.min(axis=1).mean())

    assert mean_nn("C") < 0.8 * mean_nn("R")


@pytest.mark.parametrize(
    "kwargs", [{"layout": "X"}, {"tw": "medium"}, {"capacity": "huge"}, {"n_customers": 0}]
)
def test_invalid_arguments_raise(kwargs: dict) -> None:
    args = {"n_customers": 10, "layout": "R", "seed": 0} | kwargs
    with pytest.raises(ValueError):
        generate_instance(**args)
