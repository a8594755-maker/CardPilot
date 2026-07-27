# AlphaHoldem V5 Slumbot Takeover Handoff

Checked at: 2026-07-06 09:25 EDT  
Workspace: `C:\Users\a8594\CardPilot`

## Scope

This is the AlphaHoldem V5-from-zero Slumbot track, not the 200bb SRP CFR asset build.

Reference target: reproduce and extend AlphaHoldem, Zhao et al. AAAI 2022, for 200bb heads-up no-limit Hold'em with end-to-end RL, PPO/Trinal-Clip-style updates, K-best historical self-play, and greedy policy evaluation against Slumbot.

Final claim target:

- L5: at least 100,000 official greedy Slumbot hands, bb/100 > 0, and 95% CI lower bound > 0.
- L6: same proof gate, plus performance near the paper result, about +11.1 bb/100 versus Slumbot.

Do not claim stronger-than-V4, beats Slumbot, L5, or L6 from training health, self-play reward, internal probes, selector diagnostics, or 5k quick screens.

## Active Run

Run dir:

`C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`

Trainer PID: `56876`

Do not stop, restart, or replace the trainer just to inspect state.

Known watcher PIDs at handoff:

- dashboard watcher: `50348`
- eval cadence watcher: `41668`
- gate watcher: `7988`
- internal strength watcher: `57068`
- promotion20k watcher: `56144`
- formal100k watcher: `39752`
- checkpoint archive watcher: `38004`

## Current State Snapshot

Latest dashboard file read:

`<run_dir>\v5_dashboard_watch_status.json`

Dashboard checked_at: `2026-07-06T13:23:46.710179+00:00`

- live iteration: `8832`
- live hands: `144,919,423`
- checkpoint iteration: `8800`
- checkpoint hands: `144,394,363`
- recent throughput: `772.76 h/s`
- next gate: `8900`, `PENDING`
- next external Slumbot: `quick5k_150M`
- remaining checkpoint hands to 150M quick screen: `5,605,637`
- latest official Slumbot bb/100: `-85.037`
- Slumbot analysis coverage: `WARN_HISTORICAL_INCOMPLETE`

Latest next-action queue read:

`<run_dir>\v5_next_action_queue.json`

- queue recommendation: wait for `gate_8900`
- first item: `gate_8900`, `WAITING`
- reason: live iter `8833 < 8900`, remaining `67` iterations
- next scheduled internal probe: `internal_probe_9000`
- 150M quick5k waits for checkpoint hands `>= 150,000,000`

## Gate 8800 Review

Latest completed post-gate review:

`<run_dir>\v5_post_gate_review_8800.json`

- overall: `REVIEW_REQUIRED_NO_AUTO_RESTART`
- gate: `PASS`
- checkpoint: iter `8800`, hands `144,394,363`
- internal probe: `COMPLETED`
- internal verdict: `REGRESSION_RISK_INTERNAL`
- internal delta mean bb/100 versus 8600: `-812.125`
- internal delta lower bb/100 versus 8600: `-1039.408`
- preflop probe: `WARN`
- preflop warning count: `1`
- checkpoint delta: `LOCAL_GUARDRAILS_REGRESSED`
- strength answer: `NOT_PROVEN_STRONGER_THAN_V4`

Interpretation: gate health passed, but local strength/preflop guardrails worsened. This is not enough to restart or tune by itself. Carry it into the next intervention review together with Slumbot loss shape.

## Latest Official Slumbot Evidence

Latest complete official Slumbot result:

`models\bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_100M_quick5k_cadence_ci_summary.json`

- evidence class: quick screen
- policy mode: greedy
- hands: `5,000`
- bb/100: `-85.037`
- 95% CI: `[-129.224, -40.851]`
- promotion gate: `FAIL`
- milestone: `L0`
- not stronger than V4
- cannot support L5/L6 claim

Complete evidence bundle exists for 100M:

- CI summary JSON
- hand JSONL files
- decision dump JSONL files
- promotion gate JSON/MD
- dump analysis TXT
- loss report JSON/MD
- artifact audit JSON/MD
- hand review JSON/MD

Key 100M loss shape:

- position: SB `-115.0 bb/100`, BB `-55.0 bb/100`
- terminal: hero_fold `-167.7 bb/100`, showdown `-10.6 bb/100`, allin_runout small sample `-5454.5 bb/100`, opponent fold `+348.3 bb/100`
- first preflop losses: `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`, `bb_vs_open_lt2.5bb_c`
- rates: SB open fold/call/raise/all-in `0.327/0.506/0.167/0.000`; BB versus open call/raise `0.340/0.088`
- current hypothesis: SB first-action EV, limp-heavy/under-raised opens, BB defense/realization, and postflop/hero-fold realization

Do not tune from this quick5k alone. Use it as one signal together with preflop probes, selector diagnostics, internal probes, and health gates.

## Slumbot Analysis Backfill Completed

The user's concern was whether every Slumbot loss was analyzed. Historical coverage was incomplete. I backfilled all historical quick5k results where decision dumps still exist.

Before backfill:

- complete/total: `2/7`
- complete: 75M, 100M
- incomplete: 50M, 59M, 62M, 65M, 72M

After backfill and trend ledger refresh:

- file: `<run_dir>\v5_trend_ledger.json`
- overall: `WARN_HISTORICAL_INCOMPLETE`
- complete/total: `6/7`
- complete: 59M, 62M, 65M, 72M, 75M, 100M
- incomplete: 50M only

50M cannot be fully reconstructed because the `*_part*_dump.jsonl` decision dumps are missing. It has hand JSONL files but no decision dump, so loss report and action-level hand review cannot be trusted for tuning.

Coverage rows after refresh:

| Milestone | bb/100 | Complete | Artifact audit | Hand review | Notes |
|---:|---:|---|---|---|---|
| 50M | -76.221 | no | FAIL | INCOMPLETE | missing decision dumps and loss report |
| 59M | -58.763 | yes | PASS | PASS | backfilled |
| 62M | -82.524 | yes | PASS | PASS | backfilled |
| 65M | -73.806 | yes | PASS | PASS | backfilled |
| 72M | -122.732 | yes | PASS | PASS | regenerated old loss report and backfilled |
| 75M | -71.462 | yes | PASS | PASS | already complete |
| 100M | -85.037 | yes | PASS | PASS | already complete, latest official |

## Backfill Commands Used

For milestones with decision dumps:

```powershell
python scripts\alpha_holdem\v5_slumbot_loss_report.py `
  --dumps "models\bench_v55_<tag>_part*_dump.jsonl" `
  --label <tag> `
  --out-json "models\bench_v55_<tag>_loss_report.json" `
  --out-md "models\bench_v55_<tag>_loss_report.md"

python scripts\alpha_holdem\v5_slumbot_artifact_audit.py `
  --tag <tag> `
  --output-dir models `
  --expected-parts 4 `
  --min-parts 4 `
  --expected-hands <hands> `
  --min-hands <hands> `
  --out-json "models\bench_v55_<tag>_artifact_audit.json" `
  --out-md "models\bench_v55_<tag>_artifact_audit.md"

python scripts\alpha_holdem\v5_slumbot_hand_review.py `
  --output-dir models `
  --tag <tag> `
  --selection official `
  --policy-mode greedy `
  --out-json "models\bench_v55_<tag>_hand_review.json" `
  --out-md "models\bench_v55_<tag>_hand_review.md"
```

Trend ledger refresh:

```powershell
python scripts\alpha_holdem\v5_trend_ledger.py `
  --run-dir <run_dir> `
  --output-dir models `
  --out-json "<run_dir>\v5_trend_ledger.json" `
  --out-md "<run_dir>\v5_trend_ledger.md"
```

Important note: the first multi-milestone backfill attempt wrote logs to `tmp\backfill__loss.log`, `tmp\backfill__audit.log`, and `tmp\backfill__review.log` because of a PowerShell interpolation mistake. Those logs only preserve the last overwritten step and are not the source of truth. The source of truth is the generated JSON/MD artifacts and refreshed `v5_trend_ledger.json`.

The 72M re-run used unique logs:

- `tmp\backfill_72M_loss.log`
- `tmp\backfill_72M_audit.log`
- `tmp\backfill_72M_review.log`
- `tmp\trend_ledger_after_backfill.log`

## Next AI Checklist

1. Re-read local state before answering the user. Start with:
   - `<run_dir>\v5_dashboard_watch_status.json`
   - `<run_dir>\v5_next_action_queue.json`
   - `<run_dir>\v5_trend_ledger.json`
   - `<run_dir>\v5_eval_cadence_watch_status.json`
   - latest `gate_*_status.json`
   - latest `v5_post_gate_review_*.json`
2. Do not touch trainer PID `56876` unless the user explicitly approves a documented intervention.
3. Wait for `gate_8900`; next internal probe is `9000`.
4. Do not launch Slumbot 150M early. It launches only when saved checkpoint hands reach `150,000,000`.
5. Future Slumbot results are incomplete unless they include hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, loss report, artifact audit, and hand review.
6. If a future Slumbot result is worse, first analyze where it lost chips: SB/BB, terminal bucket, street, first preflop decision, SB open rates, BB facing-open rates, top losing lines, hole families.
7. Do not change training from bb/100 alone. Tune only when Slumbot hand review, preflop probe, selector diagnostics, internal probe, and health point to the same stable leak.
8. Official strength remains greedy versus Slumbot. Callguard/guarded/sample variants are diagnostics only.
9. 50M historical quick5k should remain historical score-only evidence because action-level data is missing.

