# Offline deployment parity for the frozen physical1m final

Registered before new model queries. This is an outcome-blind deployment
diagnostic while independent confirmation continues unchanged. It cannot admit
any Slumbot run without that separate confirmation passing. No policy selection,
model update, external request, new deck, or strength evaluation is allowed.

Only final SHA256
bc4f62257a474ad438cd574d4c59b28ea009060749f0fb86e3e97c46120d0172.
Reuse the entire existing exogenous512-hand/4202-state corpus from
v6-common-state-retention-diagnostic-20260831/attempt01, with exact input hashes.
These original trajectories were chosen without model decisions. Replay their
recorded actions only; do not advance using candidate decisions or read any
partial strength-matrix outcome. Report512replayed validation trajectories and
4202input states separately, never as new training/evaluation/Slumbot hands.

For every state reconstruct a native full-deck state and a public Slumbot-style
state (own cards, board, action prefix and seat only). Require exact equality of
observation tensors and legal action tables, then compare native decide with the
journaled client's actual external_decision using the same preselected uniform
(independent RNG seed20261003). Require exact full decision/probability equality,
finite normalized probabilities, valid selected actions and coverage of all
eight street/seat strata. Two model calls per state:8404total, all CPU1thread.
Do not compute win rates or use the probabilities to change any policy.

Use the already live-audited journaled source runtime's immutable source copy.
Verify every loaded poker runtime file is hash-identical to the ongoing
confirmation's captured version. Block socket connection attempts and record
zero network activity. Preserve all76active source/copy pairs, frozen weights,
parent evidence and original corpus. Create this experiment's own code snapshot,
hashes, exact commands, per-state results and audit summary.

Passing establishes candidate-specific inference/input parity on this fixed
corpus only, not universal API compatibility, playing strength or100kqualification.
No automatic live run, retry, changed corpus or checkpoint fallback. Preserve
failure evidence and record the limitation if any check fails.

Command: python research/experiments/v6-physical1m-deployment-parity-20260831/run_parity.py
