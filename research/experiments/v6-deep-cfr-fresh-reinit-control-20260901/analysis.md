# Exact-v6 Deep CFR fresh-reinit versus warm control

Decision: `ADMIT_PAPER_FRESH_REINIT`.

Both arms used epsilon 0, the paper's sequential player loop, identical initial
weights and common decks, 512 optimizer steps per update, and the same
iteration-weighted per-hand snapshot/action-sampled deployment contract.

Fresh reinitialization improved two of three generic anchors and raised the
three-anchor mean from -111.26 to +213.74 bb/100, a +325.01 delta. It also
preserved nonzero traverser coverage in every seat×iteration cell, while warm
had zero player-0 nodes in iteration 2. The fresh arm did not improve min-bet and
its mean log imbalance was slightly worse (4.035 versus 3.745). All 256-pair
intervals remain broad, so the result selects an algorithm contract rather than
establishing policy strength.

Fresh training losses were materially lower and more stable (39.4--65.2) than
warm's early/late range, consistent with Brown et al.'s report that training the
value model from random initialization each CFR iteration improves convergence.

The remaining coverage imbalance is dominated by K=2 root traversals, orders of
magnitude below the paper's regime. The next scale step should increase
traversals per player while holding iterations, fresh reinit, epsilon0, network,
and optimizer dose fixed. This reduces the probability that both sampled roots
terminate before the traverser acts and provides a more meaningful regret
corpus before considering more CFR iterations.
