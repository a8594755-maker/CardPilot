# BC vs heuristic_v3 disagreement analysis

_Generated 2026-05-21 14:16:00_

## Summary

BC ckpt: `models\bc\v3_anchor_5M_d1_light\best.pt`
Data: `data\phase2\teacher_v3_5M.jsonl` (sampled 50000 rows, seed=123)
Pot median (nonzero): 2
Overall disagreement: 1.42%

### Stratified disagreement

| slice | n | disagreement % | top confusions |
|---|---:|---:|---|
| all | 50000 | 1.42% | teacher=3→bc=1=262; teacher=2→bc=1=167; teacher=1→bc=0=119 |
| SB (pos=1) | 20402 | 0.52% | teacher=1→bc=0=41; teacher=0→bc=1=20; teacher=3→bc=1=18 |
| BB (pos=0) | 29598 | 2.04% | teacher=3→bc=1=244; teacher=2→bc=1=157; teacher=1→bc=0=78 |
| preflop | 16637 | 0.04% | teacher=7→bc=0=4; teacher=0→bc=7=3 |
| flop | 11651 | 1.54% | teacher=1→bc=0=84; teacher=2→bc=1=54; teacher=1→bc=2=20 |
| turn | 10961 | 2.12% | teacher=2→bc=1=112; teacher=3→bc=2=32; teacher=1→bc=0=28 |
| river | 10751 | 2.72% | teacher=3→bc=1=234; teacher=1→bc=3=21; teacher=3→bc=2=19 |
| facing_bet=1 | 2442 | 3.19% | teacher=0→bc=1=36; teacher=1→bc=0=35; teacher=7→bc=0=4 |
| facing_bet=0 (no bet) | 47558 | 1.33% | teacher=3→bc=1=262; teacher=2→bc=1=167; teacher=1→bc=0=84 |
| BB facing aggression (pos=0 & facing_bet) | 1708 | 2.93% | teacher=1→bc=0=27; teacher=0→bc=1=16; teacher=7→bc=0=4 |
| preflop 3-bet spot (preflop+facing_bet+to_call>=2BB) | 0 | - | - |
| river facing bet (street=3+facing_bet) | 377 | 3.45% | teacher=0→bc=1=8; teacher=1→bc=0=5 |
| high-pot state (pot > median nonzero pot) | 10053 | 2.91% | teacher=3→bc=1=155; teacher=3→bc=2=38; teacher=0→bc=1=36 |
| teacher chose raise (slots 2-7) | 11776 | 4.17% | teacher=3→bc=1=262; teacher=2→bc=1=167; teacher=3→bc=2=56 |
| teacher chose jam/allin (slot 8) | 0 | - | - |
| teacher chose fold (slot 0) facing_bet | 1252 | 3.12% | teacher=0→bc=1=36; teacher=0→bc=7=3 |
