# Public opponent worker integration analysis

The accepted recovery2 completed exactly 256 physical-v6 terminal hands through
the real single-worker shared-memory path.  The worker emitted 1,138 hero
transition rows and requested main-process inference 1,139 times, all with the
hero model identity.  Its 984 public-opponent decisions were sampled locally,
all counted as inference bypasses, and their action counts summed exactly.
Environment and public-opponent hand counters both reported 256.

The initial `run/` ended when the parent observed Windows pipe closure before it
could write a summary.  `run_recovery/` established exact core accounting but
the harness joined before draining the final transition batch, so pipe
backpressure forced termination and failed only the exit-code gate.
`run_recovery2/` drains during shutdown and exited zero.  The accepted worker
model, seed, target, action path, and accounting semantics were unchanged.

Decision: `ADMIT_MATCHED_PUBLIC_OPPONENT_HERO_SMOKE`.  The integration remains
default-off and has not updated hero weights.  The next experiment may expose a
bounded fraction through the production CLI/checkpoint accounting and run a
short matched Standard10-initialized control/treatment.  The public model must
remain a minority of external-opponent hands and promotion must rely on
untouched learned-policy anchors, not performance against the fitted model.
