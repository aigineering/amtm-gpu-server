# solo-gemma-31b-16k-kv-310b2ade39-m3

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


profile: **solo-gemma-31b-16k-kv** | config: `310b2ade39` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-16T09:02:43Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-31b | gemma-4-31b-it-awq-4bit | 16,384 | 0.9 | 78,941 tok (19.0 GiB) | 4.82x @ 16,384 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-31b` = gemma-4-31b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-31b-it-awq-4bit | 1 | 6,219.1 | 6,268.9 | 6,273.1 | 33.1 | 32.7 | 14,608.9 | 17.6 | 0.1 | 58s | 52,481 | 1,024 | 19% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 5 | 10,876.7 | 28,671.0 | 30,522.3 | 1,046.5 | 134.9 | 59,949.4 | 30.5 | 0.1 | 84s | 131,203 | 2,560 | 54% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 20 | 95,979.7 | 128,540.6 | 150,967.4 | 1,335.4 | 259.6 | 195,306.0 | 31.4 | 0.1 | 326s | 524,823 | 10,240 | 94% | 0.0% | 0.0% | FAIL |
| context | gemma-4-31b-it-awq-4bit | 50 | 334,469.5 | 351,568.6 | 389,606.9 | 1,352.4 | 259.8 | 416,736.8 | 31.3 | 0.1 | 819s | 1,312,037 | 25,600 | 95% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 1 | 116.4 | 1,128.1 | 1,468.3 | 30.3 | 30.3 | 12,324.2 | 32.1 | 0.2 | 47s | 2,484 | 1,494 | 4% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 5 | 131.9 | 558.5 | 559.0 | 32.2 | 40.8 | 17,571.9 | 122.8 | 0.6 | 65s | 9,227 | 7,949 | 9% | 0.0% | 0.0% | PASS |
| solo | gemma-4-31b-it-awq-4bit | 20 | 270.2 | 1,526.7 | 1,528.0 | 87.6 | 71.3 | 27,672.4 | 293.0 | 1.6 | 99s | 48,814 | 29,075 | 44% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-31b-it-awq-4bit | 50 | 314.5 | 3,964.6 | 4,770.4 | 200.0 | 119.9 | 43,078.2 | 561.1 | 2.8 | 143s | 94,413 | 79,980 | 91% | 0.0% | 0.2% | FAIL |

totals: 27.3 min of benchmarked load across 8 runs | 2,175,482 prompt tokens in | 157,922 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-31b | 1 | 0.30 | 208 / 412 | 31 / 31 | 3,364 / 3,746 | 2,056 / 2,838 | 32,892 / 1,660 | 5% | 78.6% | 0.0% | 6.21 / 0.00 GB | 54s |
| gemma-31b | 5 | 1.00 | 292 / 1,670 | 41 / 55 | 4,278 / 6,769 | 2,213 / 4,633 | 221,279 / 9,911 | 27% | 83.2% | 0.0% | 32.75 / 0.00 GB | 100s |
| gemma-31b | 20 | 0.96 | 2,291 / 8,496 | 166 / 242 | 18,591 / 30,208 | 2,163 / 4,889 | 813,160 / 37,506 | 100% | 14.5% | 3.3% | 554.43 / 26.51 GB | 393s |
| gemma-31b | 50 | 0.92 | 27,902 / 44,503 | 210 / 563 | 48,743 / 94,887 | 2,179 / 4,837 | 2,048,579 / 94,112 | 100% | 8.7% | 1.1% | 1473.31 / 128.94 GB | 1,023s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-31b-c1.kvuse.txt`, `multiturn-gemma-31b-c20.kvuse.txt`, `multiturn-gemma-31b-c5.kvuse.txt`, `multiturn-gemma-31b-c50.kvuse.txt`
