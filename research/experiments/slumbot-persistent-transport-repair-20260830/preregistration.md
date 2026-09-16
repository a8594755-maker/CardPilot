# Offline transport repair

Parent: standard10-native-sampled-slumbot20k-20260830 was outcome-blind aborted
after a proven local connection-setup failure. Its 4,168 complete raw hands,
weights, seeds, source snapshots and closed record remain untouched. The partial
outcome is exploratory, not a completed baseline or admission to a formal test.

This experiment changes no weights, observation encoding or action probabilities.
Actual training/evaluation/Slumbot hands are zero. Local HTTP fixture requests
are protocol tests, never poker evidence.

Implement one lazy per-process Requests Session with one pooled connection,
max_retries=0, fully consumed/closed responses, no cross-request cookie retention,
default TLS verification, no redirect-following POSTs. Explicitly refuse redirects
rather than implicitly replaying a state-changing API call. A new opt-in strict
client mode aborts on any hand error, before fallback actions or a new hand, closes
files/sockets, and emits no misleading completed result. Historical default
fallback mode remains available and continues to mark unclean evidence.

Acceptance: local HTTP/1.1 server receives exactly120 application POSTs in each
arm; ordinary per-call requests.post uses120connections, pooled path uses1, with
identical ordered payload/reply values and no cookie carryover. Rejected HTTP,
redirect, malformed JSON, dropped-response and refused-connection tests must not
retry POSTs. Mocked real play_hand/main must show strict failure before fallback
or next attempt and unchanged ordinary seeded policy execution. Existing
evidence, CI, seed and logger contracts must pass. Strict manifest extension must
reject missing/mismatched raw or summary execution metadata without changing
historical manifest interpretation. Real Standard10 zero-hand loader must pass
with unchanged source SHA. Save source/patch snapshot, exact commands, test logs,
connection counts and hashes before finishing.

Limits: local reuse proves client behavior, not Slumbot server persistence or a
system-wide ephemeral-port-exhaustion diagnosis. No Windows network settings are
changed. Only after passing, separately preregister a fresh baseline with new
session seeds and immutable outputs. Never resume or pool the aborted parent.
