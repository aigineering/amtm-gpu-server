# Roadmap

## v0.1 — done

End-to-end validated on the AWS test env: scripted provisioning
([aws-test-env.md](aws-test-env.md)), model fetch, detect-then-manage roles for
driver/Docker/firewalld/SELinux, and two AWQ models (Gemma 4 26B-A4B, Llama 3.2
3B) serving concurrently on one L40S with the validated 0.68/0.2 split
([model-tuning-and-placement.md](model-tuning-and-placement.md)). Endpoints
smoke-tested (text + image input) through the SSH tunnel.

## v0.2 — evaluation & profiles (next)

Goal: stop hand-testing and start measuring. The client needs to swap models
and quantizations with confidence, and to *prove* the two-models-on-one-GPU
story holds under load.

1. **Benchmark suite, programmatic.** A repeatable run that benchmarks each
   model individually (latency: TTFT / time-per-output-token / e2e percentiles;
   throughput under swept concurrency) and both models **simultaneously** — the
   contention run is the one that validates the product claim, and comparing it
   against the solo runs quantifies the cost of co-location.
2. **Profiles.** A named, versioned definition of a serving configuration:
   which models (and quantization), GPU memory split, max context length, and
   the relevant `extra_args`. Applying a profile and benchmarking it should be
   one command each. Chat-focused metrics come first (see
   [model-tuning-and-placement.md](model-tuning-and-placement.md) for why).
3. **Result tracking.** Every benchmark run recorded with its profile name, git
   commit, model revisions, and raw metrics — comparable across runs, so
   "profile A vs profile B" and "AWQ vs other quant of the same model" are
   answerable from data instead of memory.
4. **Model/quantization swap validation.** The client workflow: fetch a new
   model or quant, define a profile, benchmark it solo + co-located, compare
   against the incumbent. Documentation for that loop.

Decisions (settled 2026-07-15):

- **Performance only** for v0.2 — quality evals (quantization accuracy impact)
  deferred to a later phase.
- **Harness: `vllm bench serve`**, run on the GPU host against localhost (the
  tunnel's SSH overhead skews latency at high concurrency). It ships inside the
  deployed vLLM image, so it's versioned with the server and works on the
  offline customer box. guidellm can be added later if capacity-planning
  numbers (max sustainable RPS) are requested — the orchestration should leave
  room for a second harness.
- **Results git-tracked in this repo**: one JSON per run tagged with profile
  name, git SHA and timestamp, plus a comparison-table renderer. Revisit an
  external store only at high run volume.

## Later / parked

- KV cache offloading to CPU RAM — decision notes captured in
  [model-tuning-and-placement.md](model-tuning-and-placement.md); revisit only
  when prefix-cache evictions show up in benchmark results (v0.2 will produce
  exactly the evidence needed).
- Single-endpoint router in front of the two instances (e.g. an
  OpenAI-compatible gateway aggregating both `/v1/models`) if the customer
  wants one URL instead of two ports.
- Customer host RAM confirmation (prerequisite for any offloading decision).
