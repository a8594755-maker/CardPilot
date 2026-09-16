# Reach-target fidelity gap decomposition

Prepared only after the independently reviewed parent decision
REACH_TARGET_FIDELITY_GATE_NOT_PASSED. Parent review SHA256 is
9c439acec863c6cbb02cf89c51356f14e4c676e8a5a6953844bb7a93b4f04890. This record changes no learned weights.

## Fixed evidence and work

Use only the parent's frozen initializer/epoch01/epoch04/epoch08 checkpoints,
the exact262144 retained training observations and reach targets, and the exact
8192 fresh native validation-hand evidence already collected by the parent.
No new environment, Slumbot or strength hands; no network. Evaluate each four
checkpoint once on every retained training state with the parent's qualified
GPU batched probability path (1048576 model-state queries). Parent validation
probabilities are reused, not queried again. Preserve full probability arrays,
checkpoint/input hashes and exact row order.

Independently reconstruct validation metadata from raw native actions: street,
actor/hero, decision depth, legal-action count, own earlier-action count,
whether the current street had more than six prior events (not represented by
the fixed action tensor), three-teacher probability disagreement, target
entropy, and maximum own-reach posterior weight before the current action.
Posterior weights are separate by seat, reset per hand, and update only after
predicting the current action.

## Fixed descriptive statistics and decision

For each checkpoint, compute target CE, JS and TV on retained training rows and
validation rows. Compute the preregistered per-hand hero TV and paired
epoch08-minus-epoch04 interval on the existing8192-hand validation set. Report
TV/CE by fixed street, truncation, posterior-concentration quartile,
teacher-disagreement quartile and target-entropy quartile. Empty groups remain
empty; no zero imputation. These are fidelity diagnostics, not returns.

Flags:
- TRAINING_FIT_UNDER_THRESHOLD iff epoch08 training-row meanTV >0.15.
- GENERALIZATION_GAP iff epoch08 validation-row TV minus training-row TV >0.03.
- CE_TV_OBJECTIVE_CONFLICT iff epoch08 validation CE < epoch04 validation CE
  while the paired hero epoch08-minus-epoch04 TV95% lower bound is >0.
- HISTORY_TRUNCATION_CONCENTRATION iff truncated validation rows have at least
  0.03 higher epoch08 meanTV than nontruncated rows.
Primary decision priority is training underfit, then generalization gap, then
CE/TV conflict, then history concentration, otherwise GAP_NOT_LOCALIZED.
Multiple flags remain reported.

If training underfit and CE/TV conflict both hold, next test a metric-aligned
hand/seat-balanced TV-family learned fit with a fresh untouched validation
cohort; do not rescue epoch04 or strength-test either parent checkpoint. If a
generalization or history flag dominates, prioritize representation/history
before more optimization. No conclusion here establishes strategy quality,
exploitability or Slumbot transfer.


