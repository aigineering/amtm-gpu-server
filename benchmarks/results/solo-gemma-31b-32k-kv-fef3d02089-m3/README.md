# solo-gemma-31b-32k-kv-fef3d02089-m3

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
| KV use | Peak GPU KV cache usage DURING the run (scraped from the engine's periodic log; the post-run gauge reads ~0 once load drains) |
| GPU hit | GPU prefix-cache hit rate during that row (Δhits/Δqueries vs the previous snapshot in the run) |
| ext hit | External (RAM-offloaded) prefix-cache hit rate during that row — requires KV offloading |
| SLO | PASS/FAIL against the working targets (docs/benchmarking.md): TTFT p95 ≤ 1.5s (≤2.5s at 50 users) AND ITL p95 ≤ 100ms. Evaluated on every row; read per scenario — `colocated` is the binding product judgment, `solo` is a model's standalone ceiling, and `context`/`contextpair` failing at high tiers is the expected capacity cliff (worst-case probe), not a defect |

**Multi-turn conversations table** — conversation replay with growing
history (prefix-cache and KV-offloading behavior), parsed from the harness
reports; raw reports remain in `multiturn-*.txt`.

| Column | Meaning |
|---|---|
| req/s | Completed turns per second |
| TTFT / TPOT / e2e mean/tail | ms; tail = p99, falling back to p90 or max when small runs omit percentiles |
| input tok mean/max | Input tokens per request — shows how deep conversations grew |
| ≈tok in/out total | Approximate totals (count × mean; the harness reports distributions, not sums) |
| KV use / GPU hit / ext hit | Same meaning as the main-table columns, per tier (deltas vs the previous tier's snapshot, starting at the c0 baseline) |
| KV stored/loaded | GB pushed to / pulled back from CPU RAM during that tier |


profile: **solo-gemma-31b-32k-kv** | config: `fef3d02089` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T01:47:06Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 32,768 | 0.9 | 119,913 tok (19.0 GiB) | 3.66x @ 32,768 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 14,706.2 | 14,903.7 | 14,918.2 | 35.2 | 34.9 | 23,799.6 | 10.8 | 0.0 | 94s | 104,909 | 1,024 | 23% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 21,946.9 | 68,062.4 | 73,108.0 | 1,442.1 | 274.3 | 131,861.5 | 14.8 | 0.1 | 173s | 262,273 | 2,560 | 81% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 265,897.9 | 306,764.8 | 343,167.0 | 1,704.7 | 362.0 | 398,158.5 | 14.3 | 0.1 | 718s | 1,049,103 | 10,240 | 98% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 809,232.4 | 824,994.0 | 877,183.6 | 1,740.1 | 364.1 | 917,643.5 | 14.2 | 0.1 | 1,807s | 2,622,737 | 25,600 | 98% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 116.2 | 1,090.8 | 1,415.8 | 30.4 | 30.3 | 12,286.5 | 32.2 | 0.2 | 46s | 2,484 | 1,494 | 4% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 131.9 | 572.1 | 572.5 | 32.1 | 41.3 | 17,557.2 | 122.8 | 0.6 | 65s | 9,227 | 7,949 | 8% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 250.9 | 1,534.7 | 1,535.8 | 84.4 | 69.5 | 27,315.1 | 296.2 | 1.6 | 99s | 48,814 | 29,363 | 45% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 50 | 314.9 | 3,086.6 | 4,798.8 | 189.5 | 118.4 | 44,452.1 | 556.6 | 2.8 | 144s | 94,413 | 80,297 | 91% | 0.0% | 0.2% | FAIL |

totals: 52.4 min of benchmarked load across 8 runs | 4,193,960 prompt tokens in | 158,527 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-31b | 1 | 0.30 | 208 / 415 | 31 / 31 | 3,364 / 3,745 | 2,056 / 2,838 | 32,892 / 1,660 | 5% | 78.6% | 0.0% | 6.20 / 0.00 GB | 54s |
| gemma-31b | 5 | 1.00 | 307 / 1,701 | 41 / 57 | 4,301 / 6,590 | 2,221 / 4,633 | 222,132 / 9,920 | 26% | 83.2% | 0.0% | 32.78 / 0.00 GB | 100s |
| gemma-31b | 20 | 0.98 | 2,297 / 6,971 | 168 / 240 | 18,758 / 30,391 | 2,126 / 4,428 | 778,236 / 36,438 | 100% | 16.9% | 2.2% | 538.02 / 7.95 GB | 373s |
| gemma-31b | 50 | 0.97 | 28,383 / 44,203 | 186 / 354 | 46,783 / 72,163 | 2,167 / 4,837 | 2,043,132 / 94,479 | 100% | 9.7% | 0.7% | 1448.14 / 129.89 GB | 970s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-31b-c1.kvuse.txt`, `multiturn-gemma-31b-c20.kvuse.txt`, `multiturn-gemma-31b-c5.kvuse.txt`, `multiturn-gemma-31b-c50.kvuse.txt`
