# Conditional fixed20k strict sampled weak-KL Slumbot pilot

Prepared conditionally before independent-confirmation results, then registered
after weak-source-kl-independent-confirmation-20260830 completed147456hands with
WEAK_KL_REPLICATION_PASSED, a passing post-exit review and a warning-free record
audit. No tests or external hands for this experiment preceded registration.
The runner enforces this condition, verifies its raw input hashes, and refuses
existing output paths. This protocol is frozen before any external result.

## Single frozen learned policy

Use exactly weak-source-kl-pilot-20260830/frozen/weak.pt,
SHA256 a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b.
No weight updates, archive selection, policy mixing, action bias, range/context
override, guarded selector or benchmark-specific rules. Native model/sample,
temperature1,200bb,v4,GN,separate preflop head. Copy the checkpoint and all execution
source before the first hand. Keep the confirmation's weights unchanged.

## Fixed external sample

Eight independent client processes, each2500successful fresh hands, seeds
2026091001 through2026091008, for exactly20000hands. Seeds had no prior research
record use when this draft was prepared. Each process starts token=None and uses
the tested persistent-session-no-retries transport with strict policy execution.
Use one CPU Torch thread and one interop thread per client. Start each after the
previous client's first raw hand and decision dump are available; no score-based
start, stop, extension or replacement. Maximum operational time10800seconds.

On a failed client, malformed/truncated evidence or operational timeout, stop
only this wrapper's owned live clients and preserve every file. No retry, resume,
reseed, supplement or overwrite is authorized by this protocol. Any later
recovery requires a separately reasoned evidence-preserving decision.

## Evidence and primary estimate

Keep raw successful-hand JSONL, decision dumps, result JSON, exact commands,
process/session ledger, frozen SHA256 identities and source patch. Update both
evaluation_hands and slumbot_hands from complete raw rows during execution.
Require all8clients exit0 and each raw stream contains attempts/successes1..2500.
Strict audit must pass checkpoint/mode/temperature/seed/reward/action-replay,
fallback-free execution and observable session-independence checks. Hidden server
deck independence cannot be proven from client evidence alone.

Compute pooled raw bb/100 and a two-sided95% normal interval from individual
hand outcomes; independently recompute in chip units with100chips/bb. Report
all8session means and a predeclared Student-t95 interval over session means(df7)
as sensitivity evidence, not a replacement selected for favorability.

## Fixed decision and limits

Only the complete valid20000-hand pilot receives a performance decision. If raw
bb/100>0, admit a separate preregistered100000fresh-hand test of this exact frozen
policy. Otherwise do not extend, reselect or pool this pilot; use the completed
evidence to choose the next general learned-weight experiment. The pilot's CI
is always reported, but this admission rule is not a claim of significant victory.

The qualifying100k would exclude these20k and all historical hands. The Goal is
still at least100000fresh Slumbot hands from one frozen policy,bb/100>0 and95%CI
lower bound>0; a positive20k point estimate does not meet it.

For context only, strict native-sampled Standard10 previously scored-48.9778bb/100
on a separate20k. Older greedy Standard10 scored-11.4275; it is a different executed
policy. Do not pool either baseline, the aborted external run, or internal
confirmation outcomes. Historical differences are not matched causal effects.

Zero training hands. Run synthetic runner/review/gate tests after registration,
then a zero-hand load of this run's exact snapshot before any external hand.
After all clients/audit complete, wait for the original wrapper to exit, perform
independent chip-space review and finish this same record before any next run.
