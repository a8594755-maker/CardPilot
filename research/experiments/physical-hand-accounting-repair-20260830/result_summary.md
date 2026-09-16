# Physical environment-hand accounting repair

## Outcome

Decision: `PHYSICAL_HAND_ACCOUNTING_REPAIRED_AND_RESUME_VERIFIED`.

The legacy trainer counter omitted no-decision hero hands and unconsumed completed worker tails. Independent shared terminal counters now measure physical environment work while preserving legacy total_hands, optimizer, and assignment evidence. New physical budgets use an opt-in PPO-boundary stopping target. See `research/HAND_ACCOUNTING.md` for the contract and historical limitations.

## Implementation

- Both single and multi-env workers count every completed terminal hand independently of transition buffers, and count no-trainable-decision hands separately.
- Checkpoints, manifests, and metrics persist a versioned physical-accounting prefix, per-session/per-worker counters, and the unchanged legacy marker count.
- Resume adds new physical work exactly once to the preserved prefix. Unknown legacy prefixes remain explicitly incomplete; physical-target continuation is rejected rather than guessed.
- `--total-environment-hands` overrides the legacy target, uses physical progress for learning-rate scheduling, and stops only at PPO boundaries. Already-completed physical endpoints fail before worker startup.
- Fixed-pool audit v2 separates legacy targets/counters from physical values. Old records without the new schema no longer receive a newly generated false exact-physical label.
- Paired-session audit v2 reports emitted-pair physical lower bounds and explicitly states that historical worker tails are unknown.

## Verification

- 37 relevant tests passed, including six new accounting tests. All changed Python modules compiled.
- Single smoke: target 512 physical hands; ended at 771 physical, 574 legacy markers, 137 no-decision hands, and 60 completed unconsumed decision-bearing tails. Audit PASS.
- Same-checkpoint resume: 771 + 429 = 1,200 physical hands; legacy 574 to 851; no-decision 137 + 79 = 216; optimizer steps 10 to 14. Original iter1/2 archive hashes unchanged, assignment chain contiguous, pending=null. Audit PASS.
- Resume deliberately moved the fixed-deal start index to 100000 to avoid repeating prior smoke deals. Skipped indices were not counted. This verifies accounting/optimizer continuation, not bitwise uninterrupted rollout equivalence.
- Multi-env smoke (2 workers x 4 envs): 624 physical, 568 legacy, 33 no-decision hands. Audit PASS.
- A legacy frozen checkpoint with no physical prefix was rejected at the intended physical-prefix guard before worker startup or checkpoint creation.
- A measured checkpoint already beyond the requested endpoint was rejected at the completed-target guard, with its original SHA256 unchanged.
- Two preliminary probe commands were rejected by existing parser guards (missing explicit no-reset-optimizer and required value coefficient); no worker or training artifact was created by them. Corrected probes reached the intended guards.
- Total new physical environment hands: 1,824. Evaluation hands: 0. Slumbot hands: 0.

## Historical correction

The immutable paired-actor production logs contain 158,350 balanced emitted pairs, proving at least 316,700 physical hands despite legacy marker counter 263,479. The two completed smokes each emitted 275 pairs (550 physical hands). That experiment's new-training accounting is now explicitly the physical lower bound 317,800, with legacy total 264,545 retained separately. Unsaved tails and failed pre-update smoke work are not fabricated. Raw checkpoints, training logs, manifests, and frozen evaluation outcomes were not changed; the old v1 audit remains preserved with a superseding v2 lower-bound artifact.

Earlier marker-budget comparisons remain comparisons at their historical update/marker budget, not exactly matched physical environment cost. Their policy outcomes are unchanged, but they do not justify a precise paper-scale environment-hand claim.

## Next step

Use the explicit physical budget and both accounting axes for the next training experiment. The recent paired-return and sampled-policy diagnostics did not show robust general gains, so do not scale those treatments unchanged. Choose a new learned-policy optimization/representation experiment from the evidence, with an immutable pre-run code snapshot and staged physical-hand gates.
