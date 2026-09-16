# Offline preparation, not an external experiment launch

`pair_protocol.py` contains only deterministic draft scheduling, command assembly
and descriptive statistics. No networking, game execution, model loading or file
writing is implemented. The draft is conditional on valid completion and research
finish of the current phase-held-reference experiment, followed by a separate
prospective external-development record binding the actual endpoint/runtime SHA.

It proposes40k/arm,16sessions/arm,2500hands/session, four balanced waves with eight
concurrent jobs maximum. Both fixed endpoints are included regardless of internal
rank. Greedy/legacy-v4 bridge is explicit. Primary contrast is moving minus static;
raw-hand Welch, session Welch, four-wave t sensitivity and Bonferroni-three
intervals are descriptive conditional on their independence assumptions. Neither
empirical zero variance nor a positive point score authorizes model selection,
100k qualification or a claim that server RNG is independent.

Actual offline command completed with16tests passing and zero poker hands:

`python -B -m pytest -q research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation/test_pair_protocol.py --junitxml=research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation/tests.xml`

The current live controller owns its experiment logger. Attach this preparation's
source, tests, XML, README and the decision note
`research/decision_notes/phase-held-external-readiness-20260905.md` to that same
record after the controller is terminal, before finish. No existing live or
historical sources were changed. Complete session/terminal/decision replay,
cross-arm/prior-token checks, both-seat reporting and runtime preflight still need
to be wired and validated in the external experiment; these16unit tests do not
establish that full evaluation readiness.

Readiness detail from the existing auditor: the frozen
`audit_journaled_slumbot_independence.py` intentionally rejects mixed model hashes.
Run it separately on each16-session arm, then add explicit cross-arm/prior token
and visible-stream checks. Do not pass all32 mixed-checkpoint sessions to it or
weaken its existing single-model invariant. Use the existing full-model auditor's
`--observation-bridge legacy-v4` argument explicitly for every replay.

## Executor preparation (still no Slumbot launch)

`run_pair.py` now wires four fixed waves, incremental complete-JSONL accounting,
file-backed hidden children, failure draining/no later wave, runtime/model SHA
binding, per-arm full greedy-bridge replay and independence audits, cross-arm/prior
tokens, cross-arm visible hero-hole streams, both-seat reporting and the draft
statistics. A preregistered `launch_spec.json` and a completed interruption-aware
training report are mandatory. Before the first client request it reruns the
SHA-bound offline tests. No launch spec or external experiment directory exists yet.

Combined tests ran three times while the executor was developed:34 passed
(`runner_tests.xml`),37 passed (`runner_tests_v2.xml`), then45 passed
(`runner_tests_v3.xml`). The45-test suite includes80k synthetic JSONL records and
a harmless real child process; these are not poker environment executions, Slumbot
hands or model queries. The later pre-client-test wiring is tested in
`runner_tests_final.xml`. Full source and all receipts must be attached to the
current record after its logger owner exits, before finish.

The actual `--preflight-only` path was also exercised against the proposed, absent
`v6-phase-reference-greedy-paired-fresh80k-20260905` directory. It refused because
the current training record was RUNNING; the directory remained absent and no
client was launched. This is an expected admission refusal, not a failed poker run.

Qualification command (repeat paths only in a new XML output if rerun):

`python -B -m pytest -q research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation/test_run_pair.py research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation/test_pair_protocol.py --junitxml=research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation/runner_tests_final.xml`
