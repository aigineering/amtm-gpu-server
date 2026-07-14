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

The default 0.6 (Gemma) / 0.3 (Llama) split (see
[vllm-configuration.md](vllm-configuration.md)) leaves ~10% headroom. With
`--enable-prefix-caching` on, cached prefixes accumulate in KV cache as more
conversations happen — if you see cache evictions or latency creeping up under real
traffic, that headroom (or lowering `--max-model-len`) is the first thing to revisit,
before assuming you need to shrink the other model's share.

## Re-benchmarking

Same loop as before: edit `group_vars/all.yml`, re-run with `--tags vllm`. The
container is recreated but the host isn't touched — the main cost of an iteration is
model load time from disk (see storage-type note above) plus KV cache warm-up before
prefix caching starts paying off.
