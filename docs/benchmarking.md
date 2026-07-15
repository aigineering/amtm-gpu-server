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
| 2026-07-15 | Second harness: vLLM's `benchmark_serving_multi_turn.py`, vendored at a pinned version | Only tool that replays real multi-turn sessions (history + think-time + shared prefixes); not in the container image, so vendor it (Apache-2.0) for the offline box |
| 2026-07-15 | Open-loop (Poisson) load generation; p99 recorded alongside p95 | Closed-loop generators self-throttle and flatter results; SLO practice judges tails |

## Considered and rejected (for now)

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
- How the ShareGPT file gets onto the box (fetch playbook vs git-tracked
  subset) — decide at implementation.
