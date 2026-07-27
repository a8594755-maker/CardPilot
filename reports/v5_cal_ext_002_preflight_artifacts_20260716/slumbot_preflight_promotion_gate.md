# V5 Slumbot Promotion Gate

- Checked at: `2026-07-16T19:58:22.158282+00:00`
- Overall metadata/artifact status: **FAIL**
- Checkpoint: `C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_002_h11_control_greedy_quick5k_20260716_checkpoint.pt`
- CI JSON: `reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_ci_summary.json`
- Run dir: `C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715`

Slumbot result:

- Hands: `10`
- bb/100: `+25.00`
- 95% CI lower: `-79.58`
- Milestone: `L4` - candidate champion; CI gate not yet proven
- L5 blockers: `['hands < 100000', '95% CI lower bound <= 0']`

Preflop guardrail:

- Overall: `None`
- Clean for promotion: `False`
- Probe JSON: `C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\v5_preflop_probe_latest.json`

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

- PASS: `checkpoint_load` - loaded C:\Users\a8594\CardPilot\models\bench_v55_cal_ext_002_h11_control_greedy_quick5k_20260716_checkpoint.pt
- PASS: `version` - version=v5.zero
- PASS: `env_version` - env_version=v55
- PASS: `obs_version` - obs_version=v55
- PASS: `action_space_version` - action_space_version=9slot_v5
- PASS: `starting_stack_bb` - starting_stack_bb=200.0
- PASS: `actual_hand_accounting` - actual_hand_accounting=True
- PASS: `fresh_from_zero_lineage` - fresh_from_zero_lineage=True
- PASS: `terminal_endpoint_health` - terminal endpoint/protocol identity PASS
- WARN: `preflop_guardrail` - missing v5_preflop_probe_latest.json in C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715
- WARN: `selector_replay_provided` - selector replay JSON not provided; postflop selector behavior not verified
- PASS: `ci_json` - loaded reports\v5_cal_ext_002_preflight_artifacts_20260716\slumbot_preflight_ci_summary.json
- PASS: `hand_artifacts` - 1 hand artifact files exist
- FAIL: `promotion_hands` - hands=10 < 20000
