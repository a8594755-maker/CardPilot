# EXP-W1 Post-Reboot Audit — 2026-07-11

Checked: 2026-07-11T11:40:17Z

- Overall: `PASS_WAITING_EXPLICIT_USER_AUTHORIZATION`.
- Authoritative immutable lock v2 SHA256: `df8c9d61c66980d8e7103df0c8ae5523ddf1a0326d4f53b99d43699a5c8c72aa`; file is read-only.
- Exact gate31400 source checkpoint exists and SHA256 matches `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`.
- All 20 locked tool hashes match.
- Control and treatment post-reboot immutable-lock preflights each passed all 22 checks.
- Python process count: 0. V5 trainer/watcher/Slumbot process count: 0.
- Both planned W1 run directories are absent; the warmup report is absent.
- `AGENTS.md` latest-handoff paragraph was corrected from superseded v1 to authoritative v2. No historical ledger row was edited.
- Launch authority remains `NONE`; next transition requires explicit user authorization to start the control arm.
- Latest official evidence remains L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].
