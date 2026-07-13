# Runbook

## 1. Prerequisites (control machine)

```bash
python3 -m pip install --user ansible
cd ansible
ansible-galaxy collection install -r requirements.yml
```

You'll need SSH access to the target host and, for the customer environment, an
accepted-license Hugging Face token for Gemma and Llama (see
[vllm-configuration.md](vllm-configuration.md)).

## 2. First run: clean AWS L40S box

1. Launch an EC2 instance from the L40S family (e.g. `g6e.xlarge`) with RHEL 9.
2. Fill in `ansible/inventories/aws-test/hosts.yml` with its IP/DNS and SSH user.
3. Confirm `nvidia_driver_manage: true` in
   `ansible/inventories/aws-test/group_vars/all.yml` (default) — this box is disposable,
   so a from-scratch driver install is expected.
4. Dry-run first:
   ```bash
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml --check --diff
   ```
5. Real run:
   ```bash
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml
   ```
6. If the driver role reports `reboot_required: true`, reboot manually and re-run:
   ```bash
   ansible aws_test -i inventories/aws-test/hosts.yml -m reboot -b
   ansible-playbook -i inventories/aws-test/hosts.yml playbooks/site.yml
   ```
7. Verify both vLLM endpoints:
   ```bash
   curl http://<host>:8001/v1/models   # gemma
   curl http://<host>:8002/v1/models   # llama
   ```

## 3. Before touching the customer server

**Do not skip this.** The customer's server may already have an NVIDIA driver and other
software installed outside of Ansible.

1. Run driver detection only:
   ```bash
   ansible customer -i inventories/customer/hosts.yml -m command \
     -a "nvidia-smi --query-gpu=driver_version,name,memory.total --format=csv"
   ```
2. Set `nvidia_driver_min_version` in `inventories/customer/group_vars/all.yml` to match
   what's already installed, and leave `nvidia_driver_manage: false` until you've
   reviewed the report with the customer.
3. Check what else is already on the box (existing Docker install, existing GPU
   workloads competing for VRAM) before assuming the full `vllm_instances` GPU split
   from the test run applies as-is.

## 4. Apply to the customer server

```bash
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml --check --diff
# review the diff with the customer/stakeholder before proceeding
ansible-playbook -i inventories/customer/hosts.yml playbooks/site.yml
```

Per [AGENTS.md](../AGENTS.md), this run should only happen with explicit confirmation —
treat it as a production deploy.

## 5. Iterating on configuration

Once the stack is up on either environment, most experiments only need the `vllm` tag:

```bash
# edit inventories/<env>/group_vars/all.yml (gpu_memory_utilization, model, extra_args…)
ansible-playbook -i inventories/<env>/hosts.yml playbooks/site.yml --tags vllm
```

## 6. Rollback / teardown

```bash
ansible <env> -i inventories/<env>/hosts.yml -m shell \
  -a "cd /opt/vllm && docker compose down" -b
```

Driver and Docker installs are not automatically rolled back — they're treated as host
state, not deploy state. To fully tear down a host, terminate the AWS instance (test
env) or coordinate a manual driver/Docker removal with the customer.
