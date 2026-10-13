from __future__ import annotations

import itertools

import pytest

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.generator import generate_instance
from route_opt.model import Customer, Depot, Instance
from route_opt.validate import validate


@pytest.mark.parametrize("metric", ["distance", "time-oriented"])
def test_greedy_is_always_validator_clean(metric: str) -> None:
    for n, layout, tw, cap, seed in itertools.product(
        (5, 17, 40, 75), ("C", "R", "RC"), ("tight", "loose"), ("tight", "loose"), (1, 2)
    ):
        inst = generate_instance(n, layout, seed, tw=tw, capacity=cap)
        sol = greedy_nearest_neighbour(inst, metric=metric)
        rep = validate(inst, sol)
        assert rep.ok, (inst.name, metric, rep.errors)
        assert sol.feasible


def test_greedy_is_deterministic(small_instance: Instance) -> None:
    a = greedy_nearest_neighbour(small_instance)
    b = greedy_nearest_neighbour(small_instance)
    assert a.routes == b.routes and a.total_distance_scaled == b.total_distance_scaled


def test_greedy_on_a_line_visits_in_order(line_instance: Instance) -> None:
    sol = greedy_nearest_neighbour(line_instance)
    assert sol.routes == [[1, 2, 3]]
    assert sol.total_distance == pytest.approx(60.0)


def test_greedy_waits_for_ready_time() -> None:
    inst = Instance(
        name="wait",
        depot=Depot(0.0, 0.0, 0.0, 200.0),
        customers=[Customer(1, 10.0, 0.0, 1, 50.0, 60.0, 5.0)],
        vehicle_capacity=10,
        num_vehicles=1,
    )
    sol = greedy_nearest_neighbour(inst)
    assert sol.arrival_times == [[1000]]  # arrives at t = 10.00
    assert sol.start_times == [[5000]]  # waits until t = 50.00


def test_greedy_opens_new_vehicle_on_capacity(line_instance: Instance) -> None:
    tight = Instance(
        name="cap",
        depot=line_instance.depot,
        customers=line_instance.customers,
        vehicle_capacity=10,
        num_vehicles=3,
    )
    sol = greedy_nearest_neighbour(tight)
    assert sol.routes == [[1, 2], [3]]
    assert validate(tight, sol).ok


def test_unservable_customer_raises() -> None:
    inst = Instance(
        name="impossible",
        depot=Depot(0.0, 0.0, 0.0, 100.0),
        customers=[Customer(1, 90.0, 0.0, 1, 0.0, 10.0, 1.0)],  # 90 away, due at 10
        vehicle_capacity=10,
        num_vehicles=1,
    )
    with pytest.raises(ValueError):
        greedy_nearest_neighbour(inst)


def test_greedy_reports_fleet_overflow_as_infeasible(line_instance: Instance) -> None:
    one_truck = Instance(
        name="fleet",
        depot=line_instance.depot,
        customers=line_instance.customers,
        vehicle_capacity=5,  # one customer per vehicle -> needs 3 vehicles
        num_vehicles=2,
    )
    sol = greedy_nearest_neighbour(one_truck)
    assert not sol.feasible
    assert not validate(one_truck, sol).ok
