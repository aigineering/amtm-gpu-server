# solo-gemma-31b-8k-kv-e5688e0a33-m3

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


profile: **solo-gemma-31b-8k-kv** | config: `e5688e0a33` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T05:31:20Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 8,192 | 0.9 | 46,894 tok (19.0 GiB) | 5.72x @ 8,192 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 2,829.0 | 2,832.7 | 2,833.0 | 31.7 | 31.6 | 10,877.7 | 23.6 | 0.1 | 43s | 26,265 | 1,024 | 7% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 5,845.8 | 13,001.7 | 13,812.3 | 40.7 | 81.6 | 31,775.1 | 53.0 | 0.2 | 48s | 65,663 | 2,560 | 43% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 27,340.5 | 66,023.8 | 70,783.1 | 1,122.0 | 191.4 | 114,416.6 | 61.5 | 0.2 | 167s | 262,663 | 10,240 | 99% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 156,995.0 | 173,714.7 | 186,299.9 | 1,182.8 | 198.4 | 223,131.2 | 62.3 | 0.2 | 411s | 656,637 | 25,600 | 99% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 116.8 | 1,090.0 | 1,415.0 | 30.3 | 30.3 | 12,284.5 | 32.2 | 0.2 | 46s | 2,484 | 1,494 | 4% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 131.0 | 564.6 | 565.1 | 32.1 | 41.1 | 17,554.2 | 122.9 | 0.6 | 65s | 9,227 | 7,949 | 7% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 266.5 | 1,518.1 | 1,519.0 | 85.3 | 69.3 | 27,301.9 | 295.3 | 1.6 | 98s | 48,814 | 28,993 | 43% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 50 | 315.4 | 3,073.0 | 4,799.1 | 204.4 | 120.3 | 43,953.3 | 556.6 | 2.8 | 144s | 94,413 | 80,052 | 90% | 0.0% | 0.2% | FAIL |

totals: 17.0 min of benchmarked load across 8 runs | 1,166,166 prompt tokens in | 157,912 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-31b | 1 | 0.30 | 209 / 416 | 31 / 31 | 3,364 / 3,745 | 2,056 / 2,838 | 32,892 / 1,660 | 5% | 78.6% | 0.0% | 6.21 / 0.00 GB | 54s |
| gemma-31b | 5 | 1.01 | 301 / 1,341 | 41 / 56 | 4,302 / 6,522 | 2,218 / 4,633 | 221,806 / 9,934 | 25% | 83.2% | 0.1% | 32.79 / 0.03 GB | 99s |
| gemma-31b | 20 | 0.98 | 2,511 / 9,155 | 166 / 238 | 18,896 / 31,768 | 2,137 / 4,638 | 782,288 / 36,431 | 100% | 13.5% | 2.7% | 539.55 / 28.10 GB | 374s |
| gemma-31b | 50 | 0.93 | 27,835 / 46,292 | 215 / 654 | 49,160 / 103,575 | 2,180 / 4,837 | 2,072,752 / 95,271 | 100% | 7.2% | 1.2% | 1479.80 / 134.90 GB | 1,027s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-31b-c1.kvuse.txt`, `multiturn-gemma-31b-c20.kvuse.txt`, `multiturn-gemma-31b-c5.kvuse.txt`, `multiturn-gemma-31b-c50.kvuse.txt`
