# Static current-KL 1M-to-2M scale preregistration

## Rationale

The seed-matched 262k-to-1M experiment had positive internal slopes in two of
three seeds and positive median slope, while Standard10 drift remained small.
Only one seed met the full breadth gate, so the result was insufficient rather
than a promotion or rejection. A subsequent fresh 24,576-hand critic audit did
not reproduce a high-pot-specific calibration failure: pooled 1M-minus-262k
high-pot squared-error delta was negative and only one seed pointed toward
worsening. There is therefore no mechanism-level reason to patch high-pot
actions or abandon this preserved learned-policy method at one million hands.

This stage doubles each lineage to at least 2,097,152 cumulative physical
environment hands. It is the next geometric observation, not a benchmark claim.
No Slumbot calls are authorized by this experiment.

## Exact continuation contract

The frozen 1M parent checkpoint SHA256 values are:

- seed1: `1fdc7ebc2560888938cc55bbf6c9eef05deb2e5c9270fbebb123d3143357dbe3`
- seed2: `d17081e1d611f9c1bbc4129c715211780d2c8e1f48519c8699b071481a85e27c`
- seed3: `9c3235d2254d923103730310946b1c23be3e3122068f68bdc9e6273554bd9ee5`

Each continuation preserves the same model, optimizer and current learning rate,
serialized two-iteration complete-hand replay and replay RNG, loss-K-best pool
state and history, adaptive-league statistics, run ID, transition and physical
counters, and hash-chained opponent-assignment evidence. The static reference
remains Standard10 SHA256
`91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`
with coefficient 1, direction `current_to_reference`, and no refresh.

The training configuration otherwise remains identical to the 1M stage:
physical-v6/legacy-v4 observation bridge, 12 workers, 4096 hands/update,
sampled hero execution, all policy heads plus critic-v2, PPO epochs 2,
target-KL 0.01, LR preserved at 1e-4, entropy coefficient 0.005/floor 0.05,
25% self-play, adaptive loss-K-best league, replay ratio 0.5, and fixed training
deal streams. New continuation deal starts are 33.3M, 34.3M, and 35.3M and must
pass the staging tool's per-worker non-overlap bound. Only the suffix beyond each
parent's physical counter counts as new environment training hands.

## Evaluation and next scale gate

After all three lineages reach the physical target, compare the frozen 1M parents
and 2M endpoints on new common-deck deals against Standard10, CFR4, legacy iter16,
and legacy mixed65k in both seats, with independent seeds and no endpoint selected
from training rewards. Also audit 20,000 fresh offline Standard10 drift states per
endpoint. Raw deck evidence must be disjoint from every prior static-current-KL
evaluation corpus.

Continue to 4M only if all causal/evidence checks pass, drift remains below mean-TV
0.08 and greedy-disagreement 0.12, at least two seeds have positive 1M-to-2M pooled
slopes, the median slope is positive, and at least two seeds avoid a replicated
broad reversal (defined as both seat slopes negative or at least three of four
anchor slopes negative). A stricter breadth-positive result strengthens the case
but is not required to observe the next geometric point because 2M remains tiny
relative to paper scale. Reject only for replicated broad reversal, catastrophic
drift, or a causal mechanics/evidence failure. Mixed non-catastrophic results stop
for diagnosis rather than being called proof the long-horizon method cannot work.

