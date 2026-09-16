"""Stage and audit immutable evidence needed for exact multi-seed continuation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_v5 import restore_group_assignment_rng_from_evidence


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


def parse_named_path(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("value must be NAME=PATH")
    name, raw = value.split("=", 1)
    if not name or not raw:
        raise argparse.ArgumentTypeError("value must be NAME=PATH")
    return name, Path(raw)


def parse_named_int(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("value must be NAME=INTEGER")
    name, raw = value.split("=", 1)
    try:
        number = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be NAME=INTEGER") from exc
    return name, number


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=parse_named_path, required=True)
    parser.add_argument("--deal-start", action="append", type=parse_named_int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest-name", default="resume_stage_manifest.json")
    args = parser.parse_args()
    sources = dict(args.source)
    deal_starts = dict(args.deal_start)
    if len(sources) != len(args.source) or len(deal_starts) != len(args.deal_start):
        parser.error("names must be unique")
    if set(sources) != set(deal_starts):
        parser.error("source and deal-start names must match")
    if Path(args.manifest_name).name != args.manifest_name:
        parser.error("manifest-name must be a file name")
    manifest_path = args.out_dir / args.manifest_name
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    staged = []
    for name in sorted(sources):
        source = sources[name].resolve()
        destination = (args.out_dir / name).resolve()
        if destination.exists():
            raise FileExistsError(destination)
        checkpoint_path = source / "latest.pt"
        metrics_path = source / "h1_training_metrics.jsonl"
        assignments_path = source / "opponent_assignments.jsonl"
        for path in (checkpoint_path, metrics_path, assignments_path):
            if not path.is_file():
                raise FileNotFoundError(path)
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        metrics = load_jsonl(metrics_path)
        assignments = load_jsonl(assignments_path)
        config = checkpoint["config"]
        pool_ids = [int(row["id"]) for row in checkpoint["pool_snapshots"]]
        restored = restore_group_assignment_rng_from_evidence(
            assignments,
            metrics,
            rng=random.Random(0),
            seed=int(config["seed"]),
            worker_count=int(config["workers"]),
            pool_size=len(pool_ids),
            pool_snapshot_ids=pool_ids,
            group_count=int(config["opponent_groups"]),
            self_play_fraction=float(config["self_play_fraction"]),
            checkpoint_iteration=int(checkpoint["iteration"]),
            checkpoint_total_hands=int(checkpoint["total_hands"]),
        )
        accounting = checkpoint["environment_hand_accounting"]
        worker_counts = accounting["session_worker_counts"]
        prior_start = int(config["fixed_training_deal_start_index"])
        first_unused_upper_bound = prior_start + max(
            int(row["completed_hands"]) for row in worker_counts
        )
        next_start = int(deal_starts[name])
        optimizer_steps = []
        for state in checkpoint["optimizer"]["state"].values():
            step = state.get("step", 0)
            optimizer_steps.append(int(step.item() if hasattr(step, "item") else step))
        gates = {
            "checkpoint_metric_identity": (
                int(checkpoint["iteration"]) == int(metrics[-1]["iteration"])
                and int(checkpoint["total_hands"]) == int(metrics[-1]["hands"])
            ),
            "assignment_chain_exact": (
                restored["tail_iteration"] == int(checkpoint["iteration"])
                and restored["pending_assignments"] is None
            ),
            "optimizer_serialized": (
                len(optimizer_steps) == 10
                and len(set(optimizer_steps)) == 1
                and optimizer_steps[0] > 0
            ),
            "replay_serialized": (
                len(checkpoint["ppo_replay_entries"]) == 2
                and checkpoint.get("ppo_replay_rng_state") is not None
                and int(checkpoint["ppo_replay_cumulative_rows"]) > 0
                and not checkpoint["ppo_replay_recovery_boundaries"]
            ),
            "dynamic_pool_serialized": len(pool_ids) == 5,
            "adaptive_league_serialized": (
                len(checkpoint["adaptive_opponent_ema_rewards"]) == 5
                and len(checkpoint["adaptive_opponent_weights"]) == 5
                and len(checkpoint["adaptive_opponent_observations"]) == 5
            ),
            "physical_accounting_complete": (
                accounting["prefix_complete"]
                and int(accounting["unknown_prefix_training_marker_hands"]) == 0
                and int(accounting["completed_hands"]) >= 65_536
            ),
            "new_deal_window_nonoverlapping": next_start >= first_unused_upper_bound,
            "same_run_resume_supported": str(checkpoint.get("run_id") or "")
            == str(config.get("run_id") or ""),
        }
        if not all(gates.values()):
            raise RuntimeError(f"{name} resume preflight failed: {gates}")
        destination.mkdir(parents=True)
        staged_metrics = destination / metrics_path.name
        staged_assignments = destination / assignments_path.name
        shutil.copy2(metrics_path, staged_metrics)
        shutil.copy2(assignments_path, staged_assignments)
        if sha256_path(staged_metrics) != sha256_path(metrics_path):
            raise RuntimeError(f"{name} staged metrics hash mismatch")
        if sha256_path(staged_assignments) != sha256_path(assignments_path):
            raise RuntimeError(f"{name} staged assignments hash mismatch")
        staged.append(
            {
                "name": name,
                "source_run_dir": str(source),
                "destination_run_dir": str(destination),
                "checkpoint": {
                    "path": str(checkpoint_path),
                    "sha256": sha256_path(checkpoint_path),
                    "run_id": checkpoint["run_id"],
                    "iteration": int(checkpoint["iteration"]),
                    "transition_hands": int(checkpoint["total_hands"]),
                    "physical_environment_hands": int(accounting["completed_hands"]),
                },
                "staged_metrics": {
                    "path": str(staged_metrics),
                    "sha256": sha256_path(staged_metrics),
                    "rows": len(metrics),
                },
                "staged_assignments": {
                    "path": str(staged_assignments),
                    "sha256": sha256_path(staged_assignments),
                    "rows": len(assignments),
                },
                "deal_window": {
                    "prior_start": prior_start,
                    "first_unused_upper_bound": first_unused_upper_bound,
                    "continuation_start": next_start,
                },
                "assignment_restore": restored,
                "gates": gates,
            }
        )
    output = {
        "schema": "cardpilot.integrated_alphaholdem_scale_resume_stage.v1",
        "staged": staged,
        "passed": bool(staged) and all(
            all(row["gates"].values()) for row in staged
        ),
        "command": [sys.executable, *sys.argv],
    }
    manifest_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
