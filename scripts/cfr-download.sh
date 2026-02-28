#!/bin/bash
# ============================================================
# Download CFR solver data from iDrive e2 (S3-compatible)
# ============================================================
#
# Usage:
#   bash scripts/cfr-download.sh [--raw] [--models] [--all]
#
# Flags:
#   (default)  Download binary .bin.gz files only (~1.4 GB)
#   --raw      Also download and extract raw JSONL archives
#   --models   Also download model files
#   --all      Download everything
#
# Requires: AWS CLI (aws) + credentials in cluster.env
# ============================================================

set -e

# --- Find project root ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CFR_DIR="${PROJECT_ROOT}/data/cfr"
MODELS_DIR="${PROJECT_ROOT}/models"

# --- Load e2 credentials ---
ENV_FILE="${PROJECT_ROOT}/packages/cfr-solver/scripts/cluster.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found."
  echo "Create it with E2_PROFILE, E2_ENDPOINT, E2_BUCKET"
  echo ""
  echo "Example:"
  echo "  E2_PROFILE=idrive-e2"
  echo "  E2_ENDPOINT=https://s3.us-east-1.idrivee2.com"
  echo "  E2_BUCKET=cardpilot-cfr-data"
  exit 1
fi
source "$ENV_FILE"

if [ -z "$E2_PROFILE" ] || [ -z "$E2_ENDPOINT" ] || [ -z "$E2_BUCKET" ]; then
  echo "ERROR: Missing e2 credentials in $ENV_FILE"
  echo "Required: E2_PROFILE, E2_ENDPOINT, E2_BUCKET"
  exit 1
fi

S3="aws s3 --profile ${E2_PROFILE} --endpoint-url ${E2_ENDPOINT}"
S3_BUCKET="s3://${E2_BUCKET}"

# --- Parse flags ---
DOWNLOAD_RAW=false
DOWNLOAD_MODELS=false

for arg in "$@"; do
  case $arg in
    --raw)     DOWNLOAD_RAW=true ;;
    --models)  DOWNLOAD_MODELS=true ;;
    --all)     DOWNLOAD_RAW=true; DOWNLOAD_MODELS=true ;;
    *)         echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

echo "============================================"
echo "  CardPilot CFR Data Download (iDrive e2)"
echo "============================================"
echo "Bucket:   ${E2_BUCKET}"
echo "Target:   ${CFR_DIR}"
echo ""

# --- Ensure directories exist ---
mkdir -p "$CFR_DIR"
mkdir -p "$MODELS_DIR"

# --- Download binary files (always) ---
echo "=== Downloading binary .bin.gz files ==="
BINARIES=$($S3 ls "${S3_BUCKET}/binary/" 2>/dev/null | awk '{print $NF}' || true)

if [ -z "$BINARIES" ]; then
  echo "  No binary files found in bucket"
else
  BIN_COUNT=0
  while IFS= read -r BASENAME; do
    [ -z "$BASENAME" ] && continue
    LOCAL_PATH="${CFR_DIR}/${BASENAME}"

    if [ -f "$LOCAL_PATH" ]; then
      echo "  ${BASENAME} — already exists, skipping"
      echo "    (delete to force re-download)"
      continue
    fi

    echo "  Downloading ${BASENAME} ..."
    $S3 cp "${S3_BUCKET}/binary/${BASENAME}" "$LOCAL_PATH"
    BIN_COUNT=$((BIN_COUNT + 1))
  done <<< "$BINARIES"
  echo "  Downloaded ${BIN_COUNT} new binary file(s)"
fi
echo ""

# --- Download and extract raw JSONL ---
if [ "$DOWNLOAD_RAW" = true ]; then
  echo "=== Downloading raw JSONL archives ==="
  ARCHIVES=$($S3 ls "${S3_BUCKET}/raw/" 2>/dev/null | awk '{print $NF}' || true)

  if [ -z "$ARCHIVES" ]; then
    echo "  No raw archives found in bucket"
  else
    RAW_COUNT=0
    while IFS= read -r ARCHIVE; do
      [ -z "$ARCHIVE" ] && continue
      # Archive name like pipeline_hu_3bet_50bb.tar.gz
      DIRNAME="${ARCHIVE%.tar.gz}"
      TARGETDIR="${CFR_DIR}/${DIRNAME}"

      if [ -d "$TARGETDIR" ]; then
        LOCAL_META=$(ls "${TARGETDIR}"/*.meta.json 2>/dev/null | wc -l)
        if [ "$LOCAL_META" -gt 0 ]; then
          echo "  ${DIRNAME}/ — already exists (${LOCAL_META} flops), skipping"
          echo "    (delete ${TARGETDIR} to force re-download)"
          continue
        fi
      fi

      echo "  Downloading ${ARCHIVE} ..."
      TMPFILE="/tmp/${ARCHIVE}"
      $S3 cp "${S3_BUCKET}/raw/${ARCHIVE}" "$TMPFILE"

      echo "  Extracting to ${CFR_DIR}/ ..."
      tar -xzf "$TMPFILE" -C "${CFR_DIR}/"
      rm -f "$TMPFILE"

      EXTRACTED=$(ls "${TARGETDIR}"/*.meta.json 2>/dev/null | wc -l)
      echo "  Extracted ${EXTRACTED} flops"
      RAW_COUNT=$((RAW_COUNT + 1))
    done <<< "$ARCHIVES"
    echo "  Downloaded ${RAW_COUNT} raw archive(s)"
  fi
  echo ""
fi

# --- Download model files ---
if [ "$DOWNLOAD_MODELS" = true ]; then
  echo "=== Downloading model files ==="
  MODELS=$($S3 ls "${S3_BUCKET}/models/" 2>/dev/null | awk '{print $NF}' || true)

  if [ -z "$MODELS" ]; then
    echo "  No model files found in bucket"
  else
    MODEL_COUNT=0
    while IFS= read -r BASENAME; do
      [ -z "$BASENAME" ] && continue
      LOCAL_PATH="${MODELS_DIR}/${BASENAME}"

      if [ -f "$LOCAL_PATH" ]; then
        echo "  ${BASENAME} — already exists, skipping"
        continue
      fi

      echo "  Downloading ${BASENAME} ..."
      $S3 cp "${S3_BUCKET}/models/${BASENAME}" "$LOCAL_PATH"
      MODEL_COUNT=$((MODEL_COUNT + 1))
    done <<< "$MODELS"
    echo "  Downloaded ${MODEL_COUNT} model file(s)"
  fi
  echo ""
fi

# --- Summary ---
echo "============================================"
echo "  Download complete!"
echo ""
echo "  Binary files: ${CFR_DIR}/*.bin.gz"
if [ "$DOWNLOAD_RAW" = true ]; then
  echo "  Raw JSONL:    ${CFR_DIR}/*/"
fi
if [ "$DOWNLOAD_MODELS" = true ]; then
  echo "  Models:       ${MODELS_DIR}/"
fi
echo "============================================"
