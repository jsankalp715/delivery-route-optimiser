"""Seeded, reproducible Solomon-style CVRPTW instance generator, plus instance I/O.

The idea
--------
Coordinates live in a 100 x 100 square with the depot in the centre, like Solomon's benchmark:

* ``R``  - customers uniformly at random;
* ``C``  - customers in Gaussian clusters around a few random centres;
* ``RC`` - half clustered, half random.

Feasibility is guaranteed *by construction*, the same trick Solomon used for his C-class
instances: we first build a reasonable **reference plan** (sweep the customers by polar angle,
cut a new route whenever capacity would be exceeded, then order each route with a quick
nearest-neighbour + 2-opt pass), simulate it to get an arrival time ``a_i`` at every customer, and
only then draw customer ``i``'s time window so that it *contains* ``a_i`` (random width, random
offset). The reference plan therefore satisfies every window, the capacity, and the horizon, and the
fleet always has at least as many vehicles as the reference plan uses. The reference plan is stored
in ``instance.metadata["reference_routes"]`` and checked before the instance is returned.

Knobs: ``tw`` = ``tight`` / ``loose`` window widths (as a fraction of the horizon) and
``capacity`` = ``tight`` / ``medium`` / ``loose`` vehicle capacity.

Generation is O(n^2) (distance matrix) and fully determined by ``(seed, n, layout)``; the time
windows additionally depend on ``tw`` and ``capacity``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from route_opt.model import SCALE, Customer, Depot, Instance, make_solution, route_distance

LAYOUTS = ("C", "R", "RC")
GRID = 100.0  # side of the square service area
DEPOT_XY = (50.0, 50.0)
DEMAND_RANGE = (5, 30)  # integer demands, inclusive (mean 17.5)
SERVICE_TIME = 10  # minutes per stop, same for every customer (Solomon R/RC use 10)
CAPACITY_LEVELS = {"tight": 100, "medium": 150, "loose": 250}  # ~5.7 / ~8.6 / ~14 stops per route
TW_WIDTH = {"tight": (0.05, 0.15), "loose": (0.25, 0.50)}  # window width as a fraction of horizon
HORIZON_SLACK = 1.25  # horizon = longest reference route x slack
CLUSTER_STD = 5.0


# ----------------------------------------------------------------------------- geometry
def _coordinates(rng: np.random.Generator, n: int, layout: str) -> np.ndarray:
    """Return an (n, 2) array of customer coordinates rounded to 0.1."""
    if layout == "R":
        pts = rng.uniform(0.0, GRID, size=(n, 2))
    elif layout == "C":
        pts = _clustered(rng, n)
    elif layout == "RC":
        n_c = n // 2
        pts = np.vstack([_clustered(rng, n_c), rng.uniform(0.0, GRID, size=(n - n_c, 2))])
        pts = pts[rng.permutation(n)]  # interleave so ids carry no layout information
    else:
        raise ValueError(f"layout must be one of {LAYOUTS}, got {layout!r}")
    return np.round(np.clip(pts, 0.0, GRID), 1)


def _clustered(rng: np.random.Generator, n: int) -> np.ndarray:
    """Gaussian clusters around well-separated random centres (rejection sampling)."""
    k = max(2, round(n / 10))
    centres: list[np.ndarray] = []
    for _ in range(1000):
        if len(centres) == k:
            break
        cand = rng.uniform(10.0, GRID - 10.0, size=2)
        if all(np.linalg.norm(cand - c) >= 18.0 for c in centres):
            centres.append(cand)
    while len(centres) < k:  # pragma: no cover - only if the square is too crowded
        centres.append(rng.uniform(10.0, GRID - 10.0, size=2))
    owner = rng.integers(0, k, size=n)
    return np.asarray(centres)[owner] + rng.normal(0.0, CLUSTER_STD, size=(n, 2))


# ------------------------------------------------------------------------ reference plan
def _two_opt(route: list[int], d: list[list[int]]) -> list[int]:
    """Plain first-improvement 2-opt on a depot-anchored route. O(k^2) per pass, k <= ~20."""
    tour = [0, *route, 0]
    improved = True
    while improved:
        improved = False
        for i in range(1, len(tour) - 2):
            for j in range(i + 1, len(tour) - 1):
                a, b, c, e = tour[i - 1], tour[i], tour[j], tour[j + 1]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e]:
                    tour[i : j + 1] = reversed(tour[i : j + 1])
                    improved = True
    return tour[1:-1]


def _reference_plan(
    rng: np.random.Generator, xy: np.ndarray, demand: list[int], capacity: int, d: list[list[int]]
) -> list[list[int]]:
    """Sweep heuristic: sort by polar angle from a random start ray, cut on capacity, 2-opt."""
    angles = np.arctan2(xy[:, 1] - DEPOT_XY[1], xy[:, 0] - DEPOT_XY[0])
    start = rng.uniform(-math.pi, math.pi)
    order = np.argsort((angles - start) % (2 * math.pi), kind="stable") + 1  # node ids
    routes: list[list[int]] = [[]]
    load = 0
    for c in order.tolist():
        if load + demand[c] > capacity:
            routes.append([])
            load = 0
        routes[-1].append(c)
        load += demand[c]
    plans = []
    for r in routes:
        nn_order, rest, cur = [], set(r), 0  # nearest-neighbour seed order inside the petal
        while rest:
            cur = min(rest, key=lambda j, cur=cur: (d[cur][j], j))
            nn_order.append(cur)
            rest.remove(cur)
        plans.append(_two_opt(nn_order, d))
    return plans


def default_fleet_size(n: int, reference_routes: int) -> int:
    """Generous fleet size, deliberately non-binding.

    The pure-distance nearest-neighbour baseline is myopic and needed up to 0.45 * n vehicles on
    tight-window instances during calibration, so the fleet cap is ``ceil(n / 2) + 2`` (always at
    least the reference plan's routes + 2). The objective is distance; vehicles used are reported.
    """
    return max(reference_routes + 2, math.ceil(n / 2) + 2)


# ----------------------------------------------------------------------------- generator
def generate_instance(
    n_customers: int,
    layout: str = "R",
    seed: int = 0,
    tw: str = "tight",
    capacity: str = "medium",
    name: str | None = None,
    tw_mode: str = "planted",
) -> Instance:
    """Generate a feasible Solomon-style CVRPTW instance.

    Args:
        n_customers: number of customers (designed for 5..100; any positive value works).
        layout: ``"C"``, ``"R"`` or ``"RC"``.
        seed: RNG seed; same arguments -> identical instance.
        tw: ``"tight"`` or ``"loose"`` time-window widths.
        capacity: ``"tight"``, ``"medium"`` or ``"loose"`` vehicle capacity.
        name: optional instance name.
        tw_mode: ``"planted"`` (default; windows drawn around the reference plan's arrival times,
            feasible with the reference plan's vehicles) or ``"random"`` (Solomon R-style
            independent windows: centre uniform over the times at which the customer can be
            served directly from the depot; feasible because a dedicated vehicle can always serve
            any single customer, and the fleet is set to n). ``"random"`` is used only for the
            robustness check against planted-window bias.

    Complexity: O(n^2) time and memory (distance matrix), O(n log n) for the sweep.
    """
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {LAYOUTS}")
    if tw not in TW_WIDTH:
        raise ValueError(f"tw must be one of {tuple(TW_WIDTH)}")
    if capacity not in CAPACITY_LEVELS:
        raise ValueError(f"capacity must be one of {tuple(CAPACITY_LEVELS)}")
    if n_customers < 1:
        raise ValueError("n_customers must be >= 1")
    if tw_mode not in ("planted", "random"):
        raise ValueError("tw_mode must be 'planted' or 'random'")

    # Independent streams: geometry/demand depend only on (seed, n, layout); windows on the rest.
    ss = np.random.SeedSequence([seed, n_customers, LAYOUTS.index(layout)])
    rng_geo, rng_plan, rng_tw = (np.random.default_rng(s) for s in ss.spawn(3))
    xy = _coordinates(rng_geo, n_customers, layout)
    demands = rng_geo.integers(DEMAND_RANGE[0], DEMAND_RANGE[1] + 1, size=n_customers).tolist()
    cap = CAPACITY_LEVELS[capacity]

    # Provisional instance with an "infinite" horizon, used only to get the integer matrix.
    provisional = Instance(
        name="provisional",
        depot=Depot(*DEPOT_XY, ready_time=0.0, due_time=1e7),
        customers=[
            Customer(i + 1, float(x), float(y), int(q), 0.0, 1e7, float(SERVICE_TIME))
            for i, ((x, y), q) in enumerate(zip(xy.tolist(), demands, strict=True))
        ],
        vehicle_capacity=cap,
        num_vehicles=n_customers,
    )
    d = provisional.dist_rows
    plan = _reference_plan(rng_plan, xy, provisional.demand, cap, d)

    # Simulate the reference plan without waiting: a_i = arrival = service start at customer i.
    arrival: dict[int, int] = {}
    longest = 0
    svc = SERVICE_TIME * SCALE
    for r in plan:
        t, prev = 0, 0
        for c in r:
            t += (svc if prev else 0) + d[prev][c]
            arrival[c] = t
            prev = c
        longest = max(longest, t + svc + d[prev][0])
    horizon = math.ceil(longest / SCALE * HORIZON_SLACK)

    lo, hi = TW_WIDTH[tw]
    customers = []
    for c in range(1, n_customers + 1):
        width = rng_tw.uniform(lo, hi) * horizon
        latest = math.floor((horizon * SCALE - svc - d[c][0]) / SCALE)  # must still get home
        if tw_mode == "planted":
            # Draw the window so that it contains the reference arrival time a_i.
            a = arrival[c] / SCALE
            offset = rng_tw.uniform(0.0, width)  # where a_i falls inside the window
            ready = max(0, math.floor(a - offset))
            due = math.ceil(a - offset + width)
            due = max(min(due, latest, horizon), math.ceil(a))  # never cut a_i out of the window
        else:
            # Independent window: centre uniform over [direct arrival, latest feasible start].
            earliest = math.ceil(d[0][c] / SCALE)
            centre = rng_tw.uniform(earliest, latest)
            ready = max(0, round(centre - width / 2))
            due = max(min(latest, round(centre + width / 2)), earliest)
        customers.append(
            Customer(
                id=c,
                x=float(xy[c - 1, 0]),
                y=float(xy[c - 1, 1]),
                demand=int(demands[c - 1]),
                ready_time=float(ready),
                due_time=float(due),
                service_time=float(SERVICE_TIME),
            )
        )

    fleet = default_fleet_size(n_customers, len(plan))
    if tw_mode == "random":
        plan = [[c] for c in range(1, n_customers + 1)]  # one dedicated vehicle per customer
        fleet = n_customers
    suffix = "-rw" if tw_mode == "random" else ""
    inst = Instance(
        name=name or f"{layout}{n_customers}-{tw}-{capacity}-s{seed}{suffix}",
        depot=Depot(*DEPOT_XY, ready_time=0.0, due_time=float(horizon)),
        customers=customers,
        vehicle_capacity=cap,
        num_vehicles=fleet,
        metadata={
            "generator": "route_opt.generator",
            "layout": layout,
            "n": n_customers,
            "seed": seed,
            "tw": tw,
            "capacity": capacity,
            "tw_mode": tw_mode,
            "reference_routes": plan,
            "reference_distance": sum(route_distance(provisional, r) for r in plan) / SCALE,
        },
    )
    # Safety net: the reference plan must be feasible for the final instance.
    if not make_solution(inst, plan, "reference-plan").feasible:  # pragma: no cover
        raise RuntimeError(f"generator bug: reference plan infeasible for {inst.name}")
    return inst


# ------------------------------------------------------------------------------- JSON I/O
def instance_to_dict(inst: Instance) -> dict[str, Any]:
    return {
        "name": inst.name,
        "vehicle_capacity": inst.vehicle_capacity,
        "num_vehicles": inst.num_vehicles,
        "depot": {
            "x": inst.depot.x,
            "y": inst.depot.y,
            "ready_time": inst.depot.ready_time,
            "due_time": inst.depot.due_time,
        },
        "customers": [
            {
                "id": c.id,
                "x": c.x,
                "y": c.y,
                "demand": c.demand,
                "ready_time": c.ready_time,
                "due_time": c.due_time,
                "service_time": c.service_time,
            }
            for c in inst.customers
        ],
        "metadata": inst.metadata,
    }


def instance_from_dict(data: dict[str, Any]) -> Instance:
    dep = data["depot"]
    return Instance(
        name=data["name"],
        depot=Depot(float(dep["x"]), float(dep["y"]), float(dep["ready_time"]), float(dep["due_time"])),
        customers=[
            Customer(
                id=int(c["id"]),
                x=float(c["x"]),
                y=float(c["y"]),
                demand=int(c["demand"]),
                ready_time=float(c["ready_time"]),
                due_time=float(c["due_time"]),
                service_time=float(c["service_time"]),
            )
            for c in data["customers"]
        ],
        vehicle_capacity=int(data["vehicle_capacity"]),
        num_vehicles=int(data["num_vehicles"]),
        metadata=dict(data.get("metadata", {})),
    )


def save_instance(inst: Instance, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(instance_to_dict(inst), indent=1))


def load_instance(path: str | Path) -> Instance:
    """Load an instance from JSON (this package's format) or a Solomon ``.txt`` file."""
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return load_solomon(path)
    return instance_from_dict(json.loads(path.read_text()))


# --------------------------------------------------------------------------- Solomon I/O
def load_solomon(path: str | Path, max_customers: int | None = None) -> Instance:
    """Parse a Solomon-format VRPTW file (e.g. ``R101.txt``).

    The format is a name line, a ``VEHICLE`` block (``NUMBER CAPACITY``) and a ``CUSTOMER`` table
    whose rows are ``id x y demand ready due service``; row 0 is the depot. Following common
    practice, ``max_customers`` keeps the first k customers (Solomon's 25/50-customer variants).
    """
    lines = [ln.strip() for ln in Path(path).read_text().splitlines()]
    lines = [ln for ln in lines if ln]
    name = lines[0]
    num_vehicles = capacity = None
    rows: list[list[float]] = []
    for i, ln in enumerate(lines):
        if ln.upper().startswith("NUMBER") and num_vehicles is None:
            num_vehicles, capacity = (int(float(v)) for v in lines[i + 1].split()[:2])
        parts = ln.split()
        if len(parts) == 7 and all(_is_number(p) for p in parts) and num_vehicles is not None:
            rows.append([float(p) for p in parts])
    if num_vehicles is None or capacity is None or not rows:
        raise ValueError(f"{path}: not a Solomon-format file")
    depot_row, cust_rows = rows[0], rows[1:]
    if max_customers is not None:
        cust_rows = cust_rows[:max_customers]
    customers = [
        Customer(k, r[1], r[2], int(r[3]), r[4], r[5], r[6])
        for k, r in enumerate(cust_rows, start=1)  # re-number 1..n so node index == id
    ]
    return Instance(
        name=name if max_customers is None else f"{name}.{max_customers}",
        depot=Depot(depot_row[1], depot_row[2], depot_row[4], depot_row[5]),
        customers=customers,
        vehicle_capacity=capacity,
        num_vehicles=num_vehicles,
        metadata={"source": str(path), "format": "solomon"},
    )


def save_solomon(inst: Instance, path: str | Path) -> None:
    """Write an instance in Solomon text format (inverse of :func:`load_solomon`)."""
    out = [
        inst.name,
        "",
        "VEHICLE",
        "NUMBER     CAPACITY",
        f"{inst.num_vehicles:>6}{inst.vehicle_capacity:>12}",
    ]
    out += [
        "",
        "CUSTOMER",
        "CUST NO.  XCOORD.   YCOORD.    DEMAND   READY TIME  DUE DATE   SERVICE   TIME",
        "",
    ]
    dep = inst.depot
    out.append(f"{0:>5}{dep.x:>10g}{dep.y:>10g}{0:>10}{dep.ready_time:>12g}{dep.due_time:>11g}{0:>10}")
    for c in inst.customers:
        out.append(
            f"{c.id:>5}{c.x:>10g}{c.y:>10g}{c.demand:>10}{c.ready_time:>12g}{c.due_time:>11g}{c.service_time:>10g}"
        )
    Path(path).write_text("\n".join(out) + "\n")


def _is_number(s: str) -> bool:
    try:
        float(s)
    except ValueError:
        return False
    return True
