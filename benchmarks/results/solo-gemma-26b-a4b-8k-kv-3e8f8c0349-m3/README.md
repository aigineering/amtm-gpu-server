# solo-gemma-26b-a4b-8k-kv-3e8f8c0349-m3

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


profile: **solo-gemma-26b-a4b-8k-kv** | config: `3e8f8c0349` | git: `bebdbe2a04` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T21:46:38Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 8,192 | 0.9 | 209,368 tok (21.2 GiB) | 25.56x @ 8,192 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 465.9 | 501.2 | 506.2 | 8.5 | 8.2 | 2,592.4 | 99.7 | 0.4 | 10s | 26,265 | 1,024 | 0% | 0.0% | 0.0% | PASS |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 1,069.5 | 2,004.3 | 2,138.6 | 14.7 | 19.6 | 6,437.8 | 229.5 | 0.9 | 11s | 65,663 | 2,560 | 7% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 1,133.7 | 7,912.2 | 8,556.5 | 177.2 | 51.9 | 21,092.9 | 353.4 | 1.4 | 29s | 262,663 | 10,240 | 31% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 1,252.9 | 20,198.6 | 22,103.6 | 198.0 | 109.4 | 48,082.0 | 423.6 | 1.7 | 60s | 656,637 | 25,600 | 78% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 35.1 | 952.0 | 1,334.1 | 7.9 | 7.7 | 3,792.3 | 116.7 | 0.6 | 13s | 2,484 | 1,494 | 0% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 45.0 | 104.4 | 104.8 | 13.0 | 13.2 | 5,971.2 | 352.5 | 1.8 | 22s | 9,227 | 7,923 | 2% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 77.1 | 206.6 | 254.1 | 32.2 | 23.3 | 10,802.4 | 761.9 | 4.2 | 38s | 48,814 | 28,944 | 8% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 96.4 | 510.5 | 729.2 | 44.1 | 33.5 | 18,621.7 | 1,432.3 | 7.1 | 56s | 94,413 | 80,567 | 18% | 0.2% | 0.0% | PASS |

totals: 4.0 min of benchmarked load across 8 runs | 1,166,166 prompt tokens in | 158,352 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.16 | 58 / 84 | 8 / 8 | 855 / 960 | 2,056 / 2,838 | 32,892 / 1,660 | 1% | 78.6% | 0.0% | 1.55 / 0.00 GB | 14s |
| gemma-26b-a4b | 5 | 3.17 | 78 / 290 | 13 / 16 | 1,359 / 1,841 | 2,200 / 4,633 | 220,037 / 9,940 | 6% | 83.1% | 0.0% | 8.19 / 0.00 GB | 32s |
| gemma-26b-a4b | 20 | 6.75 | 132 / 1,122 | 26 / 34 | 2,662 / 4,443 | 2,162 / 4,889 | 804,204 / 37,002 | 22% | 82.1% | 0.1% | 31.23 / 0.04 GB | 55s |
| gemma-26b-a4b | 50 | 7.04 | 577 / 2,440 | 60 / 93 | 6,483 / 10,812 | 2,170 / 5,290 | 2,059,671 / 94,966 | 57% | 7.3% | 28.5% | 266.91 / 74.08 GB | 135s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-26b-a4b-c1.kvuse.txt`, `multiturn-gemma-26b-a4b-c20.kvuse.txt`, `multiturn-gemma-26b-a4b-c5.kvuse.txt`, `multiturn-gemma-26b-a4b-c50.kvuse.txt`
