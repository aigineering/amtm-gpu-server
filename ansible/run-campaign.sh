#!/usr/bin/env bash
# Run a benchmark campaign: for every given profile, re-deploy the serving
# stack (site.yml --tags vllm) and run the benchmark suite against it. The
# vault password is provided ONCE (see below), not per playbook run.
#
#   ansible/run-campaign.sh                          # default: profiles/solo-gemma-*.yml
#   ansible/run-campaign.sh profiles/baseline.yml    # explicit profile(s)
#   ansible/run-campaign.sh profiles/solo-gemma-31b-*.yml
#
# Vault password source, in priority order:
#   1. $ANSIBLE_VAULT_PASSWORD_FILE (standard Ansible env var)
#   2. .vault_pass at the repo root (gitignored — create it with:
#        printf '%s' 'your-vault-pass' > .vault_pass && chmod 600 .vault_pass)
#   3. a single interactive prompt (kept in a mktemp file, removed on exit)
#
# Benchmark runs are resumable (docs/benchmarking.md), so re-running the
# campaign after an interruption only executes what's missing. The script
# stops at the first failure — fix, re-run, it picks up where it left off.
#
# Overridables: INVENTORY (inventories/aws-test/hosts.yml),
#               VAULT_FILE (inventories/aws-test/group_vars/vault.yml)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

INVENTORY="${INVENTORY:-inventories/aws-test/hosts.yml}"
VAULT_FILE="${VAULT_FILE:-inventories/aws-test/group_vars/vault.yml}"

profiles=("$@")
if [ ${#profiles[@]} -eq 0 ]; then
  profiles=(profiles/solo-gemma-*.yml)
fi

for p in "${profiles[@]}"; do
  [ -f "$p" ] || { echo "no such profile: $p" >&2; exit 1; }
done

if [ -n "${ANSIBLE_VAULT_PASSWORD_FILE:-}" ]; then
  pass_file="$ANSIBLE_VAULT_PASSWORD_FILE"
elif [ -f ../.vault_pass ]; then
  pass_file=../.vault_pass
else
  pass_file=$(mktemp)
  trap 'rm -f "$pass_file"' EXIT
  read -r -s -p "Vault password (asked once for the whole campaign): " vault_pass
  echo
  printf '%s' "$vault_pass" > "$pass_file"
fi

run_playbook() {
  ansible-playbook -i "$INVENTORY" --vault-password-file "$pass_file" \
    -e @"$VAULT_FILE" "$@"
}

campaign_start=$(date +%s)
n=0
for p in "${profiles[@]}"; do
  n=$((n + 1))
  echo
  echo "=== [$n/${#profiles[@]}] $(date -u '+%Y-%m-%d %H:%M:%SZ') — profile: $p ==="
  run_playbook playbooks/site.yml --tags vllm -e @"$p"
  run_playbook playbooks/benchmark.yml -e @"$p"
done

echo
echo "=== campaign finished: ${#profiles[@]} profile(s) in $(( ($(date +%s) - campaign_start) / 60 )) min ==="
python3 ../benchmarks/render_results.py || true
