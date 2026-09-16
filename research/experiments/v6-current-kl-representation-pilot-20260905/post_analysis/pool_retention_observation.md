# Closed-branch pool retention observation

Read during Seed1 full stage2; zero new poker hands, queries or weight updates.
Sources are each named branch's controller-verified `verification.json`, fields
`pool_audit.final_active_ids` and `pool_audit.anchor_retention_checks_missing`.
The final independent review binds these verification files and checkpoints.

| Closed training branch | Final active opponent IDs | Missing anchor-retention checks |
|---|---|---:|
| Seed1 full stage1 | 0, 1, 2, 904, 487 | 0 |
| Seed1 heads stage1 | 0, 1, 2, 487, 891 | 0 |
| Seed3 full stage1 | 0, 1, 2, 895, 810 | 0 |
| Seed3 heads stage1 | 0, 1, 2, 810, 217 | 0 |
| Seed3 full stage2 | 0, 1, 2, 970, 969 | 0 |
| Seed3 heads stage2 | 0, 1, 2, 810, 217 | 0 |
| Seed1 heads stage2 | 0, 1, 2, 487, 891 | 0 |

All these endpoints retain initial opponent IDs0,1,2. The generic algorithm's
permission to evict anchors is not evidence that it did so in this pilot. Do not
attribute the observed stage1 weakness to wholesale loss of initial anchors.
This endpoint observation does not prove uninterrupted anchor retention at every
iteration, sufficient style diversity, or adequate general poker strength.
Snapshot identities differ between scopes, as expected from the dynamic league;
this observation alone does not establish a causal explanation of strength.
Do not equate retained candidate-history metadata with active training opponents.
Seed1 full stage2 was still live and is deliberately not characterized here.

## Addendum after the final training branch closed

Seed1 full stage2 subsequently passed its controller audit. Final active IDs are
0,1,2,962,943, with zero missing anchor-retention checks. Frozen checkpoint SHA256
is `3d7914ba11c5deaf9725afbd59f4a805fd7f0bead37a2c8eddb6bffa9038b8f3`.
Thus all eight completed training-branch endpoints retained the three initial
opponents. The limitations above still apply; this is not a strength result.
