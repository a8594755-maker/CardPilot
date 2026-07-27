#!/usr/bin/env python3
"""Finalize H3-DATASET-SAMPLE-001 from the first corrected-board profile.

This is a fail-closed registration utility.  It writes no dataset and grants no
behavior or official-hand authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "reports" / "v5_h3_dataset_selection_preregistration_draft_20260713.json"
SMOKE = ROOT / "reports" / "v5_h3_first_corrected_board_smoke_20260713.json"
SMOKE_ROOT = ROOT / "reports" / "h3_first_board_smoke_20260713"
DEFAULT_OUTPUT = ROOT / "reports" / "v5_h3_dataset_selection_preregistration_20260713.json"
EXPECTED_DRAFT_SHA = "3d38d65b9ef3904b928d07cd3fd79371ebd48a0a12fafa008b44aa5d305bf166"
EXPECTED_SMOKE_OVERALL = "PASS_FIRST_CORRECTED_BOARD_DETERMINISTIC_SMOKE"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lexical_stratum_key(value: str) -> tuple[str, int, int]:
    street, player, action_count = value.split("|")
    if street not in {"F", "T", "R"}:
        raise ValueError(f"invalid_street:{value}")
    return street, int(player), int(action_count)


def validate_populations(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("missing_population_profile")
    populations: dict[str, int] = {}
    for key, value in raw.items():
        lexical_stratum_key(str(key))
        count = int(value)
        if count <= 0 or count != value:
            raise ValueError(f"invalid_population:{key}:{value}")
        populations[str(key)] = count
    return dict(sorted(populations.items(), key=lambda item: lexical_stratum_key(item[0])))


def capped_hamilton_quotas(
    populations: dict[str, int], target: int = 30_000, base: int = 128
) -> dict[str, int]:
    """Apply the draft's base-plus-sqrt capped Hamilton rule exactly."""
    populations = validate_populations(populations)
    if target <= 0 or base <= 0:
        raise ValueError("invalid_target_or_base")
    if sum(populations.values()) < target:
        raise ValueError("first_board_population_below_target")
    quotas = {key: min(base, count) for key, count in populations.items()}
    if sum(quotas.values()) > target:
        raise ValueError("base_quotas_exceed_target")
    remaining = target - sum(quotas.values())
    weights = {key: math.sqrt(count) for key, count in populations.items()}

    while remaining:
        active = [key for key in populations if quotas[key] < populations[key]]
        if not active:
            raise ValueError("quota_capacity_exhausted")
        weight_sum = sum(weights[key] for key in active)
        ideal = {key: remaining * weights[key] / weight_sum for key in active}
        floor_added = 0
        for key in active:
            capacity = populations[key] - quotas[key]
            addition = min(capacity, math.floor(ideal[key]))
            quotas[key] += addition
            floor_added += addition
        remaining -= floor_added
        if not remaining:
            break

        # Hamilton largest remainders, with the frozen lexical tie-break. A
        # capped stratum is skipped; if caps leave more than one round of
        # remainders, the loop recomputes only the still-unallocated amount.
        ranked = sorted(
            active,
            key=lambda key: (-(ideal[key] - math.floor(ideal[key])), lexical_stratum_key(key)),
        )
        remainder_added = 0
        for key in ranked:
            if remaining == 0:
                break
            if quotas[key] < populations[key]:
                quotas[key] += 1
                remaining -= 1
                remainder_added += 1
        if floor_added == 0 and remainder_added == 0:
            raise ValueError("hamilton_no_progress")

    if sum(quotas.values()) != target:
        raise AssertionError("quota_total_mismatch")
    if any(quotas[key] <= 0 or quotas[key] > populations[key] for key in quotas):
        raise AssertionError("quota_bounds_mismatch")
    return quotas


def load_profile(smoke_path: Path = SMOKE, smoke_root: Path = SMOKE_ROOT) -> tuple[dict, Path, dict[str, int]]:
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    if smoke.get("overall") != EXPECTED_SMOKE_OVERALL:
        raise ValueError("first_corrected_board_smoke_not_pass")
    board_id = int(smoke["board_id"])
    manifests = [smoke_root / label / "bridge_manifest.json" for label in ("a", "b")]
    loaded = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    for manifest in loaded:
        if manifest.get("status") != "PASS_SMOKE_PREFIX_FORBIDDEN_TRAINING":
            raise ValueError("bridge_manifest_not_smoke_pass")
        if int(manifest["source_qa"]["physicalRows"]) <= 0:
            raise ValueError("empty_strict_board_audit")
    profiles = [validate_populations(item["source_qa"]["streetPlayerActionCounts"]) for item in loaded]
    if profiles[0] != profiles[1]:
        raise ValueError("repeat_population_profile_mismatch")
    if loaded[0]["source_board_sha256"] != loaded[1]["source_board_sha256"]:
        raise ValueError("repeat_source_identity_mismatch")
    if int(loaded[0]["source_board_meta"].split("flop_")[-1].split(".")[0]) != board_id:
        raise ValueError("smoke_board_identity_mismatch")
    return smoke, manifests[0], profiles[0]


def build_registration(
    draft_path: Path = DRAFT,
    smoke_path: Path = SMOKE,
    smoke_root: Path = SMOKE_ROOT,
) -> dict:
    if sha256(draft_path) != EXPECTED_DRAFT_SHA:
        raise ValueError("draft_sha256_mismatch")
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    smoke, profile_manifest, populations = load_profile(smoke_path, smoke_root)
    target = int(draft["candidate_resource_contract_frozen_before_profile"]["target_rows_per_qa_pass_board"])
    base = int(draft["candidate_sampling_rule_frozen_before_profile"]["base_quota_per_nonempty_stratum"])
    quotas = capped_hamilton_quotas(populations, target=target, base=base)
    registration = deepcopy(draft)
    registration["schema_version"] = "v5.hybrid.h3.dataset_selection_preregistration.v1"
    registration["status"] = "IMMUTABLE_REGISTERED_PENDING_INDEPENDENT_AUDIT"
    registration["registered_at"] = datetime.now(timezone.utc).isoformat()
    registration["supersedes_draft_sha256"] = EXPECTED_DRAFT_SHA
    registration["frozen_draft_evidence"]["first_corrected_board_profile"] = {
        "board_id": int(smoke["board_id"]),
        "smoke_result_path": str(smoke_path.resolve()),
        "smoke_result_sha256": sha256(smoke_path),
        "bridge_manifest_path": str(profile_manifest.resolve()),
        "bridge_manifest_sha256": sha256(profile_manifest),
        "source_board_sha256": smoke["source_board_sha256"],
        "population_counts": populations,
    }
    registration["immutable_exact_quota_map"] = quotas
    registration["immutable_exact_quota_total_per_board"] = sum(quotas.values())
    registration["items_intentionally_not_frozen_until_first_corrected_profile"] = []
    registration["post_profile_decision_rule_result"] = "FEASIBLE_EXACT_QUOTAS_FROZEN"
    registration["independent_audit_required_before_materialization"] = True
    registration["dataset_materialization_authorized"] = False
    registration["h3_preregistration_authorized"] = False
    registration["behavior_launch_authorized"] = False
    registration["official_hands_authorized"] = 0
    registration["strength_claim"] = "FORBIDDEN"
    return registration


def atomic_no_overwrite_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing_to_overwrite:{path}")
    partial = path.with_name(f"{path.name}.{os.getpid()}.partial")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", type=Path, default=DRAFT)
    parser.add_argument("--smoke", type=Path, default=SMOKE)
    parser.add_argument("--smoke-root", type=Path, default=SMOKE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--print-only", action="store_true")
    args = parser.parse_args()
    try:
        result = build_registration(args.draft.resolve(), args.smoke.resolve(), args.smoke_root.resolve())
        if args.print_only:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            atomic_no_overwrite_json(args.output.resolve(), result)
            print(json.dumps({"overall": "PASS_WRITTEN", "output": str(args.output.resolve())}, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({
            "overall": "FAIL_CLOSED",
            "error": f"{type(error).__name__}:{error}",
            "dataset_materialization_authorized": False,
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
        }, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
