# V5 Slumbot Promotion Gate

- Checked at: `2026-07-15T05:52:06.026883+00:00`
- Overall metadata/artifact status: **FAIL**
- Checkpoint: `C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_001_h8_treatment_greedy_quick5k_20260715_checkpoint.pt`
- CI JSON: `C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_001_h8_treatment_greedy_quick5k_20260715_preflight\slumbot_preflight_ci_summary.json`
- Run dir: `models\alpha_holdem_v5_hybrid\v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714`

Slumbot result:

- Hands: `10`
- bb/100: `+25.00`
- 95% CI lower: `-79.58`
- Milestone: `L4` - candidate champion; CI gate not yet proven
- L5 blockers: `['hands < 100000', '95% CI lower bound <= 0']`

Preflop guardrail:

- Overall: `WARN`
- Clean for promotion: `False`
- Probe JSON: `models\alpha_holdem_v5_hybrid\v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714\v5_preflop_probe_latest.json`

Selector replay guardrail:

- Overall: `WARN`
- Clean for promotion: `False`
- Replay JSON: `None`
- played max postflop raise+all-in: `unavailable`
- greedy max postflop raise+all-in: `unavailable`
- raw_probability_mass max postflop raise+all-in: `unavailable`

Decisions:

- `promotion_20k_candidate`: `False`
- `promotion_20k_strong`: `False`
- `formal_l5_claim`: `False`
- `formal_l6_claim`: `False`
- `preflop_guardrail_clean`: `False`
- `selector_replay_clean`: `False`

Checks:

- PASS: `checkpoint_load` - loaded C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_001_h8_treatment_greedy_quick5k_20260715_checkpoint.pt
- PASS: `version` - version=v5.zero
- PASS: `env_version` - env_version=v55
- PASS: `obs_version` - obs_version=v55
- PASS: `action_space_version` - action_space_version=9slot_v5
- PASS: `starting_stack_bb` - starting_stack_bb=200.0
- PASS: `actual_hand_accounting` - actual_hand_accounting=True
- PASS: `fresh_from_zero_lineage` - fresh_from_zero_lineage=True
- FAIL: `health_status` - health overall 'FAIL'
- WARN: `preflop_guardrail` - preflop probe WARN
- WARN: `selector_replay_provided` - selector replay JSON not provided; postflop selector behavior not verified
- PASS: `ci_json` - loaded C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_001_h8_treatment_greedy_quick5k_20260715_preflight\slumbot_preflight_ci_summary.json
- PASS: `hand_artifacts` - 1 hand artifact files exist
- FAIL: `promotion_hands` - hands=10 < 20000
