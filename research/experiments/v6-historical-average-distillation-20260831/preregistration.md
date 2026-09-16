# Frozen historical behavior average distillation

Registered after the completed fixed40k experiment rejected both selfplay-share
endpoints. Control25 was -107.2536 and selfplay75 -141.0145bb/100; both raw and
session95% intervals were negative. Their unpaired difference was inconclusive.
No extension or100k qualification is admitted for either endpoint.

Hypothesis: a compact learned approximation to a temporal mixture of historical
policies may retain broader behavior than the final response policy. This is a
new supervised learned-weight experiment, NOT a repeated PPO run, weight average,
benchmark-specific rule, full NFSP implementation, or equilibrium guarantee.
NFSP motivates whole-episode strategy sampling and reservoir behavior learning:
https://arxiv.org/html/1603.01121v2 (Heinrich and Silver2016, sections2.3/3).
The present experiment does not learn new best responses. The truncated existing
observation is not perfect recall, further limiting equilibrium interpretations.

Choose the control25 trajectory by design as the original25% reference regimen,
not by a significant external ranking. Freeze17 equally weighted teachers: its
source anchor0 plus first archived checkpoints reaching each physical-hand knot
65536,131072,...,1048576. The final knot may use its immutable final checkpoint.
No checkpoint is selected by return. Verify original physical counters, contract,
all hashes and same86-tensor architecture before collecting any hands.

On every new200bb v6 native hand, independently sample one uniform teacher index
for EACH physical seat. Keep both identities fixed for the entire hand. Generate
full52-card permutations and separate action uniforms from hand-index-derived
seeds, independent of scheduling, teacher choice and outcome. Execute float32
batched teacher inference, float64 legal softmax, temperature1, no overrides.
Store a completed-hand trace with full deck, teacher identities, all observations'
digests, uniforms, probabilities, legal action slots and terminal payoffs. Hash-chain
the completed traces. No Slumbot access or external-game data is used.

Production budgets are exactly262144 new physical training hands and8192 separate
supervised validation hands. Seeds2026101001/2026101002. These are NOT strength
evaluation hands. Use256 native slots, fixed1024-hand chunks, terminating all slots
at each chunk barrier. Keep a uniform Algorithm-R reservoir of262144 decision
rows (seed2026101003), including both seats. Train on teacher probability vectors,
an unbiased conditional-behavior target under the sampled historical mixture;
do not interpret these targets as values or counterfactual regrets. Decision-row
weighting is explicit; longer trajectories contribute more states.

Initialize student from exact corrected-v6 source anchor0. Same GN critic_v2
architecture; train shared representation and both policy heads, freeze separate
value-head parameters. Adam lr0.0001, batch1024,12 full reservoir epochs, seed
2026101004, gradient norm clip1. No early stopping, epoch selection, source-KL,
action heuristics or reward optimization. Report epochs1/4/12 but ONLY epoch12
can be the candidate. Evaluate heldout soft cross-entropy for source and final;
report hand-grouped mean improvement and normal95%CI. This measures behavior fit,
not poker strength. Record every optimizer step and finite/changed parameter scope.

Before production, unit tests must cover uniform reservoir replacement/RNG resume,
serialization, independent seat teacher assignment, hand-index/deck reproducibility,
masked targets, whole-episode mixture versus naive statewise averaging, and illegal
input rejection. Compare batched CPU and GPU probabilities to canonical decide
on64 preserved states across all17teachers with max absolute tolerance0.00002;
no newly generated validation hands for this test. Record actual model calls.

After collection independently regenerate EVERY deck/teacher draw/action uniform,
replay EVERY stored physical action and terminal payoff, check all observation
hashes/legal masks/probabilities/hash chains, reconcile reservoir retained row IDs
and exact targets against the full training trace. Validation never enters reservoir.
Audit the actual frozen teacher logits again on the first64 production hands.
Regenerated/replayed hands are evidence checks, not additional unique hands.

Save dataset/reservoir state, all traces, optimizer/model checkpoints, exact commands,
source manifest/dirty patch/copies, model/data hashes, actual counters and wall time.
Fresh-only collector: no automatic restart after failure or replacement of evidence.
If interrupted before dataset persistence, preserve raw prefix and explicitly mark
the experiment incomplete rather than pretend exact reservoir recovery. Completed
dataset permits a future explicit training-only continuation from saved optimizer;
no unqualified resume is implemented here.

Fit gate: all evidence and finite weights valid, all fixed epochs complete, heldout
mean CE improves with95%CI lower>0. This admits independent internal diagnostic and
deployment-parity checks followed by a separately registered20k external pilot, not
100k qualification or a strength claim. If gate fails, finish this same experiment
and analyze the observed failure; do not rescue an earlier epoch.

Exact initial command:
python research/experiments/v6-historical-average-distillation-20260831/run_distillation.py
