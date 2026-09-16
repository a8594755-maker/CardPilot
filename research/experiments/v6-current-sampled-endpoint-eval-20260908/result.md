# Current sampled endpoint result

Completed all 65,536 preregistered internal executions on16,384 distinct decks;
zero new training or Slumbot hands. Runner exited0 after971.407 seconds. Independent
ordered raw review passed prescribed deck/action keys, four policy-seat cells,
bounded finite rewards, counts and frozen input hashes. Reviewer tests passed3
cases including mutation subcases. These checks do not constitute decision-level
replay of every hand. Raw hand JSONL remains the authoritative retained evidence.

Endpoint minus original parent, bb/100 with conditional unadjusted95% CIs:

| Seed | Pooled | Preservation | Transfer | Seat0 / Seat1 points |
| --- | --- | --- | --- | --- |
| 1 | -4.05 [-24.29,16.19] | 6.98 [-22.60,36.56] | -15.08 [-42.71,12.56] | -4.27 / -3.82 |
| 3 | 2.69 [-16.63,22.00] | 4.60 [-25.33,34.53] | 0.77 [-23.66,25.20] | -5.83 / 11.20 |

Directional support is false: pooled direction differs by seed, Seed1 transfer
is negative, and seat0 points are negative in both seeds. All pooled/panel/seat
intervals cross zero. This does NOT prove equivalence, degradation, or absence of
small improvements: pooled half-widths are approximately20.24 and19.32bb/100.
No large hidden sampled gain is established, and the claim that greedy evaluation
alone explains the plateau is unsupported. Greedy comparisons used other decks;
these results are not a paired causal estimate of execution-mode effects.

Known anchors share ancestry and do not establish unseen-family generalization.
The original training population also includes adaptive recent opponents; this
fixed panel is not exactly its on-policy reward distribution.

Decision: do not expand this execution-mode diagnostic, promote an endpoint, or
automatically allocate more unchanged training. Preserve all lineages. The next
material intervention should address the policy-improvement learning signal or
objective, checked against already completed gradient, replay, KL, margin and
counterfactual controls. Restrict source/history review to selecting that single
intervention and proceed to implementation, not another open-ended audit chain.
Neither switching to sampled deployment nor adding an independent critic has
earned a scale allocation from the evidence collected here.
