# solo-gemma-31b-8k-c3a010294a-m3

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


profile: **solo-gemma-31b-8k** | config: `c3a010294a` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T12:22:42Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 8,192 | 0.9 | 46,894 tok (19.0 GiB) | 5.72x @ 8,192 | off | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 2,843.1 | 2,868.3 | 2,870.9 | 31.6 | 31.4 | 10,868.2 | 23.6 | 0.1 | 43s | 26,265 | 1,024 | 7% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 5,927.2 | 13,049.8 | 13,867.9 | 40.8 | 82.1 | 31,963.0 | 52.7 | 0.2 | 49s | 65,663 | 2,560 | 38% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 27,174.9 | 65,652.4 | 70,442.5 | 1,085.8 | 186.0 | 112,811.9 | 62.7 | 0.2 | 163s | 262,663 | 10,240 | 99% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 148,366.7 | 166,308.5 | 177,877.5 | 1,063.7 | 185.1 | 212,997.1 | 65.7 | 0.3 | 390s | 656,637 | 25,600 | 99% | 0.0% | — | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 116.5 | 1,101.4 | 1,431.8 | 30.3 | 30.3 | 12,297.7 | 32.2 | 0.2 | 46s | 2,484 | 1,494 | 4% | 0.0% | — | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 131.6 | 553.5 | 554.1 | 32.0 | 35.6 | 17,493.0 | 122.9 | 0.6 | 64s | 9,227 | 7,915 | 9% | 0.0% | — | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 260.2 | 1,516.1 | 1,516.9 | 85.6 | 69.2 | 27,729.7 | 294.4 | 1.6 | 100s | 48,814 | 29,398 | 46% | 0.0% | — | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 50 | 315.2 | 4,153.1 | 4,991.8 | 201.3 | 112.4 | 47,710.0 | 551.4 | 2.7 | 146s | 94,413 | 80,237 | 92% | 0.0% | — | FAIL |

totals: 16.7 min of benchmarked load across 8 runs | 1,166,166 prompt tokens in | 158,468 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-31b | 1 | 0.30 | 210 / 421 | 31 / 31 | 3,361 / 3,747 | 2,056 / 2,838 | 32,892 / 1,660 | 5% | 78.6% | — | — | 54s |
| gemma-31b | 5 | 0.96 | 307 / 635 | 41 / 44 | 4,337 / 5,252 | 2,176 / 4,633 | 211,074 / 9,652 | 26% | 82.7% | — | — | 101s |
| gemma-31b | 20 | 1.00 | 2,243 / 6,962 | 164 / 228 | 18,393 / 28,287 | 2,138 / 4,428 | 793,186 / 36,936 | 99% | 17.5% | — | — | 370s |
| gemma-31b | 50 | 0.98 | 28,032 / 42,163 | 181 / 243 | 46,010 / 65,345 | 2,178 / 5,039 | 2,071,667 / 95,138 | 100% | 18.0% | — | — | 969s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-31b-c1.kvuse.txt`, `multiturn-gemma-31b-c20.kvuse.txt`, `multiturn-gemma-31b-c5.kvuse.txt`, `multiturn-gemma-31b-c50.kvuse.txt`
