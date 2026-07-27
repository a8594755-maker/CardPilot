#!/usr/bin/env python3
"""
Safe checkpoint watcher.

Reads V4 training log every 5 min. If health metrics are good, copies the
live checkpoint to a "safe" file. Also creates rolling backups every 50M hands.

Run with: python scripts/alpha_holdem/safe_watcher.py
"""

import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("models/alpha_holdem_v4_train.log")
LIVE_PATH = Path("models/alpha_holdem_v4.pt")
SAFE_PATH = Path("models/alpha_holdem_v4_safe.pt")
WATCHER_LOG = Path("models/safe_watcher.log")

# Health thresholds
MAX_VLOSS = 1500.0
MIN_ENTROPY = 0.8

# Check interval
INTERVAL = 300  # 5 minutes

# Rolling backup interval
ROLLING_INTERVAL_HANDS = 50_000_000


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(WATCHER_LOG, "a") as f:
        f.write(line)
    print(line, end="")


def parse_metric(text: str, key: str) -> float | None:
    """Extract `key=NNN.NNN` from training log line."""
    m = re.search(rf"{key}=([+-]?\d+\.?\d*)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_hands(text: str) -> int | None:
    m = re.search(r"hands=([\d,]+)", text)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def check_health() -> tuple[bool, dict]:
    """Read last 5 iterations, return (healthy, stats)."""
    if not LOG_PATH.exists():
        return False, {"error": "no log file"}

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    # Last 5 iteration lines
    iter_lines = [l for l in lines if "hands=" in l and "vloss=" in l]
    if len(iter_lines) < 5:
        return False, {"error": f"only {len(iter_lines)} iter lines"}

    last5 = iter_lines[-5:]

    vloss_vals = []
    ent_vals = []
    for line in last5:
        v = parse_metric(line, "vloss")
        e = parse_metric(line, "ent")
        if v is not None:
            vloss_vals.append(v)
        if e is not None:
            ent_vals.append(e)

    if not vloss_vals or not ent_vals:
        return False, {"error": "couldn't parse metrics"}

    avg_vloss = sum(vloss_vals) / len(vloss_vals)
    avg_ent = sum(ent_vals) / len(ent_vals)
    hands = parse_hands(last5[-1]) or 0

    healthy = avg_vloss < MAX_VLOSS and avg_ent > MIN_ENTROPY

    return healthy, {
        "hands": hands,
        "vloss": avg_vloss,
        "entropy": avg_ent,
        "healthy": healthy,
    }


def main():
    os.chdir(Path(__file__).parent.parent.parent)  # project root

    log(f"Safe watcher started (vloss<{MAX_VLOSS}, ent>{MIN_ENTROPY})")
    last_rolling_hands = 0

    while True:
        time.sleep(INTERVAL)

        try:
            healthy, stats = check_health()
        except Exception as e:
            log(f"ERROR: {e}")
            continue

        if "error" in stats:
            log(f"Skip: {stats['error']}")
            continue

        hands = stats["hands"]
        vloss = stats["vloss"]
        ent = stats["entropy"]

        if healthy:
            try:
                if LIVE_PATH.exists():
                    shutil.copy2(LIVE_PATH, SAFE_PATH)
                    log(f"hands={hands:,} vloss={vloss:.1f} ent={ent:.3f} → SAFE updated")

                    # Rolling backup
                    if hands > last_rolling_hands + ROLLING_INTERVAL_HANDS:
                        rolling = Path(f"models/alpha_holdem_v4_rolling_{hands // 1_000_000}M.pt")
                        shutil.copy2(LIVE_PATH, rolling)
                        log(f"  → rolling: {rolling.name}")
                        last_rolling_hands = hands
            except Exception as e:
                log(f"Copy failed: {e}")
        else:
            log(f"hands={hands:,} vloss={vloss:.1f} ent={ent:.3f} UNHEALTHY — skip")


if __name__ == "__main__":
    main()
