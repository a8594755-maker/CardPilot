# V5 Internal Strength Probe

- Checked at: `2026-07-26T09:24:07.159357+00:00`
- Checkpoint: `models\sourcev4_slumbot10k_strong_imitation_adapter256_kl01_20260726\best.pt`
- Checkpoint iteration: `8`
- Checkpoint hands: `262,472`
- Hands per match: `1000`
- Policy mode: `greedy`
- Temperature: `1.0`
- Device: `cpu`

This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.

## Results

| candidate       | train hands | opponent     |  bb/100 |    95% CI | W/L/D      |  h/s |
| --------------- | ----------: | ------------ | ------: | --------: | ---------- | ---: |
| latest_iter8_0M |     262,472 | aggressive   | +324.60 | +/-893.30 | 270/717/13 | 13.3 |
| latest_iter8_0M |     262,472 | call-station | +107.65 |  +/-37.63 | 465/500/35 |  4.9 |
| latest_iter8_0M |     262,472 | random       | -417.22 | +/-390.26 | 234/764/2  |  7.4 |

## Trend Flags

- `aggressive`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `call-station`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `random`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`

## Interpretation

- Use this probe for regression detection and rough direction only.
- A self-play PPO checkpoint is not expected to improve monotonically at every iteration.
- Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.
- Slumbot claims still require the gated Slumbot benchmark and promotion CI.
