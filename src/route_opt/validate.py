"""Independent feasibility checker for CVRPTW solutions.

The idea
--------
Never trust a solver's own bookkeeping. This module re-derives everything from the raw instance
data (coordinates, demands, windows) with its own code path - it deliberately does not call the
schedule/distance helpers in :mod:`route_opt.model` - and checks:

1. every customer is visited exactly once, and routes contain only customer ids
   (routes start/end at the depot implicitly);
2. the number of non-empty routes does not exceed the fleet size;
3. the load of every route is within the vehicle capacity;
4. the earliest-start schedule of every route meets every window ``[ready, due]`` (waiting allowed)
   and returns to the depot before the horizon;
5. the reported schedule (if any) is itself consistent: reported service starts lie inside the
   windows and respect travel + service times between consecutive stops;
6. the recomputed total distance equals the reported total distance exactly (integer units).

Complexity: O(n) per solution (plus O(n) distance evaluations from coordinates).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from route_opt.model import SCALE, Instance, Solution


@dataclass
class ValidationReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    recomputed_distance_scaled: int = 0

    def __bool__(self) -> bool:
        return self.ok


def _d(inst: Instance, a: int, b: int) -> int:
    """Scaled, rounded Euclidean distance recomputed from coordinates (node 0 = depot)."""
    pa = (inst.depot.x, inst.depot.y) if a == 0 else (inst.customers[a - 1].x, inst.customers[a - 1].y)
    pb = (inst.depot.x, inst.depot.y) if b == 0 else (inst.customers[b - 1].x, inst.customers[b - 1].y)
    return int(round(math.hypot(pa[0] - pb[0], pa[1] - pb[1]) * SCALE))


def validate(instance: Instance, solution: Solution, max_errors: int = 20) -> ValidationReport:
    """Re-check ``solution`` against ``instance``; see the module docstring for the checks."""
    errs: list[str] = []
    n = instance.n
    cust = instance.customers

    def scaled(v: float) -> int:
        return int(round(v * SCALE))

    # 1. Each customer exactly once, only valid ids.
    seen: dict[int, int] = {}
    for k, route in enumerate(solution.routes):
        for c in route:
            if not isinstance(c, int) or c < 1 or c > n:
                errs.append(f"route {k}: invalid node id {c!r} (depot must not appear inside a route)")
                continue
            seen[c] = seen.get(c, 0) + 1
    for c in range(1, n + 1):
        if seen.get(c, 0) != 1:
            errs.append(f"customer {c} visited {seen.get(c, 0)} times (expected exactly 1)")

    # 2. Fleet size.
    used = sum(1 for r in solution.routes if r)
    if used > instance.num_vehicles:
        errs.append(f"{used} routes used but fleet has only {instance.num_vehicles} vehicles")

    # 3-4. Capacity and earliest-start schedule per route; 6. distance.
    horizon = scaled(instance.depot.due_time)
    total = 0
    for k, route in enumerate(solution.routes):
        if not route or any(not (isinstance(c, int) and 1 <= c <= n) for c in route):
            continue
        load = sum(cust[c - 1].demand for c in route)
        if load > instance.vehicle_capacity:
            errs.append(f"route {k}: load {load} exceeds capacity {instance.vehicle_capacity}")
        t, prev, prev_svc = scaled(instance.depot.ready_time), 0, 0
        for c in route:
            leg = _d(instance, prev, c)
            total += leg
            arrive = t + prev_svc + leg
            cc = cust[c - 1]
            start = max(arrive, scaled(cc.ready_time))
            if start > scaled(cc.due_time):
                errs.append(
                    f"route {k}: customer {c} reached at {arrive / SCALE:.2f}, "
                    f"after its due time {cc.due_time:g}"
                )
            t, prev, prev_svc = start, c, scaled(cc.service_time)
        back = _d(instance, prev, 0)
        total += back
        if t + prev_svc + back > horizon:
            errs.append(
                f"route {k}: returns to depot at {(t + prev_svc + back) / SCALE:.2f}, "
                f"after horizon {instance.depot.due_time:g}"
            )

    # 5. The reported schedule must be a valid schedule in its own right.
    if solution.start_times:
        for k, (route, starts) in enumerate(zip(solution.routes, solution.start_times, strict=False)):
            if len(route) != len(starts):
                errs.append(f"route {k}: {len(starts)} reported start times for {len(route)} stops")
                continue
            prev, prev_start, prev_svc = 0, scaled(instance.depot.ready_time), 0
            for c, s in zip(route, starts, strict=True):
                if not (isinstance(c, int) and 1 <= c <= n):
                    break
                cc = cust[c - 1]
                if s < scaled(cc.ready_time) or s > scaled(cc.due_time):
                    errs.append(f"route {k}: reported start {s / SCALE:.2f} at customer {c} outside window")
                if s < prev_start + prev_svc + _d(instance, prev, c):
                    errs.append(f"route {k}: reported start at customer {c} ignores travel/service time")
                prev, prev_start, prev_svc = c, s, scaled(cc.service_time)

    if total != solution.total_distance_scaled:
        errs.append(
            f"reported distance {solution.total_distance_scaled / SCALE:.2f} "
            f"!= recomputed {total / SCALE:.2f}"
        )

    ok = not errs
    if solution.feasible and not ok:
        errs.insert(0, "solution claims feasible=True but fails validation")
    return ValidationReport(ok=ok, errors=errs[:max_errors], recomputed_distance_scaled=total)


def assert_valid(instance: Instance, solution: Solution) -> None:
    """Raise ``AssertionError`` listing every violation if ``solution`` is not feasible."""
    rep = validate(instance, solution)
    if not rep.ok:
        raise AssertionError(f"{solution.method} solution invalid:\n  " + "\n  ".join(rep.errors))
