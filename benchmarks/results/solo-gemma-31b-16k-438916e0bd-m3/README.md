# solo-gemma-31b-16k-438916e0bd-m3

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


profile: **solo-gemma-31b-16k** | config: `438916e0bd` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T00:43:12Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 16,384 | 0.9 | 78,941 tok (19.0 GiB) | 4.82x @ 16,384 | off | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 6,191.6 | 6,227.6 | 6,229.7 | 33.1 | 32.7 | 14,563.6 | 17.6 | 0.1 | 58s | 52,481 | 1,024 | 19% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 10,945.9 | 28,711.1 | 30,573.6 | 1,050.3 | 135.5 | 60,210.8 | 30.4 | 0.1 | 84s | 131,203 | 2,560 | 55% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 87,901.9 | 125,915.9 | 147,169.9 | 1,224.6 | 238.0 | 186,489.6 | 33.3 | 0.1 | 307s | 524,823 | 10,240 | 95% | 0.0% | — | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 316,312.0 | 333,919.3 | 370,618.5 | 1,240.0 | 245.5 | 396,567.2 | 33.1 | 0.1 | 773s | 1,312,037 | 25,600 | 95% | 0.0% | — | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 115.4 | 1,082.6 | 1,404.4 | 30.4 | 30.3 | 12,279.5 | 32.2 | 0.2 | 46s | 2,484 | 1,494 | 3% | 0.0% | — | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 131.4 | 550.9 | 551.4 | 32.1 | 41.1 | 17,573.4 | 122.8 | 0.6 | 65s | 9,227 | 7,949 | 7% | 0.0% | — | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 259.5 | 1,497.3 | 1,498.6 | 87.4 | 69.0 | 27,584.6 | 293.5 | 1.6 | 99s | 48,814 | 29,028 | 45% | 0.0% | — | PASS |
| solo | gemma-4-31b-it-awq-4bit | 50 | 314.1 | 3,905.8 | 5,111.5 | 201.0 | 119.3 | 44,267.4 | 552.1 | 2.8 | 145s | 94,413 | 80,053 | 88% | 0.0% | — | FAIL |

totals: 26.3 min of benchmarked load across 8 runs | 2,175,482 prompt tokens in | 157,948 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-31b | 1 | 0.30 | 206 / 410 | 31 / 31 | 3,357 / 3,745 | 2,056 / 2,838 | 32,892 / 1,660 | 5% | 78.6% | — | — | 54s |
| gemma-31b | 5 | 1.02 | 306 / 477 | 41 / 43 | 4,338 / 5,245 | 2,178 / 4,633 | 209,124 / 9,549 | 25% | 82.7% | — | — | 94s |
| gemma-31b | 20 | 0.98 | 2,237 / 8,151 | 168 / 229 | 18,746 / 29,227 | 2,153 / 4,638 | 798,633 / 36,892 | 100% | 18.6% | — | — | 378s |
| gemma-31b | 50 | 0.98 | 28,681 / 43,553 | 182 / 247 | 46,687 / 67,079 | 2,180 / 5,039 | 2,084,433 / 95,628 | 100% | 18.5% | — | — | 980s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-31b-c1.kvuse.txt`, `multiturn-gemma-31b-c20.kvuse.txt`, `multiturn-gemma-31b-c5.kvuse.txt`, `multiturn-gemma-31b-c50.kvuse.txt`
