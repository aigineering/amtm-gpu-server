# Capacity & UX analysis — what this box can promise, per scenario

**Living analysis.** Interprets the measured benchmark data
([benchmarking.md](benchmarking.md), `benchmarks/results/`) into product
terms: how many users, what experience, where the limits are. Based on runs as
of 2026-07-15 (26B-A4B and 31B AWQ solo runs, baseline pair, kv-vs-off twin);
numbers firm up as the stage-1/2/3 campaign lands. Hardware: one L40S (48 GB),
g6e.2xlarge.

## Two SLO classes, not one

Interactive chat and long-running document work have different tolerance —
judging both by the chat SLO would wrongly condemn the latter.

| Class | Targets | Judged on |
|---|---|---|
| **Interactive** (chat, multi-turn) | TTFT p95 ≤ 1.5s (≤2.5s @50), ITL p95 ≤ 100ms | ShareGPT + multi-turn rows |
| **Async / batch** (document analysis, long-context jobs) — *proposed, confirm with client* | TTFT p95 ≤ 60s, e2e p95 ≤ 5 min, at a declared concurrency cap; UI shows progress, not a cursor | context rows |

## Active requests vs real users

Benchmark tiers count **simultaneously active requests**. Real chat users
read and type most of the time — at a 10–20% duty cycle, one active request
represents roughly 5–10 logged-in users. The "real users" column below uses
that translation; it is the honest-but-estimated part of this analysis and
should be recalibrated against the client's actual traffic once any exists.

## Scenario table (single L40S, measured evidence cited)

| Scenario | Model | Optimal active load | Real-user estimate | Experience at that load | Evidence |
|---|---|---|---|---|---|
| Short chat | 26B-A4B (MoE) | ~50 active; knee likely 100+ | ~250–500 | TTFT p95 <0.5s, 24 tok/s per user (3× reading speed) — indistinguishable from unloaded | solo c50: ITL 42ms, throughput still scaling 875→1,485 tok/s |
| Short chat | 31B (dense) | ~20–30 active; fails by 50 | ~100–200 | At 20: TTFT p95 1.4s, smooth streaming. At 50: TTFT 4.2s, ITL 184ms — visibly laggy | solo 32k run: PASS ≤20, FAIL @50 |
| Deep multi-turn (2–5k history) | 26B-A4B | ~20–50 rotating clients | ~150–400 | TTFT mean 145–405ms (cached history prefills), ~7 turns/s sustained | multi-turn c20/c50 tables |
| Both models co-located (production topology) | 26B + 3B | 50 + 50 active | several hundred | All SLO tiers PASS on both models | baseline run: 8/8 PASS |
| Long-document, occasional (≤32k) | 31B @ 32k | **async only**: ~4–6 concurrent jobs | a queue, not a crowd | 10–15s to first token per job alone; minutes when queued — fine for "analyzing…" UX, unacceptable for chat | context rows: c1 TTFT 15s; ~6 slots; c20 288s |
| Long-document, interactive at scale | any | **not viable on this box** | — | queueing collapses TTFT to minutes | context c20/c50 across profiles |

## The structural rule behind all of it

The box has two nearly independent budgets: **decode throughput** (rationed by
active user count — generous, especially for the MoE at ~4× the dense model's
per-token speed) and **prefill + KV memory** (rationed by context length —
scarce). The SLO knee moves gently with users and violently with context. In
product terms: user count is negotiable, promised context window is the real
commitment. Design consequences:

- Long-document work should be a **queued/async feature** with progress UI and
  a concurrency cap (the async SLO class), not part of the chat path.
- The chat window (`max_model_len`) should be sized to the largest supported
  *conversation*, not the model's maximum — see the admission-control
  reasoning in [model-tuning-and-placement.md](model-tuning-and-placement.md).
- KV offloading (as measured so far) costs a modest TTFT tail and pays off
  only when evicted context legitimately returns — a deep-conversation
  optimization, not a capacity multiplier ([benchmarking.md](benchmarking.md),
  twin analysis).

## Predictions to verify with the m2 campaign

1. 26B-A4B holds interactive SLO at c50 co-located with deep multi-turn — if
   so, the client's realistic mixed workload fits this GPU with headroom.
2. The 31B FP8 quants are capacity-non-viable (weights leave a KV pool too
   small for meaningful concurrency) regardless of quality.
3. Deep multi-turn (post `--no-early-stop`) produces enough legitimate reuse
   for `-kv` to beat its overhead at 16k/32k — the offload verdict.
4. Stage-2's real question is quality-vs-capacity: the MoE wins capacity
   outright; the dense 31B must justify itself on answer quality.
