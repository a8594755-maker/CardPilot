# Training-hand accounting contract

Effective from `physical-hand-accounting-repair-20260830`.

`train_v5.py` historically used `total_hands` for **transition-bearing poker hands**: one marker is emitted if at least one trainable policy decision exists in the hand. A hero who never acts before the opponent folds emits no marker. Completed worker-tail hands that do not reach PPO are also absent from that counter. The legacy `actual_hand_accounting=True` flag did not establish a complete physical count.

Do not equate historical `total_hands` with paper-scale environment hands, and do not overwrite historical checkpoint counters to hide this difference. Historical physical work is unknown unless separately evidenced; paired source/mirror logs can establish a lower bound, not an exact total including unsaved worker tails.

New trainer checkpoints, manifests, and per-update metrics contain `environment_hand_accounting` with schema `cardpilot.completed_environment_hands.v1`:

- `completed_hands`: independent worker terminal count, including no-decision hands and completed unconsumed tails.
- `no_trainable_decision_hands`: completed hands with empty trainable buffers.
- `legacy_training_marker_hands`: the unchanged legacy `total_hands` counter.
- `prefix_complete`: whether the measured local run prefix is known. A new experiment with explicit hand-counter reset starts a complete local prefix; this does not claim knowledge of the inherited source model's older training history.
- `session_completed_hands` and per-worker counts: work performed in the current process session. On resume they are added once to the persisted measured prefix.

Use `--total-environment-hands N` for new physical-hand budgets. It overrides the legacy target and is checked at PPO update boundaries, so overshoot is expected and reported. The learning-rate progress uses that physical target. Without it, legacy scheduling remains unchanged. A physical-target resume with an unknown historical prefix or an already-completed endpoint fails before worker startup.

For experiment accounting, use the final complete physical count (or the increment from a preserved measured prefix), not the legacy counter. If only a lower bound is recoverable, label it explicitly and retain the old marker count separately. Never count skipped fixed-deal indices as played hands. Counter continuity is not a claim of bitwise uninterrupted rollout/RNG equivalence.

Validation evidence and the historical paired-pilot correction are in `research/experiments/physical-hand-accounting-repair-20260830/`.
