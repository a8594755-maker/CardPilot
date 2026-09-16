# Offline v6 external-evidence protocol diagnostic

This is an outcome-independent protocol diagnostic while the separately registered
v6 learning curve runs. It does not modify any captured training/runtime source,
perform optimization, contact Slumbot, or generate performance evidence.

Hypothesis: the current v6 external client preserves completed-hand evidence, but
may not persist ambiguous interrupted requests or enforce a sufficiently complete
terminal/session contract for a future external qualification run. Test the actual
client main/play_one control flow with an explicitly substituted toy policy and
offline server. The toy model's identity is a fixture hash, not any learned policy.
The offline server uses the existing native rules and is NOT an independent
rules oracle. Network connection attempts fail closed throughout this diagnostic.

Fixed cases: normal two hands; opponent-fold without a hero decision; first and
second new-hand failures; first and second hand action failures; noninteger
terminal reward; out-of-bounds integer terminal reward; midhand token rotation;
and a terminal response claiming winnings before its action history is terminal.
Retain every fixture call transcript, actual client raw hand file and summary,
exception class/message, hashes and source copies. No genuine access token is used.

The safety checks are exact call count/no retry, preservation of a completed prefix,
failure status/counters, successful raw arithmetic, decision replay, absence of a
plaintext token in production outputs, and runtime source immutability. Record
missing attempt/partial journals, accepted invalid terminal evidence, and missing
token-transition evidence as findings, not successful qualification tests.

All training/evaluation/Slumbot hand counts are zero. Synthetic fixture trajectories
and local test cases are separate diagnostic metrics. No policy-strength claim,
checkpoint selection, gate change or production patch is permitted here. Finish
this diagnostic with an explicit downstream readiness decision; any repair must
wait until the live curve no longer owns its captured source files.

Exact first command:
python research/experiments/v6-external-evidence-protocol-audit-20260831/run_audit.py
