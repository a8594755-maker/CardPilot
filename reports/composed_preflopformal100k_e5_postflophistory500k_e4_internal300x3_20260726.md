# V5 Internal Strength Probe

- Checked at: `2026-07-26T09:54:28.036578+00:00`
- Checkpoint: `models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt`
- Checkpoint iteration: `8`
- Checkpoint hands: `262,472`
- Hands per match: `300`
- Policy mode: `greedy`
- Temperature: `1.0`
- Device: `cpu`

This is an internal fixed-opponent trend probe only. It is not a Slumbot benchmark, not a promotion gate, and not an L5/L6 claim.

## Results

| candidate       | train hands | opponent     |   bb/100 |     95% CI | W/L/D      |  h/s |
| --------------- | ----------: | ------------ | -------: | ---------: | ---------- | ---: |
| latest_iter8_0M |     262,472 | aggressive   |  +140.17 | +/-1751.09 | 91/199/10  | 35.6 |
| latest_iter8_0M |     262,472 | call-station |    +2.17 |   +/-19.18 | 137/153/10 | 10.5 |
| latest_iter8_0M |     262,472 | random       | +1003.01 |  +/-782.90 | 70/229/1   | 16.2 |

## Trend Flags

- `aggressive`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `call-station`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`
- `random`: latest_is_best=`True`, strictly_increasing=`False`, positive_steps=`0/0`

## Interpretation

- Use this probe for regression detection and rough direction only.
- A self-play PPO checkpoint is not expected to improve monotonically at every iteration.
- Small hand counts have wide confidence intervals; judge trends over repeated gates, not one row.
- Slumbot claims still require the gated Slumbot benchmark and promotion CI.
