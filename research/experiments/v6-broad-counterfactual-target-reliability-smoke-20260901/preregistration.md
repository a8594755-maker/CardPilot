# Preregistration: broad exact-v6 counterfactual target reliability smoke

## Question

Can independently confirmed, all-legal-action targets be generated broadly enough
across seat and street to justify a state-conditioned learned update?  No weights are
trained unless this target gate passes.

This is materially different from chosen-action Action-Q and the 10,752-row offline
soft-policy replay.  It uses current exact physical-v6 states, every legal physical
action, candidate-continuation rollouts, four trajectory-opponent families, and an
independent future-runout confirmation half.  The prior counterfactual and imitation
failures remain negative evidence; a positive development target alone is insufficient.

## Frozen policies and state collection

- Candidate/continuation: Standard10 under the exact legacy-v4 bridge.
- Trajectory opponents, round-robin with their own observation contracts:
  Standard10 (legacy-v4), fresh-zero no-stop (legacy-v4), raw actor (native v6),
  and procedural soup (native v6).
- Exact physical-v6 greedy trajectories, alternating candidate seat by hand.
- Collect the first 32 candidate decisions in every seat x street cell: 256 rows.
- Maximum 5,000 complete trajectory hands; failure to fill any cell invalidates the run.

## Counterfactual contract

At each frozen state, branch every legal nine-slot physical action.  Thereafter the
candidate and the trajectory opponent continue greedily under their own observation
contracts.  For every action use eight development and eight confirmation future-deck
permutations with common random numbers across actions.  Own/opponent hole cards and
the public board already observed at the state remain fixed; only unseen future cards
are resampled.  This deliberately does not claim posterior resampling over opponent
holes.  Raw states, decks/outcomes, action maps, hashes, and decisions are preserved.

The development-selected action is the largest mean return, with exact ties retaining
the source action.  Confirmation outcomes are never used for action selection.

## Gate

Training is admitted only if all conditions hold:

1. overall development/confirmation selected-action agreement >= 0.80;
2. every seat x street agreement >= 0.70;
3. the aggregate confirmation delta of the development-selected action versus the
   source action has 95% CI lower bound > 0;
4. no seat x street mean confirmation delta is negative; and
5. newly selected all-in actions are <= 5% of rows.

If the gate fails, finish as a data-reliability rejection and do not train, tune gates,
or use development outcomes to select a subset.  If it passes, freeze the dataset and
start a separate residual-policy distillation experiment with heldout state and
opponent splits; this experiment itself is not strength evidence.

Accounting distinguishes complete trajectory environment hands from counterfactual
continuation rollouts/decisions.  Only complete trajectory hands enter environment
training-hand lineage; branch continuations are offline counterfactual samples.
