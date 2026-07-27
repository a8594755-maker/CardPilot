# BC vs heuristic_v3 disagreement analysis

_Generated 2026-05-21 03:58:50_

## Summary

BC ckpt: `models\bc\v3_anchor_5M_first\best.pt`
Data: `data\phase2\teacher_v3_5M.jsonl` (sampled 50000 rows, seed=123)
Pot median (nonzero): 2
Overall disagreement: 0.94%

### Stratified disagreement

| slice | n | disagreement % | top confusions |
|---|---:|---:|---|
| all | 50000 | 0.94% | teacher=0→bc=1=155; teacher=1→bc=0=77; teacher=3→bc=1=70 |
| SB (pos=1) | 20402 | 0.44% | teacher=1→bc=0=40; teacher=0→bc=1=23; teacher=2→bc=1=6 |
| BB (pos=0) | 29598 | 1.28% | teacher=0→bc=1=132; teacher=3→bc=1=65; teacher=1→bc=3=56 |
| preflop | 16637 | 0.04% | teacher=7→bc=0=7 |
| flop | 11651 | 1.75% | teacher=0→bc=1=121; teacher=1→bc=0=58; teacher=2→bc=1=15 |
| turn | 10961 | 0.99% | teacher=2→bc=1=33; teacher=0→bc=1=22; teacher=1→bc=2=18 |
| river | 10751 | 1.39% | teacher=3→bc=1=64; teacher=1→bc=3=57; teacher=0→bc=1=12 |
| facing_bet=1 | 2442 | 6.88% | teacher=0→bc=1=155; teacher=7→bc=0=7; teacher=1→bc=0=6 |
| facing_bet=0 (no bet) | 47558 | 0.63% | teacher=1→bc=0=71; teacher=3→bc=1=70; teacher=1→bc=3=61 |
| BB facing aggression (pos=0 & facing_bet) | 1708 | 8.26% | teacher=0→bc=1=132; teacher=7→bc=0=7; teacher=1→bc=0=2 |
| preflop 3-bet spot (preflop+facing_bet+to_call>=2BB) | 0 | - | - |
| river facing bet (street=3+facing_bet) | 377 | 3.71% | teacher=0→bc=1=12; teacher=1→bc=0=2 |
| high-pot state (pot > median nonzero pot) | 10053 | 2.71% | teacher=0→bc=1=155; teacher=3→bc=1=43; teacher=1→bc=3=39 |
| teacher chose raise (slots 2-7) | 11776 | 1.26% | teacher=3→bc=1=70; teacher=2→bc=1=48; teacher=3→bc=2=17 |
| teacher chose jam/allin (slot 8) | 0 | - | - |
| teacher chose fold (slot 0) facing_bet | 1252 | 12.38% | teacher=0→bc=1=155 |
