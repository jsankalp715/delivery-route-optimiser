## Distance reduction of the ILP vs greedy nearest neighbour

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| **all** | 6 | 36.6% | 35.1% | 26.1% | 46.9% | 8.5% |
| **n >= 50** | 6 | 36.6% | 35.1% | 26.1% | 46.9% | 8.5% |
| n = 100 | 6 | 36.6% | 35.1% | 26.1% | 46.9% | 8.5% |
| type C | 2 | 36.2% | 36.2% | 26.1% | 46.3% | 14.3% |
| type R | 2 | 39.8% | 39.8% | 32.7% | 46.9% | 10.0% |
| type RC | 2 | 33.9% | 33.9% | 30.5% | 37.4% | 4.9% |
| loose windows | 3 | 29.8% | 30.5% | 26.1% | 32.7% | 3.4% |
| tight windows | 3 | 43.5% | 46.3% | 37.4% | 46.9% | 5.3% |
| n = 100, loose windows | 3 | 29.8% | 30.5% | 26.1% | 32.7% | 3.4% |
| n = 100, tight windows | 3 | 43.5% | 46.3% | 37.4% | 46.9% | 5.3% |

## Sensitivity and cross-checks

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs time-oriented NN (stronger greedy) | 6 | 30.6% | 29.0% | 25.9% | 41.1% | 5.5% |
| ILP vs time-oriented NN, n >= 50 | 6 | 30.6% | 29.0% | 25.9% | 41.1% | 5.5% |
| Routing-library reference vs greedy | 6 | 35.4% | 34.3% | 24.2% | 46.2% | 8.4% |
| ILP distance relative to reference (+ = ILP longer) | 6 | -2.0% | -2.0% | -5.5% | 0.2% | 2.0% |
| ILP vs reference, n = 100 | 6 | -2.0% | -2.0% | -5.5% | 0.2% | 2.0% |

## ILP optimality gap (proven, at the time limit)

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| all | 6 | 9.7% | 10.8% | 0.0% | 18.9% | 9.1% |
| n = 100 | 6 | 9.7% | 10.8% | 0.0% | 18.9% | 9.1% |

## ILP status and solve time

| n | time limit (s) | status counts | mean time (s) | max time (s) |
|---:|---:|---|---:|---:|
| 100 | 120 | FEASIBLE: 4, OPTIMAL: 2 | 106.1 | 120.4 |

## Vehicles used

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 6 | 21.00 | 20.00 | 14.00 | 32.00 | 6.32 |
| tonn | 6 | 14.83 | 14.00 | 12.00 | 20.00 | 2.71 |
| ilp | 6 | 13.67 | 14.00 | 13.00 | 14.00 | 0.52 |
| ref | 6 | 13.67 | 13.50 | 13.00 | 15.00 | 0.82 |

ILP never worse than baseline: **True**; ILP <= reference on 5/6 instances.
