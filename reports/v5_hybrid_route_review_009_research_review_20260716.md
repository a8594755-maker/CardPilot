# V5 Poker Research Review

- Program state: `TIER2_FROZEN_ROUTE_PIVOT`
- Overall: `ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION`
- Causal action leak claim allowed: `False`
- Temporal self-play cycle claim allowed: `False`
- Global non-convergence claim allowed: `False`
- L5 / L6 claim allowed: `False` / `False`

## Evidence matrix

| domain | status | level |
|---|---|---|
| `loss_localization` | `AVAILABLE_DESCRIPTIVE_ONLY` | `OBSERVATIONAL_LOCALIZATION` |
| `action_regret` | `MISSING_OR_INVALID` | `NONE` |
| `crossplay_cycle` | `MISSING_OR_INVALID` | `NONE` |
| `value_calibration` | `SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM` | `OFF_POLICY_CALIBRATION` |
| `asset_compatibility` | `NO_COMPATIBLE_FULL_200BB_ASSET` | `ASSET_COMPATIBILITY` |
| `method_experiment` | `MISSING` | `NONE` |
| `opponent_panel` | `MISSING_OR_INVALID` | `NONE` |
| `official_strength` | `MISSING_OR_INVALID` | `NONE` |

## Required next evidence

- do not tune an action from raw loss; preregister a validated counterfactual or same-state control if action-specific causality is required
- do not claim self-play cycling; build a complete frozen common-deal snapshot cross-play matrix
- do not generalize from Slumbot alone; use a preregistered frozen 200bb opponent panel for broad-policy claims
- wait for the registered same-start method experiment rather than selecting a new behavior change

This review never launches a behavior change. It only determines which claims and experiment registrations the current evidence can support.
