# Conditional fixed20k strict sampled full-network Slumbot pilot

CONDITIONAL DRAFT prepared while representation-scope-independent-confirmation-
20260831 is RUNNING. No tests, production, external connection or admission is
authorized by this draft alone. Register this experiment only after that exact
confirmation completes196608 new internal hands, its independent post-exit
review passes, and its decision is REPRESENTATION_SCOPE_REPLICATION_PASSED.
If confirmation fails, preserve this unused draft; do not register or launch it.
The runner enforces the completed-confirmation and exact-checkpoint gates.

## One frozen learned policy

Use matched-weak-kl-representation-curve-20260830/frozen/full.pt, SHA256
ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e.
This is the full-network final endpoint selected by training counters before
discovery and independently confirmed without checkpoint reselection. Native
model/sample,temperature1,200bb,v4,GN,separate preflop head. No weight updates,
archive selection, policy mixing, action bias, range/context overrides, guarded
selector or benchmark-specific rules. Copy and hash the policy and all executed
source before the first hand. Preserve the original confirmation checkpoint.

## Fixed fresh external sample

Eight independent client processes,2500successful fresh hands each, for exactly
20000hands. New policy seeds2026091401 through2026091408. A read-only scan of
existing preregistrations/run/evidence manifests found no such seed before this
draft. Each process starts token=None, uses persistent_session_no_retries_v1,
strict policy execution,one CPU Torch thread and one interop thread. Start each
after the preceding client's first raw hand and decision dump exist. No interim
score inspection, score-based start/stop, extension, replacement or reseeding.
Maximum operational time10800seconds.

On client failure, invalid/truncated evidence or operational timeout, stop only
this wrapper's owned live children and retain all evidence. No retry, resume,
supplement, overwrite or automatic recovery under this protocol. Observation
timeouts alone are not a client failure; recheck the same original handles.

## Evidence and statistics

Keep raw successful-hand JSONL, decision dumps, result JSON, exact commands,
process/session ledger, frozen SHA256 identities and source patch/copies. Update
evaluation_hands and slumbot_hands from complete raw rows while running. Require
all8clients exit0 and each raw stream contains attempted/successful counts1..2500.
Strict audit must pass model/mode/temperature/seed/reward/action replay,
fallback-free execution and observable session-independence checks. Hidden server
deck independence cannot be proved solely from client evidence.

Primary: pooled raw bb/100 and two-sided95% normal interval from individual hand
outcomes; independently recompute in chip units with100chips/bb. Report all8
session means and predeclared Student-t95 interval over session means,df7, as
sensitivity evidence, not a replacement chosen by favorability.

## Fixed decision and limitations

Only complete valid20000hands receive a performance decision. If raw bb/100>0,
admit a separate preregistered100000fresh-hand test of this identical frozen
policy. Otherwise do not extend, reselect or pool this pilot; choose the next
general learned-weight experiment from the completed evidence. Always report
the pilot CI; a positive point alone does not establish significant victory.

The qualifying100k excludes these20k and all historical/internal hands. Goal
success still requires one frozen policy,at least100000fresh Slumbot hands,
bb/100>0 and95%CI lower>0. This pilot cannot itself fulfill that requirement.

Historical context only: strict native-sampled Standard10 scored-48.9778bb/100
on separate20k; the earlier weak-KL heads-only policy scored-55.8690 on its own
strict sampled20k. Greedy Standard10 scored-11.4275 and is a different executed
policy. None are pooled here or treated as matched causal contrasts. Internal
confirmation gains do not guarantee generalization to Slumbot.

Zero new training hands. After registration, run the adapted synthetic runner,
review and gate tests, then a zero-hand load of this experiment's exact source
snapshot before external play. Wait for all clients and the original wrapper to
exit; independently review raw evidence and close this same experiment record
before making any subsequent research decision.
