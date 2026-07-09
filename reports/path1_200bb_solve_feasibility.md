# Path-1 Feasibility — 200bb CFR Solve (scope/cost) (2026-06-07)

Supervisor cycle 11 (idle, E gated). Read-only scoping to make the recommended path-1 decision concrete
BEFORE the user funds it. No compute, no solve launched, no gate crossed. Sources: `tree-config.ts`,
`solve-v3-parallel.ts`, `df`, MEMORY pipeline notes.

## Why path-1: it targets the actual leak
Cycle-10 reconciliation: the -45 ceiling is **OOP postflop equity realization at ~200bb depth** (97.5%
of teacher decisions are SRP; 98.9% are ~200bb-deep). A 200bb **SRP** solve produces a correct OOP-postflop
strategy in exactly the dominant regime → a depth-correct teacher to re-BC (or distill). This is the only
"stronger teacher" that isn't falsified (cheap hand-written preflop widen = falsified by v2, cycle-10).

## Minimal scope = ONE config (SRP V3 @ 200bb)
Configs are cleanly parameterized (startingPot / effectiveStack / betSizes / raiseCapPerStreet). Need:
- **New config** `PIPELINE_SRP_V3_200BB` = V3 SRP but `effectiveStack: 197.5` (vs 47.5 @50bb / 97.5 @100bb).
- Small code: a `getConfigOutputDir` entry + `STACK_LABEL` handling in `solve-v3-parallel.ts` (currently
  only branches '100bb' vs default '50bb'). ~10-line diff, not algorithmic.
- 3-bet pots (1.8% of decisions) can be skipped → SRP-only covers the dominant 97.5%.

## Cost — three hard constraints (all push past gates)
| resource | 50bb V3 (ref) | 100bb SRP (ref) | **200bb SRP (est.)** |
|---|---|---|---|
| disk (raw) | ~300GB (deleted) | **743.8GB** | **~1TB+** |
| RAM/board | ~4.6GB peak | 3.9-6.8GB; hit V8 Map 16.7M limit → bucketCount=50 | **>per-worker 6GB heap → forces bucketCount=50 + 32GB fork solver, low parallelism** |
| wall time | ~16 flops/hr (16 workers) | ~20min/board | **multi-day to ~1-2 weeks** (deeper tree, low parallelism, restarts) |

- **Disk is a hard blocker:** only **814GB free**; a ~1TB+ raw solve does not fit. Requires either (a)
  freeing/relocating ~1TB, or (b) streaming straight to presampled training data with
  `--samples-per-bucket 1` (the known V3 disk trick) so raw is never fully materialized.
- **Memory:** 200bb depth blows the V8 Map limit broadly → must run the fork solver (32GB heap/board),
  which serializes boards and is what drives the multi-day/weeks estimate.
- **EV note:** policy export uses the existing format (no node EV). Path-1-as-**teacher** (re-BC/distill)
  needs only policy → ready. Path-1-as-**critic (E1)** additionally needs EV-export added to the solver.

## Cheaper alternative to surface — path-1b: real-time subgame resolving (no offline solve)
The repo already ships a **Pluribus-style real-time resolver** (`apps/bot-client/src/realtime-resolver.ts`,
StreetSolver via WASM, 11x speedup) wired into the bot. Running it at 200bb depth solves the *actual*
OOP-postflop subgame at decision time — attacking the same leak **without** the ~1TB / weeks offline solve.
Cost shifts to per-decision latency, not offline compute/disk. Caveat: it's on the TS bot-client path, not
the AlphaHoldem RL agent; using it as the Slumbot agent (or to generate a depth-correct teacher dataset
offline) is a smaller integration than a full 200bb solve. **Likely the cheapest route to the OOP-postflop fix.**

## Recommendation (refined)
1. **Path-1b first (real-time resolver @200bb)** — far cheaper (no 1TB/weeks solve); reuses an existing,
   tested asset; directly addresses OOP postflop. Try as a Slumbot agent and/or as a teacher-data generator.
2. **Path-1 full 200bb SRP solve** — principled and reusable, but a ~1TB / multi-day-to-weeks / fork-solver
   commitment that **does not fit current free disk** (needs ~1TB; 814GB free). Fund only if 1b underdelivers.
3. **Path-3 (new RL at depth)** — keep as alt; PPO-from-BC dead, needs a new idea.

## ASK (sharpened, with a cheaper lead)
Before I touch any gated build: do you want me to **prototype path-1b** (point the existing real-time
resolver at 200bb and bench a small Slumbot sample) — which is in-budget and non-destructive — OR fund the
full path-1 200bb solve (gated: >8h, ~1TB disk, fork solver)? Recommend starting with **path-1b**.

## Budget / gates
- This cycle: zero compute / zero API; read-only config+script+disk reads. No gate crossed; new report only.
- Path-1 full solve = gated (>8h / artifact scale / direction). Path-1b prototype = arguably in-budget
  (no training, small bench) but it is the first real "build" after a long hold → surfacing for a quick
  go-ahead rather than starting unilaterally.

## CYCLE-12 CORRECTION — path-1b is NOT a cheap prototype (checked before building)
Inspected the resolver + Slumbot harness before proposing to run path-1b. Three blockers downgrade it:
1. **No TS-side Slumbot client exists** (`grep slumbot apps/ packages/ --ts` = empty). Slumbot API lives
   only in Python `play_slumbot.py` (`requests` → slumbot/api). Benching the TS resolver vs Slumbot needs a
   new TS client or a Python↔TS bridge = real integration, not a flag.
2. **Resolver caps at 100bb.** `ScenarioKey = srp_50bb|srp_100bb|3bet_50bb|3bet_100bb`
   (`realtime-resolver.ts` L81); there is **no 200bb scenario**, and `selectScenario()` maps only to those.
   "Point it at 200bb" is not a flag — a 200bb scenario + 200bb StreetSolver configs must be built first.
3. **Its transition value-nets are the same ≤100bb CFR nets.** Even the realtime path bottoms out on the
   ≤100bb asset gap at every street boundary.
=> The 200bb gap is **structural across BOTH** the offline solve (path-1) AND the realtime resolver
   (path-1b). Path-1b is a *downstream consumer* of 200bb CFR/VN assets, not a cheaper way to avoid building
   them. My cycle-11 "path-1b likely cheapest" was too optimistic — corrected.

## CONVERGED conclusion (after 6 zero-compute cycles)
The -45 ceiling = OOP postflop realization at 200bb, and **every** fix requires building **200bb-native
CFR/VN assets** first; all our CFR/VN assets are ≤100bb. There is NO remaining cheap/in-budget path.
- **Build 200bb CFR/VN assets** (the gated offline solve, ~1TB/weeks) → unlocks BOTH the re-BC teacher AND
  the realtime resolver (path-1b becomes usable downstream). Single highest-leverage funded investment.
- **Path-3 (new RL idea at depth)** as the alternative; PPO-from-BC is dead.
Recommend funding the **200bb asset build** — it is the common prerequisite the whole solver-based program
needs. Still STOPPED pending the user; nothing built (avoided a second dead prototype).
