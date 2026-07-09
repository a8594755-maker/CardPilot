# BB Over-Fold: Mechanism + Reconciliation (2026-06-07)

Supervisor cycle 10 (idle, E gated). Followed the cycle-9 leak localization (BB -68 bb/100, early-street)
down to the mechanism, THEN reconciled it against existing benches before proposing any build. Zero
compute (dump mining + reading existing summaries). No Slumbot API, no gate.

## Mechanism (zero-compute, from heuristic_v3 dumps + source)
- BB hero **folds 71.6% of hands preflop** (7,307 / 10,200), each forfeiting exactly 1bb → that fold
  bucket alone = **-100 bb/100, 105% of the total BB loss**. Played BB hands (3bet/defend) ≈ breakeven.
- Source confirms by design: `heuristic_policy_v3.py` BB branch = *"PLAYABLE_21 → 3-bet/jam, else fold,
  no flat-call"* (line 156-161). BB defends only the top ~21%, purely by 3-betting.

## Reconciliation — the cheap fix is ALREADY FALSIFIED
The obvious fix ("defend wider / add BB flat-calls") was already tried and is WORSE at full scale:

| heuristic | BB strategy | Slumbot bb/100 (20k hands) |
|---|---|---|
| heuristic_v2 | **BB flat-call (wide defense)** | **-59.06** |
| heuristic_v1 (baseline) | — | -51.04 |
| heuristic_v3 | polarized 3bet/fold (no flat) | -51.54 |
| heuristic_v3_1 | polarized + jam-first sizing | **-49.09** (best heuristic) |
| BC anchor (imitates v3) | — | -44.74 (best overall) |

**v2's wider BB defense scored -59 — 7.5 bb/100 WORSE than v3's polarized fold.** So the 72% BB fold
is largely *correct* given this engine's weak out-of-position postflop play: the extra defended hands
do not realize equity and bleed on the flop (consistent with the cycle-9 BB-flop-terminal = -272 leak).
Polarizing (fold more, jam the defends — v3/v3_1) beats flat-calling wider.

## Corrected conclusion — the binding constraint is OOP POSTFLOP realization, not preflop range
- The over-fold is a real accounting leak, but it is a *symptom*: BB can't profitably defend wider
  because it plays the resulting OOP flops badly. The lever is **postflop OOP equity realization**, which
  is exactly what a hand-written heuristic does worst and what a solver does well.
- Therefore a **cheap preflop-widening v4 would regress** (v2 already proved it). I did NOT build it.
- This re-ranks the gated paths for the DOMINANT leak:
  - **Path-1 (200bb CFR solve)** — gives a correct OOP-postflop strategy at the right depth → directly
    attacks the binding constraint. Now the **most aligned** funded path (was tied on "principled").
  - **Path-3 (RL at depth)** — could also learn OOP realization, but PPO-from-BC is dead; needs a new idea.
  - **Path-2 (stronger hand teacher)** — DOWNGRADED for the dominant leak: a human can't easily hand-code
    strong OOP postflop, and the cheap preflop knob is falsified. Only viable if the "stronger teacher"
    is itself solver/learned (i.e. collapses into path-1/3).

## Net
Two cycles of zero-compute analysis converged: the -45 ceiling is **OOP postflop equity realization**.
Cheap heuristic/preflop fixes are exhausted/falsified. Breaking it needs a strong OOP-postflop signal at
200bb depth → **path-1 (200bb CFR solve) is now the best-aligned funded option**, path-3 second, path-2 out.

## Budget / gates
- This cycle: zero compute / zero API; read-only dump mining + existing-summary reads + one source read.
  No gate crossed; NO new policy built (deliberately avoided rebuilding the falsified v2 idea). New report only.
- Funded paths remain user-gated. STOPPED, awaiting the user's pick — now sharpened to **path-1 (200bb CFR
  solve) recommended** / path-3 (new RL at depth) / path-2 (out, unless solver-backed).

## Artifacts referenced
- `reports/heuristic_v3_leak_localization.md` (cycle-9 position/street split)
- `eval_logs/path_b/heuristic_v2_full_summary.txt` (-59.06), `heuristic_v3_full` (-51.54),
  `heuristic_v3_1_full` (-49.09)
- `scripts/alpha_holdem/heuristic_policy_v3.py` (BB no-flat-call design, line 156-161)
