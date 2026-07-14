# Fetching models onto the server

## Why this is a separate playbook

The customer's server has no internet access by default — their IT team has to
explicitly open a temporary egress window before this host can reach Hugging Face
Hub. That's a fundamentally different operation from the routine `site.yml` apply
(driver/Docker checks, vLLM config changes), which should work identically whether
or not the box currently has internet access. So fetching is its own playbook,
`playbooks/fetch-models.yml`, built around the `fetch_models` role:

- It is **never** included in `site.yml` and never runs as a side effect of a normal
  apply or a `--tags vllm` config-tuning run.
- It only runs when you invoke it explicitly, during a window IT has confirmed is open.
- Same detect-then-manage spirit as the rest of this repo (see
  [host-safety-model.md](host-safety-model.md)): it checks reachability to
  `huggingface.co` first and fails with a specific, actionable message if the window
  isn't open, rather than hanging on a blocked connection or failing deep inside
  `huggingface-cli` with a confusing error.

## What it does, in order

1. Asserts every `vllm_instances` entry has a `repo_id` configured.
2. Checks that `https://huggingface.co` is reachable; fails clearly if not.
3. Installs `huggingface_hub[cli]` into an isolated virtualenv
   (`/opt/model-fetch-venv` by default) — this never touches system Python packages,
   so cleanup is just deleting that directory.
4. For each instance, skips the download if `model_path` already contains a
   `config.json` (unless `model_fetch_force: true`); otherwise runs
   `huggingface-cli download <repo_id> --revision <revision> --local-dir <model_path>`.
5. Reports disk usage per model directory when done.

## Running it

```bash
cd ansible
# confirm with IT that the egress window is open, then:
ansible-playbook -i inventories/customer/hosts.yml playbooks/fetch-models.yml \
  --ask-vault-pass -e @inventories/customer/group_vars/vault.yml
```

There's little value in `--check` here — most of the substantive tasks are shell
commands that don't support meaningful check-mode simulation. Instead, rely on the
role's own idempotency: it's safe to run more than once, and already-downloaded
models are skipped automatically, so re-running (e.g. after a window closes and
reopens) only fetches what's still missing.

## Credentials (gated repos)

The current `repo_id`s (cyankiwi's AWQ community quantizations) are public and
need no token. If you switch to a gated repo (e.g. the original `meta-llama/…`
or `google/…` weights), the fetch needs an access token (never during serving —
the `vllm` role runs fully offline). Store it via Ansible Vault, not in
plaintext:

```bash
cd ansible
ansible-vault create inventories/customer/group_vars/vault.yml
# add a line: vault_hf_token: hf_xxxxxxxxxxxxxxxxxxxx
```

`group_vars/all.yml` already references `vault_hf_token` via
`model_fetch_hf_token: "{{ vault_hf_token | default('') }}"`.

Note that Ansible only auto-loads `group_vars/` files named after an inventory group
(`all`, `gpu_servers`), so `vault.yml` must be passed explicitly with
`-e @inventories/<env>/group_vars/vault.yml`, alongside `--ask-vault-pass` (or
`--vault-password-file`) — as shown in the command above. `vault.yml` is already
git-ignored (see `.gitignore`) so it can't be committed by accident.

## Handling large downloads

- `huggingface-cli download` resumes interrupted transfers automatically — if the
  egress window closes mid-download, re-running the playbook once it reopens
  continues rather than starting over.
- The download task runs with `async`/`poll` (currently a 4-hour ceiling) so a
  multi-hour transfer for the larger MoE model isn't killed by an SSH session
  timeout.
- Optional speed-up: install the `hf_transfer` package into the same virtualenv and
  set `HF_HUB_ENABLE_HF_TRANSFER: "1"` in the download task's environment for
  higher-throughput transfers. Not enabled by default because it hard-fails if the
  extra package isn't present — only turn it on if you've added the dependency.

## After fetching

Once model repos are on disk, they're just files — not tracked or managed by
Ansible beyond that point. The regular `site.yml` apply (`vllm` role) mounts them
read-only and never touches the network, so if IT closes egress again immediately
afterward, every other operation in this repo (GPU-split changes, vLLM flag tuning,
re-deploys) continues to work exactly the same.
