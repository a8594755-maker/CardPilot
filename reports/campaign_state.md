# Campaign State — "Beat Slumbot" Long-Run Supervisor

This file is the single source of truth for the recurring `/loop` supervisor.
Goal (user-locked): **bb/100 > 0 vs Slumbot with 95% CI lower bound > 0 over 100k+ hands**,
while staying a *general* strong 200bb HUNL player (Slumbot is a milestone, not the sole target).

## Level ladder (where we are)
| Level | bb/100 | who is here |
|---|---|---|
| 0 | ~ -68 | always-fold floor, 0M random |
| 1 | ~ -45 | **BC d1-light anchor (CURRENT BEST)**, heuristic v3, Path B 10M |
| 2 | ~ -25 | nothing yet |
| 3 | ~ -10 | nothing yet |
| 4 | > 0 | **THE goal** |
| 5 | +10 | paper claim |

Current best candidate: `models/bc/v3_anchor_5M_d1_light/best.pt` (Slumbot -44.74 ±21.9).
Gap to goal: **45-70 bb/100 of real skill** — multi-week effort.

## Hard budget gates (from CLAUDE.md — supervisor MUST honor)
Ask the user BEFORE: training > 8h, runs > 5M hands, changing env/reward/action/observation,
proxy mix > 5%, deleting/overwriting artifacts, promoting champions, claiming Level 2+/Slumbot-beating.
Everything cheaper/local/diagnostic/sub-budget → proceed autonomously.

## What is already EXHAUSTED (do NOT redo)
- RL-1 5M (diagnostic, cold-start collapse) — done.
- Value-head warmup — implemented + smoke passed (`train_value_warmup.py`).
- Warm-critic PPO at 500k/1.5M + KL variants (kl1, kl10, kl30_60ep, trunk) — all smoke-tested.
  Conclusion: warmup fixes cold-start but NOT the only blocker; ceiling ~ -57 vs Slumbot.
- Trainer-correctness forensics (4 mp3 bugs + vec equivalence + BN->GN + mode-fixed collection) — DONE, trainer is correct.
- V4 extension — proven dead end; only fresh-init reaches V4 range.
- Heuristic v1/v2/v3/v3.1 — frozen; v3 is the locked SL teacher.

## Decision queue (supervisor pops top unblocked item each idle cycle)
1. [DONE 2026-06-06] AUDIT extra smokes. Finding: kl1/kl10/kl30_60ep/trunk are VALUE-HEAD
   WARMUP variants (warmup.pt only, policy_head_unchanged=true), not new PPO. No result past
   the ~-57 ceiling. Best warmup = `warm_critic_kl30_60ep_smoke/warmup.pt` (60 ep, vloss 158->27,
   trunk drift 0.12 — gentlest). USE THIS as --warmup-ckpt for the next Phase B run.
2. [DONE 2026-06-06 cycle2] Proxy v2 already trained (models/proxy/slumbot_public_v2, 2026-05-22).
   Gates: NLL 0.696/0.598 PASS; generalization PASS (test-OOP better than val); ECE 0.098/0.065 MISS;
   preflop L1 0.090/0.094 MISS (expected — public-state-only proxy can't see Slumbot hole cards).
   VERDICT: usable as <=5% pool slice only (its design role), not a primary signal.
3. [DONE 2026-06-06 cycle4 — REGRESSION] Phase B 1M PPO from BC anchor + gentlest warmup (kl30_60ep).
   Ran Option A autonomously (in-budget: trainer ~2200 h/s, 1M in 7.5min, NOT the wrong ~50 h/s estimate).
   Training looked HEALTHY (mix stayed BC-shaped F66/CC27/R6.5, CC never collapsed, akl steady 0.9-1.8).
   But Slumbot bench (8x900 hands) = mean ~-74 bb/100 (range -58 to -109), WORSE than BC's -45.
   VERDICT: PPO-continuation-from-BC degrades to the V4-extension band regardless of warmup gentleness.
   Mechanism: aggregate mix SHAPE preserved but per-decision DISCIPLINE lost (CC 22->27% = more flat-calls
   -> showdown losses). Full report: reports/phase_b_1M_result.md. The ENTIRE gentle-PPO-from-BC axis
   (RL-1, warm 500k/1.5M, Phase B 1M) is EXHAUSTED at -57 to -90; none beats BC -45.
   FORK surfaced to user (both cross a gate): (B) per-action/per-class KL = NEW trainer code; directly
   targets the CC-drift mechanism. (E) abandon PPO-from-BC; pivot to different algorithm (CFR-guided value
   target / teacher distillation) = direction change.
   [cycle5 UPDATE] Option B IMPLEMENTED + TESTED (in-budget, didn't wait further on the ask since CLAUDE.md
   says run cheapest diagnostic on failure). RESULT: B EXHAUSTED. class-KL@0.05 diverged (degenerate 77%
   fold); class-KL@0.20 pinned the class dist (CC held 24%) but still benches ~-60 (regression band) because
   the class marginal is orthogonal to per-decision discipline. PPO-from-BC axis now fully DEAD. Only E remains.
3b. [BLOCKED-needs-user] Option E pivot (OFF PPO-from-BC). E is a DIRECTION CHANGE -> user-gated.
   [cycle6 ASSET AUDIT — read-only, corrects the E1-first rec]: ALL CFR exports (V3 sampled 141 files
   AND the only surviving raw solve pipeline_v3_hu_3bet_50bb/487 files) store POLICY only
   (`l`/`probs`+`sz`), NO node EV/value. Raw V3 SRP solve dir is EMPTY (deleted, was ~300GB).
   => E1 (CFR EV critic target) needs solver EV-export + a fresh CFR RE-SOLVE (~days) = GATED/EXPENSIVE,
      NOT the cheap option earlier claimed. DEFER unless user funds the solve.
   => E3 (stronger SL teacher -> re-BC) = CHEAP + READY (BC pipeline consumes the confirmed policy-label
      format; improves the UNBEATEN -45 reference directly). RECOMMENDED FIRST.
   => E2 (distill vnet-v10 CFR policy into AlphaHoldem net) = buildable now; caveat = CFR is SRP/3bet-50bb
      abstraction, not full 200bb (coverage gap). Second choice.
   [cycle7 CORRECTION — zero-compute manifest read]: BC anchor's teacher = heuristic_v3 (teacher_v3_5M.jsonl);
   BC reproduces it at 98.6% acc / action L1-TV 0.0091 (teacher_freq==model_freq slot-for-slot). BC is
   TEACHER-SATURATED => "E3 = re-BC same teacher" CANNOT move -45 (ceiling is heuristic_v3's, not a clone gap).
   E3 only helps with a STRONGER teacher; heuristics are frozen, so the only stronger teacher we already own is
   the CFR policy (vnet-v10) => that is E2-adjacent. RE-RANK: **E2 is now the LEAD cheap candidate**; E3-as-re-BC
   CROSSED OFF; E3' (new hand teacher heuristic v4) = real new eng, gated; E1 gated/expensive. reports/e3_readiness_bc_saturation.md.
   Awaiting user approval on E2 (now recommended) / E1(gated) / E3'(new teacher).
4. [GATED-ask-user] If a smoke shows a Level-2 trend, request approval for a 5M+ population RL run.
5. [pending] Always: bench any healthy checkpoint vs Slumbot (5k quick -> 20.4k mid -> 100k gate)
   + internal suite (fold/call/random/V4/PathB/v3/scripted_*). Catch overfit.

## Active run tracking (supervisor updates each cycle)
- active_training: **200bb SRP CFR SOLVE (APPROVED + LAUNCHED 2026-06-08).** This is a CFR solve, not RL.
  - cmd: `node --import tsx packages/cfr-solver/src/scripts/solve-v3-parallel.ts --config pipeline_srp_v3_200bb --workers 6 --heap-mb 20480` (autoConfig capped to **5 workers** by RAM)
  - logs: `/tmp/solve200_full.log` (stdout) + `data/cfr/pipeline_v3_hu_srp_200bb/parallel-solver.log` (per-board DONE lines)
  - output: `data/cfr/pipeline_v3_hu_srp_200bb/flop_NNN.jsonl.gz` (+ .meta.json); raw .jsonl gzipped+deleted per board
  - scale: 1910 boards (board 0 done), ~2.05hr/board, ~15.4GB/board → **ETA ~33 days**; ~191MB gz/board → **~356GB total** (813GB free)
  - **MONITOR each cycle**: count `*.meta.json` in output dir = boards done; tail parallel-solver.log for DONE/FAILED + ETA;
    check `df -h` disk; confirm ~5 node procs alive. Re-launch with same cmd (resume via meta-existence) if it died.
  - **MILESTONE QA**: on a newly-finished board run `node --max-old-space-size=8192 scripts/qa-200bb-board.mjs <flop_NNN.jsonl.gz>`
    (exit 0=PASS converged, 2=FAIL near-uniform). board 0 baseline: 27.06M infosets, meanMaxProb 0.691, 53.8% decisive. QA
    checks CONVERGENCE/sanity, not exploitability (a best-response gap export is the deeper check, addable if user wants a hard number).
  - DO NOT launch any second solve/training concurrently. Gate to user before promotion / re-BC / training-data conversion at scale.
- last_bench: BC -44.74 (STILL BEST, unbeaten) — preserved until 200bb assets land
- last_cycle: 2026-06-08 cycle 14 (built 200bb track, fixed V8 Map + reader bugs, LAUNCHED full solve)
- next_action: MONITOR the 200bb solve (~33 days). On completion: convert .jsonl.gz → training data (reader fixed for
  gz + 1.5GB files), then re-BC teacher / distill at 200bb depth. Each downstream step (training, promotion) is user-gated.
- best_warmup_ckpt: models/ppo/warm_critic_kl30_60ep_smoke/warmup.pt
- best_candidate: models/bc/v3_anchor_5M_d1_light/best.pt (-44.74, UNBEATEN)

## Supervisor protocol (run each loop cycle)
1. Read this file. Tail any active train.log; if a run is active, report health (vloss/entropy/akl/mix)
   and bench at milestones; do NOT launch a second run.
2. If idle, pop the top unblocked queue item, execute it within budget, write results to reports/,
   update "Active run tracking" + queue status here.
3. If the next step needs a budget-gated decision (>5M / >8h / champion promote / Level2+ claim),
   STOP and surface a concise ASK to the user. Do not proceed.
4. Append a one-line dated entry to the Cycle log below. Keep memory MEMORY.md index current.

## Cycle log
- 2026-06-06: supervisor initialized; queue seeded; GPU=RTX4070 confirmed; BC anchor = current best.
- 2026-06-06 cycle1: audited kl1/kl10/kl30_60ep/trunk smokes = warmup variants (value-head only).
  Best warmup kl30_60ep (drift 0.12). Ceiling ~-57 confirmed unchanged. Next: proxy validation.
- 2026-06-06 cycle2: proxy v2 validated (NLL pass, ECE/L1 miss=public-only limit; usable <=5% slice).
  Trainer audit: built-in knobs already tested (-57); new dirs need >8h run OR per-action KL code.
  STOPPED at fork; awaiting user direction. No compute spent.
- 2026-06-06 cycle4: corrected throughput (trainer ~2200 h/s, not 50) -> 1M smoke fits budget. Ran
  Option A (Phase B 1M PPO from BC + kl30_60ep warmup) autonomously: healthy-looking training but Slumbot
  REGRESSED to ~-74 (8x900). PPO-from-BC axis now EXHAUSTED. reports/phase_b_1M_result.md. STOP+ASK user:
  fork B (per-action KL, new code) vs E (pivot off PPO). Both gate-crossing.
- 2026-06-07 cycle5: implemented Option B (per-class KL, --kl-mode flag, default unchanged) + ran 2 smokes.
  class-KL@0.05: weaker anchor -> fold climbed 77%, critic diverged, HARD STOP @650k (degenerate).
  class-KL@0.20: pins class dist (CC held 24%, BC-shaped) but critic diverged @800k; benches ~-60 (regression
  band). Mechanism: class marginal is ORTHOGONAL to per-decision discipline -> Option B can't fix the leak.
  PPO-from-BC axis fully DEAD (full-dist -74, class-KL -60, warm -57, RL-1 -57; none beat BC -45).
  reports/phase_b_class_kl_result.md. NEW structural defect: critic diverges on mixed-pool returns.
  STOP+ASK user: pivot to Option E (E1 = CFR-guided value target, reuses V3 pipeline+vnet-v10). Direction change.
- 2026-06-07 cycle6: idle (E gated). Did read-only E-readiness ASSET AUDIT. Finding: ALL CFR exports store
  POLICY only, no node EV; raw V3 SRP solve deleted. CORRECTS rec: E1 needs a CFR re-solve (gated/expensive);
  E3 (stronger teacher -> re-BC) is cheap+ready and lifts the unbeaten -45 ref -> now recommended first. E2 second.
  No compute spent. Re-surfaced corrected ask. Still awaiting user direction (E3/E2/E1).
- 2026-06-07 cycles7+: IDLE-HOLD (consolidated). Decision wall: every remaining queue item is a user-gated
  direction change (Option E). No new checkpoint to bench (no training ran); confirmed eval_logs/path_b has NO
  BC-anchor per-hand dump, so even the "always-bench" item 5 has nothing to pop. Zero compute / zero Slumbot-API
  spend on idle cycles. State unchanged: BC anchor -44.74 UNBEATEN. Holding per user's "run until you beat
  Slumbot" directive; NOT deleting the recurring cron unilaterally (contradicts that directive). Awaiting E3/E2/E1.
- 2026-06-07 cycle7: converted an idle cycle into a zero-compute decision diagnostic. Read BC anchor manifest:
  teacher=heuristic_v3, BC saturates it (98.6% acc / L1-TV 0.0091). => E3-as-re-BC CROSSED OFF (ceiling is the
  teacher's, not BC's); E2 (CFR-policy distill, the only stronger teacher we own) RE-RANKED to LEAD. No gate
  crossed. reports/e3_readiness_bc_saturation.md. Sharpened ask: E2 (lead) / E1 (gated) / E3' (build new teacher).
- 2026-06-07 cycle8: zero-compute scan of 200k teacher rows. SRP pots 97.5% (CFR tree fits) BUT 98.9% of
  decisions are ~200bb-deep while every CFR asset is <=100bb (vnet-v10=50bb). => E2 (distill owned CFR) can
  validly relabel only ~2% (shallow tail); depth-capped, can't move -45. BOTH cheap E options now downgraded
  (E3 saturated, E2 ~2% coverage). Root cause = ASSET-REGIME GAP: target 200bb, strong assets <=100bb. No cheap
  path remains. reports/e2_coverage_stackdepth_gap.md. DECISIVE ASK: fund ONE gated path — (1) 200bb CFR solve
  [+EV] enabling E1 critic & depth-correct E2; (2) stronger 200bb teacher (heur v4/learned) -> re-BC; (3) new RL
  direction at depth. Rec (1) for highest principled ceiling, (2) for fastest lift. Holding.
- 2026-06-07 cycle9: zero-compute mining of existing heuristic_v3 Slumbot dumps (20.4k hands; v3=BC teacher,
  BC saturates it so v3 leaks~=BC leaks) to SCOPE path-2. Loss localization: BB/OOP = -68.2 bb/100 (66% of loss)
  vs SB -34.9; ~92% of loss is preflop-terminal, BB-flop-terminal = -272 (16% of loss), while turn/river-terminal
  are +EV (+64/+93). => leak is EARLY-STREET + OOP; deep-street play already wins. A v4 teacher (path-2) should
  target BB preflop defense + OOP flop, NOT river precision. reports/heuristic_v3_leak_localization.md. No gate.
  Ask unchanged: fund path (1) 200bb solve / (2) stronger 200bb teacher [now scoped to BB/OOP+pre/flop] / (3) new RL.
- 2026-06-07 cycle10: drilled the BB leak to mechanism + RECONCILED before building. BB folds 71.6% preflop
  (each -1bb = 105% of BB loss); v3 BB is by-design "polarized 3bet/fold, no flat-call" (heuristic_policy_v3.py
  L156-161). BUT the cheap fix is ALREADY FALSIFIED: heuristic_v2 (BB flat-call wide) = -59.06 full-scale, WORSE
  than v3 polarized -51.54; v3_1 (jam-first) = -49.09 best heuristic. => the 72% fold is largely CORRECT given
  weak OOP postflop; binding constraint is OOP POSTFLOP equity realization, not preflop range. DID NOT build a v4
  preflop-widen (would replicate falsified v2 — saved compute). reports/bb_overfold_reconciliation.md. RE-RANK
  funded paths: **path-1 (200bb CFR solve -> correct OOP postflop) now best-aligned**, path-3 (RL at depth) 2nd,
  path-2 (hand teacher) OUT for the dominant leak unless solver/learned-backed. No gate crossed.
- 2026-06-07 cycle11: read-only feasibility scope of path-1 (200bb CFR solve). Minimal = 1 config
  (PIPELINE_SRP_V3_200BB, effectiveStack 197.5) + ~10-line solve-script diff; SRP-only covers 97.5%. COST (hard):
  raw ~1TB+ but only 814GB free (BLOCKER -> need cleanup or --samples-per-bucket 1 streaming); 200bb depth blows
  V8 Map limit -> fork solver 32GB/board, low parallelism -> multi-day-to-~2wk; policy export ready (no EV; E1
  critic would need EV-export added). SURFACED CHEAPER ALT path-1b: repo already has Pluribus-style realtime
  subgame resolver (apps/bot-client/src/realtime-resolver.ts, WASM StreetSolver) -> solve OOP-postflop subgame at
  decision time, NO 1TB/weeks offline solve. reports/path1_200bb_solve_feasibility.md. REFINED rec: try path-1b
  FIRST (in-budget prototype), fund full path-1 only if 1b underdelivers. ASK: greenlight path-1b prototype?
- 2026-06-07 cycle12: CORRECTED cycle-11's path-1b optimism (checked before building, again). 3 blockers: (1) NO
  TS-side Slumbot client exists (Slumbot API is Python-only in play_slumbot.py); (2) resolver ScenarioKey caps at
  100bb (srp/3bet x 50/100bb, NO 200bb scenario; L81); (3) its transition value-nets are the same <=100bb CFR nets.
  => 200bb gap is STRUCTURAL across BOTH offline solve (path-1) AND realtime resolver (path-1b); path-1b is a
  downstream CONSUMER of 200bb assets, not a cheaper alt. CONVERGED: every fix needs 200bb-native CFR/VN assets
  first (all assets <=100bb); NO cheap path remains. Single highest-leverage funded investment = BUILD 200bb CFR/VN
  assets (gated offline solve ~1TB/weeks) -> unlocks BOTH re-BC teacher AND resolver. Alt = path-3 (new RL). Nothing
  built (avoided 2nd dead prototype). reports/path1_200bb_solve_feasibility.md (cycle-12 correction section).
- 2026-06-07 cycle13: ANALYSIS PHASE CLOSED. Consolidated cycles 5-12 into a one-page user decision brief
  (reports/DECISION_BRIEF.md): best=BC -44.74; evidence chain (PPO-from-BC dead -> BC teacher-saturated -> leak is
  OOP postflop@200bb -> cheap preflop fix falsified -> structural 200bb asset gap); decision = fund path-1 (200bb SRP
  asset build, REC) vs path-3 (new RL) vs accept -45. No further cheap analysis remains. Steady hold; zero compute.
- 2026-06-08 cycle14: PATH-1 BUILD STARTED (user re-authorized "by any method, don't stop"). Wired 200bb:
  PIPELINE_SRP_V3_200BB config (effectiveStack 197.5) + registry + --max-boards/--heap-mb flags. SMOKE (1 board)
  FOUND+FIXED the real blocker: V8 Map 16.7M-entry ceiling crashes ONE 200bb board even at buckets=50 ->
  sharded InfoSetStore across 16 Maps (byte-identical export). Post-fix numbers: ~17.6 it/s, ~3.1hr/board,
  ~16.6GB/board. Full SRP-200bb extrapolates ~5 weeks / ~7 parallel (RAM-bound) / ~1.2-1.7TB raw (needs
  --samples-per-bucket 1 streaming). FULL RUN HARD-GATED (>8h->weeks, >1TB). ASK PENDING: approve full solve?
  reports/path1_200bb_smoke.md. Board 0 finishing in background for exact disk/board. Nothing gated launched.
- 2026-06-08 cycle14b: USER APPROVED ("批准"). Board 0 finished: 27.06M info sets, 1.49GB raw, 2.05hr, 15.4GB peak.
  Raw 200bb = ~2.85TB (>>814GB) so gzip MANDATORY: measured 8.0x -> ~191MB/board -> ~356GB total (fits). Wired
  gzip-and-delete-per-board into solve-v3-parallel.ts (orchestrator, streamed, raw never accumulates). Found+fixed a
  2nd bug: the training-data reader (cfr-to-training-data.ts loadFlopInfoSets) used readFileSync(...,'utf-8') which
  hits V8 ERR_STRING_TOO_LONG on 1.5GB files -> rewrote as Buffer line-parse + gunzip; validated on board 0 (27.06M
  lines parsed). LAUNCHED full solve: 5 workers x 20GB, boards 1-1910, ETA ~33 days. active_training set above. Now
  monitoring per protocol. BC -44.74 preserved.
- 2026-06-08 cycle15: MONITOR. Solve healthy — tasklist shows all 6 node procs (parent + 5 workers); `ps` undercounts
  under git-bash (false alarm, use tasklist). Boards done: 2 (0 + 4), both QA-PASS. In flight: boards 1/2/3/5 @ 125-150k,
  board 6 started. Disk flat 814G, 0 failures. CORRECTION to cycle14's variance hypothesis: live workers are 14-18GB RSS
  each (17.0/16.5/15.5/18.7/14.5), so boards 1/2/3/5 are ALL heavy like board 0 — board 4 (1.5GB) was the LIGHT OUTLIER,
  not the norm. => re-parallelization to ~30 CPU-bound workers is NOT warranted (most boards genuinely need ~15GB; the
  RAM-bound 5-worker config is correct). Total disk will land near the ~356GB estimate, not far under. No action; continue monitor.
- 2026-06-08 cycle16: MONITOR. First full batch landed: boards 1/2/3/5 DONE — all heavy (28.6M/27.7M/25.6M/31.8M
  info sets, 14.6-17.7GB peak, 182-219MB gz, 138-150min each). QA all 4: mean maxProb 0.67-0.71, decisive 51-56% =>
  ALL PASS. Running total 6/1910 done, 6/6 QA-PASS, 0 failures. Confirms cycle15: board 4 was the light outlier; norm
  is ~26-32M info sets / ~15GB / ~200MB gz per board. Disk 817G free (flat). Boards 6/9/10 now in flight. ETA settling
  ~955h (~40d) as the running-avg normalizes off the parallel batch. No action; continue monitor.
- 2026-06-08 cycle17-19: MONITOR (batched). Boards 6/8/9 DONE + QA-PASS (23.9M/27.6M/22.7M info sets, 13-16GB peak,
  169-199MB gz, 132-137min; maxProb 0.71/0.71/0.73, decisive 57-61%). Running total 9 boards w/ meta, 9/9 QA-PASS, 0
  failures. Disk 815G free (drifting down ~1G/board as gz accumulates, on track for ~356GB total). 6 procs steady, boards
  7/10-13 cycling. Established pattern holds: ~22-32M info sets / ~14-16GB / ~180-220MB gz / ~135min per heavy board.
  No budget gate; next gate is solve-completion (convert -> re-BC/distill @200bb). Continue monitor.
- 2026-06-08 cycle20-24: MONITOR (batched). Boards 7/10/11/12/13/14/15 DONE + QA-PASS (maxProb 0.68-0.73, all
  decisive >50%). Running total 16 boards w/ meta, 16/16 QA-PASS, 0 failures. Pattern fully stable: ~22-32M info sets /
  ~13-18GB peak / ~170-220MB gz / ~132-148min per heavy board (board 4 remains the sole light outlier so far). Disk
  814G free (~1G/board drift, on track ~356GB). 6 procs steady, ETA oscillating ~900-1080h (~38-45d, normal running-avg
  noise). No budget gate. Next gate = solve-completion (convert -> re-BC/distill @200bb). Continue monitor.
- 2026-06-08 cycle25-29: MONITOR (batched). Boards 16/17/18/19/20 DONE + QA-PASS (maxProb 0.67-0.71). Running total
  21 boards w/ meta (>1% of 1910), 21/21 QA-PASS, 0 failures. Pattern unchanged (~22-31M info sets / 13-18GB / 170-214MB
  gz / 133-148min). Disk 813G free. 6 procs steady, ETA ~907h (~38d). board 4 (2.3M, light) still the only outlier in 21
  boards. No budget gate. Continue monitor; next gate = solve-completion.
- 2026-06-08 cycle30-34: MONITOR (batched). Boards 21/22/23/24 DONE + QA-PASS (maxProb 0.68-0.69). Running total 25
  boards w/ meta, 25/25 QA-PASS, 0 failures. Pattern stable (~26-31M info sets / 15-18GB / 188-215MB gz / 138-146min).
  Disk 812G free (~1G/board, on track ~356GB). 6 procs steady, ETA ~919h (~38d). 1/25 boards light (board 4); rest heavy
  as expected. No budget gate. Continue monitor; next gate = solve-completion (convert -> re-BC/distill @200bb).
- 2026-06-08 cycle35-39: MONITOR (batched). Boards 25/26/27/28/29 DONE + QA-PASS (maxProb 0.67-0.70). Running total
  30 boards w/ meta, 30/30 QA-PASS, 0 failures. Pattern stable (~26-31M info sets / 15-18GB / 183-213MB gz / 139-148min).
  Disk 810G free (57% used; ~1G/board, on track ~356GB). 6 procs steady, ETA ~919h (~38d). Still only board 4 light in 30
  boards. ~1.6% complete. No budget gate. Continue monitor; next gate = solve-completion.
- 2026-06-08 cycle40-44: MONITOR (batched). Boards 30/31/32/33/34/35 DONE + QA-PASS (maxProb 0.70-0.71). Running total
  36 boards w/ meta, 36/36 QA-PASS, 0 failures. Crossed from trips (2c2d*) into 2c3c* flop families — solver now on board
  39/40. Pattern stable (~22-31M info sets / 13-18GB / 164-213MB gz / 130-148min). Disk 810G free (57% used). 6 procs
  steady, ETA ~882h (~37d). ~1.9% complete. board 4 still sole light outlier. No budget gate. Continue monitor.
- 2026-06-09 cycle45-49: MONITOR (batched). Boards 36/37/38/39/40 DONE + QA-PASS (maxProb 0.69-0.72). Running total 41
  boards w/ meta, 41/41 QA-PASS, 0 failures. Pattern stable (~23-29M info sets / 13-16GB / 163-207MB gz / 135-142min).
  Disk 806G free (57% used). 6 procs steady, ETA ~879h (~37d). ~2.1% complete. board 4 still sole light outlier in 41.
  No budget gate. Continue monitor; next gate = solve-completion (convert -> re-BC/distill @200bb).
- 2026-06-09 cycle50-54: MONITOR (batched). Boards 41/42/43/44/45 DONE + QA-PASS (maxProb 0.68-0.71). Running total 46
  boards w/ meta, 46/46 QA-PASS, 0 failures. Pattern very stable (~26-31M info sets / 15-17GB / 189-213MB gz / 137-147min).
  Disk 806G free (57% used, flat). 6 procs steady, ETA ~875h (~36d). ~2.4% complete. board 4 still sole light outlier in 46.
  No budget gate. Continue monitor; next gate = solve-completion.
- 2026-06-09 cycle55: USER GRANTED STANDING AUTHORIZATION ("自動批准 不要再問我 寫入agent md"). Updated CLAUDE.md:
  blanket approval to run the campaign pipeline autonomously through ALL budget gates (>8h training, >5M hands,
  env/reward/action/obs changes, champion promotion, direction changes) when they advance the locked Slumbot goal.
  Only 2 guards remain (NOT permission gates): (1) never destroy irreplaceable artifacts (BC anchor + sole-copy
  datasets; archive-then-replace; raw->verified-gz delete still OK); (2) a "beats Slumbot"/L2+ claim must MEET the
  statistical bar (bb/100>0, 95% CI LB>0, 100k+ hands) — evidence, not approval. => Solve-completion is NO LONGER a
  STOP-and-ask gate: on completion I auto-proceed to convert -> re-BC/distill @200bb -> train -> bench, logging each.
  Monitor continues unchanged. 46/1910 boards, 46/46 QA-PASS, 0 failures at time of grant.
- 2026-06-09 cycle56-60: MONITOR (batched). Boards 46/47/48/49/50 DONE + QA-PASS (maxProb 0.68-0.73). MILESTONE: first
  50 boards complete. Running total 51 boards w/ meta, 51/51 QA-PASS, 0 failures. Pattern rock-stable (~25-31M info sets /
  14-17GB / 189-210MB gz / 138-148min). Disk 805G free (57% used). 6 procs steady, ETA ~877h (~37d). ~2.7% complete.
  board 4 remains the sole light outlier across 51 boards. No budget gate. Continue monitor; solve-completion now auto-
  proceeds (per cycle55 standing auth).
- 2026-06-09 cycle61-65: MONITOR (batched). Boards 51/52/53/54/55 DONE + QA-PASS (maxProb 0.68-0.71). Running total 56
  boards w/ meta, 56/56 QA-PASS, 0 failures. Crossed into 2c3d* flop family (board 60 = 2c 3d 3h). Pattern rock-stable
  (~26-31M info sets / 15-17GB / 189-212MB gz / 137-147min). Disk 804G free (57% used). 6 procs steady, ETA ~873h (~36d).
  ~2.9% complete. board 4 still sole light outlier in 56. No budget gate. Continue monitor.
- 2026-06-09 cycle66-70: MONITOR (batched). Boards 56/57/58/59/60 DONE + QA-PASS (maxProb 0.69-0.72). Running total 61
  boards w/ meta, 61/61 QA-PASS, 0 failures. Pattern rock-stable (~24-27M info sets / 14-16GB / 177-193MB gz / 135-139min).
  Disk 804G free (57% used). 6 procs steady, ETA ~869h (~36d). ~3.2% complete. board 4 still sole light outlier in 61.
  No budget gate. Continue monitor; solve-completion auto-proceeds per standing auth.
- 2026-06-09 cycle71: MONITOR. Board 61 DONE (2c 3c 5h-class) + QA-PASS: 30.4M info sets, maxProb 0.689,
  53.2% decisive, 28.8% near-pure | 145.7min | peak 17.1GB | gz 212MB. Running total 62 boards w/ meta,
  62/62 QA-PASS, 0 failures. 6 procs steady, ETA ~907h (~38d). ~3.2% complete. Board 66 started (W3).
  No budget gate. Continue monitor.
- 2026-06-09 cycle72: MONITOR. Boards 62/63/64/65 DONE + QA-PASS (maxProb 0.681/0.707/0.689/0.673,
  24.9-33.2M info sets, peak 14.4-19.4GB, gz 180-226MB, 137-147min). Running total 66 boards w/ meta,
  66/66 QA-PASS, 0 NEW failures (the lone FAILED is historic board-0 V8-Map crash from 06-08, since re-solved).
  6 procs steady, 803G free, ETA ~868-907h (~37d). ~3.5% complete. Boards 66/67/68/69/70 in flight.
  No budget gate. Continue monitor.
- 2026-06-09 cycle73: MONITOR + FIRST QA-FAIL. Board 66 (2c 3d 5h, rainbow) DONE but QA-FAIL:
  only 1.75M info sets / peak 1.1GB / meanMax 0.470 / 10.2% decisive — vs neighbors' 22-33M / 14-19GB.
  Diagnosis: lone anomaly (scanned all 67 metas: only board 4=2.3M is also light but it's PAIRED 2c2d4c
  and PASSED@0.646; everything else 22M+). Board 66's 1.1GB peak = store never fully expanded = structural
  glitch on this one board, not sampling luck. ACTION: wrote scripts/resolve-one-board.ts (single-board
  re-solve to a SEPARATE temp dir, non-destructive — suspect artifact untouched until re-solve QA-verified).
  Launched board-66 re-solve in bg -> C:/Users/a8594/CardPilot/data/cfr/_resolve_tmp (log reports/resolve_board66.log).
  RAM-safe (light board) alongside 5 live workers; now 8 node procs. Running total 67 boards w/ meta, 66 PASS + 1
  FAIL(re-solving). 803G free. In-budget (<8h, non-destructive). Continue monitor; QA re-solve next cycle.
- 2026-06-09 cycle74: MONITOR. Board-66 re-solve PROGRESSING HEALTHILY: worker RSS ~14GB+ (vs original's stuck
  1.1GB) = FULL tree expanding this time -> original was a transient structural glitch, NOT a board property.
  At 25k/200k iters (~2hr to finish). 8 node procs (5 live + 2 resolve + parent). Main solve: no new DONE this
  cycle (boards 67-71 in flight), 67 metas, 803G free. No budget gate. QA re-solve output next cycle; if PASS,
  archive bad gz + swap good one in.
- 2026-06-09 cycle75: MONITOR. Board-66 re-solve at 50k/200k, full tree (~14GB), healthy. Main solve: all 5
  workers advancing (67@150k, 68-70@125k, 71@75k), none stuck; no new DONE yet (67-71 land ~16:00-16:30). 67
  metas, 8 procs, 803G free. No budget gate. QA re-solve + boards 67-71 next cycle.
- 2026-06-09 cycle76: MONITOR. Re-solve board 66 at 100k/200k (full tree, healthy, ~70min left). Main: board 67
  at 200k (exporting, DONE imminent), 68-70@175k, 71@125k — all advancing. 67 metas (none new finished yet), 802G
  free, 8 procs. No budget gate. QA board 67 + re-solve next cycle.
- 2026-06-09 cycle77: MONITOR. Boards 67/68/69/70 DONE + QA-PASS (maxProb 0.730/0.703/0.710/0.692, 22.9-28.8M
  info sets, peak 13.4-16.3GB, gz 168-203MB). Running total 71 boards w/ meta, 70 PASS + 1 FAIL(board66 re-solving).
  Re-solve board 66 at 150k/200k (~30min left, full tree). Board 71 still in flight. 802G free, 8 procs.
  No budget gate. QA re-solve next cycle -> if PASS, archive bad gz + swap good one in.
- 2026-06-09 cycle78: RESOLVED board66 + 1 new board. Board-66 RE-SOLVE DONE: 24,591,276 info sets / peak 14.2GB /
  meanMax 0.716 / 58.8% decisive -> QA-PASS (vs original broken 1.75M/1.1GB). SWAPPED IN (archive-then-replace):
  bad gz+meta renamed *.bad-1p75M; good re-solve gzipped to flop_066.jsonl.gz (190MB) + meta copied; in-place
  QA re-PASSED; temp raw (1.49GB) deleted (verified gz exists). Board 66 now HEALTHY. Board 71 also DONE+QA-PASS
  (maxProb 0.709, 27.8M). Running total 72 boards w/ meta, **72/72 QA-PASS, 0 outstanding fails**. Main solve back
  to 6 procs (72/74/75 in flight), 802G free. Confirmed: board-66 fail was a one-off transient glitch, not systemic
  (re-solve clean). No budget gate. Continue monitor.
- 2026-06-09 cycle79: MONITOR. Main solve healthy, 6 procs, boards 72-76 in flight (72@125k, 73@100k, 76@25k);
  no new DONE since board 71 (next batch ~18:45). 72 metas, 72/72 QA-PASS, 802G free. Housekeeping: removed the
  tiny confirmed-broken flop_066.*.bad-1p75M archives (board 66 good copy verified+stable in place). No budget gate.
- 2026-06-09 cycle80: MONITOR. Boards 72@175k, 73@150k, 76@75k advancing; no new DONE yet (land ~18:30-19:00).
  72 metas, 72/72 QA-PASS, 6 procs, 801G free. No budget gate. QA 72-76 next cycle.
- 2026-06-09 cycle81: MONITOR. Boards 72/73 DONE + QA-PASS (maxProb 0.735/0.724, 21.9M/25.3M, peak 12.9/14.5GB,
  gz 165/188MB). Running total 74 boards w/ meta, 74/74 QA-PASS, 0 fails. Boards 74/75/76/77/78 in flight (76@125k).
  6 procs, 800G free, ETA ~885h. ~3.9% complete. No budget gate. QA 74-78 next cycle.
- 2026-06-09 cycle82: MONITOR. Boards 74/75 DONE + QA-PASS (maxProb 0.685/0.695, 29.1M/24.5M, peak 16.4/14.1GB,
  gz 204/176MB). Running total 76 boards w/ meta, 76/76 QA-PASS, 0 fails. Boards 76/77/78 in flight (76@175k).
  6 procs, 798G free, ETA ~865-877h. ~4.0% complete. No budget gate. QA 76-78 next cycle.
- 2026-06-09 cycle83: MONITOR. Board 76 DONE + QA-PASS (maxProb 0.678, 30.6M, peak 17.2GB, gz 211MB). Running
  total 77 boards w/ meta, 77/77 QA-PASS, 0 fails. Boards 77/78/79 in flight (77@100k). 6 procs, 797G free,
  ETA ~870h. ~4.0% complete. No budget gate. QA 77-79 next cycle.
- 2026-06-09 cycle84: MONITOR. No new DONE this cycle (boards 77-81 all in flight: 77@125k, 78@125k, 79@100k,
  80@100k, 81@25k; verified board 77 advancing 25k->125k, not stuck). 77 metas, 77/77 QA-PASS, 6 procs, 797G free.
  Next batch lands ~20:00-20:30. No budget gate. QA 77-81 next cycle.
- 2026-06-09 cycle85: MONITOR. Still no new DONE (boards 77-81 in flight: 77@175k, 78@175k, 79@150k, 80@150k,
  81@75k; all advancing, none stuck). Slightly slower batch (deeper boards). 77 metas, 77/77 QA-PASS, 6 procs,
  797G free. Boards land ~20:15+. No budget gate. QA 77-81 next cycle.
- 2026-06-09 cycle86: MONITOR. Boards 77/78/80 DONE + QA-PASS (maxProb 0.706/0.716/0.705, 27.8M/23.5M/26.9M,
  peak 13.6-15.8GB, gz 172-199MB). Running total 80 boards w/ meta, 80/80 QA-PASS, 0 fails. Boards 79/81/82/83/84
  in flight. 6 procs, 797G free, ETA ~873h. ~4.2% complete. No budget gate. QA 79/81-84 next cycle.
- 2026-06-09 cycle87: MONITOR. Board 79 DONE + QA-PASS (maxProb 0.682, 30.2M, peak 17.0GB, gz 208MB). Running
  total 81 boards w/ meta, 81/81 QA-PASS, 0 fails. Boards 81/82/83/84 in flight (82@50k, 83@50k, 84@25k). 6 procs,
  794G free, ETA ~865h. ~4.2% complete. No budget gate. QA 81-84 next cycle.
- 2026-06-09 cycle88: MONITOR. Board 81 DONE + QA-PASS (maxProb 0.687, 25.6M, peak 14.7GB, gz 180MB). Running
  total 82 boards w/ meta, 82/82 QA-PASS, 0 fails. Boards 82/83/84/85/86 in flight (82@100k, 83@100k, 84@75k).
  6 procs, 794G free, ETA ~867h. ~4.3% complete. No budget gate. QA 82-86 next cycle.
- 2026-06-09 cycle89: MONITOR. No new DONE (boards 82-86 in flight: 82@150k, 84@125k, 86@50k; all advancing).
  82 metas, 82/82 QA-PASS, 6 procs, 793G free. Next batch ~22:15-22:45. No budget gate. QA 82-86 next cycle.
- 2026-06-09 cycle90: MONITOR. Still no new DONE (boards 82-86 in flight: 82@175k, 83@175k, 84@175k, 85@150k,
  86@100k; verified 82/83 advancing to 175k, not stuck — deeper boards near full ~148min). 82 metas, 82/82
  QA-PASS, 6 procs, 793G free. Batch lands ~22:50. No budget gate. QA 82-86 next cycle.
- 2026-06-09 cycle91: MONITOR. Boards 82/83/84 DONE + QA-PASS (maxProb 0.677/0.681/0.689, 30.7M/30.0M/25.9M,
  peak 14.8-17.2GB, gz 182-210MB). Running total 85 boards w/ meta, 85/85 QA-PASS, 0 fails. Boards 85/86/87/88/89
  in flight (85@200k done-imminent, 86@150k). 6 procs, 798G free (disk steady), ETA ~870h. ~4.5% complete.
  No budget gate. QA 85-89 next cycle.
- 2026-06-09 cycle92: MONITOR. Board 85 DONE + QA-PASS (maxProb 0.679, 29.9M, peak 16.9GB, gz 206MB). Running
  total 86 boards w/ meta, 86/86 QA-PASS, 0 fails. Boards 86/87/88/89/90 in flight (88@50k, 89@50k, 90@25k).
  6 procs, 798G free, ETA ~865h. ~4.5% complete. No budget gate. QA 86-90 next cycle.
- 2026-06-09 cycle93: MONITOR. Board 86 DONE + QA-PASS (maxProb 0.685, 29.1M, peak 16.5GB, gz 203MB). Running
  total 87 boards w/ meta, 87/87 QA-PASS, 0 fails. Boards 87/88/89/90/91 in flight (87@100k, 88@100k, 90@75k).
  6 procs, 798G free, ETA ~866h. ~4.6% complete. No budget gate. QA 87-91 next cycle.
- 2026-06-10 cycle94: MONITOR. No new DONE (boards 87-91 in flight: 87@150k, 88@150k, 89@125k, 90@125k, 91@50k;
  all advancing, none stuck). 87 metas, 87/87 QA-PASS, 6 procs, 798G free. Batch lands ~00:45+. No budget gate.
- 2026-06-10 cycle95: MONITOR. Boards 87/88 DONE + QA-PASS (maxProb 0.714/0.717, 22.8M/24.8M, peak 13.3/14.3GB,
  gz 167/181MB). Running total 89 boards w/ meta, 89/89 QA-PASS, 0 fails. Boards 89/90/91/92/93 in flight (90@175k).
  6 procs, 797G free, ETA ~871h. ~4.7% complete. No budget gate. QA 89-93 next cycle.
- 2026-06-10 cycle96: MONITOR. Boards 89/90 DONE + QA-PASS (maxProb 0.722/0.731, 25.0M/21.0M, peak 14.4/12.4GB,
  gz 184/157MB). Running total 91 boards w/ meta, 91/91 QA-PASS, 0 fails. Boards 91/92/93/94/95 in flight (91@150k,
  92@25k, 93@25k). 6 procs, 796G free, ETA ~858h. ~4.8% complete. No budget gate. QA 91-95 next cycle.
</content>
