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

Open decisions (see the benchmarking-options discussion before implementing):

- Performance-only first, or performance + quality evals (does a given
  quantization degrade answer quality)?
- Benchmark harness choice and where it runs (on-host over localhost vs from
  the control machine through the tunnel — tunnel throughput and SSH overhead
  skew latency numbers at high concurrency).
- Where results live (git-tracked files in this repo vs external store).

## Later / parked

- KV cache offloading to CPU RAM — decision notes captured in
  [model-tuning-and-placement.md](model-tuning-and-placement.md); revisit only
  when prefix-cache evictions show up in benchmark results (v0.2 will produce
  exactly the evidence needed).
- Single-endpoint router in front of the two instances (e.g. an
  OpenAI-compatible gateway aggregating both `/v1/models`) if the customer
  wants one URL instead of two ports.
- Customer host RAM confirmation (prerequisite for any offloading decision).
