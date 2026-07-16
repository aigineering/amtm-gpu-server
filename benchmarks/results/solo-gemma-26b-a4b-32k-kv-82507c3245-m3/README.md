# solo-gemma-26b-a4b-32k-kv-82507c3245-m3

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


profile: **solo-gemma-26b-a4b-32k-kv** | config: `82507c3245` | git: `4aa512b44f` | host: g6e.2xlarge (NVIDIA L40S, 610.43.02) | image: vllm/vllm-openai:latest | first run: 2026-07-15T23:34:30Z

### Configuration

| instance | model | context window | GPU mem fraction | KV pool | max conc @ctx | KV offload | other flags |
|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | gemma-4-26b-a4b-it-awq-4bit | 32,768 | 0.9 | 535,354 tok (21.2 GiB) | 16.34x @ 32,768 | native, 40 GB RAM | `--enable-prefix-caching --enable-chunked-prefill --limit-mm-per-prompt {"image": 2, "video": 0}` |

workload: dataset=sharegpt | tiers=[1, 5, 20, 50] | prompts/user=8 | seed=42 | scenarios=['solo'] | context-stress inputs≈80% of window, 256 out | multi-turn: tiers [1, 5, 20, 50] × 3 conv/client, 12-18 turns

served (observed): `gemma-26b-a4b` = gemma-4-26b-a4b-it-awq-4bit

| scenario | model | users | TTFT p50 | TTFT p95 | TTFT p99 | ITL p95 | TPOT p95 | E2E p95 | out tok/s | req/s | run dur | in tok | out tok | KV use | GPU hit | ext hit | SLO |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| context | gemma-4-26b-a4b-it-awq-4bit | 1 | 2,621.9 | 2,662.3 | 2,668.0 | 9.9 | 9.4 | 5,066.1 | 50.8 | 0.2 | 20s | 104,909 | 1,024 | 3% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 5 | 4,913.3 | 11,578.8 | 12,434.6 | 241.3 | 52.9 | 22,988.7 | 77.5 | 0.3 | 33s | 262,273 | 2,560 | 19% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 20 | 4,311.1 | 46,441.5 | 50,530.5 | 331.6 | 200.9 | 97,586.0 | 90.1 | 0.4 | 114s | 1,049,103 | 10,240 | 67% | 0.0% | 0.0% | FAIL |
| context | gemma-4-26b-a4b-it-awq-4bit | 50 | 69,451.8 | 118,700.9 | 129,218.3 | 344.1 | 254.5 | 182,750.8 | 93.8 | 0.4 | 273s | 2,622,737 | 25,600 | 85% | 0.0% | 0.0% | FAIL |
| solo | gemma-4-26b-a4b-it-awq-4bit | 1 | 37.9 | 912.1 | 1,277.0 | 7.8 | 7.7 | 3,750.7 | 117.3 | 0.6 | 13s | 2,484 | 1,494 | 0% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 5 | 44.7 | 103.8 | 104.2 | 13.0 | 13.9 | 5,942.0 | 352.5 | 1.8 | 23s | 9,227 | 7,949 | 1% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 20 | 78.8 | 258.2 | 259.7 | 33.0 | 24.3 | 10,795.0 | 758.8 | 4.2 | 38s | 48,814 | 28,749 | 9% | 0.0% | 0.0% | PASS |
| solo | gemma-4-26b-a4b-it-awq-4bit | 50 | 97.5 | 456.5 | 695.1 | 42.1 | 33.8 | 18,529.5 | 1,433.2 | 7.1 | 56s | 94,413 | 80,588 | 20% | 0.2% | 0.0% | PASS |

totals: 9.5 min of benchmarked load across 8 runs | 4,193,960 prompt tokens in | 158,204 tokens generated

### Multi-turn conversations

| instance | clients | req/s | TTFT mean/tail | TPOT mean/tail | e2e mean/tail | input tok mean/max | ≈tok in/out total | KV use | GPU hit | ext hit | KV stored/loaded | runtime |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gemma-26b-a4b | 1 | 1.16 | 65 / 104 | 8 / 8 | 859 / 962 | 2,056 / 2,838 | 32,892 / 1,660 | 1% | 78.6% | 0.0% | 1.55 / 0.00 GB | 14s |
| gemma-26b-a4b | 5 | 3.18 | 77 / 91 | 13 / 14 | 1,360 / 1,646 | 2,197 / 4,633 | 217,476 / 9,831 | 6% | 83.0% | 0.0% | 8.13 / 0.00 GB | 31s |
| gemma-26b-a4b | 20 | 6.68 | 130 / 1,017 | 26 / 33 | 2,644 / 4,269 | 2,161 / 4,889 | 808,363 / 37,126 | 22% | 82.3% | 0.1% | 31.34 / 0.04 GB | 56s |
| gemma-26b-a4b | 50 | 7.09 | 545 / 2,698 | 59 / 93 | 6,375 / 10,552 | 2,170 / 5,039 | 2,070,628 / 95,514 | 58% | 8.5% | 29.6% | 262.23 / 77.28 GB | 134s |

unparsed multi-turn files (failed or unexpected format): `multiturn-gemma-26b-a4b-c1.kvuse.txt`, `multiturn-gemma-26b-a4b-c20.kvuse.txt`, `multiturn-gemma-26b-a4b-c5.kvuse.txt`, `multiturn-gemma-26b-a4b-c50.kvuse.txt`
