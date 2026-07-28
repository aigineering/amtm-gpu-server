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

### API key (`vllm_api_key`)

When `vllm_api_key` is non-empty (wired in group_vars as
`{{ vault_vllm_api_key | default('') }}` — set it via `ansible-vault` in the
same `vault.yml` as the HF token), every instance requires
`Authorization: Bearer <key>` on `/v1/*`. `/health` and `/metrics` stay open,
so healthchecks and metrics scraping keep working. The key is injected as the
`VLLM_API_KEY` environment variable in the rendered compose file (mode 0600 on
the host), and the benchmark suite authenticates automatically (bench serve via
`OPENAI_API_KEY`, the multi-turn harness via `--api-key`) while redacting the
key from result records. Client-side:

```bash
curl http://<host>:8001/v1/chat/completions \
  -H "Authorization: Bearer <key>" -H 'Content-Type: application/json' -d '…'
```

This exists because the test box's security group exposes 8001/8002 publicly —
an unauthenticated OpenAI-compatible endpoint on a public IP gets found and
abused. Rotate by changing the vault value and re-running `--tags vllm`.

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


## TLS (HTTPS)

By default every vLLM instance listens on plain HTTP. To enable TLS set **both**
of the following variables in `group_vars/all.yml`:

| Variable | Description |
|---|---|
| `vllm_tls_cert_file` | Absolute path on the **host** to the PEM certificate (or full chain). |
| `vllm_tls_key_file` | Absolute path on the **host** to the PEM private key. |

Both default to `""` (empty). The feature is disabled unless both are set to
non-empty values. Setting only one is a configuration error — the playbook will
fail immediately with a clear message before any containers are touched.

### Path and permissions expectations

* Both paths must be absolute and point to files already present on the host before
  the playbook runs (the role never generates or fetches them).
* The files are bind-mounted **read-only** into every container at `/tls/cert.pem`
  and `/tls/key.pem`.
* Permissions: the certificate file may be world-readable; the key file should be
  readable only by root (`0600` or `0640`). Docker mounts with whatever permissions
  the host file has — the `vllm` process runs as root inside the container and will
  read it regardless.

### Example group_vars snippet

```yaml
# ansible/inventories/<env>/group_vars/all.yml

# TLS — leave both empty (the default) to keep plain HTTP.
vllm_tls_cert_file: "/etc/ssl/vllm/server.crt"   # full chain PEM
vllm_tls_key_file:  "/etc/ssl/vllm/server.key"   # private key PEM
```

The role validates that cert and key are **both present or both absent**; if only
one is set the play fails with:

```
Partial TLS configuration: set both vllm_tls_cert_file and vllm_tls_key_file,
or leave both empty to disable TLS. Only one was provided.
```

### Resulting vLLM invocation (with TLS enabled)

When both variables are set the rendered `docker-compose.yml` includes the following
extra mounts and CLI flags for every service:

```yaml
volumes:
  - "/etc/ssl/vllm/server.crt:/tls/cert.pem:ro"
  - "/etc/ssl/vllm/server.key:/tls/key.pem:ro"
command:
  # … existing flags …
  - "--ssl-certfile"
  - "/tls/cert.pem"
  - "--ssl-keyfile"
  - "/tls/key.pem"
```

The healthcheck also switches from `http://` to `https://` (with `-k` to allow
self-signed certs):

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -sfk https://localhost:<port>/health || exit 1"]
```

Clients must use HTTPS once TLS is enabled:

```bash
curl https://<host>:8001/v1/chat/completions \
  -H "Authorization: ******" -H 'Content-Type: application/json' -d '...'
```

## Adding a third instance / swapping a model

Copy the new model's full repo onto the host, then add an entry to `vllm_instances`
with a unique `name`, `port`, and its `model_path`, and reduce the other entries'
`gpu_memory_utilization` so the total plus headroom stays under 1.0. The role and
compose template require no changes.
