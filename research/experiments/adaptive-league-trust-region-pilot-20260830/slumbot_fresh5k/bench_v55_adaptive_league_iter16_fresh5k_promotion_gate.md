# V5 Slumbot Promotion Gate

- Checked at: `2026-08-30T03:40:35.550892+00:00`
- Overall metadata/artifact status: **FAIL**
- Checkpoint: `research\experiments\adaptive-league-trust-region-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065934.pt`
- CI JSON: `research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k\bench_v55_adaptive_league_iter16_fresh5k_ci_summary.json`
- Run dir: `research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k`

Slumbot result:

- Hands: `5,000`
- bb/100: `-53.86`
- 95% CI lower: `-92.75`
- Milestone: `L0` - severely negative point estimate
- L5 blockers: `['hands < 100000', 'bb/100 <= 0', '95% CI lower bound <= 0']`

Preflop guardrail:

- Overall: `None`
- Clean for promotion: `False`
- Probe JSON: `research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k\v5_preflop_probe_latest.json`

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

- PASS: `checkpoint_load` - loaded research\experiments\adaptive-league-trust-region-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065934.pt
- PASS: `version` - version=v5.zero
- FAIL: `env_version` - env_version='v55preflopv2v4obs', expected 'v55'
- FAIL: `obs_version` - obs_version='v4', expected 'v55'
- FAIL: `action_space_version` - action_space_version='9slot_preflop_pot_fraction_v2', expected '9slot_v5'
- PASS: `starting_stack_bb` - starting_stack_bb=200.0
- PASS: `actual_hand_accounting` - actual_hand_accounting=True
- FAIL: `fresh_from_zero_lineage` - fresh_from_zero_lineage=False; resume='models/baseline/standard10/latest.pt'
- FAIL: `health_status` - missing health_status.json in research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k
- WARN: `preflop_guardrail` - missing v5_preflop_probe_latest.json in research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k
- WARN: `selector_replay_provided` - selector replay JSON not provided; postflop selector behavior not verified
- PASS: `ci_json` - loaded research\experiments\adaptive-league-trust-region-pilot-20260830\slumbot_fresh5k\bench_v55_adaptive_league_iter16_fresh5k_ci_summary.json
- PASS: `hand_artifacts` - 8 hand artifact files exist
- FAIL: `promotion_hands` - hands=5000 < 20000
