# Conditional scale-up engineering note

Written while the original heads arm is running,before either frozen evaluation.
This changes no current source,configuration,budget,selection or admission rule.
No follow-up experiment has been started by this note.

The already-reviewed immutable heads prefix measures224.709physical hands/s.
An unchanged-rate2.7B extrapolation is139.07continuous days,excluding startup,
evaluation and interruptions. This is an early heads measurement,not a result
for the full-network arm or proof of any useful learning curve.

## What current source actually supports

The live path is train_v5.py:run_inference_v5,not the older
train_mp3_hybrid_h1.py:run_inference_kbest. The v5 path already vectorizes waiting
indices and transfers one flat observation batch per requested model. It then
runs each hero/opponent model group separately and copies sampled action,
log-probability and value back before releasing workers. The logged iteration32
example has mean inference batch3.1,collection23.9s and PPO0.5s. These counters
suggest studying collection/inference; they do not causally isolate GPU launch,
CPU environment work,host transfer or request scheduling as the bottleneck.

The saved current config uses single rollout,12workers,one environment per worker,
inference_min_batch_slots0. Existing opt-in multi rollout allocates W*M shared
slots and supports an accumulation threshold/deadline. Multi workers maintain
per-environment buffers and fixed-deal identities w/e/d,call the physical terminal
counter in finalize_hand,emit complete hand blocks,and discard unfinished hands
at shutdown. The availability of this code is not proof that a new throughput
configuration is correct,fast or equivalent enough for scientific comparisons.

Relevant current source locations:

- scripts/alpha_holdem/train_v5.py:2537 run_inference_v5.
- scripts/alpha_holdem/train_v5.py:2104 worker_process_v5_multi area.
- scripts/alpha_holdem/train_v5.py:2259 fixed per-slot deck stream.
- scripts/alpha_holdem/train_v5.py:2338 physical terminal count.
- scripts/alpha_holdem/train_v5.py:3327 rollout and batching options.
- scripts/alpha_holdem/train_v5.py:7116 accumulation-window dispatch.

These files are already covered by this run's immutable execution_code manifest.
The historical search in research/HISTORY.md and experiment.json records did not
locate an explicit EXP-002/multi-env throughput result; this is not a claim that
no older evidence exists outside those searched records.

## Only after the registered current run finishes

Keep the current interpretation first. If final learning evidence justifies more
physical hands,consider a separately logged throughput-contract/profile before
committing to paper-scale work. Reuse the existing multi-env path before assuming
a replacement trainer is necessary. A failed learning result may instead favor
a distinct learning-mechanism experiment; this note does not preempt that choice.

A future engineering study should first validate W1/M1 fixed-deal observation,
legal-mask,action/logprob/value,reward,terminal and hand-block correspondence.
For M>1,check independent w/e/d identity,per-seat trajectory contiguity,terminal
discounts,complete/no-decision/tail physical counts,and assignment boundaries.
Shared seeds cannot promise identical realized stochastic action streams when
batch grouping changes torch RNG consumption; distinguish distributional policy
identity from bitwise schedule equivalence. No benchmark-specific action changes.

Only after those checks,a separately fixed-weight/short-budget profile can measure
actual completed physical hands/s,decision throughput,per-model batch sizes,
collection/PPO time,memory and clean stopping across preregistered slot counts.
Keep all generated environment hands accounted even when learning rate is zero.
If runtime changes affect trajectories or update counts,do not present an old
single-mode learning result as a matched multi-mode control. Preserve optimizer,
reference,counter and resume semantics before any continued learned-weight run.
