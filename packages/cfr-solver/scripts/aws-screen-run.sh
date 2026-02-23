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

REPO_URL="${1:-https://github.com/YOUR_USER/CardPilot.git}"
S3_BUCKET="${2:-cardpilot-solver-output}"

# Install screen if not available
sudo apt-get install -y screen 2>/dev/null || true

echo "Starting solver in screen session 'solver'..."
echo "To detach: Ctrl+A, then D"
echo "To re-attach: screen -r solver"
echo ""

screen -dmS solver bash -c "bash /data/cardpilot/packages/cfr-solver/scripts/aws-run.sh '${REPO_URL}' '${S3_BUCKET}' 2>&1 | tee /data/solver-full.log; echo 'DONE - press Enter to close'; read"

echo "Screen session started. Attach with:"
echo "  screen -r solver"
