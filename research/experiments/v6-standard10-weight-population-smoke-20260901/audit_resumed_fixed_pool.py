"""Resume-aware audit for the immutable iteration-27 to iteration-42 session."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RUN = BASE / "production/train"
PARENT = BASE / "frozen/parent_raw.pt"
ENDPOINT = RUN / "latest.pt"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
ENDPOINT_SHA = "5a39b7df564d42a1dba3fe6890cf363e1c6218f9d7414715c97192f6658d527e"
START_ITERATION = 27
FINAL_ITERATION = 42
START_PHYSICAL = 132553
TARGET_PHYSICAL = 198089
FINAL_PHYSICAL = 198177
ACTOR_TRAINABLE_PREFIXES = ("policy_head.", "preflop_policy_head.", "value_head.")
ARCHIVE_RE = re.compile(r"checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt$")

sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))
from train_v5 import build_group_opponent_assignments, validate_environment_hand_accounting


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical_assignment_hash(row):
    value = dict(row)
    value.pop("record_sha256", None)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def finite_tree(value):
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, list):
        return all(finite_tree(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def main():
    if sys.argv[1:]:
        raise ValueError("no arguments")
    assert sha(PARENT) == PARENT_SHA and sha(ENDPOINT) == ENDPOINT_SHA
    parent = torch.load(PARENT, map_location="cpu", weights_only=False)
    endpoint = torch.load(ENDPOINT, map_location="cpu", weights_only=False)
    manifest = json.loads((RUN / "run_manifest.json").read_text(encoding="utf-8"))
    metrics = rows(RUN / "h1_training_metrics.jsonl")
    assignments = rows(RUN / "opponent_assignments.jsonl")
    config = endpoint["config"]
    assert parent["iteration"] == START_ITERATION and endpoint["iteration"] == FINAL_ITERATION
    assert [row["iteration"] for row in metrics] == list(range(START_ITERATION + 1, FINAL_ITERATION + 1))
    assert [row["applies_to_iteration"] for row in assignments] == list(range(START_ITERATION + 1, FINAL_ITERATION + 1))
    assert len(metrics) == len(assignments) == FINAL_ITERATION - START_ITERATION
    assert manifest["status"] == "finished" and manifest["iteration"] == FINAL_ITERATION
    assert manifest["total_hands"] == endpoint["total_hands"] == metrics[-1]["hands"]
    assert all(left < right for left, right in zip([parent["total_hands"]] + [row["hands"] for row in metrics[:-1]],
                                                   [row["hands"] for row in metrics]))
    assert all(row["run_id"] == endpoint["run_id"] == parent["run_id"] for row in metrics)
    assert all(row["policy_advantage_normalization"] == "global" for row in metrics)
    assert finite_tree(metrics)

    parent_account = parent["environment_hand_accounting"]
    endpoint_account = endpoint["environment_hand_accounting"]
    manifest_account = manifest["environment_hand_accounting"]
    validate_environment_hand_accounting(parent_account)
    validate_environment_hand_accounting(endpoint_account)
    validate_environment_hand_accounting(manifest_account)
    assert parent_account["completed_hands"] == START_PHYSICAL
    assert endpoint_account["completed_hands"] == manifest_account["completed_hands"] == FINAL_PHYSICAL
    assert endpoint_account["completed_hands"] >= TARGET_PHYSICAL
    assert endpoint_account["completed_hands"] - parent_account["completed_hands"] == 65624
    physical = [row["environment_hand_accounting"]["completed_hands"] for row in metrics]
    assert all(left < right for left, right in zip([START_PHYSICAL] + physical[:-1], physical))
    assert physical[-1] == FINAL_PHYSICAL
    assert endpoint_account["prefix_complete"] and endpoint_account["unknown_prefix_training_marker_hands"] == 0
    assert sum(row["completed_hands"] for row in endpoint_account["session_worker_counts"]) == endpoint_account["session_completed_hands"]
    assert endpoint_account["session_completed_hands"] == 65624

    exact_config = {
        "total_environment_hands": TARGET_PHYSICAL, "fixed_training_deal_start_index": START_PHYSICAL,
        "fixed_training_deal_stream": True, "reset_optimizer": False, "reset_hand_counter": False,
        "preserve_resumed_optimizer_lr": True, "source_policy_kl_coef": 0.1,
        "all_policy_heads_only_training": True, "ppo_replay_ratio": 0.0,
        "ppo_replay_buffer_iterations": 0, "seed": 20261103, "worker_seed_base": 2026110300,
        "self_play_fraction": 0.25, "opponent_assignment": "per-group", "opponent_groups": 8,
        "pool_strategy": "latest", "archive_checkpoint_every": 8, "save_interval": 1,
    }
    for key, value in exact_config.items():
        assert config[key] == value, (key, config[key], value)
    assert config["resume"] == str(PARENT)
    assert config["source_policy_reference_checkpoint"] == str(PARENT)
    assert endpoint["optimizer"]["param_groups"][0]["lr"] == parent["optimizer"]["param_groups"][0]["lr"]
    assert abs(endpoint["optimizer"]["param_groups"][0]["lr"] - 1e-5) < 1e-12
    assert endpoint["actor_ema_updates"] == FINAL_ITERATION and parent["actor_ema_updates"] == START_ITERATION
    assert not endpoint.get("ppo_replay_entries") and endpoint.get("ppo_replay_cumulative_rows", 0) == 0
    assert all(torch.equal(endpoint["model"][name], tensor) for name, tensor in parent["model"].items()
               if not name.startswith(ACTOR_TRAINABLE_PREFIXES))
    assert any(not torch.equal(endpoint["model"][name], parent["model"][name]) for name in parent["model"]
               if name.startswith(ACTOR_TRAINABLE_PREFIXES))
    assert all(torch.isfinite(tensor).all() for tensor in endpoint["model"].values())
    parent_steps = sorted(int(state["step"].item()) for state in parent["optimizer"]["state"].values())
    endpoint_steps = sorted(int(state["step"].item()) for state in endpoint["optimizer"]["state"].values())
    assert len(parent_steps) == len(endpoint_steps) == 10
    assert all(after > before for before, after in zip(parent_steps, endpoint_steps))

    pool = endpoint["pool_snapshots"]
    assert len(pool) == 5 and len(endpoint["pool_candidate_history"]) == 5
    pool_ids = [row["id"] for row in pool]
    configured = [str(Path(path).resolve()) for path in config["fixed_opponent_checkpoints"]]
    recorded = [str(Path(row["score_components"]["checkpoint"]).resolve()) for row in pool]
    assert configured == recorded
    for path, row in zip(configured, pool):
        assert sha(path) == row["score_components"]["checkpoint_sha256"]
        assert row["score_components"]["kind"] == "fixed_external_opponent"
    assert len(endpoint["adaptive_opponent_weights"]) == 5
    assert abs(sum(endpoint["adaptive_opponent_weights"]) - 1.0) < 1e-9

    rng = random.Random(int(config["seed"]))
    previous_sha = None
    prior_hands = parent["total_hands"]
    for assignment, metric in zip(assignments, metrics):
        iteration = assignment["applies_to_iteration"]
        assert assignment["previous_record_sha256"] == previous_sha
        assert assignment["record_sha256"] == canonical_assignment_hash(assignment)
        assert assignment["total_hands_before_iteration"] == prior_hands
        assert assignment["worker_count"] == config["workers"] and assignment["pool_size"] == 5
        assert [row["snapshot_id"] for row in assignment["pool_snapshot_refs"]] == pool_ids
        generated, _ = build_group_opponent_assignments(
            worker_count=config["workers"], pool_size=5, group_count=config["opponent_groups"],
            self_play_fraction=config["self_play_fraction"], rng=rng,
            pool_weights=assignment["pool_sampling_weights"],
        )
        recorded_workers = [row["opponent"]["local_index"] for row in assignment["workers"]]
        assert generated.tolist() == recorded_workers, iteration
        previous_sha = assignment["record_sha256"]
        prior_hands = metric["hands"]

    archives = []
    for path in sorted((RUN / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        match = ARCHIVE_RE.match(path.name)
        assert match
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        iteration, hands = int(match["iteration"]), int(match["hands"])
        assert checkpoint["iteration"] == iteration and checkpoint["total_hands"] == hands
        assert next(row["hands"] for row in metrics if row["iteration"] == iteration) == hands
        archives.append({"iteration": iteration, "hands": hands, "path": str(path), "sha256": sha(path)})
    assert [row["iteration"] for row in archives] == [32, 40]

    result = {
        "schema": "cardpilot.train_v5.resumed_fixed_pool_session_audit.v1", "status": "PASS",
        "parent_iteration": START_ITERATION, "final_iteration": FINAL_ITERATION,
        "metric_iterations": [START_ITERATION + 1, FINAL_ITERATION], "metric_rows": len(metrics),
        "assignment_iterations": [START_ITERATION + 1, FINAL_ITERATION], "assignment_rows": len(assignments),
        "assignment_tail_sha256": previous_sha, "parent_environment_hands": START_PHYSICAL,
        "final_environment_hands": FINAL_PHYSICAL, "new_environment_hands": 65624,
        "target_environment_hands": TARGET_PHYSICAL, "optimizer_lr": endpoint["optimizer"]["param_groups"][0]["lr"],
        "optimizer_step_min": min(endpoint_steps), "optimizer_step_max": max(endpoint_steps),
        "fixed_opponents": [{"path": path, "sha256": sha(path)} for path in configured],
        "archives": archives, "checkpoint_sha256": ENDPOINT_SHA,
        "original_auditor_failure": "training metric iterations are not exactly contiguous because shared auditor assumes iteration1 session start",
        "artifacts": {name: {"path": str(path), "sha256": sha(path)} for name, path in {
            "checkpoint": ENDPOINT, "manifest": RUN / "run_manifest.json", "metrics": RUN / "h1_training_metrics.jsonl",
            "assignments": RUN / "opponent_assignments.jsonl", "train_log": RUN / "latest_train.log",
            "original_audit_stdout": RUN / "audit_stdout.log", "parent": PARENT,
        }.items()},
    }
    (RUN / "resume_session_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
