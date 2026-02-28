#!/bin/bash
# ============================================================
# CardPilot CFR Solver — Collect Results from Worker Machines
# ============================================================
#
# After a distributed solve, each machine has its own output files.
# This script uses scp/rsync to collect all results to this machine.
#
# Usage:
#   ./collect-results.sh
#
# Prerequisites:
#   - SSH access to worker machines (key-based auth recommended)
#   - Edit the WORKERS array below with your machine addresses
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load config
source "$SCRIPT_DIR/cluster.env" 2>/dev/null || true
SOLVER_CONFIG="${SOLVER_CONFIG:-pipeline_srp}"

# ---- Configure worker machines ----
# Format: "user@host:project_root"
# Edit these to match your setup:
WORKERS=(
  "user@192.168.1.101:/path/to/CardPilot"
  "user@192.168.1.102:/path/to/CardPilot"
)

# ---- Derive output dirs from config ----
get_output_dir() {
  case "$1" in
    pipeline_srp)        echo "pipeline_hu_srp_50bb" ;;
    pipeline_3bet)       echo "pipeline_hu_3bet_50bb" ;;
    standard_50bb)       echo "standard_hu_srp_50bb" ;;
    standard_100bb)      echo "standard_hu_srp_100bb" ;;
    v1_50bb)             echo "v2_hu_srp_50bb" ;;
    *)                   echo "$1" ;;
  esac
}

# All HU pipeline output dirs (when config=all)
ALL_HU_CONFIGS=(
  hu_btn_bb_srp_100bb
  hu_btn_bb_3bp_100bb
  hu_btn_bb_srp_50bb
  hu_btn_bb_3bp_50bb
  pipeline_hu_srp_50bb
  pipeline_hu_3bet_50bb
  hu_co_bb_srp_100bb
  hu_co_bb_3bp_100bb
  hu_utg_bb_srp_100bb
)

# Determine which output dirs to collect
if [ "$SOLVER_CONFIG" = "all" ]; then
  OUTPUT_SUBDIRS=("${ALL_HU_CONFIGS[@]}")
elif echo "$SOLVER_CONFIG" | grep -q ','; then
  # Comma-separated list
  IFS=',' read -ra CONFIGS <<< "$SOLVER_CONFIG"
  OUTPUT_SUBDIRS=()
  for cfg in "${CONFIGS[@]}"; do
    cfg=$(echo "$cfg" | xargs) # trim whitespace
    OUTPUT_SUBDIRS+=("$(get_output_dir "$cfg")")
  done
else
  OUTPUT_SUBDIRS=("$(get_output_dir "$SOLVER_CONFIG")")
fi

echo "=== Collecting Results ==="
echo "Config:      $SOLVER_CONFIG"
echo "Output dirs: ${#OUTPUT_SUBDIRS[@]}"
for d in "${OUTPUT_SUBDIRS[@]}"; do
  echo "  - $d"
done
echo ""

TOTAL_NEW=0

for OUTPUT_SUBDIR in "${OUTPUT_SUBDIRS[@]}"; do
  LOCAL_DIR="$PROJECT_ROOT/data/cfr/$OUTPUT_SUBDIR"
  mkdir -p "$LOCAL_DIR"

  # Count local files before
  LOCAL_BEFORE=$(ls "$LOCAL_DIR"/*.meta.json 2>/dev/null | wc -l || echo 0)

  echo "--- Config: $OUTPUT_SUBDIR (local: $LOCAL_BEFORE flops) ---"

  for WORKER in "${WORKERS[@]}"; do
    # Parse "user@host:path"
    HOSTPART="${WORKER%%:*}"
    REMOTE_ROOT="${WORKER#*:}"
    REMOTE_DIR="$REMOTE_ROOT/data/cfr/$OUTPUT_SUBDIR/"

    echo "  Syncing from $HOSTPART..."

    if command -v rsync &>/dev/null; then
      rsync -avz --progress \
        --include="*.jsonl" --include="*.meta.json" --include="completed.jsonl" \
        --exclude="*" \
        "$HOSTPART:$REMOTE_DIR" "$LOCAL_DIR/" 2>/dev/null || {
          scp "$HOSTPART:${REMOTE_DIR}*.jsonl" "$LOCAL_DIR/" 2>/dev/null || true
          scp "$HOSTPART:${REMOTE_DIR}*.meta.json" "$LOCAL_DIR/" 2>/dev/null || true
        }
    else
      scp "$HOSTPART:${REMOTE_DIR}*.jsonl" "$LOCAL_DIR/" 2>/dev/null || true
      scp "$HOSTPART:${REMOTE_DIR}*.meta.json" "$LOCAL_DIR/" 2>/dev/null || true
    fi
  done

  # Count local files after
  LOCAL_AFTER=$(ls "$LOCAL_DIR"/*.meta.json 2>/dev/null | wc -l || echo 0)
  NEW_FILES=$((LOCAL_AFTER - LOCAL_BEFORE))
  TOTAL_NEW=$((TOTAL_NEW + NEW_FILES))
  echo "  Result: $LOCAL_AFTER flops (+$NEW_FILES new)"
  echo ""
done

echo "=== Collection Complete ==="
echo "Total new flops collected: $TOTAL_NEW"
echo ""

# Create archive per config
for OUTPUT_SUBDIR in "${OUTPUT_SUBDIRS[@]}"; do
  LOCAL_DIR="$PROJECT_ROOT/data/cfr/$OUTPUT_SUBDIR"
  FILE_COUNT=$(ls "$LOCAL_DIR"/*.meta.json 2>/dev/null | wc -l || echo 0)
  if [ "$FILE_COUNT" -gt 0 ]; then
    ARCHIVE="$PROJECT_ROOT/data/cfr/${OUTPUT_SUBDIR}.tar.gz"
    echo "Creating archive: $ARCHIVE ($FILE_COUNT flops)"
    (cd "$LOCAL_DIR" && tar -czf "$ARCHIVE" *.jsonl *.meta.json 2>/dev/null) || true
    if [ -f "$ARCHIVE" ]; then
      SIZE=$(du -h "$ARCHIVE" | awk '{print $1}')
      echo "  Archive: $ARCHIVE ($SIZE)"
    fi
  fi
done
