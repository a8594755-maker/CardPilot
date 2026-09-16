# v6 learned-opponent diversity result

Decision: LEAGUE_DIVERSITY_GATE_NOT_PASSED.

527130 actual new training hands;245760 internal hands;17 normal child exits. Full evidence review passed.

| Contrast | bb/100 | 95%CI | Six-contrast adjusted CI |
|---|---:|---|---|
| diverse5-source anchor0 | +208.2209 | [139.42921862190332, 277.0125538390342] | [115.62388754531939, 300.8178849156181] |
| diverse5-source anchor1 | -92.7153 | [-176.80229007268613, -8.628251919501366] | [-205.90057185517446, 20.470029862986948] |
| diverse5-source anchor2 | +157.3903 | [65.6778992153178, 249.10274043311972] | [33.94085005912078, 280.83978958931675] |
| diverse5-source anchor3 | +118.4026 | [17.533539728160875, 219.27163605308914] | [-17.372156998812585, 254.17733278006259] |
| diverse5-source anchor4 | +274.1206 | [128.54090676263493, 419.7003041748651] | [78.16310598815713, 470.0781049493429] |
| heldout diverse5-control3 mean | -35.6038 | [-126.33215361498158, 55.12457304857533] | [-157.72867011519588, 86.52108954878965] |

No Slumbot qualification or control/checkpoint rescue. Matched seeds are not identical asynchronous trajectories. These anchors are held out of training, not unseen policy families or independent training seeds.
