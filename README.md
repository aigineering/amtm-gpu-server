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
  read-only from the host, not downloaded during a normal apply — see
  [docs/model-tuning-and-placement.md](docs/model-tuning-and-placement.md) and, for
  the optional standalone playbook that fetches them onto the host,
  [docs/model-fetching.md](docs/model-fetching.md).

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
│   ├── model-fetching.md      # optional, opt-in: pulling models onto the host
│   ├── aws-test-env.md        # provisioning/reset/teardown of the AWS test box
│   └── runbook.md             # step-by-step operational procedures
├── infra/                     # CloudFormation + env.sh for the AWS test env
│   ├── persistent.yml         # key, SG, EIP (survives resets)
│   ├── models.yml             # models EBS volume (survives resets; blank via --wipe-models)
│   ├── instance.yml           # the RHEL GPU instance (disposable)
│   └── env.sh                 # up / reset [--wipe-models] / stop / start / status / ssh / down
├── benchmarks/
│   ├── results/               # one dir per benchmark run (git-tracked)
│   └── render_results.py      # comparison tables + SLO pass/fail
└── ansible/
    ├── ansible.cfg
    ├── requirements.yml       # required collections
    ├── inventories/
    │   ├── aws-test/          # clean AWS L40S box used for dry runs
    │   └── customer/          # customer's existing RHEL server
    ├── profiles/              # named serving configs — apply/benchmark via -e @profiles/<name>.yml
    ├── playbooks/
    │   ├── site.yml
    │   ├── fetch-models.yml   # standalone, opt-in — see docs/model-fetching.md
    │   └── benchmark.yml      # performance suite — see docs/benchmarking.md
    └── roles/
        ├── common/            # base OS prep
        ├── nvidia_driver/     # detect-then-install NVIDIA driver
        ├── docker/            # Docker CE + nvidia-container-toolkit
        ├── vllm/               # docker-compose.yml templating + deploy
        ├── fetch_models/       # optional: download model repos + benchmark assets
        └── benchmark/          # solo/co-located/multi-turn benchmark runs
```

## Operator guide 1 — AWS test environment (training)

Use this environment to rehearse everything before installation day. The box is
disposable: all `*_manage` flags are `true`, so the playbook installs the driver,
Docker, and firewall config from scratch. Full background:
[docs/runbook.md](docs/runbook.md).

### 1.1 Launch the instance

Provisioning is scripted — see [docs/aws-test-env.md](docs/aws-test-env.md) for
the full design (three CloudFormation stacks: key/SG/EIP + models volume +
disposable instance):

```bash
infra/env.sh up                   # g6e.2xlarge (1× L40S 48GB, 64GB RAM), RHEL 9, /opt/models on EBS
infra/env.sh reset                # clean OS; models volume and IP kept
infra/env.sh reset --wipe-models  # clean OS + blank models volume
infra/env.sh down                 # full teardown, incl. models volume
```

`up` prints the Elastic IP to put in `inventories/aws-test/hosts.yml` (once —
it's stable across resets). Note the SG opens SSH to 0.0.0.0/0; ports 8001–8002
are not exposed — test the endpoints through an SSH tunnel
(`ssh -L 8001:localhost:8001 …`) or add ingress rules deliberately.

### 1.2 Prepare the control machine

```bash
python3 -m pip install --user ansible
cd ansible
ansible-galaxy collection install -r requirements.yml   # community.docker, ansible.posix
```

Fill in `ansible_host` in `inventories/aws-test/hosts.yml` (the key file already
points at the repo's `.ssh/aws_key`), then confirm SSH works before anything else:

```bash
chmod 600 ../.ssh/aws_key
ansible all -i inventories/aws-test/hosts.yml -m ping
```

### 1.3 Fetch the models (one-time per box)

`site.yml` never downloads models — they must already be on disk. The `repo_id`s
in `inventories/aws-test/group_vars/all.yml` point at the current AWQ builds
(`cyankiwi/gemma-4-26B-A4B-it-AWQ-4bit`, `cyankiwi/Llama-3.2-3B-Instruct-AWQ-INT4`).
Store your HF token in Vault, then run the fetch playbook:

```bash
cat > inventories/aws-test/group_vars/vault.yml <<'EOF'
vault_hf_token: hf_xxxxxxxxxxxx
EOF
ansible-vault encrypt inventories/aws-test/group_vars/vault.yml

ansible-playbook -i inventories/aws-test/hosts.yml playbooks/fetch-models.yml \
  --ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml
```

(The explicit `-e @…` is needed because `vault.yml` doesn't match a group name, so
Ansible won't load it from `group_vars/` on its own.)

Downloads run async (up to 4 h) and resume if interrupted — if the run dies, just
re-run it. Already-present models are skipped unless `model_fetch_force: true`.

### 1.4 Deploy

```bash
# always dry-run first — this is the habit you'll need on installation day
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml --check --diff

ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml
```

If the driver was freshly installed, the run **stops itself** and reports that a
reboot is required. That's expected, not a failure:

```bash
ansible all -i inventories/aws-test/hosts.yml -m reboot -b
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml   # re-run to finish
```

Then run the [verification checklist](#verification-checklist).

### 1.5 Drills to practice before installation day

1. **Reconfigure**: change `gpu_memory_utilization` or `max_model_len` in group_vars,
   re-apply with `--tags vllm`, verify both endpoints come back.
2. **Read a report-only run**: temporarily set all `*_manage` flags to `false` and run
   `--check --diff` — this is exactly what the first customer-side run looks like.
   Learn what each detect/fail message means (see [common errors](#common-errors)).
3. **Recover**: `docker compose down` on the host, re-run the playbook, confirm recovery.
4. **Diagnose**: kill one container, find the cause via `docker logs` (see
   [diagnostics](#diagnostics)).

### 1.6 Benchmark a configuration

```bash
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/benchmark.yml \
  -e @profiles/baseline.yml
python3 ../benchmarks/render_results.py
```

Solo + co-located scenarios across 1/5/20/50 concurrent users, plus a
multi-turn conversation pass (~1h total); results are git-tracked under
`benchmarks/results/`. Full instructions — including how to interpret the
tables, the SLO verdicts, and the solo-vs-co-located delta — in
[docs/benchmarking.md](docs/benchmarking.md). Test env only: it drives real
load and stops/starts the serving containers.

### 1.7 Teardown

```bash
infra/env.sh down     # from the repo root — removes instance, key/SG/IP, and ALL models volumes
```

## Operator guide 2 — Installation day (customer server)

The customer server is **not** disposable: it may already have a driver, Docker,
firewall, and SELinux policy that this repo must not clobber. All `*_manage` flags
default to `false`, so the playbook can only detect and report until you deliberately
flip them. Read [docs/host-safety-model.md](docs/host-safety-model.md) first.

### 2.1 Bring with you (prep checklist)

- [ ] At least one full AWS rehearsal completed, including the drills in 1.5
- [ ] `ansible` + collections installed on your laptop (`ansible-galaxy collection install -r requirements.yml`) — don't assume on-site internet
- [ ] Confirmed from the customer: SSH host/user/auth, and who signs off on driver/Docker/firewall/SELinux changes
- [ ] `inventories/customer/hosts.yml` filled in
- [ ] Model paths on the host confirmed and filled into `inventories/customer/group_vars/all.yml` (they're `CHANGEME`)
- [ ] Plan for the vLLM Docker image: the host has **no egress by default**, so either pull `vllm/vllm-openai` during the same approved egress window used for model fetching, or bring it as a tarball (`docker save` on the test box → `docker load` on the customer host)
- [ ] Agreed egress window with customer IT if models still need fetching ([docs/model-fetching.md](docs/model-fetching.md))

### 2.2 Connectivity and report-only pass

```bash
cd ansible
ansible all -i inventories/customer/hosts.yml -m ping

# all *_manage flags false → this can only detect and report, never change
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml --check --diff
```

The run **fails at the first gap it finds** with a message naming exactly what's
missing. That's the designed behavior — work through the failures in order (driver →
Docker/toolkit → SELinux → models → GPU budget), not around them.

### 2.3 For each reported gap, decide with the customer

| Reported gap | Option A: let Ansible manage it | Option B: fix out-of-band |
|---|---|---|
| Driver missing / below min version | `nvidia_driver_manage: true` (expect a reboot) | Customer installs/upgrades driver, re-run to confirm |
| Docker missing / stopped | `docker_manage: true` | Customer's team installs/starts Docker |
| nvidia-container-toolkit missing / runtime not configured | `docker_manage: true` | `nvidia-ctk runtime configure --runtime=docker` + restart docker |
| SELinux blocks GPU device access | `selinux_manage: true` | `setsebool -P container_use_devices on` |
| firewalld inactive (warning, not failure) | `firewalld_manage: true` | Confirm ports 8001/8002 open via the host's actual mechanism |

Also, from the detection output of that first run:

1. Set `nvidia_driver_min_version` to the version `nvidia-smi` actually reports —
   don't demand an upgrade the customer didn't ask for.
2. Check the reported **existing GPU processes and memory use**. If another workload
   holds part of the GPU, shrink the `gpu_memory_utilization` values — the playbook
   refuses to apply if existing + requested exceeds 97 % of VRAM.

### 2.4 Apply

```bash
# final review — walk the diff with the customer/stakeholder before proceeding
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml --check --diff

ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml
```

Treat this as a production deploy (see [AGENTS.md](AGENTS.md)). If a driver install
was approved, the run stops for the reboot the same way as on AWS: reboot (with the
customer's blessing), re-run.

Finish with the [verification checklist](#verification-checklist).

### 2.5 If it goes wrong

Rollback is container-level only — driver and Docker changes are host state and stay:

```bash
ansible all -i inventories/customer/hosts.yml -m shell -a "cd /opt/vllm && docker compose down" -b
```

The host is then back to serving nothing, with everything else untouched. Diagnose
offline using the sections below, fix group_vars, re-apply with `--tags vllm`.

## Verification checklist

Run after every deploy, on either environment:

```bash
# 1. GPU visible, driver loaded, both vLLM processes on the GPU
nvidia-smi

# 2. Both containers up (run on the host)
docker compose -f /opt/vllm/docker-compose.yml ps

# 3. Both endpoints healthy (from wherever clients will connect)
curl -s http://<host>:8001/health && echo "gemma OK"
curl -s http://<host>:8002/health && echo "llama OK"
curl -s http://<host>:8001/v1/models
curl -s http://<host>:8002/v1/models

# 4. Real inference on each instance
curl -s http://<host>:8001/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model": "gemma", "messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 20}'
curl -s http://<host>:8002/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model": "llama", "messages": [{"role": "user", "content": "Say hi"}], "max_tokens": 20}'
```

First startup takes minutes (weight loading + CUDA graph capture) — `/health` failing
immediately after deploy usually just means "still loading"; watch
`docker logs -f vllm-gemma` until `Application startup complete`.

## Common commands

```bash
# --- Ansible (from ansible/, <env> = aws-test | customer) ---
ansible all -i inventories/<env>/hosts.yml -m ping                        # SSH reachability
ansible-playbook -i inventories/<env>/hosts.yml playbooks/site.yml --check --diff   # dry run
ansible-playbook -i inventories/<env>/hosts.yml playbooks/site.yml       # full apply
ansible-playbook -i inventories/<env>/hosts.yml playbooks/site.yml --tags vllm      # config-only re-apply
ansible-playbook ... --start-at-task "Render docker-compose.yml"          # resume mid-play
ansible-playbook ... -vvv                                                 # verbose debugging
ansible all -i inventories/<env>/hosts.yml -m reboot -b                   # reboot after driver install

# --- On the GPU host ---
nvidia-smi                                            # driver, VRAM use, GPU processes
watch -n1 nvidia-smi                                  # live VRAM view while loading models
cd /opt/vllm && docker compose ps                     # container status
docker logs -f vllm-gemma                             # follow one instance's log
docker logs --tail 100 vllm-llama
docker compose -f /opt/vllm/docker-compose.yml restart vllm-gemma   # bounce one instance
getenforce && getsebool container_use_devices         # SELinux state
sudo firewall-cmd --list-ports                        # open ports (if firewalld active)
df -h /opt/models && du -sh /opt/models/*             # model disk usage
journalctl -u docker --since "10 min ago"             # docker daemon log
```

## Common errors

Playbook-time failures — most are the safety model working as intended:

| Error / message | Cause | Fix |
|---|---|---|
| `This repo targets RHEL 9. Detected …` | Wrong AMI or wrong host | Use a RHEL 9 image / check `ansible_host` |
| `UNREACHABLE` / SSH timeout | Bad IP, security group, key perms | Check `hosts.yml`, SG port 22, `chmod 600` the key |
| Host key prompt blocks run | First connection, `host_key_checking = True` | SSH to the host once manually to accept the key |
| `couldn't resolve module … docker_compose_v2` | Collections not installed | `ansible-galaxy collection install -r requirements.yml` |
| `NVIDIA driver is missing/below the minimum version … nvidia_driver_manage is false` | Detect-only mode found a gap | Decide per §2.3: flip the flag or fix out-of-band; set `min_version` to reality |
| `A reboot is required …` and run stops | Fresh driver install | Reboot host, re-run playbook (§1.4) |
| `Docker is not installed / not running … docker_manage is false` | Detect-only mode | §2.3 decision |
| `nvidia-container-toolkit is not installed … containers will not be able to access the GPU` | Toolkit/runtime gap | `docker_manage: true` or configure manually |
| `SELinux is Enforcing and container_use_devices is off` | RHEL 9 default policy | `selinux_manage: true` or `setsebool -P container_use_devices on` |
| `model_path … does not exist` | Models not on host yet | Run `fetch-models.yml` (egress window!) or copy models on |
| `… has no config.json` | Weights-only copy, not full HF repo | Copy the complete repo (config, tokenizer, safetensors) |
| `would overcommit the GPU` | Existing GPU workload + requested split > 97 % | Lower `gpu_memory_utilization` values or investigate the other process |
| `This host cannot reach huggingface.co` (fetch-models) | Egress window not open | Confirm window with customer IT, re-run |
| `401 / gated repo` during fetch | Missing/invalid HF token or license not accepted | Fix `vault_hf_token`, accept the model license on HF |

Runtime failures — after the playbook succeeded:

| Symptom | Cause | Fix |
|---|---|---|
| `could not select device driver "nvidia"` on container start | nvidia runtime not configured / docker not restarted | `nvidia-ctk runtime configure --runtime=docker && systemctl restart docker` |
| Container restarts in a loop, log shows `CUDA out of memory` | Split too large for model + context | Lower that instance's `gpu_memory_utilization` or `max_model_len`, re-apply `--tags vllm` |
| Log shows `Permission denied` on `/models/...` | SELinux blocking the bind mount | Check `getsebool container_use_devices`; see §2.3 |
| Image pull fails on customer host | No egress | `docker load` a saved image tarball (§2.1) |
| `/health` OK on the host but unreachable remotely | Firewall / security group | `firewall-cmd --list-ports` on host; SG on AWS |
| `curl: connection refused` right after deploy | Model still loading | Wait; follow `docker logs -f` until startup completes |
| Both endpoints slow / one instance starves | GPU contention between the two instances | Re-benchmark the split; see [docs/model-tuning-and-placement.md](docs/model-tuning-and-placement.md) |

## Diagnostics

When something is off and the tables above don't match, work top-down:

1. **Is Ansible even reaching the host?** `ansible all -i … -m ping`; add `-vvv` for the SSH detail.
2. **What did the playbook detect?** Every role prints its detection facts (driver
   version, Docker state, SELinux mode, GPU memory in use) even in `--check` mode —
   re-run report-only and read those `debug` lines before changing anything.
3. **Is the GPU healthy?** `nvidia-smi` — driver version, VRAM, and whether the two
   `vllm` processes appear. `nvidia-smi -q -d MEMORY` for detail.
4. **What do the containers say?** `docker compose ps` for state,
   `docker logs -f vllm-<name>` for the actual error. vLLM prints its full resolved
   config at startup — verify the flags match your group_vars.
5. **Is it the path between client and container?** Test in order:
   `curl localhost:<port>/health` on the host → same from your machine → firewall/SG
   is the difference.
6. **Docker daemon itself:** `journalctl -u docker --since "10 min ago"`.

Never edit `/opt/vllm/docker-compose.yml` by hand — it's overwritten on every apply.
All changes go through `inventories/<env>/group_vars/all.yml` + `--tags vllm`.

## Status

Early scaffolding — Ansible roles are being built out incrementally. Model repos are
assumed to already exist on the target host as full local copies (see
[docs/model-tuning-and-placement.md](docs/model-tuning-and-placement.md)); the exact
`model_path` values and default GPU memory splits in
`ansible/inventories/*/group_vars/all.yml` are placeholders and must be confirmed
before a real deploy.
