# Corrected-v6 frozen physical1m independent confirmation

Registered before any new evaluation. Parent physical1m experiment completed
1,051,652 actual training hands and 327,680 internal hands with a passing
six-contrast gate and independent evidence review. Only its final is eligible.
The parent is COMPLETED; no training, checkpoint rescue, extra seed search,
parameter change, or pooling parent outcomes is permitted here.

## Fixed identities and sample

Parent review SHA256
68e6214a068f727f7abae83c0070bc5f1d765371b6bcd9fc733985dd3f8373aa;
parent execution SHA256
076e30fd46017800d344abe691c5b1d1380cb001484bb4fc21de5ffa870b211c.
Final SHA256
bc4f62257a474ad438cd574d4c59b28ea009060749f0fb86e3e97c46120d0172;
mid262 SHA256
7d7eeb0d648f2d1a51ff79b600e59e0fdc4afcca73541e90bd5dda304348a0c3;
source SHA256
944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2.
All five anchors retain the exact parent identities. Copy and hash all models
before launching the first cell. No model writes during or after evaluation.

Twelve cells: source and final versus each of five anchors, plus mid262 versus
held-out anchors3/4 only. Exactly8192 mirrored pairs per cell, two seats per pair:
196,608 new internal hands. One new seed20261002, common full52card deck sequence
and physical-seat/decision RNG across cells. Explicitly verify unique full decks
and no overlap with the parent's8192 full decks before evaluation. This does not
claim all partial boards/private-card combinations are unseen.

CPU6 concurrent evaluators, one torch thread each, below-normal priority. Same
corrected-v6 sampled policy, temperature1, legal masks, observations and rules.
Run the evaluator from the captured source copy, not a mutable alternative.
Zero new training hands, zero Slumbot hands. No interim scores or early stopping;
monitor only process exits, durable raw newline counts and frozen identities.
No restarts/retries/extensions. Preserve partial evidence on infrastructure error.

## Statistics and decision

Independent unit is the common-deal mirrored pair, not each seat or anchor.
Six primary contrasts: final-source on anchors0..4, and the within-pair average
(final-mid262) on anchors3/4. Report ordinary95% normal CIs and Bonferroni
simultaneous95% family6 CIs (z at1-.05/12). Do not pool parent samples.

Confirmation passes only if all five source-difference points are positive,
at least three adjusted lower bounds are positive including anchor0 and at least
one of3/4, and the held-out growth adjusted lower bound is positive. All raw,
identity, session and independent arithmetic checks must pass. The same gate as
the parent is locked; mid262 is a reference, never an eligible fallback.

A pass admits a separately preregistered fresh Slumbot20k pilot of this exact
final, after candidate-specific offline deployment parity/readiness checks. It
does NOT admit/claim the100k goal, automatically scale training, or establish
Nash strength, unseen-family generalization or multi-seed training causality.
A failure directs mechanism research; no alternative checkpoint promotion.
Known-family anchors3/4 did not enter this model's training but have informed
earlier research. The corrected-v6 source itself scored-82.8164bb/100 on its
separate audited fresh20k; no external data are used to train or modify policies.

## Provenance and execution

python research/experiments/v6-physical1m-independent-confirmation-20260831/run_confirmation.py

Log exact expanded commands, source copies/SHA256/dirty patch and ongoing raw
accounting. Preserve the parent's copies and all recorded evidence; historical
original paths need not remain immutable forever. Current execution copies and
originals must agree throughout this run. A known legacy logger classification
warning for two executed Python comparison commands remains documented in the
parent; it is not removed/reclassified here and has no effect on raw statistics.
Wrapper ends at COMPLETED_PENDING_REVIEW. A separate independent review checks
all12normal child exits, regenerates deals and CI arithmetic, then finishes this
same record. No external requests or automatic subsequent experiment in wrapper.
