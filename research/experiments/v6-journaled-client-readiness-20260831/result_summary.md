# Journaled v6 client offline readiness

Decision: OFFLINE_CLIENT_EVIDENCE_READINESS. No live qualification is admitted.

The first preserved attempt passed17directed test methods covering43offline
fixture cases,248fixture requests and48synthetic terminal trajectories. The
fixtures deliberately reuse the same two seeded decks across cases; these are
not48independent deals or a policy-strength sample. The separate controlled crash
child exited17after its first intent was flushed/fsynced,leaving an auditable
pending request and no falsely completed hand.

The new client persists hash-linked intents before requests and public response
evidence before use. It does not retry,resume,overwrite,replace a failed hand,or
persist plaintext session tokens/exception messages. Exact terminal validation,
server hand counters/totals,frozen checkpoint/runtime identity,raw hand commits,
request continuity and the original shared sampled policy are enforced. Invalid
responses and disk/transport/policy failures stop with preserved evidence.

An independent journal state-machine audit checks order,hashes,counts,chip totals,
token transitions,RNG sequence and frozen-model decision replay. Tests reject
raw/summary/hash tampering,rehash-forged token/seed/probability changes,duplicate
session IDs,seeds and overlapping token chains. Distinct token chains do not
prove independence of the server's RNG; the fixture tests explicitly report that
limitation. Showdown cards or required server counters missing from a future API
response must cause a preserved failure,not a guessed result or replacement.

Post-run read-only checks verified258preserved evidence files,76own source pairs
and71unchanged source pairs of the active source-KL pilot. A separate actual CLI
invocation audited the real frozen source-policy fixture and replayed all8sampled
decisions exactly,with2fixture hands,10requests,no incomplete records and17runtime
source files verified. This added no new trajectories or poker API calls.

Real fixture identity:
944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2

Preserved evidence manifest SHA256:
784bcdba139c9f9e1e292707c12722a6f8728a91efc24beb89d5edecf0d8ce21

All new_training_hands,evaluation_hands,and slumbot_hands are0. Existing training,
inference,transport,terminal-validator and legacy-client sources were not edited.
Only the new journaled entry point,journal utility,auditor and this experiment's
helpers were added. Current live API compatibility,external strength and the
100000fresh-hand goal remain unproven. Finish the ongoing fixed policy comparison,
then require the specified independent confirmation before preregistering any
live frozen-policy evaluation; retain an outcome-independent abort rule.
