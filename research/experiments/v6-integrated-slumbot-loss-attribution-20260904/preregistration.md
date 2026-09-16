# V6 integrated Slumbot loss attribution

## Purpose

Use the already-audited, independent Seed1 1M and 2M fresh-20k Slumbot hand
corpora to localize general state classes associated with external loss.  This
experiment consumes no new Slumbot or training hands and must not turn observed
Slumbot actions or per-hand outcomes into action labels.

## Frozen inputs

- 1M corpus: `v6-integrated-seed1-1m-greedy-fresh20k-slumbot-20260903`,
  frozen policy SHA256 `6fbbe021b140b91e448917ae3e2cbb9bcdca444865433074ac944cae79fa844a`.
- 2M corpus: `v6-integrated-seed1-2m-greedy-fresh20k-slumbot-20260903`,
  frozen policy SHA256 `993fe99bd0a5ac0eaa0135e449315752d99efc25bedf220f93a1ad08884344c3`.
- CPU-exact 124,121-state replay from
  `v6-integrated-1m-2m-slumbot-state-drift-20260903`.
- Standard10 SHA256
  `91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`.
- CFR4 frozen teacher SHA256
  `571a9c413834247c80b63a797548689ea745878c060f265876d00bddcc3ff2db`.

Every input record, raw hand file, replay file, and checkpoint hash must be
verified before analysis.  The script refuses to overwrite evidence.

## Discovery and confirmation

Sessions 1--4 of each corpus are discovery data.  Sessions 5--8 are untouched
confirmation data.  Candidate hand classes are fixed before looking at the
confirmation outcomes:

- single fields: seat, terminal type, maximum reached street, preflop raise
  topology, maximum exposure bucket, final-decision street, final-decision
  action class, final pot bucket, and minimum/final policy-margin bucket;
- fixed interactions: seat x maximum street, seat x preflop topology, final
  street x action class, final street x exposure, and terminal type x exposure.

For every class, compute hands, net bb, bb/100, loss contribution, its bb/100
difference from the complement, and per-session direction.  Large-win/loss
tails are reported descriptively but cannot be candidate definitions.

Discovery may nominate at most 12 classes having at least 200 hands in each
corpus half, negative class-minus-complement bb/100 in both corpora, and the
largest pooled negative excess contribution.  A class confirms only when:

1. it still has at least 200 hands in each confirmation corpus;
2. class-minus-complement is at most -10 bb/100 in both confirmation corpora;
3. the class bb/100 is negative in at least 3 of 4 confirmation sessions in
   each corpus; and
4. its direction is therefore replicated across cohort and session rather than
   being driven by one tail hand.

## Solver-teacher proxy validation

Replay CFR4 only on the final hero decision of each audited hand.  A proxy row
is admissible when Standard10 and CFR4 select the same physical action and both
greedy margins are at least 0.05.  For each confirmed class, compare the frozen
on-policy action's disagreement with that high-confidence consensus against the
class complement, separately in both confirmation corpora.  Proxy support
requires at least 100 admissible rows per side and a disagreement-rate uplift
of at least 0.02 in both corpora.

This is a matched-state solver-teacher proxy, not a causal action-value estimate:
the two teachers can share errors, and earlier fixed-hole/posterior one-step
counterfactual targets were explicitly unreliable.  Unsupported classes remain
descriptive correlations and cannot motivate an action patch.

## Decision

- `ADMIT_GENERAL_STATE_CLASS_INTERVENTION` only if at least one class passes all
  confirmation and proxy requirements.  The follow-up may alter only general
  training distribution, value calibration, or solver supervision and must use
  fresh internal data plus a new blinded external cohort.
- Otherwise `NO_REPLICATED_CAUSAL_PROXY`; do not train from this attribution.
  Return to broad long-horizon self-play/league alternatives or scale only a
  method whose geometric multi-seed evidence remains positive.

