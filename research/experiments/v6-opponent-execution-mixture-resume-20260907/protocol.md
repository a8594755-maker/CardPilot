# Fixed two-seed real-worker resume qualification

Use the retained recent-pool stage2 Seed1 and Seed3 checkpoints, not new
initializations. Sequentially run at least 16,384 additional physical hands each,
allowing one complete-update overshoot, with a 600-second per-job natural boundary.
No automatic retries. All 12 workers, eight environments per worker, seeds,
optimizer LR/state, replay state, reference weights, actor scope and opponent
assignment state remain inherited. Keep the anchor-latest strategy unchanged.

The only learning distribution intervention is historical opponent mixture weight
0.5. Each managed attempt uses a new exclusive namespace: statistical continuation,
not bitwise restoration of in-flight workers. Parent raw prefixes are copied and
verified, not overwritten. Initial captured checkpoint must preserve all previous
initial-state keys including the pool strategy. Optimizer/replay/counters advance.

An exclusive mixture_runtime.json binds the exact wrapper, qualified source,
mixture setting and parent hash. The frozen trainer checkpoint itself does not
serialize this extra setting; subsequent continuation must bind and check this
sidecar, not infer the execution setting from the checkpoint alone.
Actual historical-opponent forward counts and the first eight original/mixed
probability rows are retained to verify this intervention occurred during rollout.
The first batch is mechanism evidence, not a representative strength sample.

Qualification requires two clean worker exits, preserved parent/initial state,
distinct verified attempt receipts, contiguous appended logs, finite advanced
optimizer state, active replay and nonzero actual mixture inference. No internal
or Slumbot strength evaluation is allocated. Smokes are retained training work,
not evidence that the method improves poker. Terminal review precedes any larger
matched multi-seed allocation. Existing experiments and runtime files are immutable.
