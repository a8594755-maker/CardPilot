# Heuristic_v3 (= BC teacher) Slumbot Leak Localization (2026-06-07)

Supervisor cycle (idle, E gated). Zero-compute mining of existing per-hand Slumbot dumps to SCOPE
path-2 (build a stronger 200bb teacher → re-BC). Source: `eval_logs/path_b/heuristic_v3_full_part*_dump.jsonl`
(12 sessions, 20,399 hands, heuristic_v3 = the BC anchor's teacher; BC saturates it at 98.6%, so v3's
leaks ≈ the BC anchor's leaks). No training, no Slumbot API, no gate.

## Headline: -51.54 bb/100. Where it comes from
| slice | n | bb/100 | share of total loss |
|---|---:|---:|---:|
| **BB (out of position)** | 10,200 | **-68.21** | **66.2%** |
| SB (in position) | 10,199 | -34.88 | 33.8% |
| terminal-street = preflop | 17,783 | -54.22 | 91.7% |
| terminal-street = flop | 944 | **-240.15** | 21.6% |
| terminal-street = turn | 562 | +64.16 | -3.4% |
| terminal-street = river | 1,110 | +93.10 | -9.8% |
| **BB, flop-terminal** | 613 | **-272.10** | 15.9% |
| BB, preflop-terminal | 8,835 | -60.97 | 51.2% |
| SB, preflop-terminal | 8,948 | -47.55 | 40.5% |

## Read
1. **OOP is the dominant leak.** BB loses 2x what SB loses (-68 vs -35) and is 66% of the bleed.
   The teacher plays the out-of-position (big blind) seat badly vs Slumbot.
2. **The bleed is EARLY-street, not late.** ~92% of the loss is in hands that end preflop, and the
   small set of hands that end on the flop are catastrophic (-240; BB-flop -272). Hands that reach
   turn/river are actually **+EV** (+64 / +93). Translation: when v3 gets deep it wins; it loses by
   getting blown off / stacking off badly **preflop and on the flop**, especially OOP.
3. Therefore a stronger teacher should fix **BB preflop defense ranges + OOP flop play**, NOT river
   precision (already profitable). This is the highest-leverage, most concentrated target.

## Caveats (honest)
- Attribution is whole-hand winnings bucketed by the hand's terminal street — it is directional, not
  per-street EV. "Preflop-terminal" lumps all-in-preflop coolers (variance) with fold-outs.
- Flop/turn/river buckets are small-n (562-1110) → wide CIs on those means; the BB-vs-SB split and the
  early-vs-late concentration are the robust signals (large n).
- `showdown` field in the dump is constant-True → unusable; ignored.

## Use
- Scopes **path-2** (gated): if the user funds a stronger 200bb teacher → re-BC, aim it at **BB/OOP +
  preflop/flop**. A targeted v4 (better BB defense + flop OOP) could plausibly recover a large chunk of
  the -68 BB leak without touching the already-profitable deep-street play.
- Also informs **path-1/3**: any 200bb solve or new RL signal should likewise be weighted to OOP/early-street
  coverage, where the deficiency actually lives.

## Budget / gates
- This cycle: **zero compute / zero API**, read-only dump mining + report. No gate crossed; new artifact only.
- The actual teacher build / solve / RL run remain user-gated. Still STOPPED, awaiting the user's pick
  among the three funded paths (200bb CFR solve / stronger 200bb teacher / new RL direction).
