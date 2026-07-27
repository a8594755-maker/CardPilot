# V5 Poker Researcher Decision Contract

This contract governs how the V5 agent turns poker evidence into research
decisions. It complements the training playbook: the playbook governs how an
experiment runs; this document governs what the evidence is allowed to mean.

The final claim contract is unchanged. L5 requires at least 100,000 official
greedy-direct Slumbot hands, positive bb/100, and a 95% CI lower bound above
zero. L6 additionally requires performance near +11.1 bb/100.

## 1. Evidence levels

Every finding must be assigned exactly one level before it appears in a method
selection or intervention plan.

| Level | Examples | May justify | May not justify |
|---|---|---|---|
| `OPS` | health, PID, h/s, stderr, watcher coverage | incident response, validity | poker strength or strategy change |
| `OBSERVATIONAL` | raw loss bucket, action rate, hole-family loss | localization and hypotheses | action regret or causal leak |
| `ASSOCIATIONAL` | uncertainty-aware candidate/base slice difference | repeated mechanism support | unchosen-action EV |
| `COUNTERFACTUAL` | validated same-information-state action comparison | action-specific experiment registration | Slumbot strength |
| `SAME_START_CAUSAL` | frozen checkpoint control/treatment with common deals | method PASS/FAIL for the registered scope | general method claim from one seed |
| `CROSSPLAY` | complete duplicate-deal snapshot payoff matrix | panel non-transitivity/cycle diagnosis | global non-convergence or Slumbot strength |
| `EXTERNAL_STAGED` | official greedy quick5k/promotion20k | calibration/promotion | L5/L6 |
| `FORMAL_EXTERNAL` | official greedy 100k+ with valid CI | L5/L6 under exact rules | claims outside the tested harness |

An artifact cannot be promoted to a higher level by narrative agreement. Two
observational signals remain observational unless a registered design identifies
the counterfactual.

## 2. Required research loop

1. State the exact question and estimand. Examples: treatment endpoint minus
   control endpoint on common deals; action regret at a frozen information-state
   family; or whether a frozen snapshot panel contains a supported cycle.
2. Validate the harness, policy mode, stack, action/observation version,
   checkpoint identity, source hashes, and statistical unit.
3. Localize losses with position/action/terminal/street/hole cuts and uncertainty.
   This generates hypotheses only.
4. Connect the observation to a code-level upstream mechanism. Explicitly list
   confounders and downstream symptoms.
5. Pre-register the minimum meaningful effect, sample size, CI, abort, rollback,
   multiplicity treatment, seed scope, and terminal PASS/FAIL/INCONCLUSIVE rule.
6. Use same-start control/treatment for training-method questions. Use common
   deal IDs and complete seat swaps for poker payoff questions.
7. Freeze and audit the first eligible endpoint. Never substitute a later
   checkpoint, extend an inconclusive sample, or add a post-hoc seed.
8. Judge the registered estimand. Then separately test external validity against
   Slumbot and an opponent panel.
9. Record what was falsified, what remains unknown, and whether the result applies
   to one trained model, one seed, or a general method.
10. Apply the registered program stop/pivot rule. Remaining compute budget is not
    evidence.

## 3. Poker loss inference rules

Raw realized payoff answers where chips were won or lost, not what would have
happened after an unchosen action.

- `hero_fold` is accounting-defined negative after money was committed. Its loss
  is not proof that folding was wrong.
- A losing preflop line mixes card distribution, opponent response, later play,
  pot size, and selection into that line. It is not the EV of the first action.
- Weak hole families are expected to lose. Compare opportunity-normalized,
  uncertainty-aware candidate/base changes before calling the pattern unusual.
- Top-loss tables are post-hoc high-cardinality searches. Use predeclared slices,
  minimum counts, session-cluster uncertainty, and multiplicity control.
- An action-specific intervention requires a validated counterfactual estimator
  or a separately registered same-state controlled experiment.

Run `v5_loss_inference_audit.py` after every complete official bundle. Its output
is always descriptive/associational and cannot authorize tuning alone.

## 4. Action regret contract

Until a valid estimator exists, the correct output is `ACTION_REGRET_MISSING`, not
an approximate causal claim.

A future `v5.action_regret.audit.v1` artifact is accepted only when all are true:

- the estimator is validated on controlled fixtures with known action values;
- chosen and alternative actions begin from the same information state;
- all compared actions are legal under the exact v55/9slot contract;
- opponent continuation and chance sampling are frozen or explicitly modeled;
- state families and multiplicity rules were selected before outcomes were read;
- uncertainty covers state sampling, chance, and rollout/opponent-model error;
- the artifact declares its scope as internal-model counterfactual or external;
- no Slumbot strength claim is made from an internal opponent model.

The current Slumbot dump does not contain counterfactual opponent responses.
Therefore replaying its realized terminal winnings under imagined actions would
be invalid. Building an opponent model, resolver, or same-state rollout harness
is a separate registered measurement experiment.

## 5. Self-play cycle contract

Action-frequency swings, KL, value loss, and 200-hand probes may nominate a cycle
hypothesis but cannot prove it.

A temporal self-play cycle requires:

- at least three identity-bound ordered snapshots;
- every unordered pair evaluated on a frozen common-deal stream with both seats;
- one policy mode, stack, environment, and action contract;
- a complete payoff matrix with preregistered pair count and CI;
- supported directed edges whose CIs clear the registered margin;
- a supported directed cycle such as A > B, B > C, C > A.

Even then, the claim is limited to non-transitivity in the tested snapshot panel.
It does not prove global non-convergence, exploitability, or Slumbot strength.

Use `v5_crossplay_cycle_audit.py` to validate and classify a matrix.

## 6. Seed and generalization scope

- One paired training seed can select a single candidate model if the registered
  same-start experiment and external promotion gates pass.
- One seed cannot establish that a training method generally improves poker play.
- A general method claim requires at least two preregistered independent paired
  seeds; three is preferred when compute permits.
- Adding a seed after seeing an endpoint is a new confirmatory experiment, never
  an extension of the original result.
- Slumbot is the acceptance opponent, but a general 200bb HUNL description also
  requires a frozen opponent panel or restricted-best-response evidence.

## 7. Research inference review

Before any new behavior experiment is selected, run
`v5_poker_research_review.py` over the available loss, action-regret, cross-play,
value, asset, method, and official artifacts.

The reviewer is fail-closed:

- descriptive loss never unlocks action-specific tuning;
- value calibration can support EXP-W1 only after the registered program stop;
- asset compatibility can support EXP-W2 only after the registered program stop;
- EXP-W1 and EXP-W2 can never be bundled;
- a single-seed method PASS is labeled conditional;
- no review artifact launches a trainer or changes behavior;
- L5/L6 remain formal official claims only.

Example reporting-only commands:

```powershell
python scripts/alpha_holdem/v5_loss_inference_audit.py `
  --candidate-dumps "models/<official-tag>_part*_dump.jsonl" `
  --label <official-tag> `
  --out-json reports/<tag>_loss_inference.json `
  --out-md reports/<tag>_loss_inference.md

python scripts/alpha_holdem/v5_crossplay_cycle_audit.py `
  --matrix-json reports/<design>_crossplay_matrix.json `
  --out-json reports/<design>_cycle_audit.json `
  --out-md reports/<design>_cycle_audit.md

python scripts/alpha_holdem/v5_poker_research_review.py `
  --loss-inference-json reports/<tag>_loss_inference.json `
  --value-audit-json reports/v5_value_audit_001_20260710.json `
  --asset-audit-json reports/v5_asset_audit_001_20260710.json `
  --official-result-json reports/v5_500m_promotion_loss_review_20260710.json `
  --program-state ACTIVE_REGISTERED_EXPERIMENT `
  --out-json reports/<tag>_research_review.json `
  --out-md reports/<tag>_research_review.md
```

## 8. Decision language

Use precise statements:

- `localized`: a realized-outcome slice is unusual or costly.
- `associated`: candidate/base differences persist with uncertainty control.
- `supports hypothesis`: multiple evidence classes agree, but causality is not
  identified.
- `causal for this seed/window`: a registered same-start experiment passed.
- `general method effect`: multiple preregistered independent paired seeds passed.
- `panel cycle`: a complete cross-play audit found a supported cycle.
- `beats Slumbot`: only the formal official L5 rule passed.

Never substitute `looks wrong`, `obviously leaking`, `value head learned nothing`,
or `training is non-convergent` for the evidence class and exact estimand.
