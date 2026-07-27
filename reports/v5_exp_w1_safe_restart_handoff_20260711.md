# EXP-W1 Safe Restart Handoff — 2026-07-11

Checked: 2026-07-11T11:29:46Z

- State: `SAFE_PAUSE_FOR_REBOOT`.
- Launch authority: `NONE`; no trainer, watcher, cadence, promotion, formal, or Slumbot launch was performed during closure.
- Authoritative lock: `reports/v5_exp_w1_design_lock_v2_20260711.json`.
- Lock SHA256: `df8c9d61c66980d8e7103df0c8ae5523ddf1a0326d4f53b99d43699a5c8c72aa`; read-only.
- Control and treatment identity preflights: `PASS` (22 checks each).
- Both planned W1 run directories are absent; the warmup report is absent.
- v1 is preserved for audit but superseded after its watcher-gap CENSURE.
- After reboot: reread `docs/V5_CURRENT_GOAL.md` and this handoff, verify the v2 SHA and live status, and wait for explicit user authorization before any W1 launch.
- Latest official strength remains L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].