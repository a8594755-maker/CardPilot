#!/bin/bash
# ============================================================
# CardPilot CFR Solver — Run on EC2 Instance
# ============================================================
#
# Run this INSIDE the EC2 instance after SSH'ing in.
#
# This script:
#   1. Clones the CardPilot repo
#   2. Installs dependencies
#   3. Runs the Standard tier solver (50bb + 100bb)
#   4. Compresses and uploads results to S3
#
# Usage:
#   bash aws-run.sh [YOUR_GITHUB_REPO_URL]
#
# ============================================================

set -e

REPO_URL="${1:-https://github.com/a8594755-maker/CardPilot.git}"
S3_BUCKET="${2:-cardpilot-solver-output}"
WORK_DIR="/data/cardpilot"

echo "=== CardPilot CFR Solver — EC2 Runner ==="
echo "Repo: ${REPO_URL}"
echo "S3 Bucket: ${S3_BUCKET}"
echo ""

# ---- Wait for setup to complete ----
echo "Waiting for instance setup..."
while [ ! -f /home/ubuntu/setup-done ]; do sleep 5; done
echo "Setup complete."

# ---- Clone repo ----
if [ ! -d "${WORK_DIR}" ]; then
  echo "Cloning repository..."
  git clone "${REPO_URL}" "${WORK_DIR}"
else
  echo "Repository exists, pulling latest..."
  cd "${WORK_DIR}" && git pull
fi

cd "${WORK_DIR}"

# ---- Install dependencies ----
echo "Installing dependencies..."
npm install

# ---- Create S3 bucket (if not exists) ----
aws s3 mb "s3://${S3_BUCKET}" 2>/dev/null || true

# ---- Solve: Standard 50bb ----
echo ""
echo "=========================================="
echo "  Phase 1: Standard 50bb (5 sizes, 200k iter)"
echo "=========================================="
echo ""

cd packages/cfr-solver

# Use nohup + screen so it survives SSH disconnection
# Output data goes to /data volume (2.5TB EBS)
npm run solve:standard:50bb 2>&1 | tee /data/solve_50bb.log

echo ""
echo "Phase 1 complete! Compressing 50bb data..."
cd /data/cardpilot/data/cfr/standard_hu_srp_50bb
tar -czf /data/standard_50bb.tar.gz *.jsonl *.meta.json
echo "Uploading 50bb to S3..."
aws s3 cp /data/standard_50bb.tar.gz "s3://${S3_BUCKET}/standard_50bb.tar.gz"
echo "50bb uploaded to s3://${S3_BUCKET}/standard_50bb.tar.gz"

# ---- Solve: Standard 100bb ----
echo ""
echo "=========================================="
echo "  Phase 2: Standard 100bb (5 sizes, 200k iter)"
echo "=========================================="
echo ""

cd "${WORK_DIR}/packages/cfr-solver"
npm run solve:standard:100bb 2>&1 | tee /data/solve_100bb.log

echo ""
echo "Phase 2 complete! Compressing 100bb data..."
cd /data/cardpilot/data/cfr/standard_hu_srp_100bb
tar -czf /data/standard_100bb.tar.gz *.jsonl *.meta.json
echo "Uploading 100bb to S3..."
aws s3 cp /data/standard_100bb.tar.gz "s3://${S3_BUCKET}/standard_100bb.tar.gz"
echo "100bb uploaded to s3://${S3_BUCKET}/standard_100bb.tar.gz"

# ---- Summary ----
echo ""
echo "============================================"
echo "  ALL DONE!"
echo "============================================"
echo ""
echo "S3 outputs:"
echo "  s3://${S3_BUCKET}/standard_50bb.tar.gz"
echo "  s3://${S3_BUCKET}/standard_100bb.tar.gz"
echo ""
echo "To download locally:"
echo "  aws s3 cp s3://${S3_BUCKET}/standard_50bb.tar.gz ."
echo "  aws s3 cp s3://${S3_BUCKET}/standard_100bb.tar.gz ."
echo ""
echo "To terminate this instance:"
echo "  INSTANCE_ID=\$(curl -s http://169.254.169.254/latest/meta-data/instance-id)"
echo "  aws ec2 terminate-instances --instance-ids \$INSTANCE_ID"
echo ""
echo "Don't forget to terminate to stop billing!"
