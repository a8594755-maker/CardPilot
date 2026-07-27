# V5 Internal Strength Probe

- Checked at: `2026-07-26T09:48:26.731668+00:00`
- Checkpoint: `models\sourcev4_slumbot_history500k_postflop_imitation_adapter256_kl01_mappingfix_20260726\epoch_5.pt`
- Checkpoint iteration: `8`
- Checkpoint hands: `262,472`
- Hands per match: `300`
- Policy mode: `greedy`
- Temperature: `1.0`
- Device: `cpu`

This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.

## Results

| candidate       | train hands | opponent     |  bb/100 |     95% CI | W/L/D      | h/s |
| --------------- | ----------: | ------------ | ------: | ---------: | ---------- | --: |
| latest_iter8_0M |     262,472 | aggressive   | +361.17 | +/-1774.96 | 95/192/13  | 9.6 |
| latest_iter8_0M |     262,472 | call-station |  +20.17 |   +/-33.26 | 134/156/10 | 3.7 |
| latest_iter8_0M |     262,472 | random       | +975.00 |  +/-754.22 | 74/223/3   | 5.4 |

## Trend Flags

- `aggressive`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `call-station`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `random`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`

## Interpretation

- Use this probe for regression detection and rough direction only.
- A self-play PPO checkpoint is not expected to improve monotonically at every iteration.
- Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.
- Slumbot claims still require the gated Slumbot benchmark and promotion CI.
