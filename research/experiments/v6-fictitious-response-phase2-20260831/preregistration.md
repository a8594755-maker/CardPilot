# Conditional fictitious response phase2: two-million actual hands

Prepared while the fixed phase1 average strategic assessment is still running.
This is PLANNED ONLY until that same172032hand record independently finishes
PASS/ADMIT_NEXT_RESPONSE_PHASE and both preregistered family2 primary lower
bounds exceed0. Freeze its reviewed_analysis SHA256 after terminal review.
No interim assessment outcomes were inspected or used to create this plan.
If parent fails its gate, do not launch; preserve and close this conditional plan.

## Why another response and why this budget

The first response to the old average showed fixed-checkpoint improvement
at approximately0.25M/0.5M/1M actual hands:547.14/719.65/850.01bb/100
versus its frozen training average. The final paired95% interval was
[718.9989680502032,981.0269108560468]. Two known-anchor effects regressed.
These are internal approximate-response results, not general/external strength.
Monotonic point estimates are not proof that each additional budget improves.

Conditional on an average that hedges the first response and restores targeted
anchor performance, train a new response against that UPDATED frozen average.
Increase this per-response budget to2097152NEWactual physical terminal hands,
twice the prior1048576target. Preserve the1M intermediate checkpoint to quantify
the incremental benefit of2M. No leap to2.7B without subsequent evidence.
This is approximate phased fictitious play with PPO and separate learned averaging,
not fullNFSP, exact best-response optimization, equilibrium or an exploitability bound.

## Immutable input and new-training semantics

Phase1 exact epoch04:
a73dd73af04e990bdff9892ba2b3eeebf96ded26ba6d4f099597feb262329d38.
Initialize all86policy/critic tensors from those weights and use the SAMEimmutable
checkpoint as sole opponent. Start an explicitly NEWAdam, NEWrun identity,
NEWcounters and NEWseeds. This is not a continuation of its80state SL optimizer.
Preserve its4epochs/1024optimizersteps, reservoir,262144datahands,8192validation
hands and all earlier PPOhands; never import or recount them.
No legacy-v6 rebinding, replay, teacher penalty, action rules or dynamic pool.
No evaluation/Slumbot data enter training.

Qualified GPUmulti8 v6trainer,12workers x8slots,200bb,fp32,
self_play_fraction0, fixed1opponent, assigned weight1.
Adam3e-5,2PPOepochs,KLtarget.01,minibatch1024,advclip3,
globaladvantage normalization,entropy.005/floor.05,valuecoef1,sourceKL0.
Native sampled9-action contract unchanged.
Seed20261018,workerbase2026101800. Saveeachupdate/archiveevery4.
Stopfirstcompletedupdate reaching2097152ACTUALhands. Report overshoot and
shutdowncountertail. Runtime7200s safetycap, no automatic restarts.
Qualified multi8 is fresh-start only, not a claim of lossless interruption resume.
Any failure preserves checkpoints, optimizer, counters and logs. Abnormal
output-buffer loss means durable evidence is a lower bound, not fabricated exact
physical accounting; diagnose before any continuation.

## Outcome-blind curve and fixed assessment

Freeze exactly four checkpoints before any assessment:
initial average; first archive at or above524288actualhands;
first archive at or above1048576actualhands; and completed2Mfinal.
Use actual counter metadata, never filename hands or returns.
Only final can be the next average component; no checkpoint/seed rescue.

Eight opponents: current average, previous averageCD7, previous response58ef,
and known corrected-v6anchor0..4. All are frozen before training; ONLYcurrent
average used as a training opponent. Previous policies/anchor families are known,
not novel adversaries or untouched opponent identities.
Fourtimes8cells x4096mirroredpairs x2hands =262144NEWinternalhands.
All32commands frozen before firstcell. Seed20261019 full52carddecks and
physical-seat action uniforms, CPUfloat32sampletemperature1, max6children.
Allfixedcellscomplete before outcomes or curves are inspected. No replacements.

Regenerate all4096new unique full52decks and match32cells independently.
Verify rawcomplete rows, frozen hashes/runtime/sourcepatch, all33normal exits
(one trainer+32evaluationchildren), exact commands and initial self-match0.
Independent reviewer recomputes arithmetic and counter/archive selection.

## Statistics and allocation

Mirroredpair is the variance unit, inbb/100.
Primary: final-minus-initial against currentaverage; ordinary two-sided95%CI
lower>0 -> ADMIT_SEPARATE_AVERAGE_UPDATE, otherwise RESPONSE_LEARNING_GATE_NOT_PASSED.
This allocates separate averaging ONLY, not external/100k qualification.

Report24response-minus-initial paired effects (3trainedcheckpoints x8opponents)
plus one preregistered final-minus-half againstaverage budget contrast.
For these25diagnostics report ordinary95% and Bonferroni family25 intervals,
z=NormalInvCDF(1-.05/(2*25)); combine within matching deckpair before variance.
A positive final-minus-half adjusted lower would support considering another
budget increase; crossing0 does not prove equality or absence of improvement.
Do not compare oracle returns across different training opponents as an exact
exploitability reduction. No pooling past or external hands.

All meaningful commands, hashes, walltime, counters and sessionaudit recorded
in this same experiment. Independently finish valid positive or negative results.
A subsequent average would preserve the prior and both response teachers and use
whole-hand mixtures; no average update is performed inside this record.

Exact preparation: python -m pytest research/experiments/v6-fictitious-response-phase2-20260831/test_pilot.py -q --junitxml=research/experiments/v6-fictitious-response-phase2-20260831/preparation_tests.xml
Conditional launch: python research/experiments/v6-fictitious-response-phase2-20260831/run_pilot.py
Terminal review: python research/experiments/v6-fictitious-response-phase2-20260831/review_finish.py

Parent completed and independently reviewed on2026-08-31:
SHA256 644231eb6cefb426ab7ed366dce92d743e4bb18ec9e2816f35ffd847d89930bd.
Both preregistered strategic family2 lower bounds are positive:
hedge+385.786499[205.275993,566.297005] and retention+251.739685[115.439787,388.039583].
The student still loses to response1(-237.807983bb/100), so this admission is
for response learning only, not equilibrium or external qualification.
All seven mixture-calibration family7 intervals include0; this is not equivalence.
No changes to prepared training configuration, budget, seeds or evaluation gates.
