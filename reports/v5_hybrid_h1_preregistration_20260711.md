# H1 HYBRID Critic-v2 Preregistration

Status: `REGISTERED_NO_LAUNCH`

## Exact question

Does one integrated critic-v2 contract materially reduce normalized held-out critic error after fixed same-start 20M-hand arms without degrading throughput or entropy? H1 makes no component-level causal claim.

## Atomic treatment

- Fixed unit conversion: terminal reward, old value, GAE return, critic target and Trinal-Clip value bounds are divided by the exact 200bb effective stack. PopArt is forbidden.
- Replace the linear value head with 256→256→128→1 and feed it `shared_h.detach()`, so value gradients cannot update the actor trunk.
- Set value-loss coefficient from 0.5 to 1.0. Actor/shared weights and actor optimizer state are exact copies; pretraining policy logits must be bitwise identical.

## Same-start design

Control critic-v1 and treatment critic-v2 each run exactly 20M actual hands from gate31400 / 515,989,661 hands / checkpoint SHA `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`. Fixed deals, seeds, pool, priors, optimizer source and rollout configuration are identical. EXP-W1 and EXP005-C are not reopened and their endpoints are not reused.

## Primary gate

On immutable holdout `H1-CAL-001`, PASS requires normalized held-out MSE relative reduction point ≥15% and deal-cluster bootstrap 95% CI lower ≥10%, plus treatment/control effective h/s ≥0.85 and entropy non-inferiority. The endpoint sample is fixed; no extension, second seed or later checkpoint substitution.

FAIL and INCONCLUSIVE are frozen exactly as specified in the JSON. H1 uses training metrics only. It launches no official Slumbot hands and authorizes no V4/L5/L6 claim. Registration authorizes implementation and offline validation only; both arms remain blocked until a separate immutable design lock and preflight PASS.

