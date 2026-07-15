# Runbook

## 1. Prerequisites (control machine)

```bash
python3 -m pip install --user ansible
cd ansible
ansible-galaxy collection install -r requirements.yml
```

You'll need SSH access to the target host.

## 2. Getting model repos onto the host (if not already there)

`site.yml` never touches the network for models — it expects the full repo already
on disk at each instance's `model_path` (see
[vllm-configuration.md](vllm-configuration.md)). If it isn't there yet:

```bash
# only during a window the host's egress is confirmed open (customer hosts have
# none by default) — see model-fetching.md
ansible-playbook -i inventories/<env>/hosts.yml playbooks/fetch-models.yml \
  --ask-vault-pass -e @inventories/<env>/group_vars/vault.yml
```

This is a separate, opt-in playbook precisely because the customer host's internet
access isn't something this repo controls or can assume. See
[model-fetching.md](model-fetching.md) for credentials setup (Ansible Vault) and how
it behaves if the window isn't open yet.

## 3. First run: clean AWS L40S box

1. Provision the box: `infra/env.sh up` (g6e.xlarge, RHEL 9, models EBS volume
   mounted at `/opt/models`, Elastic IP) — see [aws-test-env.md](aws-test-env.md).
2. Put the printed Elastic IP into `ansible/inventories/aws-test/hosts.yml`
   (`ansible_host`; the key file already points at the repo's `.ssh/aws_key`).
   The IP is stable across resets, so this is a one-time step.
3. Confirm `nvidia_driver_manage: true` in
   `ansible/inventories/aws-test/group_vars/all.yml` (default) — this box is disposable,
   so a from-scratch driver install is expected.
4. Create the vault (one-time; holds the HF token and the vLLM API key — the
   test box's endpoints are public, the key is mandatory; see the README
   operator guide for the exact snippet). Every run below passes
   `--ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml`
   (abbreviated `<vault args>`).
5. Dry-run first:
   ```bash
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml --check --diff <vault args>
   ```
6. Real run:
   ```bash
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml <vault args>
   ```
7. If the driver role reports `reboot_required: true`, reboot manually and re-run:
   ```bash
   ansible gpu_servers -i inventories/aws-test/hosts.yml -m reboot -b
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml <vault args>
   ```
8. Verify both vLLM endpoints (public on the test box, API-key protected —
   see [vllm-configuration.md](vllm-configuration.md)):
   ```bash
   curl -H "Authorization: Bearer <key>" http://<host>:8001/v1/models   # gemma
   curl -H "Authorization: Bearer <key>" http://<host>:8002/v1/models   # llama
   ```
   (Or tunnel with `infra/env.sh tunnel` — the key is still required on
   /v1/* either way.)

## 4. Before touching the customer server

**Do not skip this.** The customer's server may already have an NVIDIA driver, Docker,
a firewall config, and an SELinux policy in place outside of Ansible. Every
`*_manage` flag defaults to `false` in `inventories/customer/group_vars/all.yml`, so a
run at this stage cannot change anything — it can only detect and report. See
[host-safety-model.md](host-safety-model.md) for the pattern behind this.

1. Run a full report-only pass (all `*_manage` flags false):
   ```bash
   ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml --check --diff
   ```
   This will fail at the first gap it finds (e.g. driver below minimum version, Docker
   missing, GPU toolkit not configured, SELinux boolean off) with a message naming
   exactly what's missing. That's expected — work through each failure in order.
2. For each failure, decide with the customer/stakeholder whether to:
   - Set the matching `*_manage` flag (`nvidia_driver_manage`, `docker_manage`,
     `firewalld_manage`, `selinux_manage`) to `true` and let Ansible handle it, or
   - Handle it manually/out-of-band and re-run to confirm the check now passes.
3. Set `nvidia_driver_min_version` to match what's already installed (from the
   `nvidia-smi` output surfaced in step 1) rather than an arbitrary target.
4. Confirm existing GPU memory usage (also reported automatically by the `vllm` role)
   before assuming the full `vllm_instances` GPU split from the test run applies as-is
   — another workload may already be using part of the GPU.

## 5. Apply to the customer server

```bash
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml --check --diff
# review the diff with the customer/stakeholder before proceeding
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml
```

Per [AGENTS.md](../AGENTS.md), this run should only happen with explicit confirmation —
treat it as a production deploy.

## 6. Iterating on configuration

Once the stack is up on either environment, most experiments only need the `vllm` tag:

```bash
# edit inventories/<env>/group_vars/all.yml (gpu_memory_utilization, model, extra_args…)
ansible-playbook -i inventories/<env>/hosts.yml playbooks/site.yml --tags vllm
```

## 7. Benchmarking a configuration

Once the stack serves, measure it before and after any tuning change — see
[benchmarking.md](benchmarking.md) ("Running the benchmark" for the exact
commands, "Interpreting results" for reading the output):

```bash
ansible-playbook -i inventories/aws-test/hosts.yml playbooks/benchmark.yml \
  --ask-vault-pass -e @inventories/aws-test/group_vars/vault.yml \
  -e @profiles/baseline.yml
python3 ../benchmarks/render_results.py
```

Test-env only — the suite drives real load and stops/starts the serving
containers.

## 8. Rollback / teardown

```bash
ansible gpu_servers -i inventories/<env>/hosts.yml -m shell \
  -a "cd /opt/vllm && docker compose down" -b
```

Driver and Docker installs are not automatically rolled back — they're treated as host
state, not deploy state. To fully tear down a host: on the test env, use
`infra/env.sh reset` (fresh OS, models kept) or `infra/env.sh down` (everything
gone, models volume included) — see [aws-test-env.md](aws-test-env.md); on the
customer server, coordinate a manual driver/Docker removal with the customer.
