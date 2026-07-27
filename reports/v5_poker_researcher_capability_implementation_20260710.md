# V5 Poker Researcher Capability Implementation

Status: `PASS_REPORTING_ONLY_CAPABILITY_BUILT`

The V5 agent now has a machine-checked research-inference layer in addition to
its existing experiment and operations discipline. No trainer weights, rollout
behavior, Slumbot scheduling, or active EXP005 pilot flags were changed. Trainer
PID `30224` remained alive after validation.

## Capabilities added

- `v5_loss_inference_audit.py` reconstructs official hands, reports session-cluster
  bootstrap CIs, total and within-context opportunity rates, and multiplicity-
  controlled candidate/baseline slice associations. It always labels realized
  terminal loss as descriptive rather than counterfactual action regret.
- `v5_crossplay_cycle_audit.py` requires identity-bound checkpoints, result hashes,
  one greedy 200bb common-deal stream, complete seat swaps, a complete payoff
  matrix, sufficient pairs, and supported CI-clearing edges before it reports a
  panel cycle. It still refuses global non-convergence and strength claims.
- `v5_poker_research_review.py` consolidates loss, action-regret, cross-play,
  value, asset, same-start method, opponent-panel, and official evidence. Missing
  evidence remains missing. It limits one-seed method results to conditional
  claims and never launches behavior.
- `docs/V5_POKER_RESEARCHER_DECISION_CONTRACT.md` is referenced by `AGENTS.md` and
  the V5 playbook as the mandatory evidence-to-decision contract.

## Real evidence validation

The new loss audit was run over the complete 500M gate30700 official promotion
bundle and the 250M official promotion baseline:

- candidate/baseline: `20,400 / 20,400` hands;
- source sessions: `12 / 12`;
- candidate result reproduced exactly: `-153.2998529 bb/100`;
- multiplicity-controlled slice associations: `16`;
- final inference: `LOCALIZE_ONLY_COUNTERFACTUAL_OR_CONTROL_REQUIRED_FOR_INTERVENTION`;
- causal action-regret and behavior-change permissions: `false / false`.

The consolidated current review correctly reports:

- official evidence is staged promotion-scale, not formal;
- action-leak, temporal-cycle, global-nonconvergence, general-panel, L5, and L6
  claims are all blocked;
- VALUE-AUDIT support does not unlock EXP-W1 while the registered EXP005-C
  program is active;
- no new behavior change is authorized.

## Validation

- Python compile: `PASS`.
- Focused research tests: `11/11 PASS`.
- Full `test_v5_*.py` suite: `188/188 PASS`.
- EXP-002/003/005 focused suite: `8/8 PASS`.
- The unfilled cross-play template fails closed with exit code `2`.

## Honest boundary

This adds decision-analysis discipline and executable inference guards; it does
not pretend that missing scientific evidence already exists. In particular,
Slumbot logs do not contain unchosen opponent continuations, so a genuine action-
regret evaluator still requires a separately validated frozen-opponent rollout,
opponent model, or resolver design. No real cross-play panel or multi-opponent
generalization benchmark was launched in this reporting-only change.
