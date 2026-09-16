# Preregistration: history-consistent opponent-hole posterior support

## Question

The fixed-hole counterfactual target smoke failed because development action identity
was unstable and 26.6% of rows selected new all-ins despite a large apparent value
gain.  Before generating more action targets, test whether exact frozen-opponent action
histories leave enough opponent-hole posterior support to marginalize hidden cards.

## Contract

- Candidate: frozen Standard10 using the exact legacy-v4 bridge.
- Round-robin trajectory opponents: Standard10 and fresh-zero no-stop under legacy-v4;
  raw actor and procedural soup under native v6.
- Exact physical-v6 greedy trajectories, alternating candidate seat.
- Collect eight candidate decision states in every seat x street cell (64 rows), using
  seed 2026133001 and at most 5,000 complete hands.
- For each row enumerate every unordered opponent-hole pair disjoint from candidate
  holes and the observed board.
- Rebuild and replay the exact public/financial history.  Retain a hole pair only when
  the frozen opponent's greedy physical action matches every observed opponent action.
  Candidate actions are replayed as observations and do not condition the opponent
  posterior.
- Preserve every accepted pair, the true trajectory pair, public history, hashes, and
  support counts.  This experiment evaluates posterior support only; it generates no
  action targets or learned weights.

## Gate

Posterior-marginalized target generation is admitted only if:

1. the true trajectory opponent holes are present for every row;
2. every retained replay exactly reproduces public and financial state;
3. at least 95% of rows retain at least 16 hole pairs;
4. overall median support is at least 64 pairs; and
5. every seat x street median support is at least 32 pairs.

If the gate fails, do not use deterministic greedy-history filtering as a posterior;
the next method must use likelihood weighting or a stochastic behavior model.  If it
passes, start a separate posterior-marginalized 8+8 action-target reliability run;
support alone is not value, policy, or strength evidence.

Complete trajectory hands count as environment data-collection hands.  Enumerated
hole candidates are offline inference samples, not environment hands.
