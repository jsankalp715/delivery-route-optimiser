"""Negative tests: the validator must catch every kind of violation."""

from __future__ import annotations

import copy

import pytest

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.model import Customer, Depot, Instance, Solution, make_solution
from route_opt.validate import assert_valid, validate


@pytest.fixture
def inst() -> Instance:
    return Instance(
        name="v",
        depot=Depot(0.0, 0.0, 0.0, 100.0),
        customers=[
            Customer(1, 10.0, 0.0, 4, 0.0, 50.0, 2.0),
            Customer(2, 0.0, 10.0, 4, 0.0, 50.0, 2.0),
            Customer(3, -10.0, 0.0, 4, 30.0, 35.0, 2.0),
        ],
        vehicle_capacity=8,
        num_vehicles=2,
    )


def _sol(inst: Instance, routes: list[list[int]]) -> Solution:
    s = make_solution(inst, routes, "test")
    s.feasible = False  # we test the validator, not the self-check
    return s


def test_feasible_solution_passes(inst: Instance) -> None:
    sol = greedy_nearest_neighbour(inst)
    assert validate(inst, sol).ok
    assert_valid(inst, sol)


def test_missing_customer(inst: Instance) -> None:
    rep = validate(inst, _sol(inst, [[1, 2]]))
    assert not rep.ok and any("customer 3 visited 0 times" in e for e in rep.errors)


def test_duplicate_customer(inst: Instance) -> None:
    rep = validate(inst, _sol(inst, [[1, 2], [3, 1]]))
    assert not rep.ok and any("customer 1 visited 2 times" in e for e in rep.errors)


def test_depot_inside_route(inst: Instance) -> None:
    rep = validate(inst, _sol(inst, [[1, 0, 2], [3]]))
    assert not rep.ok and any("invalid node id 0" in e for e in rep.errors)


def test_capacity_violation(inst: Instance) -> None:
    rep = validate(inst, _sol(inst, [[1, 2, 3]]))  # load 12 > 8
    assert not rep.ok and any("exceeds capacity" in e for e in rep.errors)


def test_time_window_violation(inst: Instance) -> None:
    # Customer 3's window is [30, 35]; going 1 -> 2 -> ... makes us late? use a forced late order:
    late = Instance(
        name="late",
        depot=inst.depot,
        customers=[*inst.customers[:2], Customer(3, -10.0, 0.0, 4, 0.0, 12.0, 2.0)],
        vehicle_capacity=8,
        num_vehicles=2,
    )
    rep = validate(late, _sol(late, [[2], [1, 3]]))  # reach 3 at 10 + 2 + 20 = 32 > 12
    assert not rep.ok and any("after its due time" in e for e in rep.errors)


def test_horizon_violation() -> None:
    inst = Instance(
        name="h",
        depot=Depot(0.0, 0.0, 0.0, 25.0),
        customers=[Customer(1, 10.0, 0.0, 1, 0.0, 20.0, 10.0)],  # back at 10 + 10 + 10 = 30 > 25
        vehicle_capacity=5,
        num_vehicles=1,
    )
    rep = validate(inst, _sol(inst, [[1]]))
    assert not rep.ok and any("after horizon" in e for e in rep.errors)


def test_fleet_violation(inst: Instance) -> None:
    rep = validate(inst, _sol(inst, [[1], [2], [3]]))
    assert not rep.ok and any("fleet has only 2" in e for e in rep.errors)


def test_wrong_reported_distance(inst: Instance) -> None:
    sol = greedy_nearest_neighbour(inst)
    sol.total_distance_scaled -= 1
    rep = validate(inst, sol)
    assert not rep.ok and any("reported distance" in e for e in rep.errors)
    assert "claims feasible=True" in rep.errors[0]


def test_inconsistent_reported_schedule(inst: Instance) -> None:
    sol = copy.deepcopy(greedy_nearest_neighbour(inst))
    sol.start_times[0][0] = -100  # before the window opens and before the vehicle can arrive
    rep = validate(inst, sol)
    assert not rep.ok and any("outside window" in e for e in rep.errors)
    assert any("ignores travel/service time" in e for e in rep.errors)


def test_assert_valid_raises(inst: Instance) -> None:
    with pytest.raises(AssertionError):
        assert_valid(inst, _sol(inst, [[1, 2, 3]]))
