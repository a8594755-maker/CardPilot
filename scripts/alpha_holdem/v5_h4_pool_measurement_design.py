#!/usr/bin/env python3
"""Freeze the reporting-only H4 pool-selection measurement design.

The panel is selected without reading any cross-play payoff: five snapshots active at
the exact source gate plus the N lowest-loss reconstructable historical exclusions that
are identity-matched in the source checkpoint's candidate history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


SCHEMA = "v5.pool_selection.measurement_design.v1"
DESIGN_ID = "H4-POOL-MEAS-001"
POLICY_MODE = "greedy_argmax_both_sides"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def state_dict_sha256(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = canonical_bytes([name, str(tensor.dtype), list(tensor.shape)])
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def payload_sha256(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("design_payload_sha256", None)
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def snapshot_row(snapshot: dict[str, Any], *, active: bool, source: str) -> dict[str, Any]:
    return {
        "id": int(snapshot["id"]),
        "iteration": int(snapshot["iteration"]),
        "hands": int(snapshot["hands"]),
        "selection_loss": float(snapshot["selection_loss"]),
        "state_sha256": state_dict_sha256(snapshot["state_dict"]),
        "active_at_gate31400": active,
        "state_source_container": source,
    }


def build_design(source_path: Path, historical_path: Path, *, excluded_count: int) -> dict[str, Any]:
    if excluded_count < 1:
        raise ValueError("excluded_count must be positive")
    source_path = source_path.resolve()
    historical_path = historical_path.resolve()
    source = torch.load(source_path, map_location="cpu", weights_only=False)
    historical = torch.load(historical_path, map_location="cpu", weights_only=False)
    for label, checkpoint in (("source", source), ("historical", historical)):
        if checkpoint.get("env_version") != "v55" or checkpoint.get("obs_version") != "v55":
            raise ValueError(f"{label} checkpoint is not v55/v55")
    if int(source.get("iteration", -1)) != 31400 or int(source.get("total_hands", -1)) != 515_989_661:
        raise ValueError("source is not exact gate31400 / 515,989,661")

    active_snapshots = list(source.get("pool_snapshots", []))
    if len(active_snapshots) != 5:
        raise ValueError("source must contain exactly five active pool snapshots")
    active_ids = {int(row["id"]) for row in active_snapshots}
    history_identity = {
        (int(row["id"]), int(row["iteration"]), int(row["hands"])): float(row["selection_loss"])
        for row in source.get("pool_candidate_history", [])
        if row.get("iteration") is not None and row.get("selection_loss") is not None
    }
    eligible: list[dict[str, Any]] = []
    for row in historical.get("pool_snapshots", []):
        key = (int(row["id"]), int(row["iteration"]), int(row["hands"]))
        if int(row["id"]) in active_ids or key not in history_identity:
            continue
        if abs(float(row["selection_loss"]) - history_identity[key]) > 1e-12:
            raise ValueError(f"candidate-history selection-loss mismatch for snapshot {row['id']}")
        eligible.append(row)
    eligible.sort(key=lambda row: (float(row["selection_loss"]), int(row["id"])))
    if len(eligible) < excluded_count:
        raise ValueError("insufficient reconstructable historical exclusions")
    excluded = eligible[:excluded_count]

    panel = [snapshot_row(row, active=True, source=str(source_path)) for row in active_snapshots]
    panel.extend(snapshot_row(row, active=False, source=str(historical_path)) for row in excluded)
    panel.sort(key=lambda row: int(row["id"]))
    design: dict[str, Any] = {
        "schema_version": SCHEMA,
        "design_id": DESIGN_ID,
        "status": "IMMUTABLE_REGISTERED_REPORTING_ONLY",
        "immutable": True,
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "question": "Does the gate31400 loss-kbest proxy exclude reconstructable snapshots that are materially stronger on frozen common-deal cross-play?",
        "estimand": "excluded minus active greedy common-deal payoff for every active/excluded edge; full panel matrix retained",
        "selection_rule": {
            "active": "all five exact source-gate pool snapshots",
            "excluded": "lowest selection_loss then lowest id among historical-container snapshots identity-matched in source candidate history and not active",
            "excluded_count": excluded_count,
            "payoff_blind": True,
            "selected_excluded_ids": [int(row["id"]) for row in excluded],
        },
        "containers": [
            {"role": "exact_gate31400_source", "path": str(source_path), "sha256": file_sha256(source_path)},
            {"role": "historical_state_reconstruction", "path": str(historical_path), "sha256": file_sha256(historical_path)},
        ],
        "panel": panel,
        "measurement": {
            "pairs_per_edge": 2000,
            "seed": 2026071501,
            "seat_order": [0, 1],
            "policy_mode": POLICY_MODE,
            "starting_stack_bb": 200.0,
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "statistical_unit": "whole common-deal seat-swapped pair",
            "same_deal_stream_on_every_edge": True,
            "no_adaptive_extension": True,
            "runtime_ceiling_seconds": 172800.0,
            "max_ood_rate": 0.01,
        },
        "decision_rule": {
            "meaningful_inversion_margin_bb100": 10.0,
            "familywise_alpha": 0.05,
            "multiplicity": "holm_bonferroni_active_vs_excluded",
            "pass": "at least two excluded identities each have a supported >10 bb/100 inversion, or one excluded has supported inversions against at least two active identities",
            "fail": "simultaneous adjusted upper bounds show no active/excluded inversion exceeds 10 bb/100",
            "otherwise": "INCONCLUSIVE",
        },
        "inference_scope": "pool-selection mechanism candidate permission only; not a behavior verdict and not external strength",
        "tooling": {
            "design_generator_path": str(Path(__file__).resolve()),
            "design_generator_sha256": file_sha256(Path(__file__).resolve()),
            "measurement_path": str((Path(__file__).parent / "v5_pool_selection_measurement.py").resolve()),
            "measurement_sha256": file_sha256((Path(__file__).parent / "v5_pool_selection_measurement.py").resolve()),
        },
        "authority": "REPORTING_ONLY_NO_LAUNCH",
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }
    design["design_payload_sha256"] = payload_sha256(design)
    return design


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--historical", required=True, type=Path)
    parser.add_argument("--excluded-count", type=int, default=3)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"one-shot output exists: {args.out}")
    design = build_design(args.source, args.historical, excluded_count=args.excluded_count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(design, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": "PASS_WRITTEN", "out": str(args.out.resolve()), "panel_ids": [row["id"] for row in design["panel"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
