# Preserved Slumbot-state policy-distribution diagnostic

The frozen raw actor failed fresh5k at -79.2126 bb/100 even though it improved
substantially against five learned anchors.  Before spending more training or
external hands, replay every public decision state preserved in that complete
audited cohort through two frozen policies: the failed raw actor SHA256
9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4 and
the v6-rebound Standard10 source/anchor0 SHA256
944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2.

This experiment is read-only and offline: zero network calls, Slumbot hands,
training hands, weight updates, or endpoint selection.  Verify every input hand
and decision identity against the completed fresh5k audit.  For all preserved
states and each street-seat partition, compute raw/source policy entropy,
bidirectional KL, total variation, greedy-action disagreement, probability on
each policy's greedy action, and mean action-slot probability/greedy mixes.
Treat the corpus as raw-policy on-policy states, not an unbiased source-policy
value evaluation; do not infer counterfactual win rate.

The diagnostic is informative if it identifies a reproducible partition with
at least 100 states and either greedy disagreement above 25% or mean total
variation above 0.10.  Its decision is descriptive: choose the next training or
execution-contract hypothesis from the largest well-supported drift, without
using Slumbot outcomes as labels and without reviving imitation solely because
the source is externally stronger.
