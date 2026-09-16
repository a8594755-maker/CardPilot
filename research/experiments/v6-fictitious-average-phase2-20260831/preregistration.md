# Conditional phase2 three-teacher learned average

Prepared during the original v6-fictitious-response-phase2-20260831 PPO run.
PLANNED only: no new hands, GPU work, teacher copying or collector output until
that exact parent completes2097152or more actual PPOhands,262144internal hands,
independent PASS/ADMIT_SEPARATE_AVERAGE_UPDATE and primary95%lower>0.
Freeze parent finalcheckpoint and reviewed_analysis SHA256 ONLY after terminal
review. Only the preregistered2Mfinal can become response2; no earlier checkpoint.
No current parent training or assessment outcomes are used for this plan.

## Average construction

Three immutable normal-form teachers, equal1/3weights:
1. Original warm-start prior CD7:
cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b.
2. First learned response58ef:
58ef62e875ce8ad1ecf518a1a65c8f54ba711b3bc1ea1a3ab3a00ed1e1a3540d.
3. Exact final second response (hash pending terminal parent review).

Each seat independently chooses one teacher at the beginning of each fullhand,
keeping that identity for its entire hand. Train conditional soft legal-action
behavior on visited states. This accounts for own-policy reach frequencies
through whole-episode sampling; it is neither a parameter average nor an
unweighted per-state probability average.

The previous fitted average a73dd73af04e990bdff9892ba2b3eeebf96ded26ba6d4f099597feb262329d38
initializes the STUDENT WEIGHTS ONLY. It is not a fourth teacher and does not
replace the originalprior+response1 by another recursively fitted approximation.
Keep original teacher evidence to limit accumulation of approximation error.
The original17-policy historical average still counts as ONEwarm-start prior,
not17fictitious-play best-response iterates.
Truncated observation/history prevents exact realization/perfect-recall claims.
This is approximate phased fictitious play with PPO, not complete DQN-NFSP,
exact best response, equilibrium or guaranteed generalization.

## Fresh collection and preserved evidence

Exactly262144NEWphysical training-data hands plus8192separateSLvalidationhands.
Newseeds2026102001train,2026102002validation,2026102003reservoir,2026102004fit.
Full52decks, independent per-physical-seat action draws, no external data.
GPUfloat32teacher inference, float64legalsoftmax/sampletemperature1,256slots,
1024-hand full-collection barriers. Use byte-identical qualified
temporal_average.py SHA836ad2770bd1ec725c57cf53757c26bb81ea813f72bb506e0ca71759e3c2b0db.
Uniform Algorithm-R reservoir262144decisionrows, serialized observation/targets,
rawhand/eventidentities, seen count and RNG. Do not reset/reuse prior buffers,
optimizers, rawhands, teacher weights or counters. Parent PPOhands are NOT counted
again. Supervised epochs add zero physicalenvironmenthands.

Before collection compare all3teachers on64oldstates each: scalarCPU/batchCPU/
batchGPU,576model-statequeries, tolerance2e-5 and0newuniquehands.
Audit every full rawtrace: regenerate decks/teacher IDs/action draws/legalstates/
terminalpayoffs/hashchains. Match all262144retained reservoir rows exactly.
First64collected hands additionally scalar-replayed against frozenGPUteachers;
replays add0newuniquehands. Any separate CPU rounding check must be read-only
and separately registered, not an extra collection.

## Eight fixed supervised epochs

Initialize exactly a73dd weights, NEWAdam1e-4,batch1024,gradclip1.
Train80shared/policy tensors, freeze6value tensors; do not import its80state
SLoptimizer or the newresponse's86state PPOoptimizer. Decouple initializer from
teacher0 explicitly and record/hash both separately.
Exactly8fullreservoir epochs,2048optimizersteps, only fixed epoch08 result.
Record epoch1/4/8validation CE and trainingCE diagnostically, never select an
earlier epoch or extend based on partial outcomes.

Why8epochs: priorphase1 epoch1validationCE1.17378 fell to0.96232at fixedepoch4,
whose trainingCE0.96830 showed no observed train/validation gap. Its complete
strategic test passed both preregistered primary gates, but mixture-calibration
intervals were too broad to establish equivalence. Additional supervised
optimization is therefore a prospective fit experiment, not a claim that more
epochs or exact equivalence already proved useful. Doubling SLsteps adds no
extra environmenthands beyond the fixed collection and cannot validate poker
strength by itself.

Checkpoint metadata names fictitious_average_phase2_distillation_v1 and an
explicit SL-only resume contract, with inputmanifest/dataset/initializer SHA256,
optimizer and fitRNGstates. It must not masquerade as PPOcontinuation.

## Terminal decision and failure semantics

After fullcollection and8epochs, require exactrawbudget,270336unique train/val
decks, correct3x3teacherpaircounts, allretainedrows, finite80updatedtensors,
unchanged6valuetensors, complete2048metrics/Adamsteps and intactsource hashes.
Independent reviewer recomputes hand-clustered validation source-minus-final
cross-entropy improvement and95%CI.
Lower>0 -> ADMIT_SEPARATE_AVERAGE_ASSESSMENT; otherwise
AVERAGE_UPDATE_FIT_GATE_NOT_PASSED. This is a fit gate only. Zero strength,
Slumbot orqualificationhands in this record. No automaticexternal test.
A later strategic assessment must be separately preregistered and frozen.

No automatic restart/replay. The unchangedcollector commits at1024handbarriers.
If interrupted in activecollection, up to1024additionalterminalhands may be
unserialized inRAM: report preservedrawclaims and unknownextra count, never
claim losslessresume/exactfailedtotals or regenerate missinghands automatically.
Normal completion requires the exact fullbudgets and trace audits.
Finish the same record for validpositive ornegative fits. Capture exactcommands,
SHA256/sourcecopies/patches, liveaccounting, walltime and terminalreview.

Preparation: python -m pytest research/experiments/v6-fictitious-average-phase2-20260831/test_temporal_average.py -q --junitxml=research/experiments/v6-fictitious-average-phase2-20260831/preparation_tests.xml
Conditional launch: python research/experiments/v6-fictitious-average-phase2-20260831/run_distillation.py
Terminal review: python research/experiments/v6-fictitious-average-phase2-20260831/review_finish.py
