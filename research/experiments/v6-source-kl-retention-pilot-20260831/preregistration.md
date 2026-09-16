# Corrected-v6 source-KL retention intervention

Registered before this experiment's tests, training and evaluation. Parent
v6-full-network-learning-curve-20260831 completed265430physical training hands and
81920internal evaluation hands with valid evidence, but failed its final breadth
gate. Its final-minus-source estimates were positive on all5anchors; only the3
training anchors had positive Bonferroni lower bounds. The two held-out intervals
were wide, so failure is not proof of no improvement. A post-hoc common-deal
late-minus-early contrast found training-anchor average+192.36 and heldout
average-185.85bb/100. This motivates a retention intervention,not promotion of a
selected midpoint or extension/retesting for admission of the old final.

## One changed learning mechanism

Start the ORIGINAL Standard10 weights
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428,
with explicit v6 binding, NEW Adam/counters/run identity. No old optimizer,
replay, Slumbot hands, pool outcomes or old learned final initialize training.
The ONLY training hyperparameter change from the parent is source-policy-KL
coefficient0.01 to0.1. Hypothesis: stronger source regularization retains broader
learned strength at the same physical budget instead of mainly improving against
the training pool. The intermediate coefficient is not assumed effective.

Reuse the parent's exact training seeds20260918/workerbase2026091800 and regimen:
12single-env workers,cuda,262144actual completed hands at first PPO boundary,
4096legacy collection markers,1024minibatch,LR3e-5,2epochs,targetKL.01,advclip3,
entropy.005/floor.05,GN,critic_v2,valuecoef1,stackdiv200,separatepreflophead,
all86tensors,25%self-play,3fixed adaptive league anchors,per-group8,EMA.9,
temperature2/minprob.05. Save everyupdate/archiveevery4,operational cap6000seconds.
Same training seeds are an intentional matched-seed control; asynchronous
trajectories and adaptive assignments need not stay identical. Count new physical
executions separately; do not claim unique training deals or multi-seed causality.
No restart/reset/overwrite of the parent. Report target overshoot explicitly.

Exact first command:
python research/experiments/v6-source-kl-retention-pilot-20260831/run_pilot.py

The command is derived from the parent's terminal execution.json SHA
47e842579af7d536b09571db45e8bd02620d52afe614d0bdbdca13ee2640b41c,
changing only coefficient,run-id and output/frozen-copy paths. Tests verify this.
Training anchors are byte-identical copies of parent anchor0..2. Parent
anchor3..4 remain excluded from the training pool/reference. These are held out
from THIS run,not wholly unseen policy families. Archive checkpoints are for
evidence/health only; the sole new candidate is the final physical-budget output.

## New fixed evaluation,not old-checkpoint rescue

After training, freeze source, new treatment final and the parent's final
0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606
as weak_control. The old control is a comparator only,never eligible for admission.
Evaluate all3candidates against all5unchanged v6 anchors with8192mirrored pairs
per cell and NEW seed20260921:245760physical internal evaluation hands. The larger
fixed sample addresses the wide held-out intervals when testing a NEW intervention;
it does not extend the parent's gate or pool its old outcomes.

Same strict sampled-both,temp1,CPUfloat32forward/float64legalsoftmax,physical-seat
and decision-keyed RNG. Maximum6CPU processes with1torch thread each,below-normal
priority; no concurrent GPU trainer. Host preflight found24physical/32logical cores
and98GiB available RAM; require>=16GiB available and>=8logical cores before launch.
Record exact commands,raw pairs,live raw-hand accounting and every child exit.

Six prespecified contrasts form one Bonferroni family: treatment-minus-source on
each5anchors,plus the mean treatment-minus-weak_control effect across the2heldout
anchors. Compute the latter within each common-deal pair BEFORE variance estimation
so cross-anchor dependence is retained. Report ordinary95%normal and simultaneous
1-0.05/6 two-sided intervals using NormalDist.inv_cdf(1-0.05/12).

Admission to separate independent confirmation requires ALL:5source contrasts
have positive means;>=3adjusted lower bounds>0 including Standard10 and>=1heldout;
the heldout retention contrast's adjusted lower bound>0;all integrity checks pass.
Control contrasts and training-anchor tradeoffs are descriptive only. There is no
alternate gate, midpoint candidate, seed replacement or budget extension. Passing
does not establish Slumbot success or Nash strength. No external call occurs here.

## Evidence and next action

Capture full runtime/helper sources,hashes and dirty patch before launch. Require
complete known physical prefix,worker count totals,first-budget-crossing and
fixed-pool audit,86finite changed tensors/Adam states,frozen/source identity and
all15cells and exactly16children (one trainer plus15evaluators) exiting0.
Independently recompute raw statistics and the joint gate before finishing the same
record. Preserve any interruption without automatically retraining or repeating
completed cells. A failed gate guides a different mechanism,not old-final rescue.
Before any future external qualification, separately repair and validate the
journal/terminal/session deficiencies identified in the offline protocol audit.
