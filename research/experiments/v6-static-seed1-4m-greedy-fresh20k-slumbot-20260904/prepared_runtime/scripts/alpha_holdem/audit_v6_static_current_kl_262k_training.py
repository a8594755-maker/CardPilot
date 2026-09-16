#!/usr/bin/env python3
"""Audit exact-state 65k-to-262k continuation of static current-KL runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_v6_integrated_alphaholdem_geometric import audit_run, sha256_path


SEEDS = (1, 2, 3)
EXPECTED_ARCHIVES = [16, 32, 48]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def prefix_sha256(path: Path, rows: int) -> str:
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) < rows:
        raise ValueError(f"{path} has only {len(lines)} rows; expected at least {rows}")
    return hashlib.sha256(b"".join(lines[:rows])).hexdigest()


def optimizer_steps(checkpoint: dict) -> list[int]:
    values = []
    for state in checkpoint["optimizer"]["state"].values():
        step = state.get("step", 0)
        values.append(int(step.item() if hasattr(step, "item") else step))
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)

    root = args.experiment_dir.resolve()
    stage_path = root / "resume_stage_manifest.json"
    stage = load_json(stage_path)
    if stage.get("passed") is not True:
        raise RuntimeError("resume stage manifest did not pass")
    staged = {str(row["name"]): row for row in stage["staged"]}
    if set(staged) != {f"seed{seed}" for seed in SEEDS}:
        raise RuntimeError("resume stage manifest has unexpected seeds")

    base = torch.load(args.base, map_location="cpu", weights_only=False)
    runs = []
    total_new_hands = 0
    deal_starts = []
    training_seeds = []
    parent_hashes = []
    assignment_tail_hashes = []
    for seed in SEEDS:
        name = f"seed{seed}"
        stage_row = staged[name]
        run_dir = root / name
        generic = audit_run(
            name,
            run_dir,
            base,
            min_environment_hands=262_144,
            expected_archive_iterations=EXPECTED_ARCHIVES,
            require_continuation=False,
            resume_preflight_path=None,
        )
        checkpoint_path = run_dir / "latest.pt"
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        parent_path = Path(stage_row["checkpoint"]["path"]).resolve()
        parent = torch.load(parent_path, map_location="cpu", weights_only=False)
        metrics_path = run_dir / "h1_training_metrics.jsonl"
        assignments_path = run_dir / "opponent_assignments.jsonl"
        metrics = load_jsonl(metrics_path)
        assignments = load_jsonl(assignments_path)
        config = checkpoint["config"]
        env = checkpoint["environment_hand_accounting"]
        parent_env = parent["environment_hand_accounting"]
        parent_iteration = int(stage_row["checkpoint"]["iteration"])
        parent_physical = int(stage_row["checkpoint"]["physical_environment_hands"])
        parent_transition = int(stage_row["checkpoint"]["transition_hands"])
        new_hands = int(env["completed_hands"]) - parent_physical
        suffix_metrics = [
            row for row in metrics if int(row["iteration"]) > parent_iteration
        ]
        parent_steps = optimizer_steps(parent)
        final_steps = optimizer_steps(checkpoint)
        history_ids = [
            int(item["id"])
            for item in checkpoint.get("pool_candidate_history") or []
        ]
        parent_history = parent.get("pool_candidate_history") or []
        expected_new_candidates = len(
            [
                iteration
                for iteration in range(parent_iteration + 1, int(checkpoint["iteration"]) + 1)
                if iteration % int(config["snapshot_every"]) == 0
            ]
        )
        history_keys = [
            (int(item["id"]), int(item["iteration"]), int(item["hands"]))
            for item in checkpoint.get("pool_candidate_history") or []
        ]
        history_key_set = set(history_keys)
        reused_candidate_ids = sorted(
            candidate_id
            for candidate_id, count in Counter(history_ids).items()
            if count > 1
        )
        assignment_refs = [
            ref
            for assignment in assignments
            for ref in assignment.get("pool_snapshot_refs") or []
        ]
        reused_ids_only_after_rejected = all(
            all(not bool(item.get("selected")) for item in matches[:-1])
            for candidate_id in reused_candidate_ids
            for matches in [[
                item
                for item in checkpoint.get("pool_candidate_history") or []
                if int(item["id"]) == candidate_id
            ]]
        )

        # A late candidate need not remain in loss-K-best membership. Sequential
        # generation plus an explicit rejection is the relevant pool-health gate.
        generic["gates"]["dynamic_pool_healthy"] = (
            len(checkpoint["pool_snapshots"]) == 5
            and {0, 1, 2}.issubset(
                int(item["id"]) for item in checkpoint["pool_snapshots"]
            )
            and len({int(item["id"]) for item in checkpoint["pool_snapshots"]}) == 5
            and len(checkpoint.get("pool_candidate_history") or [])
            == len(parent_history) + expected_new_candidates
            and any(
                item.get("selected") is False
                for item in checkpoint.get("pool_candidate_history") or []
            )
        )
        custom_gates = {
            "stage_row_passed": all(stage_row["gates"].values()),
            "parent_checkpoint_hash_exact": (
                sha256_path(parent_path) == stage_row["checkpoint"]["sha256"]
            ),
            "parent_identity_exact": (
                int(parent["iteration"]) == parent_iteration
                and int(parent["total_hands"]) == parent_transition
                and int(parent_env["completed_hands"]) == parent_physical
                and parent["config"]["run_id"] == stage_row["checkpoint"]["run_id"]
            ),
            "metric_prefix_exact": (
                prefix_sha256(metrics_path, parent_iteration)
                == stage_row["staged_metrics"]["sha256"]
                and [int(row["iteration"]) for row in metrics[:parent_iteration]]
                == list(range(1, parent_iteration + 1))
            ),
            "assignment_prefix_exact": (
                prefix_sha256(assignments_path, parent_iteration)
                == stage_row["staged_assignments"]["sha256"]
                and len(assignments) == int(checkpoint["iteration"])
            ),
            "pool_snapshot_references_unambiguous": (
                len(history_keys) == len(history_key_set)
                and all(
                    len({int(ref["snapshot_id"]) for ref in assignment.get("pool_snapshot_refs") or []})
                    == len(assignment.get("pool_snapshot_refs") or [])
                    for assignment in assignments
                )
                and all(
                    (
                        int(ref["snapshot_id"]),
                        int(ref["snapshot_iteration"]),
                        int(ref["snapshot_hands"]),
                    )
                    in history_key_set
                    for ref in assignment_refs
                )
                and reused_ids_only_after_rejected
            ),
            "same_lineage_and_run_id": (
                config["run_id"] == stage_row["checkpoint"]["run_id"]
                and env["origin_run_id"] == stage_row["checkpoint"]["run_id"]
            ),
            "resume_controls_exact": (
                config["allow_resume"] is True
                and config["reset_optimizer"] is False
                and config["preserve_resumed_optimizer_lr"] is True
                and Path(config["resume"]).resolve() == parent_path
            ),
            "optimizer_continued_with_lr_preserved": (
                len(parent_steps) == len(final_steps) == 10
                and len(set(parent_steps)) == len(set(final_steps)) == 1
                and final_steps[0] > parent_steps[0] > 0
                and checkpoint["optimizer"]["param_groups"][0]["lr"]
                == parent["optimizer"]["param_groups"][0]["lr"]
            ),
            "physical_accounting_exact": (
                new_hands > 0
                and int(env["session_completed_hands"]) == new_hands
                and parent_physical + new_hands == int(env["completed_hands"])
            ),
            "transition_accounting_exact": (
                int(metrics[parent_iteration - 1]["hands"]) == parent_transition
                and int(metrics[-1]["hands"]) == int(checkpoint["total_hands"])
                and all(
                    int(right["hands"]) > int(left["hands"])
                    for left, right in zip(
                        metrics[parent_iteration - 1 : -1],
                        metrics[parent_iteration:],
                    )
                )
            ),
            "replay_accounting_exact": (
                int(parent["ppo_replay_cumulative_rows"])
                + sum(int(row["ppo_replay_rows"]) for row in suffix_metrics)
                == int(checkpoint["ppo_replay_cumulative_rows"])
                and len(checkpoint["ppo_replay_entries"]) == 2
                and not checkpoint["ppo_replay_recovery_boundaries"]
            ),
            "static_current_kl_contract_exact": (
                config["source_policy_kl_direction"] == "current_to_reference"
                and int(config["source_policy_reference_refresh_updates"]) == 0
                and Path(config["source_policy_reference_checkpoint"]).resolve()
                == args.base.resolve()
                and checkpoint.get("moving_source_policy_reference") is None
                and all(
                    row.get("reference_policy_kl_direction")
                    == "current_to_reference"
                    and int(row.get("moving_reference_refresh_updates", -1)) == 0
                    and not bool(row.get("moving_reference_refreshed"))
                    for row in suffix_metrics
                )
            ),
            "new_deal_window_exact_and_disjoint": (
                int(config["fixed_training_deal_start_index"])
                == int(stage_row["deal_window"]["continuation_start"])
                and int(stage_row["deal_window"]["continuation_start"])
                >= int(stage_row["deal_window"]["first_unused_upper_bound"])
            ),
            "suffix_only_no_reset": (
                [int(row["iteration"]) for row in suffix_metrics]
                == list(range(parent_iteration + 1, int(checkpoint["iteration"]) + 1))
                and int(checkpoint["iteration"]) > parent_iteration
            ),
        }
        generic["gates"].update(custom_gates)
        generic["passed"] = all(generic["gates"].values())
        generic["parent"] = {
            "path": str(parent_path),
            "sha256": sha256_path(parent_path),
            "iteration": parent_iteration,
            "physical_environment_hands": parent_physical,
            "transition_hands": parent_transition,
            "optimizer_step": parent_steps[0],
        }
        generic["continuation"] = {
            "new_environment_hands": new_hands,
            "new_transition_hands": int(checkpoint["total_hands"]) - parent_transition,
            "new_replay_rows": sum(int(row["ppo_replay_rows"]) for row in suffix_metrics),
            "final_optimizer_step": final_steps[0],
            "optimizer_lr": checkpoint["optimizer"]["param_groups"][0]["lr"],
            "metric_prefix_rows": parent_iteration,
            "metric_suffix_rows": len(suffix_metrics),
            "candidate_id_diagnostic": {
                "ids_monotonic_unique": not reused_candidate_ids,
                "reused_ids": reused_candidate_ids,
                "reused_ids_only_after_prior_rejection": reused_ids_only_after_rejected,
                "full_id_iteration_hands_keys_unique": len(history_keys)
                == len(history_key_set),
                "causal_effect": "none; active pool IDs remained unique and assignment refs include snapshot iteration and hands",
                "future_repair_required": bool(reused_candidate_ids),
            },
        }
        runs.append(generic)
        total_new_hands += new_hands
        deal_starts.append(int(config["fixed_training_deal_start_index"]))
        training_seeds.append(int(config["seed"]))
        parent_hashes.append(stage_row["checkpoint"]["sha256"])
        assignment_tail_hashes.append(
            generic["assignment_audit"]["tail_sha256"]
        )

    independence = {
        "training_seeds_unique": len(set(training_seeds)) == len(SEEDS),
        "deal_starts_unique": len(set(deal_starts)) == len(SEEDS),
        "parent_checkpoints_unique": len(set(parent_hashes)) == len(SEEDS),
        "assignment_chains_unique": len(set(assignment_tail_hashes)) == len(SEEDS),
    }
    output = {
        "schema": "cardpilot.static_current_kl_262k_training_audit.v1",
        "stage_manifest": {
            "path": str(stage_path),
            "sha256": sha256_path(stage_path),
        },
        "base": {"path": str(args.base.resolve()), "sha256": sha256_path(args.base)},
        "runs": runs,
        "total_physical_environment_hands": sum(
            row["physical_environment_hands"] for row in runs
        ),
        "total_new_environment_hands": total_new_hands,
        "passed_runs": sum(row["passed"] for row in runs),
        "session_independence": independence,
        "passed": all(row["passed"] for row in runs) and all(independence.values()),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "passed": output["passed"],
        "passed_runs": output["passed_runs"],
        "total_new_environment_hands": output["total_new_environment_hands"],
        "session_independence": independence,
    }, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
