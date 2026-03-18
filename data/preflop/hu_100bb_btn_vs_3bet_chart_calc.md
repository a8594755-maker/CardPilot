# CASH GAME PREFLOP CHARTS

## 100BB Heads-Up: BTN vs BB 3-Bet (Calculated)

### Model setup
- Solver: local `legacy_preflop_cfr`
- Base config: `cash_6max_100bb` with overrides
- Players: `2` (`BTN`, `BB`)
- Stack: `100bb`
- Blinds / ante: `0.5 / 1 / 0`
- Open size: `2.5bb`
- BB 3-bet size: `8.75bb` (`3.5x`)
- BTN 4-bet size: `19.69bb` (`2.25x` of 3-bet)
- Iterations: `1,000,000` (seed `42`)
- Spot key: `Bo-b3` (BTN open, BB 3-bet, BTN decision)

### Aggregate response (within BTN open range, facing 3-bet)
- Fold: `11.28%`
- Call: `81.86%`
- 4-bet: `6.86%`

### Chart construction rule
- Include hands with BTN open frequency `>= 20%`
- Category assignment:
- `4-bet`: dominant action >= `70%`
- `Call`: dominant action >= `70%`
- `Fold`: dominant action >= `70%`
- `Mix 4-bet/Call`: neither action >= 70%, with both 4-bet and call meaningful
- `Mix Call/Fold`: neither action >= 70%, with both call and fold meaningful

## BTN vs 3-bet chart

### 4-bet
- `AA-JJ, AKo`

### Mix 4-bet / Call
- `TT, 99, AKs, AQo`

### Call
- `88-22`
- `AQs-A2s`
- `KQs-K2s`
- `QJs-Q2s`
- `JTs-J2s`
- `T9s-T3s`
- `98s-95s`
- `87s-83s`
- `76s-73s`
- `65s-62s`
- `54s-52s`
- `42s`
- `AJo-A2o`
- `KQo-K4o`
- `QJo-Q8o, Q6o`
- `JTo-J7o`
- `T9o-T7o`
- `98o, 97o, 87o, 86o`

### Mix Call / Fold
- `93s, 32s, K3o, K2o, Q7o, Q5o, Q4o, T6o`

### Fold
- `J6o, J5o`

## Notes
- This chart is solver-calculated from the local model in this repo, not copied from external charts.
- Because this tree allows BTN complete at root, the chart is conditioned on the BTN open branch and then facing BB 3-bet.
