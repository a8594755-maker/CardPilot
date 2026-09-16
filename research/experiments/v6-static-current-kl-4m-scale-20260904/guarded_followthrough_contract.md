# One-shot ownership and safe-boundary contract

Command: `python research/experiments/v6-static-current-kl-4m-scale-20260904/run_guarded_followthrough.py --trainer-pid 57140 --launcher-pid 29580`

The process owns only this existing experiment's accounting and preregistered
evaluation. It never starts more training, restarts a stopped run, selects an
endpoint, overwrites an existing evaluation directory, or promotes to 8M.

Read `guarded_followthrough_v1/ownership.json` for owner PID and creation time,
and `guarded_followthrough_v1/status.json` for phase and any active child PID.
Verify those identities against the OS; a status file alone is not proof of life.

While the owner is live:

- Do not write this experiment record from another process. The owner updates
  physical training counts every five minutes while waiting and evidenced paired
  evaluation hands every minute during evaluation. A partial gzip only contributes
  complete JSON pair rows (four physical hands each); unrecorded work is not invented.
- Do not modify its 267 hash-bound Python/source dependencies. In particular,
  leave production train_v5.py unchanged until the guarded evaluation is terminal.
- Do not run another evaluation or aggregate writer against the same output paths.

The process first waits for the exact existing trainer and sequential-launcher
identities to terminate naturally. If any endpoint remains below 4,194,304 hands,
it stops with `SAFE_BOUNDARY_NEEDS_MANAGED_TRAINING_CONTINUATION`, retaining all
evidence. The main researcher then integrates/qualifies managed resume and continues
only the remaining hands; the existing target and learned method remain unchanged.

If all three targets are complete, it retains the old production runtime for the
already-preregistered evaluation before source cutover. It saves the original
training audit, permits only the precisely known incident-related failures to
reach the independent post-hoc checker, and starts no evaluation unless that
checker qualifies all three frozen endpoints. The original failure values stay
unchanged. Any unrelated integrity failure stops the sequence.

All original anchors, 2048 pairs/anchor, both seats, three evaluation seeds,
20k-state drift budgets and drift seeds remain unchanged. Drift jobs run
sequentially to simplify single-GPU ownership; this changes scheduling only.
Existing original aggregation is preserved, including its failed integrity gate
and historical AND label. The additional scoped report reconstructs paired reward
arithmetic, uses the preregistered broad-reversal OR and strict drift bounds,
always includes all three seeds and the fixed Seed1/Seed3 subset, and always sets
automatic promotion to false.

After `EVIDENCE_READY_FOR_RESEARCH_ANALYSIS`, the main researcher analyzes actual
results and finishes the same record. Only then may the next research allocation
be chosen. Production managed-resume integration remains required before any new
training. If the owner stops unexpectedly, inspect its active child PID before
taking ownership; do not assume a child evaluation stopped with its parent.

Qualification before launch: 25 synthetic protocol/report tests pass, and reward
arithmetic was checked on 24,576 already-existing 2M pair rows. Zero new poker
hands were consumed by these checks. Preflight verified both exact live processes,
unchanged production source, absent evaluation destinations and the original
evaluation parameters. This does not claim that future execution has succeeded.
