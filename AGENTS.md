# Agent instructions

This repo manages a real GPU server (and eventually a customer's production server) via
Ansible. Playbook runs are not sandboxed — a bad run can take down inference for real
users or leave a customer's server in a broken state. Treat `ansible-playbook` runs
against the `customer` inventory as production deploys, not local dev commands.

## Ground rules

- **Never run playbooks against the `customer` inventory without explicit user
  confirmation for that specific run.** Running against `aws-test` for iteration is fine.
- **Never assume any part of the host is a blank slate.** The customer's server may
  already have an NVIDIA driver, Docker, firewalld config, or SELinux policy in place
  before this repo ever touched it — not just the driver. Every one of those areas
  follows the same detect-then-manage pattern: check current state, and only
  install/change something when the matching `*_manage` variable
  (`nvidia_driver_manage`, `docker_manage`, `firewalld_manage`, `selinux_manage`) is
  explicitly true for that environment. See
  [docs/host-safety-model.md](docs/host-safety-model.md) (general pattern) and
  [docs/nvidia-driver-management.md](docs/nvidia-driver-management.md) (driver
  specifics).
- **Never run `--force`, driver reinstalls, or anything that triggers a reboot without
  surfacing that to the user first.** A reboot on the customer's server has real
  downtime cost.
- **Agentless, SSH-only.** Nothing in this repo should require installing a persistent
  agent, daemon, or control-plane component on the target host. Every run connects
  over SSH, applies changes, and disconnects.
- **Model IDs and licensing**: Gemma and Llama weights are gated on Hugging Face. Don't
  invent or guess exact HF repo IDs/revisions — they're Ansible variables
  (`group_vars/all.yml`) that the user must confirm. If a variable looks like a
  placeholder (e.g. contains `CHANGEME` or is obviously a guess), flag it rather than
  treating it as correct.
- **Idempotency matters more than speed here.** Every role should be safe to re-run.
  This repo's whole point is "run once on a clean AWS box, then re-run unchanged on a
  customer box that already has some things installed." Tasks that aren't naturally
  idempotent need explicit `creates:`/`when:` guards.

## Conventions

- Ansible-lint should pass (`ansible-lint ansible/`) before considering a role done.
- Variables that vary between environments (model IDs, GPU memory fractions, ports,
  driver version pins) live in `ansible/inventories/<env>/group_vars/all.yml`, not
  hardcoded in role tasks/templates.
- Each role should be testable in isolation via tags (e.g. `--tags nvidia_driver`).
- Prefer `command`/`shell` with explicit `changed_when`/`failed_when` over assuming
  Ansible's default change detection is correct — many of the checks here
  (driver version, GPU memory available) require custom logic.
- Docker Compose files for vLLM are Jinja2 templates (`roles/vllm/templates/`) rendered
  from variables, not static files — this repo exists specifically so configurations can
  be changed and re-benchmarked without editing YAML by hand.

## When making changes

- If you add a new configurable knob (new vLLM flag, new model, new GPU split), add it
  as a variable with a sane default and document it in
  [docs/vllm-configuration.md](docs/vllm-configuration.md).
- If you change driver-detection or install logic, update
  [docs/nvidia-driver-management.md](docs/nvidia-driver-management.md) — this is the
  most safety-critical part of the repo.
- If you add a new detect-then-manage gate (a new `*_manage` variable) or change an
  existing one, update [docs/host-safety-model.md](docs/host-safety-model.md).
- Don't add abstractions (dynamic role generation, custom modules) for the two-model
  case in front of us. Two vLLM services, two sets of vars, one compose template with a
  loop is enough.
