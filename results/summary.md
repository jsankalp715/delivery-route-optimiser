## Distance reduction of the ILP vs greedy nearest neighbour

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| **all** | 96 | 36.2% | 36.4% | 14.0% | 55.0% | 8.4% |
| **n >= 50** | 48 | 38.1% | 37.1% | 16.4% | 55.0% | 7.7% |
| n = 20 | 24 | 34.0% | 34.2% | 19.2% | 51.5% | 8.1% |
| n = 30 | 24 | 34.5% | 35.3% | 14.0% | 48.6% | 9.4% |
| n = 50 | 24 | 37.9% | 37.0% | 24.7% | 51.4% | 6.9% |
| n = 75 | 24 | 38.4% | 37.4% | 16.4% | 55.0% | 8.5% |
| type C | 32 | 36.5% | 37.6% | 14.0% | 55.0% | 10.6% |
| type R | 32 | 35.3% | 35.3% | 16.4% | 51.4% | 7.6% |
| type RC | 32 | 36.9% | 36.6% | 23.2% | 50.4% | 6.7% |
| loose windows | 48 | 32.9% | 32.5% | 14.0% | 51.5% | 7.6% |
| tight windows | 48 | 39.6% | 39.4% | 19.2% | 55.0% | 7.9% |
| n = 20, loose windows | 12 | 35.5% | 33.0% | 25.5% | 51.5% | 7.8% |
| n = 20, tight windows | 12 | 32.5% | 35.2% | 19.2% | 44.7% | 8.5% |
| n = 30, loose windows | 12 | 30.0% | 30.6% | 14.0% | 48.6% | 9.9% |
| n = 30, tight windows | 12 | 39.1% | 39.8% | 26.2% | 47.4% | 6.4% |
| n = 50, loose windows | 12 | 33.3% | 33.2% | 24.7% | 42.0% | 5.0% |
| n = 50, tight windows | 12 | 42.5% | 41.3% | 36.0% | 51.4% | 5.4% |
| n = 75, loose windows | 12 | 32.6% | 33.8% | 16.4% | 40.9% | 6.6% |
| n = 75, tight windows | 12 | 44.1% | 44.4% | 35.7% | 55.0% | 6.0% |

## Sensitivity and cross-checks

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs time-oriented NN (stronger greedy) | 96 | 27.6% | 28.7% | 0.0% | 45.3% | 8.8% |
| ILP vs time-oriented NN, n >= 50 | 48 | 30.0% | 30.5% | 18.3% | 39.7% | 4.9% |
| Routing-library reference vs greedy | 96 | 36.0% | 35.7% | 11.5% | 55.0% | 8.3% |
| ILP distance relative to reference (+ = ILP longer) | 96 | -0.4% | 0.0% | -4.7% | 5.3% | 1.6% |
| ILP vs reference, n = 20 | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| ILP vs reference, n = 30 | 24 | -0.7% | 0.0% | -4.5% | 0.0% | 1.5% |
| ILP vs reference, n = 50 | 24 | -0.4% | -0.3% | -4.7% | 5.3% | 1.9% |
| ILP vs reference, n = 75 | 24 | -0.3% | 0.0% | -4.5% | 4.8% | 2.2% |

## ILP optimality gap (proven, at the time limit)

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| all | 96 | 2.4% | 0.0% | 0.0% | 17.2% | 4.4% |
| n = 20 | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| n = 30 | 24 | 0.2% | 0.0% | 0.0% | 3.8% | 0.8% |
| n = 50 | 24 | 2.9% | 0.0% | 0.0% | 10.1% | 3.7% |
| n = 75 | 24 | 6.7% | 7.3% | 0.0% | 17.2% | 6.0% |

## ILP status and solve time

| n | time limit (s) | status counts | mean time (s) | max time (s) |
|---:|---:|---|---:|---:|
| 20 | 20 | OPTIMAL: 24 | 0.3 | 1.4 |
| 30 | 30 | FEASIBLE: 1, OPTIMAL: 23 | 3.7 | 30.0 |
| 50 | 60 | FEASIBLE: 11, OPTIMAL: 13 | 32.5 | 60.1 |
| 75 | 75 | FEASIBLE: 16, OPTIMAL: 8 | 52.5 | 75.2 |

## Vehicles used

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 96 | 9.77 | 9.00 | 3.00 | 22.00 | 5.04 |
| tonn | 96 | 6.97 | 6.00 | 2.00 | 14.00 | 3.27 |
| ilp | 96 | 6.08 | 5.50 | 2.00 | 12.00 | 2.85 |
| ref | 96 | 6.03 | 5.50 | 2.00 | 11.00 | 2.77 |

ILP never worse than baseline: **True**; ILP <= reference on 85/96 instances.
