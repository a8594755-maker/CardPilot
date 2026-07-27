# V5 75M-7500 / 100M Intervention Review

- Checked at: `2026-07-06T12:03Z`
- Active run: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- Intervention: preflop prior `0.24,0.36,0.38,0.02`, coef `0.02`
- Source checkpoint: iter `4600`, hands `75,479,020`
- Latest dashboard/queue/watchdog refresh: live iter `8644` / `141,834,522` hands, checkpoint iter `8600` / `141,112,380`, health `PASS`, latest gate pass `8600`, next gate `8700`, strength still unproven. Direct `gate_8700_status` read at `12:03Z` is still `PENDING`, live iter `8646` / `141,867,346`, with `54` live iterations and `100` checkpoint iterations remaining. `v5_post_gate_review_8600` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`, and next action remains `gate_8700`.
- Latest health/report read: trainer PID `56876` remains active. Dashboard watcher was reporting-only reloaded from PID `45616` to PID `47024`; gate watcher PID `7988`, internal watcher PID `57068`, eval cadence watcher PID `25044`, promotion20k watcher PID `56144`, formal100k watcher PID `39752`, and checkpoint archive watcher PID `38004` remain active.
- Latest gate/internal refresh: `gate_8600_status` passed at checkpoint iter `8600` / `141,112,380` hands. `internal_strength_probe_iter8600_200h` completed with verdict `MIXED_INTERNAL`: aggressive `+1416.50 bb/100` with CI about `+/-786.00`, call-station `-8.25 bb/100` with CI about `+/-15.18`, mean internal delta `+99.602`, and lower-bound delta `+254.739`. This is internal fixed-opponent evidence only; the next scheduled internal probe is `8800`.
- Latest local quality: 8600 is mixed local evidence, not a strength proof. `v5_post_gate_review_8600` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`, preflop probe `WARN` with 3 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, internal probe `COMPLETED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8500 to 8600, warning count stayed `3 -> 3`; checkpoint delta reports warning delta `0.0`. Do not restart or claim progress from this local evidence without fresh Slumbot hand-log evidence.
- Latest throughput audit/status: overall `WARN`, top-level `throughput_decision=PREPARE_SWEEP_CONTROLLED_RESTART_ONLY`, effective h/s about `631.8`, `speed_decision=WAIT_FOR_GATE_BEFORE_SPEED_CHANGE`. This still points to rollout/collection/batching rather than GPU memory or PPO/backprop, but do not run a CUDA throughput sweep concurrently with active trainer PID `56876`; review mixed 8600 internal/preflop evidence and wait for Slumbot evidence before any controlled speed or training intervention.
- Latest action-prior trend diagnostic: `v5_action_prior_trend.md` refreshed at `2026-07-05T21:40Z`, overall `PASS`, with candidate latest iteration `6664`. Active preflop call delta is `+0.0771`, preflop all-in delta is `-0.0338`, postflop raise/all-in delta is `+0.0104`, and postflop call delta is `-0.0223`. This supports that the training log action mix is not collapsing, but it is not Slumbot strength evidence and does not cancel the 6600 internal regression-risk marker.
- Runtime speed tweak: at `2026-07-05T18:42Z`, trainer PID `56876` priority was raised from `Normal` to `AboveNormal`, and Windows power plan was changed from `Balanced` to `High performance`. No model/checkpoint/training args changed and no restart was performed. A post-tweak rolling comparison did not show improvement: pre-tweak iter `6228-6286` effective h/s mean `599.0` versus post-tweak iter `6287-6310` effective h/s mean `597.6`; post-tweak inf batch mean was lower (`10.42` vs `11.55`). Keep the tweak if system stability is fine, but real speed improvement still needs a controlled workers/hands-per-iter sweep.
- Slumbot artifact check: the 75M quick5k, the 100M quick5k, and every post-cutover selector-pair policy run from `77M/4700`, `4800`, `5000`, `5100`, `5200`, `5300`, and `5800` has hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, and hand-review JSON/MD. The 100M quick5k also has selector replay JSON/MD.
- Hand-review check: `v5_slumbot_hand_review.py` produces `bench_v55_<tag>_hand_review.json/md` from CI, artifact audit, and loss report. Existing reviews use `SMOKE_ONLY_USE_AS_ONE_SIGNAL` for quick5k smoke results and `DIAGNOSTIC_ONLY_NO_AUTO_TUNE` for selector-pair diagnostics. The 4800 and 77M/4700 selector loss reports were repaired from existing dump JSONL to add required SB open call/raise/all-in rates; no Slumbot hands were rerun for that backfill.
- Trend-ledger check: `v5_trend_ledger.py` now emits both `selector_pair_history` and `official_slumbot_loss_trend`. The markdown report has `Selector Pair Diagnostic History` and `Official Slumbot Loss Trend` tables with score, CI, SB/BB split, terminal buckets, key preflop rates, audit/review status, top leak hypotheses, and `training_adjustment`. This ledger is now part of the required training-adjustment workflow.
- Official Slumbot loss-trend refresh: regenerated `<run_dir>\v5_trend_ledger.json/md` at `2026-07-06T11:14Z`. The current official rows are the 75M and 100M quick5k results, both artifact audit `PASS` and hand review present. The 100M quick5k regressed by `-13.575 bb/100` versus 75M. The loss shape shifted: SB worsened from `-36.366` to `-115.046 bb/100`, while BB improved from `-106.558` to `-55.028`, hero-fold improved from `-269.170` to `-167.737`, and showdown improved from `-795.126` to `-10.629`. Latest largest first-preflop loss buckets are `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`, `bb_vs_open_lt2.5bb_c`, and `sb_open_f`; worst hole-family losses are other offsuit, broadway offsuit, other suited, wheel-ace offsuit, and ace offsuit.
- Next-action queue hardening: `v5_next_action_queue.py` now emits `slumbot_loss_trend_latest`, and `v5_dashboard_watch.py` mirrors it into top-level dashboard status fields. Verified at `2026-07-06T11:28Z` as `WATCH`, not `REVIEW`: official loss-trend rows `2`, latest `-85.037 bb/100`, delta versus previous `-13.575`, SB/BB `-115.046/-55.028`, hero-fold/showdown `-167.737/-10.629`, and top preflop loss buckets `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`. If a future official Slumbot CI exists without matching loss trend, hand review, loss report, or artifact audit, this queue item becomes `REVIEW` before any training adjustment.
- Loss-trend queue/dashboard regression tests: added `scripts/alpha_holdem/test_v5_next_action_queue.py` covering complete loss trend, missing hand review, missing loss trend, latest-CI mismatch, and no latest CI. Added `scripts/alpha_holdem/test_v5_trend_ledger.py` covering official loss extraction/delta and missing sibling artifacts. Verification passed with `python -m py_compile scripts\alpha_holdem\v5_dashboard_watch.py scripts\alpha_holdem\v5_next_action_queue.py scripts\alpha_holdem\v5_trend_ledger.py scripts\alpha_holdem\test_v5_next_action_queue.py scripts\alpha_holdem\test_v5_trend_ledger.py`, `python scripts\alpha_holdem\test_v5_next_action_queue.py` (`5` tests OK), and `python scripts\alpha_holdem\test_v5_trend_ledger.py` (`2` tests OK). Dashboard watcher was reporting-only reloaded from PID `63460` to PID `31228` so recurring refreshes expose the loss-trend aliases.
- Dashboard completed-review alias hardening: `v5_dashboard_watch.py` now separates current pending post-gate target from latest completed post-gate review. Current status reports `post_gate_review_target=8700` / `PENDING_EVIDENCE`, while `latest_completed_post_gate_review_target=8600` / `REVIEW_REQUIRED_NO_AUTO_RESTART`, gate `PASS`, internal `COMPLETED`. Added `scripts/alpha_holdem/test_v5_dashboard_watch.py` covering latest non-pending review selection, and reloaded dashboard watcher to PID `45616`.
- Dashboard gate-alias hardening: `v5_dashboard_watch.py` now mirrors detailed next/latest gate fields to top-level dashboard status. Current status exposes `next_gate_target_iteration=8700`, `next_gate_overall=PENDING`, and the next-gate remaining live/checkpoint iterations without requiring a separate `gate_8700_status.json` read. Added `scripts/alpha_holdem/test_v5_dashboard_watch.py` coverage for gate alias extraction, and reloaded dashboard watcher to PID `47024`.
- Trend-ledger schema update: `v5_trend_ledger.json` now has top-level `overall`, `trend_direction`, `latest_official`, and `decision` fields for simple machine checks. Current top-level `overall` is `SLUMBOT_POINT_ESTIMATE_DOWN`, latest official remains the 100M quick5k `-85.037 bb/100`, and both `decision.claim_latest_is_better` and `decision.promote_strength_claim` are `false`. Dashboard watcher was restarted from PID `18644` to PID `45960` so automatic refreshes load this schema.
- Automation update: `v5_slumbot_benchmark_plan.py` now lists artifact-audit and hand-review outputs in the planned artifact manifest. `v5_slumbot_benchmark_watch.py` runs `v5_slumbot_artifact_audit.py` and `v5_slumbot_hand_review.py` after future Slumbot benchmarks and fails the benchmark result if audit or hand-review completeness fails. `v5_selector_pair_watch.py` now requires audit `PASS` and hand-review completeness before reusing existing diagnostic artifacts.
- Quick5k cadence path checked: `v5_eval_cadence_watch.py` launched `quick5k_100M` through `v5_slumbot_benchmark_watch.py` from frozen checkpoint iter `6100` / `100,091,135`. The benchmark finished `PASS` at `2026-07-05T17:49Z`; artifact audit `PASS`, hand review `PASS`, selector replay `PASS`, promotion gate `FAIL` as expected for a 5k smoke run. The next quick5k is `150M`, waiting because saved checkpoint hands are `141,112,380 < 150,000,000`; `8,887,620` checkpoint hands remain. The eval cadence watcher is PID `25044`; its status exposes top-level `WAITING_FOR_TARGET`, `next_external_eval_key=quick5k_150M`, and `next_external_eval_state=WAITING`.
- Evidence watchdog/status refresh: `v5_run_dashboard.md`, `v5_evidence_watchdog.md`, and `v5_next_action_queue.md` were refreshed through the 8600 gate window; `v5_next_action_queue.md` now recommends waiting for `gate_8700`, with `internal_probe_8800` and 150M quick5k still queued. It carries `internal_mixed_review_8600` and `preflop_guardrail_review_8600` as `WATCH` items instead of automatic restart triggers. Watchdog overall remains evidence-active/strength-unproven. The hard blocks are strength/latest-better claims because formal Slumbot evidence is insufficient and the latest quick5k point estimate regressed.
- Slumbot hand-log workflow refresh: `v5_next_action_queue.py` now states that `slumbot_quick5k_*`, `slumbot_promotion20k_*`, and `slumbot_formal100k_*` require hand JSONL, loss report, artifact audit, and hand review before any training adjustment. A 150M quick5k planner preview (`slumbot_cadence_quick5k_150M_plan_preview.json/md`) was generated while checkpoint hands were below `150,000,000`; its artifact manifest includes hands JSONL, loss report, artifact audit, and hand review outputs. Dashboard watcher PID `60456` was reloaded so recurring queue refreshes preserve this wording.
- Latest official Slumbot hand-review queue: `v5_next_action_queue.py` now emits `slumbot_hand_review_latest`, derived from the latest official CI path in `v5_trend_ledger.json`. Verified current item is `WATCH`: latest official Slumbot `5,000` hands at `-85.037 bb/100`, CI lower `-129.224`, hand review `PASS`, evidence class `quick_screen`, training adjustment `SMOKE_ONLY_USE_AS_ONE_SIGNAL`, artifact audit `PASS`. This item keeps the hand review/loss report visible before any training adjustment and will move to the 150M hand review after that result becomes latest. Dashboard watcher PID `53748` was reloaded so recurring queue refreshes preserve it.
- Slumbot hand-review claim-blocking update: `slumbot_hand_review_latest` now sets `blocks_strength_claim=true` if the latest official CI exists but hand review, loss report, or artifact audit is missing/unreadable. Current artifacts are complete, so the item remains `WATCH` with `blocks_strength_claim=false`; the formal strength claim remains blocked by the Slumbot CI rule.
- 5800 selector-pair diagnostic completed PASS from frozen checkpoint iter `5800` / `95,168,341`. Greedy scored `-115.422 bb/100` over `2,000` hands, CI lower `-211.626`; preflop-callguard scored `-89.4535 bb/100`, CI lower `-141.603`; callguard-greedy delta `+25.969`. Both policies have hand JSONL, decision dump JSONL, CI, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, and hand-review JSON/MD. This is diagnostic only and cannot support V4/L5/L6 claims.
- Watcher reload: promotion20k watcher PID `56144` and formal100k watcher PID `39752` load the audit+hand-review-aware benchmark watcher. Both remain `WAITING`; checkpoint hands `124,703,946` are below `250,000,000`.
- 100M saved-checkpoint coverage through 7600 completed. Gate extension watcher PID `7988` now covers `7100..9200`; internal extension watcher PID `57068` watches `7200..9200` with status `internal_strength_watch_7200_9200_status.json`. This avoids losing local gate/internal evidence while waiting for 150M and 250M Slumbot targets.
- Dashboard/watchdog reload: dashboard watcher PID `33836` is active after the latest post-gate alias, cutover-alias, status-alias, checkpoint/queue top-level alias, internal-verdict alias, external-eval alias, post-gate target-selection, cached preflop-probe alias, and internal-regression queue fixes. `v5_preflop_policy_probe.py` now writes top-level `checkpoint_iteration`, `checkpoint_hands`, `warning_count`, and `failure_count`; `v5_dashboard_watch.py` backfills those aliases for cached probe files. `v5_next_action_queue.py` now adds `internal_regression_review_<iter>` as a `WATCH` item when the latest internal verdict is `REGRESSION_RISK_INTERNAL`. Verified on `v5_preflop_probe_latest.json`: checkpoint `7800` / `127,985,463`, warnings `7`, failures `0`. This is reporting only and does not change trainer weights or training policy.
- Checkpoint archive recovery: checkpoint archive watcher PID `38004` is active. `v5_checkpoint_archive_watch.py` now shortens archive filenames with a run-id hash to avoid Windows long-path failures while keeping full metadata in the manifest. It successfully archived 50M and 100M milestone checkpoints from saved checkpoint iter `6200` / `101,732,149` hands into `<run_dir>\milestone_archives\`, and is now `PENDING` on the 250M milestone.

## External Evidence

| result | policy | hands | bb/100 | CI lower | note |
|---|---|---:|---:|---:|---|
| 72M official quick5k | greedy | 5,000 | -122.732 | -183.708 | pre-intervention |
| 75M selector pair | greedy | 2,000 | -155.185 | -270.447 | same source checkpoint family |
| 75M selector pair | preflop-callguard | 2,000 | -74.1915 | -162.192 | diagnostic only |
| 75M post-cutover quick5k | greedy | 5,000 | -71.462 | -136.249 | initial resume checkpoint, not yet trained under new prior |
| 77M selector pair | greedy | 2,000 | -188.911 | -306.110 | iter 4700, trained under new prior |
| 77M selector pair | preflop-callguard | 2,000 | -147.475 | -255.007 | diagnostic only, iter 4700 |
| 4800 selector pair | greedy | 2,000 | +2.0875 | -88.471 | iter 4800, diagnostic L4 point estimate only |
| 4800 selector pair | preflop-callguard | 2,000 | -105.386 | -155.119 | diagnostic only, callguard worse |
| 5000 selector pair | greedy | 2,000 | -156.5635 | -276.175 | iter 5000, diagnostic only |
| 5000 selector pair | preflop-callguard | 2,000 | -17.9765 | -110.054 | diagnostic only, callguard much better |
| 5100 selector pair | greedy | 2,000 | -116.330 | -196.988 | iter 5100, diagnostic only |
| 5100 selector pair | preflop-callguard | 2,000 | -68.9795 | -132.625 | diagnostic only, modest callguard improvement |
| 5200 selector pair | greedy | 2,000 | -121.054 | -254.009 | iter 5200, diagnostic only |
| 5200 selector pair | preflop-callguard | 2,000 | -133.748 | -236.450 | diagnostic only, callguard worse |
| 5300 selector pair | greedy | 2,000 | -38.9865 | -184.473 | iter 5300, diagnostic L1 point estimate only |
| 5300 selector pair | preflop-callguard | 2,000 | -34.3855 | -163.113 | diagnostic only, callguard only slightly better |
| 5800 selector pair | greedy | 2,000 | -115.422 | -211.626 | iter 5800, diagnostic only |
| 5800 selector pair | preflop-callguard | 2,000 | -89.4535 | -141.603 | diagnostic only, callguard helps but remains L0 |
| 100M quick5k cadence | greedy | 5,000 | -85.037 | -129.224 | iter 6100, official quick-screen L0; point estimate down vs 75M |

The post-cutover quick5k is not proof that the intervention worked. It froze the initial resume checkpoint at iter `4600`, before the new prior had meaningful training time.

## 100M Quick5k Finding

The 100M quick5k used frozen checkpoint iter `6100` / `100,091,135` hands. It completed through the guarded cadence watcher with artifact audit `PASS`, hand review `PASS`, selector replay `PASS`, and promotion gate `FAIL` as expected for a 5k smoke screen.

Score:

- Greedy official quick-screen: `-85.037 bb/100` over `5,000` hands.
- 95% CI lower / upper: `-129.224` / `-40.851`.
- Milestone: `L0`; no V4 improvement, no L5, no L6.
- Delta versus V4 point estimate: `-35.337 bb/100`.
- Delta versus 75M quick5k point estimate: `-13.575 bb/100`.

Hand-review loss shape:

- Position: SB `-115.0 bb/100`, BB `-55.0 bb/100`.
- Terminal buckets: hero_fold `-167.7 bb/100`, showdown `-10.6`, all-in runout `-5454.5` on only `11` hands, opponent-fold `+348.3`.
- First preflop decision losses: `sb_open_c` `-135.2`, `bb_vs_open_lt2.5bb_f` `-100.0`, `sb_open_raise_lt2.5bb` `-181.4`, `bb_vs_open_lt2.5bb_c` `-81.6`.
- Preflop rates: SB open fold/call/raise/all-in `0.327` / `0.506` / `0.167` / `0.000`; BB vs open call/raise `0.340` / `0.088`.
- Hole-family losses concentrate in offsuit hands: other offsuit `-98.5 bb/100`, broadway offsuit `-177.0`, wheel-ace offsuit `-221.7`, ace offsuit `-235.0`; pairs were positive at `+234.5`.

Interpretation:

- The 100M result is a regression versus the 75M quick5k and remains below the V4 point estimate. It cannot support any strength claim.
- The old pure BB zero-call leak is not the only blocker here: BB vs open call recovered to `0.340`, but the model still loses from BB and loses more from SB.
- The strongest repeated leak is SB first-action quality: too much SB limp/call, too little SB raise, and high SB open fold. This matches the 5300 context-preflop review direction.
- Large hero-fold losses and negative postflop/showdown realization remain important. Do not try to fix the result only by increasing preflop calls.
- This result justifies preparing a fresh 6100/100M-reviewed intervention plan. It does not justify an automatic restart without a reviewed, reversible plan and follow-up gates.
- Fresh review artifacts were written to `<run_dir>\v5_context_preflop_intervention_plan_6100.md` and `<run_dir>\v5_100m_intervention_review_6100.md`. The proposed test is SB-open-focused: SB-open prior coef `0.03`, target `0.15,0.20,0.63,0.02`; BB-vs-open prior remains off at coef `0.0`.

## 5800 Selector Pair Finding

The 5800 selector pair used frozen checkpoint iter `5800` / `95,168,341` hands. Both policies completed artifact audit and hand review.

Greedy result:

- Score: `-115.422 bb/100` over `2,000` hands, CI lower `-211.626`.
- SB open fold / call / raise / all-in: `0.383` / `0.005` / `0.612` / `0.000`.
- BB vs open call / raise: `0.000` / `0.455`.
- Position split: SB `-143.2 bb/100`, BB `-87.6 bb/100`.
- Main loss buckets: hero_fold `-253,687` chips, showdown `-117,877` chips.

Preflop-callguard result:

- Score: `-89.4535 bb/100` over `2,000` hands, CI lower `-141.603`.
- SB open fold / call / raise / all-in: `0.389` / `0.003` / `0.608` / `0.000`.
- BB vs open call / raise: `0.466` / `0.039`.
- Position split: SB `-118.8 bb/100`, BB `-60.1 bb/100`.
- Main loss buckets: hero_fold `-190,948` chips, showdown `-25,224` chips.

Interpretation:

- Callguard improved the point estimate by `+25.969 bb/100`, so BB call suppression is a real leak.
- The result remains far below V4 and L1. Restoring BB calls alone does not solve the model.
- SB first-action EV is still poor under both policies: SB open fold stays around `38-39%`, and SB position remains the larger loss.
- Greedy also loses heavily at showdown and hero-fold buckets, so postflop/value/realization remains a blocker.
- At 5800, the correct action was not to restart from this diagnostic alone, but to keep the current trainer running to the scheduled 100M quick5k and use that hand-review loop before any new intervention. That 100M quick5k has now completed and is summarized above.

## 75M Cutover Baseline Finding

The post-cutover quick5k still shows the core greedy selector leak:

- BB vs open call / raise: `0.000` / `0.574`
- SB open fold rate: `0.238`
- BB position: `-106.6 bb/100`
- SB position: `-36.4 bb/100`
- Showdown bucket: `-795.1 bb/100 within bucket`

Interpretation: training-time action mix improved after the restart, but the frozen iter-4600 greedy Slumbot policy still has zero BB call rate versus opens. The intervention must be judged only after at least one new checkpoint trained under the new prior.

## 77M Trained Checkpoint Finding

The 77M selector pair used frozen checkpoint iter `4700` / `77,119,719` hands, so it is the first direct check of the new preflop prior after additional training.

Greedy result:

- Score: `-188.911 bb/100` over `2,000` hands, CI lower `-306.110`.
- BB vs open call / raise: `0.221` / `0.177`.
- SB open fold rate: `0.166`.
- Position split: BB `-142.3 bb/100`, SB `-235.5 bb/100`.
- Major loss buckets: showdown `-225,373` chips, all-in runout `-280,000` chips.
- Main warning: showdown losses are `-689.2 bb/100` within the showdown bucket.

Preflop-callguard result:

- Score: `-147.475 bb/100` over `2,000` hands, CI lower `-255.007`.
- BB vs open call / raise: `0.810` / `0.023`.
- SB open fold rate: `0.154`.
- Position split: BB `-188.2 bb/100`, SB `-106.7 bb/100`.
- Main warning: showdown losses are `-857.3 bb/100` within the showdown bucket.

Interpretation:

- The original greedy BB call suppression improved: greedy BB vs open moved from `0.000` / `0.574` at 75M to `0.221` / `0.177` at 77M.
- The selector gap shrank from about `+80.993 bb/100` to `+41.436 bb/100`, but it still exists.
- Both policies are far below the V4 baseline and below L1. This is not strength improvement evidence.
- The remaining loss shape is no longer just "zero BB call"; the larger concern is postflop/showdown quality, SB losses, and costly all-in/showdown outcomes.
- Do not perform another restart from this 2k diagnostic alone. Continue to the next scheduled checkpoint/eval unless a repeated structural leak is confirmed by 4800/internal probe or the 100M quick screen.

## 4800 Follow-Up Finding

The 4800 selector pair used frozen checkpoint iter `4800` / `78,760,653` hands.

Greedy result:

- Score: `+2.0875 bb/100` over `2,000` hands, CI lower `-88.471`, CI upper `92.646`.
- This is a diagnostic L4 point estimate only. It is not proof of V4 improvement, L5, L6, or Slumbot-positive strength.
- BB vs open call / raise: `0.106` / `0.214`.
- SB open fold rate: `0.274`.
- Position split: BB `-41.9 bb/100`, SB `+46.0 bb/100`.
- Terminal buckets: hero_fold `-225,050` chips, opponent_fold `+214,544` chips, showdown `+34,681` chips, all-in runout `-20,000` chips.
- Loss-report warnings: none.

Preflop-callguard result:

- Score: `-105.386 bb/100` over `2,000` hands, CI lower `-155.119`, CI upper `-55.653`.
- BB vs open call / raise: `0.779` / `0.012`.
- SB open fold rate: `0.258`.
- Position split: BB `-139.4 bb/100`, SB `-71.4 bb/100`.
- Terminal buckets: hero_fold `-222,330` chips, opponent_fold `+100,268` chips, showdown `-68,710` chips, all-in runout `-20,000` chips.
- Main warning: showdown hands lost `-68,710` chips.

Interpretation:

- Greedy improved sharply from the 77M diagnostic and is the first positive Slumbot point estimate in this sequence.
- The confidence interval is still very wide and negative on the lower bound, so the result is not a strength claim.
- Greedy BB defense is still fold-heavy relative to a robust defend strategy, but the 4800 loss shape is no longer dominated by the same postflop/showdown collapse seen at 77M.
- Callguard-greedy delta is `-107.473 bb/100`, so forcing calls is harmful at this checkpoint.
- Official policy must remain greedy. Callguard is only a leak-localization tool and should not be promoted.
- Do not restart from the 4800 2k diagnostic alone. Keep training to the 100M quick screen and the 5000 internal/gate checks. Consider a 20k promotion-style screen only if 100M is positive or another scheduled check confirms the signal.

## 4900 Local Gate Finding

Checkpoint iter `4900` / `80,401,836` hands passed the local gate:

- Gate 4900: `PASS`.
- Health: `PASS`.
- Entropy: about `1.405` at gate refresh.
- Value loss: about `3145.9` at gate refresh.
- Pool snapshots: `5`.
- Environment/action-space lineage: `v55`, `9slot_v5`, fresh-from-zero lineage intact.

The 4900 preflop probe is still `WARN`, but the warning shape changed:

- SB open start greedy: fold `0.274`, call/limp `0.608`, raise `0.118`, all-in `0.000`.
- BB vs min-open greedy: fold `0.414`, call `0.468`, raise `0.118`, all-in `0.000`.
- BB vs 3bb open greedy: fold `0.324`, call `0.459`, raise `0.217`, all-in `0.000`.
- SB facing 3-bet greedy: fold `0.680`, call `0.183`, raise `0.137`, all-in `0.000`.

Delta versus 4800:

- Mean greedy fold delta `-0.174`.
- Mean greedy call delta `+0.336`.
- Mean greedy raise delta `-0.162`.
- Warning count stayed `2`.

Interpretation:

- The 4800 BB overfold warning improved materially by 4900; BB defend now has much more greedy call frequency.
- The new local concern is SB open quality: greedy overlimps and underraises at first action.
- This is mixed local evidence only. It does not prove V4 improvement or Slumbot strength.
- Do not restart from 4900 local probes. Keep training to 5000 internal/gate and the 100M Slumbot quick screen.
- The Slumbot loss report now exposes SB open fold / limp-call / raise / all-in rates, so the 100M hand-log review should verify whether this SB-open leak appears against Slumbot.

## 5000 Gate/Internal Finding

Checkpoint iter `5000` / `82,042,477` hands passed the local gate:

- Gate 5000: `PASS`.
- Health: `PASS`.
- Entropy: `1.3572`.
- Value loss: `2700.6792`.
- Pool snapshots: `5`.
- Environment/action-space lineage: `v55`, `9slot_v5`, fresh-from-zero lineage intact.

The 5000 internal strength probe completed, but it is a regression-risk signal, not a Slumbot strength claim:

- Probe size: `200` hands per opponent.
- Latest checkpoint vs call-station: `-879.465 bb/100`, CI lower `-1570.222`.
- Latest checkpoint vs aggressive: `+99.000 bb/100`, CI lower `-636.257`.
- Mean latest internal result: `-390.233 bb/100`.
- Previous 4800 mean internal result: `+59.420 bb/100`.
- Delta versus previous internal probe: `-449.653 bb/100`.
- Internal verdict: `REGRESSION_RISK_INTERNAL`; dashboard overall: `WORSE_THAN_PREVIOUS_INTERNAL`.

Interpretation:

- The checkpoint is structurally healthy and valid, but local/internal strength evidence got worse from 4800 to 5000.
- Internal probes are very small and noisy; they do not prove Slumbot regression or justify a restart by themselves.
- Because the 4800 Slumbot diagnostic was positive but 5000 internal evidence is weak, a 5000 paired Slumbot selector diagnostic was launched from a frozen iter-5000 checkpoint.
- Do not tune from the 5000 internal probe alone. Wait for the 5000 selector-pair hand/loss report and the staged 100M quick screen before another intervention.

## 5000 Selector Pair Finding

The 5000 selector pair used frozen checkpoint iter `5000` / `82,042,477` hands.

Greedy result:

- Score: `-156.5635 bb/100` over `2,000` hands, CI lower `-276.175`, CI upper `-36.952`.
- BB vs open call / raise: `0.000` / `0.343`.
- SB open fold / call / raise / all-in: `0.519` / `0.000` / `0.481` / `0.000`.
- Position split: BB `-73.1 bb/100`, SB `-240.0 bb/100`.
- Terminal buckets: all-in runout `-260,000` chips, hero_fold `-232,792` chips, showdown `-215,639` chips, opponent_fold `+395,304` chips.
- Warnings: high SB open fold, BB vs open call rate `0.0%`, and large showdown loss.

Preflop-callguard result:

- Score: `-17.9765 bb/100` over `2,000` hands, CI lower `-110.054`, CI upper `74.101`.
- BB vs open call / raise: `0.540` / `0.026`.
- SB open fold / call / raise / all-in: `0.521` / `0.000` / `0.479` / `0.000`.
- Position split: BB `-54.7 bb/100`, SB `+18.7 bb/100`.
- Terminal buckets: hero_fold `-207,922` chips, showdown `-136,674` chips, all-in runout `-60,000` chips, opponent_fold `+368,643` chips.
- Warnings: high SB open fold and showdown losses.

Interpretation:

- The 4800 positive greedy diagnostic did not repeat at 5000.
- The greedy BB-defense leak returned: BB vs open call rate is again `0.000`.
- Callguard improved the point estimate by `+138.587 bb/100`, mainly by restoring BB calls and recovering SB position EV, but it did not prove strength because the CI lower bound is still negative and showdown remains weak.
- This confirms a preflop selector/training-shape leak strongly enough to prepare a reviewed intervention plan, but not enough to claim Slumbot progress or promote callguard as official policy.

## 5100 Selector Pair Finding

The 5100 selector pair used frozen checkpoint iter `5100` / `83,683,550` hands.

Greedy result:

- Score: `-116.330 bb/100` over `2,000` hands, CI lower `-196.988`.
- BB vs open call / raise: `0.275` / `0.117`.
- SB open fold / call / raise / all-in: `0.370` / `0.435` / `0.195` / `0.000`.
- Position split: BB `-93.4 bb/100`, SB `-139.3 bb/100`.
- Terminal buckets: hero_fold `-218,513` chips, showdown `-192,734` chips, all-in runout `-80,000` chips, opponent_fold `+258,587` chips.
- Warnings: high SB open fold, low SB open raise, and large showdown loss.

Preflop-callguard result:

- Score: `-68.9795 bb/100` over `2,000` hands, CI lower `-132.625`.
- BB vs open call / raise: `0.645` / `0.025`.
- SB open fold / call / raise / all-in: `0.359` / `0.445` / `0.196` / `0.000`.
- Position split: BB `+7.0 bb/100`, SB `-144.9 bb/100`.
- Terminal buckets: hero_fold `-253,646` chips, showdown `-121,998` chips, all-in runout `-40,000` chips, opponent_fold `+277,685` chips.

Interpretation:

- The 5000 pure BB zero-call leak did not repeat. Greedy BB vs open call recovered from `0.000` to `0.275`.
- The main visible preflop issue shifted to SB first action: too much fold/limp and too little raise.
- Callguard still improves the 2k point estimate by `+47.351 bb/100`, but the gap is smaller than 5000 and remains diagnostic only.
- The 5000 global-prior restart plan is stale. A single global "more call" target would conflict with the 5100 SB-open issue.
- The next preflop intervention, if chosen, should be context-conditioned: SB-open prior separate from BB-vs-open prior.
- A new reviewed plan exists at `<run_dir>\v5_context_preflop_intervention_plan_5100.md` with overall `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`. It has not been executed.

## 5200 Selector Pair Finding

The 5200 selector pair used frozen checkpoint iter `5200` / `85,324,274` hands.

Greedy result:

- Score: `-121.054 bb/100` over `2,000` hands, CI lower `-254.009`, CI upper `+11.901`.
- BB vs open call / raise: `0.000` / `0.561`.
- SB open fold / call / raise / all-in: `0.099` / `0.001` / `0.900` / `0.000`.
- Position split: BB `-100.0 bb/100`, SB `-142.1 bb/100`.
- Terminal losses: hero_fold `-330,954` chips, showdown `-301,417`, all-in runout `-200,000`.
- Opponent folds gained `+590,263` chips.

Preflop-callguard result:

- Score: `-133.748 bb/100` over `2,000` hands, CI lower `-236.450`, CI upper `-31.046`.
- BB vs open call / raise: `0.506` / `0.112`.
- SB open fold / call / raise / all-in: `0.126` / `0.001` / `0.873` / `0.000`.
- Position split: BB `-100.4 bb/100`, SB `-167.1 bb/100`.
- Terminal losses: hero_fold `-296,444` chips, showdown `-278,177`, all-in runout `-140,000`.
- Opponent folds gained only `+447,125` chips.

Interpretation:

- The greedy BB zero-call leak returned at 5200, but callguard was not an improvement this time.
- Callguard restored BB call frequency, reduced some fold/showdown/all-in losses, but lost more overall because opponent-fold gains fell by about `143,138` chips and SB performance got worse.
- This means the 5200 evidence does not justify a simple "more BB call" intervention or promoting callguard.
- A new 5200 intervention plan was generated at `<run_dir>\v5_context_preflop_intervention_plan_5200.md`; overall `STRICT_GATE_PASS_REVIEW_REQUIRED`, not `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`.
- The 5100 context-preflop plan should not be executed blindly after the 5200 pair; the leak shape changed again.

## 5300 Selector Pair Finding

The 5300 selector pair used frozen checkpoint iter `5300` / `86,965,097` hands.

Greedy result:

- Score: `-38.9865 bb/100` over `2,000` hands, CI lower `-184.473`, CI upper `106.500`.
- BB vs open call / raise: `0.017` / `0.463`.
- SB open fold / call / raise / all-in: `0.328` / `0.017` / `0.655` / `0.000`.
- Position split: BB `+149.4 bb/100`, SB `-227.3 bb/100`.
- Main terminal losses: showdown `-255,374` chips, hero_fold `-252,152`, all-in runout `-100,000`.

Preflop-callguard result:

- Score: `-34.3855 bb/100` over `2,000` hands, CI lower `-163.113`, CI upper `94.342`.
- BB vs open call / raise: `0.740` / `0.057`.
- SB open fold / call / raise / all-in: `0.349` / `0.022` / `0.629` / `0.000`.
- Position split: BB `+27.3 bb/100`, SB `-96.1 bb/100`.
- Main terminal losses: showdown `-376,304` chips, hero_fold `-171,473`, all-in runout `-60,000`.

Interpretation:

- The 5300 local preflop guardrail improvement partially transferred to Slumbot point estimate, but the 2k CI is too wide for any strength claim.
- Callguard only improved the 2k point estimate by `+4.601 bb/100`; this is not enough to justify promoting callguard or forcing BB calls.
- The dominant remaining problems are SB EV, showdown/postflop value, and unstable BB facing-open strategy. The 5300 context plan should be reviewed, not executed automatically.

## 5400 Local Gate/Internal Finding

Checkpoint iter `5400` / `88,605,809` hands passed the local gate:

- Gate 5400: `PASS`.
- Health: `PASS`; stderr empty.
- Entropy near gate: `1.3383` at live iter `5401`; latest read after gate was iter `5405`, entropy `1.3288`.
- Value loss near gate: `2651.7` at live iter `5401`; latest read after gate was `2369.6`.
- Pool snapshots: `5`.
- Environment/action-space lineage: `v55`, `9slot_v5`, fresh-from-zero lineage intact.

The 5400 local preflop probe regressed:

- 5300 preflop probe: `PASS`.
- 5400 preflop probe: `WARN`.
- Warning delta: `+7`.
- Dashboard quality: `PREFLOP_GUARDRAIL_WARN`.

The 5400 internal strength probe completed, but it is a regression-risk signal only:

- Probe size: `200` hands per opponent.
- Latest checkpoint vs call-station: `+101.31 bb/100`, CI `+/-189.10`.
- Latest checkpoint vs aggressive: `-1079.25 bb/100`, CI `+/-1381.37`.
- Mean latest internal result: `-488.970 bb/100`.
- Delta versus 5200 internal mean: `-426.543 bb/100`.
- Latest-best: `0/2`.
- Internal verdict: `REGRESSION_RISK_INTERNAL`.

Interpretation:

- 5400 is a valid checkpoint, but local quality regressed after the 5300 improvement.
- This is not a Slumbot result and not enough to claim that the model is weaker or stronger than V4.
- Do not restart from 5400 local regression alone. Verify whether the same leak persists at 5500/5600 and in the scheduled 100M Slumbot quick screen with hand-log loss reports.

## 5500 Local Gate Finding

Checkpoint iter `5500` / `90,246,780` hands passed the local gate:

- Gate 5500: `PASS`.
- Health: `PASS`; stderr empty.
- Live health at refresh: iter `5503`, hands `90,295,976`, entropy `1.357`, reward100 `+0.045`.
- Environment/action-space lineage remains `v55`, `9slot_v5`, fresh-from-zero lineage intact.

The 5500 preflop probe remains a warning, but improved versus 5400:

- 5400 preflop probe: `WARN`, `7` warnings.
- 5500 preflop probe: `WARN`, `4` warnings.
- Checkpoint delta: `LOCAL_GUARDRAILS_MIXED`.
- Main remaining issue: greedy argmax suppresses preflop calls even when mean call probability is around `0.28-0.30`.
- SB open greedy rates: fold `0.247`, call `0.000`, raise `0.753`, all-in `0.000`.
- BB versus min-open greedy rates: fold `0.179`, call `0.000`, raise `0.821`, all-in `0.000`.
- BB versus 3bb open greedy rates: fold `0.213`, call `0.001`, raise `0.786`, all-in `0.000`.
- SB versus 3-bet greedy rates: fold `0.259`, call `0.000`, raise `0.741`, all-in `0.000`.

Interpretation:

- 5500 reduces the local warning count versus 5400, but it does not remove the selector-margin problem.
- This is still not Slumbot evidence and does not prove improvement over V4.
- Do not restart from 5500 alone. The next useful local evidence is `gate_5600` plus the 5600 internal probe; the next external evidence remains the 100M quick5k with hand-log and loss-report review.

## 5600 Local Gate/Internal Finding

Checkpoint iter `5600` / `91,887,151` hands passed the local gate:

- Gate 5600: `PASS`.
- Health: `PASS`; stderr empty.
- Live status around dashboard refresh: iter `5604`, hands `91,952,832`.
- Latest direct train row after refresh: iter `5605`, hands `91,969,219`, h/s `1046`.
- Environment/action-space lineage remains `v55`, `9slot_v5`, fresh-from-zero lineage intact.

The 5600 internal fixed-opponent probe improved, but it is not Slumbot evidence:

- Probe size: `200` hands per opponent.
- Versus call-station: `+60.66 bb/100`, CI `+/-230.27`.
- Versus aggressive: `+1607.50 bb/100`, CI `+/-1269.08`.
- Mean latest: `+834.080 bb/100`; mean lower: `+84.407`.
- Delta versus 5400 internal: `+1323.050 bb/100`.
- Verdict: `MIXED_INTERNAL`; latest-best `1/2`.

The 5600 preflop probe regressed versus 5500:

- 5500 preflop probe: `WARN`, `4` warnings.
- 5600 preflop probe: `WARN`, `5` warnings.
- Checkpoint delta: `LOCAL_GUARDRAILS_REGRESSED`.
- Greedy preflop calls remain suppressed in SB open, BB versus min-open, BB versus 3bb open, and SB versus 3-bet contexts.

Interpretation:

- 5600 is healthy and locally better on the tiny internal probe, but it is still not Slumbot evidence.
- The local preflop guardrail got worse from 5500 to 5600.
- Do not restart or tune from 5600 alone. Wait for the next local gate/internal cadence and the scheduled 100M quick5k with hand-log, loss-report, artifact-audit, trend-ledger, and hand-review checks.

## Current Decision

- Keep the active intervention run running.
- Do not claim V4 improvement, L1, L5, or L6.
- Do not tune again from the 77M, 4800 selector pair, 4900 local gate, or 5000 internal probe alone.
- Treat the preflop prior intervention as unstable and currently back in WARN: 5300 preflop probe was `PASS`, 5400 regressed to `WARN`, 5500 remained `WARN` with fewer warnings, 5600 regressed to `5` warnings, 5700/5900/6000 stayed `WARN`, 6200 was still `WARN`, 6500 remained `WARN` with 4 warnings, 6600 remained `WARN` with 3 warnings, 7400 improved to 1 warning, 7500 regressed to 4 warnings, 7600 improved to 2 warnings, 7700 regressed to 7 warnings, 7800 stayed at 7 warnings, 7900 improved to `PASS` with 0 warnings, 8000 regressed to `WARN` with 7 warnings, 8100 improved only to `WARN` with 6 warnings, 8200 improved further to `WARN` with 2 SB-open warnings, 8300 regressed to `WARN` with 4 warnings, 8400 improved to `PASS` with 0 warnings, 8500 regressed to `WARN` with 3 warnings, and 8600 stayed `WARN` with 3 warnings. The 5300/5800 Slumbot diagnostics and 100M quick5k still show SB EV, BB realization, and hero-fold/postflop issues.
- The older global-prior intervention plan `v5_preflop_intervention_plan.md`, the 5100/5200 context plans, the 5300 context review, and the 6100/6400/6500 context plans are superseded for current review by `v5_context_preflop_intervention_plan_6600.md` plus the existing `v5_100m_intervention_review_6100.md` hand-log overlay.
- The newest completed review artifacts are `v5_context_preflop_intervention_plan_6600.md`, `v5_post_gate_review_8600.md`, `internal_strength_probe_iter8600_200h.md`, and `v5_100m_intervention_review_6100.md`. The 6600 context plan reports `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, but dashboard/cutover remains `HOLD_NO_CUTOVER`. Current next action queue recommends waiting for `gate_8700`; the next scheduled internal probe is `internal_probe_8800`.
- Do not execute any planned restart automatically. The 100M quick5k hand review is strong enough to justify a new intervention review, but a restart still needs a reversible plan that accounts for SB first-action, BB realization, and postflop/hero-fold losses together.
- Watch for repeated postflop/showdown, BB-defense, SB leaks, and preflop guardrail regressions in 8600 local/internal evidence and the next staged 150M Slumbot quick screen.
- Throughput is being watched separately from strength. `v5_throughput_sweep_plan.md` is `READY_WITH_WARNINGS` and proposes workers `24/28/32` with hands-per-iter `16384/32768`, but it warns the source trainer is still alive. Do not run CUDA sweeps concurrently with the main trainer; use them only in a controlled restart/cutover window and compare with `v5_throughput_compare.py`.
- The old dedicated `slumbot_quick5k_launch` watcher finished the 75M quick5k and exited. The next quick screen is handled by `v5_eval_cadence_watch.py` PID `25044`; it successfully launched and completed `quick5k_100M`. The next quick target is 150M and the watcher status is `WAITING_FOR_TARGET`. `PREFLOP_GUARDRAIL_WARN` is non-blocking for quick5k smoke benchmarks, but remains blocking for promotion20k/formal100k.
- Dashboard watcher remains active as PID `48156` after a reporting-only reload that preserves `preflop_guardrail_review_8000`, Slumbot hand-log/hand-review requirements, `slumbot_hand_review_latest`, and hand-review artifact claim-blocking in the next-action queue. Trainer PID `56876` was not restarted.
- `gate_8500_status` passed at checkpoint iter `8500` / `139,471,247` hands with health `PASS`.
- `v5_post_gate_review_8500.md` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: internal probe `NOT_SCHEDULED`, latest internal verdict remains `8400 REGRESSION_RISK_INTERNAL`, preflop probe `WARN` with 3 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength still `NOT_PROVEN_STRONGER_THAN_V4`.
- `v5_cutover_decision.py` was corrected to choose the latest `v5_context_preflop_intervention_plan_*.json` before falling back to `v5_preflop_intervention_plan.json`. It now reports intervention `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, target `6600`, source `v5_context_preflop_intervention_plan_6600.json`, with decision `HOLD_NO_CUTOVER` and recommendation to collect stronger internal or Slumbot evidence first.
- `v5_evidence_watchdog.py` was corrected to choose the latest `slumbot_selector_pair_*_status.json` instead of the old hardcoded 75M path. It now reports the 5800 selector pair as latest: frozen checkpoint iter `5800` / `95,168,341`, callguard-greedy delta `+25.969`.
- 5300 local gate completed `PASS` at checkpoint iter `5300` / `86,965,097` hands. Preflop probe improved from 5200 `WARN` with 4 warnings to 5300 `PASS` with 0 warnings; dashboard quality is now `SLUMBOT_CANDIDATE_ONLY`. This is a local guardrail improvement, not evidence that V5 is stronger than V4 or close to L6.
- 5300 paired selector diagnostic completed `PASS`. Frozen checkpoint iter `5300` / `86,965,097`; greedy `-38.9865 bb/100` over `2,000` hands, CI lower `-184.473`; preflop-callguard `-34.3855 bb/100`, CI lower `-163.113`; callguard-greedy delta `+4.601`. This is diagnostic-only and cannot support L5/L6 claims.
- 5300 loss shape: local preflop probe improved, but Slumbot still shows SB and showdown leaks. Greedy position split was BB `+149.4 bb/100`, SB `-227.3`; callguard was BB `+27.3`, SB `-96.1`. Showdown lost `-255,374` chips for greedy and `-376,304` chips for callguard. Greedy BB vs open call/raise remained `0.017` / `0.463`; callguard restored BB call to `0.740` but only improved score by `+4.601 bb/100`.
- A 6600 context preflop plan was generated at `<run_dir>\v5_context_preflop_intervention_plan_6600.md`, with the 100M hand-log overlay still at `<run_dir>\v5_100m_intervention_review_6100.md`. It recommends reviewing SB first-action separately from BB facing-open behavior. Dashboard/cutover decision remains `HOLD_NO_CUTOVER`; after the 8600 gate/internal review, next action queue recommends waiting for `gate_8700` and `internal_probe_8800` while considering the reviewed SB-open-focused test. Do not restart from 6600, 6700, 6800, 6900, 7000, 7100, 7200, 7300, 7400, 7500, 7600, 7700, 7800, 7900, 8000, 8100, 8200, 8300, 8400, 8500, or 8600 local evidence alone.

## Follow-Up Watchers

- 77M paired selector diagnostic completed PASS:
  - Status file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_77M_status.md`
  - Greedy: `-188.911 bb/100`
  - Preflop-callguard: `-147.475 bb/100`
  - Delta: `+41.436 bb/100`
- 4800 paired selector diagnostic completed:
  - Status file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_4800_status.md`
  - Log: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_4800_watch.log`
  - Greedy: `+2.0875 bb/100`
  - Preflop-callguard: `-105.386 bb/100`
  - Delta: `-107.473 bb/100`
- 5000 gate/internal probe completed:
  - Gate: `PASS` at iter `5000` / `82,042,477` hands.
  - Internal probe: `REGRESSION_RISK_INTERNAL`, mean latest `-390.233 bb/100`, delta versus previous `-449.653 bb/100`.
- 5000 paired selector diagnostic launched from frozen checkpoint:
  - Status file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5000_status.md`
  - Log: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5000_watch.log`
  - Greedy: `-156.5635 bb/100`
  - Preflop-callguard: `-17.9765 bb/100`
  - Delta: `+138.587 bb/100`
- 5000 reviewed preflop intervention plan generated:
  - Plan file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\v5_preflop_intervention_plan.md`
  - Overall: `PREFLOP_INTERVENTION_REVIEW_REQUIRED`
  - Proposed preflop prior: coef `0.03`, target `0.20,0.46,0.32,0.02`
- 5100-6000 gate watcher and 5200-6000 internal strength watcher completed; extension gate watcher covers `6100..7000`, and extension internal strength watcher covers `6200,6400,6600,6800,7000`.
- 5100 paired selector diagnostic completed:
  - Status file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5100_status.md`
  - Log: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5100_watch.log`
  - Greedy: `-116.330 bb/100`
  - Preflop-callguard: `-68.9795 bb/100`
  - Delta: `+47.351 bb/100`
- 5100 context-preflop intervention plan generated:
  - Plan file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\v5_context_preflop_intervention_plan_5100.md`
  - Overall: `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`
  - Planned SB-open prior: coef `0.02`, target `0.15,0.20,0.63,0.02`
  - Planned BB-vs-open prior: coef `0.0`, target `0.25,0.55,0.18,0.02`
- 5200 paired selector diagnostic completed:
  - Status file: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5200_status.md`
  - Log: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1\slumbot_selector_pair_5200_watch.log`
  - PID at launch: `58232`
  - State at launch: `WAITING`; checkpoint hands `83,683,550` below required `85,300,000`
  - Final state: `PASS`; frozen checkpoint iter `5200` / `85,324,274` hands
  - Greedy policy completed: `-121.054 bb/100` over `2,000` hands, CI lower `-254.009`, L0.
  - Preflop-callguard completed: `-133.748 bb/100` over `2,000` hands, CI lower `-236.450`, L0.
  - Callguard-greedy delta: `-12.694 bb/100`.
  - Greedy loss report: SB open fold/call/raise/all-in `0.099` / `0.001` / `0.900` / `0.000`; BB vs open call/raise `0.000` / `0.561`.
  - Greedy terminal leaks: hero_fold `-330,954` chips, showdown `-301,417`, all-in runout `-200,000`, opponent_fold `+590,263`.
  - Callguard loss report: SB open fold/call/raise/all-in `0.126` / `0.001` / `0.873` / `0.000`; BB vs open call/raise `0.506` / `0.112`.
  - Callguard terminal leaks: hero_fold `-296,444` chips, showdown `-278,177`, all-in runout `-140,000`, opponent_fold `+447,125`.
- 5400 gate/internal probe completed:
  - Gate: `PASS` at iter `5400` / `88,605,809` hands.
  - Local preflop probe: `WARN`; warning delta `+7` versus 5300.
  - Internal probe: `REGRESSION_RISK_INTERNAL`, mean latest `-488.970 bb/100`, delta versus 5200 internal `-426.543 bb/100`, latest-best `0/2`.
  - Opponent split: call-station `+101.31 bb/100`; aggressive `-1079.25 bb/100`.
- 5500 gate completed `PASS` at iter `5500` / `90,246,780` hands.
- 5600 gate/internal probe completed:
  - Gate: `PASS` at iter `5600` / `91,887,151` hands.
  - Local preflop probe: `WARN`; warning count increased from `4` at 5500 to `5`.
  - Checkpoint delta: `LOCAL_GUARDRAILS_REGRESSED`.
  - Internal probe: `MIXED_INTERNAL`, mean latest `+834.080 bb/100`, mean lower `+84.407`, delta versus 5400 internal `+1323.050 bb/100`, latest-best `1/2`.
- 5700 gate completed:
  - Gate: `PASS` at iter `5700` / `93,527,695` hands.
  - Local preflop probe: `WARN`; warning count stayed at `5`.
  - Checkpoint delta: `LOCAL_GUARDRAILS_MIXED`.
  - Greedy preflop calls are still suppressed to `0.000` in SB open, BB facing open, and SB facing 3-bet contexts; BB versus min-open greedy fold is `0.650`.
  - This is local guardrail evidence only and cannot prove V4/L5/L6 strength.
- 5800 paired selector diagnostic completed:
  - Greedy: `-115.422 bb/100` over `2,000` hands, CI lower `-211.626`, L0.
  - Preflop-callguard: `-89.4535 bb/100` over `2,000` hands, CI lower `-141.603`, L0.
  - Delta: `+25.969 bb/100`; diagnostic only. Hand JSONL, decision dump JSONL, CI, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, and hand-review JSON/MD all exist.
- 5900 gate completed:
  - Gate: `PASS` at iter `5900` / `96,809,187` hands.
  - Local preflop probe: `WARN`; checkpoint delta remained `LOCAL_GUARDRAILS_MIXED`.
  - This is local guardrail evidence only and did not justify restart.
- 6000 gate/internal probe completed:
  - Gate: `PASS` at iter `6000` / `98,450,386` hands.
  - Local preflop probe: `WARN`; checkpoint delta remained `LOCAL_GUARDRAILS_MIXED`.
  - Internal probe: `MIXED_INTERNAL`, mean latest `+362.500 bb/100`, mean lower `-378.114`, delta versus 5800 internal `+465.785`, latest-best `1/2`.
  - This is internal-only evidence and cannot prove V4/L5/L6 strength. It did not justify a restart from 6000 alone; the next evidence at that time was `gate_6100`, the 6200 internal probe, and the 100M quick5k hand-review loop.
- 6100 gate and 100M quick5k completed:
  - Gate: `PASS` at iter `6100` / `100,091,135` hands.
  - Quick5k: `-85.037 bb/100` over `5,000` hands, CI lower `-129.224`, L0.
  - Artifact audit, hand review, and selector replay all passed. Promotion gate failed as expected for 5k hands and negative score.
  - Loss shape: SB first-action EV is the largest visible leak, BB realization is still negative, and hero-fold/postflop realization remains costly.
  - This is external regression evidence, not a promotion claim. Prepare a fresh 6100/100M intervention review; do not restart automatically from score alone.
- 6200 gate/internal probe completed:
  - Gate: `PASS` at iter `6200` / `101,732,149` hands.
  - Local preflop probe: `WARN`; warning count improved from `2` to `1`, but the remaining warning is SB open overlimp with greedy fold/call/raise/all-in `0.058` / `0.637` / `0.305` / `0.000`.
  - Checkpoint delta: `LOCAL_GUARDRAILS_MIXED`.
  - Internal probe: `MIXED_INTERNAL`, mean latest `+697.000 bb/100`, mean lower `+74.355`, delta versus 6000 internal `+334.500`, latest-best `1/2`.
  - Opponent split: call-station `+87.00 bb/100`, aggressive `+1307.00 bb/100`.
  - This is internal/local evidence only. It reinforces the SB-open review direction but cannot prove V4/L5/L6 strength and does not justify an automatic restart.
- 6353 live status and dashboard evidence fields:
  - Live training remained healthy at iter `6353` / `104,242,582` hands; `gate_6400` was still pending.
  - Dashboard watcher was reloaded as PID `54152` after adding direct trend-decision fields.
  - `v5_dashboard_watch_status.json` and `v5_l6_status_brief.json` now expose latest official Slumbot hands/bb100/CI lower and the two decision flags.
  - Current external evidence remains `5000` hands, `-85.037 bb/100`, CI lower `-129.224`, `claim_latest_is_better=False`, `promote_strength_claim=False`, `SLUMBOT_POINT_ESTIMATE_DOWN`.
- 6400 post-gate review automation:
  - Added `scripts\alpha_holdem\v5_post_gate_review.py` and integrated it into `v5_dashboard_watch.py`.
  - Dashboard now writes `<run_dir>\v5_post_gate_review_6400.json/md` every refresh.
  - Current review status is `PENDING_EVIDENCE`: `gate_6400=PENDING`, `internal_probe_6400=PENDING`, and formal Slumbot claim remains blocked.
  - Live training at the verified refresh was iter `6367` / `104,472,317` hands, health `PASS`.
  - Dashboard watcher was reloaded as PID `19348`; trainer PID `56876` was not restarted.
- Next-action queue integration:
  - `v5_next_action_queue.py` now adds `post_gate_review_6400` after `internal_probe_6400`.
  - Current status is `WAITING`, ETA about `12m`, and it blocks strength claims.
  - Reason: wait for `gate_6400` and `internal_probe_6400`; no restart or strength claim.
  - Dashboard watcher was reloaded as PID `46408`; trainer PID `56876` was not restarted.
- Dashboard refresh-order fix:
  - `v5_dashboard_watch.py` now writes `v5_post_gate_review_6400.json/md` before rebuilding `v5_next_action_queue.json/md`.
  - This prevents the queue from reading a stale post-gate review for one refresh cycle.
  - Verified same-cycle timestamps at `2026-07-05T19:28:04Z`; `post_gate_review_6400` remained `WAITING`, ETA about `9m`, and blocks strength claims.
  - Dashboard watcher was reloaded as PID `4152`; trainer PID `56876` was not restarted.
- Post-gate target selection fix:
  - `v5_dashboard_watch.py` and `v5_next_action_queue.py` now choose the earliest pending gate/internal evidence target.
  - This keeps the review on `6400` if `gate_6400` passes before `internal_probe_6400` finishes.
  - `v5_post_gate_review.py` marks non-scheduled internal probes as `NOT_SCHEDULED` so non-internal gate reviews do not wait forever.
  - Verified at `2026-07-05T19:31Z`: `post_gate_review_6400` remained `WAITING`, internal scheduled `true`, ETA about `5m`.
  - Dashboard watcher was reloaded as PID `45396`; trainer PID `56876` was not restarted.
- Post-gate due-state fix:
  - `v5_post_gate_review.py` now distinguishes `PENDING_EVIDENCE` from `DUE_EVIDENCE_REFRESH`.
  - If live/checkpoint reaches the target but the relevant gate/internal watcher has not refreshed, next-action queue can mark `post_gate_review_<target>` as `DUE`.
  - `NOT_SCHEDULED` internal probes are treated as non-blocking for gates without a scheduled internal probe.
  - Verified at `2026-07-05T19:35Z`: live iter `6394` / `104,915,368` hands, `post_gate_review_6400=PENDING_EVIDENCE`, readiness `gate_live_ready=false`, `gate_checkpoint_ready=false`, `internal_due=false`.
  - Dashboard watcher was reloaded as PID `55748`; trainer PID `56876` was not restarted.
- 6400 gate/internal evidence:
  - `gate_6400` passed at checkpoint iter `6400` / `105,013,740` hands.
  - `internal_strength_probe_iter6400_200h` completed with verdict `REGRESSION_RISK_INTERNAL`.
  - Internal summary: mean latest `+47.697 bb/100`, mean lower `-353.203`, delta mean `-649.303`, delta lower `-427.558`, latest-best `0/2`.
  - Split: call-station `-65.605 bb/100`; aggressive `+161.000 bb/100`, both over only `200` hands.
  - `v5_post_gate_review_6400.md` now reports `REVIEW_REQUIRED_NO_AUTO_RESTART`.
  - This is local/internal evidence only; it does not prove V4/L5/L6 strength and does not justify an automatic restart or promotion.
- 6400 intervention review:
  - Wrote `<run_dir>\v5_context_preflop_intervention_plan_6400.md/json`.
  - Overall: `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`.
  - Dashboard/cutover remains `HOLD_NO_CUTOVER`; next-action queue marks `preflop_intervention_review_6400` as `PASS` because no restart/cutover is queued.
  - Plan remains SB-open-focused if explicitly selected later: global preflop prior coef `0.02`, SB-open prior coef `0.03` target `0.15,0.20,0.63,0.02`, BB-vs-open prior coef `0.0`.
  - Supporting checks: action-prior trend `PASS` with lag `1`, preflop probe `WARN`, internal probe `REGRESSION_RISK_INTERNAL`, selector pair diagnostic still from 5800.
  - Do not launch the dry-run automatically; wait for `gate_6500` and later Slumbot evidence unless explicitly choosing a controlled intervention.
- 6500 post-gate queue correction:
  - `v5_post_gate_review.py` now builds recommendations from the evidence that is actually pending or due.
  - For gate-only targets where internal probe is `NOT_SCHEDULED`, it must not tell the operator to wait for `internal_probe_<target>`.
  - Verified at `2026-07-05T19:50Z`: `post_gate_review_6500` reports `PENDING_EVIDENCE` with recommendation `Wait for gate_6500; no restart or strength claim. No scheduled internal probe for this target.`
  - At `2026-07-05T19:55Z`, `v5_next_action_queue.py` was also corrected so the trigger text is gate-only: `gate evidence available for iteration 6500; no internal probe scheduled for this target`.
  - `v5_next_action_queue.json` now shows `gate_6500` waiting, `post_gate_review_6500` waiting on gate only, and the next scheduled internal probe as `internal_probe_6600`.
  - Dashboard watcher was reloaded as PID `50452`; trainer PID `56876` was not restarted.
- L6 status brief compatibility:
  - `v5_l6_status_brief.py` now emits backward-compatible top-level aliases `training`, `readiness`, and `internal_strength`.
  - This prevents old progress queries from reading `null` for live iteration, gate state, or internal probe state after the canonical schema moved to `live`, `checkpoint`, and `next_evidence`.
  - Verified at `2026-07-05T19:58Z`: live iter/hands `6446` / `105,768,494`, latest gate `6400 PASS`, next gate `6500 PENDING`, latest internal `6400 REGRESSION_RISK_INTERNAL`, next internal `6600 PENDING`, latest official Slumbot `5000` hands at `-85.037 bb/100`, claim/promote flags `false` / `false`.
- Dashboard watcher status compatibility:
  - `v5_dashboard_watch.py` now mirrors the same key status aliases to the top level of `v5_dashboard_watch_status.json`.
  - Verified at `2026-07-05T20:02Z`: top-level status directly reports live iter/hands `6454` / `105,899,744`, latest gate `6400`, next gate `6500`, latest official Slumbot `5000` hands at `-85.037 bb/100`, claim/promote `false` / `false`, queue `Wait for gate_6500`, and gate-only post-gate recommendation.
  - Dashboard watcher was reloaded as PID `55672`; trainer PID `56876` was not restarted.
- Dashboard freshness fields:
  - `v5_dashboard_watch.py` now writes top-level freshness fields: `health_age_seconds`, `latest_gate_age_seconds`, `next_gate_age_seconds`, `run_dashboard_checked_at`, `l6_status_brief_checked_at`, `next_action_queue_checked_at`, and `post_gate_review_checked_at`.
  - Verified at `2026-07-05T20:05Z`: live iter/hands `6460` / `105,998,213`, health age `0.737s`, next gate status age `29.380s`, and queue/post-gate timestamps were refreshed in the same cycle.
  - Dashboard watcher was reloaded as PID `7536`; trainer PID `56876` was not restarted.
- Dashboard first-action fields:
  - `v5_dashboard_watch.py` now mirrors the first next-action queue item to top-level status fields: `next_action_first_key`, `next_action_first_status`, `next_action_first_reason`, `next_action_first_eta`, and `next_action_first_blocks_strength_claim`.
  - Verified at `2026-07-05T20:07Z`: first action is `gate_6500`, status `WAITING`, ETA `14m`, reason `live iter 6467 < target 6500; remaining 33 iterations.`, and it blocks strength claims.
  - Dashboard watcher was reloaded as PID `55300`; trainer PID `56876` was not restarted.
- Dashboard first-action ownership fields:
  - `v5_dashboard_watch.py` now also mirrors `next_action_first_trigger`, `next_action_first_action`, and `next_action_first_owner`.
  - Verified at `2026-07-05T20:10Z`: first action is still `gate_6500`, trigger `iteration >= 6500 and checkpoint >= 6500`, action `Let gate watcher validate lineage, env/action-space, health, and checkpoint freshness.`, owner `v5_gate_sequence_watch.py`, ETA `12m`, and it blocks strength claims.
  - Dashboard watcher was reloaded as PID `55952`; trainer PID `56876` was not restarted.
- 6500 gate and post-gate review:
  - `gate_6500` passed at `2026-07-05T20:23Z` with checkpoint iter `6500` / `106,654,347` hands.
  - `v5_post_gate_review_6500.json/md` now reports `REVIEW_REQUIRED_NO_AUTO_RESTART`.
  - Evidence shape: gate PASS, health PASS at live iter `6501`, internal probe `NOT_SCHEDULED` for 6500, latest internal remains 6400 `REGRESSION_RISK_INTERNAL`, and formal Slumbot proof is still the hard blocker.
  - Local watches: checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with 4 warnings, all `argmax_suppresses_call` in SB open, BB vs min-open, BB vs 3bb open, and SB vs 3bet contexts.
  - This is local evidence only and does not prove V4/L5/L6 strength.
- Post-gate skip fix:
  - `v5_dashboard_watch.py` and `v5_next_action_queue.py` now include the latest passed gate as a post-gate candidate if its review is missing or still `PENDING_EVIDENCE`/`DUE_EVIDENCE_REFRESH`.
  - This prevents gate-only targets like 6500 from being skipped when the dashboard advances to the next pending gate/internal target.
  - After the finalized 6500 review, the current next target can correctly move to `6600`.
  - Dashboard watcher was reloaded as PID `49052`; trainer PID `56876` was not restarted.

The next useful answer is whether `gate_8700` stays healthy, whether `internal_probe_8800` confirms or weakens the 8600 `MIXED_INTERNAL` signal, and whether the 150M quick5k Slumbot screen improves the external evidence. Until formal Slumbot evidence passes, the model is not proven stronger than V4 and is not near Slumbot-positive.

## 21:33Z Continuation Check

- Verified current state at `2026-07-05T21:33Z`: trainer PID `56876` remained active; live training was about iter `6650` / `109,115,543` hands, checkpoint remained iter `6600` / `108,294,892` hands, and health was `PASS`.
- `gate_6700` remained `PENDING`, not passed: live iter `6649-6650 < 6700`, checkpoint iter `6600 < 6700`, remaining about `50` live iterations and `100` checkpoint iterations at the check. The generated `v5_post_gate_review_6700.md/json` is a pending-evidence review, not a gate pass.
- Next scheduled evidence remains `gate_6700`, then `internal_probe_6800`, then `quick5k_150M`. No `internal_strength_probe_iter6800_200h.json` existed at this check.
- Latest official Slumbot strength evidence remains the 100M `quick5k`: `5,000` greedy hands, `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, L0, `NOT_PROVEN_STRONGER_THAN_V4`.
- Latest 100M hand-log/loss-report diagnosis is usable because selector replay matched the greedy dump exactly. The loss shape is SB `-115.0 bb/100`, BB `-55.0`; terminal `hero_fold` `-167.7 bb/100`, showdown `-10.6`, all-in runout tiny-sample `-5454.5`, and opponent fold `+348.3`.
- First-preflop losses are dominated by `sb_open_c` `-135.2 bb/100`, `bb_vs_open_lt2.5bb_f` `-100.0`, `sb_open_raise_lt2.5bb` `-181.4`, and `bb_vs_open_lt2.5bb_c` `-81.6`. Rates are SB open fold/call/raise/all-in `0.327/0.506/0.167/0.000`, BB vs open call/raise `0.340/0.088`.
- Decision: no automatic restart or cutover from this evidence. The leak is not a simple BB-call problem; callguard replay changed many decisions but mostly on losing hands and is diagnostic only. Continue the active trainer through `gate_7400` and `internal_probe_7400` for fresh local evidence, while holding the context-preflop intervention review as a reviewed option only.

## 00:08Z Gate 7000 Continuation Check

- Verified current state at `2026-07-06T00:08Z`: trainer PID `56876` remained active; live training was about iter `7010` / `115,022,793` hands, checkpoint iter `7000` / `114,858,660` hands, and health was `PASS`.
- `gate_7000` passed and `internal_strength_probe_iter7000_200h` completed. The post-gate review is `REVIEW_REQUIRED_NO_AUTO_RESTART`, not a cutover trigger.
- Latest internal probe remains `REGRESSION_RISK_INTERNAL`: call-station `+4.64 bb/100` with CI lower about `-99.66`, aggressive `+1005.75 bb/100` with CI lower about `-148.40`, mean `+505.195 bb/100`, delta versus 6800 mean `+515.630`. This is local-only evidence.
- Latest official Slumbot strength evidence remains the 100M `quick5k`: `5,000` greedy hands, `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, L0, `NOT_PROVEN_STRONGER_THAN_V4`.
- Next scheduled evidence is `gate_7400`, `internal_probe_7400`, and `quick5k_150M` after checkpoint hands reach `150,000,000`.
- New watcher coverage is active: gate watcher PID `7988` covers `7100..9200`; internal watcher PID `42588` covers `7200..9200`. Promotion20k and formal100k Slumbot watchers remain waiting for `250,000,000` checkpoint hands.

## 21:38Z Evidence Watchdog Alias Fix

- `v5_evidence_watchdog.py` now writes top-level strength aliases so quick status reads do not return `null` for strength: `strength_answer`, `strength_status`, `latest_better_answer`, `trend_answer`, latest Slumbot hands/bb100/CI lower, milestone level, and V4/L5/L6 claim booleans.
- Verified with a one-shot refresh at `2026-07-05T21:38Z`: overall `EVIDENCE_ACTIVE_STRENGTH_UNPROVEN`, `strength_answer=SAMPLE_TOO_SMALL_FOR_BASELINE_CLAIM`, `strength_status=UNPROVEN`, `latest_better_answer=LATEST_POINT_ESTIMATE_DOWN`, `trend_answer=SLUMBOT_POINT_ESTIMATE_DOWN`, latest Slumbot `5000` hands at `-85.037 bb/100` with CI lower `-129.224`, milestone `L0`, and all claim booleans `false`.
- This is a reporting/schema fix only. It does not change training, checkpoints, benchmark policy, or strength evidence.

## 21:40Z Action-Prior Trend Refresh

- Refreshed `v5_action_prior_trend.json/md` without touching the trainer. Result: `PASS` at candidate latest iter `6664` / `109,345,300` hands.
- Tail-80 candidate means: preflop call `0.302`, preflop all-in `0.079`, postflop raise/all-in `0.568`, postflop call `0.226`.
- Delta versus the baseline run: preflop call `+0.0771`, preflop all-in `-0.0338`, postflop raise/all-in `+0.0104`, postflop call `-0.0223`.
- Interpretation: the action-prior guardrail remains healthy enough to keep training, but this is training-log action-mix evidence only. It does not prove V4 improvement, L5, or L6, and it does not override the 100M Slumbot L0 result or the 6600 internal `REGRESSION_RISK_INTERNAL` marker.

## 21:42Z Eval Cadence Alias Fix

- `v5_eval_cadence_watch.py` now mirrors compatibility aliases at the top of `v5_eval_cadence_watch_status.json`: `next_eval_key`, `next_stage`, `next_target_hands`, `next_state`, `next_eta`, and `remaining_checkpoint_hands`.
- Verified with a one-shot refresh at `2026-07-05T21:42Z`: `next_eval_key=quick5k_150M`, `next_stage=quick5k`, `next_target_hands=150000000`, `next_state=WAITING`, `next_eta=16h 34m`, checkpoint hands `108,294,892`, current hands `109,443,756`, and remaining checkpoint hands `41,705,108`.
- The long-running eval cadence watcher was restarted from PID `48356` to PID `47484` so future refreshes keep these aliases. Trainer PID `56876` was not restarted.

## 21:45Z Dashboard Eval Alias Fix

- `v5_dashboard_watch.py` now forwards the same eval-cadence compatibility aliases to `v5_dashboard_watch_status.json`: `next_eval_key`, `next_stage`, `next_target_hands`, `next_state`, `next_eta`, and `remaining_checkpoint_hands`.
- Verified with a one-shot dashboard refresh at `2026-07-05T21:45Z`: dashboard status reports `next_eval_key=quick5k_150M`, `next_stage=quick5k`, `next_target_hands=150000000`, `next_state=WAITING`, and `remaining_checkpoint_hands=41,705,108`.
- Dashboard watcher was restarted from PID `48876` to PID `53676` so future dashboard refreshes retain the aliases. Trainer PID `56876` was not restarted.

## 21:57Z Gate 6700 Review

- `gate_6700` passed at checkpoint iter `6700` / `109,936,130` hands with health `PASS`.
- A one-shot dashboard refresh wrote `<run_dir>\v5_post_gate_review_6700.json/md`, reporting `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED` for 6700, latest internal evidence still 6600 `REGRESSION_RISK_INTERNAL`, preflop probe `WARN` with 3 warnings, and strength `NOT_PROVEN_STRONGER_THAN_V4`.
- Dashboard/queue advanced to `gate_6800` (`WAITING`, ETA about `46m`) and then `internal_probe_6800`.
- The next external Slumbot screen remains `quick5k_150M`, waiting for checkpoint hands `150,000,000`; latest checkpoint hands are `109,936,130`, so `40,063,870` checkpoint hands remain.
- No automatic restart, cutover, V4 claim, L5 claim, or L6 claim is justified by the 6700 gate. Trainer PID `56876` was not restarted.
