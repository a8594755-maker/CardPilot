# Corrected-v6 real-GPU multi-environment throughput and health qualification

The completed KL0.1 retention pilot failed its preregistered strength gate. Do
not promote its control, intermediate checkpoints, or final. This experiment
addresses measured collection overhead before increasing useful training volume.
It is not a strength experiment and authorizes no Slumbot hands or confirmation.

## Fixed design, recorded before execution

Run exactly three fresh-start arms in order: single1, multi4, multi8. Each uses
12 workers and respectively single/1, multi/4, multi/8 environments per worker.
Each stops at the first completed PPO-update boundary reaching 32,768 independently
counted physical terminal hands. Record overshoot, no-decision hands, completed
but unconsumed transitions, and shutdown counter tail, without relabeling them as
optimizer-consumed training. No performance-based early stop or extra arm.

All arms reuse the original Standard10 tensors (SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428),
with explicit new v6 binding, fresh Adam and counters, distinct run/output IDs.
Parent exact-command evidence is v6-full-network-learning-curve-20260831,
execution.json SHA256
47e842579af7d536b09571db45e8bd02620d52afe614d0bdbdca13ee2640b41c.
Keep that command's learning regimen: full network, source KL0.01, PPO2 epochs,
target KL0.01, LR0.00003, minibatch1024, collection4096 legacy hand markers,
GN critic_v2, source reference and fixed adaptive training anchors0/1/2,
self-play fraction0.25 and 8 opponent groups. Seed20260925 and worker seed base
2026092500 are shared by the three arms. Slot-specific fixed decks are generated
from (worker_seed, env_index, deal_index); added slots introduce different streams.
This is not an identical-deal or identical-learning-trajectory experiment.

Common options: validate-stream enabled on all consumed worker packets,
inference-min-batch-slots0 (no deliberate accumulation), deadline700us, archive
every4 updates and save every update. Runtime safety cap1200 seconds per arm.
Run sequentially on the single GPU, no other research computation in parallel.
Do not retry, overwrite, or resume failed/interrupted arms automatically.

## Evidence and decision

Primary rate is actual completed physical hands divided by trainer subprocess
wall seconds, including startup, saves, and shutdown. Secondary rate uses logged
collection+PPO time (rounded0.1s); show both all updates and the prespecified
window excluding only update1. Report per-update inference batch means, PPO KL,
reference KL, optimizer steps, changed/finite tensors, and accounting. No IID
timing CI or causal / multi-seed speed claim from one ordered run per arm.

Mandatory health: normal trainer exit, target reached at first update boundary,
contiguous metrics, complete physical prefix and worker counter sums, validated
whole-hand packets, finite changed model and Adam states, exact fixed-anchor
identities, assignment-chain/RNG replay and fixed-pool session audit, immutable
code/checkpoint evidence. Preserve all artifacts and partial counts on failure.
The existing trainer can terminate workers after its shutdown timeout; its exit0
alone does not establish all workers exited normally. Per-slot interrupted resume
is NOT qualified: cursors/in-flight slots are not serialized. Fresh starts only.
Packet structure checks do not independently replay every training hand's rules;
the prior fixed-action CPU contract and independent rules-oracle audits provide
separate, narrower validation.

If all three health audits pass, choose the fastest multi arm only when its
primary and warm-window secondary rates are each at least1.25x single1; otherwise
retain single1 and diagnose the measured bottleneck. Tie-break on primary rate,
then fewer environments. This chooses an implementation configuration only, never
a policy checkpoint. Any next strength experiment needs a new preregistered
training budget/league and untouched evaluation; these short-arm weights are not
eligible for external promotion. Count actual physical executions as new training
hands, but evaluation_hands=0 and slumbot_hands=0 throughout.
