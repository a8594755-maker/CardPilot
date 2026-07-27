# V5 Slumbot Selector Replay

- Checkpoint: `models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\latest.pt`
- Iteration: `90`
- Training hands: `2957599`
- Env/obs/action: `v55preflopv2v4obs` / `v4` / `9slot_preflop_pot_fraction_v2`
- Dump files: `4`
- Hero decisions replayed: `1000`

## Policy Mix

| Policy   | Overall mix                                            | Exact match vs dump | Class match vs dump |
| -------- | ------------------------------------------------------ | ------------------: | ------------------: |
| `greedy` | fold 14.6%, call/check 55.8%, raise 29.6%, all-in 0.0% |               98.7% |               98.8% |

## Policy Probability Mass

| Distribution | Overall mass                                           |
| ------------ | ------------------------------------------------------ |
| `raw`        | fold 15.3%, call/check 51.0%, raise 33.6%, all-in 0.1% |
| `guarded`    | fold 15.3%, call/check 51.1%, raise 33.6%, all-in 0.0% |

## Preflop Facing Bet

| Policy   | Count |  Fold |  Call | Raise | All-in |
| -------- | ----: | ----: | ----: | ----: | -----: |
| `greedy` |   178 | 20.8% | 69.1% | 10.1% |   0.0% |

## Probability Mass By Street

| Distribution | Street    |  Fold |  Call | Raise | All-in |
| ------------ | --------- | ----: | ----: | ----: | -----: |
| `raw`        | `flop`    | 13.9% | 60.6% | 25.6% |   0.0% |
| `raw`        | `preflop` | 18.2% | 30.1% | 51.6% |   0.1% |
| `raw`        | `river`   | 14.4% | 64.0% | 21.3% |   0.3% |
| `raw`        | `turn`    | 13.3% | 62.4% | 24.2% |   0.1% |
| `guarded`    | `flop`    | 13.9% | 60.6% | 25.6% |   0.0% |
| `guarded`    | `preflop` | 18.2% | 30.1% | 51.7% |   0.0% |
| `guarded`    | `river`   | 14.4% | 64.2% | 21.3% |   0.1% |
| `guarded`    | `turn`    | 13.3% | 62.5% | 24.2% |   0.0% |

## Changes Vs Greedy
