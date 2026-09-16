# Learned-policy frontier audit

| Experiment | Hands | bb/100 | 95% CI | Checkpoint | Provenance |
|---|---:|---:|---:|---|---|
| `legacy-best-mature-external-reference` | 20,000 | -11.4275 | [-28.7124, 5.8574] | available | imported summary |
| `legacy-scaled-slumbot-imitation-teacher` | 20,000 | -18.5025 | [-41.8045, 4.7995] | absent | imported summary |
| `v6-standard10-legacy-bridge-greedy-fresh20k-20260901` | 20,000 | -24.5683 | [-42.8407, -6.2959] | available | current record |
| `legacy-counterfactual-capped-softresidual-seed4363-fresh20k` | 20,000 | -38.0775 | [-56.8388, -19.3162] | absent | imported summary |
| `v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901` | 20,000 | -41.8162 | [-74.4660, -9.1664] | available | current record |
| `v6-actor-raw-greedy-fresh20k-slumbot-20260901` | 20,000 | -46.5992 | [-78.8896, -14.3088] | available | current record |
| `standard10-strict-sampled-slumbot20k-20260830` | 20,000 | -48.9778 | [-71.6649, -26.2907] | available | current record |
| `weak-kl-strict-sampled-slumbot20k-20260830` | 20,000 | -55.8690 | [-93.6089, -18.1291] | available | current record |
| `v6-historical-average-fresh20k-slumbot-20260831` | 20,000 | -70.4076 | [-107.6049, -33.2102] | available | current record |
| `representation-full-strict-sampled-slumbot20k-20260831` | 20,000 | -81.2510 | [-123.1600, -39.3420] | available | current record |
| `v6-source-fresh20k-slumbot-20260831` | 20,000 | -82.8164 | [-114.5675, -51.0653] | available | current record |
| `v6-physical1m-fresh20k-slumbot-20260831` | 20,000 | -137.7392 | [-183.1155, -92.3630] | available | current record |
| `v6-selfplay-transfer-fresh40k-slumbot-20260831` | 40,000 | -141.0145 | unknown | available | current record |
| `v6-fictitious-average-phase2-fresh20k-slumbot-20260831` | 20,000 | -182.1045 | [-234.0126, -130.1964] | available | current record |

## Decision

`STANDARD10_ONLY_REPRODUCIBLE_FRONTIER_PARENT`

Use frozen Standard10 as a preservation prior and initialization for a qualitatively different state-conditioned policy-improvement signal. Treat single-teacher imitation as a negative control, not a revived route.

The historical imitation result remains negative and its imported record does not identify a surviving checkpoint. It therefore cannot displace Standard10 as the reproducible parent or be treated as new evidence for imitation.
