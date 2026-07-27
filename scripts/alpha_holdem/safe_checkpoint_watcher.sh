#!/bin/bash
# Watches V4 training log + auto-saves "safe" checkpoint when health is good.
# Runs forever in background. Kill with taskkill if needed.

LOG=c:/Users/a8594/CardPilot/models/alpha_holdem_v4_train.log
LIVE=c:/Users/a8594/CardPilot/models/alpha_holdem_v4.pt
SAFE=c:/Users/a8594/CardPilot/models/alpha_holdem_v4_safe.pt
WATCHER_LOG=c:/Users/a8594/CardPilot/models/safe_watcher.log

# Health thresholds
MAX_VLOSS=1500
MIN_ENTROPY=0.8

# Check interval: 5 minutes
INTERVAL=300

# Rolling backup interval: every 50M hands
ROLLING_INTERVAL_HANDS=50000000
LAST_ROLLING_HANDS=0

echo "Safe checkpoint watcher started at $(date)" > "$WATCHER_LOG"
echo "Thresholds: vloss < $MAX_VLOSS, entropy > $MIN_ENTROPY" >> "$WATCHER_LOG"

while true; do
  sleep $INTERVAL

  # Read last 5 iterations to assess health
  LAST5=$(tail -5 "$LOG" 2>/dev/null)
  if [ -z "$LAST5" ]; then continue; fi

  # Average vloss over last 5
  AVG_VLOSS=$(echo "$LAST5" | grep -oP 'vloss=\K[0-9.]+' | awk '{s+=$1; n++} END {if(n>0) print s/n; else print 99999}')
  # Average entropy over last 5
  AVG_ENT=$(echo "$LAST5" | grep -oP 'ent=\K[0-9.]+' | awk '{s+=$1; n++} END {if(n>0) print s/n; else print 0}')
  # Latest hands count
  HANDS=$(tail -1 "$LOG" | grep -oP 'hands=\K[0-9,]+' | tr -d ',')
  if [ -z "$HANDS" ]; then continue; fi

  TS=$(date '+%Y-%m-%d %H:%M:%S')

  # Health check
  VLOSS_OK=$(echo "$AVG_VLOSS < $MAX_VLOSS" | bc -l 2>/dev/null)
  ENT_OK=$(echo "$AVG_ENT > $MIN_ENTROPY" | bc -l 2>/dev/null)

  if [ "$VLOSS_OK" = "1" ] && [ "$ENT_OK" = "1" ]; then
    # Healthy — copy to safe
    cp "$LIVE" "$SAFE" 2>/dev/null
    echo "[$TS] hands=$HANDS vloss=$AVG_VLOSS ent=$AVG_ENT → SAFE updated" >> "$WATCHER_LOG"

    # Rolling backup every 50M hands
    if [ "$HANDS" -gt $((LAST_ROLLING_HANDS + ROLLING_INTERVAL_HANDS)) ]; then
      ROLLING="c:/Users/a8594/CardPilot/models/alpha_holdem_v4_rolling_$((HANDS / 1000000))M.pt"
      cp "$LIVE" "$ROLLING" 2>/dev/null
      echo "[$TS]   → rolling backup: $ROLLING" >> "$WATCHER_LOG"
      LAST_ROLLING_HANDS=$HANDS
    fi
  else
    REASON=""
    if [ "$VLOSS_OK" != "1" ]; then REASON="vloss=$AVG_VLOSS"; fi
    if [ "$ENT_OK" != "1" ]; then REASON="$REASON ent=$AVG_ENT"; fi
    echo "[$TS] hands=$HANDS UNHEALTHY ($REASON) — not updating safe" >> "$WATCHER_LOG"
  fi
done
