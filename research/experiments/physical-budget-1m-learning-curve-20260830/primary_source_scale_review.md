# Primary-source context for interpreting this run

Read-only literature check during the unchanged running experiment, 2026-08-30. No new games, model updates, API registrations, or benchmark-policy rules result from this review. Attach this note when the single background record writer has finished; do not race its accounting updates.

## AlphaHoldem scale

The [AAAI AlphaHoldem paper](https://ojs.aaai.org/index.php/AAAI/article/view/20394/20153), experimental setup on printed page4693, reports eight TITANV GPUs, 64 CPU cores, aggregate mini-batch16384 (2048 per GPU), initial Adam learning rate0.0003, discount0.999, GAE lambda0.95, and50000 iterations. Its6.5B training samples correspond approximately to2.7B hands. The paper describes asynchronous replay and an ELO-selected historical K-best pool. These are reported experimental settings, not independently reproduced results here.

Local facts: this run uses one RTX4070,12 workers, mini-batch1024, LR0.00003, frozen representation with trainable policy/value heads, source KL1, and a fixed three-anchor adaptive league with25% self-play. Its explicit local budget is1048576 completed physical hands. Prior code/log evidence already rejects several short replay/K-best/full-network variants; simply restoring an individual paper setting does not guarantee improvement.

Inference: this run isolates a longer local sample horizon within the established training configuration. A flat curve would reject scaling this unchanged configuration on these diagnostics; it would not falsify the paper or show that larger effective optimizer batches, full-network learning, or better variance control cannot work. Conversely, larger training reward or more hands alone is not admission to2.7B scale. If the curve is flat, a separately preregistered effective-optimizer-batch/noise study is more informative than silently changing this run or claiming a faithful paper reproduction. Preserve this as a conditional hypothesis, not an already selected next experiment.

## Additional evaluation research, not an active dependency

The [2026 GTO Wizard Benchmark paper](https://arxiv.org/html/2603.23660v1) describes a200bb HUNL API with AIVAT-adjusted evaluation and explicitly distinguishes head-to-head EV performance from exploitability. This could eventually provide an additional general-strength diagnostic. It does not replace the user's required100k fresh Slumbot raw-win-rate/CI criterion.

The [official client README](https://github.com/gtowizard-ai/researcher-api-client) requires requesting an API key and approval. No application, account change, key discovery, data transmission, or API game was attempted. Its README and paper phrase variance reduction differently, so no numerical reduction factor is adopted here. The active run and its preregistered three-anchor matrix remain entirely local and unchanged; the optional API is not a blocker.

## Conditional optimizer-batch diagnostic context

[McCandlish et al., An Empirical Model of Large-Batch Training](https://arxiv.org/html/1812.06162) relates gradient covariance to useful batch size across several domains, including RL. Its simplified noise scale omits curvature; the stated assumptions include independent data, local loss geometry, and suitable learning rates. It does not establish generalization. For poker, treating multiple decisions within a hand as independent evidence would violate the independence approximation; whole-hand or independent-rollout grouping is needed. [Merrill et al., Critical Batch Size Revisited](https://arxiv.org/html/2505.23971v1) further motivates direct empirical batch comparisons rather than treating noise scale as an automatic batch-size prescription; its results concern language models, not poker.

Conditional local inference, not a change to this live run: if the complete curve misses admission, measuring fixed-weight actor-gradient agreement across independent hand groups can distinguish noisy updates from simply adding more iterations. Compare PPO-only and regularized-actor gradients, and separately account for Adam steps and actual batch size. A larger batch at unchanged learning rate also reduces optimizer-step count, so a subsequent training treatment would need to state this confound and test actual heldout poker outcomes. No result from that prospective diagnostic has been observed or claimed here.
