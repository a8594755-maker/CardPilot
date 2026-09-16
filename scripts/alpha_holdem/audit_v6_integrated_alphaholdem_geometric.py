"""Independent artifact audit for multi-seed integrated AlphaHoldem pilots."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_v5 import restore_group_assignment_rng_from_evidence


ARCHIVE_RE = re.compile(r"checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt")
ALLOWED_CHANGED = {
    "policy_head.weight", "policy_head.bias",
    "preflop_policy_head.weight", "preflop_policy_head.bias",
    "value_head.0.weight", "value_head.0.bias",
    "value_head.2.weight", "value_head.2.bias",
    "value_head.4.weight", "value_head.4.bias",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("run must be NAME=PATH")
    return name, Path(raw_path)


def audit_run(
    name: str,
    run_dir: Path,
    base: dict,
    *,
    min_environment_hands: int,
    expected_archive_iterations: list[int],
    require_continuation: bool,
    resume_preflight_path: Path | None,
) -> dict:
    run = run_dir.resolve()
    paths = {
        "checkpoint": run / "latest.pt",
        "manifest": run / "run_manifest.json",
        "metrics": run / "h1_training_metrics.jsonl",
        "assignments": run / "opponent_assignments.jsonl",
        "log": run / "latest_train.log",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    checkpoint = torch.load(paths["checkpoint"], map_location="cpu", weights_only=False)
    resume_preflight = None
    if resume_preflight_path is not None:
        resume_preflight = json.loads(
            resume_preflight_path.resolve().read_text(encoding="utf-8")
        )
        if resume_preflight.get("status") != "PASS":
            raise RuntimeError(f"resume preflight did not pass: {resume_preflight_path}")

    # ``legacy_weights_rebound_to_new_contract`` is intentionally a per-process
    # event flag.  A valid continuation therefore records False after the
    # initial bridge run.  Follow the immutable resume lineage so second- and
    # later-generation continuations do not lose evidence of that binding.
    bridge_lineage = []
    lineage_checkpoint = checkpoint
    lineage_path = paths["checkpoint"].resolve()
    seen_lineage_paths: set[Path] = set()
    while lineage_path not in seen_lineage_paths:
        seen_lineage_paths.add(lineage_path)
        bridge_lineage.append(
            {
                "path": str(lineage_path),
                "sha256": sha256_path(lineage_path),
                "iteration": int(lineage_checkpoint["iteration"]),
                "legacy_weights_rebound_to_new_contract": bool(
                    lineage_checkpoint.get("legacy_weights_rebound_to_new_contract", False)
                ),
                "observation_bridge_contract": lineage_checkpoint.get(
                    "observation_bridge_contract"
                ),
            }
        )
        if bridge_lineage[-1]["legacy_weights_rebound_to_new_contract"]:
            break
        resume_value = (lineage_checkpoint.get("config") or {}).get("resume")
        if not resume_value:
            break
        next_path = Path(resume_value)
        if not next_path.is_absolute():
            next_path = (Path.cwd() / next_path).resolve()
        if (
            next_path == paths["checkpoint"].resolve()
            and resume_preflight is not None
        ):
            next_path = Path(
                resume_preflight["source_policy_reference"]["path"]
            ).resolve()
        if not next_path.is_file():
            break
        lineage_path = next_path
        lineage_checkpoint = torch.load(
            lineage_path, map_location="cpu", weights_only=False
        )
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    metrics = load_jsonl(paths["metrics"])
    assignments = load_jsonl(paths["assignments"])
    log_text = paths["log"].read_text(encoding="utf-8")
    ratio_maxima = [float(value) for value in re.findall(r"rmax=([0-9.]+)", log_text)]
    log_iterations = [int(value) for value in re.findall(r"\[\s*(\d+)\]", log_text)]
    config = checkpoint["config"]
    changed = sorted(
        tensor_name
        for tensor_name, value in base["model"].items()
        if tensor_name in checkpoint["model"]
        and torch.is_tensor(value)
        and not torch.equal(value, checkpoint["model"][tensor_name])
    )
    final_pool = checkpoint["pool_snapshots"]
    final_ids = [int(row["id"]) for row in final_pool]
    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config["seed"]),
        worker_count=int(config["workers"]),
        pool_size=len(final_pool),
        pool_snapshot_ids=final_ids,
        group_count=int(config["opponent_groups"]),
        self_play_fraction=float(config["self_play_fraction"]),
        checkpoint_iteration=int(checkpoint["iteration"]),
        checkpoint_total_hands=int(checkpoint["total_hands"]),
    )
    replay_rows = [int(row["ppo_replay_rows"]) for row in metrics]
    replay_buffers = [int(row["ppo_replay_buffer_iterations"]) for row in metrics]
    env = checkpoint["environment_hand_accounting"]
    archive_rows = []
    for path in sorted((run / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        match = ARCHIVE_RE.fullmatch(path.name)
        if match:
            archive_rows.append(
                {
                    "iteration": int(match.group("iteration")),
                    "hands": int(match.group("hands")),
                    "path": str(path),
                    "sha256": sha256_path(path),
                }
            )
    optimizer_steps = []
    for state in checkpoint["optimizer"]["state"].values():
        step = state.get("step", 0)
        optimizer_steps.append(int(step.item() if hasattr(step, "item") else step))
    iterations = [int(row["iteration"]) for row in metrics]
    expected_iterations = list(range(1, int(checkpoint["iteration"]) + 1))
    continuation = None
    if require_continuation:
        resume_path = Path(config["resume"])
        if not resume_path.is_absolute():
            resume_path = (Path.cwd() / resume_path).resolve()
        in_place_resume = (
            resume_path == paths["checkpoint"].resolve()
            and resume_preflight is not None
        )
        in_place_boundary = None
        if in_place_resume:
            immediate_parent_iteration = int(
                resume_preflight["checkpoint"]["iteration"]
            )
            immediate_parent_transition_hands = int(
                resume_preflight["checkpoint"]["hands"]
            )
            immediate_parent_environment_hands = int(env["completed_hands"]) - int(
                env["session_completed_hands"]
            )
            immediate_parent_replay_cumulative_rows = sum(
                int(row["ppo_replay_rows"])
                for row in metrics
                if int(row["iteration"]) <= immediate_parent_iteration
            )
            in_place_metrics = [
                row
                for row in metrics
                if int(row["iteration"]) > immediate_parent_iteration
            ]
            in_place_boundary = {
                "parent_path": str(resume_path),
                "parent_sha256": resume_preflight["checkpoint"]["sha256"],
                "parent_iteration": immediate_parent_iteration,
                "parent_transition_hands": immediate_parent_transition_hands,
                "parent_environment_hands": immediate_parent_environment_hands,
                "parent_replay_cumulative_rows": (
                    immediate_parent_replay_cumulative_rows
                ),
                "new_environment_hands": int(env["session_completed_hands"]),
                "new_transition_hands": int(
                    checkpoint["total_hands"]
                    - immediate_parent_transition_hands
                ),
                "new_replay_rows": sum(
                    int(row["ppo_replay_rows"])
                    for row in in_place_metrics
                ),
            }
            resume_path = Path(
                resume_preflight["source_policy_reference"]["path"]
            ).resolve()
            parent = torch.load(
                resume_path, map_location="cpu", weights_only=False
            )
            parent_env = parent["environment_hand_accounting"]
            parent_iteration = int(parent["iteration"])
            parent_transition_hands = int(parent["total_hands"])
            parent_environment_hands = int(parent_env["completed_hands"])
            parent_replay_cumulative_rows = int(
                parent["ppo_replay_cumulative_rows"]
            )
            parent_path = str(resume_path)
            parent_sha256 = sha256_path(resume_path)
        else:
            parent = torch.load(resume_path, map_location="cpu", weights_only=False)
            parent_env = parent["environment_hand_accounting"]
            parent_iteration = int(parent["iteration"])
            parent_transition_hands = int(parent["total_hands"])
            parent_environment_hands = int(parent_env["completed_hands"])
            parent_replay_cumulative_rows = int(
                parent["ppo_replay_cumulative_rows"]
            )
            parent_path = str(resume_path)
            parent_sha256 = sha256_path(resume_path)
        continuation_metrics = [
            row for row in metrics if int(row["iteration"]) > parent_iteration
        ]
        continuation = {
            "parent_path": parent_path,
            "parent_sha256": parent_sha256,
            "in_place_resume_preflight": in_place_resume,
            "parent_iteration": parent_iteration,
            "parent_transition_hands": parent_transition_hands,
            "parent_environment_hands": parent_environment_hands,
            "parent_replay_cumulative_rows": parent_replay_cumulative_rows,
            "new_environment_hands": int(env["completed_hands"])
            - parent_environment_hands,
            "new_transition_hands": int(
                checkpoint["total_hands"] - parent_transition_hands
            ),
            "new_replay_rows": sum(int(row["ppo_replay_rows"]) for row in continuation_metrics),
            "in_place_boundary": in_place_boundary,
        }
    finite_fields = (
        "approx_kl", "reference_policy_kl", "preupdate_critic_mse",
        "entropy", "reward_per_hand",
    )
    gates = {
        "manifest_finished": manifest["status"] == "finished",
        "contiguous_updates": iterations == expected_iterations,
        "checkpoint_manifest_metric_identity": (
            checkpoint["iteration"] == manifest["iteration"] == metrics[-1]["iteration"]
            and checkpoint["total_hands"] == manifest["total_hands"] == metrics[-1]["hands"]
        ),
        "physical_environment_target_reached": (
            env["completed_hands"] >= min_environment_hands
            and env["prefix_complete"]
            and env["unknown_prefix_training_marker_hands"] == 0
        ),
        "all_12_workers_completed_hands": (
            len(env["session_worker_counts"]) == 12
            and all(row["completed_hands"] > 0 for row in env["session_worker_counts"])
        ),
        "fresh_replay_boundary_then_nonzero": (
            replay_rows[0] == 0 and all(value > 0 for value in replay_rows[1:])
        ),
        "replay_cumulative_exact": (
            sum(replay_rows) == checkpoint["ppo_replay_cumulative_rows"]
            and len(checkpoint["ppo_replay_entries"]) == 2
            and not checkpoint["ppo_replay_recovery_boundaries"]
            and set(replay_buffers) == {2}
        ),
        "dynamic_pool_healthy": (
            len(final_pool) == 5
            and {0, 1, 2}.issubset(final_ids)
            and max(final_ids) >= 8
        ),
        "assignment_rng_replay_exact": (
            assignment_audit["tail_iteration"]
            in {checkpoint["iteration"], checkpoint["iteration"] + 1}
            and (
                (assignment_audit["pending_assignments"] is None)
                == (assignment_audit["tail_iteration"] == checkpoint["iteration"])
            )
        ),
        "paper_recipe_exact": (
            config["mini_batch_size"] == 16_384
            and config["lr"] == 0.0003
            and config["ppo_replay_ratio"] == 0.5
            and config["ppo_replay_buffer_iterations"] == 2
            and config["k_best"] == 5
            and config["pool_strategy"] == "loss-kbest"
            and config["snapshot_every"] == 2
            and config["source_policy_kl_coef"] == 1.0
        ),
        "corrected_legacy_contract_bound": (
            checkpoint["env_version"] == "v6legacyv4obs"
            and any(
                row["legacy_weights_rebound_to_new_contract"]
                for row in bridge_lineage
            )
            and checkpoint["observation_bridge_contract"]
            == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
            and all(
                row["observation_bridge_contract"]
                == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
                for row in bridge_lineage
            )
        ),
        "only_policy_and_value_heads_changed": set(changed) == ALLOWED_CHANGED,
        "optimizer_state_nonempty_and_synchronized": (
            len(optimizer_steps) == 10
            and len(set(optimizer_steps)) == 1
            and optimizer_steps[0] > 0
        ),
        "finite_health_metrics": all(
            math.isfinite(float(row[key])) for row in metrics for key in finite_fields
        ),
        "trust_region_healthy": (
            max(abs(float(row["approx_kl"])) for row in metrics) < 0.01
            and max(float(row["reference_policy_kl"]) for row in metrics) < 0.01
            and not any(row["kl_early_stop_triggered"] for row in metrics)
        ),
        "importance_ratios_below_delta1": (
            len(ratio_maxima) == len(log_iterations)
            and bool(ratio_maxima)
            and max(ratio_maxima) < 3.0
        ),
        "geometric_archives_present": (
            [row["iteration"] for row in archive_rows] == expected_archive_iterations
        ),
    }
    if require_continuation:
        assert continuation is not None
        gates.update(
            {
                "continuation_flags_exact": (
                    config["allow_resume"] is True
                    and config["reset_optimizer"] is False
                    and config["preserve_resumed_optimizer_lr"] is True
                ),
                "continuation_log_suffix_exact": (
                    log_iterations[
                        -(
                            int(checkpoint["iteration"])
                            - continuation["parent_iteration"]
                        ):
                    ]
                    == list(
                        range(
                            continuation["parent_iteration"] + 1,
                            int(checkpoint["iteration"]) + 1,
                        )
                    )
                    and log_iterations
                    == list(
                        range(log_iterations[0], int(checkpoint["iteration"]) + 1)
                    )
                ),
                "continuation_environment_accounting_exact": (
                    continuation["parent_environment_hands"]
                    + continuation["new_environment_hands"]
                    == int(env["completed_hands"])
                ),
                "continuation_transition_accounting_exact": (
                    continuation["parent_transition_hands"]
                    + continuation["new_transition_hands"]
                    == int(checkpoint["total_hands"])
                ),
                "continuation_replay_accounting_exact": (
                    continuation["parent_replay_cumulative_rows"]
                    + continuation["new_replay_rows"]
                    == int(checkpoint["ppo_replay_cumulative_rows"])
                ),
            }
        )
        if continuation["in_place_resume_preflight"]:
            assert resume_preflight is not None
            assert continuation["in_place_boundary"] is not None
            boundary = continuation["in_place_boundary"]
            preflight_checkpoint = resume_preflight["checkpoint"]
            preflight_deals = resume_preflight["fixed_deal_recovery"]
            gates["in_place_resume_preflight_exact"] = (
                int(preflight_checkpoint["iteration"])
                == boundary["parent_iteration"]
                and int(preflight_checkpoint["hands"])
                == boundary["parent_transition_hands"]
                and int(resume_preflight["evidence"]["metric_rows"])
                == boundary["parent_iteration"]
                and int(resume_preflight["assignment_recovery"]["tail_iteration"])
                == boundary["parent_iteration"] + 1
                and resume_preflight["replay_state_serialized"] is True
                and int(config["fixed_training_deal_start_index"])
                == int(preflight_deals["deal_start_index"])
                and int(preflight_deals["deal_start_index"])
                >= int(preflight_deals["conservative_first_unused_deal_index"])
                and boundary["parent_environment_hands"]
                + boundary["new_environment_hands"]
                == int(env["completed_hands"])
                and boundary["parent_transition_hands"]
                + boundary["new_transition_hands"]
                == int(checkpoint["total_hands"])
                and boundary["parent_replay_cumulative_rows"]
                + boundary["new_replay_rows"]
                == int(checkpoint["ppo_replay_cumulative_rows"])
            )
    return {
        "name": name,
        "run_dir": str(run),
        "hashes": {key: sha256_path(path) for key, path in paths.items()},
        "transition_hands": int(checkpoint["total_hands"]),
        "physical_environment_hands": int(env["completed_hands"]),
        "iterations": int(checkpoint["iteration"]),
        "replay_cumulative_rows": int(checkpoint["ppo_replay_cumulative_rows"]),
        "final_pool_ids": final_ids,
        "changed_tensors": changed,
        "max_approx_kl": max(abs(float(row["approx_kl"])) for row in metrics),
        "max_reference_policy_kl": max(float(row["reference_policy_kl"]) for row in metrics),
        "max_importance_ratio": max(ratio_maxima),
        "assignment_audit": assignment_audit,
        "bridge_lineage": bridge_lineage,
        "continuation": continuation,
        "archives": archive_rows,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", type=parse_run, required=True)
    parser.add_argument(
        "--resume-preflight", action="append", type=parse_run, default=[]
    )
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--min-environment-hands", type=int, default=65_536)
    parser.add_argument("--expected-archive-iterations", default="4,8,12")
    parser.add_argument("--expected-run-count", type=int, default=3)
    parser.add_argument("--require-continuation", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    names = [name for name, _ in args.run]
    if len(names) != len(set(names)):
        parser.error("run names must be unique")
    resume_preflights = dict(args.resume_preflight)
    if not set(resume_preflights).issubset(names):
        parser.error("resume preflight names must match supplied run names")
    base = torch.load(args.base, map_location="cpu", weights_only=False)
    expected_archive_iterations = [
        int(value) for value in args.expected_archive_iterations.split(",") if value
    ]
    runs = [
        audit_run(
            name,
            path,
            base,
            min_environment_hands=args.min_environment_hands,
            expected_archive_iterations=expected_archive_iterations,
            require_continuation=args.require_continuation,
            resume_preflight_path=resume_preflights.get(name),
        )
        for name, path in args.run
    ]
    output = {
        "schema": "cardpilot.integrated_alphaholdem_geometric_audit.v1",
        "base": {"path": str(args.base.resolve()), "sha256": sha256_path(args.base)},
        "runs": runs,
        "total_physical_environment_hands": sum(
            row["physical_environment_hands"] for row in runs
        ),
        "total_transition_hands": sum(row["transition_hands"] for row in runs),
        "passed_runs": sum(row["passed"] for row in runs),
        "expected_run_count": args.expected_run_count,
        "passed": (
            len(runs) == args.expected_run_count
            and all(row["passed"] for row in runs)
        ),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
