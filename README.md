# Delivery Route Optimizer: CVRPTW as an Integer Linear Program (Python, OR-Tools CP-SAT)

[![CI](https://github.com/jsankalp715/delivery-route-optimiser/actions/workflows/ci.yml/badge.svg)](https://github.com/jsankalp715/delivery-route-optimiser/actions/workflows/ci.yml)

This project plans delivery routes for a fleet of capacity-limited vans, where every stop must be
served inside its time window. It models the **capacitated vehicle routing problem with time
windows (CVRPTW)** as an **integer linear program**, solves it with Google OR-Tools **CP-SAT**, and
compares it against a greedy nearest-neighbour baseline on a reproducible benchmark. On
96 Solomon-style instances with 20-75 stops, the ILP cut total distance by **36.2%
on average** (median 36.4%). On the 48 instances with **50+ stops** the
reduction was **38.1%** (median 37.1%, range 16.4% to 55.0%). Every number comes from
`results/benchmark.csv`, and every solution in it passes an independent validator.

> **Honest headline.** The project was started to support a "~25 % shorter routes" claim. The
> measured reduction is **larger than 25 %** (38.1% at 50+ stops), mainly because pure nearest
> neighbour is myopic under time windows. Against a stronger greedy (Solomon's time-oriented
> nearest neighbour) the ILP is still 30.0% shorter at 50+ stops. At 50+ stops most
> loose-window instances are **not proven optimal**: those results are the *best solution found
> within 60/75 s*, with a mean proven optimality gap of 4.8%. See [Results](#results) and
> [Limitations](#limitations).

## Contents

- [Problem](#problem)
- [Why an ILP instead of a greedy heuristic?](#why-an-ilp-instead-of-a-greedy-heuristic)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [CLI](#cli)
- [Results](#results)
- [How correctness is checked](#how-correctness-is-checked)
- [Design decisions](#design-decisions)
- [Limitations](#limitations)
- [Future work](#future-work)
- [Repository layout](#repository-layout)

## Problem

A depot and `n` customers lie in the plane. Customer `i` has a demand `q_i`, a service time `s_i`
and a time window `[e_i, l_i]` in which service must **start** (vehicles that arrive early wait).
`K` identical vehicles with capacity `Q` leave the depot and must be back before the horizon `H`.
Each customer is served exactly once by one vehicle, no vehicle is overloaded, and every window is
respected. **Objective: minimise total travelled distance** (travel time = distance). Optionally,
vehicle count can be a lexicographic secondary or primary objective.

The full mathematical model (variables, constraints, objective, size) is in
**[docs/formulation.md](docs/formulation.md)**. In brief:

```
min  Σ d_ij x_ij
s.t. AddMultipleCircuit(x)                       # in/out degree 1 per customer, every cycle via depot
     x_ij ⇒ t_j ≥ t_i + s_i + d_ij               # time windows: reified, no big-M; t_i ∈ [E_i, L_i]
     x_ij ⇒ u_j ≥ u_i + q_j                      # capacity: MTZ-style load propagation; u_i ∈ [q_i, Q]
     ⌈Σq/Q⌉ ≤ Σ_j x_0j ≤ K                       # fleet size
     x ∈ {0,1}, t, u ∈ ℤ                          # O(n²) variables and constraints
```

## Why an ILP instead of a greedy heuristic?

Nearest neighbour makes one locally optimal choice at a time and never revisits it. With time
windows that is especially costly. It happily drives to the closest customer even if that
customer's window opens an hour later, waits, and by then other customers' windows have closed, so it
opens extra vehicles (it used 9.8 vehicles on average against 6.1 for the ILP),
and each extra vehicle costs two depot legs. The ILP reasons about all routes, loads and times
*jointly*, and it also reports how far from optimal it might be: the proven lower bound and gap.
The price is runtime: NN takes milliseconds and O(n²) time, while the ILP is NP-hard and runs under a
time limit.

## Architecture

```mermaid
flowchart LR
    G[generator.py<br/>Solomon-style C/R/RC<br/>+ Solomon loader] --> I[(Instance<br/>model.py<br/>integer x100 matrices)]
    D[data/*.json, *.txt] --> I
    I --> B[baseline.py<br/>greedy nearest neighbour]
    I --> P[ilp.py<br/>CP-SAT model]
    B -- full hint + cut-off --> P
    I --> R[reference_solver.py<br/>OR-Tools routing + GLS]
    B --> V{validate.py<br/>independent checker}
    P --> V
    R --> V
    V --> H[bench.py / run_benchmark.py<br/>CSV, summary, plots]
    V --> C[cli.py<br/>route-opt]
```

| Module | Role |
|---|---|
| `src/route_opt/model.py` | `Customer`, `Depot`, `Instance`, `Solution` dataclasses; shared integer distance/time matrices |
| `src/route_opt/generator.py` | seeded C/R/RC generator with a feasibility guarantee; JSON and Solomon-format I/O |
| `src/route_opt/baseline.py` | nearest-feasible-neighbour heuristic (+ Solomon's time-oriented variant), O(n²) |
| `src/route_opt/ilp.py` | **the core**: CP-SAT model, pruning, warm start, gap/bound reporting |
| `src/route_opt/reference_solver.py` | OR-Tools `RoutingModel` cross-check (not the main method) |
| `src/route_opt/validate.py` | independent feasibility + distance re-check |
| `src/route_opt/bench.py`, `benchmarks/` | benchmark grid, statistics, verification of stored solutions |
| `src/route_opt/plotting.py` | route maps and benchmark figures |
| `src/route_opt/cli.py` | `route-opt` command-line interface |

## Quick start

Requires Python 3.11+.

```bash
git clone https://github.com/jsankalp715/delivery-route-optimiser.git
cd delivery-route-optimiser
make setup            # python3 -m venv .venv && pip install -r requirements.txt && pip install -e ".[dev]"
source .venv/bin/activate

route-opt generate --n 50 --type RC --seed 1 --tw loose --out data/inst.json
route-opt compare --instance data/inst.json --time-limit 30 --plot compare.png
make test             # ~30 s
```

`make demo` does the generate + compare step in one go. Reproducing the full benchmark:

```bash
make benchmark        # = python benchmarks/run_benchmark.py --config benchmarks/config.yaml  (~40 min on 4 cores)
make verify           # re-generates every instance and re-validates every stored route set
```

## CLI

```bash
# Generate a reproducible instance (C = clustered, R = random, RC = mixed; tight/loose windows)
route-opt generate --n 50 --type RC --seed 1 --out data/inst.json

# Solve with one method: greedy | greedy-tonn | ilp | reference
route-opt solve --instance data/inst.json --method ilp --time-limit 60 --plot out.png --out sol.json
route-opt solve --instance data/demo_parcels_12_solomon.txt --method ilp      # Solomon .txt works too
route-opt solve --instance data/inst.json --method ilp --vehicle-objective primary   # vehicles first, then distance
route-opt solve --instance data/inst.json --method ilp --log                         # CP-SAT search log

# All methods side by side
route-opt compare --instance data/inst.json

# Check a saved solution independently
route-opt validate --instance data/inst.json --solution sol.json

# Benchmark grid from a YAML config (or rebuild tables/plots from an existing CSV)
route-opt benchmark --config benchmarks/config.yaml
route-opt benchmark --config benchmarks/config.yaml --analyze-only
```

Example `compare` output on `RC50-loose-medium-s1` (30 s ILP limit, 4 cores):

```
RC50-loose-medium-s1: n=50, Q=150, fleet=27

method         distance  vs greedy  vehicles     status     gap  time(s)  valid
-------------------------------------------------------------------------------
greedy          1159.34      +0.0%         9  HEURISTIC       -     0.00    yes
greedy-tonn     1027.45     -11.4%         7  HEURISTIC       -     0.00    yes
ilp              782.01     -32.5%         7   FEASIBLE    5.4%    30.05    yes
reference        780.12     -32.7%         6  HEURISTIC       -    10.00    yes

plot (greedy vs ILP) written to results/demo/rc50_greedy_vs_ilp.png
```

Re-running gives slightly different ILP values because multithreaded CP-SAT is not deterministic. Three 30 s runs of this instance gave 769.4, 778.0 and 782.0. At this short limit the ILP and the 10 s routing-library reference are within about 1 % of each other, and both are about a third shorter than greedy. (Five 60 s calibration runs with different CP-SAT portfolios and worker counts gave 768.1 to 787.1; see Design decisions.)

## Results

**Setup.** 96 instances: sizes {20, 30, 50, 75} × layouts {C, R, RC} × 8 seeds. Seeds 1, 3, 5, 7
use tight windows and seeds 2, 4, 6, 8 loose windows, so every (size, layout) cell has 4 of each.
Medium capacity (Q = 150; demands 5-30), service time 10, horizon 1.25 × the longest reference
route. Fleet size `ceil(n/2) + 2` is deliberately non-binding. The ILP gets **20 / 30 / 60 / 75 s**
wall-clock for 20 / 30 / 50 / 75 stops with 4 CP-SAT workers on a 4-core machine. The routing-library
reference gets 0.2 s per stop on one thread. The whole run took 39 minutes. Reduction =
(greedy − ILP) / greedy, per instance.

**Key findings**

1. **Distance:** 36.2% shorter on average (median 36.4%, range 14.0% to 55.0%); 38.1% at 50+ stops.
   It is never worse than greedy (guaranteed by construction and checked on every instance).
2. **Window regime matters:** 39.6% with tight windows vs 32.9% with loose windows. With tight windows,
   nearest neighbour waits for the closest customer and strands others. This holds from 30 stops up; at 20 stops
   the order flips (see the per-size rows below).
3. **Fewer vehicles as a side effect:** 9.8 → 6.1 vehicles on average, although
   vehicles are not in the objective.
4. **A stronger greedy closes part of the gap:** against Solomon's time-oriented NN the ILP is 27.6% shorter
   (30.0% at 50+ stops). Part of the headline number is therefore the plain NN's weakness.
5. **Optimality is proven only on smaller or tighter instances:** all 20-stop instances,
   13/24 at 50 stops and 8/24 at 75 stops. The remaining instances stop at the time limit with
   a mean proven gap of 4.8% at 50+ stops.
6. **The independent routing engine agrees closely:** mean ILP length relative to the OR-Tools routing reference is
   -0.4%. The ILP is ≤ the reference on 85/96 instances, and on large loose-window
   instances the reference is sometimes better (ILP up to 5.3% longer).

### Distance reduction vs greedy nearest neighbour

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| **all instances** | 96 | 36.2% | 36.4% | 14.0% | 55.0% | 8.4% |
| **n ≥ 50** | 48 | 38.1% | 37.1% | 16.4% | 55.0% | 7.7% |
| n = 20 | 24 | 34.0% | 34.2% | 19.2% | 51.5% | 8.1% |
| n = 30 | 24 | 34.5% | 35.3% | 14.0% | 48.6% | 9.4% |
| n = 50 | 24 | 37.9% | 37.0% | 24.7% | 51.4% | 6.9% |
| n = 75 | 24 | 38.4% | 37.4% | 16.4% | 55.0% | 8.5% |
| type C | 32 | 36.5% | 37.6% | 14.0% | 55.0% | 10.6% |
| type R | 32 | 35.3% | 35.3% | 16.4% | 51.4% | 7.6% |
| type RC | 32 | 36.9% | 36.6% | 23.2% | 50.4% | 6.7% |
| loose windows | 48 | 32.9% | 32.5% | 14.0% | 51.5% | 7.6% |
| tight windows | 48 | 39.6% | 39.4% | 19.2% | 55.0% | 7.9% |
| n ≥ 50, tight windows | 24 | 43.3% | 43.8% | 35.7% | 55.0% | 5.6% |
| n ≥ 50, loose windows | 24 | 33.0% | 33.8% | 16.4% | 42.0% | 5.7% |

### Sensitivity and cross-checks

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs **time-oriented NN** (stronger greedy), all | 96 | 27.6% | 28.7% | 0.0% | 45.3% | 8.8% |
| ILP vs time-oriented NN, n ≥ 50 | 48 | 30.0% | 30.5% | 18.3% | 39.7% | 4.9% |
| routing-library reference vs greedy, all | 96 | 36.0% | 35.7% | 11.5% | 55.0% | 8.3% |
| routing-library reference vs greedy, n ≥ 50 | 48 | 37.9% | 37.4% | 20.2% | 55.0% | 7.3% |
| ILP length relative to reference, n = 20 (− = ILP shorter) | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| ILP length relative to reference, n = 30 (− = ILP shorter) | 24 | -0.7% | 0.0% | -4.5% | 0.0% | 1.5% |
| ILP length relative to reference, n = 50 (− = ILP shorter) | 24 | -0.4% | -0.3% | -4.7% | 5.3% | 1.9% |
| ILP length relative to reference, n = 75 (− = ILP shorter) | 24 | -0.3% | 0.0% | -4.5% | 4.8% | 2.2% |

### Robustness probes (smaller samples, reported separately)

**Independent random windows** (`benchmarks/config_random_windows.yaml`). In the main grid, windows are
drawn around a planted reference plan, which might favour an optimiser. This probe keeps the same
geometry and demands but draws every window independently, Solomon R-style: the window centre is
uniform over the times the customer can be served straight from the depot. That gives 50 stops ×
{C, R, RC} × 4 seeds (2 tight + 2 loose), 60 s each.

| instance | greedy NN | time-oriented NN | ILP | routing ref. | ILP vs greedy | ILP vs TONN | ILP status (gap) | vehicles greedy → ILP |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| C50-tight-medium-s1-rw | 1549.8 | 1094.6 | 839.8 | 841.0 | 45.8% | 23.3% | OPTIMAL (0.0%) | 16 → 7 |
| C50-loose-medium-s2-rw | 945.6 | 995.3 | 705.3 | 695.5 | 25.4% | 29.1% | FEASIBLE (11.0%) | 9 → 8 |
| C50-tight-medium-s3-rw | 1251.9 | 1092.5 | 773.2 | 802.6 | 38.2% | 29.2% | OPTIMAL (0.0%) | 14 → 8 |
| C50-loose-medium-s4-rw | 980.4 | 1003.2 | 663.7 | 682.5 | 32.3% | 33.8% | FEASIBLE (3.9%) | 9 → 8 |
| R50-tight-medium-s1-rw | 2164.2 | 1745.8 | 1208.8 | 1214.6 | 44.1% | 30.8% | OPTIMAL (0.0%) | 21 → 10 |
| R50-loose-medium-s2-rw | 1499.8 | 1331.2 | 987.2 | 963.3 | 34.2% | 25.8% | FEASIBLE (9.5%) | 10 → 7 |
| R50-tight-medium-s3-rw | 1915.5 | 1905.4 | 1336.8 | 1362.6 | 30.2% | 29.8% | OPTIMAL (0.0%) | 16 → 11 |
| R50-loose-medium-s4-rw | 1328.3 | 1331.1 | 961.9 | 968.4 | 27.6% | 27.7% | FEASIBLE (8.0%) | 10 → 7 |
| RC50-tight-medium-s1-rw | 1647.1 | 1358.5 | 945.7 | 953.0 | 42.6% | 30.4% | OPTIMAL (0.0%) | 15 → 8 |
| RC50-loose-medium-s2-rw | 1302.6 | 1345.4 | 908.0 | 939.4 | 30.3% | 32.5% | FEASIBLE (9.0%) | 9 → 7 |
| RC50-tight-medium-s3-rw | 1736.0 | 1403.5 | 1044.6 | 1073.5 | 39.8% | 25.6% | OPTIMAL (0.0%) | 17 → 9 |
| RC50-loose-medium-s4-rw | 1320.5 | 1156.5 | 780.0 | 786.7 | 40.9% | 32.6% | FEASIBLE (4.6%) | 11 → 7 |

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs greedy NN | 12 | 36.0% | 36.2% | 25.4% | 45.8% | 6.8% |
| ILP vs time-oriented NN | 12 | 29.2% | 29.5% | 23.3% | 33.8% | 3.2% |
| ILP length relative to routing reference (− = ILP shorter) | 12 | -1.1% | -0.8% | -3.7% | 2.5% | 1.9% |
| ILP vs greedy NN, tight windows | 6 | 40.1% | 41.2% | 30.2% | 45.8% | 5.6% |
| ILP vs greedy NN, loose windows | 6 | 31.8% | 31.3% | 25.4% | 40.9% | 5.5% |

**100 stops** (`benchmarks/config_n100.yaml`): 3 layouts × 2 seeds (1 tight + 1 loose), 120 s each
(the 1.2 s/stop CLI default). This sample is too small for statistics and only shows how the method
behaves at 100 stops.

| instance | greedy NN | time-oriented NN | ILP | routing ref. | ILP vs greedy | ILP vs TONN | ILP status (gap) | vehicles greedy → ILP |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| C100-tight-medium-s1 | 2410.6 | 1781.3 | 1294.1 | 1297.8 | 46.3% | 27.4% | OPTIMAL (0.0%) | 23 → 13 |
| C100-loose-medium-s2 | 1524.4 | 1620.7 | 1126.4 | 1155.4 | 26.1% | 30.5% | FEASIBLE (17.9%) | 14 → 13 |
| R100-tight-medium-s1 | 3040.9 | 2742.6 | 1616.0 | 1709.3 | 46.9% | 41.1% | OPTIMAL (0.0%) | 32 → 14 |
| R100-loose-medium-s2 | 2431.1 | 2376.9 | 1636.1 | 1633.6 | 32.7% | 31.2% | FEASIBLE (18.9%) | 17 → 14 |
| RC100-tight-medium-s1 | 2514.6 | 2124.5 | 1573.4 | 1612.1 | 37.4% | 25.9% | FEASIBLE (4.7%) | 22 → 14 |
| RC100-loose-medium-s2 | 2343.0 | 2249.4 | 1629.2 | 1657.2 | 30.5% | 27.6% | FEASIBLE (16.9%) | 18 → 14 |

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs greedy NN | 6 | 36.6% | 35.1% | 26.1% | 46.9% | 8.5% |
| ILP vs time-oriented NN | 6 | 30.6% | 29.0% | 25.9% | 41.1% | 5.5% |
| ILP length relative to routing reference (− = ILP shorter) | 6 | -2.0% | -2.0% | -5.5% | 0.2% | 2.0% |
| ILP vs greedy NN, tight windows | 3 | 43.5% | 46.3% | 37.4% | 46.9% | 5.3% |
| ILP vs greedy NN, loose windows | 3 | 29.8% | 30.5% | 26.1% | 32.7% | 3.4% |

### Optimality gap and solve time

The ILP is **not** proven optimal on every instance. Where status is `FEASIBLE`, the number is the
*best solution found within the time limit* and the gap is CP-SAT's proven bound on how far it can be
from the optimum.

| n | time limit | proven optimal | best found at limit (FEASIBLE) | mean time (s) | median time to best solution (s) | arcs kept after pruning |
|---:|---:|---:|---:|---:|---:|---:|
| 20 | 20 s | 24/24 | 0/24 | 0.3 | 0.1 | 62% |
| 30 | 30 s | 23/24 | 1/24 | 3.7 | 0.9 | 58% |
| 50 | 60 s | 13/24 | 11/24 | 32.5 | 18.0 | 55% |
| 75 | 75 s | 8/24 | 16/24 | 52.5 | 60.2 | 52% |

| proven optimality gap at stop | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| n = 20 | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| n = 30 | 24 | 0.2% | 0.0% | 0.0% | 3.8% | 0.8% |
| n = 50 | 24 | 2.9% | 0.0% | 0.0% | 10.1% | 3.7% |
| n = 75 | 24 | 6.7% | 7.3% | 0.0% | 17.2% | 6.0% |
| **n ≥ 50** | 48 | 4.8% | 4.3% | 0.0% | 17.2% | 5.3% |

### Vehicles used

| vehicles used | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| greedy NN | 96 | 9.77 | 9.00 | 3.00 | 22.00 | 5.04 |
| time-oriented NN | 96 | 6.97 | 6.00 | 2.00 | 14.00 | 3.27 |
| ILP | 96 | 6.08 | 5.50 | 2.00 | 12.00 | 2.85 |
| routing reference | 96 | 6.03 | 5.50 | 2.00 | 11.00 | 2.77 |

### Plots

| | |
|---|---|
| ![Reduction by size](results/reduction_by_size.png) | ![Greedy vs ILP](results/baseline_vs_ilp.png) |
| ![Solve time](results/solve_time_vs_n.png) | |

Route map for the 50-stop instance with the **median** reduction (picked by rule, not by eye):
`R50-loose-medium-s8`. Labels show `customer id [time window]`.

![Route map](results/route_map_50.png)

**Reproducibility.** CP-SAT with several workers is not bit-for-bit deterministic. An earlier full
dress-rehearsal run of the same grid, made before a corner-case fix to the depot-arc constraints
(see Design decisions), measured a mean reduction of 36.1% (38.0% at 50+ stops), against
36.2% (38.1%) in the final run. Its summary is kept in `results/rehearsal/`.

## How correctness is checked

- **Independent validator** (`validate.py`): every customer exactly once; route loads ≤ Q; an
  earliest-start re-simulation meets every window and returns before the horizon; fleet size;
  reported service times form a valid schedule; distance recomputed from raw coordinates equals the
  reported one *exactly*. Every solution in tests and in the benchmark passes it, and the benchmark
  aborts otherwise. `make verify` re-checks all 384 stored solutions.
- **Brute-force optimum**: on 9 instances with 5-8 customers, the ILP returns `OPTIMAL` and exactly the
  optimum of an exhaustive solver (all permutations of all subsets + set-partition DP).
- **Negative tests**: missing/duplicate customers, depot inside a route, capacity, window, horizon and
  fleet violations, wrong distance, inconsistent schedule.
- **ILP ≤ greedy** always (hint + cut-off + fallback), tested even with a 10 ms limit.
- **Independent engine**: the OR-Tools routing library on the same data. The ILP was ≤ the reference
  on 85 / 96 instances.

## Design decisions

- **Integer scaling ×100.** CP-SAT needs integers, so distances and times are scaled by 100 and
  rounded (2 decimals). *All* methods and the validator share the same matrix, so comparisons are
  exact. Rounding can break the triangle inequality by one unit for near-collinear points (29 of the 96
  benchmark instances). Time bounds therefore use shortest paths, and depot-arc time constraints are
  added explicitly in that case.
- **`AddMultipleCircuit` rather than explicit degree + subtour constraints.** It is equivalent (see
  the formulation), handles the exponential subtour family lazily, and lets CP-SAT add routing cuts.
- **Reified time/load links instead of big-M**, with domains tightened to `[E_i, L_i]` via shortest
  paths, and **exact arc pruning** (capacity pairs, time-infeasible pairs).
- **Warm start**: a full hint (arcs, times, loads, vehicle count) from the greedy solution plus an
  objective cut-off, so the ILP is never worse than the baseline. If CP-SAT finds nothing, the greedy
  solution is returned with status `FALLBACK_*` (it never happened in the benchmark).
- **CP-SAT portfolio.** With ≥4 workers, half the threads run full-model workers (`default_lp`,
  `max_lp`) and half run LNS. On a 50-stop calibration instance (RC50-loose, seed 1, 60 s), the
  default portfolio gave distance 768.7 with a lower bound of 494 (gap 36 %). The tuned one gave
  777.2 with a bound of 742 (gap 4.6 %), and a tight-window instance went from "time limit, gap 18 %" to
  "proven optimal". This trades a possible ~1 % in primal quality (single runs, noisy) for
  meaningful gaps and early termination. 2 workers × 60 s was worse (787.1, single trial) than 4 workers, so
  the benchmark runs one instance at a time with all cores. Neither calibration instance
  (RC50-loose-s1, C50-tight-s2) is in the benchmark grid, where seed 1 is tight and seed 2 is loose,
  so nothing was tuned on test instances.
- **Time limits** 20/30/60/75 s (60 s at 50 stops as specified). 75 s at 75 stops instead of the
  1.2 s/stop CLI rule (90 s) keeps the full benchmark at about 40 minutes. n = 100 was left out of the
  main grid for the same reason; the model and CLI handle it (default limit 120 s).
- **Generator feasibility by construction** (Solomon's C-class approach): a sweep + 2-opt reference
  plan is built first, and each window is drawn around that plan's arrival time (random width and
  offset). The window regime alternates by seed parity (fixed before any benchmark run) so that tight
  and loose windows are equally represented. The ILP beat the planted plan on
  75/96 instances.
- **Fleet size `ceil(n/2) + 2`, deliberately non-binding.** During calibration, the myopic NN needed up
  to 0.45·n vehicles on tight-window instances. A tighter fleet would make the *baseline* infeasible,
  not the problem harder for the ILP.
- **Baseline = textbook nearest feasible neighbour** (capacity + window with waiting + return
  look-ahead, deterministic tie-break). Solomon's time-oriented NN is reported as a stronger-baseline
  sensitivity check, not cherry-picked away.
- **The routing library is a cross-check only**, with a smaller budget (0.2 s/stop, one thread). It is
  not presented as the project's method.
- **Pinned dependencies**: `pyproject.toml` (direct deps) and `requirements.txt` (full lock; numpy
  2.4.6 because 2.5 dropped Python 3.11).

## Limitations

- **Scaling.** The compact two-index model has O(n²) variables and constraints. At 75 stops with
  loose windows CP-SAT no longer proves optimality within 75 s (mean gap 6.7%). Hundreds of
  stops would need decomposition or a metaheuristic.
- **Time limit.** Results at 50+ stops are "best found within 60/75 s on 4 cores", not optima. More
  cores or time would change them slightly, and multithreaded runs are not bit-for-bit
  reproducible.
- **Euclidean distances**, travel time = distance, no traffic, symmetric.
- **Synthetic data.** Solomon-style but generated, and windows are planted around a reference plan
  (tight-window results may favour optimisers; reported separately). No real Solomon files are
  bundled; the loader supports them.
- **Single depot, homogeneous fleet, hard windows, no driver breaks.**
- **Weak baseline.** Pure NN is the textbook construction but not a strong heuristic. Insertion
  heuristics or OR-Tools routing would close much of the gap, as the reference column shows.

## Future work

- Column generation / branch-price-and-cut (set partitioning + ESPPRC pricing) for strong bounds
- ALNS or HGS hybrid with the ILP as a repair/polishing step (matheuristic) for 200+ stops
- Real road networks via OSRM/Valhalla travel-time matrices (asymmetric, time-dependent)
- Stochastic travel times (chance constraints or robust buffers)
- Rolling-horizon re-optimisation as new orders arrive; soft windows with penalties
- Run the original Solomon and Gehring-Homberger benchmark files and compare with best-known solutions

## Repository layout

```
src/route_opt/        model, generator, baseline, ilp, reference_solver, validate, bench, plotting, cli
benchmarks/           run_benchmark.py, config.yaml (main grid), config_random_windows.yaml,
                      config_n100.yaml (probes), smoke.yaml
data/                 3 hand-made demo instances (2 JSON, 1 Solomon-format .txt)
docs/formulation.md   exact mathematical model
results/              final run: benchmark.csv, summary.{md,json}, solutions.jsonl, plots, benchmark.log
results/random_windows/, results/n100/   robustness probes (same file layout)
results/rehearsal/    superseded dress-rehearsal run (reproducibility check)
results/demo/         CLI compare example (instance + captured output)
tests/                pytest suite incl. brute-force optimum (tests/brute_force.py)
```
