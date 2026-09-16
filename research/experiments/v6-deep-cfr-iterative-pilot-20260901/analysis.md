# Exact-v6 iterative neural regret pilot

Decision: `REJECT_ITERATIVE_NEURAL_REGRET_PILOT`.

All 12 planned roots and 6,144 fixed-panel evaluation hands completed. The run
visited 74,953 decision nodes and 48,271 terminal branches without reaching the
250,000-node fail-only limit. Every checkpoint includes networks, full reservoir
contents, strategy snapshots, and Python/NumPy/Torch traversal RNG states; the
terminal checkpoint reloaded exactly.

The terminal policy moved strongly from passive (mean greedy argmax movement
67.9%), but movement did not translate into a coherent generic-anchor curve.
The fixed-panel greedy mean across call-station, uniform, and min-bet fell from
+69.26 at initialization to -359.11 bb/100. Only call-station improved; terminal
uniform was -982.56 and min-bet -375.92 bb/100, with very wide 128-pair intervals.
No larger pilot is admitted.

The traversal accounting exposes a likely algorithmic confound. Within each
iteration the runner collected and updated player 0 before collecting player 1,
so the two traversers did not see the same frozen strategy profile. At iteration
2, player 0 produced 1,203 traverser nodes while player 1, already responding to
updated player 0, produced 9,674. At iteration 3 player 0 collapsed to only 154
new traverser nodes versus 2,324 for player 1. Fixed update steps then operated
on sharply unequal buffers. This sequential-update behavior also exists in the
legacy trainer and is not faithful to a simultaneous CFR iteration.

Highest-information next step: a matched synchronization control from identical
initial weights and common decks. Collect both traversers against frozen
iteration-start networks before updating either player, compare node/sample
imbalance and terminal fixed-panel behavior with the sequential treatment, and
do not increase root count. A positive result would justify changing the trainer;
a negative result would weaken the neural-regret route.
