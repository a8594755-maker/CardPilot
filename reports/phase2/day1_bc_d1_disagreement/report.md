# BC vs heuristic_v3 disagreement analysis

_Generated 2026-05-21 08:41:18_

## Summary

BC ckpt: `models\bc\v3_anchor_5M_d1\best.pt`
Data: `data\phase2\teacher_v3_5M.jsonl` (sampled 50000 rows, seed=123)
Pot median (nonzero): 2
Overall disagreement: 2.00%

### Stratified disagreement

| slice | n | disagreement % | top confusions |
|---|---:|---:|---|
| all | 50000 | 2.00% | teacher=1→bc=2=387; teacher=1→bc=0=172; teacher=1→bc=3=146 |
| SB (pos=1) | 20402 | 0.92% | teacher=1→bc=0=69; teacher=1→bc=2=55; teacher=1→bc=3=22 |
| BB (pos=0) | 29598 | 2.75% | teacher=1→bc=2=332; teacher=1→bc=3=124; teacher=1→bc=0=103 |
| preflop | 16637 | 0.07% | teacher=7→bc=0=11 |
| flop | 11651 | 2.51% | teacher=1→bc=2=158; teacher=1→bc=0=87; teacher=2→bc=1=26 |
| turn | 10961 | 3.81% | teacher=1→bc=2=228; teacher=1→bc=0=65; teacher=2→bc=3=36 |
| river | 10751 | 2.60% | teacher=1→bc=3=132; teacher=3→bc=1=91; teacher=1→bc=0=20 |
| facing_bet=1 | 2442 | 5.65% | teacher=1→bc=0=113; teacher=0→bc=1=14; teacher=7→bc=0=11 |
| facing_bet=0 (no bet) | 47558 | 1.81% | teacher=1→bc=2=387; teacher=1→bc=3=146; teacher=3→bc=1=109 |
| BB facing aggression (pos=0 & facing_bet) | 1708 | 6.26% | teacher=1→bc=0=86; teacher=7→bc=0=11; teacher=0→bc=1=10 |
| preflop 3-bet spot (preflop+facing_bet+to_call>=2BB) | 0 | - | - |
| river facing bet (street=3+facing_bet) | 377 | 6.10% | teacher=1→bc=0=17; teacher=0→bc=1=6 |
| high-pot state (pot > median nonzero pot) | 10053 | 3.62% | teacher=1→bc=0=113; teacher=1→bc=3=99; teacher=3→bc=1=52 |
| teacher chose raise (slots 2-7) | 11776 | 2.39% | teacher=3→bc=1=109; teacher=2→bc=3=62; teacher=3→bc=2=51 |
| teacher chose jam/allin (slot 8) | 0 | - | - |
| teacher chose fold (slot 0) facing_bet | 1252 | 1.12% | teacher=0→bc=1=14 |
