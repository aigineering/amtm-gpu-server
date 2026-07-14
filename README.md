# gpu-vllm-setup

Ansible-managed deployment of two [vLLM](https://github.com/vllm-project/vllm) inference
instances on a single RHEL 9 server with an NVIDIA L40S GPU:

- **Gemma 4 (26B total / 4B active, MoE)** — served on its own vLLM instance
- **Llama 3.2 3B** — served on a second vLLM instance, sharing the same GPU

Both instances run as Docker Compose services on one GPU, each pinned to a configurable
share of GPU memory. The goal is to make it easy to reconfigure and re-benchmark different
model/GPU-split combinations on the same hardware.

## Why Ansible

- **Agentless**: every run connects over plain SSH from your machine (or CI), applies
  changes, and disconnects — nothing persistent is installed on the target to make
  this work.
- **Repeatable**: stand up the same stack on a clean AWS EC2 box (g6e/L40S family) for
  testing, then re-apply the identical playbook to the customer's existing RHEL server.
- **Safe on pre-provisioned servers**: the customer's server may already have an NVIDIA
  driver, Docker, firewalld config, or SELinux policy in place. Every one of those
  areas is detected before anything is touched — see
  [docs/host-safety-model.md](docs/host-safety-model.md).
- **Configuration as data**: model paths, GPU memory fractions, ports, and vLLM CLI
  flags are all Ansible variables, not hardcoded — see
  [docs/vllm-configuration.md](docs/vllm-configuration.md). Model repos are mounted
  read-only from the host, not downloaded — see
  [docs/model-tuning-and-placement.md](docs/model-tuning-and-placement.md).

Non-technical summary: [docs/executive-overview.md](docs/executive-overview.md).

## Repo layout

```
.
├── AGENTS.md                  # instructions for AI coding agents working in this repo
├── docs/
│   ├── executive-overview.md  # non-technical summary, with diagrams
│   ├── architecture.md        # topology, GPU split, compose design
│   ├── host-safety-model.md   # the detect-then-manage pattern used everywhere
│   ├── nvidia-driver-management.md
│   ├── vllm-configuration.md
│   ├── model-tuning-and-placement.md  # model placement + chat-focused tuning
│   └── runbook.md             # step-by-step operational procedures
└── ansible/
    ├── ansible.cfg
    ├── requirements.yml       # required collections
    ├── inventories/
    │   ├── aws-test/          # clean AWS L40S box used for dry runs
    │   └── customer/          # customer's existing RHEL server
    ├── playbooks/
    │   └── site.yml
    └── roles/
        ├── common/            # base OS prep
        ├── nvidia_driver/     # detect-then-install NVIDIA driver
        ├── docker/            # Docker CE + nvidia-container-toolkit
        └── vllm/              # docker-compose.yml templating + deploy
```

## Quickstart

See [docs/runbook.md](docs/runbook.md) for the full procedure. Short version:

```bash
cd ansible
ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml
```

To target the customer server, point at the other inventory:

```bash
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml
```

## Status

Early scaffolding — Ansible roles are being built out incrementally. Model repos are
assumed to already exist on the target host as full local copies (see
[docs/model-tuning-and-placement.md](docs/model-tuning-and-placement.md)); the exact
`model_path` values and default GPU memory splits in
`ansible/inventories/*/group_vars/all.yml` are placeholders and must be confirmed
before a real deploy.
