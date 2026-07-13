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
    model: "CHANGEME/gemma-4-26b-a4b"   # confirm exact HF repo id before deploying
    port: 8001
    gpu_memory_utilization: 0.6
    max_model_len: 8192
    extra_args: []

  - name: llama
    model: "meta-llama/Llama-3.2-3B-Instruct"
    port: 8002
    gpu_memory_utilization: 0.3
    max_model_len: 8192
    extra_args: []
```

Every field is optional except `name` and `model` — the role has sane defaults for
port allocation, memory utilization, etc. defined in `roles/vllm/defaults/main.yml`.

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

## Model IDs and licensing

Both Gemma and Llama weights are gated on Hugging Face and require an accepted license
+ an HF token available on the target host (`HUGGING_FACE_HUB_TOKEN`, injected via the
`vllm_hf_token` variable — keep this in an Ansible Vault–encrypted file, never commit it
in plaintext). The `CHANGEME` placeholder in the Gemma model ID above must be replaced
with the exact repo ID/revision you've confirmed access to before running against any
real host.

## Adding a third instance / swapping a model

Add another entry to `vllm_instances` with a unique `name` and `port`, and reduce the
other entries' `gpu_memory_utilization` so the total plus headroom stays under 1.0. The
role and compose template require no changes.
