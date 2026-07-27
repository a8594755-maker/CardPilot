# V5 AlphaHoldem Takeover Handoff - 2026-07-11

Checked: 2026-07-11T09:01:16.4109514Z

## Immutable objective

- AlphaHoldem V5-from-zero, full 200bb HUNL, official greedy-direct Slumbot.
- L5: 100k+ official hands, bb/100 > 0, 95% CI lower > 0. L6 additionally near +11.1 bb/100.
- EXP-002 retained; EXP-003 terminally INCONCLUSIVE; EXP-004 priors fixed 0.01/0.02.
- Ledger append-only, fail-closed, exact checkpoint identity, complete bundle, one behavior change.
- Remaining 2.7B budget is not continuation authority.

## Terminal EXP005-C state

- Historical EXP-005 pilot remains EXPLORATORY_PILOT_NO_METHOD_JUDGMENT.
- EXP005-C remains EXP005C_FAIL_PROTOCOL_ABORT at first60 throughput ratio 0.4141816098 < 0.85.
- All post-row60 treatment data is POST_PROTOCOL_EXPLORATORY_ONLY.
- EXP005-C primary/MEAS/promotion/formal remain forbidden and Tier-2 remains frozen.

## EXP-W1 route

- EXP-W1 is now exactly preregistered; preregistration SHA dd14e588b0fe7aee06422534663f8ff802375325cae1db2f823a28ed10ff4324.
- Immutable design lock v1 SHA de522a42e6948842f8d06ad3b0c26b07d15f1d18fe721c3eb8b03cf6e29ab02b is read-only.
- Exact source is gate31400 / 515,989,661 hands / SHA bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e.
- Sole behavior variable: control warmup epochs 0 versus treatment epochs 8.
- Treatment is value-head-only at iteration31401 on the first fixed-deal on-policy rollout batch. Reward semantics, trunk, policy weights, optimizer source state, pool, seeds, assignment and all other flags are identical.
- Both arms are sequential per-iteration fixed20M actual hands. Primary is exactly100k common-deal paired treatment-minus-control; PASS requires CI lower > 0 and halfwidth <=15 bb/100.
- Control and treatment full dry-runs each passed 22/22 immutable-lock checks.
- Cutover verifies candidate trainer SHA before copy and live train_v5.py again after copy before launch.
- W1 focused tests 12/12 and cutover/lock tests 5/5 PASS.
- Live train_v5.py remains unchanged; W1 run directories and warmup report do not exist.
- Launch authority remains NONE because automatic W1 launch was forbidden. Next action is explicit user decision to launch the control arm or stop.

## Official strength

- L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].