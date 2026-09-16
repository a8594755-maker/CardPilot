# Matched native own-reach target average pilot

Evidence: v6-realization-average-fidelity-20260831 reviewSHA
6c3db8a85270afd70a4c03924a7a4d9b9ca11d704e2b8978ebbefd76dfcd4e12
found nativeheroTV0.2253 and externalheroTV0.2317 relative to the samefull-ownhistory
three-teacher mixture. The nativegap itself is large; the shift0.0064 did not
meet prespecified0.05threshold. This identifies a fitfidelityproblem but does not
prove that betterfidelity improves reward, that teachers are strong, or that
representationloss can be removed by targetvariance reduction.

Hypothesis: replace the selectedteacher softtarget by its exactconditional
own-reach mixture expectation (RaoBlackwellizedtarget), holding native training
states, initializer, modelscope and optimizationbudget fixed. This may reduce
teacheridentitylabelvariance and improve learned-average fidelity.

## Matched immutable training inputs
Parent v6-fictitious-average-phase2-20260831.
Reuse its262144historical native traininghands/2242056decisionprefixes and EXACT
262144retainedreservoir row IDs/observations/order. ReservoirSHA
5f6be731f0a14a5d6a64f4847bb519fab31ee68ad5183c4476b8db26a07717c6.
Preserve original reservoir,optimizer,checkpoints and allrawtraces unchanged.
Replaying alreadygeneratedtraininghands adds ZEROnewtrainingenvironmenthands.

Same three equal whole-hand teachers CD7/58ef/393f. Evaluate each teacher at
everynecessarynative prefix so the mixture's ownreach can be reconstructed;
maintain separateposteriors forbothseats, reset eachhand. Weightupdates use only
thatseat's earlieractualactions; predict currenttarget before updating it.
No teacherID/future/otherseat-action evidence in posterior. Currentfullhistory
reference may remain richer than truncated studentrepresentation.
Store newtargets separately,scatter tosameoldrowIDs exactly once, validate all
rows and compare retainedobservations bitwise. No externaltrajectory is used in
targetgeneration,loss,optimizersteps or actionrules.

Reuse hash-pinned verifiedposterior implementation
2a40888852ebfddb29a71c63529543655f5c829523654e91dcc7b9515f2e506c.
Streaminghandblocks may limitmemory; every necessaryprefix still gets allthree
teacherprobabilities. Preserve newmodelquery accounting, per-block manifests and
source/dataset/targethashes. Do not silentlyrestart partialrelabeling.
Actuallearnedteacher GPUbatch probabilities use samequalifiedbackend, with
CPUscalar/CPUbatch/GPUbatch qualification and independent retainedtargetreview.

## Fixed learned-weight treatment
Initializer: a73dd73af04e990bdff9892ba2b3eeebf96ded26ba6d4f099597feb262329d38.
Exactlysame80shared/policytrainable tensors,6frozenvalue tensors,NEWAdam1e-4,
batch1024,clip1,8epochs2048steps,fit/orderseed2026102004 as originalcontrol.
This is a NEWsupervisedexperiment, not PPOresume; preserve alloldoptimizer states.
Only finalepoch08, no earlier-epochrescue or outcome-basedextension.
Historicalmatchedcontrol is existing C60:
c60dfc881ff1b97245219b226eabb5f4c00c1a3d421f71681b63097f45bfa3ea.
Do not rerun that completedcontrol. Record limitations of nonconcurrent control;
sameinputs/optimizerconfiguration do not imply bitwiseidenticalGPUexecution.

## New native validation only
Generate exactly8192NEWnative200bb validationhands with equal3whole-hand teachers,
seed2026102401, qualified256slot/1024barriercollector, independentphysical-seat
actiondraws and complete52deck traces. Newtraininghands=0; nativevalidation8192
is explicitly accounted as newevaluation/SLvalidationhands,notstrengthtesthands.
This newcohort is not used in anygradient or earlystopping.
Before relabeling, qualify three teachers plus control on64preservedstates with
CPUscalar/CPUbatch/GPUbatch:768model-statequeries. After fitting, separately
qualify the newtreatment on64storedvalidationstates in allthree modes:192queries.
These replays add0newuniquehands; recordallinferencecounts separately.
Evaluate controlC60 and treatmentepoch08 on identicalnewstates against the
full-ownhistory mixture reference, keeping bothseat posteriors separate.
Primary: perhandhero=index%2 meanTV, condition onatleastonehero decision and
reportzero-decisioncoverage. Paired hand-level control-minus-treatment95%CI.
Gate: CI lower>0 AND finaltreatment meanTV<=0.15. Other outcomes validCOMPLETED,
notfailed; no automaticextraepochs or externaltest.
Secondary all-decisionCE/JS and epoch1/4/8fitcurves are diagnostic only.
No winning,exploitability,100k or exactstudentrealization claim from thisgate.

If gatepasses, separately preregister learned-policy strategic/transfer assessment
of ONLYthisfixedendpoint. Ifnot, examinecapacity/encodedhistory/datafittingbefore
increasingresponsebudget. No trainingonSlumbotdata or benchmark-specificrules.

## Current implementation status
Initial preparation: puretwo-seat target/scatter implementation and unit tests.
No relabeling/modelqueries, data collection,fit or launcherexecution yet.
The mainpipeline andindependentreview must implement thisfixedprotocol before
RUNNING; captureexactcommands/sourcecopies/patch/artifacthashes.
Reuse qualifiedcollectorandSLinfrastructure with explicitnewalgorithm metadata,
not anewgoal. Preserve failedattempts and unknown in-flightcollection counters.

Implementation addition before any model query: streaming 1024-hand blocks retain
all three teacher probabilities, exact observations/hand identities and target
hashes. Independent review eagerly reads each block once and recomputes targets
with separately normalized two-seat probability products, not the log-posterior
training helper. Review checks all retained states, new validation trace/decks,
matched epoch permutations, 80 Adam tensors at step2048, unchanged value head,
endpoint and input hashes, grouped paired-TV arithmetic and descriptive CE/JS.
No gate, model, seed, data or optimizer budget changed. Historical control is
not rerun. The final review makes zero additional model calls/new hands.

Preparation:
python -m pytest research/experiments/v6-reach-target-average-pilot-20260831/test_reach_targets.py -q --junitxml=research/experiments/v6-reach-target-average-pilot-20260831/preparation_tests.xml
