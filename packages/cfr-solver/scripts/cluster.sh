#!/bin/bash
# ============================================================
# CardPilot CFR Solver — Distributed Cluster Runner
# ============================================================
#
# One script to rule them all. Run on each machine with the
# appropriate role. Config is read from cluster.env.
#
# Usage:
#   ./cluster.sh coord              Start coordinator + local workers
#   ./cluster.sh worker             Start workers only (connect to coordinator)
#   ./cluster.sh status             Check pipeline status
#   ./cluster.sh dashboard          Open dashboard in browser
#
# Quick start (3 machines):
#   1. Edit cluster.env on ALL machines (set COORDINATOR_IP)
#   2. Machine A:  ./cluster.sh coord
#   3. Machine B:  ./cluster.sh worker
#   4. Machine C:  ./cluster.sh worker
#   5. Any machine: ./cluster.sh status
#
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOLVER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SOLVER_DIR/../.." && pwd)"

# ---- Load config ----
CONFIG_FILE="$SCRIPT_DIR/cluster.env"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: cluster.env not found at $CONFIG_FILE"
  echo "Copy cluster.env.example to cluster.env and edit it."
  exit 1
fi
source "$CONFIG_FILE"

# ---- Defaults ----
COORDINATOR_IP="${COORDINATOR_IP:-192.168.1.100}"
COORDINATOR_PORT="${COORDINATOR_PORT:-3500}"
SOLVER_CONFIG="${SOLVER_CONFIG:-pipeline_srp}"
ITERATIONS="${ITERATIONS:-200000}"
NUM_WORKERS="${NUM_WORKERS:-0}"
HEAP_MB="${HEAP_MB:-0}"
RESUME="${RESUME:-true}"

SERVER_URL="http://${COORDINATOR_IP}:${COORDINATOR_PORT}"
ROLE="${1:-help}"

# ---- Colors ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ---- Helpers ----
print_banner() {
  echo ""
  echo -e "${CYAN}╔═══════════════════════════════════════════════════════╗${NC}"
  echo -e "${CYAN}║${NC}  ${BOLD}CardPilot CFR Solver — Distributed Cluster${NC}          ${CYAN}║${NC}"
  echo -e "${CYAN}╚═══════════════════════════════════════════════════════╝${NC}"
  echo ""
}

print_config() {
  echo -e "${BOLD}Configuration:${NC}"
  echo -e "  Coordinator:  ${GREEN}${COORDINATOR_IP}:${COORDINATOR_PORT}${NC}"
  echo -e "  Config:       ${GREEN}${SOLVER_CONFIG}${NC}"
  echo -e "  Iterations:   ${GREEN}${ITERATIONS}${NC}"
  echo -e "  Workers:      ${GREEN}${NUM_WORKERS:-auto}${NC}"
  echo -e "  Heap/worker:  ${GREEN}${HEAP_MB:-auto}MB${NC}"
  echo -e "  Resume:       ${GREEN}${RESUME}${NC}"
  echo ""
}

check_prerequisites() {
  local ok=true

  # Check Node.js
  if ! command -v node &>/dev/null; then
    echo -e "${RED}[FAIL]${NC} Node.js not found. Install Node.js 20+."
    ok=false
  else
    local node_ver=$(node -v | sed 's/v//' | cut -d. -f1)
    if [ "$node_ver" -lt 18 ]; then
      echo -e "${YELLOW}[WARN]${NC} Node.js $(node -v) detected. v18+ recommended."
    else
      echo -e "${GREEN}[OK]${NC} Node.js $(node -v)"
    fi
  fi

  # Check npm
  if ! command -v npm &>/dev/null; then
    echo -e "${RED}[FAIL]${NC} npm not found."
    ok=false
  else
    echo -e "${GREEN}[OK]${NC} npm $(npm -v)"
  fi

  # Check project structure
  if [ ! -f "$PROJECT_ROOT/data/preflop_charts.json" ]; then
    echo -e "${RED}[FAIL]${NC} data/preflop_charts.json not found at $PROJECT_ROOT"
    echo "       Make sure the CardPilot repo is properly cloned."
    ok=false
  else
    echo -e "${GREEN}[OK]${NC} preflop_charts.json found"
  fi

  # Check node_modules
  if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
    echo -e "${YELLOW}[WARN]${NC} node_modules not found. Running npm install..."
    (cd "$PROJECT_ROOT" && npm install)
  else
    echo -e "${GREEN}[OK]${NC} node_modules exists"
  fi

  # Check tsx
  if [ ! -f "$PROJECT_ROOT/node_modules/.bin/tsx" ] && ! command -v tsx &>/dev/null; then
    echo -e "${RED}[FAIL]${NC} tsx not found in node_modules."
    ok=false
  else
    echo -e "${GREEN}[OK]${NC} tsx available"
  fi

  echo ""

  if [ "$ok" = false ]; then
    echo -e "${RED}Prerequisites check failed. Fix the issues above and try again.${NC}"
    exit 1
  fi
}

get_local_ip() {
  # Try to get the LAN IP address
  if command -v ip &>/dev/null; then
    ip route get 1 2>/dev/null | awk '{print $7; exit}' || hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown"
  elif command -v ipconfig &>/dev/null; then
    # Windows (Git Bash / MSYS2)
    ipconfig 2>/dev/null | grep -E "IPv4.*: [0-9]" | head -1 | awk '{print $NF}' | tr -d '\r' || echo "unknown"
  else
    hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown"
  fi
}

# ---- Commands ----

run_coordinator() {
  print_banner
  echo -e "${BOLD}Role: COORDINATOR + WORKER${NC}"
  echo ""
  print_config

  echo -e "${BOLD}Checking prerequisites...${NC}"
  check_prerequisites

  local local_ip=$(get_local_ip)
  echo -e "${BOLD}This machine's IP: ${GREEN}${local_ip}${NC}"
  echo ""

  if [ "$local_ip" != "$COORDINATOR_IP" ] && [ "$COORDINATOR_IP" != "localhost" ] && [ "$COORDINATOR_IP" != "127.0.0.1" ]; then
    echo -e "${YELLOW}[WARN]${NC} COORDINATOR_IP in cluster.env is ${COORDINATOR_IP}"
    echo -e "       but this machine's IP appears to be ${local_ip}."
    echo -e "       Make sure cluster.env is correct on all machines!"
    echo ""
  fi

  # Build coordinator args
  local coord_args="coordinator --port $COORDINATOR_PORT --config $SOLVER_CONFIG"
  if [ "$ITERATIONS" -gt 0 ] 2>/dev/null; then
    coord_args="$coord_args --iterations $ITERATIONS"
  fi
  if [ "$RESUME" = "true" ]; then
    coord_args="$coord_args --resume"
  fi

  echo -e "${BOLD}Starting coordinator...${NC}"
  echo -e "  Dashboard: ${GREEN}http://${local_ip}:${COORDINATOR_PORT}${NC}"
  echo ""
  echo -e "${BOLD}Workers on other machines should run:${NC}"
  echo -e "  ${CYAN}./cluster.sh worker${NC}"
  echo ""
  echo "---"
  echo ""

  # Start coordinator (it blocks)
  cd "$SOLVER_DIR"
  node --import tsx src/cli/pipeline.ts $coord_args &
  COORD_PID=$!

  # Give coordinator a moment to start
  sleep 3

  # Start local workers too
  echo ""
  echo -e "${BOLD}Starting local workers...${NC}"
  local worker_args="worker --server http://localhost:${COORDINATOR_PORT} --id coordinator"
  if [ "$NUM_WORKERS" -gt 0 ]; then
    worker_args="$worker_args --workers $NUM_WORKERS"
  fi
  if [ "$HEAP_MB" -gt 0 ]; then
    worker_args="$worker_args --heap $HEAP_MB"
  fi

  node --import tsx src/cli/pipeline.ts $worker_args &
  WORKER_PID=$!

  # Handle Ctrl+C — stop both
  trap "echo ''; echo 'Shutting down...'; kill $WORKER_PID 2>/dev/null; kill $COORD_PID 2>/dev/null; wait; exit 0" INT TERM

  # Wait for either to exit
  wait $COORD_PID $WORKER_PID
}

run_worker() {
  print_banner
  echo -e "${BOLD}Role: WORKER${NC}"
  echo ""
  print_config

  echo -e "${BOLD}Checking prerequisites...${NC}"
  check_prerequisites

  # Build worker args
  local worker_args="worker --server ${SERVER_URL}"
  if [ "$NUM_WORKERS" -gt 0 ]; then
    worker_args="$worker_args --workers $NUM_WORKERS"
  fi
  if [ "$HEAP_MB" -gt 0 ]; then
    worker_args="$worker_args --heap $HEAP_MB"
  fi

  # Auto-detect worker ID from hostname
  local wid=$(hostname 2>/dev/null || echo "worker-$$")
  worker_args="$worker_args --id $wid"

  echo -e "${BOLD}Connecting to coordinator at ${GREEN}${SERVER_URL}${NC}..."
  echo ""

  cd "$SOLVER_DIR"
  node --import tsx src/cli/pipeline.ts $worker_args
}

run_status() {
  cd "$SOLVER_DIR"
  node --import tsx src/cli/pipeline.ts status --server "$SERVER_URL"
}

run_dashboard() {
  local url="http://${COORDINATOR_IP}:${COORDINATOR_PORT}/dashboard"
  echo -e "Dashboard URL: ${GREEN}${url}${NC}"
  echo ""

  # Try to open in browser
  if command -v xdg-open &>/dev/null; then
    xdg-open "$url"
  elif command -v open &>/dev/null; then
    open "$url"
  elif command -v start &>/dev/null; then
    start "$url"
  elif command -v cmd.exe &>/dev/null; then
    cmd.exe /c start "$url" 2>/dev/null
  else
    echo "Open this URL in your browser."
  fi
}

print_help() {
  print_banner
  echo -e "${BOLD}Usage:${NC} ./cluster.sh <command>"
  echo ""
  echo -e "${BOLD}Commands:${NC}"
  echo -e "  ${CYAN}coord${NC}       Start coordinator + local workers (run on 1 machine)"
  echo -e "  ${CYAN}worker${NC}      Start workers only (run on other machines)"
  echo -e "  ${CYAN}status${NC}      Check pipeline progress"
  echo -e "  ${CYAN}dashboard${NC}   Open web dashboard in browser"
  echo ""
  echo -e "${BOLD}Quick start (3 machines):${NC}"
  echo ""
  echo "  1. Edit cluster.env on ALL machines:"
  echo -e "     Set ${GREEN}COORDINATOR_IP${NC} to the LAN IP of Machine A"
  echo -e "     Set ${GREEN}SOLVER_CONFIG${NC} to the desired config"
  echo ""
  echo "  2. Machine A (coordinator):"
  echo -e "     ${CYAN}./cluster.sh coord${NC}"
  echo ""
  echo "  3. Machine B & C (workers):"
  echo -e "     ${CYAN}./cluster.sh worker${NC}"
  echo ""
  echo "  4. Monitor from anywhere:"
  echo -e "     ${CYAN}./cluster.sh status${NC}"
  echo -e "     ${CYAN}./cluster.sh dashboard${NC}"
  echo ""
  echo -e "${BOLD}Available configs:${NC}"
  echo "  all                  — All 9 HU configs in priority order (recommended)"
  echo "  pipeline_srp         — HU SRP 50bb, 1 size/street (fast)"
  echo "  pipeline_3bet        — HU 3-bet 50bb, 1 size/street"
  echo "  hu_btn_bb_srp_100bb  — BTN vs BB SRP 100bb, 3 sizes"
  echo "  hu_btn_bb_3bp_100bb  — BTN vs BB 3BP 100bb, 2 sizes"
  echo "  hu_btn_bb_srp_50bb   — BTN vs BB SRP 50bb, 2 sizes"
  echo "  hu_btn_bb_3bp_50bb   — BTN vs BB 3BP 50bb, 2 sizes"
  echo "  hu_co_bb_srp_100bb   — CO vs BB SRP 100bb, 2 sizes"
  echo "  hu_co_bb_3bp_100bb   — CO vs BB 3BP 100bb, 1 size"
  echo "  hu_utg_bb_srp_100bb  — UTG vs BB SRP 100bb, 1 size"
  echo ""
  echo "  Combine with commas: SOLVER_CONFIG=\"hu_btn_bb_srp_100bb,hu_btn_bb_3bp_100bb\""
  echo ""
  echo -e "${BOLD}Config file:${NC} $CONFIG_FILE"
  echo ""
}

# ---- Main ----

case "$ROLE" in
  coord|coordinator)
    run_coordinator
    ;;
  worker)
    run_worker
    ;;
  status|stat)
    run_status
    ;;
  dashboard|dash)
    run_dashboard
    ;;
  help|--help|-h|*)
    print_help
    ;;
esac
