"""CVRPTW as an integer linear program, solved with OR-Tools CP-SAT.

The idea
--------
Classic two-index arc formulation (the exact maths is in ``docs/formulation.md``):

* ``x[i, j]`` - binary, 1 if some vehicle drives directly from node ``i`` to node ``j``;
* ``t[i]``    - integer service-start time at customer ``i`` (domain = its time window);
* ``u[i]``    - integer load delivered so far when leaving customer ``i`` (domain ``[q_i, Q]``).

Constraints:

1. **Routes** - ``AddMultipleCircuit`` on the arc literals: every customer gets exactly one
   incoming and one outgoing arc, and every cycle must pass through the depot (node 0). This
   is the degree constraints plus subtour elimination in one global constraint, and CP-SAT adds
   its linear relaxation and subtour/capacity cuts to the LP automatically.
2. **Time windows** - ``x[i, j] => t[j] >= t[i] + s_i + d_ij`` written with ``OnlyEnforceIf``
   (reified), so no big-M constant is needed. Waiting is implicit because the inequality allows
   ``t[j]`` to be later than the arrival.
3. **Capacity** - MTZ-style load propagation ``x[i, j] => u[j] >= u[i] + q_j``. Together with
   ``u[i] <= Q`` this caps the load of every route.
4. **Fleet** - ``ceil(sum q / Q) <= sum_j x[0, j] <= K``.

Arcs to/from the depot need no extra constraints: the domains of ``t`` and ``u`` already encode
"reachable from the depot in time", "can get back before the horizon" and "load starts at q_i".

Objective: minimise ``sum d_ij x[i, j]`` (optionally with vehicles as a lexicographic secondary or
primary term).

Tuning that keeps the model exact:

* **Arc pruning** - an arc ``i -> j`` is dropped when ``q_i + q_j > Q`` or when even leaving ``i``
  at its earliest possible time reaches ``j`` after its latest feasible start. Earliest/latest
  bounds use shortest paths from/to the depot, so they stay valid even if integer rounding breaks
  the triangle inequality. Only provably infeasible arcs are removed.
* **Tight domains** - ``t[i]`` lives in ``[E_i, L_i]`` with
  ``E_i = max(ready_i, depot_ready + sp(0, i))`` and ``L_i = min(due_i, H - s_i - sp(i, 0))``.
* **Warm start** - the greedy solution is passed with ``AddHint`` (every variable is hinted, so
  CP-SAT starts from a complete feasible solution) *and* the objective is bounded by the greedy
  objective, so the solver can never return anything worse than the baseline. If it finds no
  solution at all in the time limit, the greedy solution is returned unchanged (status
  ``FALLBACK_*``).
* No vehicle-index symmetry: vehicles are not indexed, so there is nothing to break.

Size: with ``A <= n(n+1)`` surviving arcs the model has ``A`` Booleans + ``2n`` integers, one
routes constraint over ``A`` literals and at most ``2 n (n - 1)`` enforced linear constraints, i.e.
O(n^2) variables, constraints and memory. Solving is NP-hard, hence the time limit; the result is
"the best solution found within the time limit" together with CP-SAT's proven lower bound and gap.
"""

from __future__ import annotations

import itertools
import math
import os
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from ortools.sat.python import cp_model

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.model import SCALE, Instance, Solution, make_solution

VEHICLE_OBJECTIVES = ("none", "secondary", "primary")


@dataclass
class IlpModel:
    """Handles to a built CP-SAT model (exposed for tests and introspection)."""

    model: cp_model.CpModel
    x: dict[tuple[int, int], cp_model.IntVar]
    t: dict[int, cp_model.IntVar]
    u: dict[int, cp_model.IntVar]
    vehicles: cp_model.IntVar
    distance: cp_model.LinearExpr
    objective: cp_model.LinearExpr
    earliest: list[int]
    latest: list[int]
    num_arcs_full: int


# Full-model CP-SAT workers, in priority order (CP-SAT schedules the first ``num_full_subsolvers``).
# ``max_lp`` (linearization level 2) adds CP-SAT's routing cuts to the LP and is what produces a
# strong lower bound; ``default_lp`` is the main tree search. The remaining threads run LNS.
TUNED_SUBSOLVERS = ["default_lp", "max_lp", "no_lp", "quick_restart", "reduced_costs", "pseudo_costs"]


def portfolio_params(workers: int) -> dict[str, Any]:
    """CP-SAT portfolio used with >= 4 workers: half full-model workers, half LNS.

    Calibrated on a 50-stop instance (see README "Design decisions"): versus CP-SAT's default
    portfolio, the proven lower bound rose from 494 to 742 (reported gap 36% -> 5%) and tight
    instances finished with a proof of optimality instead of hitting the time limit.
    """
    if workers < 4:
        return {}  # too few threads to split; keep CP-SAT's default
    return {"subsolvers": TUNED_SUBSOLVERS, "num_full_subsolvers": max(2, workers // 2)}


def default_time_limit(n: int) -> float:
    """1.2 s per customer: 60 s for 50 stops, scaling linearly for larger instances."""
    return round(1.2 * n, 1)


def _shortest_from_depot(d: np.ndarray) -> np.ndarray:
    """Shortest-path lengths from node 0 (Bellman-Ford style, vectorised). O(n^2) per pass."""
    sp = d[0].astype(np.int64).copy()
    while True:
        new = np.minimum(sp, (sp[:, None] + d).min(axis=0))
        if np.array_equal(new, sp):
            return sp
        sp = new


def time_bounds(instance: Instance) -> tuple[list[int], list[int]]:
    """Earliest/latest feasible service-start times E_i, L_i (scaled) for every node.

    E_i = max(ready_i, depot_ready + sp(0, i)); L_i = min(due_i, H - s_i - sp(i, 0)).
    Raises ``ValueError`` if a customer can never be served (E_i > L_i).
    """
    d = instance.dist
    sp_out = _shortest_from_depot(d)  # depot -> i
    sp_in = _shortest_from_depot(d.T)  # i -> depot
    e0, horizon = instance.ready[0], instance.horizon
    earliest = [e0] + [max(instance.ready[i], e0 + int(sp_out[i])) for i in range(1, instance.num_nodes)]
    latest = [horizon] + [
        min(instance.due[i], horizon - instance.service[i] - int(sp_in[i]))
        for i in range(1, instance.num_nodes)
    ]
    bad = [i for i in range(1, instance.num_nodes) if earliest[i] > latest[i]]
    if bad:
        raise ValueError(f"customers {bad[:10]} cannot be served by any vehicle (infeasible instance)")
    return earliest, latest


def build_model(
    instance: Instance,
    hint: Solution | None = None,
    vehicle_objective: str = "none",
    prune_arcs: bool = True,
) -> IlpModel:
    """Build the CP-SAT model. See the module docstring for the formulation.

    Complexity: O(n^2) time and memory (one pass over all ordered pairs of nodes).
    """
    if vehicle_objective not in VEHICLE_OBJECTIVES:
        raise ValueError(f"vehicle_objective must be one of {VEHICLE_OBJECTIVES}")
    nodes = range(instance.num_nodes)
    d, q, s = instance.dist_rows, instance.demand, instance.service
    cap, fleet = instance.vehicle_capacity, instance.num_vehicles
    earliest, latest = time_bounds(instance)
    m = cp_model.CpModel()

    # ---- Decision variables -----------------------------------------------------------
    # t[i]: service-start time at customer i, restricted to its (tightened) window [E_i, L_i].
    t = {i: m.new_int_var(earliest[i], latest[i], f"t_{i}") for i in nodes if i > 0}
    # u[i]: cumulative load after serving i; at least its own demand, at most the capacity.
    u = {i: m.new_int_var(q[i], cap, f"u_{i}") for i in nodes if i > 0}

    # x[i, j]: arc literals, created only for arcs that can appear in some feasible solution.
    hint_arcs = _arcs_of(hint) if hint is not None else set()
    x: dict[tuple[int, int], cp_model.IntVar] = {}
    for i in nodes:
        for j in nodes:
            if i == j:
                continue
            if prune_arcs and i > 0 and j > 0 and (i, j) not in hint_arcs:
                if q[i] + q[j] > cap:  # both on one route would overload the vehicle
                    continue
                if earliest[i] + s[i] + d[i][j] > latest[j]:  # even leaving i ASAP is too late for j
                    continue
            x[i, j] = m.new_bool_var(f"x_{i}_{j}")

    # ---- (1) Routes: degree-1 at customers, all cycles through the depot ------------------
    # Node 0 is the depot of add_multiple_circuit; customers have no self-loop literal, so each
    # must be visited exactly once.
    m.add_multiple_circuit([(i, j, lit) for (i, j), lit in x.items()])

    # ---- (2) Time windows, big-M free: x[i,j] => t_j >= t_i + s_i + d_ij -------------------
    # (Depot arcs are covered by the domains: E_j already includes the drive from the depot and
    #  L_i already includes the service at i plus the drive home before the horizon.)
    for (i, j), lit in x.items():
        if i > 0 and j > 0:
            m.add(t[j] >= t[i] + s[i] + d[i][j]).only_enforce_if(lit)

    # ---- (3) Capacity, MTZ-style: x[i,j] => u_j >= u_i + q_j ------------------------------
    # (From the depot, u_j >= q_j is the domain lower bound.) Loads only grow along a route and
    # are capped by Q through the domain, so every route respects the capacity.
    for (i, j), lit in x.items():
        if i > 0 and j > 0:
            m.add(u[j] >= u[i] + q[j]).only_enforce_if(lit)

    # ---- (4) Fleet size: one depot departure per vehicle used ------------------------------
    vehicles = m.new_int_var(min(instance.min_vehicles_by_capacity, fleet), fleet, "vehicles")
    m.add(vehicles == sum(x[0, j] for j in nodes if j > 0 and (0, j) in x))

    # ---- Objective -------------------------------------------------------------------------
    distance = cp_model.LinearExpr.weighted_sum(list(x.values()), [d[i][j] for (i, j) in x])
    if vehicle_objective == "none":
        objective = distance
    elif vehicle_objective == "secondary":
        # Distance first, then fewest vehicles: vehicles <= K < K + 1, so the multiplier
        # makes the order exactly lexicographic.
        objective = (fleet + 1) * distance + vehicles
    else:
        # Fewest vehicles first, then distance: multiplier > any feasible total distance.
        dist_ub = sum(max(d[i][j] for j in nodes if j != i) for i in nodes if i > 0)
        dist_ub += fleet * max(d[0][j] for j in nodes if j > 0)
        objective = (dist_ub + 1) * vehicles + distance
    m.minimize(objective)

    # ---- Warm start --------------------------------------------------------------------------
    if hint is not None:
        _add_hint(m, instance, hint, x, t, u, vehicles)
        if hint.feasible:
            # Cut-off: never accept anything worse than the baseline.
            hint_obj = _objective_value(hint, vehicle_objective, instance)
            m.add(objective <= hint_obj)

    return IlpModel(
        model=m,
        x=x,
        t=t,
        u=u,
        vehicles=vehicles,
        distance=distance,
        objective=objective,
        earliest=earliest,
        latest=latest,
        num_arcs_full=instance.num_nodes * (instance.num_nodes - 1),
    )


def _arcs_of(sol: Solution) -> set[tuple[int, int]]:
    arcs = set()
    for r in sol.routes:
        if r:
            path = [0, *r, 0]
            arcs.update(itertools.pairwise(path))
    return arcs


def _objective_value(sol: Solution, vehicle_objective: str, instance: Instance) -> int:
    dist, veh = sol.total_distance_scaled, sol.vehicles_used
    if vehicle_objective == "none":
        return dist
    if vehicle_objective == "secondary":
        return (instance.num_vehicles + 1) * dist + veh
    d, nodes = instance.dist_rows, range(instance.num_nodes)
    dist_ub = sum(max(d[i][j] for j in nodes if j != i) for i in nodes if i > 0)
    dist_ub += instance.num_vehicles * max(d[0][j] for j in nodes if j > 0)
    return (dist_ub + 1) * veh + dist


def _add_hint(
    m: cp_model.CpModel,
    instance: Instance,
    hint: Solution,
    x: dict[tuple[int, int], cp_model.IntVar],
    t: dict[int, cp_model.IntVar],
    u: dict[int, cp_model.IntVar],
    vehicles: cp_model.IntVar,
) -> None:
    """Hint *every* variable so CP-SAT starts from a complete feasible solution."""
    used = _arcs_of(hint)
    for arc, lit in x.items():
        m.add_hint(lit, arc in used)
    for route, starts in zip(hint.routes, hint.start_times, strict=True):
        load = 0
        for c, st in zip(route, starts, strict=True):
            load += instance.demand[c]
            m.add_hint(t[c], st)
            m.add_hint(u[c], load)
    m.add_hint(vehicles, hint.vehicles_used)


class _Progress(cp_model.CpSolverSolutionCallback):
    """Records (wall time, objective) for every improving solution."""

    def __init__(self) -> None:
        super().__init__()
        self.trace: list[tuple[float, float]] = []

    def on_solution_callback(self) -> None:
        self.trace.append((round(self.wall_time, 3), self.objective_value))


def solve_ilp(
    instance: Instance,
    time_limit: float | None = None,
    num_workers: int | None = None,
    vehicle_objective: str = "none",
    warm_start: bool = True,
    hint: Solution | None = None,
    seed: int = 0,
    log: bool = False,
    prune_arcs: bool = True,
    sat_params: dict[str, Any] | None = None,
) -> Solution:
    """Solve the CVRPTW ILP with CP-SAT and return the best solution found.

    Args:
        instance: the instance.
        time_limit: wall-clock limit in seconds (default :func:`default_time_limit`).
        num_workers: CP-SAT search workers (default: all cores).
        vehicle_objective: ``"none"`` (pure distance), ``"secondary"`` (distance, then vehicles)
            or ``"primary"`` (vehicles, then distance).
        warm_start: hint the greedy solution and bound the objective by it.
        hint: custom warm-start solution (default: the greedy nearest-neighbour solution).
        seed: CP-SAT random seed (multi-threaded search is still not fully deterministic).
        log: print CP-SAT's search log.
        prune_arcs: drop provably infeasible arcs before solving (exact).
        sat_params: extra ``SatParameters`` fields, e.g. ``{"num_full_subsolvers": 2}``;
            applied on top of :func:`portfolio_params`.

    Returns:
        A :class:`Solution` with ``status`` OPTIMAL / FEASIBLE (or FALLBACK_* if CP-SAT found
        nothing and the warm start was returned), the proven lower bound and the relative gap.
    """
    t0 = time.perf_counter()
    time_limit = default_time_limit(instance.n) if time_limit is None else time_limit
    workers = num_workers or os.cpu_count() or 1
    if warm_start and hint is None:
        hint = greedy_nearest_neighbour(instance)
    built = build_model(
        instance,
        hint=hint if warm_start else None,
        vehicle_objective=vehicle_objective,
        prune_arcs=prune_arcs,
    )
    build_time = time.perf_counter() - t0

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = int(workers)
    solver.parameters.random_seed = int(seed)
    solver.parameters.log_search_progress = bool(log)
    for key, value in {**portfolio_params(workers), **(sat_params or {})}.items():
        field = getattr(solver.parameters, key)
        if isinstance(value, list | tuple):  # repeated field, e.g. ignore_subsolvers
            field.extend(value)
        else:
            setattr(solver.parameters, key, value)
    progress = _Progress()
    status = solver.solve(built.model, progress)
    status_name = solver.status_name(status)

    proto = built.model.proto
    info: dict[str, Any] = {
        "time_limit_s": float(time_limit),
        "num_workers": int(workers),
        "vehicle_objective": vehicle_objective,
        "arcs_kept": len(built.x),
        "arcs_full": built.num_arcs_full,
        "num_variables": len(proto.variables),
        "num_constraints": len(proto.constraints),
        "build_time_s": round(build_time, 3),
        "progress": progress.trace,
        "warm_start": warm_start,
    }

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        routes = _extract_routes(solver, built, instance.n)
        obj, bound = solver.objective_value, solver.best_objective_bound
        gap = 0.0 if status == cp_model.OPTIMAL else max(0.0, (obj - bound) / max(1.0, abs(obj)))
        sol = make_solution(instance, routes, "ilp", status=status_name, gap=gap, info=info)
        sol.lower_bound_scaled = _distance_lower_bound(bound, vehicle_objective, instance)
        info["objective"], info["objective_bound"] = obj, bound
    elif hint is not None:
        # CP-SAT found nothing better in time: return the baseline itself (never worse).
        sol = make_solution(instance, hint.routes, "ilp", status=f"FALLBACK_{status_name}", info=info)
    else:
        sol = make_solution(instance, [], "ilp", status=status_name, info=info)
        sol.feasible = False
    sol.solve_time = time.perf_counter() - t0
    info["solver_wall_time_s"] = round(solver.wall_time, 3)
    return sol


def _distance_lower_bound(bound: float, vehicle_objective: str, instance: Instance) -> float | None:
    """Translate CP-SAT's objective bound into a lower bound on total (scaled) distance."""
    if vehicle_objective == "none":
        return float(bound)
    if vehicle_objective == "secondary":
        k = instance.num_vehicles
        return max(0.0, math.ceil((bound - k) / (k + 1)))
    return None  # vehicles-first objective: the bound is not a distance bound


def _extract_routes(solver: cp_model.CpSolver, built: IlpModel, n: int) -> list[list[int]]:
    """Follow successor arcs from the depot to recover ordered routes. O(A)."""
    succ: dict[int, int] = {}
    starts: list[int] = []
    for (i, j), lit in built.x.items():
        if solver.boolean_value(lit):
            if i == 0:
                starts.append(j)
            else:
                succ[i] = j
    routes = []
    for first in sorted(starts):
        route, cur = [], first
        while cur != 0 and len(route) <= n:
            route.append(cur)
            cur = succ[cur]
        routes.append(route)
    return routes


def scaled_to_units(value: float | None) -> float | None:
    return None if value is None else value / SCALE
