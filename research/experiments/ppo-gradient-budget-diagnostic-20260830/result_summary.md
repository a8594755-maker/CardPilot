# PPO gradient-budget diagnostic

Decision: `NO_PERSISTENT_GRADIENT_SUPPRESSION_IDENTIFIED`.

Two fresh diagnostic cohorts completed normally: Standard10 source **20,636 physical hands**, mature all-heads iter64 **19,314**, total **39,950**. Their legacy transition-bearing counts were 16,439 and 16,443. Each had four PPO updates and 32 probes (first four minibatches of each epoch). This is a mechanism study, with **zero evaluation/Slumbot hands**, not evidence of increased poker strength.

| Probe average | Source | Mature |
|---|---:|---:|
| PPO gradient norm | 0.28430 | 0.25054 |
| Weighted source-KL norm | 0.11380 | 0.09330 |
| Weighted entropy norm | 0.00726 | 0.00709 |
| Actor/PPO norm ratio | 0.94744 | 1.01281 |
| PPO/actor cosine | 0.90040 | 0.92969 |
| Global clipping scale | 0.92942 | 0.97677 |
| Fraction subject to global clipping | 21.875% | 15.625% |

The regularizer sometimes opposes PPO but does not systematically cancel it. Critic gradients exceed actor gradients in 56.25% of probes, yet global clipping is absent in most probes and only mildly scales the mature-cohort mean. Removing regularization or separating clipping is therefore not the highest-information next treatment. These are pre-Adam gradients, not effective optimizer step magnitudes; this study does not prove that optimization or small KL is harmless. Probe selection is deterministic and not a representative random sample of all minibatches. Short local LR schedules also differ from an uninterrupted long run.

The mature input's optimizer steps were 1796, and the output steps are 1914 across all ten state entries; optimizer state was loaded, not reset. The new local counter was intentionally reset for this separate experiment. Neither the completed historical experiment nor its frozen checkpoint was resumed/overwritten. Both cohorts use the exact original Standard10 source-KL anchor. Checkpoints, per-update diagnostics, physical counters, assignment chains, and source snapshots are retained.

Integrity: 22 helper/accounting/replay tests passed; an additional real-PPO integration test verifies bitwise-identical model, Adam, and torch RNG with probes enabled/disabled. Both fixed-pool session audits PASS. Initial wrapper stopped after successful source training because the auditor incorrectly also enforced the irrelevant legacy target. Auditor now honors physical-target precedence and checks the configured target; a mismatched-target negative probe correctly fails. Only the unstarted mature cohort was subsequently launched. Original execution source snapshot and corrected mature snapshot both remain, and trainer bytes did not change between cohorts.

Next experiment: one preregistered, uninterrupted **1,048,576 physical-hand** learning curve with unchanged all-heads PPO/source KL, from the original Standard10, using new seeds. This is a bounded sample-budget hypothesis test, not promotion of a proven policy. Keep early/mid/final archives, evaluate frozen checkpoints on independent multi-anchor greedy and sampled deals, and do not expand toward paper scale without a reproducible general gain. Formal success remains one frozen policy on at least 100,000 fresh Slumbot hands with positive bb/100 and positive 95% lower bound; it has not been achieved.
