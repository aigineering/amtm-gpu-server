# Drop cred envars from aws login console.

cd /Users/sim/src/amitim/gpu-vllm-setup/infra

REGION=us-east-1 AZ=us-east-1a ./env.sh reset
REGION=eu-central-1 AZ=eu-central-1a ./env.sh reset
REGION=eu-south-2 AZ=eu-south-2b ./env.sh reset