#!/usr/bin/env python3
"""Independent fail-closed audit for H4-POOL-MEAS-001."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def state_hash(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = canonical_bytes([name, str(tensor.dtype), list(tensor.shape)])
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def audit(design_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    design = json.loads(design_path.read_text(encoding="utf-8-sig"))
    unsigned = dict(design)
    claimed_payload = unsigned.pop("design_payload_sha256", None)
    actual_payload = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
    if claimed_payload != actual_payload:
        errors.append("design payload hash mismatch")
    if design.get("schema_version") != "v5.pool_selection.measurement_design.v1" or design.get("design_id") != "H4-POOL-MEAS-001":
        errors.append("design identity mismatch")
    if design.get("immutable") is not True or design.get("status") != "IMMUTABLE_REGISTERED_REPORTING_ONLY":
        errors.append("immutability/status mismatch")
    containers = design.get("containers", [])
    if len(containers) != 2:
        errors.append("exactly two containers required")
        source = historical = {}
    else:
        loaded = []
        for row in containers:
            path = Path(row.get("path", ""))
            if not path.is_file() or sha256(path) != row.get("sha256"):
                errors.append(f"container identity mismatch: {path}")
                loaded.append({})
            else:
                loaded.append(torch.load(path, map_location="cpu", weights_only=False))
        source, historical = loaded
    if int(source.get("iteration", -1)) != 31400 or int(source.get("total_hands", -1)) != 515_989_661:
        errors.append("source endpoint mismatch")
    active = list(source.get("pool_snapshots", []))
    active_ids = {int(row["id"]) for row in active}
    history_keys = {
        (int(row["id"]), int(row["iteration"]), int(row["hands"])): float(row["selection_loss"])
        for row in source.get("pool_candidate_history", [])
        if row.get("iteration") is not None and row.get("selection_loss") is not None
    }
    eligible = []
    for row in historical.get("pool_snapshots", []):
        key = (int(row["id"]), int(row["iteration"]), int(row["hands"]))
        if int(row["id"]) not in active_ids and key in history_keys and abs(float(row["selection_loss"]) - history_keys[key]) <= 1e-12:
            eligible.append(row)
    eligible.sort(key=lambda row: (float(row["selection_loss"]), int(row["id"])))
    count = int(design.get("selection_rule", {}).get("excluded_count", -1))
    expected_excluded = [int(row["id"]) for row in eligible[:count]]
    if expected_excluded != design.get("selection_rule", {}).get("selected_excluded_ids"):
        errors.append("payoff-blind excluded selection rule mismatch")
    panel = design.get("panel", [])
    if len(panel) != 5 + count or sum(row.get("active_at_gate31400") is True for row in panel) != 5:
        errors.append("panel cardinality/active count mismatch")
    inventory = {int(row["id"]): row for row in active + eligible[:count]}
    for row in panel:
        actual = inventory.get(int(row.get("id", -1)))
        if not actual:
            errors.append(f"panel snapshot missing: {row.get('id')}")
            continue
        for key in ("iteration", "hands"):
            if int(row.get(key, -1)) != int(actual[key]):
                errors.append(f"snapshot {row['id']} {key} mismatch")
        if abs(float(row.get("selection_loss", float("inf"))) - float(actual["selection_loss"])) > 1e-12:
            errors.append(f"snapshot {row['id']} selection loss mismatch")
        if row.get("state_sha256") != state_hash(actual["state_dict"]):
            errors.append(f"snapshot {row['id']} state hash mismatch")
    measurement = design.get("measurement", {})
    expected_measurement = {
        "pairs_per_edge": 2000,
        "seed": 2026071501,
        "seat_order": [0, 1],
        "policy_mode": "greedy_argmax_both_sides",
        "starting_stack_bb": 200.0,
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
        "same_deal_stream_on_every_edge": True,
        "no_adaptive_extension": True,
    }
    for key, value in expected_measurement.items():
        if measurement.get(key) != value:
            errors.append(f"measurement contract mismatch: {key}")
    decision = design.get("decision_rule", {})
    if decision.get("meaningful_inversion_margin_bb100") != 10.0 or decision.get("familywise_alpha") != 0.05 or decision.get("multiplicity") != "holm_bonferroni_active_vs_excluded":
        errors.append("decision gate mismatch")
    tooling = design.get("tooling", {})
    for prefix in ("design_generator", "measurement"):
        path = Path(tooling.get(f"{prefix}_path", ""))
        if not path.is_file() or sha256(path) != tooling.get(f"{prefix}_sha256"):
            errors.append(f"tool identity mismatch: {prefix}")
    if design.get("authority") != "REPORTING_ONLY_NO_LAUNCH" or design.get("behavior_launch_authorized") is not False or design.get("official_hands_authorized") != 0:
        errors.append("authority boundary mismatch")
    return {
        "schema_version": "v5.h4.pool_measurement_design_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMMUTABLE_H4_POOL_MEASUREMENT_DESIGN" if not errors else "FAIL_CLOSED",
        "errors": errors,
        "design_path": str(design_path.resolve()),
        "design_sha256": sha256(design_path),
        "design_payload_sha256": actual_payload,
        "panel_ids": [int(row["id"]) for row in panel],
        "expected_excluded_ids": expected_excluded,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"one-shot output exists: {args.out}")
    result = audit(args.design.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
