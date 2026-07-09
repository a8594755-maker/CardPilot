# V5 EXP-003 Adversarial Review (Offline Candidate)

- Timestamp: 2026-07-09 02:13 EDT
- Scope: `scripts/alpha_holdem/train_v5_exp003.py` and `scripts/alpha_holdem/test_exp003_variance.py`
- Live trainer touched: no
- Active run touched: no
- Verdict: OFFLINE_ONLY_NOT_CUTOVER_APPROVED

## Reviewed Claims

1. EXP-003 flags are isolated and default off.
2. Mirrored self-play deals replay a self-play hand with P0/P1 hole cards swapped while preserving the future board order.
3. All-in runout EV replaces only non-fold terminal all-in sampled runouts and keeps existing payoff units.
4. CPU smokes and deterministic seedcheck can catch obvious stream/seed regressions before any cutover.

## Evidence Checked

- Flag isolation: `--mirror-self-play-deals`, `--allin-runout-ev`, and `--allin-runout-ev-max-runouts` are explicit opt-in flags in `train_v5_exp003.py`.
- Mirror implementation: `exp003_mirrored_deck_from_env()` swaps deck entries 0:4 only; `exp003_reset_env_with_deck()` resets the env and writes the mirrored deck before rebuilding obs.
- Board-order basis: the engine deals future board cards via `deck.pop()`, so preserving the tail of the shuffled deck preserves the runout order used by the environment.
- EV replacement guard: `exp003_allin_ev_reward()` refuses folds, non-terminal states, river-complete pre-boards, missing holes, and non-all-in states.
- Reward units: EV uses the same invested-chip convention as `HUNLGameState.payoff()`, and the wrapper big blind is 1.0 in the current 200bb configuration.
- Completed validation: py_compile PASS, unit smoke PASS, no-flag trace equivalence PASS, mirror-only trainer smoke PASS, capped both-flags smoke PASS, and deterministic seedcheck PASS.

## Findings

- P1 CUTOVER BLOCKER: unbounded exact preflop all-in EV is too expensive for live throughput. The observed trained-checkpoint smoke completed only 50 hands with `collect=204.8s` and `aiev=5:5137946`. Do not cut over unbounded exact mode without an optimization or a very small live pilot that satisfies the registered h/s abort gate.
- P1 REGISTRATION RISK: `--allin-runout-ev-max-runouts 1000` makes the smoke fast, but it skips large preflop enumerations and keeps sampled payoff for those hands. That is a behavior amendment relative to "exact all-in EV" and needs an explicit ledger amendment before any live cutover.
- P2 COVERAGE GAP: the unit smoke covers mirror deck preservation and turn exact-EV zero-sum behavior, but it does not yet prove a full preflop all-in average against exhaustive engine payoff paths. This should be added before cutover if unbounded exact mode is still considered.
- P2 METRIC RISK: mirror-deal counters and all-in EV counters exist, but cutover should require they appear in train logs/manifests at nonzero rates and that skipped EVs, if any, are visible.

## Non-Findings

- No evidence that the isolated candidate mutates the active trainer or active run.
- No evidence that default-off flags change current EXP-002 behavior; no-flag equivalence already passed for W=1 single and W=1 multi(M=1).
- No evidence from the reviewed code that mirror replays enter non-self-play opponent-pool hands.

## Required Before Cutover

1. Capture both clean stable-coef-0.01 mirror points from the live rollback run.
2. Decide whether EXP-003 uses exact unbounded all-in EV or a capped/streets-only amendment.
3. If capped or streets-only, append an EXP-003 amendment row before cutover.
4. Rerun py_compile, unit smoke, deterministic seedcheck, no-flag equivalence, and a cutover-flag CPU smoke with the exact flags.
5. Cut over only at a PASS gate boundary, with archived live trainer/checkpoint and watcher rearm only through `scripts/alpha_holdem/v5_rearm_watchers.ps1`.
