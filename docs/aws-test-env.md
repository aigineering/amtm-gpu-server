# AWS test environment

The `infra/` directory provisions the disposable AWS box that the `aws-test`
inventory targets. It's plain CloudFormation driven by a bash wrapper — no CDK,
no Terraform state, nothing to install beyond the AWS CLI.

## Design: three stacks

The environment is split so that "reset the machine" and "keep the models" don't
fight each other:

- **`gpu-vllm-test-persistent`** (`infra/persistent.yml`) — the imported SSH key
  (from `.ssh/aws_key.pub` in this repo), the security group (SSH and the vLLM
  ports 8001–8002 open to 0.0.0.0/0 — test env only, never copy this to
  anything real; the vLLM ports are only safe because the app layer requires
  an API key, see `vllm_api_key` in
  [vllm-configuration.md](vllm-configuration.md)), and an Elastic IP. Survives
  resets.
- **`gpu-vllm-test-models-<az>`** (`infra/models.yml`) — only the gp3 EBS
  volume that holds `/opt/models`, **one stack per AZ**. In its own stack so a
  plain `reset` can never touch it, while `reset --wipe-models` can swap the
  current AZ's for a blank one without disturbing the key/SG/IP. Per-AZ because
  L40S capacity is scarce and zone-dependent: hopping AZs keeps a warm model
  cache in every zone you've visited (~$24/mo per idle 300GB volume) instead of
  forcing a re-fetch on each hop.
- **`gpu-vllm-test-instance`** (`infra/instance.yml`) — the RHEL 9 GPU instance
  (default `g6e.2xlarge`: 1× L40S 48GB, 64 GiB RAM — the RAM headroom also
  serves the parked KV-offloading experiments), the volume attachment, and the
  EIP association. First-boot user-data formats the models volume **only if it
  has no filesystem** and mounts it at `/opt/models` via fstab.

Because the IP is an EIP in the persistent stack, `ansible_host` in
`ansible/inventories/aws-test/hosts.yml` only needs to be set once — it holds
across resets and stop/start cycles.

## Commands

```
infra/env.sh up                   # create/update everything; prints the IP for hosts.yml
infra/env.sh reset                # recreate ONLY the instance — clean RHEL, models kept
infra/env.sh reset --wipe-models  # clean RHEL + blank models volume (confirms first)
infra/env.sh stop                 # done for the day: stop instance, pay only EBS+EIP
infra/env.sh start                # resume, same IP
infra/env.sh status               # stacks, instance state, IP, ssh hint
infra/env.sh ssh                  # ssh in as ec2-user with the repo key
infra/env.sh tunnel               # forward vLLM ports 8001/8002 to localhost (Ctrl-C closes)
infra/env.sh down                 # full teardown incl. models volume (confirms first)
```

Override via `REGION` (preferred — it beats any `AWS_REGION` exported in your
shell, which once silently redirected a run to the wrong region), `AZ`, and
`INSTANCE_TYPE` env vars; defaults are in the script header. `REGION` and `AZ`
must agree (AZ = region + letter) — enforced before any command runs, and every
command prints `region=… az=…` first.

Capacity hunting across regions works: CloudFormation stacks are region-scoped,
so each region gets its own persistent/models/instance stacks and its own
Elastic IP (update `hosts.yml` when switching regions) and needs one
fetch-models run. A stack stuck in `ROLLBACK_COMPLETE` from a failed create is
deleted automatically on the next deploy. Note `down` cleans only the region
it's pointed at.

Every command first verifies (via `sts get-caller-identity`) that the current
credentials belong to account `088070740738` and refuses to run otherwise —
protection against provisioning into, or tearing down, the wrong account.
Override with `AWS_ACCOUNT=<id>` if the env ever moves.

## When to reset vs stop

- **`stop`** is the cost lever. Everything on both disks survives; you stop
  paying the g6e.2xlarge on-demand rate (~$2.2/hr) and keep paying only for
  the EBS volumes and the idle-EIP fee.
- **`reset`** is the correctness lever. This repo's whole point is "run once on
  a clean box, then re-run on a box that already has things installed" — reset
  gives you the clean box back to re-verify `site.yml` from scratch, without
  re-fetching the ~150GB model catalog. After a reset, clear the old host key
  (`ssh-keygen -R <ip>`) before running Ansible.
- **`reset --wipe-models`** additionally replaces the models volume with a
  blank one — use it to re-verify the fetch playbook end-to-end, or if the
  volume's contents are suspect. Only `down` and this flag ever destroy model
  data, and both ask for confirmation.

## Caveats

- **AZ hopping is cheap.** L40S capacity comes and goes per zone. When the
  current AZ has none, `AZ=us-east-1b infra/env.sh reset` moves the instance —
  the first visit to a new AZ creates a blank models volume there (run the
  fetch playbook once), and every previously visited AZ keeps its warm cache
  for the next hop back. The instance always launches in `$AZ`, and its models
  volume is always the one belonging to that AZ.
- **`down` destroys the models volumes of every AZ.** That's deliberate (easy
  full cleanup — it lists what it's about to delete and asks); the fetch
  playbook re-populates a volume in one run. See
  [model-fetching.md](model-fetching.md).
- The RHEL 9 AMI is looked up fresh (latest Red Hat–owned `RHEL-9.*` image) on
  every `up`/`reset`, so a reset may also move you to a newer RHEL point
  release. That's a feature for this repo's purpose — the customer box's exact
  state is unknown anyway.
- The user-data mount uses `nofail`, so a boot with a detached volume still
  comes up SSH-able.
