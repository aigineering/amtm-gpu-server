# solo-gemma-26b-a4b-16k-kv-07bb7e8e50-m3

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


profile: **solo-gemma-26b-a4b-16k-kv** | config: `07bb7e8e50` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T22:50:50Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 16,384 | 0.9 | 352,443 tok (21.2 GiB) | 21.51x @ 16,384 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 1,057.2 | 1,059.1 | 1,059.1 | 9.1 | 8.7 | 3,268.1 | 78.4 | 0.3 | 13s | 52,481 | 1,024 | 2% | 0.0% | 0.0% | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 2,080.4 | 4,617.3 | 4,925.1 | 99.0 | 28.5 | 11,102.4 | 149.6 | 0.6 | 17s | 131,203 | 2,560 | 11% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 2,000.1 | 18,200.1 | 19,813.1 | 230.4 | 92.0 | 41,549.7 | 196.9 | 0.8 | 52s | 524,823 | 10,240 | 43% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 7,485.0 | 46,909.4 | 52,713.8 | 267.1 | 195.9 | 96,073.4 | 217.1 | 0.8 | 118s | 1,312,037 | 25,600 | 98% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 36.7 | 946.5 | 1,326.3 | 7.8 | 7.7 | 3,786.4 | 116.9 | 0.6 | 13s | 2,484 | 1,494 | 0% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 45.4 | 102.1 | 102.5 | 13.0 | 13.7 | 5,952.9 | 352.4 | 1.8 | 23s | 9,227 | 7,949 | 2% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 77.4 | 238.5 | 239.6 | 32.0 | 25.1 | 10,778.5 | 760.9 | 4.2 | 38s | 48,814 | 28,817 | 9% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 96.2 | 577.8 | 754.9 | 43.9 | 35.1 | 18,857.1 | 1,421.1 | 7.1 | 57s | 94,413 | 80,592 | 19% | 0.2% | 0.0% | PASS |

totals: 5.5 min of benchmarked load across 8 runs | 2,175,482 prompt tokens in | 158,276 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.17 | 59 / 91 | 8 / 8 | 853 / 958 | 2,056 / 2,838 | 32,892 / 1,660 | 1% | 78.6% | 0.0% | 1.55 / 0.00 GB | 14s |
| gemma-26b-a4b | 5 | 3.26 | 77 / 228 | 13 / 16 | 1,368 / 1,824 | 2,209 / 4,633 | 220,907 / 9,922 | 6% | 83.2% | 0.0% | 8.19 / 0.00 GB | 31s |
| gemma-26b-a4b | 20 | 6.91 | 134 / 1,172 | 25 / 34 | 2,594 / 4,538 | 2,137 / 4,428 | 788,390 / 36,656 | 22% | 81.9% | 0.1% | 31.04 / 0.04 GB | 53s |
| gemma-26b-a4b | 50 | 6.90 | 566 / 2,308 | 60 / 94 | 6,541 / 10,713 | 2,173 / 4,816 | 2,079,618 / 95,728 | 58% | 9.3% | 27.2% | 272.09 / 71.87 GB | 139s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-26b-a4b-c1.kvuse.txt`, `multiturn-gemma-26b-a4b-c20.kvuse.txt`, `multiturn-gemma-26b-a4b-c5.kvuse.txt`, `multiturn-gemma-26b-a4b-c50.kvuse.txt`
