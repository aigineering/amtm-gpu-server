# solo-gemma-26b-a4b-32k-88cdbcd143-m3

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


profile: **solo-gemma-26b-a4b-32k** | config: `88cdbcd143` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T00:00:23Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 32,768 | 0.9 | 535,354 tok (21.2 GiB) | 16.34x @ 32,768 | off | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 2,623.8 | 2,640.9 | 2,643.3 | 9.9 | 9.4 | 5,042.6 | 50.9 | 0.2 | 20s | 104,909 | 1,024 | 5% | 0.0% | — | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 4,745.0 | 11,610.9 | 12,477.2 | 245.6 | 53.1 | 23,274.2 | 77.4 | 0.3 | 33s | 262,273 | 2,560 | 16% | 0.0% | — | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 4,294.1 | 46,625.4 | 50,770.1 | 329.4 | 200.8 | 97,797.3 | 89.9 | 0.4 | 114s | 1,049,103 | 10,240 | 68% | 0.0% | — | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 70,499.4 | 120,238.6 | 131,003.5 | 337.1 | 256.5 | 185,321.3 | 92.7 | 0.4 | 276s | 2,622,737 | 25,600 | 85% | 0.0% | — | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 34.4 | 914.2 | 1,280.5 | 7.8 | 7.7 | 3,751.5 | 117.4 | 0.6 | 13s | 2,484 | 1,494 | 1% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 43.9 | 103.8 | 104.2 | 13.0 | 13.7 | 5,955.4 | 352.6 | 1.8 | 23s | 9,227 | 7,949 | 2% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 78.7 | 249.6 | 250.4 | 31.8 | 23.6 | 10,850.8 | 757.8 | 4.2 | 38s | 48,814 | 29,103 | 8% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 96.5 | 457.9 | 706.6 | 42.2 | 34.4 | 18,823.0 | 1,428.1 | 7.1 | 57s | 94,413 | 80,908 | 20% | 0.2% | — | PASS |

totals: 9.6 min of benchmarked load across 8 runs | 4,193,960 prompt tokens in | 158,878 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.17 | 54 / 78 | 8 / 8 | 851 / 958 | 2,056 / 2,838 | 32,892 / 1,660 | 1% | 78.6% | — | — | 14s |
| gemma-26b-a4b | 5 | 3.21 | 78 / 95 | 13 / 14 | 1,369 / 1,650 | 2,175 / 4,633 | 208,779 / 9,531 | 6% | 82.7% | — | — | 30s |
| gemma-26b-a4b | 20 | 6.40 | 128 / 1,110 | 25 / 35 | 2,639 / 4,493 | 2,166 / 4,889 | 805,763 / 37,110 | 22% | 82.3% | — | — | 58s |
| gemma-26b-a4b | 50 | 6.10 | 387 / 2,169 | 70 / 91 | 7,383 / 10,437 | 2,185 / 4,837 | 2,106,465 / 96,544 | 57% | 21.7% | — | — | 158s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-26b-a4b-c1.kvuse.txt`, `multiturn-gemma-26b-a4b-c20.kvuse.txt`, `multiturn-gemma-26b-a4b-c5.kvuse.txt`, `multiturn-gemma-26b-a4b-c50.kvuse.txt`
