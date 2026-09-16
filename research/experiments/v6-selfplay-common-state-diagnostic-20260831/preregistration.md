# Preserved common-state self-play-mixture behavior diagnostic

Registered while the fixed40k external cohort is running, before its outcome is
inspected. This analysis cannot change either endpoint, live session, budget,
ranking/allocation rule or existing experiment source. No live hands/journals/
returns are read. No model query, environment step or network request is made.

Read only completed v6-selfplay-transfer-deployment-parity-20260831 inputs:
analysis SHA8e584ec8268fdd31e5f639efccaf20804a27e5832ee3f0c1957ab4c5d7370df2;
parity raw SHAbf5fca7060e852363747341ba207dffd17b7e96d65dba9f20dcd01ab2150b8f0.
Both fixed models were queried on the same4202states from512old exogenous hands,
with identical uniforms seed20261009. No new samples are generated here.

Hypothesis: changing self-play share produces measurable distribution changes,
not merely an indistinguishable endpoint. This describes the intervention;
neither larger nor smaller distance implies stronger poker or positive transfer.
The internal heldout contrast was inconclusive; external testing still includes
both endpoints irrespective of this diagnostic. No benchmark action rules.

Primary descriptive quantity: total variation between nine-slot action
distributions, averaged first within each of512exogenous hand blocks and then
across blocks. Report ordinary95% normal CI over those512blocks. Also report
hand-weighted Jensen-Shannon divergence in bits, common-uniform selected-action
disagreement, changes in fold/passive/raise/all-in probability, and unweighted
state means. The common-uniform disagreement is coupling/order dependent; it is
not the theoretical minimal disagreement or a win-rate estimate. All-in is the
dedicated slot8, and raise probability includes slot8.

Eight street/seat strata are descriptive only, with no significance labels or
strength selection. This is a fixed synthetic corpus, not policy occupancy,
unseen opponent families or independent fresh Slumbot data. State-weighted and
hand-weighted summaries must not be conflated. Confidence intervals describe
the fixed exogenous-hand sampling unit, not uncertainty in external win rate.

Validate aligned state/hand/seat/street/uniform/model identities, finite normalized
probabilities, selected-action support and all4202indices per arm. Compare exact
analytic numeric fixtures and hand-versus-state weighting; prohibit network.
Capture own sources/hash/patch and preserve all5active external source/copy pairs,
both active frozen model hashes and input dependency hashes before/after.

python research/experiments/v6-selfplay-common-state-diagnostic-20260831/run_diagnostic.py

Accounting: zero new training, evaluation, Slumbot or validation hands; zero model
queries and network attempts.512hand blocks/8404preserved policy-state rows are
reused observations, not new games or training samples. Finish this record after
tests and integrity checks; do not affect the ongoing external cohort.
