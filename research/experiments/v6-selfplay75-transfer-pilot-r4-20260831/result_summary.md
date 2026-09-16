# v6 self-play share training and internal diagnostics

Decision: ADMIT_FIXED_EXTERNAL_TRANSFER_PAIR.

2102762 actual new training hands;122880 internal hands;17 normal child exits. Full evidence review passed.

| Contrast | bb/100 | 95%CI | Six-contrast adjusted CI |
|---|---:|---|---|
| selfplay75-source anchor0 | +409.8556 | [292.61081782061706, 527.1003638200079] | [252.0383075837936, 567.6728740568315] |
| selfplay75-source anchor1 | -154.5703 | [-291.3864362802957, -17.754188719704302] | [-338.73160520013295, 29.590980200132947] |
| selfplay75-source anchor2 | +320.3177 | [172.84427299974547, 467.7912250471295] | [121.8111312864963, 518.8243667603787] |
| selfplay75-source anchor3 | +246.4425 | [89.93379385884145, 402.95121590678355] | [35.774012422882635, 457.1109973427424] |
| selfplay75-source anchor4 | +122.9834 | [-81.89332836934074, 327.86012524434074] | [-152.79084373814123, 398.75764061314123] |
| heldout selfplay75-control25 mean | -84.0480 | [-226.74128746435898, 58.645340198733976] | [-276.1202558229034, 108.0243085572784] |

Both healthy endpoints are admitted to the prespecified external transfer pair regardless of these internal scores. No100k qualification. Matched seeds are not identical asynchronous trajectories. These anchors are held out of training, not unseen policy families or independent training seeds.
