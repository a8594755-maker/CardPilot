#!/usr/bin/env python3
"""
Safe checkpoint watcher for V5.5 burn-in.

Adapted from safe_watcher.py (V4 era). Polls the V5.5 train log every 5 min:
- If health is good (vloss < threshold AND entropy > threshold) -> copy live
  ckpt to models/alpha_holdem_v55_safe.pt (rollback target if cycling crash)
- Every ROLLING_INTERVAL_HANDS, also drop a tagged rolling backup
  models/alpha_holdem_v55_rolling_<NNN>M.pt for audit + restoration

Usage: python scripts/alpha_holdem/safe_watcher_v55.py
Run in parallel with the trainer.
"""

import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("models/alpha_holdem_v55_train.log")
LIVE_PATH = Path("models/alpha_holdem_v55.pt")
SAFE_PATH = Path("models/alpha_holdem_v55_safe.pt")
WATCHER_LOG = Path("models/safe_watcher_v55.log")

# Health thresholds — calibrated from Phase 2 smoke (vloss ~300-500, ent ~1.2)
# V5.5 EMA training stays much lower-vloss than V4 phase 5 did, so we
# tighten the thresholds a bit. Bump if false-negative on healthy training.
MAX_VLOSS = 1500.0   # spike at start expected; mature training should be <500
MIN_ENTROPY = 0.6    # well above 0.3 floor; if dropping below 0.6, suspicious

INTERVAL = 300                       # 5 minutes
ROLLING_INTERVAL_HANDS = 50_000_000  # tagged backup every 50M real hands

# rew100 dynamics watchdog (V5.5 EMA-specific)
# Three alert types tuned for fictitious-play transients:
#
# 1. alert_catastrophic (any iter):  abs(rew100) > REW100_CATASTROPHIC
#    Even early transient should never produce this; signals broken dynamics.
#
# 2. alert_too_slow (iter >= MIN_ITER_FOR_NORMAL_ALERT):
#    rew100 > REW100_TOO_HIGH
#    AND (window monotonically increasing  OR  recent mean > earlier mean
#         + plateau tolerance — i.e., not declining)
#    The OR-branch catches plateau-at-high which strict monotonicity misses.
#
# 3. alert_cycling (any iter): rew100 max-min range > REW100_OSCILLATION_RANGE
#    Different signature from "too_slow"; fires regardless of iter window.
#
# At alpha=0.99 we expect peak around iter 30-50 then decline. iter < 80 is
# the transient grace window. Use catastrophic only as the early safety net.
REW100_WINDOW = 10
REW100_TOO_HIGH = 6.0
REW100_CATASTROPHIC = 12.0
REW100_OSCILLATION_RANGE = 10.0
REW100_COLLAPSE_LOW = -0.45
REW100_COLLAPSE_RANGE = 0.25
MIN_ITER_FOR_NORMAL_ALERT = 80
PLATEAU_TOLERANCE = 0.3
REACCEL_THRESHOLD = 0.02             # second-half slope must exceed first-half by at least this
MIN_ENTROPY_COLLAPSE = 0.05
RECENT_COLLAPSE_WINDOW = 200
ALERT_FLAG = Path("models/v55_alert.flag")
PAUSE_FLAG = Path("models/v55_pause.flag")
PAUSE_STATES = {
    "alert_catastrophic",
    "alert_too_slow",
    "alert_collapse",
    "alert_entropy_collapse",
}


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    with open(WATCHER_LOG, "a") as f:
        f.write(line)
    print(line, end="")


def parse_metric(text: str, key: str) -> float | None:
    m = re.search(rf"{key}=([+-]?\d+\.?\d*)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def parse_hands(text: str) -> int | None:
    m = re.search(r"real_hands=([\d,]+)", text)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def parse_rew100_window(lines: list, window: int) -> list:
    """Return list of float rew100 values from last `window` iter lines."""
    out = []
    for line in lines[-window:]:
        v = parse_metric(line, "rew100")
        if v is not None:
            out.append(v)
    return out


def linreg_slope(values: list) -> float:
    """Slope of simple linear regression y = a + b*x with x = 0..N-1.
    Returns 0.0 for N<2."""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den > 0 else 0.0


def assess_rew100_dynamics(window: list) -> tuple[str, dict]:
    """Classify the rew100 trajectory.

    Returns (state_label, stats). state_label is one of:
      "no_data"             - too few iters
      "healthy_balanced"    - rew100 small, no concern
      "catching_up"         - rew100 positive but trending down (EMA closing gap)
      "alert_catastrophic"  - rew100 absolute value extreme (always fires)
      "alert_too_slow"      - rew100 high and not declining (subject to iter gate)
      "alert_cycling"       - large oscillation within window
      "alert_collapse"      - deterministic small-loss plateau
    """
    n = len(window)
    if n < 5:
        return "no_data", {"n": n}

    last = window[-1]
    slope = linreg_slope(window)
    rng = max(window) - min(window)
    mean_recent_3 = sum(window[-3:]) / 3
    mean_prior_3 = sum(window[:3]) / 3 if n >= 6 else mean_recent_3

    # Split window into halves for slope-on-slope (re-acceleration) detection
    half = n // 2
    prior_half = window[:half]
    recent_half = window[half:]
    slope_prior = linreg_slope(prior_half) if len(prior_half) >= 2 else 0.0
    slope_recent = linreg_slope(recent_half) if len(recent_half) >= 2 else 0.0
    # Re-accelerating: second-half slope notably exceeds first-half slope.
    # This is the "slope from 0.05 bouncing back to 0.08" pattern user flagged.
    re_accelerating = (slope_recent > slope_prior + REACCEL_THRESHOLD)

    # Plateau-not-declining detection
    mean_recent_half = sum(recent_half) / max(len(recent_half), 1)
    mean_prior_half = sum(prior_half) / max(len(prior_half), 1)
    not_declining = mean_recent_half >= (mean_prior_half - PLATEAU_TOLERANCE)

    deltas = [window[i + 1] - window[i] for i in range(n - 1)]
    monotonic_up = all(d > 0 for d in deltas) if deltas else False

    stats = {
        "n": n, "last": last, "slope": slope, "range": rng,
        "slope_prior": slope_prior, "slope_recent": slope_recent,
        "re_accelerating": re_accelerating,
        "mean_prior_3": mean_prior_3, "mean_recent_3": mean_recent_3,
        "mean_prior_half": mean_prior_half, "mean_recent_half": mean_recent_half,
        "monotonic_up": monotonic_up, "not_declining": not_declining,
    }

    # 1. Catastrophic — absolute value past expected transient ceiling.
    #    Always fires regardless of iter (no grace period for catastrophe).
    if abs(last) > REW100_CATASTROPHIC:
        return "alert_catastrophic", stats

    if n >= 8 and last <= REW100_COLLAPSE_LOW and rng <= REW100_COLLAPSE_RANGE:
        return "alert_collapse", stats

    # 2. Cycling — large absolute swing across the window.
    if rng >= REW100_OSCILLATION_RANGE and n >= 8:
        return "alert_cycling", stats

    # 3. Too slow — high AND re-accelerating (slope_recent > slope_prior).
    #    Per user spec: don't alert just because slope is positive; require it
    #    to be GROWING. If hero is in deceleration phase (slope_recent < slope_prior),
    #    we are approaching peak and must NOT abort.
    if last > REW100_TOO_HIGH and (re_accelerating or monotonic_up or not_declining):
        return "alert_too_slow", stats

    # 4. Catching up — positive but trending down. Also catches the
    #    deceleration-toward-peak window (slope > 0 but recent < prior).
    if last > 0.5 and (slope < -0.05 or (slope_recent < slope_prior - REACCEL_THRESHOLD)):
        return "catching_up", stats

    # 5. Otherwise — small / balanced rew100.
    return "healthy_balanced", stats


def check_health() -> tuple[bool, dict]:
    """Read recent iter lines; return (vloss/entropy healthy, stats incl. rew100 dynamics)."""
    if not LOG_PATH.exists():
        return False, {"error": "no log file yet"}

    with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    iter_lines = [l for l in lines if "real_hands=" in l and "vloss=" in l]
    if len(iter_lines) < 5:
        return False, {"error": f"only {len(iter_lines)} iter lines"}

    last5 = iter_lines[-5:]
    vloss_vals, ent_vals = [], []
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
    metric_healthy = avg_vloss < MAX_VLOSS and avg_ent > MIN_ENTROPY

    # rew100 dynamics over a longer window
    rew_window = parse_rew100_window(iter_lines, REW100_WINDOW)
    state, rew_stats = assess_rew100_dynamics(rew_window)
    rew_last = rew_stats.get("last", 0.0)

    if avg_ent <= MIN_ENTROPY_COLLAPSE:
        state = "alert_entropy_collapse"
        rew_stats["entropy"] = avg_ent

    recent_ent = []
    for line in iter_lines[-RECENT_COLLAPSE_WINDOW:]:
        e = parse_metric(line, "ent")
        if e is not None:
            recent_ent.append(e)
    recent_min_entropy = min(recent_ent) if recent_ent else avg_ent
    recent_entropy_collapse = recent_min_entropy <= MIN_ENTROPY_COLLAPSE
    if recent_entropy_collapse and not state.startswith("alert_"):
        state = "cooldown_after_collapse"
        rew_stats["recent_min_entropy"] = recent_min_entropy
        rew_stats["cooldown_window"] = RECENT_COLLAPSE_WINDOW

    # Iter gate for "too_slow": suppress during the early transient.
    # Catastrophic + cycling are NOT suppressed — they fire regardless of iter.
    iters_since_resume = len(iter_lines)
    if state == "alert_too_slow" and iters_since_resume < MIN_ITER_FOR_NORMAL_ALERT:
        state = "transient_climbing"
        rew_stats["iters_since_resume"] = iters_since_resume
        rew_stats["alert_suppressed_until_iter"] = MIN_ITER_FOR_NORMAL_ALERT

    dynamics_healthy = (
        state in ("healthy_balanced", "no_data")
        and abs(rew_last) <= REW100_TOO_HIGH
        and not recent_entropy_collapse
    )
    healthy = metric_healthy and dynamics_healthy

    return healthy, {
        "hands": hands,
        "vloss": avg_vloss,
        "entropy": avg_ent,
        "healthy": healthy,
        "rew100_state": state,
        "rew100_stats": rew_stats,
        "iters_since_resume": iters_since_resume,
    }


def maybe_alert(state: str, stats: dict, rew_stats: dict, hands: int):
    """If dynamics indicate a problem, log loudly and touch alert/pause flags."""
    if state in (
        "alert_too_slow",
        "alert_cycling",
        "alert_catastrophic",
        "alert_collapse",
        "alert_entropy_collapse",
    ):
        msg = (f"!!! ALERT [{state}] hands={hands:,} "
               f"rew_last={rew_stats.get('last', 0):.2f} "
               f"slope={rew_stats.get('slope', 0):+.3f} "
               f"range={rew_stats.get('range', 0):.2f}")
        if state == "alert_catastrophic":
            msg += f" | abs(rew100) > {REW100_CATASTROPHIC} — broken dynamics, pause immediately"
        elif state == "alert_too_slow":
            msg += " | rew100 high and not declining; pause and resume from a safe pool checkpoint"
        elif state == "alert_collapse":
            msg += " | deterministic -0.5 plateau; policy likely collapsed"
        elif state == "alert_entropy_collapse":
            msg += f" | entropy <= {MIN_ENTROPY_COLLAPSE}; policy collapsed"
        else:  # cycling
            msg += " | rew100 oscillation suggests cycling; check entropy + maybe pause"
        log(msg)
        try:
            ALERT_FLAG.write_text(
                f"{state}\nhands={hands}\nstats={rew_stats}\n",
                encoding="utf-8",
            )
        except OSError as e:
            log(f"  (failed to touch ALERT_FLAG: {e})")
        if state in PAUSE_STATES:
            try:
                PAUSE_FLAG.write_text(
                    f"{state}\nhands={hands}\nstats={rew_stats}\n",
                    encoding="utf-8",
                )
                log(f"  -> pause requested via {PAUSE_FLAG}")
            except OSError as e:
                log(f"  (failed to touch PAUSE_FLAG: {e})")
    elif state == "catching_up":
        log(f"  rew100 dynamics: catching_up (last={rew_stats['last']:+.2f}, "
            f"slope={rew_stats['slope']:+.3f}) -- EMA closing gap, healthy")
    elif state == "healthy_balanced":
        log(f"  rew100 dynamics: balanced (last={rew_stats['last']:+.2f}, "
            f"slope={rew_stats['slope']:+.3f})")
    elif state == "transient_climbing":
        log(f"  rew100 dynamics: transient_climbing (last={rew_stats['last']:+.2f}, "
            f"slope={rew_stats['slope']:+.3f}, iter={rew_stats.get('iters_since_resume',0)}/"
            f"{rew_stats.get('alert_suppressed_until_iter',0)} -- alert suppressed during early transient)")
    elif state == "cooldown_after_collapse":
        log(f"  rew100 dynamics: cooldown_after_collapse "
            f"(recent_min_entropy={rew_stats.get('recent_min_entropy', 0):.4f}, "
            f"window={rew_stats.get('cooldown_window', 0)}) -- safe update blocked")


def main():
    os.chdir(Path(__file__).parent.parent.parent)  # repo root

    log(f"V5.5 safe watcher started (vloss<{MAX_VLOSS}, ent>{MIN_ENTROPY}, "
        f"interval={INTERVAL}s, rolling every {ROLLING_INTERVAL_HANDS:,} hands)")
    log(f"rew100 watchdog: window={REW100_WINDOW}, too_high>{REW100_TOO_HIGH}, "
        f"cycling_range>{REW100_OSCILLATION_RANGE}, entropy_collapse<={MIN_ENTROPY_COLLAPSE}, "
        f"cooldown_window={RECENT_COLLAPSE_WINDOW}")
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
        rew_state = stats.get("rew100_state", "no_data")
        rew_stats = stats.get("rew100_stats", {})

        if healthy:
            try:
                if LIVE_PATH.exists():
                    shutil.copy2(LIVE_PATH, SAFE_PATH)
                    log(f"hands={hands:,} vloss={vloss:.1f} ent={ent:.3f} -> SAFE updated")

                    if hands > last_rolling_hands + ROLLING_INTERVAL_HANDS:
                        rolling = Path(f"models/alpha_holdem_v55_rolling_{hands // 1_000_000}M.pt")
                        shutil.copy2(LIVE_PATH, rolling)
                        log(f"  -> rolling backup: {rolling.name}")
                        last_rolling_hands = hands
            except Exception as e:
                log(f"Copy failed: {e}")
        else:
            log(f"hands={hands:,} vloss={vloss:.1f} ent={ent:.3f} UNHEALTHY -- skip "
                f"(thresholds: vloss<{MAX_VLOSS}, ent>{MIN_ENTROPY})")

        # Always run rew100 dynamics check (independent of save/skip decision)
        maybe_alert(rew_state, stats, rew_stats, hands)


if __name__ == "__main__":
    main()
