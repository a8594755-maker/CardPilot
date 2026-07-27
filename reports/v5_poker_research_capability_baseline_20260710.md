# V5 Poker Research Review

- Program state: `ACTIVE_REGISTERED_EXPERIMENT`
- Overall: `CONTINUE_REGISTERED_PROGRAM_NO_NEW_BEHAVIOR_DECISION`
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
| `value_calibration` | `{'authorization_condition': 'only after EXP005-C FAIL/INCONCLUSIVE or non-strong promotion enters route-pivot review, and only if W1 is the single selected route', 'decision': 'SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM', 'exp_w1_registration_authorized_now': False, 'global_red_flags': ['explained_variance_below_-0.05', 'rmse_over_target_std_above_1.05'], 'note': 'Reporting-only diagnostic; no automatic trainer change and no strength inference.', 'route_pivot_exp_w1_eligible': True, 'supporting_strata_count': 9}` | `OFF_POLICY_CALIBRATION` |
| `asset_compatibility` | `{'decision': 'NO_COMPATIBLE_FULL_200BB_ASSET', 'route_pivot_exp_w2_eligible': False, 'exp_w2_registration_authorized_now': False, 'note': 'An adapter or conversion project would be a new experiment, not evidence that a compatible asset already exists.'}` | `ASSET_COMPATIBILITY` |
| `method_experiment` | `MISSING` | `NONE` |
| `opponent_panel` | `MISSING_OR_INVALID` | `NONE` |
| `official_strength` | `EXTERNAL_NONFORMAL` | `STAGED_EXTERNAL` |

## Required next evidence

- do not tune an action from raw loss; preregister a validated counterfactual or same-state control if action-specific causality is required
- do not claim self-play cycling; build a complete frozen common-deal snapshot cross-play matrix
- do not generalize from Slumbot alone; use a preregistered frozen 200bb opponent panel for broad-policy claims
- wait for the registered same-start method experiment rather than selecting a new behavior change

This review never launches a behavior change. It only determines which claims and experiment registrations the current evidence can support.
