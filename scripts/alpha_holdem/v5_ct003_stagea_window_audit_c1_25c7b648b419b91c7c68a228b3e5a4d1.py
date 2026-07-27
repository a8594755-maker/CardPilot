#!/usr/bin/env python3
"""Fresh independent CT003 Stage-A endpoint audit after a derived checker defect."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import psutil
import torch


IDENTITY = "25c7b648b419b91c7c68a228b3e5a4d1147719d258ec96791341039311332377"
TOKEN = IDENTITY[:32]
CT003_TOKEN = "7296402ab1ddaadd86ebde1795d0f2ad"
CT003_PREREG_SHA256 = "7702ff2d7323bcb053443a7b1e540e4624f43e3d932bfd2c3ecbb7afb0bb11fe"
LG003_TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
LG003_PREREG_SHA256 = "525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d"
SOURCE_CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_HANDS = 576_021_901
SOURCE_ITERATION = 35_051
TARGET_HANDS = 581_021_901
ASSIGNMENT_SEED = 2_026_072_301
TARGET_MODE = "full_trajectory_discounted_mc_gamma_0.999"
RUN_ID = "v5_ct003_mc_target_stagea_7296402ab1ddaadd86ebde1795d0f2ad"
POOL_REFS = [
    {"local_index": 0, "snapshot_hands": 450_186_098, "snapshot_id": 109, "snapshot_iteration": 27_400},
    {"local_index": 1, "snapshot_hands": 469_929_538, "snapshot_id": 115, "snapshot_iteration": 28_600},
    {"local_index": 2, "snapshot_hands": 486_379_183, "snapshot_id": 120, "snapshot_iteration": 29_600},
    {"local_index": 3, "snapshot_hands": 515_989_661, "snapshot_id": 129, "snapshot_iteration": 31_400},
    {"local_index": 4, "snapshot_hands": 430_445_532, "snapshot_id": 103, "snapshot_iteration": 26_200},
]
POOL_ORDER = [row["snapshot_id"] for row in POOL_REFS]
WEIGHTS = {"103": 0.2, "109": 0.2, "115": 0.2, "120": 0.2, "129": 0.2}
EXPECTED_INPUTS = {
    "latest.pt": ("76b85c5bd377533329424140d01352075e44b6a1aeb5796828fee60f34037f62", 261_418_894),
    "h1_training_metrics.jsonl": ("21d63aaadb114cb630227eab3b8cf8dc02993c2ed898bf2491d02f65933ed8d1", 279_619),
    "opponent_assignment_provenance.jsonl": ("93f6d8c252738d9f95fdde016222e01e3878ff93984e2ca259a4102bd5fa967d", 1_324_764),
    "run_manifest.json": ("87ad99f17c020d5dd31812851dd5ab3a84fa61bb8fbc93dd4721e0351ccc4fa2", 12_316),
}
ORIGINAL_AUDIT_SHA256 = "63ac2e1bfbca08846dbbb6c1154bc7a132d44a63a8d4bf082cf84d1af5bafb66"
CONTROL_METRICS_SHA256 = "50db465ea1f1037ec7d8d1c7ec5d947fa04cab7b9071a81bc6372cc0779c32ca"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite_tree(value) -> bool:
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(item) for item in value)
    return not isinstance(value, float) or math.isfinite(value)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def assignment(iteration: int) -> dict:
    payload = f"LG003_ASSIGNMENT_V1|{LG003_TOKEN}|{ASSIGNMENT_SEED}|{iteration}"
    u64 = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
    unit = u64 / float(1 << 64)
    if unit < 0.2:
        return {
            "u64": u64,
            "unit": unit,
            "conditional": None,
            "member": None,
            "local_index": -1,
            "kind": "self_play",
        }
    conditional = (unit - 0.2) / 0.8
    cumulative = 0.0
    member = None
    for candidate in sorted(int(key) for key in WEIGHTS):
        cumulative += WEIGHTS[str(candidate)]
        if conditional < cumulative:
            member = candidate
            break
    if member is None:
        member = max(int(key) for key in WEIGHTS)
    return {
        "u64": u64,
        "unit": unit,
        "conditional": conditional,
        "member": member,
        "local_index": POOL_ORDER.index(member),
        "kind": "pool_snapshot",
    }


def exact_float(left, right) -> bool:
    return left == right


def producer_absent() -> bool:
    own_pid = psutil.Process().pid
    for proc in psutil.process_iter(["pid", "cmdline"]):
        if proc.info["pid"] == own_pid:
            continue
        try:
            command = " ".join(proc.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if (
            "v5_ct003_train_7296402ab1ddaadd86ebde1795d0f2ad.py" in command
            or "v5_ct003_launcher_7296402ab1ddaadd86ebde1795d0f2ad.ps1" in command
        ):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--original-audit", required=True)
    parser.add_argument("--control-metrics", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    original_audit_path = Path(args.original_audit).resolve()
    control_metrics_path = Path(args.control_metrics).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite audit: {out}")

    paths = {name: run_dir / name for name in EXPECTED_INPUTS}
    checks: dict[str, bool] = {}
    artifacts: dict[str, dict] = {}
    for name, path in paths.items():
        expected_hash, expected_bytes = EXPECTED_INPUTS[name]
        actual_hash = sha256_path(path) if path.is_file() else None
        actual_bytes = path.stat().st_size if path.is_file() else None
        checks[f"frozen_{name}_exact"] = actual_hash == expected_hash and actual_bytes == expected_bytes
        artifacts[str(path)] = {"sha256": actual_hash, "bytes": actual_bytes}

    checks["original_audit_exact"] = (
        original_audit_path.is_file() and sha256_path(original_audit_path) == ORIGINAL_AUDIT_SHA256
    )
    checks["control_metrics_exact"] = (
        control_metrics_path.is_file() and sha256_path(control_metrics_path) == CONTROL_METRICS_SHA256
    )
    artifacts[str(original_audit_path)] = {
        "sha256": sha256_path(original_audit_path),
        "bytes": original_audit_path.stat().st_size,
    }
    artifacts[str(control_metrics_path)] = {
        "sha256": sha256_path(control_metrics_path),
        "bytes": control_metrics_path.stat().st_size,
    }
    checks["producer_process_absent"] = producer_absent()

    original = json.loads(original_audit_path.read_text(encoding="utf-8"))
    checks["original_failure_localized"] = (
        original.get("status") == "FAIL"
        and original.get("failed") == 1
        and original.get("failed_checks") == ["provenance_uniform"]
    )
    manifest = json.loads(paths["run_manifest.json"].read_text(encoding="utf-8"))
    metrics = load_jsonl(paths["h1_training_metrics.jsonl"])
    provenance = load_jsonl(paths["opponent_assignment_provenance.jsonl"])
    checkpoint = torch.load(paths["latest.pt"], map_location="cpu", weights_only=False)

    iteration = int(checkpoint.get("iteration", -1))
    hands = int(checkpoint.get("total_hands", -1))
    checks["manifest_endpoint_exact"] = (
        manifest.get("status") == "finished"
        and int(manifest.get("iteration", -1)) == iteration == 35_356
        and int(manifest.get("total_hands", -1)) == hands == 581_038_145
    )
    checks["registered_hand_budget"] = 5_000_000 <= hands - SOURCE_HANDS <= 5_050_000
    checks["metric_count_and_iterations"] = (
        len(metrics) == iteration - SOURCE_ITERATION == 305
        and [int(row.get("iteration", -1)) for row in metrics]
        == list(range(SOURCE_ITERATION + 1, iteration + 1))
    )
    checks["metric_hands_monotonic_and_endpoint"] = (
        all(int(metrics[index]["hands"]) < int(metrics[index + 1]["hands"]) for index in range(len(metrics) - 1))
        and int(metrics[-1].get("hands", -1)) == hands
    )
    checks["target_contract_every_metric"] = all(
        row.get("ct003_target_mode") == TARGET_MODE
        and row.get("ct003_mc_target_fraction") == 1.0
        and int(row.get("ct003_mc_target_rows", 0)) > 0
        for row in metrics
    )
    checks["metrics_finite"] = finite_tree(metrics)
    checks["checkpoint_model_finite"] = finite_tree(checkpoint.get("model"))
    checks["checkpoint_optimizer_finite"] = finite_tree(checkpoint.get("optimizer"))
    contract = checkpoint.get("lg003") or {}
    checks["checkpoint_contract"] = (
        contract.get("source_checkpoint_sha256") == SOURCE_CHECKPOINT_SHA256
        and contract.get("ct003_registration_token") == CT003_TOKEN
        and contract.get("ct003_preregistration_sha256") == CT003_PREREG_SHA256
        and contract.get("ct003_target_mode") == TARGET_MODE
        and contract.get("pool_checkpoint_order") == POOL_ORDER
    )
    snapshots = checkpoint.get("pool_snapshots") or []
    checks["checkpoint_pool_exact"] = [
        {
            "local_index": index,
            "snapshot_hands": int(row.get("hands", -1)),
            "snapshot_id": int(row.get("id", -1)),
            "snapshot_iteration": int(row.get("iteration", -1)),
        }
        for index, row in enumerate(snapshots)
    ] == POOL_REFS

    checks["provenance_count_and_iterations"] = (
        len(provenance) == len(metrics)
        and [int(row.get("applies_to_iteration", -1)) for row in provenance]
        == list(range(SOURCE_ITERATION + 1, iteration + 1))
    )
    checks["provenance_hands_alignment"] = all(
        int(row.get("total_hands_before_iteration", -1))
        == (SOURCE_HANDS if index == 0 else int(metrics[index - 1]["hands"]))
        for index, row in enumerate(provenance)
    )

    chain_ok = True
    semantics_ok = True
    previous_hash = None
    for row in provenance:
        payload = dict(row)
        record_hash = payload.pop("record_sha256", None)
        if payload.get("previous_record_sha256") != previous_hash:
            chain_ok = False
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != record_hash:
            chain_ok = False
        previous_hash = record_hash

        iteration_value = int(row.get("applies_to_iteration", -1))
        expected = assignment(iteration_value)
        lg003 = row.get("lg003") or {}
        selected_ref = (
            None if expected["local_index"] == -1 else POOL_REFS[expected["local_index"]]
        )
        expected_worker_opponent = (
            {"kind": "self_play", "local_index": -1}
            if selected_ref is None
            else {
                "kind": "pool_snapshot",
                "local_index": selected_ref["local_index"],
                "snapshot_hands": selected_ref["snapshot_hands"],
                "snapshot_id": selected_ref["snapshot_id"],
                "snapshot_iteration": selected_ref["snapshot_iteration"],
            }
        )
        expected_workers = [
            {"worker_id": worker_id, "opponent": expected_worker_opponent}
            for worker_id in range(22)
        ]
        expected_group = [{
            "group_id": 0,
            "opponent_id": expected["local_index"],
            "workers": list(range(22)),
        }]
        semantics_ok = semantics_ok and (
            row.get("schema_version") == "v5.lg003.opponent_assignment_provenance.v1"
            and row.get("run_id") == RUN_ID
            and row.get("assignment_mode") == "per-iteration"
            and int(row.get("worker_count", -1)) == 22
            and int(row.get("worker_seed_base", -1)) == 73_000
            and int(row.get("pool_size", -1)) == 5
            and row.get("pool_snapshot_refs") == POOL_REFS
            and row.get("group_metadata") == expected_group
            and row.get("workers") == expected_workers
            and lg003.get("registration_token") == LG003_TOKEN
            and lg003.get("registration_sha256") == LG003_PREREG_SHA256
            and lg003.get("assignment_rule") == "LG003_ASSIGNMENT_V1"
            and int(lg003.get("assignment_seed", -1)) == ASSIGNMENT_SEED
            and lg003.get("arm") == "control_uniform"
            and lg003.get("conditional_weights_by_member_id") == WEIGHTS
            and lg003.get("self_probability") == 0.2
            and int(lg003.get("u64", -1)) == expected["u64"]
            and exact_float(lg003.get("unit_interval"), expected["unit"])
            and exact_float(lg003.get("conditional_unit_interval"), expected["conditional"])
            and lg003.get("selected_kind") == expected["kind"]
            and int(lg003.get("selected_local_index", -999)) == expected["local_index"]
            and lg003.get("selected_member_id") == expected["member"]
        )
    checks["provenance_hash_chain"] = chain_ok
    checks["provenance_assignment_semantics"] = semantics_ok

    treatment_hps = sorted(float(row["hands_per_second"]) for row in metrics)
    control_rows = load_jsonl(control_metrics_path)
    control_hps = sorted(float(row["hands_per_second"]) for row in control_rows)
    median_hps = treatment_hps[len(treatment_hps) // 2]
    control_median_hps = control_hps[len(control_hps) // 2]
    checks["throughput_ratio_at_least_0_85"] = median_hps / control_median_hps >= 0.85

    failed = [name for name, value in checks.items() if not value]
    result = {
        "schema_version": "v5.ct003.stage_a.window_audit.c1.v1",
        "identity": IDENTITY,
        "token": TOKEN,
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": failed,
        "measurements": {
            "iteration": iteration,
            "total_hands": hands,
            "new_hands": hands - SOURCE_HANDS,
            "metric_rows": len(metrics),
            "provenance_rows": len(provenance),
            "median_hps": median_hps,
            "control_median_hps": control_median_hps,
            "throughput_ratio": median_hps / control_median_hps,
        },
        "artifacts": artifacts,
        "classification": (
            "FRESH_CORRECTED_DERIVED_AUDIT_PASS_SCIENTIFIC_ENDPOINT_VALID"
            if not failed
            else "FRESH_CORRECTED_DERIVED_AUDIT_FAIL"
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
