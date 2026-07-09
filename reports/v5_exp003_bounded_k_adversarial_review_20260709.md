# V5 EXP-003 Bounded-K Adversarial Review

- Timestamp: 2026-07-09 09:50 EDT
- Scope: `scripts/alpha_holdem/train_v5_exp003.py`, `scripts/alpha_holdem/test_exp003_variance.py`
- Live trainer touched: no
- Active run touched: no
- Verdict: OFFLINE_VALIDATION_PASS_CUTOVER_ALLOWED_ONLY_AT_PASS_GATE_BOUNDARY

## Change Reviewed

EXP-003 all-in runout EV no longer skips high-cardinality preflop/flop all-ins when `--allin-runout-ev-max-runouts` is positive. If exact missing-board runouts exceed K, it now samples K deterministic runouts keyed by hole cards and pre-board, then replaces the terminal sampled payoff with that bounded-K EV. Exact enumeration is still used when total runouts are <= K, and `K=0` remains an explicit exhaustive mode for offline use only.

Cutover flags reviewed:

```text
--mirror-self-play-deals --allin-runout-ev --allin-runout-ev-max-runouts 200
```

## Evidence

- `python -m py_compile scripts\alpha_holdem\v5_mirror_eval.py scripts\alpha_holdem\train_v5_exp003.py scripts\alpha_holdem\test_exp003_variance.py`: PASS.
- `python scripts\alpha_holdem\test_exp003_variance.py`: PASS.
- Native-anchor mirror default smoke: PASS; default anchor `v55_native_75M_quick5k`, anchor OOD `0.0000`, OOD gate VALID.
- Bounded-K both-flags CPU smoke from frozen active checkpoint copy: PASS; 50 hands, `mirror=25/25`, `aiev=6:1200`, `aiev_skip=0:0`, `h/s=8`.
- Same-config CPU baseline without EXP-003 flags: 50 hands, `h/s=7`; bounded-K smoke ratio `8/7 = 1.14`, so the offline h/s abort gate did not trip.
- Determinism seedcheck: two W=1/M=1 CPU runs with the same seed and cutover flags produced identical trace SHA256 `253ABC2859E94C68C8440C2255AADDF2EC4C0A3A8EEACE486D3E2C95A2ED38EF`.
- Unit coverage now includes full preflop all-in bounded averaging with K=100, deterministic repeatability, and actor-0/actor-1 zero-sum symmetry.

## Findings

- No remaining blocker from the prior exact-EV cost issue: bounded K=200 replaced the old skip behavior and kept `aiev_skip=0:0` in the trained-checkpoint smoke.
- No deterministic-seeding regression found in the reviewed W=1/M=1 path.
- No h/s regression found in the offline CPU smoke. This does not replace the live post-cutover h/s abort gate because GPU/live worker scheduling differs.
- The high-runout EV is now a deterministic Monte Carlo estimate, not exact exhaustive EV. This is an explicit EXP-003 amendment accepted for throughput; K can be raised later only through a separate gate if live h/s has margin.

## Required Live Guards

- Cut over only at a PASS gate boundary.
- Archive the pre-cutover live trainer and checkpoint before copying the EXP-003 trainer into the live `train_v5.py` path.
- Preserve current EXP-002 multi-env flags and stable prior floor: preflop coef `0.01`, postflop coef `0.02`; no further prior decay.
- Abort/rollback if live real h/s drops more than 20%, health fails, stderr is nonempty, EXP-003 counters are absent after self-play hands, or `aiev_skip` becomes nonzero under the reviewed K=200 mode.
- Judge EXP-003 by postflop bet-frequency movement and fixed native-anchor mirror improvement beyond CI over at least 50M hands; do not use quarantined V4-anchor mirror numbers.
