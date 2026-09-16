# Current full-network half-rate continuation qualification

This is a prerequisite, not a new poker-strength experiment. Prior completed
two-seed representation pilot motivates a step-size control, not a causal claim.
Keep its original full-rate learner primary. The sole major comparator will be
full-network training at half its actual restored Adam learning rate. Preserve
the completed heads endpoints as frozen references; no third learning family.

## Fixed inputs and allowed transformation

Use the completed representation pilot's seed1_full_stage2/latest.pt SHA256
3d7914ba11c5deaf9725afbd59f4a805fd7f0bead37a2c8eddb6bffa9038b8f3 and
seed3_full_stage2/latest.pt SHA256
0a5e09c32dbdc098215fb29221a7f497a95755e2c5273060c8c01924d92d5cc0.
Their physical counters are 9,445,556 and 9,441,064 respectively; iterations
1992 and 1993. Do not restart from Standard10, the earlier8M parents, or zero.

Change ONLY the single optimizer group's actual LR by factor0.5 and append
explicit transformation provenance. Preserve every other checkpoint field,
including model tensors, all86 Adam states/moments/clocks and parameter order,
replay entries/RNG, physical/transition counters, main RNG, and opponent pool.
No optimizer reset, fabricated states, hand-counter reset or parent overwrites.
Save exclusive unstepped derived files; fixture updates must never be persisted.

## Mechanical acceptance

Bind source, completed parent evidence and checkpoint SHA256 before/after work.
Verify actual86-parameter model/Adam mapping, finite moments, counters, single
group LR and supported Adam options. Unit tests must reject unintended weight,
moment, clock, replay, RNG, counter, group and provenance changes. Round-trip each
derived checkpoint and compare its entire tree with parent except allowed edits.
Load original and derived copies into real model/Adam objects, supply identical
synthetic finite gradients, step once, and verify all86 Adam clocks advance by
one with bitwise-identical moment states. Verify effective LR ratio0.5 and
parameter-displacement half scaling within float32 rounding. Discard stepped
fixtures; these are not PPO or poker-learning results.

Source-bind the unchanged production trainer. Its optimizer.load_state_dict
restores the group LR; --preserve-resumed-optimizer-lr guards its only decay
assignment and requires inherited counters plus --no-reset-optimizer. Inspection
and fixture do not certify actual worker/RNG continuation. Later production must
still run the existing exact initial-state/trace audit and fresh managed attempt
namespace checks. Worker continuation is statistical, not bitwise resumed play.

Stop on any failure, preserve partial outputs, and record the failure before a
deliberate recovery. No auto retry or overwrite. This record consumes zero
environment, evaluation, Slumbot or final-qualification hands.

## Follow-on decision

Only a passing qualification admits a separately preregistered two-seed matched
continuation from these current full endpoints: full rate versus half rate,
first+262144 then cumulative+1048576 physical hands per arm/seed if mechanical
and preregistered safety gates permit. Keep other settings fixed. Evaluate
untouched multi-anchor and both-seat gains, realized Adam steps, KL stops and
policy KL. This is not automatic16M, paper-scale, or final Slumbot authorization.
