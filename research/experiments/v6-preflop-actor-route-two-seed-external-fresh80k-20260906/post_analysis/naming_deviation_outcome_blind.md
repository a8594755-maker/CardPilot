# Outcome-blind session-name documentation deviation

Observed after first-wave admission on 2026-09-06, before reading any aggregate
or individual winnings. At the first verified live snapshot (15:39:17 UTC), the
controller had recorded179 committed hands and all eight registered clients were
live. No outcomes were inspected to make the following decision.

The prose preregistration names session IDs
`v6_actor_route_external_20260906_{arm}_sXX`. The executable protocol, its
offline tests, prospective launch_spec and actual session commands instead use
`v6_detached_step_size_external_20260906_{arm}_sXX`. This was a mechanical
source-derivation replacement-order error: replacing "_full" before the whole
old prefix prevented the intended subsequent prefix rename.

Preserve the discrepancy, do not rewrite preregistration or any frozen source.
All32 actual IDs were fixed before the first request; they match each other in
the executable protocol, launch specification, session_commands and launched
client argv. Before launch they and all32 policy seeds passed the historical
unused-ID/seed checks over362 readable initial-session records. The prefix is a
journal identifier, not an input to the model, server-card seed or action rule.
Model hashes, arm mapping, four-wave allocation,2500hands/session, policy seeds,
CPU greedy bridge, stopping rules and statistics are unchanged.

Continue the exact already frozen32-session schedule. Do not rename, reopen,
replace or duplicate any current/future planned session. This is an explicitly
disclosed prose/executable naming deviation, not a perfectly matching prose
preregistration claim or evidence that remote RNG independence is proven.
The terminal review must bind this note and verify actual raw IDs/seeds against
the pre-request executable schedule. Full history/token/stream audits remain
required and are not waived. Controller retains sole logger ownership; attach
this deviation as a note to the same record after its exact process is terminal.

Read-only observed SHA256 bindings:

- preregistration.md: 4c9afee3c9e1f702c4601993298605acdc5fd9a2109281bc6ddeb5ffd6f65269
- pair_protocol.py: f35236e9075b975137e7423aff0daf4a3a6b343628595cc7536478578856a247
- launch_spec.json: 43d667dd1cf048a46b4f07d8a658cca3848337fad4a4dba126a3a7cb28e4cb10
- session_commands.json: 3ea281d56490418c76d7a234ab245e8f28a117afb21137dbad6f4867648369dc
