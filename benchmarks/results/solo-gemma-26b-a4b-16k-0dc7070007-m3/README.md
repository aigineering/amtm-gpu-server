# solo-gemma-26b-a4b-16k-0dc7070007-m3

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


profile: **solo-gemma-26b-a4b-16k** | config: `0dc7070007` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T23:13:36Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 16,384 | 0.9 | 352,443 tok (21.2 GiB) | 21.51x @ 16,384 | off | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 1,056.0 | 1,058.5 | 1,058.6 | 9.1 | 8.7 | 3,269.8 | 78.3 | 0.3 | 13s | 52,481 | 1,024 | 2% | 0.0% | — | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 2,076.1 | 4,628.5 | 4,940.4 | 114.6 | 28.6 | 11,079.1 | 149.1 | 0.6 | 17s | 131,203 | 2,560 | 10% | 0.0% | — | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 1,995.6 | 18,298.5 | 19,945.9 | 224.4 | 92.9 | 41,896.5 | 195.2 | 0.8 | 52s | 524,823 | 10,240 | 43% | 0.0% | — | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 7,506.4 | 47,079.8 | 52,604.1 | 242.3 | 193.6 | 95,929.8 | 218.3 | 0.9 | 117s | 1,312,037 | 25,600 | 100% | 0.0% | — | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 34.6 | 918.8 | 1,287.2 | 7.8 | 7.7 | 3,756.1 | 117.3 | 0.6 | 13s | 2,484 | 1,494 | 0% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 44.6 | 96.3 | 96.7 | 12.9 | 13.7 | 5,953.9 | 352.2 | 1.8 | 23s | 9,227 | 7,949 | 1% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 75.8 | 251.5 | 252.9 | 31.8 | 23.5 | 10,983.5 | 760.6 | 4.2 | 38s | 48,814 | 29,036 | 9% | 0.0% | — | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 96.2 | 581.4 | 707.1 | 41.6 | 34.2 | 18,781.0 | 1,431.1 | 7.1 | 56s | 94,413 | 80,645 | 18% | 0.2% | — | PASS |

totals: 5.5 min of benchmarked load across 8 runs | 2,175,482 prompt tokens in | 158,548 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.17 | 54 / 78 | 8 / 8 | 850 / 958 | 2,056 / 2,838 | 32,892 / 1,660 | 0% | 78.6% | — | — | 14s |
| gemma-26b-a4b | 5 | 3.20 | 75 / 93 | 13 / 14 | 1,363 / 1,641 | 2,192 / 4,633 | 216,999 / 9,846 | 5% | 83.0% | — | — | 31s |
| gemma-26b-a4b | 20 | 6.68 | 124 / 1,024 | 25 / 34 | 2,594 / 4,500 | 2,152 / 4,428 | 802,684 / 37,154 | 22% | 82.2% | — | — | 56s |
| gemma-26b-a4b | 50 | 6.16 | 384 / 2,242 | 71 / 93 | 7,413 / 10,741 | 2,174 / 4,816 | 2,059,062 / 94,917 | 57% | 22.0% | — | — | 154s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-26b-a4b-c1.kvuse.txt`, `multiturn-gemma-26b-a4b-c20.kvuse.txt`, `multiturn-gemma-26b-a4b-c5.kvuse.txt`, `multiturn-gemma-26b-a4b-c50.kvuse.txt`
