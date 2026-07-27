# V5 Control Snapshot — Before Trajectory-Native R1 Registration

Captured: 2026-07-22T17:58:25.401Z

This snapshot binds the four live control documents immediately before the clean-resume
R1 registration refresh. Their topmost state was the post-concurrency hard stop:
`NO_AUTOMATIC_SUCCESSOR_REGISTRATION_RESULT_OR_CONTROL_REFRESH`; resume was permitted
only in a new clean user/root session after rereading the state.

- `docs/V5_CURRENT_GOAL.md`: `8227fee989a52efeaa39ee168aa58b5bb8b7a68d48a84cf4b8543ef5e8b7dea5`
- `AGENTS.md`: `ace15e7ac8f1f4e4e49c61ff528bb0d323ecb73ff5f0b40a1f4c3f23b15094da`
- `reports/v5_alpha_holdem_takeover_handoff_20260711.md`: `c0bdc1dfdd2b6c1f584d27628abcc67a50358b773aee11a9d27b47c033cf4d45`
- `reports/v5_next_action_queue.md`: `e4e5db1a94952c052a0990f6675afec41abef19576f5375d33f369796f2387cf`

The immutable prior state remains in those hashes, the append-only ledger, hard-stop
CENSURE `187d4e7f...d037b`, and blanket CENSURE `f208da94...6789`. This snapshot does not
reclassify any stale artifact.
