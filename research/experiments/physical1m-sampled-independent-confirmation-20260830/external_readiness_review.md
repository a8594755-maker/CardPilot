# Conditional external sampled-policy readiness review

Read-only review during the unchanged independent internal confirmation. No Slumbot sessions, model changes, or new training have been started by this review. This is a conditional dependency for a possible later external experiment, not a change to the current preregistration.

## Sampling semantics

`play_slumbot.py` supports `policy-mode=sample` and temperature1 via categorical draws from the unguarded model probabilities. The guarded/preflop-mixed modes are different policies and must not be substituted for the internally tested sampled policy. The exact model SHA256, observation/action mapping, stack and temperature must be fixed in an external record. Internal and external random-number algorithms need not produce identical individual actions, but must implement the same categorical distribution.

The unchanged final checkpoint passed an actual `--hands 0` loader check, saved as `deployment_dry_run.json`: GroupNorm,8253187 parameters, v4 observation and sample/temp=1, requested/successful hands0. No API game was requested. This establishes model/selector loading only, not end-to-end observation/action parity or strength. Read-only checkpoint inspection found the preflop_pot_fraction_v2 mapping and no stored policy_logit_bias, policy_range_override, policy_context_override or preflop_strategy_profile; no such override is added by this work.

## Independence audit limitation requiring attention before stochastic external testing

`audit_slumbot_session_independence.py:fingerprint` includes hero position/cards, observed opponent cards/board, **actions and winnings**. Its repeated-stream checks compare exact full fingerprints. Consequently two sessions that replay the same deals but sample different actions can have unequal fingerprints and escape the repeated-stream test. Different action trajectories can also expose different board prefixes/opponent cards. The existing audit is an observable deal/action-replay diagnostic, not sufficient proof of independent deals for a stochastic benchmark.

A future external-readiness change should retain existing full fingerprints and add an action-independent observable-deal test, at least position plus initial sorted hero cards at matching indices and consecutive-match runs. Test a deliberately duplicated deal stream with different sampled actions/winnings and test independent streams for acceptable false-positive behavior. Preserve historical evidence/results; do not retroactively label old runs as failed solely from this code limitation. Session readiness staggering already reduces startup collisions, but is not proof of independence.

## Raw-hand evidence and baseline interpretation

`slumbot_ci_from_hands.py` computes raw reward mean/sample-standard-deviation CI, but input-glob expansion does not itself deduplicate overlapping paths or validate policy/session/hand identities. A future external wrapper should use one explicit unique resolved file manifest, reject duplicate hand indices within sessions and non-finite/out-of-stack rewards, reconcile each completed session and dump, and freeze hashes before its final accounting. Never rerun an existing output tag, since the PowerShell bench launcher is not a general immutable-evidence manager.

The current default Standard10 reference of-11.4275bb/100 is a greedy-policy reference. A sampled candidate's raw bb/100 and CI remain meaningful, but its delta against that number is not a matched learned-weight treatment effect. A future sampled benchmark must label this distinction explicitly or collect a separately frozen sampled baseline. The user's success condition is absolute frozen-policy fresh Slumbot EV and CI, not a baseline-relative milestone.

## Decision scope

Finish the currently running98304-hand internal replication first. If its gate fails, follow the registered mechanism-diagnostic branch without external games. If it passes, address and test the stochastic evidence-audit gap before launching an independently preregistered external assessment. Any future formal claim still needs at least100000 fresh Slumbot hands under one unchanged policy and a positive95% lower bound.
