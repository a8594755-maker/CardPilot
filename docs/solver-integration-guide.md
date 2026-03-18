# GTO Solver Integration Guide

## Overview

CardPilot now supports importing real GTO solver data and advanced strategy features:

- ✅ **Solver Data Import**: PioSolver, GTO+, GTOWizard formats
- ✅ **Range Estimation**: Dynamic opponent modeling based on action history
- ✅ **Multiway Pots**: Automatic strategy adjustments for 3+ players
- ✅ **Multiple Sizings**: Support for 2.5x, 3x, 4x, pot-sized bets

---

## 1. Importing Solver Data

### Supported Formats

#### PioSolver CSV Export

```csv
Hand,Raise,Call,Fold
AA,1.0,0.0,0.0
AKs,0.95,0.0,0.05
AKo,0.85,0.0,0.15
```

#### GTO+ JSON Export

```json
{
  "solver": "gto+",
  "spots": [
    {
      "name": "BTN_unopened_open2.5x",
      "ranges": {
        "AA": { "raise": 1.0, "call": 0, "fold": 0, "ev": 2.5 },
        "AKs": { "raise": 0.95, "call": 0, "fold": 0.05, "ev": 2.1 }
      }
    }
  ]
}
```

### Import Command

```bash
# Import PioSolver CSV for BTN open spot
node data/import-solver-data.mjs btn_open.csv \
  --spot BTN_unopened_open2.5x \
  --sizing open2.5x \
  -o data/preflop_charts.json

# Import GTO+ JSON and merge with existing data
node data/import-solver-data.mjs gtoplus_export.json \
  --merge \
  -o data/preflop_charts.json

# Import with custom solver type
node data/import-solver-data.mjs custom_data.csv \
  --solver piosolver \
  --spot CO_vs_BTN_facing_open3x \
  --sizing open3x
```

### Import Options

| Option         | Description                         | Default                      |
| -------------- | ----------------------------------- | ---------------------------- |
| `--output, -o` | Output file path                    | `preflop_charts_solver.json` |
| `--solver, -s` | Solver type (auto, piosolver, gto+) | `auto`                       |
| `--format, -f` | Game format                         | `cash_6max_100bb`            |
| `--spot`       | Spot identifier (required for CSV)  | -                            |
| `--sizing`     | Bet sizing category                 | `open2.5x`                   |
| `--merge, -m`  | Merge with existing chart           | `false`                      |

---

## 2. Range Estimation System

### How It Works

The `RangeEstimator` dynamically narrows opponent ranges based on:

1. **Preflop Actions**: Opening range varies by position
2. **Postflop Actions**: Bet/raise/call/check/fold narrow the range
3. **Bet Sizing**: Large bets indicate polarized ranges
4. **Multiway Adjustments**: Tighten ranges with more opponents

### Example Usage

```typescript
import { RangeEstimator } from '@cardpilot/advice-engine';

const estimator = new RangeEstimator();

// Build initial BTN opening range
let range = estimator.buildPreflopRange('BTN', 'raise');

// Narrow based on flop c-bet (75% pot)
range = estimator.narrowRangePostflop(
  range,
  'raise', // action type
  'FLOP', // street
  ['Ah', 'Kc', '7d'], // board
  0.75, // bet size relative to pot
);

// Sample hands from range for equity calculation
const villainHands = estimator.sampleHandsFromRange(range, 50);
```

### Range Building Logic

**Opening Ranges by Position**:

- **UTG**: 14% (tight, premium hands)
- **MP/HJ**: 18-22% (strong hands + suited connectors)
- **CO**: 28% (wide value + some bluffs)
- **BTN**: 45% (widest range, maximum fold equity)
- **SB**: 38% (steal range)

**3bet Ranges**:

- Polarized: Top 8% value hands + bottom 15% bluffs
- Linear adjustments based on opponent position

**Postflop Narrowing**:

- **Bet/Raise**: Favor strong hands + draws, reduce weak holdings
- **Call**: Medium strength + draws + slowplays
- **Check**: Weak hands + check-traps
- **Large bets (>75% pot)**: Highly polarized (nuts or air)

---

## 3. Multiway Pot Adjustments

When `numVillains > 1`, the system automatically:

### Equity Adjustments

```typescript
// Reduce equity by 12% per additional opponent
const adjustedEquity = equity * (1 - (numVillains - 1) * 0.12);
```

### Strategy Tightening

**Defense (Facing Bet)**:

- Nutted/Strong: 70% raise, 30% call
- Medium (with odds): 10% raise, 70% call, 20% fold
- Weak: 0% raise, 20% call, 80% fold

**Aggression (First to Act)**:

- Nutted/Strong: 85% bet, 15% check
- Medium: 40% bet, 60% check
- Weak: 5% bet (rare bluffs), 95% check

### Range Narrowing

```typescript
// Multiway tightening factor
const tighteningFactor = 1 - (numOpponents - 1) * 0.15;

// Premium hands retain more weight
const adjustedWeight = isPremium
  ? weight * max(0.8, tighteningFactor + 0.2)
  : weight * max(0.3, tighteningFactor);
```

---

## 4. Multiple Bet Sizing Support

### Supported Sizings

| Sizing     | Preflop | Postflop | Strategy Impact               |
| ---------- | ------- | -------- | ----------------------------- |
| `open2.5x` | 2.5BB   | -        | Standard, balanced ranges     |
| `open3x`   | 3BB     | -        | Slightly tighter, more linear |
| `open4x`   | 4BB     | -        | Tight and polarized           |
| `half_pot` | -       | 0.5x pot | Small value bets, weak draws  |
| `pot`      | -       | 1x pot   | Standard value/bluff ratio    |
| `2x_pot`   | -       | 2x pot   | Polarized (nuts or air)       |
| `all_in`   | -       | All-in   | Maximum polarization          |

### Automatic Sizing Detection

```typescript
import { detectBetSizing } from '@cardpilot/advice-engine';

// Preflop sizing
const sizing = detectBetSizing(
  300, // raise amount (chips)
  100, // big blind
  150, // pot size
);
// Returns: 'open3x' (300 / 100 = 3x BB)

// Postflop sizing
const sizing = detectBetSizing(
  750, // bet amount
  100, // big blind
  1000, // pot size
);
// Returns: 'pot' (750 / 1000 = 0.75x pot)
```

### Sizing Impact on Ranges

**Larger sizes → Tighter/Polarized**:

```javascript
// Premium hands (AA-JJ, AKs): raise MORE with larger sizes
raiseAdj = 1 + (multiplier - 1) * 0.5;

// Marginal hands (suited connectors, weak Ax): fold MORE
raiseAdj = 1 - (multiplier - 1) * 0.8;

// Bluffs: bluff LESS (slightly)
raiseAdj = 1 - (multiplier - 1) * 0.3;
```

---

## 5. Chart Generation with Sizings

### Generate Multi-Sizing Charts

```bash
# Generate charts with 2.5x, 3x, 4x sizings
node data/generate_charts.mjs

# Output:
# 8 base spots × 3 sizings × 169 hands = 4,056 entries
```

### Chart Structure

```json
[
  {
    "format": "cash_6max_100bb",
    "spot": "BTN_unopened_open2.5x",
    "hand": "AKs",
    "mix": { "raise": 0.96, "call": 0, "fold": 0.04 },
    "notes": ["BROADWAY_STRENGTH", "IP_ADVANTAGE"]
  },
  {
    "format": "cash_6max_100bb",
    "spot": "BTN_unopened_open3x",
    "hand": "AKs",
    "mix": { "raise": 0.98, "call": 0, "fold": 0.02 },
    "notes": ["BROADWAY_STRENGTH", "IP_ADVANTAGE"]
  }
]
```

---

## 6. Integration Examples

### Server-Side Usage

```typescript
// server.ts - Automatic sizing detection
const advice = getPreflopAdvice({
  tableId,
  handId: state.handId,
  seat,
  heroPos: 'BTN',
  villainPos: 'BB',
  line: 'unopened',
  heroHand: 'AKs',
  // Auto-detect sizing from game state
  raiseAmount: 300,
  bigBlind: 100,
  potSize: 150,
});
// Will use 'open3x' spot automatically
```

### Postflop with Range Estimation

```typescript
const context: PostflopContext = {
  tableId,
  handId,
  seat,
  street: 'FLOP',
  heroHand: ['Ah', 'Kd'],
  board: ['Kc', '9s', '4h'],
  heroPosition: 'BTN',
  villainPosition: 'BB',
  potSize: 1200,
  toCall: 600,
  effectiveStack: 8000,
  aggressor: 'villain',
  numVillains: 1,
  // Action history for range estimation
  actionHistory: [
    { seat: 3, street: 'PREFLOP', type: 'raise', amount: 250, at: 1000 },
    { seat: 1, street: 'PREFLOP', type: 'call', amount: 250, at: 1100 },
    { seat: 3, street: 'FLOP', type: 'raise', amount: 600, at: 2000 },
  ],
};

const advice = getPostflopAdvice(context);
// Range is estimated from preflop call + flop bet
// Equity calculated vs estimated range
// Strategy adjusted for IP, hand strength, board texture
```

---

## 7. Migration Guide

### Upgrading from Hardcoded Charts

1. **Backup existing charts**:

   ```bash
   cp data/preflop_charts.json data/preflop_charts.backup.json
   ```

2. **Export your solver data** (PioSolver/GTO+)

3. **Import solver data**:

   ```bash
   # Import BTN opening range
   node data/import-solver-data.mjs btn_pio_export.csv \
     --spot BTN_unopened_open2.5x \
     --merge -o data/preflop_charts.json

   # Import BB defense vs BTN
   node data/import-solver-data.mjs bb_vs_btn.csv \
     --spot BB_vs_BTN_facing_open2.5x \
     --merge -o data/preflop_charts.json
   ```

4. **Verify data**:

   ```bash
   node -e "console.log(require('./data/preflop_charts.json').length)"
   # Should show increased entry count
   ```

5. **Test in-game**:
   - Start dev server
   - Check advice in COACH mode
   - Verify correct frequencies displayed

---

## 8. Best Practices

### Solver Data Quality

✅ **DO**:

- Use recent solver outputs (2023+)
- Verify rake/ante settings match your game
- Import complete ranges (not just top hands)
- Test edge cases (72o, A2s, etc.)

❌ **DON'T**:

- Mix solvers with different assumptions
- Use outdated charts (pre-2020)
- Cherry-pick only premium hands
- Ignore bet sizing differences

### Range Estimation

✅ **DO**:

- Track full action history
- Update ranges per street
- Consider multiway dynamics
- Account for player tendencies (future feature)

❌ **DON'T**:

- Assume static ranges
- Ignore bet sizing signals
- Treat all villains identically
- Forget to adjust for ICM (tournaments)

### Performance

- **Chart Size**: ~4K entries = 0.5MB JSON (acceptable)
- **Range Sampling**: 50 hands = fast Monte Carlo
- **Cache**: Ranges cached by spot key (fast lookup)
- **Memory**: RangeEstimator is stateless (low overhead)

---

## 9. Troubleshooting

### Issue: "Chart entry not found"

**Cause**: Spot key mismatch or missing sizing

**Solution**:

```typescript
// Enable fallback candidates
const candidates = buildSpotCandidates({
  heroPos: 'BTN',
  villainPos: 'BB',
  line: 'unopened',
  size: 'open3x', // Will fallback to 'open2.5x' if missing
});
```

### Issue: "Advice seems too tight/loose"

**Cause**: Solver assumptions differ from your game

**Solution**:

1. Check rake settings in solver
2. Verify stack depths match
3. Adjust `tightnessAdjustment` in RangeEstimator config
4. Re-import with correct parameters

### Issue: "Multiway pots give strange advice"

**Cause**: Range not adjusted for multiple opponents

**Solution**:

```typescript
// Ensure numVillains is correctly passed
const context = {
  ...otherFields,
  numVillains: activePlayers.length - 1, // Exclude hero
};
```

---

## 10. Future Enhancements

**Planned Features**:

- [ ] ICM adjustments for tournaments
- [ ] Player profiling (exploitative ranges)
- [ ] Postflop solver import
- [ ] Dynamic range visualization
- [ ] Hand history analysis

**Contribute**:

- Report issues: GitHub Issues
- Submit solver data: Discord #solver-data
- Request features: GitHub Discussions
