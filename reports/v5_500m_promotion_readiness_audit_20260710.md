# V5 500M Promotion Readiness Audit

Checked at `2026-07-10 02:13 EDT`.

## Verdict

`WAITING_BLOCKED_EXPECTED`. The immediate direction is safe after two
control-plane hardenings, but the 500M promotion is not currently eligible and
was not launched. Training remains unchanged.

## Live state

- Run: `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709`
- Trainer: PID `48476`, alive, not restarted
- Live: iter `27424`, `450,580,699` hands
- Saved checkpoint: iter `27400`, `450,186,098` hands
- Health: `PASS`
- Throughput: collect `4,560.78 h/s`; effective `1,784.3 h/s`; long effective `1,822.7 h/s`
- Gate `27400`: exact `PASS`; post-gate review `REVIEW_REQUIRED_NO_AUTO_RESTART`; preflop `WARN`
- Next gate: `27500`
- Watcher rearm: canonical script only, survival `PASS`, range `27500..28600`

## 500M cadence

- Stage: official greedy-direct `promotion20k`
- Plan: `12 x 1,700 = 20,400` hands, temperature `1.0`
- Current status: `CANDIDATES_BLOCKED`
- Expected blockers: `training_hands`, `quality_gate`
- Saved-checkpoint remainder: `49,813,902` hands
- Effective ETA: about `7.7h`; the dashboard's roughly `3h` collect-rate ETA is not the governing ETA
- Output collision: `PASS`
- Active launches: none

The declared full bundle includes hand JSONL, decision dump JSONL, CI,
promotion JSON/MD, dump analysis, loss report JSON/MD, artifact audit JSON/MD,
hand review JSON/MD, and selector replay JSON/MD.

## Control-plane corrections

1. Formal100k now requires `promotion_20k_strong=true` from the exact same
   checkpoint identity and is pinned to that promotion checkpoint and gate.
   A strong result from another checkpoint can no longer authorize it.
2. Official direct sessions now fail closed if Windows `BelowNormal` priority
   cannot be applied.

These changes do not alter trainer behavior, weights, rollout parameters,
priors, or experiment selection. No Slumbot benchmark was launched.

Verification: focused tests `9/9`, full V5 unittest suite `151/151`, rearm
contract checks `14/14`.

## Direction

Keep the current trainer unchanged until the first eligible saved checkpoint at
or above 500M whose health and exact-checkpoint quality gate pass. Then run the
20,400-hand official greedy-direct promotion bundle. Formal100k may run only on
that same checkpoint when the promotion gate is strong.

EXP-005 remains a provisional structural priority, not an adopted method. It
may be separately registered only if the 500M promotion is non-strong and the
complete loss review confirms the structural diagnosis. EXP-006A can replace
it only if its fixed 500M direct-signal gate passes. Never bundle the two.

No stronger-than-V4, L5, or L6 claim is currently allowed.
