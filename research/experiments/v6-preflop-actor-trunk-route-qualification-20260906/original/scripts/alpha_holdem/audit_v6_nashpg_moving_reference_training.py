"""Audit matched static/current-KL versus every-update moving-reference runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_v6_integrated_alphaholdem_geometric import audit_run, sha256_path


ARMS = ("static", "moving")
SEEDS = (1, 2, 3)
ALLOWED_MATCHED_CONFIG_DIFFERENCES = {
    "opponent_assignment_provenance_file",
    "out",
    "run_dir",
    "run_id",
    "source_policy_reference_refresh_updates",
}


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def tensors_equal(left: dict, right: dict) -> bool:
    return set(left) == set(right) and all(
        torch.equal(left[name].detach().cpu(), right[name].detach().cpu())
        for name in left
    )


def moving_state_gates(checkpoint: dict, metrics: list[dict]) -> dict:
    state = checkpoint.get("moving_source_policy_reference")
    if not isinstance(state, dict):
        return {"moving_state_present": False}
    iteration = int(checkpoint["iteration"])
    rng = state.get("rng_state") or {}
    archive_iterations = []
    archive_states_exact = True
    run_dir = Path(checkpoint["config"]["run_dir"])
    for path in sorted((run_dir / "checkpoints").glob("checkpoint_iter*_hands*.pt")):
        archived = torch.load(path, map_location="cpu", weights_only=False)
        archive_state = archived.get("moving_source_policy_reference") or {}
        archived_iteration = int(archived["iteration"])
        archive_iterations.append(archived_iteration)
        archive_states_exact = archive_states_exact and (
            int(archive_state.get("completed_updates", -1)) == archived_iteration
            and int(archive_state.get("last_refresh_update", -1)) == archived_iteration
            and int(archive_state.get("reference_round", -1)) == archived_iteration
            and int(archive_state.get("trainer_iteration", -1)) == archived_iteration
            and int(archive_state.get("activation_iteration", -1)) == 0
            and tensors_equal(
                archive_state.get("reference_model") or {}, archived["model"]
            )
        )
    return {
        "moving_state_present": True,
        "moving_schema_exact": (
            state.get("schema_version")
            == "alpha_holdem.moving_source_policy_reference.v1"
        ),
        "moving_direction_interval_exact": (
            state.get("direction") == "current_to_reference"
            and int(state.get("refresh_interval_updates", -1)) == 1
        ),
        "moving_final_cadence_exact": (
            int(state.get("completed_updates", -1)) == iteration
            and int(state.get("last_refresh_update", -1)) == iteration
            and int(state.get("reference_round", -1)) == iteration
            and int(state.get("activation_iteration", -1)) == 0
            and int(state.get("trainer_iteration", -1)) == iteration
        ),
        "moving_final_reference_equals_postupdate_policy": tensors_equal(
            state.get("reference_model") or {}, checkpoint["model"]
        ),
        "moving_rng_complete": (
            set(rng) == {"python", "numpy", "torch_cpu", "torch_cuda"}
            and torch.is_tensor(rng.get("torch_cpu"))
        ),
        "moving_metrics_cadence_exact": all(
            row.get("reference_policy_kl_direction") == "current_to_reference"
            and int(row.get("moving_reference_refresh_updates", -1)) == 1
            and bool(row.get("moving_reference_refreshed"))
            and int(row.get("moving_reference_completed_updates", -1))
            == int(row["iteration"])
            and int(row.get("moving_reference_last_refresh_update", -1))
            == int(row["iteration"])
            and int(row.get("moving_reference_round", -1))
            == int(row["iteration"])
            for row in metrics
        ),
        "moving_archive_states_exact": (
            archive_iterations == [4, 8, 12] and archive_states_exact
        ),
    }


def static_state_gates(checkpoint: dict, metrics: list[dict]) -> dict:
    return {
        "static_has_no_moving_state": (
            checkpoint.get("moving_source_policy_reference") is None
        ),
        "static_direction_interval_exact": (
            checkpoint["config"].get("source_policy_kl_direction")
            == "current_to_reference"
            and int(
                checkpoint["config"].get(
                    "source_policy_reference_refresh_updates", -1
                )
            )
            == 0
        ),
        "static_metrics_no_refresh": all(
            row.get("reference_policy_kl_direction") == "current_to_reference"
            and int(row.get("moving_reference_refresh_updates", -1)) == 0
            and not bool(row.get("moving_reference_refreshed"))
            and int(row.get("moving_reference_completed_updates", -1)) == 0
            and int(row.get("moving_reference_round", -1)) == 0
            for row in metrics
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    base = torch.load(args.base, map_location="cpu", weights_only=False)
    output_runs = []
    checkpoints = {}
    for seed in SEEDS:
        for arm in ARMS:
            name = f"{arm}_seed{seed}"
            run_dir = args.experiment_dir / name
            row = audit_run(
                name,
                run_dir,
                base,
                min_environment_hands=65_536,
                expected_archive_iterations=[4, 8, 12],
                require_continuation=False,
                resume_preflight_path=None,
            )
            checkpoint = torch.load(
                run_dir / "latest.pt", map_location="cpu", weights_only=False
            )
            checkpoints[name] = checkpoint
            metrics = load_jsonl(run_dir / "h1_training_metrics.jsonl")
            history_ids = [
                int(item["id"])
                for item in checkpoint.get("pool_candidate_history") or []
            ]
            expected_last_id = 2 + int(checkpoint["iteration"]) // 2
            # The generic audit incorrectly requires a late candidate to remain
            # in active K-best membership. Candidate generation and explicit
            # rejection are the actual dynamic-pool health contract.
            row["gates"]["dynamic_pool_healthy"] = (
                len(checkpoint["pool_snapshots"]) == 5
                and {0, 1, 2}.issubset(
                    int(item["id"]) for item in checkpoint["pool_snapshots"]
                )
                and history_ids == list(range(expected_last_id + 1))
                and any(
                    item.get("selected") is False
                    for item in checkpoint.get("pool_candidate_history") or []
                )
            )
            row["gates"].update(
                moving_state_gates(checkpoint, metrics)
                if arm == "moving"
                else static_state_gates(checkpoint, metrics)
            )
            row["candidate_history_ids"] = history_ids
            row["passed"] = all(row["gates"].values())
            output_runs.append(row)

    matched_pairs = []
    for seed in SEEDS:
        static = checkpoints[f"static_seed{seed}"]["config"]
        moving = checkpoints[f"moving_seed{seed}"]["config"]
        differences = {
            key: [static.get(key), moving.get(key)]
            for key in sorted(set(static) | set(moving))
            if static.get(key) != moving.get(key)
        }
        pair = {
            "seed": seed,
            "config_differences": differences,
            "only_refresh_and_artifact_paths_differ": (
                set(differences) == ALLOWED_MATCHED_CONFIG_DIFFERENCES
                and differences["source_policy_reference_refresh_updates"]
                == [0, 1]
            ),
        }
        matched_pairs.append(pair)

    output = {
        "schema": "cardpilot.nashpg_moving_reference_training_audit.v1",
        "base": {
            "path": str(args.base.resolve()),
            "sha256": sha256_path(args.base),
        },
        "runs": output_runs,
        "matched_pairs": matched_pairs,
        "total_physical_environment_hands": sum(
            row["physical_environment_hands"] for row in output_runs
        ),
        "passed_runs": sum(row["passed"] for row in output_runs),
        "passed": (
            all(row["passed"] for row in output_runs)
            and all(
                row["only_refresh_and_artifact_paths_differ"]
                for row in matched_pairs
            )
        ),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "passed": output["passed"],
        "passed_runs": output["passed_runs"],
        "total_physical_environment_hands": output[
            "total_physical_environment_hands"
        ],
        "matched_pairs": matched_pairs,
    }, sort_keys=True))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
