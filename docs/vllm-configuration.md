# vLLM configuration

## Design goal

The two vLLM instances (Gemma, Llama) need to be re-configured and re-benchmarked
repeatedly — different GPU memory splits, different vLLM flags, possibly different
models entirely. Nothing model- or GPU-split-specific should be hardcoded in the role;
it should all come from Ansible variables so a config change is a one-line edit and a
re-run, not a template edit.

## Where variables live

`ansible/inventories/<env>/group_vars/all.yml` defines a `vllm_instances` list. The
`vllm` role loops over it to render one service per entry into
`roles/vllm/templates/docker-compose.yml.j2`.

```yaml
vllm_instances:
  - name: gemma
    model_path: "/opt/models/gemma-4-26b-a4b-it-awq-4bit"   # full local repo, already on the host
    port: 8001
    gpu_memory_utilization: 0.68
    max_model_len: 8192
    extra_args:
      - "--enable-prefix-caching"
      - "--enable-chunked-prefill"
      - "--limit-mm-per-prompt"
      - '{"image": 2, "video": 0}'

  - name: llama
    model_path: "/opt/models/llama-3.2-3b-instruct-awq-int4"
    port: 8002
    gpu_memory_utilization: 0.2
    max_model_len: 8192
    extra_args:
      - "--enable-prefix-caching"
      - "--enable-chunked-prefill"
```

`name` and `model_path` are required; everything else has a default in
`roles/vllm/defaults/main.yml`. Instances start one at a time (each waits for
the previous one's `/health`; grace period `vllm_healthcheck_start_period`,
default 600s) because concurrent vLLM startups corrupt each other's GPU memory
profiling — see [model-tuning-and-placement.md](model-tuning-and-placement.md). `model_path` must point at a full local Hugging Face
repo already present on the host — see
[model-tuning-and-placement.md](model-tuning-and-placement.md) for the expected
layout, disk/permission guidance, and why `extra_args` defaults to those two flags
for a chat-focused deployment.

## GPU memory split

`gpu_memory_utilization` is the fraction of *total* GPU memory (0.0–1.0) each vLLM
process is allowed to claim for weights + KV cache. On a 48GB L40S:

- `gemma: 0.6` → ~29GB reserved for the Gemma instance
- `llama: 0.3` → ~14GB reserved for the Llama instance
- ~10% headroom left unclaimed for CUDA context overhead, driver, etc.

The two values don't have to sum to 1.0 — leaving headroom avoids OOM if either model's
actual usage runs slightly over its nominal share. When experimenting, change these
values in `group_vars/all.yml` and re-run the `vllm` role tag; don't hand-edit the
rendered compose file (it will be overwritten on the next run).

## Re-running with a new configuration

```bash
# edit ansible/inventories/aws-test/group_vars/all.yml, then:
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml --tags vllm
```

This re-renders `docker-compose.yml` and runs `docker compose up -d`, which recreates
only the containers whose config actually changed.

## Model source: local mount, not download

This repo assumes the full model repository is already present on the host — the
`vllm` role only bind-mounts `model_path` read-only into the container at
`/models/<name>` and passes that path to `--model`. It never contacts Hugging Face Hub
(`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` are set in the container to guarantee
that), so there's no HF token, license gate, or network dependency at deploy time —
getting the model repo onto the host in the first place is out of scope for this role.
See [model-tuning-and-placement.md](model-tuning-and-placement.md) for the directory
layout the role expects and validates before every deploy.

## Adding a third instance / swapping a model

Copy the new model's full repo onto the host, then add an entry to `vllm_instances`
with a unique `name`, `port`, and its `model_path`, and reduce the other entries'
`gpu_memory_utilization` so the total plus headroom stays under 1.0. The role and
compose template require no changes.
