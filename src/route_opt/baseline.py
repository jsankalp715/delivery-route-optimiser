"""Greedy nearest-neighbour baseline for the CVRPTW.

The idea
--------
Build routes one vehicle at a time. The vehicle starts at the depot; from its current position it
moves to the *nearest* unvisited customer that it can still feasibly serve, i.e.

* capacity: ``load + demand_j <= Q``;
* time window: arrival at ``j`` no later than ``due_j`` (arriving early is fine - it waits until
  ``ready_j``);
* return: after serving ``j`` it can still drive straight back to the depot before the horizon
  (this look-ahead guarantees that the route can always be closed, so every route is feasible).

When no unvisited customer is feasible, the vehicle returns to the depot and a new vehicle starts.
Ties are broken by customer id, so the heuristic is deterministic.

This is the textbook "nearest feasible neighbour" construction. ``metric="time-oriented"`` gives
Solomon's (1987) time-oriented nearest neighbour, which scores candidates by a blend of distance,
time gap (including waiting) and urgency; it is a stronger greedy used only as a sensitivity check.
"""

from __future__ import annotations

import time

from route_opt.model import Instance, Solution, make_solution

# Solomon (1987) time-oriented NN weights (delta1, delta2, delta3): distance, time gap, urgency.
TONN_WEIGHTS = (0.4, 0.4, 0.2)


def greedy_nearest_neighbour(instance: Instance, metric: str = "distance") -> Solution:
    """Construct a feasible solution with the nearest-feasible-neighbour heuristic.

    Args:
        instance: the CVRPTW instance.
        metric: ``"distance"`` (default; pure nearest neighbour) or ``"time-oriented"``.

    Returns:
        A :class:`Solution` with ``method="greedy"`` (or ``"greedy-tonn"``). ``feasible`` is False
        only if the greedy needs more vehicles than the fleet has.

    Raises:
        ValueError: if some customer cannot be served even by a dedicated vehicle (the instance is
            infeasible for any method).

    Complexity: every step scans all unvisited customers, O(n) per step and n steps in total,
    so O(n^2) time; O(n) extra memory on top of the O(n^2) distance matrix.
    """
    if metric not in ("distance", "time-oriented"):
        raise ValueError("metric must be 'distance' or 'time-oriented'")
    t0 = time.perf_counter()
    d, ready, due, svc = instance.dist_rows, instance.ready, instance.due, instance.service
    q, cap, horizon = instance.demand, instance.vehicle_capacity, instance.horizon
    unvisited = set(range(1, instance.n + 1))
    routes: list[list[int]] = []

    while unvisited:
        route: list[int] = []
        cur, t, load = 0, ready[0], 0  # position, service start time at cur, load so far
        while True:
            best, best_key = None, None
            depart = t + svc[cur]  # time the vehicle leaves its current node
            for j in unvisited:
                if load + q[j] > cap:  # capacity check
                    continue
                arrive = depart + d[cur][j]
                if arrive > due[j]:  # too late for j's window
                    continue
                start = max(arrive, ready[j])  # wait if early
                if start + svc[j] + d[j][0] > horizon:  # could not get home in time afterwards
                    continue
                if metric == "distance":
                    key = (d[cur][j], j)
                else:  # Solomon's time-oriented NN: distance, time gap and urgency
                    w1, w2, w3 = TONN_WEIGHTS
                    score = w1 * d[cur][j] + w2 * (start - depart) + w3 * (due[j] - arrive)
                    key = (score, j)
                if best_key is None or key < best_key:
                    best, best_key = j, key
            if best is None:
                break  # nothing feasible: close the route
            arrive = depart + d[cur][best]
            t = max(arrive, ready[best])
            load += q[best]
            cur = best
            route.append(best)
            unvisited.remove(best)
        if not route:  # even a fresh vehicle cannot serve any remaining customer
            raise ValueError(
                f"instance {instance.name} is infeasible: customers {sorted(unvisited)[:10]} "
                "cannot be served by a dedicated vehicle"
            )
        routes.append(route)

    method = "greedy" if metric == "distance" else "greedy-tonn"
    sol = make_solution(instance, routes, method, status="HEURISTIC")
    sol.solve_time = time.perf_counter() - t0
    return sol
