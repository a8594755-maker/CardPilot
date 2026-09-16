# Persistent Slumbot transport repair

PASS: 83 tests; actual poker hands: **0**.

Local HTTP/1.1 fixture:120 ordered POSTs over120 connections in the per-call control, versus120 identical POSTs over1 connection using the new transport. No duplicate requests or cookie carryover.

HTTP/redirect/JSON/dropped-response/refused-connection failures do not replay POSTs. Strict client execution stops before fallback or subsequent attempts and preserves completed raw rows. Legacy behavior remains opt-in by absence of the strict flag; error fallback telemetry remains auditable.

Strict manifest metadata, old evidence/CI contracts, seed tests and logger tests passed. Real Standard10 strict sample/temp1 loader passed atzero hands with unchanged model SHA. The aborted parent record and retained session artifacts have unchanged hashes.

- Loopback fixture demonstrates client reuse, not server keepalive or global port exhaustion.
- No POST retries even after ambiguous response failure; a failed fresh session remains nonqualifying.
- No strength claim or actual poker evaluation follows from offline protocol fixtures.
- Native action probabilities are unchanged; strict mode removes legacy error fallback/skip behavior.
- Redirects are explicitly refused rather than followed; cookies are not retained between API calls.

Next: separately preregister a fresh fixed20k sampled Standard10 baseline using this validated strict transport; new seeds/outputs, no pooling with the aborted4,168hands. Still not the qualifying100k goal.

[Requests Session connection pooling](https://requests.readthedocs.io/en/stable/user/advanced/)
