# solo-gemma-26b-a4b-8k-2d44e6f25d

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
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md): TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms. Evaluated on every row; read per scenario — `colocated` is the binding product judgment, `solo` is a model's standalone ceiling, and `context`/`contextpair` failing at high tiers is the expected capacity cliff (worst-case probe), not a defect |

**Multi-turn conversations table** (conversation replay with growing history —
prefix-cache and KV-offloading behavior): parsed from the harness reports.
Columns: req/s (completed turns per second), TTFT/TPOT/e2e mean/p99 (ms —
the harness's report truncates mid percentiles when piped, so mean is the
stable center),
input tokens per request mean/max (shows how deep conversations grew), and
approximate total tokens in/out (count × mean — the harness reports
distributions, not exact sums). Raw reports remain in `multiturn-*.txt`.


profile: **solo-gemma-26b-a4b-8k** | config: `2d44e6f25d` | git: `5861469c6b` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T20:28:10Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 8,192 | 0.9 | 209,368 tok (21.2 GiB) | 25.56x @ 8,192 | off | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 466.8 | 468.8 | 468.9 | 8.5 | 8.2 | 2,548.2 | 100.6 | 0.4 | 10s | 26,267 | 1,024 | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 553.2 | 1,364.7 | 1,436.3 | 14.5 | 18.7 | 5,492.4 | 267.6 | 1.0 | 10s | 65,667 | 2,560 | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 1,169.9 | 7,893.4 | 8,557.4 | 172.5 | 52.5 | 21,141.4 | 349.1 | 1.4 | 29s | 262,661 | 10,240 | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 1,244.0 | 20,159.1 | 22,058.0 | 189.7 | 109.5 | 48,066.3 | 423.3 | 1.7 | 60s | 656,640 | 25,600 | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 27.3 | 904.5 | 1,280.9 | 7.8 | 7.6 | 4,978.8 | 124.4 | 0.4 | 22s | 1,228 | 2,681 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 49.5 | 69.1 | 71.7 | 13.1 | 13.0 | 7,149.9 | 363.8 | 1.6 | 25s | 11,305 | 9,043 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 69.5 | 94.2 | 98.9 | 24.1 | 22.3 | 14,050.7 | 875.6 | 3.8 | 42s | 37,857 | 36,533 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 96.6 | 473.6 | 702.7 | 42.3 | 33.7 | 20,227.0 | 1,484.6 | 6.9 | 58s | 95,684 | 86,457 | PASS |

totals: 4.3 min of benchmarked load across 8 runs | 1,157,309 prompt tokens in | 174,138 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/p99 | TPOT mean/p99 | e2e mean/p99 | input tok mean/max | ≈tok in/out total | runtime |
|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.17 | 54 / — | 8 / — | 851 / — | 2,056 / 2,838 | 32,892 / 1,660 | 14s |
| gemma-26b-a4b | 20 | 7.34 | 136 / 1,095 | 26 / 34 | 2,690 / 4,441 | 2,051 / 4,428 | 656,243 / 31,824 | 44s |
| gemma-26b-a4b | 5 | 3.47 | 80 / — | 13 / — | 1,401 / — | 2,049 / 4,429 | 172,079 / 8,305 | 24s |
| gemma-26b-a4b | 50 | 6.66 | 395 / 2,363 | 71 / 93 | 7,441 / 10,571 | 2,053 / 4,816 | 1,670,995 / 81,619 | 122s |
