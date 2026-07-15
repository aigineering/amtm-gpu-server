# Model placement and tuning (chat-focused)

This repo assumes **interactive chat serving**, not batch/offline scoring: many short
prompts, tokens streamed back to a human who's actively waiting, users idling between
turns, and a premium on time-to-first-token and per-token latency rather than maximum
aggregate tokens/sec across a queue. Every recommendation below is made with that
workload in mind — a deployment optimized for overnight batch scoring would tune
several of these knobs the other way.

It also assumes the **full model repository** (not just weight files) is already
present on the host — the normal apply (`site.yml`) never downloads a model. See
[vllm-configuration.md](vllm-configuration.md) for the `vllm_instances` variable
schema that points at it, and [model-fetching.md](model-fetching.md) for the
separate, opt-in playbook that can put it there in the first place (customer hosts
have no internet access by default).

## Model placement on disk

### Expected layout

`model_path` must point at a directory containing a complete Hugging Face–format
repo, e.g.:

```
/opt/models/gemma-4-26b-a4b-it-awq-4bit/
├── config.json
├── generation_config.json
├── tokenizer.json
├── tokenizer_config.json      # chat template lives here (or a separate chat_template.jinja)
├── special_tokens_map.json
├── model.safetensors.index.json   # for sharded weights
└── model-0000X-of-0000Y.safetensors
```

The `vllm` role checks for `model_path` existing and containing `config.json` before
every deploy and fails with a clear message if either is missing — it does not check
every file (tokenizer/weights) since a partial copy would surface as a much clearer
vLLM startup error at that point.

### Where to put them

- Keep model repos **outside** `vllm_deploy_dir` (`/opt/vllm` by default) — e.g.
  `/opt/models/<name>` — so re-running the `vllm` tag to change a serving flag never
  touches model data, and vice versa.
- Use **versioned subdirectories** if you expect to compare model revisions side by
  side, e.g. `/opt/models/gemma-4-26b-a4b-it-awq-4bit-v1`, `.../-v2`. Point `model_path` at
  whichever is under test rather than overwriting one directory in place — that way a
  bad benchmark run never silently destroys the previous known-good copy.
- **Storage type matters for iteration speed, not just steady-state serving.** Model
  load time happens on every container (re)start, which will happen often while
  benchmarking configurations — put model repos on local NVMe/SSD, not network
  storage, if you're iterating frequently.
- **Permissions**: the `vllm/vllm-openai` image runs as root inside the container by
  default and the compose template mounts `model_path` **read-only** (`:ro`) — the
  container never needs write access to it, and shouldn't have it.
- Rough disk footprint for the current AWQ 4-bit repos (confirm against the actual
  repo you copy over): Llama 3.2 3B AWQ-INT4 ≈ 2–3 GB; Gemma 4 26B-A4B AWQ-4bit ≈
  15–18 GB. Leave real headroom on the volume.

## Tuning vLLM for chat, not batch

Both example instances in `group_vars/all.yml` already set:

```yaml
extra_args:
  - "--enable-prefix-caching"
  - "--enable-chunked-prefill"
```

- **`--enable-prefix-caching`** — reuses KV cache across requests that share a prefix
  (a system prompt, or the growing history of a multi-turn conversation). This is
  usually the single biggest win for chat specifically, since each new turn in a
  conversation re-sends the entire prior history as a shared prefix. Batch/offline
  scoring jobs with mostly-unique prompts see much less benefit from this.
- **`--enable-chunked-prefill`** — splits long prompt prefill into chunks interleaved
  with other requests' decode steps, instead of letting one long prompt block token
  generation for everyone else. This improves fairness and tail latency when several
  conversations are active at once, at a small cost to raw throughput — the right
  trade for chat, the wrong one for maximizing a single big batch job's completion time.

### Other levers to reach for while benchmarking

Not set by default — add to `extra_args` as you tune:

| Flag | Effect | Chat guidance |
|---|---|---|
| `--max-num-seqs <N>` | Caps concurrent in-flight sequences | Bound this to keep per-user latency stable under load; too high trades latency for utilization, too low wastes GPU. Tune down if p50/p99 token latency degrades as concurrent chats increase. |
| `--max-num-batched-tokens <N>` | Token budget per scheduler step | Lower favors decode (chat) latency; higher favors prefill/batch throughput. |
| `--max-model-len` | Caps context length | Long chat histories cost KV cache memory per active conversation, which competes directly against how many concurrent chats fit within `gpu_memory_utilization`. Don't size this larger than real conversations need. |
| `--swap-space <GiB>` | CPU RAM used to overflow KV cache instead of erroring/evicting | Cheap insurance against bursty concurrent chat traffic; irrelevant for batch jobs sized to fit in GPU memory up front. |
| `--dtype` | Numeric precision | Leave `auto` unless you're specifically benchmarking a precision trade-off. |

### What NOT to reach for in this deployment

- Anything from vLLM's offline/batch scoring tooling (fixed-size batch jobs run once
  and exit) — this deployment always serves the OpenAI-compatible HTTP API
  continuously, it doesn't run one-shot batch jobs.
- Cranking `--max-num-batched-tokens` up purely to maximize aggregate tokens/sec — that
  optimizes for the wrong metric here (throughput over latency).

### Not server flags at all

**Sampling parameters** (`temperature`, `top_p`, `max_tokens`, `presence_penalty`,
etc.) are sent **per request** by the chat client calling `/v1/chat/completions` —
they're not vLLM server flags and don't belong in `extra_args`. Tune those in the
client/UI you're testing with.

**Streaming** likewise needs no server-side flag: a client sends `"stream": true` in
the request body and vLLM streams tokens back over Server-Sent Events on the same
endpoint automatically.

## GPU memory split, revisited for chat

The validated split on the L40S (~45 GiB usable) is **0.68 (Gemma) / 0.2 (Llama)**.
The original 0.6/0.3 guess failed on real hardware: `gpu_memory_utilization` caps an
instance's *total* footprint, and Gemma's ~16.6 GiB of AWQ weights plus vLLM's
profiling/cudagraph overhead left *negative* KV-cache memory inside a 27 GiB (0.6)
budget — the engine refuses to start with "No available memory for the cache
blocks". At 0.68 Gemma gets roughly 10 GiB of KV; Llama's 2.3 GiB of weights leave
~6 GiB of KV (≈7 concurrent 8k-token chats) inside 0.2.

Two related startup facts worth knowing when re-tuning:

- **Instances start serially, by design.** vLLM sizes its KV cache by profiling
  free GPU memory at startup; two engines profiling concurrently each see the
  other's in-flight allocations and compute garbage. The compose template chains
  `depends_on: service_healthy` so each instance waits for the previous one.
  `vllm_healthcheck_start_period` (default 600s) is the per-instance grace period.
- **Gemma is a multimodal model, capped to image input only.** Multimodal here
  means *input* (the model can receive and describe/analyze images) — never
  generation; vLLM only ever produces tokens. Without limits, vLLM profiles the
  video-encoder path at startup, burning several GiB of activation headroom.
  `--limit-mm-per-prompt '{"image": 2, "video": 0}'` in its `extra_args` allows
  up to 2 images per request and disables video. Image profiling still costs
  some KV headroom — if KV memory goes negative at startup after a config
  change, drop to `"image": 1` (or 0 for pure text) before reaching for a
  bigger `gpu_memory_utilization`.

With `--enable-prefix-caching` on, cached prefixes accumulate in KV cache as more
conversations happen — if you see cache evictions or latency creeping up under real
traffic, that headroom (or lowering `--max-model-len`) is the first thing to revisit,
before assuming you need to shrink the other model's share.

## KV memory rule of thumb: ≈1 GiB per 10k tokens

Measured on this deployment (fp16 KV cache; both numbers derived from the
serving logs — every vLLM startup prints the exact pair as
`Available KV cache memory: <GiB>` / `GPU KV cache size: <N> tokens`):

| Architecture | KV per token | per 10k tokens | one full 32k sequence |
|---|---|---|---|
| Llama 3.2 3B | ~112 KB (measured) | ~1.1 GiB | ~3.5 GiB |
| Llama 3.1 8B | ~128 KB (formula) | ~1.25 GiB | ~4.1 GiB |
| Gemma 4 31B | ~125 KB (measured) | ~1.2 GiB | ~4.0 GiB |
| Gemma 4 26B-A4B | TBD (read from stage-1 startup logs) | — | — |

Per **architecture**, not per quantization: quantization compresses weights,
never the KV cache (`kv_cache_dtype: auto` = fp16 for all catalog models — an
FP8 checkpoint does not imply an FP8 KV cache). So all four 31B variants share
one row; what differs between them is weight size, and therefore how much KV
*pool* remains — same cost per token, very different token budgets. Note also
that KV cost and parameter count are nearly decoupled here: the 8B costs about
the same per token as the 31B, and the 3B only ~12% less.

Formula, for a new model before it's measured:
`2 (K+V) × layers × kv_heads × head_dim × 2 bytes (fp16)` per token — but for
architectures with heterogeneous attention (Gemma-4's interleaved local/global
head dims), trust the startup-log numbers over the formula.

What ~1 GiB / 10k tokens means in practice:

- **KV is often bigger than the model.** One 32k conversation on the 3B costs
  more memory than the 3B's own weights (3.5 vs 2.3 GiB).
- **Window admission**: vLLM refuses to start unless the instance's KV pool
  holds at least ONE full `max_model_len` sequence — with ~4 GiB per 32k, a
  pair-config memory share can fail this check even though the weights fit.
- **Concurrency math is now mental arithmetic**: a ~20 GiB pool ÷ 26k-token
  requests ≈ 6 concurrent long-context users (exactly what the capacity runs
  observe); 150 multi-turn conversations at ~3k tokens ≈ 56 GiB of working
  set, which is why high-tier multi-turn is where CPU offloading gets tested.

## KV cache offloading to CPU RAM (not enabled — decision notes)

If GPU KV cache proves too small under real traffic (symptom: prefix-cache
evictions / rising latency in vLLM's logs and metrics as concurrent conversations
grow), evicted KV blocks can be parked in CPU RAM and pulled back over PCIe on
reuse instead of being recomputed. Two candidate approaches, **neither enabled**;
this section exists so the discussion doesn't restart from zero.

**Native vLLM offloading** (built-in CPU-offloading path for the prefix cache,
via vLLM's offloading connector / swap mechanism):

- Pros: config-only — no new dependency, same container image, fits this repo's
  offline-customer and minimal-moving-parts constraints.
- Cons: RAM-only tier, per-instance (no sharing between the two engines), fewer
  tuning knobs, capped by host RAM.

**LMCache** (external KV-cache layer plugged into vLLM's connector API):

- Pros: higher ceiling — disk tier below RAM, cache sharing across instances,
  smarter eviction, pipelined transfers, optional KV compression.
- Cons: version-coupled to vLLM (pin and re-validate on every image bump), and
  it must be verified to ship inside the exact `vllm/vllm-openai` image deployed
  — if it doesn't, we'd have to bake and distribute a custom image, a real cost
  given the customer host has no internet access.

**Hardware reality check:** the L40S itself is a good fit (single GPU over PCIe
gen4 is exactly what KV offloading targets — fetching a block is usually faster
than recomputing its prefill). The constraint is host RAM: the g6e.xlarge test
box has 32 GiB total (~24 GiB free with both engines loaded), so offloading buys
maybe 8–12 GiB on top of ~16 GiB of GPU KV. **Confirm the customer host's RAM**
before treating offloading as part of the production design; if it becomes
load-bearing, test on a host with comparable RAM (e.g. g6e.2xlarge, 64 GiB).

**Agreed escalation order:** (1) measure — no offloading until eviction shows up
in real workloads; (2) native vLLM offloading first, it's one `extra_args`
change; (3) LMCache only for a concrete need it alone solves (disk tier,
cross-instance sharing), after confirming image support.

## Re-benchmarking

Same loop as before: edit `group_vars/all.yml`, re-run with `--tags vllm`. The
container is recreated but the host isn't touched — the main cost of an iteration is
model load time from disk (see storage-type note above) plus KV cache warm-up before
prefix caching starts paying off.
