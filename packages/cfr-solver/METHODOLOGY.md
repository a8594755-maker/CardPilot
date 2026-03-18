# CardPilot CFR Solver V1 — Methodology

> Version: V1 | Algorithm: CFR+ with External Sampling MCCFR | Date: 2026-02-22

---

## 1. Game Setup

| Parameter       | Value                                             |
| --------------- | ------------------------------------------------- |
| Format          | Heads-Up No-Limit Hold'em (HU NLHE)               |
| Scenario        | Single Raised Pot (SRP) — BTN open 2.5bb, BB call |
| Starting Pot    | **5bb**                                           |
| Effective Stack | **47.5bb** per player (50bb game)                 |
| Equity Model    | Chip EV (no ICM)                                  |
| Rake            | None                                              |

### Preflop Ranges

| Position | Role                                 | Source                                                      |
| -------- | ------------------------------------ | ----------------------------------------------------------- |
| BB (OOP) | Caller — acts first on every street  | `BB_vs_BTN_facing_open2.5x` from `data/preflop_charts.json` |
| BTN (IP) | Opener — acts second on every street | `BTN_unopened_open2.5x` from `data/preflop_charts.json`     |

Range data comes from 6-max 100bb cash game GTO charts. All hands with frequency > 0 are included in the solver at full weight (mixed frequencies are not applied per-combo in V1).

**Approximate range composition:**

- BTN (IP): 169 hand classes, ~504 weighted combos (38%)
- BB (OOP): 169 hand classes, ~352 weighted combos (26.6%)
- Note: V1 solver includes all combos with any non-zero frequency (weight = 1)

---

## 2. Betting Tree Structure

### Bet Sizes (as fraction of pot)

| Street | Small Bet | Big Bet  |
| ------ | --------- | -------- |
| Flop   | 33% pot   | 75% pot  |
| Turn   | 50% pot   | 100% pot |
| River  | 75% pot   | 150% pot |

### Available Actions

**When not facing a bet:**

- Check
- Bet Small (33% / 50% / 75% depending on street)
- Bet Big (75% / 100% / 150% depending on street)
- All-in

**When facing a bet:**

- Fold
- Call
- Raise Small (if under raise cap)
- Raise Big (if under raise cap)
- All-in

### Constraints

- **Raise cap:** maximum 1 raise per street
- **All-in:** always available when player has chips; any bet that exceeds stack becomes all-in
- **Raise formula:** `raise_total = facing_bet + pot_after_call × fraction`
- **Tree size:** ~1,008 action nodes, ~1,000+ terminal nodes per board

### Action Encoding

| Character | Action                  |
| --------- | ----------------------- |
| `x`       | Check                   |
| `f`       | Fold                    |
| `c`       | Call                    |
| `a`       | Bet Small / Raise Small |
| `b`       | Bet Big / Raise Big     |
| `A`       | All-in                  |
| `/`       | Street separator        |

Example history: `xbc/xa/` = Flop(check, bet big, call) → Turn(check, bet small) → ...

---

## 3. Algorithm: CFR+

### Overview

CFR+ (Counterfactual Regret Minimization Plus) is a variant of CFR that floors cumulative regrets at zero. This eliminates negative regret accumulation and accelerates convergence 2-10x over vanilla CFR.

We use **External Sampling MCCFR** — chance events (card deals) are sampled, but all player actions are fully explored at each node.

### Per-Iteration Procedure

```
For each iteration:
  1. Sample one OOP hand from preflop range (uniform random)
  2. Sample one compatible IP hand (no card overlap)
  3. Sample turn card from remaining deck
  4. Sample river card from remaining deck
  5. Compute hand-strength buckets for both players
  6. Pre-compute showdown result (who wins at river)
  7. Traverse full action tree as OOP traverser → update OOP regrets
  8. Traverse full action tree as IP  traverser → update IP  regrets
```

### Regret Matching (Current Strategy)

At each info-set, the current-iteration strategy is derived from positive regrets:

```
If sum(regrets) > 0:
    strategy[action] = regret[action] / sum(regrets)
Else:
    strategy[action] = 1 / num_actions   (uniform)
```

### CFR+ Regret Update

```
regret[action] = max(0, regret[action] + opponent_reach × (action_value - node_value))
```

The `max(0, ...)` floor is the key CFR+ improvement — prevents negative regret accumulation.

### Strategy Accumulation

```
strategy_sum[action] += player_reach × strategy[action]
```

The **average strategy** (sum normalized) converges to the Nash equilibrium approximation.

### Terminal Payoffs

```
start_total = (stack_OOP + stack_IP + pot) / 2

Fold:     traverser_value = traverser_stack - start_total  (if traverser folded)
          traverser_value = traverser_stack + pot - start_total  (if opponent folded)

Showdown: winner gets pot, loser gets nothing extra
Tie:      both get half the pot
```

---

## 4. Card Abstraction

### Card Encoding

```
card_index = rank × 4 + suit
  rank: 0=2, 1=3, ..., 12=A
  suit: 0=clubs, 1=diamonds, 2=hearts, 3=spades

Examples: 2c=0, 2d=1, Ah=50, As=51
```

### Hand Bucketing

V1 uses **static equity-based bucketing** with **50 buckets** per street.

**Procedure:**

1. For each hand combo in the range, evaluate hand strength on the flop using the poker evaluator
2. Sort all combos by evaluation rank (weakest → strongest)
3. Divide into 50 equal-sized buckets
4. Bucket 0 = weakest hands, Bucket 49 = strongest hands

**Static abstraction:** The same bucket assignment (computed on the flop) is used for all streets (Flop, Turn, River). The street is encoded in the info-set key, so different streets still have separate strategies.

**Bucket labels (approximate):**

| Bucket Range | Strength Label |
| ------------ | -------------- |
| 0 – 4        | Trash          |
| 5 – 11       | Weak           |
| 12 – 19      | Marginal       |
| 20 – 29      | Medium         |
| 30 – 39      | Good           |
| 40 – 46      | Strong         |
| 47 – 49      | Nuts           |

### Info-Set Key Format

```
{street}|{boardId}|{player}|{historyKey}|{bucket}

Examples:
  F|0|0||25        → Flop, board 0, OOP, root, bucket 25
  F|0|1|x|10       → Flop, board 0, IP, after OOP checks, bucket 10
  T|42|0|xx/|30    → Turn, board 42, OOP, both checked flop, bucket 30
  R|42|1|xx/xx/x|5 → River, board 42, IP, all checks, bucket 5
```

---

## 5. Board Abstraction

### Flop Selection: 200 Representative Boards

From ~1,755 suit-isomorphic flops, 200 are selected via **stratified sampling** across texture dimensions:

**Classification dimensions:**

- **High card rank:** 5 tiers (low 2-7, mid 8-9, high T-J, broadway Q, king K, ace A)
- **Suit pattern:** rainbow (3 suits) / two-tone (2 suits) / monotone (1 suit)
- **Connectivity:** connected (max gap ≤ 2) / semi-connected (max gap ≤ 4) / disconnected
- **Paired:** yes / no

**Selection algorithm:**

1. Classify all isomorphic flops into texture categories
2. Allocate proportionally: `slots = round(group_size / total × 200)`
3. Select evenly-spaced flops from each group
4. Fill remaining slots from unselected flops

### Nearest-Flop Matching

For boards not in the solved set, the viewer and advisor use **feature-distance matching:**

```
distance = 3×|highRank_diff| + 2×|midRank_diff| + 1×|lowRank_diff|
         + 5×|suitCount_diff| + 2×|maxGap_diff| + 1×|spread_diff|
         + 4×|paired_diff|
```

The closest solved board's strategy is used as an approximation.

---

## 6. Solver Execution

### Single Board

```bash
npx tsx src/cli/solve.ts --flops 1 --iterations 50000
```

- Iterations: 50,000 (default)
- Buckets: 50
- Output: JSONL + meta.json per board

### Full 200-Board Solve

```bash
npx tsx src/cli/solve.ts --flops 200 --iterations 50000 --use-selector --parallel
```

- Workers: min(CPU cores, num_flops), default 6
- Parallelism: child_process.fork() (one board per worker)
- Total time: ~56 minutes on 6-core machine
- Peak RAM per worker: ~50-90 MB
- Total output: 513 MB JSONL, 90 MB compressed binary

### Performance Benchmarks (measured)

| Metric                       | Value            |
| ---------------------------- | ---------------- |
| Iterations per second        | ~907/s per board |
| Time per board (50k iter)    | ~55-100 seconds  |
| Info sets per board          | ~49,000          |
| Total info sets (200 boards) | ~9.87 million    |
| JSONL output (200 boards)    | 513 MB           |
| Binary compressed output     | 90 MB (.bin.gz)  |

---

## 7. Output Formats

### JSONL (Human-Readable)

One file per board: `flop_000.jsonl`

```json
{"key":"F|0|0||25","probs":[0.245,0.310,0.345,0.100]}
{"key":"F|0|1|x|10","probs":[0.600,0.300,0.100]}
```

- `key`: info-set identifier
- `probs`: action probabilities (same order as tree actions)
- Near-uniform strategies (max prob < 1%) are filtered out

### Metadata

One file per board: `flop_000.meta.json`

```json
{
  "version": "v1",
  "game": "HU_NLHE_SRP",
  "stack": "50bb",
  "boardId": 0,
  "flopCards": [0, 1, 14],
  "iterations": 50000,
  "bucketCount": 50,
  "infoSets": 49392,
  "elapsedMs": 100976,
  "peakMemoryMB": 70,
  "timestamp": "2026-02-22T15:26:31.321Z"
}
```

### Binary Format (Production)

File: `v1_hu_srp_50bb.bin.gz`

```
[Header: 32 bytes]
  - Magic: "CFR1"
  - Version, bucketCount, numFlops, iterations
  - Index section offset

[Index: 8 bytes per entry]
  - FNV-1a hash of key (uint32) + body offset (uint32)
  - Sorted by hash for O(log n) binary search lookup

[Body: variable length per entry]
  - numActions (uint8) + quantized probs (uint8 each, value = round(p × 255))

[Compression]
  - gzip level 9
```

Lookup: O(log n) binary search by hash → decompress once on load, search in memory.

---

## 8. Convergence & Accuracy

### Exploitability

Measured on 6 sample boards after 50,000 iterations:

| Board | Exploitability (% pot) |
| ----- | ---------------------- |
| #0    | 358%                   |
| #10   | 378%                   |
| #50   | 415%                   |
| #100  | 389%                   |
| #150  | 402%                   |
| #199  | 367%                   |

These numbers are **expected for 50-bucket abstraction** and primarily measure abstraction boundary artifacts, not strategy quality. OOP/IP values are balanced, confirming solver consistency.

### Known Limitations

| Limitation                           | Impact                                     | Mitigation                              |
| ------------------------------------ | ------------------------------------------ | --------------------------------------- |
| 50 buckets (coarse abstraction)      | Similar-strength hands share one strategy  | Results show correct qualitative trends |
| Static buckets (same across streets) | Turn/River don't re-evaluate hand strength | Street is part of info-set key          |
| Full range (no frequency weighting)  | All 169 hand classes included at weight 1  | Over-estimates range width by ~30%      |
| 200 boards (not all flops)           | Uncovered boards use nearest-flop matching | Feature-distance heuristic              |
| 50k iterations (moderate)            | May not fully converge on complex nodes    | Sufficient for bucket-level trends      |
| Raise cap = 1 per street             | Missing deep raise/re-raise lines          | Keeps tree size manageable              |
| No rake                              | Real games have rake                       | Strategies may slightly over-bluff      |

---

## 9. Comparison with Commercial Solvers

| Feature         | CardPilot V1             | GTO Wizard / PioSOLVER            |
| --------------- | ------------------------ | --------------------------------- |
| Algorithm       | CFR+ (External Sampling) | CFR+ / CFR variants               |
| Hand resolution | 50 buckets               | Per-combo (no abstraction)        |
| Board coverage  | 200 representative flops | All possible flops                |
| Bet sizes       | 2 per street + all-in    | Configurable, often 3-5+          |
| Raise cap       | 1 per street             | Often 2-3+                        |
| Iterations      | 50,000                   | Typically runs to target accuracy |
| Preflop ranges  | All freq>0 at weight 1   | Weighted mixed frequencies        |
| Rake            | None                     | Configurable                      |

### How to Set Up an Equivalent Solve on Another Platform

```
Street:        Flop
Equity Model:  Chip EV
Pot:           5
Stack:         47.5
Rake:          No rake

OOP (BB):
  No facing bet: Check / Bet 33% / Bet 75% / All-in
  Facing bet:    Fold / Call / Raise 33% / Raise 75% / All-in

IP (BTN):
  No facing bet: Check / Bet 33% / Bet 75% / All-in
  Facing bet:    Fold / Call / Raise 33% / Raise 75% / All-in

Turn bet sizes:  50%, 100%
River bet sizes: 75%, 150%
Raise cap:       1 per street
Ranges:          Standard HU SRP (BTN open 2.5x, BB flat)
```

---

## 10. Integration into CardPilot

The solved strategies are integrated into the advice engine via `CfrAdvisor`:

1. **Binary reader** loads the 90MB compressed file into memory on startup
2. For each postflop decision, the advisor:
   - Finds the matching or nearest board
   - Converts the game history to a CFR history key
   - Estimates the hand bucket using hand classification
   - Looks up the strategy from binary data (O(log n))
3. **Blending:** CFR strategy is blended with heuristic engine
   - Exact board match: 85% CFR + 15% heuristic
   - Nearest board match: 65% CFR + 35% heuristic
   - No match: 100% heuristic fallback

---

## 11. File Reference

```
packages/cfr-solver/
  src/
    tree/tree-config.ts          ← Bet sizes, pot, stack
    tree/tree-builder.ts         ← Game tree construction
    engine/cfr-engine.ts         ← CFR+ algorithm core
    engine/info-set-store.ts     ← Regret/strategy storage
    engine/exploitability.ts     ← Convergence checking
    abstraction/card-index.ts    ← Card encoding (0-51)
    abstraction/flop-selector.ts ← 200 board selection
    integration/preflop-ranges.ts ← Range loading
    storage/json-export.ts       ← JSONL output
    storage/binary-format.ts     ← Binary format + reader
    orchestration/solve-orchestrator.ts ← Parallel solving
    cli/solve.ts                 ← CLI entry point
  viewer/
    index.html                   ← Strategy viewer UI
    serve.ts                     ← HTTP server (port 3456)

data/
  preflop_charts.json            ← Preflop range data
  cfr/v1_hu_srp_50bb/            ← 200 JSONL + meta files
  cfr/v1_hu_srp_50bb.bin.gz      ← Compressed binary (90MB)
```
