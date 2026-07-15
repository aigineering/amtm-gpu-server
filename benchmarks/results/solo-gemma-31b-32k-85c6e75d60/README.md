# solo-gemma-31b-32k-85c6e75d60

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


profile: **solo-gemma-31b-32k** | config: `85c6e75d60` | git: `eba2cf6f5a` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T18:38:22Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 32,768 | 0.9 | 46,894 tok | 5.72x @ 8,192 | off | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: 20 clients / 60 conversations

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 14,869.3 | 14,965.1 | 14,976.3 | 35.1 | 34.8 | 23,836.1 | 10.8 | 0.0 | 95s | 104,911 | 1,024 | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 20,644.9 | 68,305.5 | 73,344.1 | 1,455.1 | 275.9 | 134,379.2 | 14.7 | 0.1 | 174s | 262,277 | 2,560 | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 246,785.1 | 288,190.6 | 322,217.7 | 1,578.2 | 337.5 | 373,563.9 | 15.2 | 0.1 | 674s | 1,049,101 | 10,240 | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 748,739.3 | 765,962.3 | 821,315.9 | 1,602.1 | 338.0 | 850,412.0 | 15.2 | 0.1 | 1,682s | 2,622,740 | 25,600 | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 57.0 | 1,041.3 | 1,459.7 | 30.3 | 30.1 | 19,691.7 | 33.0 | 0.1 | 81s | 1,228 | 2,681 | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 202.6 | 412.7 | 413.4 | 33.4 | 35.8 | 17,561.8 | 125.1 | 0.6 | 71s | 11,305 | 8,825 | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 202.0 | 1,354.3 | 2,030.4 | 47.1 | 54.2 | 29,793.7 | 378.9 | 1.7 | 96s | 37,857 | 36,349 | PASS |
| solo | gemma-4-31b-it-awq-4bit | 50 | 316.7 | 4,209.6 | 5,050.8 | 183.5 | 111.1 | 47,764.6 | 575.4 | 2.7 | 149s | 95,684 | 85,768 | FAIL |

totals: 50.4 min of benchmarked load across 8 runs | 4,185,103 prompt tokens in | 173,047 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/p99 | TPOT mean/p99 | e2e mean/p99 | input tok mean/max | ≈tok in/out total | runtime |
|---|---|---|---|---|---|---|---|---|
| gemma-31b | 20 | 1.06 | 2,226 / 8,710 | 167 / 227 | 18,656 / 27,209 | 2,029 / 4,428 | 634,942 / 31,077 | 295s |
