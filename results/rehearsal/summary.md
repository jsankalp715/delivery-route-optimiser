## Distance reduction of the ILP vs greedy nearest neighbour

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| **all** | 96 | 36.1% | 36.7% | 14.0% | 55.0% | 8.4% |
| **n >= 50** | 48 | 38.0% | 37.1% | 18.4% | 55.0% | 7.7% |
| n = 20 | 24 | 34.0% | 34.2% | 19.2% | 51.5% | 8.1% |
| n = 30 | 24 | 34.5% | 35.3% | 14.0% | 48.6% | 9.4% |
| n = 50 | 24 | 37.8% | 37.1% | 26.0% | 51.4% | 6.9% |
| n = 75 | 24 | 38.2% | 37.2% | 18.4% | 55.0% | 8.5% |
| type C | 32 | 36.4% | 37.6% | 14.0% | 55.0% | 10.6% |
| type R | 32 | 35.5% | 35.7% | 18.4% | 51.4% | 7.4% |
| type RC | 32 | 36.5% | 36.6% | 23.2% | 50.4% | 6.8% |
| loose windows | 48 | 32.7% | 32.3% | 14.0% | 51.5% | 7.4% |
| tight windows | 48 | 39.6% | 39.4% | 19.2% | 55.0% | 7.9% |
| n = 20, loose windows | 12 | 35.5% | 33.0% | 25.5% | 51.5% | 7.8% |
| n = 20, tight windows | 12 | 32.5% | 35.2% | 19.2% | 44.7% | 8.5% |
| n = 30, loose windows | 12 | 30.0% | 30.6% | 14.0% | 48.6% | 9.9% |
| n = 30, tight windows | 12 | 39.1% | 39.8% | 26.2% | 47.4% | 6.4% |
| n = 50, loose windows | 12 | 33.1% | 31.9% | 26.0% | 41.0% | 4.8% |
| n = 50, tight windows | 12 | 42.5% | 41.3% | 36.0% | 51.4% | 5.4% |
| n = 75, loose windows | 12 | 32.1% | 33.2% | 18.4% | 39.1% | 5.9% |
| n = 75, tight windows | 12 | 44.2% | 44.9% | 35.7% | 55.0% | 6.0% |

## Sensitivity and cross-checks

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| ILP vs time-oriented NN (stronger greedy) | 96 | 27.6% | 28.4% | 0.0% | 45.3% | 8.8% |
| ILP vs time-oriented NN, n >= 50 | 48 | 29.8% | 30.0% | 18.3% | 39.7% | 4.9% |
| Routing-library reference vs greedy | 96 | 36.0% | 35.7% | 11.5% | 55.0% | 8.3% |
| ILP distance relative to reference (+ = ILP longer) | 96 | -0.3% | 0.0% | -4.7% | 3.6% | 1.5% |
| ILP vs reference, n = 20 | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| ILP vs reference, n = 30 | 24 | -0.6% | 0.0% | -4.5% | 0.0% | 1.5% |
| ILP vs reference, n = 50 | 24 | -0.2% | -0.0% | -4.7% | 3.0% | 1.7% |
| ILP vs reference, n = 75 | 24 | -0.2% | 0.0% | -4.2% | 3.6% | 2.0% |

## ILP optimality gap (proven, at the time limit)

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| all | 96 | 2.5% | 0.0% | 0.0% | 15.9% | 4.6% |
| n = 20 | 24 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| n = 30 | 24 | 0.2% | 0.0% | 0.0% | 3.5% | 0.8% |
| n = 50 | 24 | 2.9% | 0.0% | 0.0% | 10.6% | 3.6% |
| n = 75 | 24 | 7.0% | 6.6% | 0.0% | 15.9% | 6.3% |

## ILP status and solve time

| n | time limit (s) | status counts | mean time (s) | max time (s) |
|---:|---:|---|---:|---:|
| 20 | 20 | OPTIMAL: 24 | 0.3 | 1.5 |
| 30 | 30 | FEASIBLE: 2, OPTIMAL: 22 | 4.5 | 30.0 |
| 50 | 60 | FEASIBLE: 11, OPTIMAL: 13 | 32.9 | 60.1 |
| 75 | 75 | FEASIBLE: 16, OPTIMAL: 8 | 53.5 | 75.2 |

## Vehicles used

| group | instances | mean | median | min | max | std |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 96 | 9.77 | 9.00 | 3.00 | 22.00 | 5.04 |
| tonn | 96 | 6.97 | 6.00 | 2.00 | 14.00 | 3.27 |
| ilp | 96 | 6.06 | 5.50 | 2.00 | 12.00 | 2.84 |
| ref | 96 | 6.04 | 5.50 | 2.00 | 11.00 | 2.78 |

ILP never worse than baseline: **True**; ILP <= reference on 81/96 instances.
