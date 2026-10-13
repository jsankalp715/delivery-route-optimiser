"""Exact brute-force CVRPTW solver for tiny instances (n <= 8), used as ground truth in tests.

Deliberately simple and independent of the package's solvers:

1. For every subset of customers (bitmask), try *every* visiting order and keep the shortest one
   that is feasible as a single route (capacity, windows with waiting, return before horizon).
2. Combine routes with a set-partition DP over bitmasks, respecting the fleet size.

Complexity: sum_k C(n, k) k! permutations (~110k for n = 8) plus O(3^n * K) for the DP.
"""

from __future__ import annotations

import itertools
import math

from route_opt.model import SCALE, Instance

INF = float("inf")


def _dist(inst: Instance, a: int, b: int) -> int:
    pa = (inst.depot.x, inst.depot.y) if a == 0 else (inst.customers[a - 1].x, inst.customers[a - 1].y)
    pb = (inst.depot.x, inst.depot.y) if b == 0 else (inst.customers[b - 1].x, inst.customers[b - 1].y)
    return round(math.hypot(pa[0] - pb[0], pa[1] - pb[1]) * SCALE)


def _route_cost(inst: Instance, order: tuple[int, ...]) -> float:
    """Distance of depot -> order -> depot if feasible in time, else inf."""
    t = round(inst.depot.ready_time * SCALE)
    prev, prev_service, total = 0, 0, 0
    for c in order:
        cust = inst.customers[c - 1]
        leg = _dist(inst, prev, c)
        total += leg
        t = max(t + prev_service + leg, round(cust.ready_time * SCALE))
        if t > round(cust.due_time * SCALE):
            return INF
        prev, prev_service = c, round(cust.service_time * SCALE)
    leg = _dist(inst, prev, 0)
    if t + prev_service + leg > round(inst.depot.due_time * SCALE):
        return INF
    return total + leg


def brute_force_optimum(inst: Instance) -> tuple[float, list[list[int]]]:
    """Return (optimal scaled distance, optimal routes). Raises if n > 9 (too slow)."""
    n = inst.n
    if n > 9:
        raise ValueError("brute force is only meant for n <= 9")
    full = (1 << n) - 1
    best_single: dict[int, tuple[float, tuple[int, ...]]] = {}
    for mask in range(1, full + 1):
        members = [i + 1 for i in range(n) if mask >> i & 1]
        if sum(inst.customers[c - 1].demand for c in members) > inst.vehicle_capacity:
            continue
        best: tuple[float, tuple[int, ...]] = (INF, ())
        for order in itertools.permutations(members):
            cost = _route_cost(inst, order)
            if cost < best[0]:
                best = (cost, order)
        if best[0] < INF:
            best_single[mask] = best

    # dp[k][mask] = min cost to serve exactly `mask` with k routes.
    max_k = min(inst.num_vehicles, n)
    dp = [dict() for _ in range(max_k + 1)]
    dp[0][0] = (0.0, [])
    for k in range(1, max_k + 1):
        for mask, (cost, routes) in dp[k - 1].items():
            rest = full & ~mask
            if not rest:
                continue
            low = rest & -rest  # the lowest unserved customer must be in the next route
            sub = rest
            while sub:
                if sub & low and sub in best_single:
                    c2, order = best_single[sub]
                    new = mask | sub
                    cand = cost + c2
                    if cand < dp[k].get(new, (INF, None))[0]:
                        dp[k][new] = (cand, [*routes, list(order)])
                sub = (sub - 1) & rest
    best_total: tuple[float, list[list[int]]] = (INF, [])
    for k in range(1, max_k + 1):
        if full in dp[k] and dp[k][full][0] < best_total[0]:
            best_total = dp[k][full]
    return best_total
