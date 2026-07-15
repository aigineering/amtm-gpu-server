# solo-gemma-26b-a4b-8k-kv-172239b7cb

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


profile: **solo-gemma-26b-a4b-8k-kv** | config: `172239b7cb` | git: `5861469c6b` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T20:07:04Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 8,192 | 0.9 | 209,368 tok (21.2 GiB) | 25.56x @ 8,192 | native, 24 GB RAM | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 467.8 | 497.2 | 501.4 | 8.5 | 8.2 | 2,586.0 | 99.8 | 0.4 | 10s | 26,267 | 1,024 | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 545.2 | 1,364.7 | 1,406.3 | 14.6 | 18.6 | 5,493.4 | 270.3 | 1.1 | 9s | 65,667 | 2,560 | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 2,518.5 | 4,444.3 | 4,572.3 | 163.9 | 50.7 | 14,398.8 | 398.5 | 1.6 | 26s | 262,661 | 10,240 | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 1,255.1 | 20,257.8 | 22,142.2 | 205.6 | 109.7 | 48,179.3 | 422.2 | 1.6 | 61s | 656,640 | 25,600 | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 30.4 | 963.2 | 1,362.7 | 7.9 | 7.7 | 4,975.0 | 123.9 | 0.4 | 22s | 1,228 | 2,681 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 51.4 | 76.0 | 83.6 | 13.1 | 12.9 | 6,665.1 | 361.4 | 1.6 | 25s | 11,305 | 8,916 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 70.8 | 105.9 | 109.4 | 24.1 | 22.2 | 14,132.3 | 875.3 | 3.8 | 42s | 37,857 | 36,567 | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 97.1 | 581.1 | 705.8 | 43.6 | 34.2 | 19,978.6 | 1,488.2 | 6.9 | 58s | 95,684 | 86,350 | PASS |

totals: 4.2 min of benchmarked load across 8 runs | 1,157,309 prompt tokens in | 173,938 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/p99 | TPOT mean/p99 | e2e mean/p99 | input tok mean/max | ≈tok in/out total | runtime |
|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.16 | 65 / — | 8 / — | 861 / — | 2,056 / 2,838 | 32,892 / 1,660 | 14s |
| gemma-26b-a4b | 20 | 7.17 | 145 / 1,156 | 27 / 36 | 2,758 / 4,611 | 2,047 / 4,428 | 659,259 / 31,993 | 45s |
| gemma-26b-a4b | 5 | 3.48 | 83 / — | 13 / — | 1,399 / — | 2,049 / 4,429 | 172,079 / 8,305 | 24s |
| gemma-26b-a4b | 50 | 6.66 | 405 / 2,362 | 71 / 91 | 7,433 / 10,481 | 2,047 / 4,629 | 1,662,082 / 81,516 | 122s |
