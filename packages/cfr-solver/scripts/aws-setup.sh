#!/bin/bash
# ============================================================
# CardPilot CFR Solver — AWS EC2 Setup & Run Script
# ============================================================
#
# Prerequisites:
#   1. AWS CLI installed and configured (aws configure)
#   2. An SSH key pair in AWS (or create one below)
#
# Usage:
#   1. Run this script on your LOCAL machine to launch the EC2 instance
#   2. SSH into the instance
#   3. Run the solver
#   4. Download results or upload to S3
#
# Recommended instance: c6i.24xlarge (96 vCPU, 192GB RAM)
#   - Spot price: ~$1.10/hr (vs $4.08 on-demand)
#   - Estimated runtime: ~60 hours for Standard tier
#   - Estimated cost: ~$65-70
#
# ============================================================

set -e

# ---- Configuration ----
INSTANCE_TYPE="c6i.8xlarge"     # 32 vCPU, 64GB RAM (4 solver workers)
EBS_SIZE_GB=2500                # 2.5TB for solver output + buffer
USE_SPOT=false                  # Set to true for spot pricing (~70% cheaper)
AMI_ID="ami-0c7217cdde317cfec"  # Ubuntu 22.04 LTS (us-east-1, update for your region)
KEY_NAME="cardpilot-solver"     # Your AWS key pair name
SECURITY_GROUP="cardpilot-sg"   # Will be created if not exists
REGION="us-east-1"

echo "=== CardPilot CFR Solver — AWS Setup ==="
echo "Instance: ${INSTANCE_TYPE}"
echo "EBS: ${EBS_SIZE_GB}GB"
echo "Region: ${REGION}"
echo ""

# ---- Step 1: Create Security Group (if not exists) ----
echo "Creating security group..."
SG_ID=$(aws ec2 describe-security-groups \
  --group-names "${SECURITY_GROUP}" \
  --region "${REGION}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || echo "")

if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group \
    --group-name "${SECURITY_GROUP}" \
    --description "CardPilot solver SSH access" \
    --region "${REGION}" \
    --query 'GroupId' --output text)

  aws ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" \
    --protocol tcp --port 22 \
    --cidr 0.0.0.0/0 \
    --region "${REGION}"
  echo "  Created: ${SG_ID}"
else
  echo "  Exists: ${SG_ID}"
fi

# ---- Step 2: Create Key Pair (if not exists) ----
KEY_FILE="${HOME}/.ssh/${KEY_NAME}.pem"
if ! aws ec2 describe-key-pairs --key-names "${KEY_NAME}" --region "${REGION}" &>/dev/null; then
  echo "Creating key pair..."
  aws ec2 create-key-pair \
    --key-name "${KEY_NAME}" \
    --region "${REGION}" \
    --query 'KeyMaterial' --output text > "${KEY_FILE}"
  chmod 400 "${KEY_FILE}"
  echo "  Saved to: ${KEY_FILE}"
else
  echo "Key pair exists: ${KEY_NAME}"
fi

# ---- Step 3: Launch Instance ----
echo ""
echo "Launching instance (spot=${USE_SPOT})..."

# User data script that runs on first boot
USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
set -e

# Install Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs git

# Create workspace
mkdir -p /home/ubuntu/solver
chown ubuntu:ubuntu /home/ubuntu/solver

# Format and mount EBS data volume (if attached as /dev/nvme1n1 or /dev/xvdf)
if [ -b /dev/nvme1n1 ]; then
  DATA_DEV=/dev/nvme1n1
elif [ -b /dev/xvdf ]; then
  DATA_DEV=/dev/xvdf
else
  DATA_DEV=""
fi

if [ -n "$DATA_DEV" ]; then
  mkfs -t ext4 "$DATA_DEV" 2>/dev/null || true
  mkdir -p /data
  mount "$DATA_DEV" /data
  chown ubuntu:ubuntu /data
  echo "$DATA_DEV /data ext4 defaults,nofail 0 2" >> /etc/fstab
fi

echo "Setup complete" > /home/ubuntu/setup-done
USERDATA
)

ENCODED_USER_DATA=$(echo "$USER_DATA" | base64 -w 0)

# Build launch command
SPOT_FLAG=""
if [ "$USE_SPOT" = true ]; then
  SPOT_FLAG="--instance-market-options {\"MarketType\":\"spot\",\"SpotOptions\":{\"SpotInstanceType\":\"one-time\"}}"
fi

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "${AMI_ID}" \
  --instance-type "${INSTANCE_TYPE}" \
  --key-name "${KEY_NAME}" \
  --security-group-ids "${SG_ID}" \
  ${SPOT_FLAG} \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":100,\"VolumeType\":\"gp3\"}},{\"DeviceName\":\"/dev/xvdf\",\"Ebs\":{\"VolumeSize\":${EBS_SIZE_GB},\"VolumeType\":\"gp3\",\"Iops\":6000,\"Throughput\":400}}]" \
  --user-data "${ENCODED_USER_DATA}" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=cardpilot-solver}]" \
  --region "${REGION}" \
  --query 'Instances[0].InstanceId' --output text)

echo "  Instance ID: ${INSTANCE_ID}"

# Wait for instance to be running
echo "Waiting for instance to start..."
aws ec2 wait instance-running --instance-ids "${INSTANCE_ID}" --region "${REGION}"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "${INSTANCE_ID}" \
  --region "${REGION}" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo ""
echo "============================================"
echo "  Instance ready!"
echo "  IP: ${PUBLIC_IP}"
echo "  SSH: ssh -i ${KEY_FILE} ubuntu@${PUBLIC_IP}"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. SSH into the instance"
echo "  2. Wait for setup: cat /home/ubuntu/setup-done"
echo "  3. Clone your repo and run the solver (see aws-run.sh)"
echo ""
echo "To terminate when done:"
echo "  aws ec2 terminate-instances --instance-ids ${INSTANCE_ID} --region ${REGION}"
