#!/usr/bin/env bash
# Phase 3 watcher: silent-poll milestones + alerts. Only emits on real events.
# Combined monitor (replaces separate health-watcher).
#
# Events emitted:
#   MILESTONE_HIT       — when +50M / +100M / +200M / +500M reached
#   BENCH_FIRED         — bench launched for milestone
#   STDERR_ERROR        — trainer Python error
#   ALERT_OR_PAUSE      — safe_watcher flagged a problem
#   STALLED             — trainer hung (no new iter in 18min)
#   HEARTBEAT           — every 2h, prints current progress

TRAIN_LOG="C:/Users/a8594/CardPilot/models/alpha_holdem_v55_train.log"
STDERR_LOG="C:/Users/a8594/CardPilot/models/v55_phase3_stderr.log"
ALERT_FLAG="C:/Users/a8594/CardPilot/models/v55_alert.flag"
PAUSE_FLAG="C:/Users/a8594/CardPilot/models/v55_pause.flag"
START_HANDS=999222193
MILESTONES=(50 100 200 500)
FIRED=()

last_iter=0
stale_count=0
heartbeat_counter=0   # emit every 24 checks * 5min = 2h

already_fired() {
    local m="$1"
    for f in "${FIRED[@]}"; do [ "$f" = "$m" ] && return 0; done
    return 1
}

while true; do
    sleep 300   # 5 min between checks
    heartbeat_counter=$((heartbeat_counter + 1))

    # 1. Stderr error?
    if [ -s "$STDERR_LOG" ]; then
        if grep -qE "Traceback|Error|Killed|OutOfMemory|RuntimeError|MemoryError" "$STDERR_LOG" 2>/dev/null; then
            echo "STDERR_ERROR at $(date +%H:%M:%S)"
            tail -20 "$STDERR_LOG"
            exit 1
        fi
    fi

    # 2. Safe-watcher alert / pause?
    if [ -f "$ALERT_FLAG" ] || [ -f "$PAUSE_FLAG" ]; then
        echo "ALERT_OR_PAUSE at $(date +%H:%M:%S)"
        [ -f "$ALERT_FLAG" ] && cat "$ALERT_FLAG"
        [ -f "$PAUSE_FLAG" ] && echo "(pause flag exists)"
        echo "--- last 5 iters ---"
        tail -5 "$TRAIN_LOG" 2>/dev/null
        exit 3
    fi

    # Read latest log line
    [ ! -s "$TRAIN_LOG" ] && continue
    LATEST_LINE=$(tail -1 "$TRAIN_LOG")
    LATEST_HANDS=$(echo "$LATEST_LINE" | grep -oE 'real_hands=[0-9,]+' | head -1 | tr -d 'real_hands=,')
    LATEST_ITER=$(echo "$LATEST_LINE" | grep -oE '^\[[ 0-9]+\]' | tr -d '[] ')
    [ -z "$LATEST_HANDS" ] && continue
    [ -z "$LATEST_ITER" ] && LATEST_ITER=0
    DELTA_M=$(( (LATEST_HANDS - START_HANDS) / 1000000 ))

    # 3. Stall detection (no iter change in 3 cycles = 15min)
    if [ "$LATEST_ITER" -eq "$last_iter" ] && [ "$LATEST_ITER" -gt 0 ]; then
        stale_count=$((stale_count + 1))
        if [ "$stale_count" -ge 3 ]; then
            echo "STALLED iter=$LATEST_ITER for 15min at $(date +%H:%M:%S)"
            tail -5 "$TRAIN_LOG"
            exit 2
        fi
    else
        stale_count=0
        last_iter=$LATEST_ITER
    fi

    # 4. Milestones
    for m in "${MILESTONES[@]}"; do
        if [ "$DELTA_M" -ge "$m" ] && ! already_fired "$m"; then
            TAG="phase3_${m}M"
            FROZEN="models/alpha_holdem_v55_iter_${TAG}.pt"
            LIVE="C:/Users/a8594/CardPilot/models/alpha_holdem_v55.pt"

            echo "MILESTONE_HIT +${m}M hands=$LATEST_HANDS iter=$LATEST_ITER at $(date +%H:%M:%S)"

            if [ -f "$LIVE" ]; then
                cp -p "$LIVE" "C:/Users/a8594/CardPilot/$FROZEN"
                # Launch bench (detached)
                (
                    cd /c/Users/a8594/CardPilot
                    powershell.exe -NoProfile -ExecutionPolicy Bypass \
                      -File scripts/alpha_holdem/bench_v55_slumbot.ps1 \
                      -ModelPath "$FROZEN" -Tag "$TAG" \
                      > "models/bench_v55_${TAG}_orchestrator.log" 2>&1 &
                ) &
                echo "BENCH_FIRED tag=$TAG (results in models/bench_v55_${TAG}_summary.txt ~50min)"
            else
                echo "  WARNING: live ckpt missing; skip bench for +${m}M"
            fi
            FIRED+=("$m")
        fi
    done

    # 5. Heartbeat every ~2h (24 checks * 5min)
    if [ "$heartbeat_counter" -ge 24 ]; then
        echo "HEARTBEAT iter=$LATEST_ITER delta=${DELTA_M}M $(date +%H:%M:%S) | $LATEST_LINE"
        heartbeat_counter=0
    fi

    # 6. Stop if all milestones done
    if [ "${#FIRED[@]}" -eq "${#MILESTONES[@]}" ]; then
        echo "ALL_MILESTONES_DONE at $(date +%H:%M:%S)"
        exit 0
    fi
done
