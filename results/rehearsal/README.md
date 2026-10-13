# Dress-rehearsal run (superseded)

First full run of the main grid, made with commit `18b94c5`, **before** the explicit depot-arc
constraints were added to the ILP (commit `71f0cec`). That change only matters when integer rounding
breaks the triangle inequality through the depot, which happens on 29 of the 96 instances. Every
solution in this run still passed the independent validator.

It is kept only as a reproducibility check: multithreaded CP-SAT is not bit-for-bit deterministic.
The headline numbers in the top-level README come from `results/benchmark.csv` (the final run).
