# Outcome-blind common-state source-retention diagnostic

Register before generating states or querying these policy distributions. The
source-KL pilot's fixed245760hand evaluation continues unchanged. Do not inspect
its partial scores,select a checkpoint,change the gate or add benchmark hands.

Training reference-KL metrics are measured on each learner's own trajectories;
different trajectory distributions can confound their direct comparison. Measure
the frozen source,KL0.01control and KL0.1treatment on exactly the same exogenous
state set to assess the retention mechanism,not winning strength.

Frozen source SHA944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2;
control SHA0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606;
treatment SHA9b7b0e3a0c2be3bdfbbab4167e1eb4a5e7f284d619a8afa13d608c9943b46efb.
No model weight update,alternate checkpoint or policy-driven state selection.

Generate512fixed synthetic native v6 hands with seed20260924. Hand index modulo4
selects uniform legal slots,80%passive-biased,70%minimum-raise-biased,or50%uniform
physical-raise-biased behavior. Save every pre-action state and the full deck and
actions of every hand. These behavior actions are independent of all3models;
model decisions are observed but never applied to generate this dataset.

Query shared execution_v6.decide on every state for each model,CPUfloat32 and
float64 legal softmax,one process/one torch thread,no GPU. Use constant uniform0.5
only to exercise the shared inference function; selection is not a played action.
Measure total variation from source,source-to-candidate KL,reverse KL,JS,entropy,
legal fold/all-in probability,and argmax disagreement. KL uses a declared1e-12
probability floor followed by renormalization over legal actions; count clipped
entries explicitly. TV/JS/entropy use original legal probabilities.

Primary descriptive summaries first average states WITHIN EACH HAND,then average
hands equally. Also report state-weighted summaries and street/seat strata with
their counts. Do not claim state rows are independent or attach an IID state CI.
The directional hypothesis is lower common-state TV to source underKL0.1than0.01;
it is a mechanism diagnostic,not an admission test or proof of better poker.
Report either direction without replacing seeds,extending the sample,or changing
the ongoing evaluator. Downstream choices still depend on the completed fixed
strength experiment and its required independent confirmation.

Test metric identities,disjoint distributions,KL floor behavior and hand weighting
before the real diagnostic. Snapshot source/helper hashes and dirty patch,retain
raw states/distributions/trajectories,verify source and all3frozen identities before
and after,and verify the active pilot's71source pairs unchanged. Preserve failed
attempts. All new_training_hands,evaluation_hands,and slumbot_hands are0;
512diagnostic trajectories and their inference queries are separate accounting.

Exact first command:
python research/experiments/v6-common-state-retention-diagnostic-20260831/run_diagnostic.py --attempt attempt01
