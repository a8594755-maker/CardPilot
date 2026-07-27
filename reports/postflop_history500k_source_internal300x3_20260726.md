# V5 Internal Strength Probe

- Checked at: `2026-07-26T09:48:27.587306+00:00`
- Checkpoint: `models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt`
- Checkpoint iteration: `8`
- Checkpoint hands: `262,472`
- Hands per match: `300`
- Policy mode: `greedy`
- Temperature: `1.0`
- Device: `cpu`

This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.

## Results

| candidate       | train hands | opponent     |   bb/100 |     95% CI | W/L/D      | h/s |
| --------------- | ----------: | ------------ | -------: | ---------: | ---------- | --: |
| latest_iter8_0M |     262,472 | aggressive   |  +361.17 | +/-1774.96 | 95/192/13  | 9.5 |
| latest_iter8_0M |     262,472 | call-station |   +97.31 |   +/-63.52 | 134/156/10 | 3.7 |
| latest_iter8_0M |     262,472 | random       | +1207.02 |  +/-848.33 | 86/212/2   | 5.2 |

## Trend Flags

- `aggressive`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `call-station`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `random`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`

## Interpretation

- Use this probe for regression detection and rough direction only.
- A self-play PPO checkpoint is not expected to improve monotonically at every iteration.
- Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.
- Slumbot claims still require the gated Slumbot benchmark and promotion CI.
