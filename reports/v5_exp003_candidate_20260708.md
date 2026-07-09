# V5 EXP-003 Candidate Package (No Cutover)

- Timestamp: 2026-07-08 13:53 EDT
- Candidate trainer: `scripts/alpha_holdem/train_v5_exp003.py`
- Test: `scripts/alpha_holdem/test_exp003_variance.py`
- Live trainer touched: no
- Active run touched: no

## 2026-07-09 Bounded-K Superseding Note

The earlier "positive cap skips EV replacement" design is superseded. `train_v5_exp003.py`
now uses deterministic bounded-K runout averaging when exact missing-board runouts exceed
`--allin-runout-ev-max-runouts`; high-runout all-ins are replaced by K-runout EV instead of
being skipped. The exact cutover-reviewed flags are:

```text
--mirror-self-play-deals --allin-runout-ev --allin-runout-ev-max-runouts 200
```

Current review artifact: `reports/v5_exp003_bounded_k_adversarial_review_20260709.md`.

## Scope

EXP-003 implements the registered R3 variance-reduction package behind default-off flags:

- `--mirror-self-play-deals`: in self-play only, each shuffled deal is replayed once with P0/P1 hole cards swapped while preserving future board/runout order.
- `--allin-runout-ev`: when both players are all-in before river, terminal payoff is replaced with exact expected profit over all missing board runouts.
- `--allin-runout-ev-max-runouts`: optional safety cap added after offline smoke exposed preflop exact-EV cost. Default `0` preserves the original exact/unbounded behavior. A positive cap skips EV replacement for all-ins whose exact enumeration would exceed the cap and leaves the sampled payoff in place.

Both flags default off. Without flags, the candidate should match current EXP-002 behavior.

## 2026-07-09 Registration Amendment

This amendment supersedes the older vloss/quick5k gate for deciding an EXP-003 cutover.
It does not authorize a live cutover.

- Hypothesis: mirrored self-play deals plus all-in runout EV reduce outcome variance enough for the critic to learn a calling game, addressing the formal/promotion loss shape with 0% BB-call, high SB-open fold, and large hero-fold losses.
- Precondition: capture the clean stable-coef-0.01 mirror curve first. The recovery mirror after formal100k and the second mirror near 340M must both exist before any EXP-003 cutover decision.
- Cutover gate: only at a PASS gate boundary after the two stable-coef-0.01 mirror points are recorded. Archive the live trainer, copy the isolated EXP-003 trainer, preserve EXP-002 multi-env flags, and enable only the registered EXP-003 flags.
- Judgment gate: over at least 30M post-cutover hands, the EXP-001 mirror-vs-V4 result must improve beyond the combined CI versus the pre-cutover recovery curve. Health must remain PASS, real h/s must not drop more than 20%, and the next official Slumbot bundle must have complete CI, loss report, artifact audit, and hand review.
- Abort: real h/s drop greater than 20%, stream-validation failure, deterministic trace mismatch, mirror regression beyond CI, artifact audit failure that cannot be repaired honestly, or preflop policy collapse worse than the stable-coef baseline.
- Rollback: revert to the archived stable-coef-0.01 checkpoint and prior live trainer, then rearm watchers only through `scripts/alpha_holdem/v5_rearm_watchers.ps1`.
- Current status: OFFLINE_ONLY. Step-3 prior decay remains BLOCKED_ON_EXP003.

## Validation Completed

- `python -m py_compile scripts\alpha_holdem\train_v5_exp003.py scripts\alpha_holdem\test_exp003_variance.py`: PASS.
- `python scripts\alpha_holdem\test_exp003_variance.py`: PASS.
- No-flag trace equivalence vs current `train_v5.py`, W=1 single mode, 64 hands / 199 transitions: PASS.
- No-flag trace equivalence vs current `train_v5.py`, W=1 multi(M=1), 64 hands / 199 transitions: PASS.
- Mirror-only trainer smoke, W=1 multi(M=1), self-play fraction 1.0, stream validation on: PASS; train log reported `mirror=25/25`, 50 hand markers.
- 2026-07-09 unbounded both-flags resume smoke from trained checkpoint copy: completed but too slow for cutover (`50` hands, collect `204.8s`, `aiev=5:5137946`). This is an EXP-003 performance risk, not a live-run change.
- 2026-07-09 capped both-flags resume smoke from trained checkpoint copy with `--allin-runout-ev-max-runouts 1000`: PASS (`50` hands, collect `3.5s`, `mirror=25/25`, `aiev=3:1078`, `aiev_skip=1:1712304`).
- 2026-07-09 deterministic seedcheck, W=1 multi(M=1), CPU, mirror deals on, stream validation on: PASS. Two independent scratch runs produced identical `trace.txt` SHA256 `533B46B8C49D98A0792CEEDEF5E9E1944BEEC1DFCD23B7E4E99E81E9C6C8372E` and empty stderr.
- 2026-07-09 adversarial review artifact: `reports/v5_exp003_adversarial_review_20260709.md`. Verdict: OFFLINE_ONLY_NOT_CUTOVER_APPROVED; the main unresolved cutover risk is unbounded preflop exact all-in EV cost, or a behavior-amending cap if capped mode is chosen.

## Hashes

- `train_v5_exp003.py`: `D110187884A394772FD1C6A3EA0112E135AC7C160E93D5977A5B9E55C8BC71E0`
- `test_exp003_variance.py`: `80FCEE99240824358897BB894F8B1FD827BE2D72BDEA6049AA69C8A5C684AC8C`

## Remaining Before Cutover

- Do not cut over while rollback recovery validation and 250M Slumbot bundles are pending.
- If using unbounded exact all-in EV, optimize preflop enumeration before cutover; current unbounded smoke is too slow.
- If using a positive `--allin-runout-ev-max-runouts`, append an EXP-003 amendment row before cutover because capped preflop all-ins retain sampled payoff instead of exact EV.
- Judge the registered abort gate strictly: real h/s drop greater than 20% aborts/reverts.
- Cutover, if later authorized, must happen only at a PASS gate boundary with archived checkpoint and append-only Ops rows.
- Before any cutover, rerun adversarial review against the exact cutover flags and the then-current live trainer hash.
