# Fixed temporal aggregate versus final and root

Two retained seeds (1,3), no checkpoint selection by outcomes. Use exactly the
three replay-control boundaries frozen in temporal qualification: root, +262k,
and +1M. Equal arithmetic mean of legal T1 probabilities, then greedy action;
all candidates and anchors physical200bb/legacy_v4. This is a deterministic
deployment ensemble, not a CFR reach-weighted average strategy.

For each seed use 1024 mirrored decks per anchor across the same eight anchors
as the completed fresh-only trial. Preservation: Standard10,CFR4,legacy_iter16,
legacy_mixed65k. Transfer: mixture_s1,mixture_s3,heads_s1,heads_s3. Shared ancestry
means transfer is not lifetime-unseen generalization. Evaluate root,final and
aggregate on identical decks with rotating execution order. Total 98304 terminal
executions; no training or Slumbot hands. Seeds are 202609081000 + 100*seed +
1000003*anchor_index. Reject reuse within this cohort or inventoried prior corpus.

Fixed horizon, no significance stopping or outcome-dependent extensions. Report
aggregate-minus-final and aggregate-minus-root, final-minus-root, each seed,
panel, anchor and seat. Use mirrored-deck paired differences with normal1.96
sample-standard-error CIs, explicitly conditional/unadjusted, not population-seed
inference. Report actual execution seconds and decision count per policy; these
include poker engine/opponent inference, not pure candidate inference latency.

Only consider further external calibration if aggregate-minus-final and
aggregate-minus-root have positive panel means in both seeds on both panels,
pooled lower CIs positive in both seeds, both seat means positive, and no anchor
upper CI below -25 bb/100. Otherwise do not promote. This is an allocation gate,
not proof of universal strength or final acceptance. Preserve inconclusive and
negative results; no automatic ensemble-weight or checkpoint sweep.

Write every completed paired comparison to raw JSONL. Update logger at each
anchor boundary. Do not restart automatically after interruption: partial
execution suffixes must be reviewed. Hash checkpoints and loaded runtime sources
before and after execution. Final result requires independent raw recomputation.
