#!/bin/bash
# ============================================================
# Run solver inside GNU Screen (survives SSH disconnect)
# ============================================================
#
# Usage (on EC2):
#   bash aws-screen-run.sh [REPO_URL] [S3_BUCKET]
#
# To re-attach after disconnect:
#   screen -r solver
#
# ============================================================

REPO_URL="${1:-https://github.com/a8594755-maker/CardPilot.git}"
S3_BUCKET="${2:-cardpilot-solver-output}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Install screen if not available
sudo apt-get install -y screen 2>/dev/null || true

# Kill existing solver session if any
screen -X -S solver quit 2>/dev/null || true

echo "Starting solver in screen session 'solver'..."
echo "  To detach: Ctrl+A, then D"
echo "  To re-attach: screen -r solver"
echo "  Progress syncs to S3 every 5 min (spot-safe)"
echo ""

screen -dmS solver bash -c "bash ${SCRIPT_DIR}/aws-run.sh '${REPO_URL}' '${S3_BUCKET}' 2>&1 | tee /data/solver-full.log; echo 'DONE - press Enter to close'; read"

echo "Screen session started. Attach with:"
echo "  screen -r solver"
