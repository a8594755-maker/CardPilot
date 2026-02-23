#!/bin/bash
# ============================================================
# CardPilot CFR Solver — Run on EC2 Instance (Spot-Safe)
# ============================================================
#
# Run this INSIDE the EC2 instance after SSH'ing in.
#
# This script:
#   1. Downloads any previous progress from S3 (resume support)
#   2. Clones/updates the CardPilot repo
#   3. Starts background S3 sync (every 5 min)
#   4. Runs the Standard tier solver (50bb + 100bb)
#   5. Uploads final results to S3
#
# Spot-safe: if the instance is interrupted, progress is saved
# to S3. Re-launch a new instance and re-run to continue.
#
# Usage:
#   bash aws-run.sh [YOUR_GITHUB_REPO_URL] [S3_BUCKET]
#
# ============================================================

set -e

REPO_URL="${1:-https://github.com/a8594755-maker/CardPilot.git}"
S3_BUCKET="${2:-cardpilot-solver-output}"
WORK_DIR="/data/cardpilot"

# Auto-detect safe worker count based on available RAM
# Each worker needs ~8-16GB RAM for 100-bucket standard solve
TOTAL_RAM_GB=$(free -g 2>/dev/null | awk '/^Mem:/{print $2}' || echo 64)
MAX_WORKERS=$(( TOTAL_RAM_GB / 16 ))
if [ "$MAX_WORKERS" -lt 1 ]; then MAX_WORKERS=1; fi
if [ "$MAX_WORKERS" -gt 32 ]; then MAX_WORKERS=32; fi

echo "=== CardPilot CFR Solver — EC2 Runner (Spot-Safe) ==="
echo "Repo: ${REPO_URL}"
echo "S3 Bucket: ${S3_BUCKET}"
echo "RAM: ${TOTAL_RAM_GB}GB → Workers: ${MAX_WORKERS}"
echo ""

# ---- Helper: Sync progress to S3 ----
sync_to_s3() {
  local CFR_DIR="${WORK_DIR}/data/cfr"
  if [ -d "$CFR_DIR" ]; then
    aws s3 sync "$CFR_DIR/" "s3://${S3_BUCKET}/progress/" \
      --exclude "*" --include "*.jsonl" --include "*.meta.json" --include "_progress.json" \
      --quiet 2>/dev/null || true
  fi
}

# ---- Helper: Download previous progress from S3 ----
sync_from_s3() {
  echo "Checking S3 for previous progress..."
  local CFR_DIR="${WORK_DIR}/data/cfr"
  mkdir -p "$CFR_DIR"

  local COUNT=$(aws s3 ls "s3://${S3_BUCKET}/progress/" --recursive 2>/dev/null | wc -l || echo 0)
  if [ "$COUNT" -gt 0 ]; then
    echo "  Found ${COUNT} files in S3. Downloading previous progress..."
    aws s3 sync "s3://${S3_BUCKET}/progress/" "$CFR_DIR/" \
      --exclude "*" --include "*.jsonl" --include "*.meta.json" --include "_progress.json" \
      --quiet 2>/dev/null || true

    # Count resumed flops per config
    for dir in "$CFR_DIR"/*/; do
      if [ -d "$dir" ]; then
        local NAME=$(basename "$dir")
        local FLOP_COUNT=$(ls "$dir"/*.meta.json 2>/dev/null | wc -l || echo 0)
        echo "  ${NAME}: ${FLOP_COUNT} flops already solved"
      fi
    done
  else
    echo "  No previous progress found. Starting fresh."
  fi
  echo ""
}

# ---- Background S3 sync (every 5 min) ----
BG_SYNC_PID=""
start_bg_sync() {
  (
    while true; do
      sleep 300
      sync_to_s3
      echo "[bg-sync] Progress synced to S3 at $(date '+%H:%M:%S')"
    done
  ) &
  BG_SYNC_PID=$!
  echo "Background S3 sync started (every 5 min, PID: ${BG_SYNC_PID})"
}

stop_bg_sync() {
  if [ -n "$BG_SYNC_PID" ]; then
    kill $BG_SYNC_PID 2>/dev/null || true
    wait $BG_SYNC_PID 2>/dev/null || true
    BG_SYNC_PID=""
  fi
}

# Clean up background sync on exit
trap 'stop_bg_sync; sync_to_s3; echo "Final S3 sync done."' EXIT

# ---- Wait for setup to complete ----
echo "Waiting for instance setup..."
while [ ! -f /home/ubuntu/setup-done ]; do sleep 5; done
echo "Setup complete."
echo ""

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

# ---- Download previous progress from S3 ----
sync_from_s3

# ---- Start background S3 sync ----
start_bg_sync

# ---- Create S3 bucket (if not exists) ----
aws s3 mb "s3://${S3_BUCKET}" 2>/dev/null || true

# ---- Solve: Standard 50bb ----
echo ""
echo "=========================================="
echo "  Phase 1: Standard 50bb (5 sizes, 200k iter)"
echo "=========================================="
echo ""

cd packages/cfr-solver

node --import tsx src/cli/solve.ts \
  --config standard_50bb --all-flops --parallel --resume \
  --workers ${MAX_WORKERS} 2>&1 | tee /data/solve_50bb.log

echo ""
echo "Phase 1 complete! Syncing 50bb to S3..."
sync_to_s3

# Also create compressed archive for final download
CFR_50BB="${WORK_DIR}/data/cfr/standard_hu_srp_50bb"
if [ -d "$CFR_50BB" ] && ls "$CFR_50BB"/*.jsonl &>/dev/null; then
  cd "$CFR_50BB"
  tar -czf /data/standard_50bb.tar.gz *.jsonl *.meta.json
  aws s3 cp /data/standard_50bb.tar.gz "s3://${S3_BUCKET}/standard_50bb.tar.gz"
  echo "50bb archive uploaded to s3://${S3_BUCKET}/standard_50bb.tar.gz"
fi

# ---- Solve: Standard 100bb ----
echo ""
echo "=========================================="
echo "  Phase 2: Standard 100bb (5 sizes, 200k iter)"
echo "=========================================="
echo ""

cd "${WORK_DIR}/packages/cfr-solver"
node --import tsx src/cli/solve.ts \
  --config standard_100bb --all-flops --parallel --resume \
  --workers ${MAX_WORKERS} 2>&1 | tee /data/solve_100bb.log

echo ""
echo "Phase 2 complete! Syncing 100bb to S3..."
sync_to_s3

# Create compressed archive
CFR_100BB="${WORK_DIR}/data/cfr/standard_hu_srp_100bb"
if [ -d "$CFR_100BB" ] && ls "$CFR_100BB"/*.jsonl &>/dev/null; then
  cd "$CFR_100BB"
  tar -czf /data/standard_100bb.tar.gz *.jsonl *.meta.json
  aws s3 cp /data/standard_100bb.tar.gz "s3://${S3_BUCKET}/standard_100bb.tar.gz"
  echo "100bb archive uploaded to s3://${S3_BUCKET}/standard_100bb.tar.gz"
fi

# ---- Summary ----
echo ""
echo "============================================"
echo "  ALL DONE!"
echo "============================================"
echo ""
echo "S3 outputs:"
echo "  s3://${S3_BUCKET}/standard_50bb.tar.gz"
echo "  s3://${S3_BUCKET}/standard_100bb.tar.gz"
echo "  s3://${S3_BUCKET}/progress/ (individual flop files)"
echo ""
echo "To download locally:"
echo "  aws s3 cp s3://${S3_BUCKET}/standard_50bb.tar.gz ."
echo "  aws s3 cp s3://${S3_BUCKET}/standard_100bb.tar.gz ."
echo ""

# Auto-shutdown after completion
echo "Shutting down instance in 5 minutes..."
sudo shutdown -h +5
