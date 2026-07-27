# EXP-W1 exact preregistration

Status: PREREGISTERED_DESIGN_COMPLETE_NO_LAUNCH_AUTHORITY

Single behavior variable: exp_w1_value_warmup_epochs, control 0 versus treatment 8. Both arms start from exact gate31400 checkpoint bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e and otherwise use identical optimizer, pool, per-iteration assignment, fixed deal stream, seeds, flags, and 20M actual-hand budgets.

Treatment performs value-head-only warmup at iteration 31401 on the first normal rollout batch, with deterministic whole-hand 80/20 split. It must improve heldout MSE by at least 2%, keep policy logits bitwise unchanged, keep every non-value model/optimizer state unchanged, and write an immutable PASS report before normal PPO may continue.

Primary evidence is exactly 100k common-deal paired treatment-minus-control endpoint differences. PASS requires CI lower above zero and halfwidth at most 15 bb/100. This is conditional single-seed method evidence, not V4/L5/L6 strength.

No trainer or Slumbot launch is authorized by this preregistration.