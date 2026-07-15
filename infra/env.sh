#!/usr/bin/env bash
# Manage the disposable AWS test env for this repo. See docs/aws-test-env.md.
#
#   infra/env.sh up                    create/update everything
#   infra/env.sh reset                 recreate ONLY the instance (clean OS, models kept)
#   infra/env.sh reset --wipe-models   recreate instance AND a blank models volume
#   infra/env.sh stop                  stop the instance (pay only EBS/EIP) — state kept
#   infra/env.sh start                 start a stopped instance (same IP)
#   infra/env.sh status                show stacks, instance state, IP
#   infra/env.sh ssh                   ssh into the box
#   infra/env.sh tunnel                forward the vLLM ports (8001, 8002) to localhost
#   infra/env.sh down                  tear EVERYTHING down, including the models volume
#
# Overridables: AWS_REGION (us-east-1), AZ (us-east-1a), INSTANCE_TYPE (g6e.xlarge),
# AWS_ACCOUNT (088070740738 — every command refuses to run against any other account),
# TUNNEL_PORTS ("8001 8002")
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
AZ="${AZ:-us-east-1c}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.xlarge}"
EXPECTED_ACCOUNT="${AWS_ACCOUNT:-088070740738}"

PREFIX="gpu-vllm-test"
PERSISTENT_STACK="${PREFIX}-persistent"
MODELS_STACK="${PREFIX}-models"
INSTANCE_STACK="${PREFIX}-instance"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBKEY_FILE="${REPO_ROOT}/.ssh/aws_key.pub"
PRIVKEY_FILE="${REPO_ROOT}/.ssh/aws_key"
INFRA_DIR="${REPO_ROOT}/infra"

aws() { command aws --region "$REGION" "$@"; }

# Guard against running (and paying, or deleting) in the wrong AWS account.
check_account() {
  local actual
  actual=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
    || { echo "not authenticated to AWS (aws sts get-caller-identity failed)" >&2; exit 1; }
  if [ "$actual" != "$EXPECTED_ACCOUNT" ]; then
    echo "authenticated to AWS account $actual, expected $EXPECTED_ACCOUNT" >&2
    echo "(switch profiles, or override with AWS_ACCOUNT=$actual)" >&2
    exit 1
  fi
}

default_vpc() {
  aws ec2 describe-vpcs --filters Name=is-default,Values=true \
    --query 'Vpcs[0].VpcId' --output text
}

subnet_in_az() { # vpc-id az
  aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$1" "Name=availability-zone,Values=$2" \
    --query 'Subnets[0].SubnetId' --output text
}

latest_rhel9_ami() {
  aws ec2 describe-images --owners 309956199498 \
    --filters 'Name=name,Values=RHEL-9.*_HVM-*-x86_64-*' \
              'Name=architecture,Values=x86_64' \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text
}

stack_output() { # stack-name output-key
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue" --output text 2>/dev/null || true
}

instance_id() { stack_output "$INSTANCE_STACK" InstanceId; }
public_ip()   { stack_output "$PERSISTENT_STACK" EipAddress; }

deploy_persistent() {
  [ -f "$PUBKEY_FILE" ] || { echo "missing $PUBKEY_FILE" >&2; exit 1; }
  local vpc; vpc=$(default_vpc)
  [ "$vpc" != "None" ] || { echo "no default VPC in $REGION" >&2; exit 1; }
  echo ">> deploying $PERSISTENT_STACK (vpc=$vpc)"
  aws cloudformation deploy \
    --stack-name "$PERSISTENT_STACK" \
    --template-file "$INFRA_DIR/persistent.yml" \
    --no-fail-on-empty-changeset \
    --parameter-overrides \
      "PublicKeyMaterial=$(cat "$PUBKEY_FILE")" \
      "VpcId=$vpc"
}

deploy_models() {
  echo ">> deploying $MODELS_STACK (az=$AZ)"
  aws cloudformation deploy \
    --stack-name "$MODELS_STACK" \
    --template-file "$INFRA_DIR/models.yml" \
    --no-fail-on-empty-changeset \
    --parameter-overrides "AvailabilityZone=$AZ"
}

# The instance must land in the same AZ as the existing models volume, even if
# $AZ was overridden differently for this invocation.
models_az() {
  local az; az=$(stack_output "$MODELS_STACK" AvailabilityZone)
  echo "${az:-$AZ}"
}

deploy_instance() {
  local vpc az subnet ami
  vpc=$(default_vpc)
  az=$(models_az)
  subnet=$(subnet_in_az "$vpc" "$az")
  [ "$subnet" != "None" ] || { echo "no default subnet in $az" >&2; exit 1; }
  ami=$(latest_rhel9_ami)
  echo ">> deploying $INSTANCE_STACK (ami=$ami type=$INSTANCE_TYPE az=$az)"
  aws cloudformation deploy \
    --stack-name "$INSTANCE_STACK" \
    --template-file "$INFRA_DIR/instance.yml" \
    --no-fail-on-empty-changeset \
    --parameter-overrides \
      "PersistentStackName=$PERSISTENT_STACK" \
      "ModelsStackName=$MODELS_STACK" \
      "AmiId=$ami" \
      "InstanceType=$INSTANCE_TYPE" \
      "SubnetId=$subnet"
}

delete_stack() {
  echo ">> deleting $1"
  aws cloudformation delete-stack --stack-name "$1"
  aws cloudformation wait stack-delete-complete --stack-name "$1"
}

cmd_up() {
  deploy_models
  deploy_persistent
  deploy_instance
  cmd_status
  echo
  echo "Ansible inventory (ansible/inventories/aws-test/hosts.yml):"
  echo "  ansible_host: $(public_ip)"
}

cmd_reset() {
  local wipe=false
  [ "${1:-}" = "--wipe-models" ] && wipe=true
  if $wipe; then
    echo "This replaces the models volume with a BLANK one (re-fetch ~20GB after)."
    read -r -p "Type 'yes' to confirm: " ans
    [ "$ans" = "yes" ] || { echo "aborted"; exit 1; }
  fi
  delete_stack "$INSTANCE_STACK"
  if $wipe; then
    delete_stack "$MODELS_STACK"
    deploy_models
  fi
  deploy_instance
  if $wipe; then
    echo ">> fresh instance + blank models volume, same IP: $(public_ip)"
  else
    echo ">> fresh instance up, models volume untouched, same IP: $(public_ip)"
  fi
  echo ">> note: run 'ssh-keygen -R $(public_ip)' — the new box has a new host key"
}

cmd_down() {
  echo "This deletes EVERYTHING, including the models volume (re-fetch ~20GB later)."
  echo "(To keep the models, use 'reset' or 'stop' instead.)"
  read -r -p "Type 'yes' to confirm: " ans
  [ "$ans" = "yes" ] || { echo "aborted"; exit 1; }
  delete_stack "$INSTANCE_STACK"
  delete_stack "$MODELS_STACK"
  delete_stack "$PERSISTENT_STACK"
  echo ">> all gone"
}

cmd_stop()  { aws ec2 stop-instances  --instance-ids "$(instance_id)" >/dev/null; echo ">> stopping $(instance_id)"; }
cmd_start() { aws ec2 start-instances --instance-ids "$(instance_id)" >/dev/null; echo ">> starting $(instance_id) (IP unchanged: $(public_ip))"; }

cmd_status() {
  local iid ip state
  iid=$(instance_id); ip=$(public_ip)
  echo "region=$REGION az=$(models_az)"
  echo "persistent stack: $(aws cloudformation describe-stacks --stack-name "$PERSISTENT_STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo absent)"
  echo "models stack:     $(aws cloudformation describe-stacks --stack-name "$MODELS_STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo absent)"
  echo "instance stack:   $(aws cloudformation describe-stacks --stack-name "$INSTANCE_STACK" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo absent)"
  if [ -n "$iid" ]; then
    state=$(aws ec2 describe-instances --instance-ids "$iid" --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo unknown)
    echo "instance: $iid ($state)  ip: $ip"
    echo "ssh: ssh -i .ssh/aws_key ec2-user@$ip"
  fi
}

cmd_ssh() { exec ssh -i "$PRIVKEY_FILE" "ec2-user@$(public_ip)"; }

# The test box's SG only opens SSH — the vLLM ports are reached through a tunnel.
# Runs in the foreground; Ctrl-C to close.
cmd_tunnel() {
  local ip forwards=()
  ip=$(public_ip)
  for p in ${TUNNEL_PORTS:-8001 8002}; do
    forwards+=(-L "$p:localhost:$p")
  done
  echo ">> forwarding ${TUNNEL_PORTS:-8001 8002} to localhost (Ctrl-C to close)"
  echo ">> try: curl http://localhost:8001/v1/models"
  exec ssh -i "$PRIVKEY_FILE" -N "${forwards[@]}" "ec2-user@$ip"
}

case "${1:-}" in
  up)     check_account; cmd_up ;;
  reset)  check_account; cmd_reset "${2:-}" ;;
  down)   check_account; cmd_down ;;
  stop)   check_account; cmd_stop ;;
  start)  check_account; cmd_start ;;
  status) check_account; cmd_status ;;
  ssh)    check_account; cmd_ssh ;;
  tunnel) check_account; cmd_tunnel ;;
  *) grep '^#   ' "$0" | sed 's/^#   //'; exit 1 ;;
esac
