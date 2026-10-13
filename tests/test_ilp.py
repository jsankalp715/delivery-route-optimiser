from __future__ import annotations

import pytest
from brute_force import brute_force_optimum

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.generator import generate_instance
from route_opt.ilp import build_model, default_time_limit, solve_ilp, time_bounds
from route_opt.model import Customer, Depot, Instance
from route_opt.reference_solver import solve_reference
from route_opt.validate import validate

TINY = [
    (n, layout, tw, cap, seed)
    for seed, (n, layout, tw, cap) in enumerate(
        [
            (5, "R", "tight", "tight"),
            (5, "C", "loose", "medium"),
            (6, "RC", "tight", "medium"),
            (6, "R", "loose", "tight"),
            (7, "C", "tight", "tight"),
            (7, "RC", "loose", "tight"),
            (8, "R", "tight", "tight"),
            (8, "C", "loose", "tight"),
            (8, "RC", "tight", "medium"),
        ],
        start=1,
    )
]


@pytest.mark.parametrize(("n", "layout", "tw", "cap", "seed"), TINY)
def test_ilp_matches_brute_force_optimum(n: int, layout: str, tw: str, cap: str, seed: int) -> None:
    inst = generate_instance(n, layout, seed, tw=tw, capacity=cap)
    opt, _ = brute_force_optimum(inst)
    sol = solve_ilp(inst, time_limit=20, num_workers=2)
    assert validate(inst, sol).ok
    assert sol.status == "OPTIMAL"
    assert sol.total_distance_scaled == opt
    assert sol.gap == 0.0
    assert sol.lower_bound_scaled == pytest.approx(opt)


@pytest.mark.parametrize(("n", "layout", "tw", "cap", "seed"), TINY[:4])
def test_arc_pruning_and_warm_start_do_not_change_the_optimum(
    n: int, layout: str, tw: str, cap: str, seed: int
) -> None:
    inst = generate_instance(n, layout, seed, tw=tw, capacity=cap)
    a = solve_ilp(inst, time_limit=20, num_workers=2)
    b = solve_ilp(inst, time_limit=20, num_workers=2, prune_arcs=False, warm_start=False)
    assert a.status == b.status == "OPTIMAL"
    assert a.total_distance_scaled == b.total_distance_scaled


@pytest.mark.parametrize(("n", "layout", "seed"), [(15, "R", 1), (20, "C", 2), (25, "RC", 3), (30, "R", 4)])
@pytest.mark.parametrize("tw", ["tight", "loose"])
def test_ilp_never_worse_than_greedy(n: int, layout: str, seed: int, tw: str) -> None:
    inst = generate_instance(n, layout, seed, tw=tw)
    greedy = greedy_nearest_neighbour(inst)
    sol = solve_ilp(inst, time_limit=3, num_workers=2)
    assert validate(inst, sol).ok
    assert sol.total_distance_scaled <= greedy.total_distance_scaled
    assert sol.status in ("OPTIMAL", "FEASIBLE")
    assert sol.lower_bound_scaled <= sol.total_distance_scaled


def test_tiny_time_limit_still_returns_a_feasible_solution_no_worse_than_greedy() -> None:
    inst = generate_instance(40, "R", 5, tw="loose")
    greedy = greedy_nearest_neighbour(inst)
    sol = solve_ilp(inst, time_limit=0.01, num_workers=1)
    assert validate(inst, sol).ok
    assert sol.total_distance_scaled <= greedy.total_distance_scaled


def test_ilp_on_obvious_instance(line_instance: Instance) -> None:
    sol = solve_ilp(line_instance, time_limit=5, num_workers=1)
    assert sol.routes == [[1, 2, 3]] and sol.status == "OPTIMAL"
    assert sol.total_distance == pytest.approx(60.0)


def test_vehicle_objectives() -> None:
    inst = generate_instance(8, "RC", 3, tw="loose", capacity="tight")
    plain = solve_ilp(inst, time_limit=20, num_workers=2)
    secondary = solve_ilp(inst, time_limit=20, num_workers=2, vehicle_objective="secondary")
    primary = solve_ilp(inst, time_limit=20, num_workers=2, vehicle_objective="primary")
    for s in (plain, secondary, primary):
        assert validate(inst, s).ok and s.status == "OPTIMAL"
    # Distance-first objectives agree on distance; the tie-break can only reduce vehicles.
    assert secondary.total_distance_scaled == plain.total_distance_scaled
    assert secondary.vehicles_used <= plain.vehicles_used
    # Vehicles-first: never more vehicles, and possibly a longer distance.
    assert primary.vehicles_used <= plain.vehicles_used
    assert primary.total_distance_scaled >= plain.total_distance_scaled
    assert primary.vehicles_used >= inst.min_vehicles_by_capacity


def test_invalid_vehicle_objective() -> None:
    with pytest.raises(ValueError):
        build_model(generate_instance(5, "R", 1), vehicle_objective="cheapest")


def test_model_size_is_quadratic_and_pruning_removes_arcs() -> None:
    inst = generate_instance(30, "R", 2, tw="tight")
    full = build_model(inst, prune_arcs=False)
    pruned = build_model(inst, prune_arcs=True)
    assert len(full.x) == inst.num_nodes * (inst.num_nodes - 1)
    assert len(pruned.x) < len(full.x)
    assert len(pruned.t) == len(pruned.u) == inst.n


def test_time_bounds_are_valid(small_instance: Instance) -> None:
    earliest, latest = time_bounds(small_instance)
    assert all(e <= lt for e, lt in zip(earliest, latest, strict=True))
    greedy = greedy_nearest_neighbour(small_instance)
    for route, starts in zip(greedy.routes, greedy.start_times, strict=True):
        for c, s in zip(route, starts, strict=True):
            assert earliest[c] <= s <= latest[c]


def test_unservable_customer_is_reported() -> None:
    inst = Instance(
        name="impossible",
        depot=Depot(0.0, 0.0, 0.0, 100.0),
        customers=[Customer(1, 90.0, 0.0, 1, 0.0, 10.0, 1.0)],
        vehicle_capacity=10,
        num_vehicles=1,
    )
    with pytest.raises(ValueError):
        time_bounds(inst)


def test_default_time_limit_is_60s_at_50_stops() -> None:
    assert default_time_limit(50) == 60.0
    assert default_time_limit(100) == 120.0


@pytest.mark.parametrize(("n", "layout", "tw", "cap", "seed"), TINY[::3])
def test_reference_solver_agrees_on_tiny_instances(n: int, layout: str, tw: str, cap: str, seed: int) -> None:
    inst = generate_instance(n, layout, seed, tw=tw, capacity=cap)
    ref = solve_reference(inst, time_limit=1)
    ilp = solve_ilp(inst, time_limit=20, num_workers=2)
    assert validate(inst, ref).ok
    assert ilp.total_distance_scaled <= ref.total_distance_scaled
