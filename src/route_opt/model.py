"""Problem model for the Capacitated Vehicle Routing Problem with Time Windows (CVRPTW).

The idea
--------
One depot (node 0) and ``n`` customers (nodes ``1..n``) sit in the plane. Each customer has a
demand, a service time and a time window ``[ready_time, due_time]`` in which service must *start*;
a vehicle that arrives early simply waits. A homogeneous fleet of ``num_vehicles`` vehicles, each
with capacity ``vehicle_capacity``, leaves the depot no earlier than the depot's ready time and must
be back no later than the depot's due time (the planning horizon). Every customer is served by
exactly one vehicle, exactly once. The goal is to minimise total travelled distance.

Integer scaling
---------------
CP-SAT only works with integers, so *every* method in this package (greedy, ILP, routing-library
reference, validator) works on the same integer data: Euclidean distances are multiplied by
``SCALE = 100`` and rounded to the nearest integer (two decimals of precision), and travel time is
equal to distance. Time windows and service times are scaled by the same factor. Distances are
reported back in original units (``scaled / SCALE``). Rounding moves an arc by at most 0.005 units;
because all methods share one matrix, comparisons between them are exact.

Conventions: arrays indexed by node (0 = depot). "Scaled" quantities are ``int`` in units of
``1 / SCALE``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np

SCALE = 100  # 1 original distance/time unit == 100 scaled units


def to_scaled(value: float) -> int:
    """Convert an original-unit time/distance to scaled integer units."""
    return int(round(value * SCALE))


def scaled_euclidean(x1: float, y1: float, x2: float, y2: float) -> int:
    """Euclidean distance between two points, scaled by ``SCALE`` and rounded to an integer."""
    return int(round(math.hypot(x1 - x2, y1 - y2) * SCALE))


@dataclass(frozen=True)
class Customer:
    """A delivery stop. Times are in original units; ``id`` is the node index (1..n)."""

    id: int
    x: float
    y: float
    demand: int
    ready_time: float
    due_time: float
    service_time: float


@dataclass(frozen=True)
class Depot:
    """The single depot. ``due_time`` is the planning horizon: vehicles must be back by then."""

    x: float
    y: float
    ready_time: float
    due_time: float


@dataclass
class Instance:
    """A CVRPTW instance plus cached integer matrices shared by every solver.

    Memory is O(n^2) for the distance matrix; building it is O(n^2).
    """

    name: str
    depot: Depot
    customers: list[Customer]
    vehicle_capacity: int
    num_vehicles: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for k, c in enumerate(self.customers, start=1):
            if c.id != k:
                raise ValueError(f"customer ids must be 1..n in order; got {c.id} at position {k}")
            if c.demand > self.vehicle_capacity:
                raise ValueError(f"customer {c.id} demand {c.demand} exceeds vehicle capacity")
            if c.ready_time > c.due_time:
                raise ValueError(f"customer {c.id} has an empty time window")
        if self.num_vehicles < 1:
            raise ValueError("num_vehicles must be >= 1")

    # ----------------------------------------------------------------------------- sizes
    @property
    def n(self) -> int:
        """Number of customers."""
        return len(self.customers)

    @property
    def num_nodes(self) -> int:
        """Number of nodes including the depot."""
        return len(self.customers) + 1

    # -------------------------------------------------------------------- node arrays
    @cached_property
    def coords(self) -> np.ndarray:
        """(n+1, 2) float array of coordinates, depot first."""
        pts = [(self.depot.x, self.depot.y)] + [(c.x, c.y) for c in self.customers]
        return np.asarray(pts, dtype=float)

    @cached_property
    def dist(self) -> np.ndarray:
        """(n+1, n+1) int64 matrix of scaled, rounded Euclidean distances.

        Built with :func:`scaled_euclidean` (``math.hypot``) so that every consumer, including the
        independent validator, rounds identically. O(n^2) time and memory.
        """
        pts = [(self.depot.x, self.depot.y)] + [(c.x, c.y) for c in self.customers]
        rows = [[scaled_euclidean(xa, ya, xb, yb) for (xb, yb) in pts] for (xa, ya) in pts]
        return np.asarray(rows, dtype=np.int64)

    @property
    def travel_time(self) -> np.ndarray:
        """Travel-time matrix; equal to the distance matrix (unit speed)."""
        return self.dist

    @cached_property
    def dist_rows(self) -> list[list[int]]:
        """Distance matrix as nested Python lists (fast scalar access in pure-Python loops)."""
        return self.dist.tolist()

    @cached_property
    def demand(self) -> list[int]:
        """Demand per node (depot = 0)."""
        return [0] + [c.demand for c in self.customers]

    @cached_property
    def ready(self) -> list[int]:
        """Scaled earliest service start per node (depot = depot ready time)."""
        return [to_scaled(self.depot.ready_time)] + [to_scaled(c.ready_time) for c in self.customers]

    @cached_property
    def due(self) -> list[int]:
        """Scaled latest service start per node (depot = horizon)."""
        return [to_scaled(self.depot.due_time)] + [to_scaled(c.due_time) for c in self.customers]

    @cached_property
    def service(self) -> list[int]:
        """Scaled service duration per node (depot = 0)."""
        return [0] + [to_scaled(c.service_time) for c in self.customers]

    @property
    def horizon(self) -> int:
        """Scaled depot due time: every vehicle must be back by then."""
        return self.due[0]

    @cached_property
    def total_demand(self) -> int:
        return sum(c.demand for c in self.customers)

    @cached_property
    def min_vehicles_by_capacity(self) -> int:
        """Trivial lower bound on the fleet size: ceil(total demand / capacity)."""
        return max(1, math.ceil(self.total_demand / self.vehicle_capacity))


@dataclass
class Solution:
    """A set of routes plus the schedule derived from them.

    ``routes`` are ordered customer ids per vehicle (the depot is implicit at both ends).
    Times are *scaled* integers: ``arrival_times`` is when the vehicle reaches each stop,
    ``start_times`` is when service starts (``max(arrival, ready)``; the difference is waiting),
    ``return_times`` is when each vehicle is back at the depot.
    """

    method: str
    routes: list[list[int]]
    arrival_times: list[list[int]]
    start_times: list[list[int]]
    return_times: list[int]
    total_distance_scaled: int
    feasible: bool
    status: str = "FEASIBLE"
    solve_time: float = 0.0
    lower_bound_scaled: float | None = None  # proven lower bound on distance (ILP only)
    gap: float | None = None  # relative optimality gap reported by the solver (ILP only)
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def total_distance(self) -> float:
        """Total distance in original units."""
        return self.total_distance_scaled / SCALE

    @property
    def vehicles_used(self) -> int:
        return sum(1 for r in self.routes if r)

    @property
    def lower_bound(self) -> float | None:
        return None if self.lower_bound_scaled is None else self.lower_bound_scaled / SCALE

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation (times converted back to original units)."""
        return {
            "method": self.method,
            "status": self.status,
            "feasible": self.feasible,
            "total_distance": self.total_distance,
            "vehicles_used": self.vehicles_used,
            "solve_time_s": round(self.solve_time, 3),
            "lower_bound": self.lower_bound,
            "gap": self.gap,
            "routes": [
                {
                    "stops": r,
                    "arrival": [t / SCALE for t in arr],
                    "service_start": [t / SCALE for t in st],
                    "return_to_depot": ret / SCALE,
                }
                for r, arr, st, ret in zip(
                    self.routes,
                    self.arrival_times,
                    self.start_times,
                    self.return_times,
                    strict=True,
                )
            ],
            "info": self.info,
        }


# ------------------------------------------------------------------------- route helpers
def route_distance(instance: Instance, route: list[int]) -> int:
    """Scaled length of depot -> route -> depot. O(len(route))."""
    d = instance.dist_rows
    prev, total = 0, 0
    for c in route:
        total += d[prev][c]
        prev = c
    return total + d[prev][0] if route else 0


def schedule_route(instance: Instance, route: list[int]) -> tuple[list[int], list[int], int, bool]:
    """Earliest-start schedule of one route (waiting allowed).

    Returns ``(arrivals, starts, return_time, time_feasible)``. Starting every service as early as
    possible is optimal for feasibility: any feasible schedule can be shifted earlier to this one.
    O(len(route)).
    """
    d, ready, due, svc = instance.dist_rows, instance.ready, instance.due, instance.service
    t, prev, ok = ready[0], 0, True  # t = service start at prev (depot "starts" at its ready time)
    arrivals: list[int] = []
    starts: list[int] = []
    for c in route:
        arrive = t + svc[prev] + d[prev][c]  # leave prev after its service, then drive
        start = max(arrive, ready[c])  # wait if early
        ok &= start <= due[c]
        arrivals.append(arrive)
        starts.append(start)
        t, prev = start, c
    ret = t + svc[prev] + d[prev][0]
    ok &= ret <= due[0]
    return arrivals, starts, ret, ok


def make_solution(
    instance: Instance,
    routes: list[list[int]],
    method: str,
    **kwargs: Any,
) -> Solution:
    """Build a :class:`Solution` (schedule, distance, feasibility flag) from bare routes.

    The ``feasible`` flag is the solver-side self-check; :mod:`route_opt.validate` performs an
    independent re-check. O(n).
    """
    routes = [list(r) for r in routes if r]
    arrivals, starts, returns = [], [], []
    ok = True
    for r in routes:
        a, s, ret, tw_ok = schedule_route(instance, r)
        arrivals.append(a)
        starts.append(s)
        returns.append(ret)
        ok &= tw_ok and sum(instance.demand[c] for c in r) <= instance.vehicle_capacity
    visited = sorted(c for r in routes for c in r)
    ok &= visited == list(range(1, instance.n + 1))
    ok &= len(routes) <= instance.num_vehicles
    total = sum(route_distance(instance, r) for r in routes)
    return Solution(
        method=method,
        routes=routes,
        arrival_times=arrivals,
        start_times=starts,
        return_times=returns,
        total_distance_scaled=total,
        feasible=bool(ok),
        **kwargs,
    )
