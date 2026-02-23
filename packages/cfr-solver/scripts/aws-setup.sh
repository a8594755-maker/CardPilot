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
#   3. Run the solver (via aws-screen-run.sh)
#   4. Results auto-sync to S3 every 5 min (spot-safe)
#
# Spot Instance Strategy:
#   - ~60-70% cheaper than on-demand
#   - If interrupted, progress is saved to S3 (incremental sync)
#   - Re-run this script + aws-screen-run.sh to resume from where it stopped
#   - The solver's --resume flag skips already-completed flops
#
# ============================================================

set -e

# ---- Configuration ----
INSTANCE_TYPE="r6i.8xlarge"     # 32 vCPU, 256GB RAM (16 solver workers, memory-optimized)
EBS_SIZE_GB=100                 # 100GB root + data (progress syncs to S3, no need for huge EBS)
USE_SPOT=true                   # Spot pricing (~70% cheaper, may be interrupted)
AMI_ID="ami-0c7217cdde317cfec"  # Ubuntu 22.04 LTS (us-east-1, update for your region)
KEY_NAME="cardpilot-solver"     # Your AWS key pair name
SECURITY_GROUP="cardpilot-sg"   # Will be created if not exists
REGION="us-east-1"
S3_BUCKET="cardpilot-solver-output"

echo "=== CardPilot CFR Solver — AWS Setup ==="
echo "Instance: ${INSTANCE_TYPE} (spot=${USE_SPOT})"
echo "Region: ${REGION}"
echo "S3 Bucket: ${S3_BUCKET}"
echo ""

# ---- Step 0: Terminate existing solver instances ----
echo "Checking for existing solver instances..."
EXISTING_IDS=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=cardpilot-solver" \
             "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --region "${REGION}" \
  --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_IDS" ] && [ "$EXISTING_IDS" != "None" ]; then
  echo "  Terminating existing instances: ${EXISTING_IDS}"
  aws ec2 terminate-instances --instance-ids ${EXISTING_IDS} --region "${REGION}" > /dev/null
  echo "  Waiting for termination..."
  aws ec2 wait instance-terminated --instance-ids ${EXISTING_IDS} --region "${REGION}" 2>/dev/null || true
  echo "  Done."
else
  echo "  No existing instances found."
fi

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

# ---- Step 3: Create S3 bucket (if not exists) ----
echo "Ensuring S3 bucket exists..."
aws s3 mb "s3://${S3_BUCKET}" --region "${REGION}" 2>/dev/null || true

# ---- Step 4: Launch Instance ----
echo ""
echo "Launching instance..."

# User data script that runs on first boot
USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
set -e

# Install Node.js 20 + AWS CLI + screen
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs git screen awscli

# Create workspace
mkdir -p /home/ubuntu/solver /data
chown ubuntu:ubuntu /home/ubuntu/solver /data

# ---- Spot Termination Monitor (systemd service) ----
cat > /usr/local/bin/spot-monitor.sh <<'SPOTMON'
#!/bin/bash
# Monitors for spot termination notice and syncs progress to S3
S3_BUCKET="cardpilot-solver-output"
WORK_DIR="/data/cardpilot"

get_imds_token() {
  curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 300" 2>/dev/null
}

check_spot_termination() {
  local TOKEN=$(get_imds_token)
  local HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-aws-ec2-metadata-token: $TOKEN" \
    "http://169.254.169.254/latest/meta-data/spot/instance-action" 2>/dev/null)
  [ "$HTTP_CODE" = "200" ]
}

sync_progress() {
  if [ -d "${WORK_DIR}/data/cfr" ]; then
    echo "[spot-monitor] Syncing progress to S3..."
    aws s3 sync "${WORK_DIR}/data/cfr/" "s3://${S3_BUCKET}/progress/" \
      --exclude "*" --include "*.jsonl" --include "*.meta.json" --include "_progress.json" \
      --quiet 2>/dev/null || true
    echo "[spot-monitor] Sync complete."
  fi
}

echo "[spot-monitor] Started. Watching for spot termination..."
while true; do
  if check_spot_termination; then
    echo "[spot-monitor] *** SPOT TERMINATION NOTICE RECEIVED ***"
    echo "[spot-monitor] Syncing progress to S3 before shutdown..."
    sync_progress
    echo "[spot-monitor] Done. Instance will be terminated by AWS."
    # Signal the solver to stop gracefully
    pkill -SIGTERM -f "solve.ts" 2>/dev/null || true
    sleep 5
    sync_progress  # one more sync after solver stops
    exit 0
  fi
  sleep 5
done
SPOTMON
chmod +x /usr/local/bin/spot-monitor.sh

# Create systemd service for spot monitor
cat > /etc/systemd/system/spot-monitor.service <<'SVCFILE'
[Unit]
Description=Spot Instance Termination Monitor
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/spot-monitor.sh
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
SVCFILE

systemctl daemon-reload
systemctl enable spot-monitor
systemctl start spot-monitor

echo "Setup complete" > /home/ubuntu/setup-done
USERDATA
)

ENCODED_USER_DATA=$(echo "$USER_DATA" | base64 -w 0)

# Build launch command
SPOT_FLAG=""
if [ "$USE_SPOT" = true ]; then
  SPOT_FLAG='--instance-market-options {"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time","InstanceInterruptionBehavior":"terminate"}}'
fi

# IAM instance profile for S3 access — create if needed
INSTANCE_PROFILE="cardpilot-solver-profile"
ROLE_NAME="cardpilot-solver-role"

echo "Setting up IAM role for S3 access..."
if ! aws iam get-instance-profile --instance-profile-name "${INSTANCE_PROFILE}" &>/dev/null; then
  # Create role
  aws iam create-role \
    --role-name "${ROLE_NAME}" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
    > /dev/null 2>&1 || true

  # Attach S3 policy
  aws iam put-role-policy \
    --role-name "${ROLE_NAME}" \
    --policy-name "S3Access" \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\",\"s3:DeleteObject\"],\"Resource\":[\"arn:aws:s3:::${S3_BUCKET}\",\"arn:aws:s3:::${S3_BUCKET}/*\"]}]}" \
    > /dev/null 2>&1 || true

  # Create instance profile and attach role
  aws iam create-instance-profile \
    --instance-profile-name "${INSTANCE_PROFILE}" > /dev/null 2>&1 || true
  aws iam add-role-to-instance-profile \
    --instance-profile-name "${INSTANCE_PROFILE}" \
    --role-name "${ROLE_NAME}" > /dev/null 2>&1 || true

  echo "  Created IAM profile: ${INSTANCE_PROFILE}"
  echo "  Waiting for IAM propagation..."
  sleep 10
else
  echo "  IAM profile exists: ${INSTANCE_PROFILE}"
fi

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "${AMI_ID}" \
  --instance-type "${INSTANCE_TYPE}" \
  --key-name "${KEY_NAME}" \
  --security-group-ids "${SG_ID}" \
  --iam-instance-profile "Name=${INSTANCE_PROFILE}" \
  ${SPOT_FLAG} \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${EBS_SIZE_GB},\"VolumeType\":\"gp3\",\"Iops\":6000,\"Throughput\":400}}]" \
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
echo "  Instance ready! (spot=${USE_SPOT})"
echo "  IP: ${PUBLIC_IP}"
echo "  SSH: ssh -i ${KEY_FILE} ubuntu@${PUBLIC_IP}"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. SSH into the instance:"
echo "     ssh -i ${KEY_FILE} ubuntu@${PUBLIC_IP}"
echo ""
echo "  2. Wait for setup, then run solver:"
echo "     cat /home/ubuntu/setup-done"
echo "     bash /home/ubuntu/solver/aws-screen-run.sh"
echo ""
echo "  3. Monitor progress:"
echo "     screen -r solver"
echo "     # Ctrl+A, D to detach"
echo ""
echo "Spot Instance Info:"
echo "  - Progress auto-syncs to S3 every 5 min"
echo "  - If interrupted, re-run this script to resume"
echo "  - Spot monitor active: systemctl status spot-monitor"
echo ""
echo "To terminate when done:"
echo "  aws ec2 terminate-instances --instance-ids ${INSTANCE_ID} --region ${REGION}"
