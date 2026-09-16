# Independent observable critic qualification (running)

Implemented an isolated cloned GroupNorm encoder from the actual frozen
network_hybrid_h1.AlphaHoldemNet, not merely the deployment network.py class.
Verified the production hybrid class also uses detached critic_v2 features at
line 847. The prior method selection's representational restriction therefore
applies to the training class as well.

`python -m pytest research/experiments/v6-independent-observable-critic-qualification-20260908/test_encoder.py -q`
completed with 10 passed in 8.12 seconds. No poker hands were generated.

Covered: four street-shaped inputs with both seat feature values, exact initial
logit/value equality, source parameter object preservation, independent storage,
no RNG consumption by cloning, nonzero encoder value-gradient and update, actor
weights/logits unchanged by that value update, no actor gradient into encoder,
strict in-memory state_dict roundtrip, duplicate-attachment rejection.

Limits: inputs are synthetic, not retained poker states. The production model
forward does not yet route through the new encoder. Tests explicitly exercise
the new value route separately. No worker/PPO path or disk/optimizer/replay
roundtrip has been qualified. These tests do not authorize launching training.

Remaining in this same experiment: isolated forward integration, explicit
checkpoint/config contract, named optimizer extension preserving all existing
states and learning rates, actual parent state parity, actual inference/PPO
update, serialized replay/resume tests and a bounded real-worker smoke with
managed namespaces if zero-hand gates pass. Do not edit frozen parent sources.

## Follow-up: real forward and retained parents

The initial limitations above describe the first implementation stage and remain
historical. A hash-bound mechanical derivation now routes candidate_network.py's
actual value forward through the independent encoder, defaulting to the unchanged
route when no encoder is attached. Privileged/Q routes fail closed.

Combined encoder/forward/optimizer suite: 16 tests passed in 4.49 seconds. The
additional tests cover actual forward gradients, single-group Adam extension,
retained moments/LR, a disk state_dict + optimizer roundtrip and identical next
parameter/Adam updates. No frozen source was edited.

check_parents.py then passed for both completed fixed2M parents with exact bound
SHA256 values: 64 actual retained replay states per seed spanning all streets,
bitwise actor/value initial equality, all old optimizer moments and group options
preserved, nonzero independent encoder value gradients with no actor gradients.
Both source checkpoint hashes rechecked unchanged. Receipt real_parent_checks.json
contains state identities and parameter counts. Runtime was 4.43 seconds.

Still incomplete: trainer argument/config serialization, actual PPO update routine,
worker inference integration, full replay/counter derivation and managed real-worker
resume smoke. No production training has been launched; this record stays RUNNING.

## Follow-up: actual PPO routine

check_ppo.py invoked the unchanged production trinal_clip_ppo_update on both
retained parents using 32 complete retained hand blocks per seed (174 transition
rows total). Both passed: actor, existing value head and independent encoder
parameters changed, all weights stayed finite, and every new encoder parameter
received an Adam state with step 1. Both checkpoint SHA256 values were unchanged.
Runtime 4.44 seconds. Report: ppo_checks.json.

This is a diagnostic CPU single-epoch update, with reference KL disabled, not the
registered production recipe. No updated model was saved; no new environment
hands were executed. Do not count those 64 old hand blocks as new training hands.
The main recipe's critic_head_only_gradient is False; the existing global clipping
path includes all model parameters, including the new tower. Keeping that path is
part of this architectural control; extra value gradients can affect actor clip
scale, so improved value fitting alone cannot establish improved policy updates.

Trainer integration inspection identifies required boundaries: serialized flag
and state-key consistency, encoder attachment before extended model load, Adam
extension before extended optimizer load (or after original load on derivation),
removing the unused extra tower from the actor-only frozen reference copy, and
loading new pool snapshots with their extended state. The default trainer's strict
model/optimizer loaders do not handle these automatically. Do not launch through
the old wrapper and assume the new tower is active. Actual live-worker and full
checkpoint/replay continuation qualification remain outstanding.

## Follow-up: candidate trainer continuation boundaries

Added resume_contract.py and hash-bound prepare_trainer.py, mechanically deriving
candidate_train.py through eight replacement sites without editing the original.
First derivation clones only after original model/Adam load; extended resumes
attach/register before strict state loading. Config flag/state prefix/version
mismatches and silent critic removal are rejected. Both normal and recovery
payloads carry the version marker. Extended pool snapshots attach their tower;
the actor-only reference copy drops only its unused extra encoder.

Six additional tests passed in 3.49 seconds, including first/second resume,
inconsistent metadata rejection and pool/reference handling. The synthetic replay
sentinel test does NOT prove full real checkpoint/replay serialization. An actual
train_candidate.py --help returned exit 0 with the new flag, reusing the existing
hash-checked anchor selector and bounded checkpoint I/O. It has not started a
worker. The wrapper is developmental and still needs full source binding before
production. Inspect relocated trainer workspace-path handling and production
configuration normalization, then perform the bounded real-worker/resume smoke.

## Real-worker results and extended restart

The first seed1 worker smoke ended normally after 9007 new physical executions,
8246 transition-bearing hands and 15468 replay rows. Its final-state review passed
all source/parent/prefix hashes, finite weights, namespace separation and Adam
step accounting: 86 original and 76 added parameter states each advanced by 8.
The review initially assumed four steps, then corrected that assumption using
actual fresh-plus-replay policy_rows and completed epochs: two minibatches per
epoch, two epochs per iteration, two iterations. No training was rerun.

First-run limitation: normal saves overwrote its initial resume checkpoint. A
second exclusive attempt therefore used train_capture.py, preserving the first
payload as initial_resume.pt and checking it before any new updates. No frozen
source from the first attempt was changed. The extended restart finished exit0
with 4603 additional physical executions, 4115 transition hands and 7548 replay
rows. Independently reopening its saved initial checkpoint reproduced exact
parent model, all 162 Adam states, replay entries/RNG/cumulative accounting,
iteration/transition count, pool and assignment-origin equality. Final Adam
states advanced four steps, all weights were finite, and the new namespace was
retained throughout. See seed1_extended_restart/restart_review.json.

Total qualification executions so far: 13610 physical, 12361 transition-bearing,
23016 replay rows. Strength-evaluation hands remain zero. Seed3 real-worker
derivation, with its initial payload independently captured, remains required
before final qualification and the matched two-seed production curve. These tests
establish statistical continuation only, not bitwise worker RNG equivalence.
