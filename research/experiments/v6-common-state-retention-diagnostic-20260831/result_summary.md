# Frozen common-state retention diagnostic

Decision: COMMON_STATE_RETENTION_MEASURED. Descriptive mechanism evidence only;
no strength gate,checkpoint choice,evaluation budget or external admission changed.

The first preserved attempt passed5metric tests and generated512fixed exogenous
hands with4202decision states (seed20260924). The same states were queried through
shared strict CPU inference for all3frozen models:12606queries. Model outputs
never selected the behavior actions that generated the states.75own source pairs,
71active pilot source pairs and all3checkpoint identities remained unchanged.
Post-run inspection verified3raw hashes,512trajectory rows,4202state rows and
the sum of per-hand state counts. All training/evaluation/Slumbot hand counts0.

Primary equal-hand-weighted TV distance from source decreased from0.1641385542
underKL0.01to0.1460614544underKL0.1(delta-0.0180770998). Equal-hand-weighted
source-to-candidate KL decreased from0.3737865100to0.2560845645; JS decreased
from0.0623504747to0.0491611407. This supports the prespecified directional
retention hypothesis on this exogenous distribution,not better poker strength.
KL is measured with1e-12legal-probability flooring and renormalization; it is
not numerically identical to the training metric's1e-8log clamp. TV/JS are based
on the unmodified probability distributions. No IID-state CI is reported.

Equal-hand-weighted TV within each street/seat stratum:

| Street / seat | States | Hands | KL0.01 control | KL0.1 treatment | Delta |
|---|---:|---:|---:|---:|---:|
| Preflop BB |720|481|0.171154|0.304077|+0.132923|
| Preflop SB |923|512|0.099885|0.068262|-0.031623|
| Flop BB |532|297|0.163591|0.066510|-0.097081|
| Flop SB |441|297|0.198276|0.082578|-0.115697|
| Turn BB |445|246|0.190641|0.098932|-0.091709|
| Turn SB |363|246|0.191637|0.094726|-0.096911|
| River BB |423|232|0.173878|0.115599|-0.058279|
| River SB |355|232|0.268553|0.134956|-0.133598|

The BB-preflop exception is material: stronger aggregate source regularization
does not guarantee uniformly smaller drift. A subsequent read-only code/config
inspection found policy_postflop_only=false,policy_position_only=all,and the
fixed anchor0reference checkpoint. train_mp3_hybrid_h1.py computes forward
KL(reference||current) for all minibatch rows in this configuration,using the
full model forward call; no explicit preflop exclusion explains the exception.
That does not identify a causal explanation. Trajectory composition,optimization
and strategic adaptation remain possible explanations; it could be helpful or
harmful,which must be judged from the unchanged completed strength experiment.

The raw JSONL retains full per-state distributions/metrics and raw trajectory
decks/actions. Hand weighting avoids overweighting long hands; strata include
only hands reaching that stratum. These are512diagnostic deals,not4202independent
hands,and a matched single-training-seed comparison is not multi-seed causality.
No partial results from the ongoing frozen strength matrix were consumed.
