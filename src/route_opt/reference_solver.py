"""Independent cross-check: the same CVRPTW solved with the OR-Tools *routing library*.

The idea
--------
The routing library (``RoutingModel``) is a completely different engine from CP-SAT: a
constructive first solution (parallel cheapest insertion) followed by local search under the
guided-local-search metaheuristic. Agreement between the two engines on the same integer data is
evidence that the ILP is modelled correctly; on small instances the ILP should match it or beat
it. This is *not* the project's main method; it is a yardstick reported as a third column.

Modelling in the routing library:

* arc cost = scaled distance (the same matrix as every other method);
* ``Time`` dimension: transit ``i -> j`` is ``service_i + d_ij``; slack (waiting) is allowed;
  every customer's cumul (service start) is restricted to its window, every vehicle's start and
  end cumuls to the depot's ``[ready, due]``;
* ``Capacity`` dimension: unary demand callback, capacity ``Q`` per vehicle;
* ``num_vehicles`` vehicles, unused vehicles cost nothing.

If no first solution is found (possible on very tight instances), the search is restarted from the
greedy routes so that a solution is always returned.
"""

from __future__ import annotations

import time

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from route_opt.baseline import greedy_nearest_neighbour
from route_opt.model import Instance, Solution, make_solution


def default_reference_time_limit(n: int) -> float:
    """0.2 s per customer (10 s at 50 stops): GLS converges quickly at these sizes."""
    return round(max(2.0, 0.2 * n), 1)


def solve_reference(instance: Instance, time_limit: float | None = None) -> Solution:
    """Solve with ``RoutingModel`` + guided local search under a wall-clock time limit.

    Model building is O(n * K) variables and O(n^2) callback evaluations; the search itself is
    a time-limited local search (single-threaded).
    """
    t0 = time.perf_counter()
    time_limit = default_reference_time_limit(instance.n) if time_limit is None else time_limit
    n_nodes, fleet = instance.num_nodes, instance.num_vehicles
    d, svc, q = instance.dist_rows, instance.service, instance.demand
    ready, due, horizon = instance.ready, instance.due, instance.horizon

    manager = pywrapcp.RoutingIndexManager(n_nodes, fleet, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_cb(from_index: int, to_index: int) -> int:
        return d[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]

    def time_cb(from_index: int, to_index: int) -> int:
        i, j = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
        return svc[i] + d[i][j]  # serve i, then drive to j

    def demand_cb(from_index: int) -> int:
        return q[manager.IndexToNode(from_index)]

    dist_idx = routing.RegisterTransitCallback(distance_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(dist_idx)

    time_idx = routing.RegisterTransitCallback(time_cb)
    # slack_max = horizon (waiting allowed), capacity = horizon, start cumul not forced to zero
    routing.AddDimension(time_idx, horizon, horizon, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")
    for node in range(1, n_nodes):
        time_dim.CumulVar(manager.NodeToIndex(node)).SetRange(ready[node], due[node])
    for v in range(fleet):
        time_dim.CumulVar(routing.Start(v)).SetRange(ready[0], horizon)
        time_dim.CumulVar(routing.End(v)).SetRange(ready[0], horizon)

    demand_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        demand_idx, 0, [instance.vehicle_capacity] * fleet, True, "Capacity"
    )

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(time_limit * 1000))

    assignment = routing.SolveWithParameters(params)
    started_from = "parallel_cheapest_insertion"
    if assignment is None:
        # Fallback: start the local search from the (always feasible) greedy routes.
        greedy = greedy_nearest_neighbour(instance)
        routing.CloseModelWithParameters(params)
        initial = routing.ReadAssignmentFromRoutes(greedy.routes, True)
        assignment = routing.SolveFromAssignmentWithParameters(initial, params)
        started_from = "greedy"

    if assignment is None:
        sol = make_solution(instance, [], "reference", status="NO_SOLUTION")
        sol.feasible = False
    else:
        routes = []
        for v in range(fleet):
            idx, route = routing.Start(v), []
            while not routing.IsEnd(idx):
                node = manager.IndexToNode(idx)
                if node:
                    route.append(node)
                idx = assignment.Value(routing.NextVar(idx))
            if route:
                routes.append(route)
        sol = make_solution(instance, routes, "reference", status="HEURISTIC")
    sol.solve_time = time.perf_counter() - t0
    sol.info = {"time_limit_s": float(time_limit), "started_from": started_from}
    return sol
