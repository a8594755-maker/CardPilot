# Execution-contract context for the terminal research decision

Read while the final frozen evaluation was live. No new training, model queries,
evaluation hands or execution-mode changes were made.

The actual Seed1 full stage2 `command.json` explicitly selects
`--hero-policy-mode sample` and does not override hero temperature. In
`scripts/alpha_holdem/train_v5.py`, the parser defaults hero temperature to1.
`run_inference_v5` samples the hero at this temperature and samples neural pool
opponents at temperature1. Final metrics confirm hero and reference temperature1.
The present preregistered internal evaluator uses greedy execution. Thus training
and testing differ in policy execution; this is a distribution difference, not
by itself an implementation error or evidence that sampled deployment is better.

Relevant existing negative evidence, not new ideas:

- `sampled-policy-frozen-diagnostic-20260830`:73,856 frozen sampled-both-sides
  internal hands, exact self-match cancellation and unchanged model hashes. Neither
  learned candidate satisfied the preregistered cross-anchor confirmation gate.
- `physical1m-sampled-independent-confirmation-20260830`:98,304 independent
  sampled internal hands. Anchor deltas+1.913,-1.276,+12.192bb/100, all adjusted
  intervals crossed zero; consistent cross-anchor improvement was not established.
- `v6-low-temperature-65k-pilot-20260901`:142,592 physical training hands across
  the T1/T0.5 comparison,49,152 internal evaluation hands. Pooled difference
  -0.422648 CI[-19.301541,18.456244], Standard10 -27.073975
  CI[-52.689087,-1.458862]. The low-temperature route did not retain its smoke gain.
- The earlier Standard10 strict-sampled20k result was-48.9778bb/100; the earlier
  full-network strict-sampled20k result was-81.2510bb/100. These are older weights
  and contracts, not results of the present frozen endpoints.

These records do not test the present exact four endpoints under sampled
execution, but they materially weaken a claim that changing temperature or
sampling alone is an untested easy solution. Any renewed execution-mode study
would need an explicit compute-allocation question and a frozen matched contract;
do not automatically repeat an old diagnostic or alter the live pilot. Assess
the complete current two-seed learning curves before choosing the next experiment.
