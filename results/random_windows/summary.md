## Distance reduction of the ILP vs greedy nearest neighbour

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| **all** | 12 | 36.0% | 36.2% | 25.4% | 45.8% | 6.8% |
| **n >= 50** | 12 | 36.0% | 36.2% | 25.4% | 45.8% | 6.8% |
| n = 50 | 12 | 36.0% | 36.2% | 25.4% | 45.8% | 6.8% |
| type C | 4 | 35.4% | 35.3% | 25.4% | 45.8% | 8.7% |
| type R | 4 | 34.0% | 32.2% | 27.6% | 44.1% | 7.3% |
| type RC | 4 | 38.4% | 40.4% | 30.3% | 42.6% | 5.5% |
| loose windows | 6 | 31.8% | 31.3% | 25.4% | 40.9% | 5.5% |
| tight windows | 6 | 40.1% | 41.2% | 30.2% | 45.8% | 5.6% |
| n = 50, loose windows | 6 | 31.8% | 31.3% | 25.4% | 40.9% | 5.5% |
| n = 50, tight windows | 6 | 40.1% | 41.2% | 30.2% | 45.8% | 5.6% |

## Sensitivity and cross-checks

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs time-oriented NN (stronger greedy) | 12 | 29.2% | 29.5% | 23.3% | 33.8% | 3.2% |
| ILP vs time-oriented NN, n >= 50 | 12 | 29.2% | 29.5% | 23.3% | 33.8% | 3.2% |
| Routing-library reference vs greedy | 12 | 35.2% | 35.8% | 26.4% | 45.7% | 6.9% |
| ILP distance relative to reference (+ = ILP longer) | 12 | -1.1% | -0.8% | -3.7% | 2.5% | 1.9% |
| ILP vs reference, n = 50 | 12 | -1.1% | -0.8% | -3.7% | 2.5% | 1.9% |

## ILP optimality gap (proven, at the time limit)

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| all | 12 | 3.8% | 1.9% | 0.0% | 11.0% | 4.4% |
| n = 50 | 12 | 3.8% | 1.9% | 0.0% | 11.0% | 4.4% |

## ILP status and solve time

| n | time limit (s) | status counts | mean time (s) | max time (s) |
|---:|---:|---|---:|---:|
| 50 | 60 | FEASIBLE: 6, OPTIMAL: 6 | 32.7 | 60.1 |

## Vehicles used

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 12 | 13.08 | 12.50 | 9.00 | 21.00 | 3.96 |
| tonn | 12 | 8.25 | 8.00 | 7.00 | 12.00 | 1.66 |
| ilp | 12 | 8.08 | 8.00 | 7.00 | 11.00 | 1.31 |
| ref | 12 | 7.83 | 7.50 | 6.00 | 10.00 | 1.27 |

ILP never worse than baseline: **True**; ILP <= reference on 10/12 instances.
