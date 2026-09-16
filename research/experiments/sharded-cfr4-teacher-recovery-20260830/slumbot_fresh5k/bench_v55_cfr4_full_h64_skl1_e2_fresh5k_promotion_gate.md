# V5 Slumbot Promotion Gate

- Checked at: `2026-08-30T02:11:15.330754+00:00`
- Overall metadata/artifact status: **FAIL**
- Checkpoint: `research\experiments\sharded-cfr4-teacher-recovery-20260830\adapter_cfr4_full_h64_skl1_l2p01_epoch02.pt`
- CI JSON: `research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k\bench_v55_cfr4_full_h64_skl1_e2_fresh5k_ci_summary.json`
- Run dir: `research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k`

Slumbot result:

- Hands: `4,999`
- bb/100: `-9.44`
- 95% CI lower: `-51.37`
- Milestone: `L3` - near break-even
- L5 blockers: `['hands < 100000', 'bb/100 <= 0', '95% CI lower bound <= 0']`

Preflop guardrail:

- Overall: `None`
- Clean for promotion: `False`
- Probe JSON: `research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k\v5_preflop_probe_latest.json`

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

- PASS: `checkpoint_load` - loaded research\experiments\sharded-cfr4-teacher-recovery-20260830\adapter_cfr4_full_h64_skl1_l2p01_epoch02.pt
- PASS: `version` - version=v5.zero
- FAIL: `env_version` - env_version='v55preflopv2v4obs', expected 'v55'
- FAIL: `obs_version` - obs_version='v4', expected 'v55'
- FAIL: `action_space_version` - action_space_version='9slot_preflop_pot_fraction_v2', expected '9slot_v5'
- PASS: `starting_stack_bb` - starting_stack_bb=200.0
- PASS: `actual_hand_accounting` - actual_hand_accounting=True
- FAIL: `fresh_from_zero_lineage` - fresh_from_zero_lineage=False; resume='C:\\Users\\a8594\\CardPilot\\models\\sourcev4_slumbot_history500k_allstreet_imitation_fullnet_20260726\\best.pt'
- FAIL: `health_status` - missing health_status.json in research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k
- WARN: `preflop_guardrail` - missing v5_preflop_probe_latest.json in research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k
- WARN: `selector_replay_provided` - selector replay JSON not provided; postflop selector behavior not verified
- PASS: `ci_json` - loaded research\experiments\sharded-cfr4-teacher-recovery-20260830\slumbot_fresh5k\bench_v55_cfr4_full_h64_skl1_e2_fresh5k_ci_summary.json
- PASS: `hand_artifacts` - 8 hand artifact files exist
- FAIL: `promotion_hands` - hands=4999 < 20000
