# Two retained-parent real-worker fresh-only smoke

Seeds1/3 fixed flat capacity9 parents from the completed family-allocation trial:
S1 SHA5cc8fd0140f03d34450027dc6160c192ea7e7b0a8c7f3c7800ba456ad967d629,
S3 SHA633e9559e05dc265f2f1eda344a4af19708851ddaeffe97293ba915252bcc6f5.
Additional16384 physical hands each, whole-iteration overshoot, maximum600s/job.
No new evaluation or Slumbot hands. No automatic retry. Original parents immutable.

Only ratio changes0.5->0; rolling buffer remains2. Preserve initial weights,
86-state Adam/LR, replay entries/RNG/cumulative count, assignment evidence and
static reference; new exclusive managed attempt namespaces. Original prefixes
copied/hash-checked. Exact old worker RNG continuation is not claimed.

Terminal requirements: clean parent/observed child exits, all requested physical
hands, Adam steps advance, zero actual new replay rows, cumulative replay/RNG
unchanged, rolling buffer ends at current iteration, all completed assignments
and metrics present, fixed anchors retained, raw prefix and source hashes intact.
An independent terminal check must reconstruct the first resumed assignment and
check observed exposure/counters before record completion. Strength is not tested.
Production, if subsequently registered, starts from original parents, not smoke
descendants. No automatic scaling from this mechanics smoke.
