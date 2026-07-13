# NVIDIA driver management

## The problem

This playbook runs against two very different hosts:

1. A **clean AWS EC2 L40S instance** with no NVIDIA driver at all — Ansible needs to
   install everything from scratch.
2. The **customer's RHEL server**, which may already have an NVIDIA driver installed —
   by the customer's own team, a previous vendor, or as part of an AMI/image — before
   Ansible ever touches it.

Blindly running a driver install (or worse, a driver *reinstall*) against case 2 risks:

- Overwriting a driver version the customer has validated against other workloads.
- Forcing an unplanned reboot on a production server.
- DKMS/kernel-module conflicts if the install method doesn't match how the existing
  driver was installed (e.g. RPM vs. `.run` installer vs. vendor image).

So the `nvidia_driver` role is **detect-then-install**, never blind-install.

## Strategy

```
1. Check whether `nvidia-smi` exists and runs successfully.
   -> rc == 0: parse `driver_version` from its output.
   -> rc != 0: no usable driver present.

2. Compare detected version (if any) against `nvidia_driver_min_version`
   (an Ansible variable, pinned per-environment in group_vars).

3. Decide:
   - No driver found                    -> install `nvidia_driver_target_version`.
   - Driver found, >= min version        -> do nothing, report detected version.
   - Driver found, < min version         -> install/upgrade (gated, see below).

4. Any branch that would install/upgrade a driver, or that requires a reboot to load a
   new kernel module, must:
   - Be skippable via `nvidia_driver_manage: false` (default `true` on aws-test,
     recommended `false` initially on customer inventory until confirmed).
   - Never reboot automatically — report `reboot_required: true` as a fact/output
     and let the operator decide when to reboot.
```

## Variables (`ansible/inventories/<env>/group_vars/all.yml`)

| Variable | Purpose | Default |
|---|---|---|
| `nvidia_driver_manage` | Master switch — if `false`, role only detects and reports, never installs | `true` (aws-test) |
| `nvidia_driver_min_version` | Minimum acceptable driver version already on the box | `550` |
| `nvidia_driver_target_version` | Version to install when a fresh install is needed | `550` |
| `nvidia_driver_repo` | RHEL 9 CUDA/NVIDIA repo URL used for install | see role defaults |

## Why `nvidia_driver_manage` exists as an explicit toggle

The AWS test box is disposable — install-from-scratch is expected and safe there.
The customer box is not. Setting `nvidia_driver_manage: false` in
`inventories/customer/group_vars/all.yml` (at least for the first run) makes the role
purely diagnostic: it reports what's installed and whether it meets the minimum, and
fails loudly instead of silently installing anything, until the operator has reviewed
the report and explicitly opts into management for that host.

## Manual verification before any customer run

Before running the playbook against `inventories/customer` for the first time:

```bash
ansible customer -i ansible/inventories/customer/hosts.yml -m command -a "nvidia-smi --query-gpu=driver_version,name --format=csv"
```

Record the output. Set `nvidia_driver_min_version` to match (or exceed) what's already
there so the role's default behavior is "detect and confirm," not "upgrade."
