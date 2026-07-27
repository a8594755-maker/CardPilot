# V5 Slumbot Pipeline Preflight

- Checked at: `2026-07-16T19:58:22.760443+00:00`
- Overall: **PASS**
- Checkpoint: `C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_002_h11_control_greedy_quick5k_20260716_checkpoint.pt`
- Checkpoint iteration: `35051`
- Checkpoint hands: `576,021,901`
- Obs version: `v55`
- Device: `cpu`

## Checks

- PASS: `checkpoint_load` - loaded C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_002_h11_control_greedy_quick5k_20260716_checkpoint.pt
- PASS: `version` - version='v5.zero', expected 'v5.zero'
- PASS: `env_version` - env_version='v55', expected 'v55'
- PASS: `obs_version` - obs_version='v55', expected 'v55'
- PASS: `action_space_version` - action_space_version='9slot_v5', expected '9slot_v5'
- PASS: `model_state` - checkpoint contains model state_dict
- PASS: `model_load` - loaded AlphaHoldemNet params=8,152,314
- PASS: `inference_cases` - 6 representative states passed
- PASS: `ci_pipeline` - wrote synthetic CI reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_ci_summary.json
- PASS: `promotion_gate_pipeline` - metadata/artifact promotion checks passed; hand-count block expected
- PASS: `promotion_hands_block` - synthetic 10-hand preflight is correctly blocked from promotion

## Inference Cases

| action string | street | legal slots | chosen | incr |
|---|---:|---|---:|---|
|  | 0 | [0, 1, 7, 8] | 7 | b200 |
| c | 0 | [1, 6, 7, 8] | 7 | b300 |
| b300 | 0 | [0, 1, 7, 8] | 7 | b600 |
| cb300 | 0 | [0, 1, 7, 8] | 7 | b600 |
| b300c/k | 1 | [1, 2, 3, 4, 5, 6, 7, 8] | 3 | b300 |
| b300c/kb600 | 1 | [0, 1, 6, 7, 8] | 7 | b1806 |

## Artifacts

- `synthetic_hands`: `reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_hands.jsonl`
- `ci_json`: `reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_ci_summary.json`
- `promotion_json`: `reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_promotion_gate.json`
- `promotion_md`: `reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_promotion_gate.md`

## Notes

- No Slumbot API calls were made.
- The synthetic promotion gate is expected to fail promotion_hands.
- A PASS here only proves local benchmark plumbing, not model strength.
