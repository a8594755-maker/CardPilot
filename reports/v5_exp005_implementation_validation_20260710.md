# EXP-005 Implementation Validation

Checked at `2026-07-10 14:17 EDT`.

Verdict: `PASS_AWAITING_EXACT_GATE_CUTOVER`.

- `train_v5.py` now supports `--opponent-assignment per-group` and
  `--opponent-groups 5`; the existing `per-iteration` and `per-worker` paths
  remain selectable for rollback.
- Five balanced groups differ in size by at most one, worker membership is
  reshuffled each iteration, one group is self-play at fraction 0.2, and pool
  groups use distinct snapshots when available.
- Focused invariant tests: `5/5 PASS`.
- Offline multi-env smoke: `5` workers, `2` envs/worker, two iterations,
  `200` actual hands, pool size advanced `0 -> 1 -> 2`, checkpoint saved, PASS.
- Full V5 regression suite: `153/153 PASS`.
- Implemented trainer SHA256:
  `d9884241740d7040eb5ad09b6810c40423e2558ddac3544cf877b127315713b5`.
- Live trainer PID `48476` was not restarted and continues its already loaded
  per-iteration behavior. This implementation changes behavior only when the
  registered continuation is launched.

Next action: at the first exact PASS gate, freeze/hash that checkpoint, fill
the cutover identity in the registration JSON/Ops log, and launch exactly one
continuation with `--opponent-assignment per-group --opponent-groups 5`. All
other flags remain unchanged.

