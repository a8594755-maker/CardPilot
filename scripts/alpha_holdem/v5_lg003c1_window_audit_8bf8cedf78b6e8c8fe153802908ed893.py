#!/usr/bin/env python3
"""Independent post-training audit for one immutable LG003C1 Stage-A arm."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
CORRECTION_TOKEN = "8bf8cedf78b6e8c8fe153802908ed893"
REGISTRATION_TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
REGISTRATION_SHA256 = "525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TRAINER_SHA256 = "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452"
LAUNCHER_SHA256 = "c20ebf0d3201b8fdb01a2a31945dbb2166defb646a2f1e410ca2e6d2e04b3d96"
CORRECTION_AUDIT_SHA256 = "10bd494e75c84fb50610ec4d5363dbf230eb198f832a82cb70aca9f7c19f3381"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TARGET_HANDS = 581021901
MAX_OVERSHOOT = 50000
ASSIGNMENT_SEED = 2026072301
POOL_ORDER = [109, 115, 120, 129, 103]
POOL_HASHES = {
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
}
WEIGHTS = {
    "control_uniform": {103: 0.2, 109: 0.2, 115: 0.2, 120: 0.2, 129: 0.2},
    "treatment_diversity": {
        103: 0.151331630996897,
        109: 0.272679451627751,
        115: 0.062503368673781,
        120: 0.325118010944971,
        129: 0.1883675377566,
    },
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_dict_sha256(state_dict: dict) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def canonical_sha256(row: dict) -> str:
    item = dict(row)
    item.pop("record_sha256", None)
    raw = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def expected_assignment(arm: str, iteration: int) -> dict:
    payload = f"LG003_ASSIGNMENT_V1|{REGISTRATION_TOKEN}|{ASSIGNMENT_SEED}|{iteration}"
    u64 = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
    unit = u64 / float(1 << 64)
    member = None
    local_index = -1
    conditional = None
    if unit >= 0.2:
        conditional = (unit - 0.2) / 0.8
        cumulative = 0.0
        for member_id in sorted(WEIGHTS[arm]):
            cumulative += WEIGHTS[arm][member_id]
            if conditional < cumulative:
                member = member_id
                break
        if member is None:
            member = max(WEIGHTS[arm])
        local_index = POOL_ORDER.index(member)
    return {
        "u64": u64,
        "unit_interval": unit,
        "conditional_unit_interval": conditional,
        "selected_kind": "self_play" if member is None else "pool_snapshot",
        "selected_local_index": local_index,
        "selected_member_id": member,
    }


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=sorted(WEIGHTS), required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--stderr-log", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    run_root = Path(args.run_root).resolve()
    stdout_log = Path(args.stdout_log).resolve()
    stderr_log = Path(args.stderr_log).resolve()
    output_path = Path(args.out).resolve()
    checkpoint_path = run_root / "latest.pt"
    manifest_path = run_root / "run_manifest.json"
    metrics_path = run_root / "h1_training_metrics.jsonl"
    provenance_path = run_root / "opponent_assignment_provenance.jsonl"
    source_path = (
        ROOT
        / "models"
        / "alpha_holdem_v5_hybrid"
        / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
        / "h11_control_endpoint.pt"
    )
    trainer_path = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003c1_train_{CORRECTION_TOKEN}.py"
    launcher_path = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003c1_launcher_{CORRECTION_TOKEN}.ps1"
    correction_audit_path = (
        ROOT / "reports" / f"v5_lg003c1_correction_audit_{CORRECTION_TOKEN}_20260723.json"
    )

    checks: dict[str, bool] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    for path in (
        checkpoint_path,
        manifest_path,
        metrics_path,
        provenance_path,
        source_path,
        trainer_path,
        launcher_path,
        correction_audit_path,
        stdout_log,
        stderr_log,
    ):
        check(f"exists:{path.name}", path.is_file())

    check("source_sha256", sha256_path(source_path) == SOURCE_SHA256)
    check("trainer_sha256", sha256_path(trainer_path) == TRAINER_SHA256)
    check("launcher_sha256", sha256_path(launcher_path) == LAUNCHER_SHA256)
    check("correction_audit_sha256", sha256_path(correction_audit_path) == CORRECTION_AUDIT_SHA256)
    correction_audit = json.loads(correction_audit_path.read_text(encoding="utf-8"))
    check("correction_audit_pass", correction_audit.get("status") == "PASS_SOLE_PREOUTPUT_CORRECTION")
    check("stderr_empty", stderr_log.stat().st_size == 0)
    check("stdout_done", "Done!" in stdout_log.read_text(encoding="utf-8", errors="replace"))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    final_iteration = int(manifest.get("iteration", -1))
    final_hands = int(manifest.get("total_hands", -1))
    expected_rows = final_iteration - SOURCE_ITERATION
    expected_run_id = f"v5_lg003c1_{args.arm}_stagea_{CORRECTION_TOKEN}"
    check("manifest_finished", manifest.get("status") == "finished")
    check("manifest_run_id", manifest.get("run_id") == expected_run_id)
    check("manifest_arm", (manifest.get("config") or {}).get("lg003_arm") == args.arm)
    check("target_reached", TARGET_HANDS <= final_hands <= TARGET_HANDS + MAX_OVERSHOOT)
    check("positive_iteration_count", expected_rows > 0)

    metrics = read_jsonl(metrics_path)
    provenance = read_jsonl(provenance_path)
    check("metrics_row_count", len(metrics) == expected_rows)
    check("provenance_row_count", len(provenance) == expected_rows)
    check("metrics_iteration_sequence", [int(r["iteration"]) for r in metrics] == list(range(SOURCE_ITERATION + 1, final_iteration + 1)))
    metric_hands = [int(r["hands"]) for r in metrics]
    check("metrics_hands_strict", all(b > a for a, b in zip([SOURCE_HANDS, *metric_hands[:-1]], metric_hands)))
    check("metrics_final_hands", bool(metric_hands) and metric_hands[-1] == final_hands)
    check(
        "metrics_finite",
        all(
            math.isfinite(float(value))
            for row in metrics
            for value in row.values()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ),
    )

    previous = None
    selection_counts: Counter[str] = Counter()
    provenance_ok = True
    worker_contract_ok = True
    total_hands_alignment_ok = True
    refs_ok = True
    for offset, row in enumerate(provenance, start=1):
        iteration = SOURCE_ITERATION + offset
        lg = row.get("lg003") or {}
        expected = expected_assignment(args.arm, iteration)
        provenance_ok = provenance_ok and int(row.get("applies_to_iteration", -1)) == iteration
        provenance_ok = provenance_ok and row.get("previous_record_sha256") == previous
        provenance_ok = provenance_ok and row.get("record_sha256") == canonical_sha256(row)
        provenance_ok = provenance_ok and lg.get("arm") == args.arm
        provenance_ok = provenance_ok and lg.get("registration_token") == REGISTRATION_TOKEN
        provenance_ok = provenance_ok and lg.get("registration_sha256") == REGISTRATION_SHA256
        provenance_ok = provenance_ok and int(lg.get("assignment_seed", -1)) == ASSIGNMENT_SEED
        provenance_ok = provenance_ok and lg.get("conditional_weights_by_member_id") == {
            str(k): v for k, v in sorted(WEIGHTS[args.arm].items())
        }
        for key, value in expected.items():
            actual = lg.get(key)
            if isinstance(value, float):
                provenance_ok = provenance_ok and math.isclose(float(actual), value, rel_tol=0, abs_tol=1e-15)
            else:
                provenance_ok = provenance_ok and actual == value
        workers = row.get("workers") or []
        worker_contract_ok = worker_contract_ok and len(workers) == 22
        worker_contract_ok = worker_contract_ok and all(
            int(item.get("worker_id", -1)) == index
            and int((item.get("opponent") or {}).get("local_index", -999)) == expected["selected_local_index"]
            for index, item in enumerate(workers)
        )
        refs = row.get("pool_snapshot_refs") or []
        refs_ok = refs_ok and [int(item.get("snapshot_id", -1)) for item in refs] == POOL_ORDER
        metric_before = SOURCE_HANDS if offset == 1 else int(metrics[offset - 2]["hands"])
        total_hands_alignment_ok = total_hands_alignment_ok and int(row.get("total_hands_before_iteration", -1)) == metric_before
        previous = row.get("record_sha256")
        selection_counts[str(expected["selected_member_id"] or "self")] += 1
    check("provenance_chain_and_selector", provenance_ok)
    check("provenance_worker_contract", worker_contract_ok)
    check("provenance_hands_alignment", total_hands_alignment_ok)
    check("provenance_pool_refs", refs_ok)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    check("checkpoint_iteration", int(checkpoint.get("iteration", -1)) == final_iteration)
    check("checkpoint_hands", int(checkpoint.get("total_hands", -1)) == final_hands)
    check("checkpoint_run_id", checkpoint.get("run_id") == expected_run_id)
    lg = checkpoint.get("lg003") or {}
    check("checkpoint_lg003_arm", lg.get("arm") == args.arm)
    check("checkpoint_lg003_registration", lg.get("registration_sha256") == REGISTRATION_SHA256)
    check("checkpoint_lg003_source", lg.get("source_checkpoint_sha256") == SOURCE_SHA256)
    check("checkpoint_provenance_tail", lg.get("assignment_provenance_tail_sha256") == previous)
    check("checkpoint_pool_order", [int(row.get("id", -1)) for row in checkpoint.get("pool_snapshots", [])] == POOL_ORDER)
    observed_pool_hashes = {
        int(row["id"]): state_dict_sha256(row["state_dict"])
        for row in checkpoint.get("pool_snapshots", [])
    }
    check("checkpoint_pool_hashes", observed_pool_hashes == POOL_HASHES)
    check("checkpoint_pool_metadata_frozen", checkpoint.get("pool_active_metadata") == [
        {key: value for key, value in row.items() if key != "state_dict"}
        for row in checkpoint.get("pool_snapshots", [])
    ])
    check(
        "checkpoint_all_tensors_finite",
        all(
            bool(torch.isfinite(tensor).all().item())
            for state in [checkpoint.get("model") or {}, checkpoint.get("optimizer") or {}]
            for tensor in _walk_tensors(state)
        ),
    )

    artifacts = {
        str(path): {"bytes": path.stat().st_size, "sha256": sha256_path(path)}
        for path in (checkpoint_path, manifest_path, metrics_path, provenance_path, stdout_log, stderr_log)
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "schema_version": "v5.lg003c1.window_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "arm": args.arm,
        "correction_token": CORRECTION_TOKEN,
        "registration_token": REGISTRATION_TOKEN,
        "checks": checks,
        "passed": sum(checks.values()),
        "failed": len(failed),
        "failed_checks": failed,
        "result": {
            "source_hands": SOURCE_HANDS,
            "target_hands": TARGET_HANDS,
            "final_hands": final_hands,
            "new_hands": final_hands - SOURCE_HANDS,
            "overshoot_hands": final_hands - TARGET_HANDS,
            "source_iteration": SOURCE_ITERATION,
            "final_iteration": final_iteration,
            "metric_rows": len(metrics),
            "provenance_rows": len(provenance),
            "selection_counts": dict(sorted(selection_counts.items())),
            "checkpoint_sha256": artifacts[str(checkpoint_path)]["sha256"],
            "provenance_tail_sha256": previous,
            "pool_state_sha256": {str(k): v for k, v in sorted(observed_pool_hashes.items())},
        },
        "artifacts": artifacts,
        "next_authority": "ONE_COMPLETE_GREEDY_DIRECT_QUICK5K_FOR_THIS_FROZEN_CHECKPOINT"
        if not failed
        else "STOP_NO_EXTERNAL_EVALUATION",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


def _walk_tensors(value):
    if torch.is_tensor(value):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_tensors(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_tensors(item)


if __name__ == "__main__":
    raise SystemExit(main())
