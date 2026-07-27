#!/usr/bin/env python3
"""Independent fail-closed audit for H3-DATASET-SAMPLE-001."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "reports" / "v5_h3_dataset_selection_preregistration_draft_20260713.json"
SMOKE = ROOT / "reports" / "v5_h3_first_corrected_board_smoke_20260713.json"
SMOKE_MANIFEST = ROOT / "reports" / "h3_first_board_smoke_20260713" / "a" / "bridge_manifest.json"
EXPECTED_DRAFT_SHA = "3d38d65b9ef3904b928d07cd3fd79371ebd48a0a12fafa008b44aa5d305bf166"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key_parts(key: str) -> tuple[str, int, int]:
    parts = key.split("|")
    if len(parts) != 3 or parts[0] not in {"F", "T", "R"}:
        raise ValueError(f"invalid_stratum:{key}")
    player, actions = int(parts[1]), int(parts[2])
    if player not in {0, 1} or actions not in {2, 3, 4, 5, 6}:
        raise ValueError(f"invalid_stratum:{key}")
    return parts[0], player, actions


def independent_quota_reference(populations: dict[str, int], target: int, base: int) -> dict[str, int]:
    """Independent implementation of capped Hamilton with lexical tie-break."""
    population = {str(key): int(value) for key, value in populations.items()}
    for key, value in population.items():
        key_parts(key)
        if value <= 0:
            raise ValueError("nonpositive_population")
    population = dict(sorted(population.items(), key=lambda item: key_parts(item[0])))
    allocation = {key: min(base, value) for key, value in population.items()}
    left = target - sum(allocation.values())
    if left < 0 or sum(population.values()) < target:
        raise ValueError("infeasible_target")

    while left > 0:
        eligible = [key for key in population if allocation[key] < population[key]]
        if not eligible:
            raise ValueError("capacity_exhausted")
        denominator = sum(math.sqrt(population[key]) for key in eligible)
        shares = {key: left * math.sqrt(population[key]) / denominator for key in eligible}
        additions = {
            key: min(population[key] - allocation[key], int(math.floor(shares[key])))
            for key in eligible
        }
        for key, value in additions.items():
            allocation[key] += value
            left -= value
        ranking = sorted(
            eligible,
            key=lambda key: (-(shares[key] - math.floor(shares[key])), key_parts(key)),
        )
        progress = sum(additions.values())
        for key in ranking:
            if left == 0:
                break
            if allocation[key] < population[key]:
                allocation[key] += 1
                left -= 1
                progress += 1
        if progress == 0:
            raise ValueError("no_progress")
    return allocation


def audit(lock_path: Path, expected_lock_sha: str) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    smoke = json.loads(SMOKE.read_text(encoding="utf-8"))
    smoke_manifest = json.loads(SMOKE_MANIFEST.read_text(encoding="utf-8"))
    populations = smoke_manifest["source_qa"]["streetPlayerActionCounts"]
    target = draft["candidate_resource_contract_frozen_before_profile"]["target_rows_per_qa_pass_board"]
    base = draft["candidate_sampling_rule_frozen_before_profile"]["base_quota_per_nonempty_stratum"]
    reference = independent_quota_reference(populations, target, base)
    profile = lock.get("frozen_draft_evidence", {}).get("first_corrected_board_profile", {})
    inherited_sections = [
        "unchanged_asset_gate",
        "candidate_resource_contract_frozen_before_profile",
        "candidate_sampling_rule_frozen_before_profile",
        "candidate_execution_plan",
        "candidate_full_corpus_gates",
    ]
    checks = {
        "expected_lock_sha": sha256(lock_path) == expected_lock_sha.lower(),
        "draft_sha": sha256(DRAFT) == EXPECTED_DRAFT_SHA,
        "schema": lock.get("schema_version") == "v5.hybrid.h3.dataset_selection_preregistration.v1",
        "status": lock.get("status") == "IMMUTABLE_REGISTERED_PENDING_INDEPENDENT_AUDIT",
        "draft_pin": lock.get("supersedes_draft_sha256") == EXPECTED_DRAFT_SHA,
        "smoke_pass": smoke.get("overall") == "PASS_FIRST_CORRECTED_BOARD_DETERMINISTIC_SMOKE",
        "smoke_pin": profile.get("smoke_result_sha256") == sha256(SMOKE),
        "manifest_pin": profile.get("bridge_manifest_sha256") == sha256(SMOKE_MANIFEST),
        "source_pin": profile.get("source_board_sha256") == smoke.get("source_board_sha256"),
        "population_exact": profile.get("population_counts") == populations,
        "quota_reference_exact": lock.get("immutable_exact_quota_map") == reference,
        "quota_total": lock.get("immutable_exact_quota_total_per_board") == target == sum(reference.values()),
        "quota_bounds": all(0 < reference[key] <= int(populations[key]) for key in reference),
        "no_pending_items": lock.get("items_intentionally_not_frozen_until_first_corrected_profile") == [],
        "decision_feasible": lock.get("post_profile_decision_rule_result") == "FEASIBLE_EXACT_QUOTAS_FROZEN",
        "inherited_sections_exact": all(lock.get(key) == draft.get(key) for key in inherited_sections),
        "audit_required": lock.get("independent_audit_required_before_materialization") is True,
        "registration_not_self_authorized": lock.get("dataset_materialization_authorized") is False,
        "no_h3_behavior_authority": lock.get("h3_preregistration_authorized") is False and lock.get("behavior_launch_authorized") is False,
        "no_official_authority": lock.get("official_hands_authorized") == 0,
        "strength_claim_forbidden": lock.get("strength_claim") == "FORBIDDEN",
    }
    passed = sum(bool(value) for value in checks.values())
    overall = "PASS_IMMUTABLE_H3_DATASET_SELECTION_PREREGISTRATION" if passed == len(checks) else "FAIL_CLOSED"
    return {
        "schema_version": "v5.hybrid.h3.dataset_selection_preregistration.audit.v1",
        "overall": overall,
        "lock_path": str(lock_path.resolve()),
        "lock_sha256": sha256(lock_path),
        "assertions_passed": passed,
        "assertions_total": len(checks),
        "checks": checks,
        "dataset_materialization_authorized": overall.startswith("PASS"),
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }


def atomic_no_overwrite(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing_to_overwrite:{path}")
    partial = path.with_name(f"{path.name}.{os.getpid()}.partial")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = audit(args.lock.resolve(), args.expected_lock_sha256)
        if args.output:
            atomic_no_overwrite(args.output.resolve(), result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["overall"].startswith("PASS") else 2
    except Exception as error:
        result = {
            "overall": "FAIL_CLOSED",
            "error": f"{type(error).__name__}:{error}",
            "dataset_materialization_authorized": False,
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
        }
        if args.output:
            atomic_no_overwrite(args.output.resolve(), result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
