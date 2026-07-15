# baseline-fa64565119

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
| in tok / out tok | Total tokens processed in that run: prompt tokens sent (prefill work) / tokens generated (decode work). Multi-turn runs are not included — see their own reports. |
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md) — only judged on `colocated` rows: TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms |

**Multi-turn conversations table** (conversation replay with growing history —
prefix-cache and KV-offloading behavior): parsed from the harness reports.
Columns: req/s (completed turns per second), TTFT/TPOT/e2e mean/p99 (ms —
the harness's report truncates mid percentiles when piped, so mean is the
stable center),
input tokens per request mean/max (shows how deep conversations grew), and
approximate total tokens in/out (count × mean — the harness reports
distributions, not exact sums). Raw reports remain in `multiturn-*.txt`.


profile: **baseline** | config: `56c9afa477` | git: `ca060db65a` (dirty) | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T17:50:39Z

### Configuration

| instance | model | context window | GPU mem fraction | KV offload | other flags |
|---|---|---|---|---|---|
| gemma | gemma-4-26b-a4b-it-awq-4bit | 8,192 | 0.68 | off | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |
| llama | llama-3.2-3b-instruct-awq-int4 | 8,192 | 0.2 | off | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo', 'colocated'] | context-stress inputs≈80% of window, 256 out | multi-turn: 20 clients / 60 conversations

served (observed): `gemma` = gemma-4-26b-a4b-it-awq-4bit, `llama` = llama-3.2-3b-instruct-awq-int4

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| colocated | gemma-4-26b-a4b-it-awq-4bit | 1 | 33.9 | 68.7 | 76.3 | 18.2 | 16.6 | 10,619.5 | 77.7 | 0.2 | 35s | 1,228 | 2,681 | PASS |
| colocated | gemma-4-26b-a4b-it-awq-4bit | 5 | 73.3 | 118.6 | 137.2 | 26.8 | 26.0 | 12,021.5 | 242.6 | 1.1 | 36s | 11,305 | 8,849 | PASS |
| colocated | gemma-4-26b-a4b-it-awq-4bit | 20 | 81.2 | 214.3 | 308.5 | 48.6 | 49.0 | 19,700.7 | 644.0 | 2.8 | 57s | 37,857 | 36,517 | PASS |
| colocated | gemma-4-26b-a4b-it-awq-4bit | 50 | 120.1 | 573.5 | 696.7 | 68.4 | 67.2 | 30,624.6 | 1,077.8 | 5.0 | 80s | 95,684 | 86,588 | PASS |
| colocated | llama-3.2-3b-instruct-awq-int4 | 1 | 20.9 | 46.4 | 56.1 | 11.9 | 10.0 | 6,532.6 | 99.7 | 0.3 | 26s | 1,365 | 2,591 | PASS |
| colocated | llama-3.2-3b-instruct-awq-int4 | 5 | 44.6 | 74.0 | 79.6 | 12.4 | 12.0 | 6,493.2 | 354.2 | 1.7 | 23s | 11,792 | 8,305 | PASS |
| colocated | llama-3.2-3b-instruct-awq-int4 | 20 | 56.7 | 303.4 | 371.5 | 18.0 | 15.7 | 8,105.5 | 1,283.5 | 6.0 | 26s | 39,450 | 34,004 | PASS |
| colocated | llama-3.2-3b-instruct-awq-int4 | 50 | 83.3 | 628.1 | 909.0 | 45.7 | 30.1 | 13,294.9 | 1,898.8 | 9.8 | 41s | 99,484 | 77,652 | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 467.6 | 469.7 | 469.9 | 8.5 | 8.2 | 2,546.7 | 100.6 | 0.4 | 10s | 26,267 | 1,024 |  |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 545.2 | 1,496.9 | 1,598.1 | 14.3 | 18.6 | 5,473.3 | 270.1 | 1.1 | 9s | 65,667 | 2,560 |  |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 1,178.1 | 7,931.4 | 8,598.7 | 173.0 | 52.5 | 21,275.2 | 348.0 | 1.4 | 29s | 262,661 | 10,240 |  |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 8,961.3 | 25,802.5 | 27,648.9 | 179.8 | 77.9 | 45,485.9 | 393.1 | 1.5 | 65s | 656,640 | 25,600 |  |
| context | llama-3.2-3b-instruct-awq-int4 | 1 | 276.8 | 278.6 | 278.6 | 5.6 | 5.4 | 1,660.1 | 154.6 | 0.6 | 7s | 26,350 | 1,024 |  |
| context | llama-3.2-3b-instruct-awq-int4 | 5 | 361.6 | 729.4 | 731.8 | 10.6 | 13.0 | 3,760.0 | 387.0 | 1.5 | 7s | 65,875 | 2,560 |  |
| context | llama-3.2-3b-instruct-awq-int4 | 20 | 6,783.0 | 10,948.7 | 11,352.3 | 79.7 | 19.1 | 15,730.4 | 390.4 | 1.5 | 26s | 263,495 | 10,240 |  |
| context | llama-3.2-3b-instruct-awq-int4 | 50 | 27,216.3 | 30,413.9 | 31,705.5 | 86.0 | 19.3 | 35,262.9 | 385.8 | 1.5 | 66s | 658,731 | 25,600 |  |
| contextpair | gemma-4-26b-a4b-it-awq-4bit | 1 | 717.0 | 982.5 | 985.4 | 21.3 | 20.1 | 6,033.8 | 57.4 | 0.2 | 18s | 26,267 | 1,024 |  |
| contextpair | gemma-4-26b-a4b-it-awq-4bit | 5 | 783.5 | 2,736.3 | 2,889.9 | 33.5 | 36.4 | 10,259.7 | 147.1 | 0.6 | 17s | 65,667 | 2,560 |  |
| contextpair | gemma-4-26b-a4b-it-awq-4bit | 20 | 2,065.6 | 15,311.6 | 16,866.2 | 365.2 | 115.7 | 44,586.4 | 169.6 | 0.7 | 60s | 262,661 | 10,240 |  |
| contextpair | gemma-4-26b-a4b-it-awq-4bit | 50 | 19,203.5 | 54,102.3 | 57,895.6 | 392.6 | 170.1 | 96,999.8 | 182.6 | 0.7 | 140s | 656,640 | 25,600 |  |
| contextpair | llama-3.2-3b-instruct-awq-int4 | 1 | 511.6 | 570.8 | 575.2 | 13.1 | 10.8 | 3,292.6 | 79.7 | 0.3 | 13s | 26,350 | 1,024 |  |
| contextpair | llama-3.2-3b-instruct-awq-int4 | 5 | 688.5 | 1,987.3 | 2,024.8 | 24.9 | 28.3 | 8,168.9 | 178.2 | 0.7 | 14s | 65,875 | 2,560 |  |
| contextpair | llama-3.2-3b-instruct-awq-int4 | 20 | 14,560.6 | 23,945.8 | 24,742.5 | 169.0 | 41.7 | 34,406.2 | 179.0 | 0.7 | 57s | 263,495 | 10,240 |  |
| contextpair | llama-3.2-3b-instruct-awq-int4 | 50 | 59,548.2 | 66,989.4 | 69,804.7 | 172.9 | 42.4 | 77,630.1 | 181.0 | 0.7 | 141s | 658,731 | 25,600 |  |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 27.2 | 48.8 | 56.6 | 7.8 | 7.6 | 4,975.5 | 132.6 | 0.4 | 20s | 1,228 | 2,681 |  |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 47.0 | 69.0 | 72.1 | 13.0 | 12.9 | 6,998.1 | 362.2 | 1.6 | 25s | 11,305 | 8,955 |  |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 72.0 | 279.3 | 281.0 | 25.3 | 22.3 | 13,823.9 | 866.0 | 3.8 | 42s | 37,857 | 36,574 |  |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 97.1 | 500.6 | 711.1 | 40.8 | 33.5 | 19,924.9 | 1,490.6 | 6.9 | 58s | 95,684 | 86,125 |  |
| solo | llama-3.2-3b-instruct-awq-int4 | 1 | 14.4 | 36.6 | 46.0 | 4.6 | 4.5 | 2,732.8 | 223.6 | 0.7 | 11s | 1,365 | 2,462 |  |
| solo | llama-3.2-3b-instruct-awq-int4 | 5 | 27.2 | 36.4 | 39.3 | 5.1 | 5.0 | 2,601.7 | 864.2 | 4.2 | 10s | 11,792 | 8,299 |  |
| solo | llama-3.2-3b-instruct-awq-int4 | 20 | 30.6 | 124.9 | 184.0 | 9.0 | 7.1 | 3,783.3 | 2,837.3 | 13.5 | 12s | 39,450 | 33,680 |  |
| solo | llama-3.2-3b-instruct-awq-int4 | 50 | 44.1 | 375.6 | 458.8 | 18.2 | 14.0 | 5,517.4 | 4,349.9 | 22.7 | 18s | 99,484 | 76,670 |  |

totals: 20.0 min of benchmarked load across 32 runs | 4,647,702 prompt tokens in | 670,329 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/p99 | TPOT mean/p99 | e2e mean/p99 | input tok mean/max | ≈tok in/out total | runtime |
|---|---|---|---|---|---|---|---|---|
| gemma | 20 | 5.08 | 234 / 1,084 | 37 / 47 | 3,876 / 5,299 | 2,022 / 4,317 | 630,810 / 30,997 | 61s |
| llama | 20 | 9.66 | 162 / 682 | 19 / 28 | 2,038 / 3,275 | 2,059 / 4,424 | 673,394 / 32,487 | 34s |
