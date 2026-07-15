# Benchmarking & evaluation definition

**Living document** — kept in sync with the ongoing design discussion. Records
what we evaluate, what we measure, on what data, plus decisions made and
options considered and rejected. Implementation lands in v0.2 (see
[roadmap.md](roadmap.md)).

## What we are evaluating

The server exists for **interactive conversations**: a human is waiting on the
other end, tokens stream back as they're generated, and several conversations
are active at once. That defines the workload we simulate and the metrics that
matter (see [model-tuning-and-placement.md](model-tuning-and-placement.md) for
how the same reasoning already shaped the serving flags).

Workload characteristics being modeled:

- Requests arrive irregularly (users think between turns), not in fixed batches.
- Input context grows over a conversation's turns; a system prompt is shared
  across all users of the same assistant.
- Outputs are chat-sized (roughly 100–500 tokens), streamed.
- Multiple independent conversations run concurrently against both models.

### Scenarios

1. **Solo baseline, per model** — each model benchmarked alone on the GPU (the
   other container stopped). Establishes the best case each model can do.
2. **Co-located (the product claim)** — both models loaded, load driven against
   **both endpoints simultaneously**. The delta vs scenario 1 quantifies the
   cost of sharing the GPU; this is the run that validates the two-models story
   for the client.
3. **Concurrency sweep** — scenarios 1 and 2 repeated at the three agreed user
   tiers — **5, 20 and 50 concurrent users** — plus a single-user reference
   point for the curve's floor. The tiers are where SLO pass/fail is judged.
4. **Context-length stress** — long-input requests near `max_model_len`,
   because long chat histories are where KV cache pressure and chunked-prefill
   behavior actually show up.

Each scenario runs against a named **profile** (models + quantization, GPU
memory split, context length, extra flags) so results are comparable across
configurations. The client's model/quant swap workflow is: define profile →
benchmark solo + co-located → compare against the incumbent from data.

## What we measure

### Primary metrics (chat UX)

| Metric | Why it matters | Reported as |
|---|---|---|
| TTFT (time to first token) | Perceived responsiveness — the "is it thinking?" gap | p50 / p95 / p99 |
| TPOT / ITL (per output token / inter-token latency) | Streaming smoothness once text starts | p50 / p95 |
| E2E request latency | Full-answer time for a complete response | p50 / p95 |
| Output token throughput (aggregate tok/s) | Capacity — how much total work the box does | mean |
| Request throughput (req/min) | Capacity in user terms | mean |

Latency percentiles outrank aggregate throughput on every trade-off — the same
priority order the serving flags were chosen for. In the co-located scenario,
every metric is reported **per model**, alongside its solo baseline and the
interference delta.

### Server-side metrics (captured alongside each run)

From vLLM's `/metrics` during the run: KV cache utilization, prefix-cache hit
rate, preemption/eviction counts, running/waiting queue depths. These explain
*why* a latency number moved, and produce exactly the evidence needed for the
parked KV-offloading decision ([model-tuning-and-placement.md](model-tuning-and-placement.md)).

### Working SLO targets (adopted from industry norms, 2026-07-15)

The client has no usage metrics yet, so targets are anchored to human
perception — the standard practice for chat serving:

- **TTFT** anchors to UI-responsiveness psychology: <500ms feels immediate,
  <1s responsive, >2–3s reads as broken.
- **Inter-token latency** anchors to reading speed: ~250 words/min ≈ 5–7
  tokens/s, so ≥10 tok/s per user stays ahead of the reader; ≥20 tok/s feels
  premium. Falling below reading speed is the visible UX cliff.

| Tier | TTFT p50 | TTFT p95 | ITL p95 (per-user tok/s) |
|---|---|---|---|
| 5 users | ≤ 500ms | ≤ 1.5s | ≤ 100ms (≥10 tok/s) |
| 20 users | ≤ 500ms | ≤ 1.5s | ≤ 100ms (≥10 tok/s) |
| 50 users | — | ≤ 2.5s | ≤ 100ms (≥10 tok/s) |

TTFT relaxes at 50 users (queueing on one shared GPU); ITL does not — once a
response streams, it must stay readable at any tier. A profile "passes" a tier
when both metrics meet targets in the **co-located** scenario. Revisit these
against real usage data once the client has any.

Sanity check against current practice (2026-07): serving literature states SLOs
on tail latency and optimizes "goodput" (throughput that still meets the SLO);
published production-chatbot P99 TTFT bounds run far looser (up to ~20s at
scale), so these targets are deliberately ambitious for a small dedicated box,
not lax. Methodology notes adopted from the same sources: **open-loop load
generation** (Poisson arrivals that don't slow down when the server does —
closed-loop generators flatter the results) and **p99 recorded alongside p95**
even where the SLO is stated at p95.

## Datasets

### Chosen

- **ShareGPT (primary)** — the standard conversational benchmark corpus; its
  input/output length distribution matches real chat traffic, and it's the
  de-facto baseline for comparing vLLM serving numbers with published results.
  A file download — must be fetched onto the box the same way models are
  (during an egress window; git-tracked or fetched by the benchmark playbook,
  TBD at implementation).
- **Synthetic/random (secondary)** — `vllm bench serve` built-in generator with
  controlled input/output lengths. No download, fully reproducible, and the
  only clean way to run the context-length stress scenario (exact lengths on
  demand). Caveat: random tokens defeat prefix caching, so its numbers are
  pessimistic for chat — used for controlled sweeps, not headline numbers.

### Multi-turn workload intensity — watch before trusting KV-offload deltas

Observation from the first baseline run (2026-07-15): the harness's **early
stop** ended the multi-turn pass after ~62s with only 3 of 60 conversations
fully finished (312 turn-samples — statistically fine for latency numbers, but
a short runtime accumulates little KV-cache pressure). For the stage-1
KV-offload on/off comparisons that pressure is the whole point: a too-light
workload makes offload-on and offload-off read identical and proves nothing.

Concrete "workload was too light" test — a run is valid for offload
comparisons only if ALL of these hold:

1. **Completion ≥ 80%** of generated conversations finished (baseline: 3/60 =
   5%, invalid), or the run used `--no-early-stop`.
2. **Sustained runtime ≥ 5 min** (baseline: 61s — too short to build cache
   pressure).
3. **Demand ratio ≥ ~1.5×**: active conversations × mean input tokens (from
   the multi-turn table) vs the engine's KV capacity in tokens (vLLM's startup
   log line "GPU KV cache size: N tokens"). Below 1×, eviction is
   arithmetically impossible.
4. **`-kv` runs**: the offload connector's counters in the `.metrics.txt`
   snapshot (blocks stored/loaded) are > 0 — zero means RAM was never touched
   and the comparison is void.
5. **Off runs**: prefix-cache eviction / preemption counters > 0.

If any fail, don't conclude "offloading doesn't help" — intensify and re-run.
Levers, in order: deeper conversations (`benchmark_multi_turn_turns_min/max`),
more conversations/clients (`benchmark_multi_turn_tiers`,
`benchmark_multi_turn_conversations_per_client`).

**Validated 2026-07-15 (26B @ 8k `-kv` run) — and defaults adjusted.** With the
harness's default early stop, the c50 run failed every criterion: 8/150
conversations completed (5%), 122s runtime, 1.47× demand ratio, 0.17 GB
loaded. Cause: early stop ends the whole benchmark when the first client
drains, so conversations never reach the deep turns that build cache pressure.
`--no-early-stop` is therefore the default now
(`benchmark_multi_turn_no_early_stop: true`) — full completion puts the c50
working set at ~3.5× the 8k pool with an estimated 4–8 min runtime, passing
all criteria without touching turn depths.

**First `-kv` run analysis (26B-A4B @ 8k, 2026-07-15) — assumptions checked.**
Multi-turn does exercise the prefix cache as designed: 42% GPU hit rate, ~1.1M
hit-tokens. Two findings from the same metrics: (1) the unexpected prefix hits
during solo/context stages were a **same-seed artifact** — every tier sampled
with the same seed, so later tiers re-sent earlier tiers' identical prompts
(the "random" context prompts regenerate byte-identically) and got cached
prefills, flattering mid-tier TTFT. Fixed: seeds now derive per scenario+tier
(`seed+tier` for ShareGPT, `+1000+tier` context, `+2000+tier` context-pair) —
still deterministic, so profile-to-profile comparability is unchanged, but
runs before the fix have optimistic mid-tier solo/context TTFT. (2) At 8k the
external cache is barely *used* (736 hit-tokens, 0.17 GB loaded back — the
209k-token GPU pool absorbs the multi-turn working set), while the store side
is busy regardless (~168 GB pushed to RAM during the c50 context run alone) —
so the kv-vs-off comparison of ShareGPT/context rows is a real measurement of
offloading's standing overhead, and offload *benefit* should be looked for at
bigger contexts / deeper conversations, as scoped.

**Twin comparison, 26B @ 8k kv-vs-off (2026-07-15, pre-seed-fix runs).**
The standing overhead of enabling offloading: ShareGPT TTFT p95 +6% (c1) to
+23% (c50, 474→581ms); ITL and throughput unchanged — the store side pushes
every eviction to RAM regardless of reuse, and that traffic costs TTFT tail
under load. The mechanism demonstrably works: context c20 showed −44% TTFT
(+14% throughput) from 1.72 GB reloaded out of RAM — but the reuse it
exploited was the same-seed artifact (identical prompts across tiers), so
that specific win disappears under the fixed seeds; its value is proof that
a RAM reload beats a multi-thousand-token recompute by a wide margin.
Multi-turn showed no benefit at any tier, consistent with the too-light
workload (shallow early-stopped conversations fit the pool). Net: at 8k with
light conversations, offloading is all cost (~modest) and no benefit — the
decisive test is deep multi-turn (post `--no-early-stop`) and larger contexts.

**Where `-kv` improvements can appear (expected signature).** ShareGPT and
context runs have (near-)zero prefix reuse, so offloading *cannot* help there
— those rows double as the idle-overhead control (expect flat or slightly
worse; a consistent regression is itself a finding). Gains are only possible
in the multi-turn rows, and only at tiers whose conversation working set
oversubscribes the GPU KV pool: c1/c5 fit entirely (control rows, expect
flat); c20 is borderline; **c50 is the main event** (~150 conversations ≈
2–3× the pool) — look for lower TTFT mean/p99 and higher req/s vs the off
run, corroborated by nonzero offload store/load counters and a higher
prefix-cache hit rate in the metrics snapshot. Best possible outcome:
identical everywhere except multi-turn c20/c50 — offloading helps under
pressure and costs nothing when idle.

### Multi-turn conversations (second harness)

`vllm bench serve` sends independent single-shot requests — it cannot replay a
conversation turn-by-turn, so on its own it under-exercises multi-turn
prefix-cache reuse. Resolution (2026-07-15): vLLM ships a dedicated tool,
**`benchmark_serving_multi_turn.py`** (vllm-project RFC #20265 / PR #20267),
that replays full sessions — each request carries the accumulated chat history,
parallel clients alternate between conversations with natural think-time, and
conversations come from ShareGPT-style JSON or a synthetic generator with
controllable turn counts and shared-prefix sizes. Same metric family
(TTFT/TPOT/e2e/throughput).

Division of labor: `vllm bench serve` produces the standard, externally
comparable single-shot numbers; the multi-turn harness produces the realistic
chat numbers and meaningful prefix-cache hit rates (which also feed the parked
KV-offloading decision). It lives in the vLLM repo's `benchmarks/` folder, not
the container image — we vendor a pinned copy into this repo (Apache-2.0,
provenance noted), which also satisfies the offline customer box.

### Planned: client-domain dataset

Agreed direction (2026-07-15): ShareGPT is the starting point, and a custom
dataset tailored to the client's needs will be added later — their actual
language and domain shift tokenizer efficiency and therefore every token-based
metric. The harness accepts custom dataset files, so this slots in without
redesign; results must record which dataset produced them (see below) so
ShareGPT-era numbers are never compared against client-dataset numbers by
accident.

## Result record: self-describing and reproducible

Requirement (2026-07-15): the client will tweak parameters over time, so every
result must embed **the actual configuration that produced it** — enough to
reproduce the run without archaeology. Each run's JSON carries:

- **Profile snapshot** — the fully resolved `vllm_instances` used for the run
  (models, quantization, `gpu_memory_utilization`, `max_model_len`, all
  `extra_args`), captured from what was *actually applied* on the host, not
  just the profile file's name — protecting against drift between the file and
  hand-tweaked reality. Plus the profile name as a label.
- **Code and image versions** — repo git SHA (and a dirty-tree flag), vLLM
  image tag + digest, model repo revisions.
- **Workload definition** — scenario, dataset name/version, concurrency tier,
  full harness command line and harness version.
- **Host fingerprint** — instance type, GPU model, driver version.
- **Timestamp** and the raw harness metrics output.

The comparison renderer treats any two runs whose profile snapshots differ as
different configurations, even if the profile *name* is the same.

## Implementation (v0.2)

| Piece | Where |
|---|---|
| Profiles | `ansible/profiles/<name>.yml` — `profile_name` + a full `vllm_instances` override; extra-vars beat group_vars. `baseline.yml` is the v0.1-validated config. |
| Apply a profile | `ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml --tags vllm -e @profiles/baseline.yml` |
| Benchmark it | `ansible-playbook -i inventories/aws-test/hosts.yml playbooks/benchmark.yml -e @profiles/baseline.yml` (`roles/benchmark`) |
| Dataset + multi-turn harness | fetched by `playbooks/fetch-models.yml` (same egress window as models) onto the models volume under `/opt/models/benchmark/`, multi-turn files pinned to a vLLM tag (`vllm_bench_pin`) |
| Raw results | `benchmarks/results/<run_id>/` — per-run `metadata.json` (the result record), one JSON per scenario/model/tier, `/metrics` snapshot after every run, multi-turn stdout as `.txt` |
| Comparison | `python3 benchmarks/render_results.py` — markdown tables + SLO PASS/FAIL on co-located rows; refuses to blur runs whose applied configs differ (grouping key = sha256 of the compose snapshot) |

Sequencing notes: solo runs stop the other container(s) and restart them
after; co-located tiers launch one bench container per endpoint in parallel
(tier = users **per model**); everything runs `--network host` against
localhost inside the serving image. First-run caveat: the exact
`vllm bench serve` / multi-turn CLI flags are per the pinned version's docs —
if the image's harness differs, the flags live in one place each
(`roles/benchmark/tasks/bench_single.yml`, `colocated_tier.yml`,
`multi_turn.yml`).

## Running the benchmark

Prerequisites, once per box (or per fresh models volume):

```bash
cd ansible
# 1. Serving stack deployed and healthy (site.yml has run)
# 2. Benchmark assets on the volume — fetch-models also downloads the
#    ShareGPT dataset and the multi-turn harness (skips models already present):
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/fetch-models.yml \
  --ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml
```

Then, per configuration you want to measure:

```bash
# 3. Apply the profile you want to measure (skip if it's already what's running)
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml \
  --tags vllm --ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml \
  -e @profiles/baseline.yml

# 4. Run the suite (expect ~1h for the full default matrix)
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/benchmark.yml \
  --ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml \
  -e @profiles/baseline.yml
```

The vault matters on both steps: it carries `vault_vllm_api_key`, which the
serving containers enforce and the bench/multi-turn harnesses authenticate
with (the key is redacted from the result records).

```bash

# 5. Render the comparison (from the repo root, on your machine)
python3 benchmarks/render_results.py            # all runs
python3 benchmarks/render_results.py <run_id>   # just one
```

Never run step 4 against a host serving real users — it drives heavy load and
stops/starts containers. Useful narrowing knobs (pass as `-e`):
`benchmark_scenarios='["colocated"]'` to skip solo runs,
`benchmark_concurrency_tiers='[5]'` for a quick single-tier check,
`benchmark_multi_turn=false` to skip the multi-turn pass. Each run leaves a
directory under `benchmarks/results/` — commit it; the history is the point.

### What a run looks like in the logs (progress tracking)

The load-generating tasks of a **solo profile** appear in this order — tiers
interleave the ShareGPT run and the context probe, then the multi-turn sweep
closes the run. Durations are for a 32k-context profile on the 31B; context
runs scale roughly linearly with the window (8k ≈ 4× faster), ShareGPT and
multi-turn runs barely change:

| # | Task in the log | ~duration (32k) |
|---|---|---|
| 1 | `Bench solo <model> c1` | 2 min |
| 2 | `Context <model> c1 (<ctx> ctx)` | 1–2 min |
| 3 | `Bench solo <model> c5` | 2–3 min |
| 4 | `Context <model> c5 (<ctx> ctx)` | 2–3 min |
| 5 | `Bench solo <model> c20` | 4–6 min |
| 6 | `Context <model> c20 (<ctx> ctx)` | 7–10 min |
| 7 | `Bench solo <model> c50` | 8–12 min |
| 8 | `Context <model> c50 (<ctx> ctx)` | 15–25 min — the long one |
| 9 | `Multi-turn: run each endpoint at each tier` (c1/c5/c20/c50) | 5–10 min total |

After #9 only bookkeeping remains (metrics snapshots, packaging, fetch,
render) — seconds. Two-instance profiles run this once per model for solo,
plus the co-located and context-pair sweeps. When dispatching a batch, order
profiles by curiosity: 8k profiles finish ~2× faster than 32k ones, so their
reports appear on the run page first.

**Campaigns: `ansible/run-campaign.sh`.** For a batch of profiles, the script
does apply → benchmark per profile with the vault password provided **once**
(via `ANSIBLE_VAULT_PASSWORD_FILE`, a gitignored `.vault_pass` at the repo
root, or a single prompt): `ansible/run-campaign.sh profiles/solo-gemma-*.yml`.
It stops at the first failure; because runs are resumable, re-running after a
fix continues where it stopped, and it renders the comparison table at the end.

**Runs are resumable.** The run id is `<profile>-<hash-of-applied-config>`,
not a timestamp: re-running the same profile+config resumes into the same
directory, and every result file already present is skipped — including the
whole stop/start model-reload cycle when an instance's solo tiers are all
done. Changing anything in the applied config changes the hash and starts a
fresh directory, so one directory can never mix configurations. To force a
redo, delete the run directory (or a specific result file) on the host under
`/opt/benchmark-results/`. Caveat: a *failed* multi-turn run still leaves its
output `.txt` as a completion marker — delete that file to retry it.

## Interpreting results

Each rendered table row is one (scenario, model, user-tier) combination:

- **The SLO column is the verdict.** It's judged only on `colocated` rows
  (that's the deployment reality) against the working targets above. A profile
  is acceptable at a tier when both its models PASS there.
- **Solo vs co-located is the cost of sharing.** The same model/tier appearing
  in both scenarios differs only by contention: TTFT p95 growing sharply on
  co-located rows means the models are fighting for prefill compute; ITL
  degradation means decode interference. Small deltas (≲20%) are the expected
  price of one GPU; large ones justify revisiting the GPU split before
  anything else.
- **Watch the trend across tiers, not just the pass/fail.** TTFT that's fine
  at 5 and 20 users but cliffs at 50 is queueing — the box's honest capacity
  is between those tiers. ITL failing at every tier is a configuration
  problem (split, `max_model_len`), not a capacity problem.
- **`*.metrics.txt` explains *why*.** Each run's vLLM `/metrics` snapshot
  shows KV-cache usage, prefix-cache hit rate, and preemption counts —
  rising preemptions/evictions alongside degrading latency is the signal that
  feeds the KV-offloading decision
  ([model-tuning-and-placement.md](model-tuning-and-placement.md)).
- **`multiturn-*.txt`** holds the multi-turn statistics table (ttft_ms /
  tpot_ms / latency_ms percentile rows printed by the harness). These are the
  realistic-chat numbers; expect better prefix-cache behavior than the
  single-shot runs show.
- **Compare configurations only within the same config id.** The renderer
  groups by the hash of the applied compose file and warns when one profile
  name spans different configs — those runs measured different things,
  whatever their label says.

The comparison loop for the client's model/quant swaps: benchmark the
incumbent profile, benchmark the challenger profile, and put their co-located
tables side by side — same tiers, same dataset, same seed make the numbers
directly comparable.

## Model evaluation campaign (planned, 2026-07-15)

Goal: a clear per-model performance picture across the fetched catalog, and a
validated co-location choice. Eight servable models (the nine-repo catalog
minus bge-m3, an embedding model outside this campaign).

### Three workload instruments, three questions

| Instrument | Question it answers | Caveat |
|---|---|---|
| ShareGPT (`vllm bench serve`) | Realistic short-chat latency/throughput; externally comparable headline numbers | Sampler uses only each conversation's FIRST turn (~tens-to-hundreds of input tokens) — never exercises large contexts |
| Multi-turn (synthetic, controllable turns/prefix) | Cache-economy under growing histories: prefix-cache hit rates, deep-conversation latency, and **the KV-offloading evaluation** — offloading's value is reuse-after-eviction (idle conversation evicted to RAM, pulled back on the next turn), which only this workload produces | Input depth is what we configure it to be (~2–7k tokens typical) |
| Random long-input (`vllm bench serve --dataset-name random`) | **Capacity mapping — a first-class deliverable**: hard memory limits per model × context × concurrency, e.g. "does 32k context + two models fit on this GPU, at how many users" | Zero prefix reuse — deliberately worst-case; not a realistic-traffic number |

### Campaign stages (Simon's design, 2026-07-15)

1. **Parameter baseline — two model types** (12 profiles, committed as
   `profiles/solo-gemma-{31b,26b-a4b}-{8k,16k,32k}[-kv].yml`): the dense 31B
   AWQ and the MoE 26B-A4B AWQ, solo at 0.9 GPU utilization, full matrix of
   context (8k/16k/32k) × KV offloading (off / 24GB native CPU offload,
   `--kv-offloading-backend native --kv-offloading-size 24`). Establishes how
   context and offloading affect each model *type* with everything else held
   constant. Each profile runs the tier sweep, ShareGPT + context-stress +
   multi-turn (~30–45 min/profile; ~6–9h total, resumable).
2. **Catalog pass — all 8 servable models** (2 configs each: 8k and 32k, KV
   setting per stage-1's verdict). Ranks the catalog and picks the 3B
   companion. Profiles written after stage 1 concludes.
3. **Co-location — top 2–4 models from stage 2 + the chosen 3B**: pair
   profiles, again across all context sizes × KV on/off, full suite including
   the parallel pair capacity runs (`contextpair-*` — the "does 32k + two
   models fit, at how many users" answer) and SLO verdicts.

Profile naming: `solo-<model>-<ctx>[-kv]`, `pair-<big>-<small>-<ctx>[-kv]`.

## Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-07-15 | Performance only in v0.2; quality evals deferred | Perf validates the co-location claim and profile comparisons now; quality gates (quant accuracy impact) are a separate, slower effort |
| 2026-07-15 | Harness: `vllm bench serve`, run on-host against localhost | Ships inside the deployed vLLM image (versioned together, works on the offline customer box); tunnel/SSH overhead would skew latency at high concurrency |
| 2026-07-15 | Results git-tracked in repo (JSON per run + comparison renderer) | History and diffs for free; external store only pays off at high run volume |
| 2026-07-15 | ShareGPT primary + synthetic secondary datasets | Realistic conversational distribution for headline numbers; controlled lengths for sweeps and context stress |
| 2026-07-15 | Concurrency tiers: 5 / 20 / 50 users (+1-user floor) | The three cases to test per Simon; SLO pass/fail judged at each tier |
| 2026-07-15 | Client-tailored dataset planned as follow-up to ShareGPT | Client's language/domain shifts token-based metrics; harness supports custom files |
| 2026-07-15 | Every result embeds its resolved profile + versions (see "Result record") | Client will tweak params; results must be reproducible and never silently compared across differing configs |
| 2026-07-15 | SLOs adopted from industry norms (perception-anchored), pending client data | Customer has no usage metrics; TTFT anchors to UI responsiveness, ITL to reading speed |
| 2026-07-15 | Implementation stays playbook-based (Ansible roles/playbooks, no side tooling) | Same operating model as the rest of the repo; agentless, works against the offline customer box |
| 2026-07-15 | Second harness: vLLM's `benchmark_serving_multi_turn.py`, **fetched pinned to the models volume** (revised from "vendor into repo") | Only tool that replays real multi-turn sessions; fetching it during the egress window (pinned to `vllm_bench_pin`) gives the same offline guarantee without carrying third-party code in the repo |
| 2026-07-15 | Open-loop (Poisson) load generation; p99 recorded alongside p95 | Closed-loop generators self-throttle and flatter results; SLO practice judges tails |
| 2026-07-15 | Evaluation campaign restructured per Simon: (1) ctx×KV baseline on the two AWQ gemmas, (2) all models at 8k+32k with the stage-1 KV verdict, (3) top 2–4 + 3B pairs across all ctx×KV | Stage 1 isolates parameter sensitivity per model type (dense vs MoE) before spending GPU-hours on the full catalog; each stage's results parameterize the next |
| 2026-07-15 | Capacity mapping via random long-input is a first-class deliverable (Simon) | The client must know hard memory limits — "32k + two models: fits or not, at how many users" — answered directly by worst-case no-reuse runs |
| 2026-07-15 | KV offloading evaluated separately, on the multi-turn workload | Offloading's value is reuse-after-eviction, which only multi-turn traffic produces; random no-reuse runs can't show it. Constrained configs + one idle-overhead control |
| 2026-07-15 | Multi-turn harness deps (pandas/xlsxwriter) installed to pylibs/ on the models volume via the container's pip | vLLM image doesn't ship them; container pip = right ABI; volume placement survives resets and is offline afterwards |

## Considered and rejected (for now)

- **Attention backend as a benchmark/profile dimension** (FlashAttention-2 /
  FlashInfer vs the default) — rejected 2026-07-15. Gemma-4's heterogeneous
  head dims (256 sliding / 512 full-attention) rule out every alternative:
  FlashInfer supports head sizes ≤256 and fails at engine init
  (vllm-project/vllm#40677), FA2 likewise — Triton is forced *because* it's
  the only backend that handles the mix. Llama already defaults to FA2, and
  as the 3B side-model its FA2-vs-FlashInfer delta can't move the headline
  numbers. Revisit if vLLM ships FA4 or FlashInfer adds head-512 support.
  (Hardware note: gemma's Triton fallback needs ~96KB shared memory/SM —
  fine on the L40S at 100KB, breaks on Turing-class GPUs; relevant if the
  customer's hardware ever changes.)

- **guidellm** — capacity-planning sweeps (max sustainable RPS). Extra
  dependency; add later only if the client asks for capacity numbers. The
  playbook design leaves room for a second harness.
- **Custom load generator (locust/k6)** — full control over traffic shape, but
  all maintenance is ours; not justified until canned workloads prove
  unrepresentative.
- **Load generation through the SSH tunnel** — rejected; encryption overhead
  and tunnel throughput poison latency percentiles at high concurrency.
- **Quality evals in v0.2** (lm-eval-harness / promptfoo) — deferred, see
  decisions log.
- **External results store (SQLite/dashboard)** — deferred until run volume
  demands it.

## Open items

- Revisit SLO targets when the client has real usage data (working targets
  adopted from industry norms meanwhile).
- Client-domain/language dataset — planned, needs the client's traffic profile.
- ~~How the ShareGPT file gets onto the box~~ — decided: the fetch playbook
  downloads it (and the multi-turn harness) alongside the models.
- Validate the harness CLI flags against the deployed image on the first real
  run (see Implementation, first-run caveat).
