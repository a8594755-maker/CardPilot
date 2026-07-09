# V5 Training Method Audit — 2026-07-06

Author: Claude (Fable 5). Audience: Codex and any agent operating the V5-from-zero run.
Scope: code-level audit of the ACTIVE training system (`train_v5.py` + `environment_v55.py` +
`train_mp3.py::trinal_clip_ppo_update` + `deep_cfr/game_state.py`), grounded in the live run's
logs and Slumbot evidence as of 145M hands.

Companion documents:
- `reports/v5_method_improvement_roadmap.md` — what to do about each problem, ranked.
- `docs/V5_TRAINING_PLAYBOOK.md` — HOW to apply changes with discipline.
- `reports/v5_experiment_ledger.md` — pre-registered experiments.

## Evidence base (measured, not guessed)

From `latest_train.log` iterations ~8854-8856 (145.3M hands):

```
collect=39-46s  ppo=3.6-4.3s        -> rollout collection is ~91% of wall time
h/s=355-422 (in-iter), ~600 effective (dashboard)
inf_bs=8.8-9.9 out of 28 workers    -> GPU inference batch ~10; GPU mostly idle
vloss=1828-2288                      -> value RMSE ~45 bb/hand at 145M hands
ent=1.35-1.41                        -> policy still highly stochastic (ln(9)=2.20 max)
kl=0.035-0.044, clipfrac=0.19-0.25  -> per-update KL on the high side for PPO
aprior=2.33 (active)                 -> 3 stacked action priors currently shaping the loss
```

Slumbot official quick5k history (greedy, 5k hands, CI ±40-60 bb/100):
50M -76.2 | 59M -58.8 | 62M -82.5 | 65M -73.8 | 72M -122.7 | 75M -71.5 | 100M -85.0.
Statistically flat. No milestone has beaten V4's -49.7 ± 21.9 (20.4k hands).

At effective ~600 h/s, 2.7B hands requires **~52 days** of uninterrupted training.
That alone makes throughput a first-class problem, not an optimization nicety.

---

## Part 1 — Throughput problems (why we only get ~600 h/s)

### S1. One env per worker + per-decision round-trip (CRITICAL)

`train_v5.py::worker_process_v5` runs exactly ONE environment per process. Every single
decision requires a full round trip:

```
worker: write obs to shm -> set WAITING -> poll loop (sleep 1µs)
main:   poll all workers -> batch waiting (typically ~10) -> GPU forward -> write results
worker: read result -> env.step() (pure Python) -> encode next obs -> repeat
```

Consequences:
- GPU sees batches of ~10 (`inf_bs=9.9`) on an 8.15M-param net. Forward on batch 10 vs
  batch 500 costs nearly the same wall time; we waste >95% of GPU inference capacity.
- While a worker steps its env (Python game engine), it requests nothing — the GPU idles.
  While it waits for inference, its CPU core idles. No pipelining in either direction.
- Two poll loops per decision (`time.sleep(0.000001)` in worker, `time.sleep(0.00001)` in
  main at `train_v5.py:1260`). On Windows, actual sleep granularity depends on timer
  resolution and Python version; measure before assuming, but poll latency is on the
  critical path of EVERY decision.

This is the single biggest structural limit. Fix = batched multi-env rollout (see roadmap R1).

### S2. Python game engine does redundant work per decision (HIGH)

- `game_state.py:374 apply()` **clones the entire state on every action** — copies the deck
  (52-card list), action history, stacks, street state. A 200bb hand with bet wars has
  10-20 actions -> 10-20 full clones per hand.
- `environment_v55.py:108 encode_action_history()` calls
  `game_state.py:498 get_actions_by_street()`, which **replays the whole action history from
  scratch on every observation**. O(N) per decision -> O(N²) per hand, plus rebuilding the
  full (25,4,5) tensor in Python loops each time.
- `encode_cards()` rebuilds the (6,4,13) tensor per decision even though hole cards never
  change and board changes only on street transitions.
- `deal_new_hand()` shuffles a full 52-card deck to consume at most 9 cards.
- Both-player collection doubles the per-decision `ci.copy(), ai.copy(), ...` cost
  (`train_v5.py:292-295`) — this is the V5.0 regression already documented in HANDOVER.md.

None of this is algorithmically necessary. Incremental encoding + in-place stepping is a
2-4x CPU-side win (roadmap R2).

### S3. Transition transport via pickled pipes (MEDIUM)

Workers accumulate Python tuples of numpy arrays and `pipe.send()` every 50 hands
(`train_v5.py:340-345`). Each send pickles ~thousands of small arrays; main unpickles and
appends to a Python list, then `trinal_clip_ppo_update` re-packs everything with
`np.array([t[0].reshape(...) for t in transitions])` (`train_mp3.py:359-369`). A shm ring
buffer with preallocated float32 blocks eliminates ~all of this (roadmap R2b).

### S4. PPO update details (LOW — only ~9% of wall time)

- fp32 only; `bf16` autocast exists in `trinal_clip_ppo_update` but `train_v5.py` never
  passes it.
- Full re-tensorization of the iteration buffer each update.
Not worth touching until S1/S2 are fixed and PPO becomes a visible fraction of time.

---

## Part 2 — Training-method problems (why 100M hands are flat vs Slumbot)

### M1. Zero variance reduction on an extremely high-variance signal (CRITICAL)

Terminal reward spans ±200 BB; vloss ≈ 2000 means the critic's per-hand RMSE is ~45 BB —
the advantage signal is dominated by dealt-card luck, not decision quality.
The two standard poker fixes are both absent:

- **Mirrored (duplicate) deals in self-play.** Play each deal twice with seats swapped
  within the same worker; the shared luck component cancels in the average gradient.
  In self-play this is nearly free and is the classic poker evaluation/training trick.
- **All-in runout EV.** When both players are all-in before the river, the remaining board
  is pure luck. Replacing the sampled runout reward with exact equity (or a K-runout
  average) removes that variance entirely. The 100M hand review shows `allin_runout`
  bucket at -5454 bb/100 on 11 hands — pure noise injected straight into the gradient.

This was already identified as V5.2's "HIGHEST PRIORITY for variance" in the old V5 plan
(PROJECT_STATUS.md §12) and then never implemented. It is the highest-EV method change
available (roadmap R3).

### M2. `loss-kbest` pool selection does not measure strength (HIGH)

`train_v5.py:124 selection_loss_from_stats` ranks snapshots by
`policy_loss + 0.5*log1p(value_loss)` computed **on the training iteration in which the
snapshot was taken**. Problems:

- PPO policy loss magnitude reflects the size of the current update, not the policy's
  poker strength. Value loss reflects the current data mix. Neither is a strength ranking.
- The paper's K-best is an ELO survivor selection — an explicitly *competitive* criterion.
- Failure mode: pool keeps snapshots from calm/passive iterations and evicts genuinely
  stronger ones; the main agent then trains against a weak, unrepresentative pool while
  `rew100 ≈ 0` looks healthy.

A real (cheap) tournament ranking is affordable — see roadmap R4.

### M3. Per-iteration opponent assignment causes distribution lurching (HIGH)

`train_v5.py:1005 assign_opponents()` with `--opponent-assignment per-iteration` puts ALL
28 workers on ONE sampled mode for the whole iteration: this iteration's 16,384 hands are
100% vs snapshot #3, the next 100% self-play, etc. Every PPO update therefore ingests data
from a single opponent distribution that changes discontinuously between updates.

This was adopted purely for inference batching (2.3x throughput, documented in
`v5_from_zero_contract.md`) but it plausibly explains the observed instability:
internal probes swinging ±800 bb/100 between gates, preflop guardrail warnings
oscillating 0→7→0→7, vloss bouncing. Group assignment recovers the batching win without
the single-opponent-per-update pathology (roadmap R5).

### M4. Stacked action priors fight the RL objective (HIGH — active deviation)

The run currently trains with three interventions stacked
(`after4000_aprior002 + after4400_preprior001 + after4600_preprior002_call36`), visible as
`aprior=2.33` in the live log. These cross-entropy terms push the policy's
fold/call/raise/all-in class masses toward hand-crafted targets (e.g. SB open raise 63%)
**unconditionally on hand strength** — the cheapest way for the network to satisfy them is
to raise more with EVERYTHING, not to raise the right hands.

Evidence they are not working:
- Official quick5k after interventions: 75M -71.5 → 100M -85.0 (flat/worse).
- Preflop guardrail warnings oscillate violently between gates (0↔7), consistent with the
  prior term and the PPO term pulling in opposite directions.
- Entropy stuck at 1.35-1.41 at 145M hands — the priors (plus entropy boost) keep the
  policy diffuse; the paper's agent sharpens far more.

The SB limp-heavy leak the priors were meant to fix is better explained by M1 (the value
signal is too noisy to distinguish open-raise EV from limp EV) than by a missing prior.
Recommendation: decay priors to 0 as a registered experiment (roadmap R6).

### M5. Entropy control is a bang-bang controller (MEDIUM)

`trinal_clip_ppo_update` (`train_mp3.py:625`) multiplies entropy_coef by 5.0 whenever
minibatch entropy < 0.3. Combined with base coef 0.05 this is a crude oscillator: nothing
until the floor, then a hammer. There is no schedule that lets the policy sharpen as
training progresses — one reason entropy sits at 1.35+ deep into the run. A linear decay
of entropy_coef with progress (with the floor kept as a safety net) is the standard fix.

### M6. Per-update KL is high (MEDIUM)

kl=0.035-0.044 with clipfrac 0.19-0.25 means each update moves the policy substantially;
combined with M3's per-iteration distribution shifts this compounds instability. Standard
mitigation: early-stop PPO epochs within an update when approx_kl exceeds ~0.03 (one `if`
in the epoch loop; zero risk).

### M7. Value scale / cold start (MEDIUM)

Returns are in BB (±200). Trinal-Clip bounds returns per-trajectory to
[-hero_chips, +villain_chips] (correct per paper Eq. 4), but the raw scale still makes
Adam step-size tuning awkward and slows early critic learning (this project has already
diagnosed value-head cold-start as a blocker in the RL-1 era). Options: train the value
head on reward/200 (rescale δ2/δ3 identically; rescale at GAE too — pure reparam, no
semantic change), or Huber loss on the clipped target.

### M8. Observation defect: history amounts normalized by CURRENT pot (LOW-MEDIUM)

`environment_v55.py:146`: `tensor[channel,2,0] = min(action.amount / max(state.pot,1), 2)/2`
uses `state.pot` at ENCODING time. The same historical bet's encoded fraction shrinks as
the pot grows during the hand — the network cannot recover the true historical pot
fraction. Fix requires storing pot-at-action-time (obs change → new env version, invalidates
nothing about the run but requires a registered obs_version bump, i.e. V6 territory).
Also documented: `MAX_ACTIONS_PER_STREET=6` silently drops overflow actions in extreme
bet wars.

### M9. Evaluation cadence cannot steer training (HIGH — process, not code)

- quick5k CI is ±40-60 bb/100: consecutive milestone deltas (e.g. -13.6) are pure noise.
- Internal probes are 200 hands vs scripted opponents: CI ±800 bb/100 — unusable except
  as smoke detection, yet their verdicts (`REGRESSION_RISK_INTERNAL`) drive review noise.
- Result: the loop generates interventions (M4) off signals that cannot support them.

Fix: mirrored-deal internal evaluation vs FROZEN anchors (V4 final; best prior V5
checkpoint) with 10k+ duplicate hands — variance drops roughly an order of magnitude and
gives a real between-Slumbot progress signal (roadmap R7). Slumbot quick5k stays as
calibration; 20k/100k stays as the only claim path.

### M10. Snapshot cadence + K=5 give a narrow opponent history (LOW)

Snapshots every 200 iters ≈ 3.3M hands; K=5 spans ~16M hands. The agent only ever trains
against its recent selves (plus 20% self-play). Adding one or two long-lag snapshots
(e.g. keep a 50M-hand-old member) is cheap diversity insurance. Ablation-grade, not urgent.

---

## Part 3 — Things checked and found OK (do not "fix" these)

- **GAE over the flat transition buffer** (`train_mp3.py:320`): per-player trajectories are
  contiguous and each ends with done=1, so bootstrap resets are correct across the
  concatenated buffer, including both-player self-play collection.
- **Terminal reward perspective**: worker converts last-actor reward to per-player sign
  correctly (`train_v5.py:307-310`).
- **Trinal-Clip policy loss** (`train_mp3.py:584-604`): inner ε-clip + δ1 cap applied only
  when advantage < 0 — matches paper Eq. 3. Value bounds from committed chips match Eq. 4.
- **Hand accounting**: `hand_marker` counts actual poker hands once (the 13:46 run's
  inflation bug is fixed in the active run).
- **Split shm assigned/request**: the V4 race is fixed; assignment is read once per hand.
- **Fresh-from-zero lineage plumbing**: checkpoints carry lineage; gates verify it.
- **Seat alternation**: `hero_player = hands_played % 2` balances positions in opp mode.

## Bottom line

The run is healthy but under-instrumented for progress and over-instrumented for noise:
it burns 91% of wall time on an unbatched Python rollout path (~600 h/s → 52 days to
paper scale), trains on a signal dominated by card luck (no mirroring, no all-in EV), uses
a pool ranked by a non-strength proxy, feeds PPO single-opponent iterations, and carries
three hand-crafted priors that evidence says are not helping. Every one of these has a
concrete, testable fix in `reports/v5_method_improvement_roadmap.md`.
