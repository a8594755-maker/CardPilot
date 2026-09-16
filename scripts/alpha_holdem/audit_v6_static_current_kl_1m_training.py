#!/usr/bin/env python3
"""Audit an exact-state static current-KL geometric continuation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_v6_integrated_alphaholdem_geometric import audit_run, sha256_path
from audit_v6_static_current_kl_262k_training import (
    load_json,
    load_jsonl,
    optimizer_steps,
    prefix_sha256,
)


SEEDS = (1, 2, 3)
EXPECTED_ARCHIVES = [64, 128, 192]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-environment-hands", type=int, default=1_048_576)
    parser.add_argument(
        "--expected-archive-iteration",
        type=int,
        action="append",
        dest="expected_archive_iterations",
    )
    parser.add_argument(
        "--schema",
        default="cardpilot.static_current_kl_1m_training_audit.v2",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    root = args.experiment_dir.resolve()
    expected_archive_iterations = (
        args.expected_archive_iterations
        if args.expected_archive_iterations is not None
        else EXPECTED_ARCHIVES
    )
    stage_path = root / "resume_stage_manifest.json"
    stage = load_json(stage_path)
    if stage.get("passed") is not True:
        raise RuntimeError("resume stage manifest did not pass")
    staged = {str(row["name"]): row for row in stage["staged"]}
    base = torch.load(args.base, map_location="cpu", weights_only=False)

    runs = []
    total_new_hands = 0
    deal_starts = []
    training_seeds = []
    assignment_tail_hashes = []
    recovery_preflight_hashes = []
    for seed in SEEDS:
        name = f"seed{seed}"
        stage_row = staged[name]
        run_dir = root / name
        recovery_preflight_paths = sorted(
            root.glob(f"{name}_resume_preflight_iter*.json"),
            key=lambda path: int(path.stem.rsplit("iter", 1)[1]),
        )
        recovery_preflight_path = (
            recovery_preflight_paths[0] if recovery_preflight_paths else None
        )
        recovery_preflights = [load_json(path) for path in recovery_preflight_paths]
        generic = audit_run(
            name,
            run_dir,
            base,
            min_environment_hands=args.min_environment_hands,
            expected_archive_iterations=expected_archive_iterations,
            require_continuation=False,
            resume_preflight_path=recovery_preflight_path,
        )
        checkpoint = torch.load(
            run_dir / "latest.pt", map_location="cpu", weights_only=False
        )
        parent_path = Path(stage_row["checkpoint"]["path"]).resolve()
        parent = torch.load(parent_path, map_location="cpu", weights_only=False)
        parent_audit_path = parent_path.parent.parent / "training_audit.json"
        inherited_parent_lineage = None
        if parent_audit_path.is_file():
            parent_audit = load_json(parent_audit_path)
            parent_audit_run = next(
                (
                    row
                    for row in parent_audit.get("runs", [])
                    if row.get("name") == name
                ),
                None,
            )
            inherited_parent_lineage = {
                "path": str(parent_audit_path),
                "sha256": sha256_path(parent_audit_path),
                "parent_audit_passed": parent_audit.get("passed") is True,
                "parent_run_found": parent_audit_run is not None,
                "parent_checkpoint_hash_exact": (
                    parent_audit_run is not None
                    and parent_audit_run.get("hashes", {}).get("checkpoint")
                    == stage_row["checkpoint"]["sha256"]
                ),
                "corrected_legacy_contract_bound": (
                    parent_audit_run is not None
                    and parent_audit_run.get("gates", {}).get(
                        "corrected_legacy_contract_bound"
                    )
                    is True
                    and any(
                        row.get("legacy_weights_rebound_to_new_contract") is True
                        for row in parent_audit_run.get("bridge_lineage", [])
                    )
                    and all(
                        row.get("observation_bridge_contract")
                        == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
                        for row in parent_audit_run.get("bridge_lineage", [])
                    )
                ),
            }
            generic["gates"]["corrected_legacy_contract_bound"] = (
                generic["gates"]["corrected_legacy_contract_bound"]
                or all(
                    inherited_parent_lineage[key]
                    for key in (
                        "parent_audit_passed",
                        "parent_run_found",
                        "parent_checkpoint_hash_exact",
                        "corrected_legacy_contract_bound",
                    )
                )
            )
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
        suffix_metrics = metrics[parent_iteration:]
        parent_history = parent.get("pool_candidate_history") or []
        final_history = checkpoint.get("pool_candidate_history") or []
        parent_max_id = max(int(item["id"]) for item in parent_history)
        # The serialized history is intentionally capped.  At longer scales its
        # prefix can be evicted, so continuation membership must be recovered
        # from the monotonic candidate identity rather than a list offset.
        suffix_history = [
            item for item in final_history if int(item["id"]) > parent_max_id
        ]
        suffix_ids = [int(item["id"]) for item in suffix_history]
        expected_new_candidates = len([
            iteration
            for iteration in range(parent_iteration + 1, int(checkpoint["iteration"]) + 1)
            if iteration % int(config["snapshot_every"]) == 0
        ])
        parent_steps = optimizer_steps(parent)
        final_steps = optimizer_steps(checkpoint)
        recovery_boundaries = []
        previous_boundary_iteration = parent_iteration
        previous_boundary_step = parent_steps[0]
        previous_deal_start = int(stage_row["deal_window"]["continuation_start"])
        for recovery_index, (recovery_preflight_path, recovery_preflight) in enumerate(
            zip(recovery_preflight_paths, recovery_preflights)
        ):
            same_parent_uncommitted_replay = (
                recovery_preflight.get("recovery_semantics")
                == "repeat_same_uncommitted_iter222_worker_deals_and_pending_assignment"
            )
            source_incident = recovery_preflight.get("source_incident_preflight")
            source_incident_path = (
                Path(source_incident["path"]).resolve()
                if source_incident is not None
                else None
            )
            source_incident_payload = (
                load_json(source_incident_path)
                if source_incident_path is not None
                else None
            )
            boundary_iteration = int(recovery_preflight["checkpoint"]["iteration"])
            boundary_metric = metrics[boundary_iteration - 1]
            boundary_env = boundary_metric["environment_hand_accounting"]
            next_boundary_iteration = (
                int(recovery_preflights[recovery_index + 1]["checkpoint"]["iteration"])
                if recovery_index + 1 < len(recovery_preflights)
                else int(checkpoint["iteration"])
            )
            recovery_segment_metrics = metrics[
                boundary_iteration:next_boundary_iteration
            ]
            recovered_prefixes = {
                int(row["environment_hand_accounting"]["completed_hands"])
                - int(row["environment_hand_accounting"]["session_completed_hands"])
                for row in recovery_segment_metrics
            }
            recovered_physical_prefix = (
                next(iter(recovered_prefixes)) if len(recovered_prefixes) == 1 else None
            )
            boundary_assignment_rows = int(
                recovery_preflight["evidence"]["assignment_rows"]
            )
            boundary_steps = {
                int(recovery_preflight["continuity"]["optimizer_step_min"]),
                int(recovery_preflight["continuity"]["optimizer_step_max"]),
            }
            recovery_boundary = {
                "path": str(recovery_preflight_path.resolve()),
                "sha256": sha256_path(recovery_preflight_path),
                "checkpoint_sha256": recovery_preflight["checkpoint"]["sha256"],
                "iteration": boundary_iteration,
                "transition_hands": int(recovery_preflight["checkpoint"]["hands"]),
                "physical_environment_hands": int(boundary_env["completed_hands"]),
                "recovered_physical_prefix": recovered_physical_prefix,
                "uncommitted_worker_tail_hands": (
                    recovered_physical_prefix - int(boundary_env["completed_hands"])
                    if recovered_physical_prefix is not None
                    else None
                ),
                "optimizer_step": min(boundary_steps),
                "source_deal_start_index": int(
                    recovery_preflight["fixed_deal_recovery"][
                        "source_deal_start_index"
                    ]
                ),
                "recovery_deal_start_index": int(
                    recovery_preflight["fixed_deal_recovery"]["deal_start_index"]
                ),
                "environment_hands_after_boundary_to_final": (
                    int(env["completed_hands"])
                    - int(boundary_env["completed_hands"])
                ),
                "gates": {
                    "source_incident_preflight_exact": (
                        source_incident is None
                        or (
                            source_incident_path is not None
                            and source_incident_payload is not None
                            and sha256_path(source_incident_path)
                            == source_incident["sha256"]
                            and source_incident_payload.get("passed") is True
                            and all(source_incident_payload.get("gates", {}).values())
                        )
                    ),
                    "preflight_passed_and_sha_bound": (
                        recovery_preflight.get("status") == "PASS"
                        and recovery_preflight.get("replay_state_serialized") is True
                        and recovery_preflight.get("replay_limitation") is None
                        and len(boundary_steps) == 1
                    ),
                    "checkpoint_metric_boundary_exact": (
                        (
                            boundary_iteration > previous_boundary_iteration
                            or (
                                same_parent_uncommitted_replay
                                and boundary_iteration == previous_boundary_iteration
                            )
                        )
                        and int(boundary_metric["iteration"]) == boundary_iteration
                        and int(boundary_metric["hands"])
                        == int(recovery_preflight["checkpoint"]["hands"])
                        and int(recovery_preflight["evidence"]["metric_rows"])
                        == boundary_iteration
                        and prefix_sha256(metrics_path, boundary_iteration)
                        == recovery_preflight["evidence"]["metrics_sha256"]
                    ),
                    "recovered_physical_prefix_exact": (
                        bool(recovery_segment_metrics)
                        and recovered_physical_prefix is not None
                        and recovered_physical_prefix
                        >= int(boundary_env["completed_hands"])
                    ),
                    "assignment_boundary_exact": (
                        boundary_assignment_rows == boundary_iteration + 1
                        and prefix_sha256(assignments_path, boundary_assignment_rows)
                        == recovery_preflight["evidence"]["assignments_sha256"]
                        and int(
                            recovery_preflight["assignment_recovery"][
                                "tail_iteration"
                            ]
                        )
                        == boundary_iteration + 1
                    ),
                    "resume_anchor_identity_exact": (
                        Path(
                            recovery_preflight["source_policy_reference"]["path"]
                        ).resolve()
                        == (
                            parent_path
                            if recovery_index == 0
                            else (run_dir / "latest.pt").resolve()
                        )
                        and recovery_preflight["source_policy_reference"]["sha256"]
                        == (
                            stage_row["checkpoint"]["sha256"]
                            if recovery_index == 0
                            else recovery_preflight["checkpoint"]["sha256"]
                        )
                        and recovery_preflight["source_policy_reference"][
                            "matches_original_resume_anchor"
                        ]
                        is True
                    ),
                    "optimizer_continued_across_boundary": (
                        (
                            min(boundary_steps) > previous_boundary_step
                            or (
                                same_parent_uncommitted_replay
                                and min(boundary_steps) == previous_boundary_step
                            )
                        )
                        and final_steps[0] > min(boundary_steps)
                    ),
                    "deal_recovery_exact_and_disjoint": (
                        int(
                            recovery_preflight["fixed_deal_recovery"][
                                "source_deal_start_index"
                            ]
                        )
                        == previous_deal_start
                        and int(
                            recovery_preflight["fixed_deal_recovery"][
                                "deal_start_index"
                            ]
                        )
                        >= int(
                            recovery_preflight["fixed_deal_recovery"][
                                "conservative_first_unused_deal_index"
                            ]
                        )
                        and recovery_preflight["fixed_deal_recovery"][
                            "provably_above_every_prior_per_worker_cursor"
                        ]
                        is True
                    ),
                },
            }
            recovery_boundaries.append(recovery_boundary)
            previous_boundary_iteration = boundary_iteration
            previous_boundary_step = min(boundary_steps)
            previous_deal_start = recovery_boundary["recovery_deal_start_index"]
        if recovery_boundaries:
            recovery_boundaries[-1]["gates"]["final_segment_physical_accounting"] = (
                recovery_boundaries[-1]["recovered_physical_prefix"]
                + int(env["session_completed_hands"])
                == int(env["completed_hands"])
            )
            recovery_boundaries[-1]["gates"]["final_deal_start_matches_config"] = (
                recovery_boundaries[-1]["recovery_deal_start_index"]
                == int(config["fixed_training_deal_start_index"])
            )

        generic["gates"]["dynamic_pool_healthy"] = (
            len(checkpoint["pool_snapshots"]) == 5
            and len({int(item["id"]) for item in checkpoint["pool_snapshots"]}) == 5
            and {0, 1, 2}.issubset(
                int(item["id"]) for item in checkpoint["pool_snapshots"]
            )
            and len(suffix_history) == expected_new_candidates
            and suffix_ids
            == list(range(parent_max_id + 1, parent_max_id + 1 + len(suffix_ids)))
        )
        gates = {
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
            ),
            "assignment_prefix_exact": (
                prefix_sha256(assignments_path, parent_iteration)
                == stage_row["staged_assignments"]["sha256"]
                and len(assignments) == int(checkpoint["iteration"])
            ),
            "monotonic_candidate_identity_repair_active": (
                bool(suffix_ids)
                and min(suffix_ids) > parent_max_id
                and len(suffix_ids) == len(set(suffix_ids))
            ),
            "same_lineage_and_run_id": (
                config["run_id"] == stage_row["checkpoint"]["run_id"]
                and env["origin_run_id"] == stage_row["checkpoint"]["run_id"]
            ),
            "resume_controls_exact": (
                config["allow_resume"] is True
                and config["reset_optimizer"] is False
                and config["preserve_resumed_optimizer_lr"] is True
                and Path(config["resume"]).resolve()
                == (
                    (run_dir / "latest.pt").resolve()
                    if recovery_boundaries
                    else parent_path
                )
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
                and (
                    int(env["session_completed_hands"])
                    == (
                        int(env["completed_hands"])
                        - recovery_boundaries[-1]["recovered_physical_prefix"]
                        if recovery_boundaries
                        else new_hands
                    )
                )
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
                (
                    int(config["fixed_training_deal_start_index"])
                    == (
                        recovery_boundaries[-1]["recovery_deal_start_index"]
                        if recovery_boundaries
                        else int(stage_row["deal_window"]["continuation_start"])
                    )
                )
                and int(stage_row["deal_window"]["continuation_start"])
                >= int(stage_row["deal_window"]["first_unused_upper_bound"])
            ),
            "suffix_only_no_reset": (
                [int(row["iteration"]) for row in suffix_metrics]
                == list(range(parent_iteration + 1, int(checkpoint["iteration"]) + 1))
            ),
        }
        if recovery_boundaries:
            gates["recovery_boundaries_all_exact"] = all(
                all(boundary["gates"].values())
                for boundary in recovery_boundaries
            )
        generic["gates"].update(gates)
        generic["passed"] = all(generic["gates"].values())
        generic["parent"] = {
            "path": str(parent_path),
            "sha256": sha256_path(parent_path),
            "iteration": parent_iteration,
            "physical_environment_hands": parent_physical,
            "transition_hands": parent_transition,
            "optimizer_step": parent_steps[0],
            "max_candidate_id": parent_max_id,
        }
        generic["continuation"] = {
            "new_environment_hands": new_hands,
            "new_transition_hands": int(checkpoint["total_hands"]) - parent_transition,
            "new_replay_rows": sum(int(row["ppo_replay_rows"]) for row in suffix_metrics),
            "final_optimizer_step": final_steps[0],
            "optimizer_lr": checkpoint["optimizer"]["param_groups"][0]["lr"],
            "first_new_candidate_id": suffix_ids[0],
            "last_new_candidate_id": suffix_ids[-1],
            "recovery_boundaries": recovery_boundaries,
        }
        generic["inherited_parent_lineage"] = inherited_parent_lineage
        runs.append(generic)
        total_new_hands += new_hands
        deal_starts.append(int(config["fixed_training_deal_start_index"]))
        training_seeds.append(int(config["seed"]))
        assignment_tail_hashes.append(generic["assignment_audit"]["tail_sha256"])
        recovery_preflight_hashes.extend(
            boundary["sha256"] for boundary in recovery_boundaries
        )

    independence = {
        "training_seeds_unique": len(set(training_seeds)) == len(SEEDS),
        "deal_starts_unique": len(set(deal_starts)) == len(SEEDS),
        "assignment_chains_unique": len(set(assignment_tail_hashes)) == len(SEEDS),
        "recovery_preflights_unique": (
            len(set(recovery_preflight_hashes)) == len(recovery_preflight_hashes)
        ),
    }
    output = {
        "schema": args.schema,
        "stage_manifest": {"path": str(stage_path), "sha256": sha256_path(stage_path)},
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
        "total_new_environment_hands": total_new_hands,
        "session_independence": independence,
    }, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
