#!/bin/bash
# ============================================================
# Upload CFR solver data to iDrive e2 (S3-compatible)
# ============================================================
#
# Usage:
#   bash scripts/cfr-upload.sh [--binary] [--raw] [--models] [--all]
#
# Flags:
#   --binary   Upload .bin.gz binary strategy files (default)
#   --raw      Compress and upload raw JSONL directories
#   --jsonl    Upload individual JSONL + meta files (for web lookup)
#   --models   Upload model files from models/
#   --all      Upload everything
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
UPLOAD_BINARY=false
UPLOAD_RAW=false
UPLOAD_JSONL=false
UPLOAD_MODELS=false

if [ $# -eq 0 ]; then
  UPLOAD_BINARY=true
fi

for arg in "$@"; do
  case $arg in
    --binary)  UPLOAD_BINARY=true ;;
    --raw)     UPLOAD_RAW=true ;;
    --jsonl)   UPLOAD_JSONL=true ;;
    --models)  UPLOAD_MODELS=true ;;
    --all)     UPLOAD_BINARY=true; UPLOAD_RAW=true; UPLOAD_JSONL=true; UPLOAD_MODELS=true ;;
    *)         echo "Unknown flag: $arg"; exit 1 ;;
  esac
done

echo "============================================"
echo "  CardPilot CFR Data Upload (iDrive e2)"
echo "============================================"
echo "Bucket:   ${E2_BUCKET}"
echo "Data dir: ${CFR_DIR}"
echo ""

# --- Upload binary files ---
if [ "$UPLOAD_BINARY" = true ]; then
  echo "=== Uploading binary .bin.gz files ==="
  BIN_COUNT=0
  for binfile in "${CFR_DIR}"/*.bin.gz; do
    [ -f "$binfile" ] || continue
    BASENAME=$(basename "$binfile")
    echo "  Uploading binary/${BASENAME} ..."
    $S3 cp "$binfile" "${S3_BUCKET}/binary/${BASENAME}"
    BIN_COUNT=$((BIN_COUNT + 1))
  done
  if [ $BIN_COUNT -eq 0 ]; then
    echo "  No .bin.gz files found in ${CFR_DIR}/"
    echo "  Run 'npx tsx scripts/export-binary.ts' first to generate binary files."
  else
    echo "  Uploaded ${BIN_COUNT} binary file(s)"
  fi
  echo ""
fi

# --- Compress and upload raw JSONL ---
if [ "$UPLOAD_RAW" = true ]; then
  echo "=== Compressing and uploading raw JSONL ==="
  RAW_COUNT=0
  for configdir in "${CFR_DIR}"/*/; do
    [ -d "$configdir" ] || continue
    DIRNAME=$(basename "$configdir")

    # Count meta files to check if there's data
    META_COUNT=$(ls "${configdir}"*.meta.json 2>/dev/null | wc -l)
    if [ "$META_COUNT" -eq 0 ]; then
      echo "  Skipping ${DIRNAME} (no solved flops)"
      continue
    fi

    TARFILE="${CFR_DIR}/${DIRNAME}.tar.gz"
    echo "  Compressing ${DIRNAME} (${META_COUNT} flops) ..."
    tar -czf "$TARFILE" -C "${CFR_DIR}" "${DIRNAME}/"

    TARSIZE=$(du -h "$TARFILE" | cut -f1)
    echo "  Uploading raw/${DIRNAME}.tar.gz (${TARSIZE}) ..."
    $S3 cp "$TARFILE" "${S3_BUCKET}/raw/${DIRNAME}.tar.gz"

    # Clean up local tar.gz (it's in .gitignore anyway)
    rm -f "$TARFILE"

    RAW_COUNT=$((RAW_COUNT + 1))
  done
  echo "  Uploaded ${RAW_COUNT} raw archive(s)"
  echo ""
fi

# --- Upload model files ---
if [ "$UPLOAD_MODELS" = true ]; then
  echo "=== Uploading model files ==="
  MODEL_COUNT=0
  for modelfile in "${MODELS_DIR}"/*.json; do
    [ -f "$modelfile" ] || continue
    BASENAME=$(basename "$modelfile")
    echo "  Uploading models/${BASENAME} ..."
    $S3 cp "$modelfile" "${S3_BUCKET}/models/${BASENAME}"
    MODEL_COUNT=$((MODEL_COUNT + 1))
  done
  echo "  Uploaded ${MODEL_COUNT} model file(s)"
  echo ""
fi

# --- Upload individual JSONL + meta files (for web CFR lookup) ---
if [ "$UPLOAD_JSONL" = true ]; then
  echo "=== Uploading individual JSONL + meta files ==="
  JSONL_CONFIG_COUNT=0
  for configdir in "${CFR_DIR}"/*/; do
    [ -d "$configdir" ] || continue
    DIRNAME=$(basename "$configdir")

    META_COUNT=$(ls "${configdir}"*.meta.json 2>/dev/null | wc -l)
    if [ "$META_COUNT" -eq 0 ]; then
      echo "  Skipping ${DIRNAME} (no solved flops)"
      continue
    fi

    echo "  Uploading ${DIRNAME}: ${META_COUNT} flops..."

    # Upload individual meta files
    for metafile in "${configdir}"*.meta.json; do
      [ -f "$metafile" ] || continue
      BASENAME=$(basename "$metafile")
      $S3 cp "$metafile" "${S3_BUCKET}/meta/${DIRNAME}/${BASENAME}" --quiet
    done

    # Upload individual JSONL files
    JSONL_COUNT=0
    for jsonlfile in "${configdir}"*.jsonl; do
      [ -f "$jsonlfile" ] || continue
      BASENAME=$(basename "$jsonlfile")
      $S3 cp "$jsonlfile" "${S3_BUCKET}/jsonl/${DIRNAME}/${BASENAME}" --quiet
      JSONL_COUNT=$((JSONL_COUNT + 1))
    done

    # Generate and upload _index.json (all metas merged)
    INDEX_TMP="/tmp/cfr_index_${DIRNAME}.json"
    echo "[" > "$INDEX_TMP"
    FIRST=true
    for metafile in "${configdir}"*.meta.json; do
      [ -f "$metafile" ] || continue
      if [ "$FIRST" = true ]; then FIRST=false; else echo "," >> "$INDEX_TMP"; fi
      cat "$metafile" >> "$INDEX_TMP"
    done
    echo "]" >> "$INDEX_TMP"
    $S3 cp "$INDEX_TMP" "${S3_BUCKET}/meta/${DIRNAME}/_index.json" --quiet
    rm -f "$INDEX_TMP"

    echo "  Done: ${DIRNAME} (${META_COUNT} metas, ${JSONL_COUNT} jsonl)"
    JSONL_CONFIG_COUNT=$((JSONL_CONFIG_COUNT + 1))
  done
  echo "  Uploaded ${JSONL_CONFIG_COUNT} config(s) with individual files"
  echo ""
fi

# --- Generate and upload manifest ---
echo "=== Generating manifest.json ==="
MANIFEST="${PROJECT_ROOT}/data/cfr/manifest.json"

{
  echo "{"
  echo "  \"version\": 1,"
  echo "  \"updated\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"binary\": {"

  FIRST=true
  for binfile in "${CFR_DIR}"/*.bin.gz; do
    [ -f "$binfile" ] || continue
    BASENAME=$(basename "$binfile")
    FILESIZE=$(wc -c < "$binfile" | tr -d ' ')
    if [ "$FIRST" = true ]; then FIRST=false; else echo ","; fi
    printf "    \"%s\": { \"sizeBytes\": %s }" "$BASENAME" "$FILESIZE"
  done

  echo ""
  echo "  },"
  echo "  \"raw\": {"

  FIRST=true
  for configdir in "${CFR_DIR}"/*/; do
    [ -d "$configdir" ] || continue
    DIRNAME=$(basename "$configdir")
    META_COUNT=$(ls "${configdir}"*.meta.json 2>/dev/null | wc -l)
    [ "$META_COUNT" -eq 0 ] && continue
    if [ "$FIRST" = true ]; then FIRST=false; else echo ","; fi
    printf "    \"%s\": { \"flops\": %s }" "$DIRNAME" "$META_COUNT"
  done

  echo ""
  echo "  }"
  echo "}"
} > "$MANIFEST"

$S3 cp "$MANIFEST" "${S3_BUCKET}/manifest.json"
rm -f "$MANIFEST"
echo "  Manifest uploaded"

echo ""
echo "============================================"
echo "  Upload complete!"
echo "============================================"
