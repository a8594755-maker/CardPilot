# V5 Internal Strength Probe

- Checked at: `2026-07-26T09:51:41.541824+00:00`
- Checkpoint: `models\sourcev4_slumbot_formal100k_preflop_imitation_head_lr3e4_kl01_mappingfix_20260726\epoch_10.pt`
- Checkpoint iteration: `8`
- Checkpoint hands: `262,472`
- Hands per match: `300`
- Policy mode: `greedy`
- Temperature: `1.0`
- Device: `cpu`

This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.

## Results

| candidate       | train hands | opponent     |  bb/100 |     95% CI | W/L/D      |  h/s |
| --------------- | ----------: | ------------ | ------: | ---------: | ---------- | ---: |
| latest_iter8_0M |     262,472 | aggressive   | -707.67 | +/-1930.85 | 104/182/14 | 21.0 |
| latest_iter8_0M |     262,472 | call-station |  +75.22 |   +/-57.94 | 133/157/10 |  7.1 |
| latest_iter8_0M |     262,472 | random       | +479.34 |  +/-900.63 | 92/204/4   |  9.7 |

## Trend Flags

- `aggressive`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `call-station`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `random`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`

## Interpretation

- Use this probe for regression detection and rough direction only.
- A self-play PPO checkpoint is not expected to improve monotonically at every iteration.
- Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.
- Slumbot claims still require the gated Slumbot benchmark and promotion CI.
