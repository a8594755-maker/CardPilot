# Preserved-data realization-average fidelity diagnostic

Motivation: fixed phase2average c60dfc88 finished fresh20kSlumbot at-182.1045bb/100,
with both raw and sessionCIs whollynegative. Its SLfit gate passed, while internal
responses specialized strongly. This does not identify whether teacherquality,
mixturecompression or distributioncoverage is limiting. Do not add trainingbudget
or interpret CE as strategic improvement without separating these possibilities.

## Fixed frozen inputs and no gameplay
Use only COMPLETED phase2average (review9f76cf2c...) and fresh20k (review7bfa2ac1...).
Models: originalprior CD7, response1 58ef, response2 393f, finalstudent c60d.
All fullSHA256 pinned in launcher. Models never change and optimizer is never used or updated.
Native corpus: all8192preserved supervised-validation hands, select hero=index%2
before inference, process only that hero's decisions while reconstructing the full
game. External corpus: all20000completed rawhands/8sessions and all61011hero
decisions. No outcome-based row filters or use of return/reward in diagnostics.
Hands with no hero decision stay in coverage accounting, excluded rather than
assigned artificialzero error. No new environmenthands, network or training.

## Realization reference
At each hero's first decision start teacherweights1/3. Before own decisiont,
weight teacherj proportional to its prior times the product of its probabilities
of THIShero's earlier observedactions in the samehand. Compute q=sum_j w_j*pi_j
BEFORE updating with currentaction. Opponent/chance events do not update the
latent teacherposterior. Do not use sampledteacheridentity, opponentprivatecards,
futureactions, winnings or a per-state uniform average as reference.
Maintain logweights to avoid underflow; unreachableprefix fails explicitly.

This is a derived diagnostic based on own-reach mixture equivalence in
Heinrich,Lanctot,Silver2015, section2.3 and Lemma6:
https://proceedings.mlr.press/v37/heinrich15.pdf
NFSP motivates separately learning an average by supervisedbehavior sampling:
https://arxiv.org/pdf/1603.01121
The reference uses full recordedownhistory; the student has truncatedencoded
history. No claim of exactstudentrealization/perfectrecall or Nashconvergence.

## Inference and evidence
Use qualified frozen nativev6 runtime and unchanged legalsoftmax semantics.
GPUfloat32batch inference for4models; float64probabilities/posterior calculations.
Before full inference compare all4models on first32nativehero+first32external
states using CPUscalar,CPUbatch,GPUbatch:768model-statequeries,tolerance2e-5.
Fullpreserved native sampledteacherprobabilities and externalstudentprobabilities
must match current GPUbatch outputs within1e-4; report maxdeltas. This explicit
numeric tolerance is not a claim of bitwiseCPU/GPUequivalence.
Archive observations,masks,metadata,all4probabilityarrays,posterior/mixturearrays
and per-stateTV/JS. Record exactqueries=4*N+768;0uniquehands even for replays.
Capture sourcecopies/patch, inputhashes and compare allbefore/after.
Block socketconnections during inference. No livepolicy deployment.

## Metrics and prospective diagnostic branches
Primary is hand-mean TV(q,student). Also report JS and TV of naive per-state
teacheraverage as a descriptivecontrol. Condition all metrics on hands with
hero decisions; report all physicalhandcoverage and seat/streetstrata.
Nativehand normal95%CI; externalhand normal95%CI plus8sessiont7CI. Compare
equal-session externalTVmean minus nativehandmean with conservative t7 times
combinedSE. Different behavior/cohorts mean this is descriptive distribution
evidence, not a causal experiment or counterfactualwinrate estimate.

If shiftCI lower>.05: EXTERNAL_DISTRIBUTION_FIDELITY_GAP.
Else if external sessionTV CI lower>.10: LARGE_AVERAGING_FIDELITY_GAP.
Else: NO_LARGE_FIDELITY_GAP_CONFIRMED, not proof that teachers are good or bad.
Thresholds are diagnosticengineering cutoffs, not exploitability or rewardbounds.
No epochselection,100k admission or Goalcompletion from these metrics.
Use result to choose a separately preregistered native coverage/averaging
experiment or generalteacher/selfplay improvement; never train on these external
hands or install benchmark-specific actionrules.

Independent terminal review rechecks allinput/code/output hashes, reconstructs
allpreservedobservations and handidentities, recomputes posterior by independent
renormalizedproduct arithmetic and summaryCIs, then finishes thissame record.
No reviewer modelqueries. Preserve originalattempt on failure; no silentretry.

Preparation: python -m pytest research/experiments/v6-realization-average-fidelity-20260831/test_mixture.py -q --junitxml=research/experiments/v6-realization-average-fidelity-20260831/preparation_tests.xml
Execution: python research/experiments/v6-realization-average-fidelity-20260831/run_diagnostic.py
Terminal review: python research/experiments/v6-realization-average-fidelity-20260831/review_finish.py
