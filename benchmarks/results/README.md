# Benchmark results

### Legend

**Scenarios**

| Scenario | Meaning |
|---|---|
| `solo` | Model alone on the GPU (other instances stopped) — per-model best case. ShareGPT workload (realistic short chat). |
| `colocated` | All models serving, load driven against every endpoint simultaneously — the production topology. ShareGPT workload. SLO verdicts are judged here. |
| `context` | Solo capacity probe: random long inputs at ~80% of the model's context window, zero prefix reuse (worst-case KV pressure). |
| `contextpair` | Same long-input probe against all endpoints at once — "does this context + all models fit, at how many users". |

**Columns**

| Column | Meaning |
|---|---|
| users | Concurrent simulated users (per model) for that row |
| TTFT p50/p95/p99 | Time to first token, ms — perceived responsiveness ("is it thinking?") at the median / 95th / 99th percentile |
| ITL p95 | Inter-token latency, ms — streaming smoothness; ≤100ms ≈ ≥10 tok/s per user, comfortably above reading speed |
| TPOT p95 | Time per output token, ms — close cousin of ITL, includes scheduling effects |
| E2E p95 | Full request latency, ms — complete answer time |
| out tok/s | Aggregate output token throughput across all users (capacity) |
| req/s | Completed requests per second (capacity in user terms) |
| run dur | Wall-clock duration of that benchmark run, seconds |
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md) — only judged on `colocated` rows: TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms |

Multi-turn results (conversation replay with growing history — prefix-cache
and KV-offloading behavior) are plain-text harness reports: see the
`multiturn-*.txt` files inside each run directory.


## baseline-fa64565119

profile: **baseline** | config: `56c9afa477` | git: `1561dec957` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T16:20:28Z

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| colocated | gemma | 1 | 33.9 | 68.7 | 76.3 | 18.2 | 16.6 | 10,619.5 | 77.7 | 0.2 | 35s | PASS |
| colocated | gemma | 5 | 73.3 | 118.6 | 137.2 | 26.8 | 26.0 | 12,021.5 | 242.6 | 1.1 | 36s | PASS |
| colocated | gemma | 20 | 81.2 | 214.3 | 308.5 | 48.6 | 49.0 | 19,700.7 | 644.0 | 2.8 | 57s | PASS |
| colocated | gemma | 50 | 120.1 | 573.5 | 696.7 | 68.4 | 67.2 | 30,624.6 | 1,077.8 | 5.0 | 80s | PASS |
| colocated | llama | 1 | 20.9 | 46.4 | 56.1 | 11.9 | 10.0 | 6,532.6 | 99.7 | 0.3 | 26s | PASS |
| colocated | llama | 5 | 44.6 | 74.0 | 79.6 | 12.4 | 12.0 | 6,493.2 | 354.2 | 1.7 | 23s | PASS |
| colocated | llama | 20 | 56.7 | 303.4 | 371.5 | 18.0 | 15.7 | 8,105.5 | 1,283.5 | 6.0 | 26s | PASS |
| colocated | llama | 50 | 83.3 | 628.1 | 909.0 | 45.7 | 30.1 | 13,294.9 | 1,898.8 | 9.8 | 41s | PASS |
| context | gemma | 1 | 467.6 | 469.7 | 469.9 | 8.5 | 8.2 | 2,546.7 | 100.6 | 0.4 | 10s |  |
| context | gemma | 5 | 545.2 | 1,496.9 | 1,598.1 | 14.3 | 18.6 | 5,473.3 | 270.1 | 1.1 | 9s |  |
| context | gemma | 20 | 1,178.1 | 7,931.4 | 8,598.7 | 173.0 | 52.5 | 21,275.2 | 348.0 | 1.4 | 29s |  |
| context | gemma | 50 | 8,961.3 | 25,802.5 | 27,648.9 | 179.8 | 77.9 | 45,485.9 | 393.1 | 1.5 | 65s |  |
| context | llama | 1 | 276.8 | 278.6 | 278.6 | 5.6 | 5.4 | 1,660.1 | 154.6 | 0.6 | 7s |  |
| context | llama | 5 | 361.6 | 729.4 | 731.8 | 10.6 | 13.0 | 3,760.0 | 387.0 | 1.5 | 7s |  |
| context | llama | 20 | 6,783.0 | 10,948.7 | 11,352.3 | 79.7 | 19.1 | 15,730.4 | 390.4 | 1.5 | 26s |  |
| context | llama | 50 | 27,216.3 | 30,413.9 | 31,705.5 | 86.0 | 19.3 | 35,262.9 | 385.8 | 1.5 | 66s |  |
| contextpair | gemma | 1 | 717.0 | 982.5 | 985.4 | 21.3 | 20.1 | 6,033.8 | 57.4 | 0.2 | 18s |  |
| contextpair | gemma | 5 | 783.5 | 2,736.3 | 2,889.9 | 33.5 | 36.4 | 10,259.7 | 147.1 | 0.6 | 17s |  |
| contextpair | gemma | 20 | 2,065.6 | 15,311.6 | 16,866.2 | 365.2 | 115.7 | 44,586.4 | 169.6 | 0.7 | 60s |  |
| contextpair | gemma | 50 | 19,203.5 | 54,102.3 | 57,895.6 | 392.6 | 170.1 | 96,999.8 | 182.6 | 0.7 | 140s |  |
| contextpair | llama | 1 | 511.6 | 570.8 | 575.2 | 13.1 | 10.8 | 3,292.6 | 79.7 | 0.3 | 13s |  |
| contextpair | llama | 5 | 688.5 | 1,987.3 | 2,024.8 | 24.9 | 28.3 | 8,168.9 | 178.2 | 0.7 | 14s |  |
| contextpair | llama | 20 | 14,560.6 | 23,945.8 | 24,742.5 | 169.0 | 41.7 | 34,406.2 | 179.0 | 0.7 | 57s |  |
| contextpair | llama | 50 | 59,548.2 | 66,989.4 | 69,804.7 | 172.9 | 42.4 | 77,630.1 | 181.0 | 0.7 | 141s |  |
| solo | gemma | 1 | 27.2 | 48.8 | 56.6 | 7.8 | 7.6 | 4,975.5 | 132.6 | 0.4 | 20s |  |
| solo | gemma | 5 | 47.0 | 69.0 | 72.1 | 13.0 | 12.9 | 6,998.1 | 362.2 | 1.6 | 25s |  |
| solo | gemma | 20 | 72.0 | 279.3 | 281.0 | 25.3 | 22.3 | 13,823.9 | 866.0 | 3.8 | 42s |  |
| solo | gemma | 50 | 97.1 | 500.6 | 711.1 | 40.8 | 33.5 | 19,924.9 | 1,490.6 | 6.9 | 58s |  |
| solo | llama | 1 | 14.4 | 36.6 | 46.0 | 4.6 | 4.5 | 2,732.8 | 223.6 | 0.7 | 11s |  |
| solo | llama | 5 | 27.2 | 36.4 | 39.3 | 5.1 | 5.0 | 2,601.7 | 864.2 | 4.2 | 10s |  |
| solo | llama | 20 | 30.6 | 124.9 | 184.0 | 9.0 | 7.1 | 3,783.3 | 2,837.3 | 13.5 | 12s |  |
| solo | llama | 50 | 44.1 | 375.6 | 458.8 | 18.2 | 14.0 | 5,517.4 | 4,349.9 | 22.7 | 18s |  |

total benchmarked load time: 20.0 min across 32 runs

multi-turn reports: `multiturn-gemma-c20.metrics.txt`, `multiturn-gemma-c20.txt`, `multiturn-llama-c20.metrics.txt`, `multiturn-llama-c20.txt`
