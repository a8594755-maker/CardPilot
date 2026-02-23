#!/bin/bash
# ============================================================
# Download solver results from S3 to local machine
# ============================================================
#
# Usage:
#   bash download-results.sh [S3_BUCKET]
#
# This downloads and extracts the solver output into the
# correct data/cfr/ directories.
# ============================================================

set -e

S3_BUCKET="${1:-cardpilot-solver-output}"

# Find project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CFR_DIR="${PROJECT_ROOT}/data/cfr"

echo "=== Download CardPilot Solver Results ==="
echo "S3 Bucket: ${S3_BUCKET}"
echo "Target: ${CFR_DIR}"
echo ""

# ---- Download 50bb ----
echo "Downloading standard_50bb..."
mkdir -p "${CFR_DIR}/standard_hu_srp_50bb"
aws s3 cp "s3://${S3_BUCKET}/standard_50bb.tar.gz" /tmp/standard_50bb.tar.gz
echo "Extracting..."
tar -xzf /tmp/standard_50bb.tar.gz -C "${CFR_DIR}/standard_hu_srp_50bb/"
rm /tmp/standard_50bb.tar.gz

COUNT_50=$(ls "${CFR_DIR}/standard_hu_srp_50bb/"*.meta.json 2>/dev/null | wc -l)
echo "  Extracted ${COUNT_50} flops"

# ---- Download 100bb ----
echo "Downloading standard_100bb..."
mkdir -p "${CFR_DIR}/standard_hu_srp_100bb"
aws s3 cp "s3://${S3_BUCKET}/standard_100bb.tar.gz" /tmp/standard_100bb.tar.gz
echo "Extracting..."
tar -xzf /tmp/standard_100bb.tar.gz -C "${CFR_DIR}/standard_hu_srp_100bb/"
rm /tmp/standard_100bb.tar.gz

COUNT_100=$(ls "${CFR_DIR}/standard_hu_srp_100bb/"*.meta.json 2>/dev/null | wc -l)
echo "  Extracted ${COUNT_100} flops"

echo ""
echo "============================================"
echo "  Done!"
echo "  50bb: ${COUNT_50} flops"
echo "  100bb: ${COUNT_100} flops"
echo "============================================"
echo ""
echo "Start the viewer:"
echo "  cd packages/cfr-solver && npm run viewer"
