# Architecture

## Target host

A single RHEL 9 server with one NVIDIA L40S GPU (48GB VRAM). Two model server
processes share that one GPU:

| Instance      | Model                              | Served via  | Default port |
|---------------|-------------------------------------|-------------|--------------|
| `vllm-gemma`  | Gemma 4, 26B total / 4B active (MoE)| vLLM (OpenAI-compatible API) | 8001 |
| `vllm-llama`  | Llama 3.2 3B                         | vLLM (OpenAI-compatible API) | 8002 |

Both run as containers via Docker Compose, both requesting the same physical GPU
device. There is no MIG/vGPU partitioning — GPU sharing is done at the software level
via vLLM's `--gpu-memory-utilization` flag, which caps how much of the GPU's memory
each process pre-allocates for its KV cache and weights.

```
┌───────────────────────────── RHEL 9 host (L40S) ─────────────────────────────┐
│                                                                               │
│  ┌────────────────────────┐        ┌────────────────────────┐               │
│  │ vllm-gemma (container) │        │ vllm-llama (container) │               │
│  │ gemma-4 26B-A4B         │        │ llama-3.2-3b            │               │
│  │ --gpu-memory-utilization│        │ --gpu-memory-utilization│               │
│  │   0.6 (default)         │        │   0.3 (default)         │               │
│  │ :8001                   │        │ :8002                   │               │
│  └───────────┬─────────────┘        └───────────┬─────────────┘               │
│              │                                   │                            │
│              └─────────────── shared L40S GPU ───┘                            │
│                     (nvidia-container-toolkit / --gpus)                       │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Why one GPU, two processes, not MIG

L40S doesn't support MIG (that's an A100/H100 feature), so partitioning is done in
software via vLLM's memory utilization flag rather than at the hardware level. This is
intentional and matches the "play around with different configurations" goal — memory
splits, batch sizes, and even swapping which model gets the bigger share are all just
variable changes and a `docker compose up -d` away, no hardware reconfiguration.

## Layers Ansible manages

1. **OS baseline** (`common` role) — packages, kernel headers, and firewalld (detected
   first; only installed/enabled if not already active and `firewalld_manage: true`).
2. **NVIDIA driver** (`nvidia_driver` role) — detected first, installed/upgraded only if
   missing or below the pinned minimum version, and only when `nvidia_driver_manage`
   is true. See [nvidia-driver-management.md](nvidia-driver-management.md).
3. **Container runtime** (`docker` role) — Docker CE, the Compose plugin,
   `nvidia-container-toolkit`, and the SELinux boolean GPU containers need under
   Enforcing mode. Each piece is detected first and only changed when `docker_manage`
   / `selinux_manage` is true.
4. **vLLM services** (`vllm` role) — validates that each configured `model_path`
   exists on the host and looks like a full model repo, checks existing GPU
   memory/compute usage (read-only), renders `docker-compose.yml` from Ansible
   variables, and brings the two services up. Model repos are bind-mounted read-only
   into each container from the host — never downloaded. See
   [vllm-configuration.md](vllm-configuration.md) and
   [model-tuning-and-placement.md](model-tuning-and-placement.md).

Every gated step in 1–3 follows the same detect-then-manage pattern — see
[host-safety-model.md](host-safety-model.md) for the general rationale instead of
repeating it per layer.

## Two environments, one playbook

- `ansible/inventories/aws-test` — a clean EC2 instance (L40S-family, e.g. `g6e.xlarge`)
  used to validate the full playbook end-to-end, including driver installation from
  scratch.
- `ansible/inventories/customer` — the customer's existing RHEL server, which may
  already have NVIDIA drivers and possibly Docker installed by someone else before this
  repo existed. Same playbook, same roles — only `group_vars` differ.

The same `site.yml` runs against both; the roles are written to be safe re-run targets
either way (see [AGENTS.md](../AGENTS.md) for the idempotency ground rules).
