# CVRPTW integer linear program: exact formulation

This is the model built by `route_opt.ilp.build_model` and solved with OR-Tools CP-SAT. Every symbol
below maps 1:1 to a line of code (the code names are given in brackets).

## 1. Data

| Symbol | Meaning | Code |
|---|---|---|
| $N = \{0, 1, \dots, n\}$ | nodes; $0$ is the depot | `range(instance.num_nodes)` |
| $C = N \setminus \{0\}$ | customers | |
| $d_{ij} \in \mathbb{Z}_{\ge 0}$ | distance **and** travel time from $i$ to $j$: $\operatorname{round}(100 \cdot \lVert p_i - p_j \rVert_2)$ | `instance.dist_rows` |
| $q_i \in \mathbb{Z}_{\ge 0}$ | demand of customer $i$ ($q_0 = 0$) | `instance.demand` |
| $s_i \in \mathbb{Z}_{\ge 0}$ | service time at $i$ ($s_0 = 0$), scaled by 100 | `instance.service` |
| $[e_i, \ell_i]$ | time window: service at $i$ must **start** in it (scaled by 100) | `instance.ready`, `instance.due` |
| $[e_0, H]$ | depot opening time and horizon (all vehicles back by $H$) | `instance.ready[0]`, `instance.horizon` |
| $Q$ | vehicle capacity (homogeneous fleet) | `instance.vehicle_capacity` |
| $K$ | number of vehicles available | `instance.num_vehicles` |

**Integer scaling.** CP-SAT accepts only integer data. All distances and times are multiplied by
100 and rounded, i.e. kept to two decimals. Every method in the project (greedy, ILP, routing
library, validator) uses this same integer matrix, so comparisons are exact. Reported distances are
divided by 100 again. Rounding moves each arc by at most 0.005 units. It can also break the
triangle inequality by one scaled unit for nearly collinear points, and the bounds below are built
to stay valid when that happens.

## 2. Preprocessing (exact, no feasible solution is removed)

Let $\delta(i, j)$ be the shortest-path length in the integer matrix (`_shortest_from_depot`).
Because $\delta(0,i) \le d_{0i}$ even if rounding breaks the triangle inequality, the following are
valid bounds on the service-start time of customer $i$ in *any* feasible solution:

$$E_i = \max\bigl(e_i,\; e_0 + \delta(0, i)\bigr), \qquad L_i = \min\bigl(\ell_i,\; H - s_i - \delta(i, 0)\bigr).$$

If $E_i > L_i$ for some $i$, no vehicle can serve $i$ and the instance is reported infeasible
(`time_bounds`).

**Arc set.** Depot arcs are always kept. A customer arc $(i, j)$ with $i \neq j$ is kept only if
both customers fit in one vehicle and $j$ can still be reached in time when $i$ is left as early
as possible:

$$A = \{(0,j), (j,0) : j \in C\} \;\cup\; \{(i,j) \in C^2 : i \ne j,\; q_i + q_j \le Q,\; E_i + s_i + d_{ij} \le L_j\}.$$

Arcs used by the warm-start solution are always kept (they are feasible, so they would pass the
test anyway; the guard makes the hint robust).

## 3. Variables

| Variable | Domain | Meaning | Code |
|---|---|---|---|
| $x_{ij}$ | $\{0, 1\}$, $(i,j) \in A$ | 1 if a vehicle drives directly from $i$ to $j$ | `x[i, j]` |
| $t_i$ | $\mathbb{Z} \cap [E_i, L_i]$, $i \in C$ | service start time at $i$ | `t[i]` |
| $u_i$ | $\mathbb{Z} \cap [q_i, Q]$, $i \in C$ | load delivered on $i$'s route up to and including $i$ | `u[i]` |
| $v$ | $\mathbb{Z} \cap [\min(\lceil \sum_i q_i / Q \rceil, K),\, K]$ | number of vehicles used | `vehicles` |

## 4. Objective

$$\min \; \sum_{(i,j) \in A} d_{ij}\, x_{ij} \qquad \text{(total distance, `distance`)}$$

Optional vehicle terms (`--vehicle-objective`):

* `secondary`, lexicographic (distance, then vehicles): $\min\ (K+1)\sum d_{ij}x_{ij} + v$. Since
  $0 \le v \le K < K+1$, one unit of distance always outweighs any change in $v$.
* `primary`, lexicographic (vehicles, then distance): $\min\ (D^{\max}+1)\,v + \sum d_{ij}x_{ij}$
  with $D^{\max} = \sum_{i\in C}\max_j d_{ij} + K\max_j d_{0j}$, an upper bound on any route plan's
  distance.

## 5. Constraints

**(1) Degree constraints.** Every customer is entered once and left once:

$$\sum_{j:(i,j)\in A} x_{ij} = 1 \quad \forall i \in C, \qquad \sum_{i:(i,j)\in A} x_{ij} = 1 \quad \forall j \in C.$$

**(2) Subtour elimination.** Every cycle passes through the depot:

$$\sum_{i \in S}\sum_{j \in S,\,(i,j)\in A} x_{ij} \;\le\; |S| - 1 \qquad \forall S \subseteq C,\ |S| \ge 2.$$

(1) and (2) are enforced together by one global constraint, `AddMultipleCircuit` (the "routes"
constraint), with node 0 as the depot and no self-loop literals for customers, so each customer
must be visited. CP-SAT propagates it combinatorially and adds the degree equalities and violated
subtour/capacity cuts to its LP relaxation lazily. The exponential family (2) is never written out.
Because $s_i + d_{ij} > 0$ on customer arcs, constraint (3) below also rules out subtours
(MTZ argument), so the model stays valid even without the global constraint's cuts.

**(3) Time windows: reified, no big-M.** For every customer arc,

$$x_{ij} = 1 \;\Rightarrow\; t_j \ge t_i + s_i + d_{ij} \qquad \forall (i,j) \in A,\ i, j \in C.$$

In code this is `m.add(t[j] >= t[i] + s[i] + d[i][j]).only_enforce_if(x[i, j])`. Waiting is
implicit: $t_j$ may exceed the arrival time $t_i + s_i + d_{ij}$, but it can never drop below
$E_j \ge e_j$. The window itself is the domain $[E_j, L_j]$. A MIP solver would linearise this as
$t_j \ge t_i + s_i + d_{ij} - M_{ij}(1 - x_{ij})$ with $M_{ij} = L_i + s_i + d_{ij} - E_j$.
CP-SAT takes the implication directly. For its LP relaxation it derives the big-M from the variable
domains, which is why tightening the domains to $[E_i, L_i]$ matters.

**(3b) Depot arcs.** Leaving the depot and returning before the horizon,

$$x_{0j} = 1 \Rightarrow t_j \ge e_0 + d_{0j}, \qquad x_{j0} = 1 \Rightarrow t_j + s_j + d_{j0} \le H,$$

are implied by the domain bounds $E_j$ and $L_j$ whenever $\delta(0,j) = d_{0j}$ and
$\delta(j,0) = d_{j0}$. When rounding makes a shortest path shorter than the direct arc, the
constraint is added explicitly, reified on the arc literal.

**(4) Capacity: MTZ-style load propagation.**

$$x_{ij} = 1 \;\Rightarrow\; u_j \ge u_i + q_j \qquad \forall (i,j) \in A,\ i, j \in C,$$

together with the domains $q_i \le u_i \le Q$. Along a route the load is non-decreasing and starts
at $q_j$ after the first stop (domain lower bound), so the last $u$ on a route is at least the
route's total demand and at most $Q$.

**(5) Fleet size.**

$$v = \sum_{j \in C} x_{0j}, \qquad \Bigl\lceil \tfrac{\sum_i q_i}{Q} \Bigr\rceil \le v \le K.$$

The lower bound is a valid inequality (redundant, but it helps the LP).

**(6) Warm-start cut-off (optional, on by default).** With the greedy solution $\bar{x}$ as hint,

$$\text{objective} \;\le\; \text{objective}(\bar{x}),$$

so every solution CP-SAT reports is at least as good as the baseline. Every variable ($x, t, u, v$)
is hinted, so CP-SAT starts from a complete feasible solution. If CP-SAT returns no solution within
the time limit, the greedy solution is returned with status `FALLBACK_<status>`.

## 6. Size and complexity

With $|A| \le n(n+1)$ arcs:

| Item | Count |
|---|---|
| Boolean arc variables | $\lvert A\rvert \le n(n+1)$ |
| integer variables | $2n + 1$ |
| global routes constraint | 1, over $\lvert A\rvert$ literals |
| reified linear constraints | $\le 2\,n(n-1)$ (time + load on customer arcs) + at most $2n$ depot-arc ones |
| linear equality / bounds | 1 (vehicle count) + 1 (cut-off) |

So the model is $O(n^2)$ in variables, constraints and memory, and building it takes $O(n^2)$ time.
For $n = 50$ there are at most 2,550 arcs. In the benchmark, pruning kept about 60-80 % of them with
loose windows and about 30-55 % with tight windows (column `ilp_arcs_kept` in `results/benchmark.csv`). Solving is NP-hard (it generalises the TSP), so CP-SAT runs under a
wall-clock limit. The result is the *best solution found within the limit*, together with CP-SAT's
proven lower bound $LB$ and the relative gap

$$\text{gap} = \frac{\text{objective} - LB}{\text{objective}},$$

which is 0 exactly when optimality is proven (status `OPTIMAL`).

## 7. Search configuration

* `num_workers` = all cores (4 on the benchmark machine).
* With 4 or more workers, half of the threads run full-model workers (`default_lp`, then `max_lp`)
  and the rest run large-neighbourhood search, including CP-SAT's routing-specific LNS. `max_lp`
  (linearization level 2) adds the routes constraint's cuts to the LP. On a 50-stop calibration
  instance it raised the proven lower bound from 494 to 742, reducing the reported gap from 36 % to
  4.6 %, and it lets tight-window instances finish with a proof of optimality instead of timing out.
* A fixed `random_seed`. Multi-threaded CP-SAT is still not bit-for-bit deterministic, because
  workers share solutions asynchronously.

## 8. How the model is checked

* `tests/test_ilp.py::test_ilp_matches_brute_force_optimum`: on nine instances with 5-8 customers
  (all layouts, tight/loose windows), the ILP returns status `OPTIMAL` and exactly the optimum of an
  independent brute-force solver (`tests/brute_force.py`: all permutations of every subset, plus a
  set-partition DP).
* Pruning and warm start do not change the optimum (`test_arc_pruning_and_warm_start_do_not_change_the_optimum`).
* Every solution produced in tests and benchmarks passes `route_opt.validate`, which re-derives the
  schedule, loads and distance from raw coordinates with separate code.
* On the benchmark, the OR-Tools routing library (a different engine) is run on the same integer
  data as a cross-check.
