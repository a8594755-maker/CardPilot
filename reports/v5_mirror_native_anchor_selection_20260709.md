# V5 Native Mirror Anchor Selection

- Checked at: `2026-07-09T11:47Z`
- Purpose: identify a v55-native frozen anchor for future mirrored-deal internal evals after V4-anchor OOD invalidation.
- Scope: reporting/instrument selection only. No trainer change, no eval launch, no strength claim.

## Recommended Anchor

`models\bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_iter4600_75M_quick5k_checkpoint.pt`

- SHA256: `47318CF20388F0F2CFDC63D9D76BD6C5519D39DE54AB0E24589FCB1F90FC8F63`
- Checkpoint iter/hands: `4600 / 75,479,020`
- Metadata: `version=v5.zero`, `env_version=v55`, `obs_version=v55`, `action_space_version=9slot_v5`, `fresh_from_zero_lineage=True`, `starting_stack_bb=200.0`
- Evidence context: official greedy quick5k at 75M was `-71.462 bb/100`, 95% CI `[-136.249, -6.675]`, `5,000` hands, L0. This was the best V5 official point estimate found in the current trend scan, but it is still a quick-screen and cannot prove strength.

## Fallback Anchor

`models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\milestone_archives\v5_zero_l6_f_973ca3447cd9_100M_iter6200_101M.pt`

- SHA256: `3E3B9F18C6BC8CA9B7A17DD7AD36EA76D6128CD991C58D1775B8431C39BC44CA`
- Checkpoint iter/hands: `6200 / 101,732,149`
- Metadata: `version=v5.zero`, `env_version=v55`, `obs_version=v55`, `action_space_version=9slot_v5`, `fresh_from_zero_lineage=True`, `starting_stack_bb=200.0`
- Evidence context: official greedy quick5k at 100M was `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, `5,000` hands, L0.

## Usage Rule

- Future mirror reports should include both the patched OOD validity gate and this native anchor before using mirror bb/100 as an internal progress signal.
- This anchor selection does not rehabilitate any quarantined V4-anchor mirror and does not support Slumbot, V4-strength, L5, or L6 claims.
