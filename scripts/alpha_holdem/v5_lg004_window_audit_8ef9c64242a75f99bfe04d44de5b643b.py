"""Independent post-training audit for the immutable LG004 Stage-A treatment."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import torch

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "8ef9c64242a75f99bfe04d44de5b643b"
PREREG_SHA256 = "156b54be70472e9f139672ba5f537a6db39cbea240c2cc21055f679c9f46ae05"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
HISTORICAL_SHA256 = "3bbaf4c6a42d5155964e05bfcef6cce45f484875d34b94f59a6804805b53fe94"
TRAINER_SHA256 = "0b3c41e789eddeabc163133e77d31fe068293e58c43c436a30f6691de0a455d8"
LAUNCHER_SHA256 = "a80192b1152b1bc9f2deb8acaa19347951b6f339ca4b4bfec18c8b64805d97f7"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TARGET_HANDS = 581021901
MAX_OVERSHOOT = 50000
ASSIGNMENT_TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
ASSIGNMENT_SEED = 2026072301
POOL_ORDER = [109, 115, 120, 129, 81]
POOL_HASHES = {
    81: "fd3aec2b32bcc7900eaf255c3ecda8c5cb8dd6339d6ba6551bba07decc91a145",
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
}
WEIGHTS = {81: 0.2, 109: 0.2, 115: 0.2, 120: 0.2, 129: 0.2}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_dict_sha256(state_dict: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def canonical_record_sha256(row: dict[str, Any]) -> str:
    payload = dict(row)
    payload.pop("record_sha256", None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def expected_assignment(iteration: int) -> dict[str, Any]:
    payload = f"LG003_ASSIGNMENT_V1|{ASSIGNMENT_TOKEN}|{ASSIGNMENT_SEED}|{iteration}"
    u64 = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
    unit = u64 / float(1 << 64)
    member = None
    local_index = -1
    conditional = None
    if unit >= 0.2:
        conditional = (unit - 0.2) / 0.8
        cumulative = 0.0
        for member_id in sorted(WEIGHTS):
            cumulative += WEIGHTS[member_id]
            if conditional < cumulative:
                member = member_id
                break
        if member is None:
            member = max(WEIGHTS)
        local_index = POOL_ORDER.index(member)
    return {
        "u64": u64, "unit_interval": unit, "conditional_unit_interval": conditional,
        "selected_kind": "self_play" if member is None else "pool_snapshot",
        "selected_local_index": local_index, "selected_member_id": member,
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def tensors_finite(value: Any) -> bool:
    if isinstance(value, torch.Tensor):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(tensors_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(tensors_finite(item) for item in value)
    return True


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--stderr-log", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_root = Path(args.run_root).resolve()
    stdout_log, stderr_log, output = map(Path, (args.stdout_log, args.stderr_log, args.out))
    checkpoint_path = run_root / "latest.pt"
    manifest_path = run_root / "run_manifest.json"
    metrics_path = run_root / "h1_training_metrics.jsonl"
    provenance_path = run_root / "opponent_assignment_provenance.jsonl"
    source_path = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/h11_control_endpoint.pt"
    historical_path = ROOT / "models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_rollback_r1_20260708/v5_mirror_plateau_second_gate20700_340M_checkpoint.pt"
    prereg_path = ROOT / f"reports/v5_lg004_membership_preregistration_{TOKEN}_20260723.json"
    trainer_path = ROOT / f"scripts/alpha_holdem/v5_lg004_train_{TOKEN}.py"
    launcher_path = ROOT / f"scripts/alpha_holdem/v5_lg004_launcher_{TOKEN}.ps1"
    checks: dict[str, bool] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    for path in (checkpoint_path, manifest_path, metrics_path, provenance_path, stdout_log,
                 stderr_log, source_path, historical_path, prereg_path, trainer_path, launcher_path):
        check(f"exists:{path.name}", path.is_file())
    check("source_sha256", sha256_path(source_path) == SOURCE_SHA256)
    check("historical_sha256", sha256_path(historical_path) == HISTORICAL_SHA256)
    check("preregistration_sha256", sha256_path(prereg_path) == PREREG_SHA256)
    check("trainer_sha256", sha256_path(trainer_path) == TRAINER_SHA256)
    check("launcher_sha256", sha256_path(launcher_path) == LAUNCHER_SHA256)
    check("stderr_empty", stderr_log.stat().st_size == 0)
    check("stdout_done", "Done!" in stdout_log.read_text(encoding="utf-8", errors="replace"))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    final_iteration = int(manifest.get("iteration", -1))
    final_hands = int(manifest.get("total_hands", -1))
    expected_rows = final_iteration - SOURCE_ITERATION
    expected_run_id = f"v5_lg004_treatment_membership_stagea_{TOKEN}"
    config = manifest.get("config") or {}
    check("manifest_finished", manifest.get("status") == "finished")
    check("manifest_run_id", manifest.get("run_id") == expected_run_id)
    check("manifest_arm", config.get("lg004_arm") == "treatment_membership")
    check("target_reached", TARGET_HANDS <= final_hands <= TARGET_HANDS + MAX_OVERSHOOT)
    check("increment_at_least_5m", final_hands - SOURCE_HANDS >= 5_000_000)
    check("positive_iteration_count", expected_rows > 0)
    expected_config = {
        "workers": 22, "hands_per_iter": 16384, "starting_stack": 200.0,
        "env_version": "v55", "lr": 0.0003, "ppo_epochs": 4,
        "ppo_target_kl": 0.03, "mini_batch_size": 1024, "gamma": 0.999,
        "entropy_coef": 0.05, "entropy_floor": 0.3, "self_play_fraction": 0.2,
        "opponent_assignment": "per-iteration", "worker_seed_base": 73000,
        "seed": 20260703, "critic_contract": "critic_v1", "value_coef": 0.5,
    }
    check("common_config_exact", all(config.get(key) == value for key, value in expected_config.items()))
    check("retained_boolean_contract", all(config.get(key) is True for key in (
        "fixed_training_deal_stream", "mirror_self_play_deals", "allin_runout_ev",
        "h8_value_head_catchup_after_kl_stop",
    )))

    metrics, provenance = read_jsonl(metrics_path), read_jsonl(provenance_path)
    check("metrics_row_count", len(metrics) == expected_rows)
    check("provenance_row_count", len(provenance) == expected_rows)
    expected_iterations = list(range(SOURCE_ITERATION + 1, final_iteration + 1))
    check("metrics_iteration_sequence", [int(row["iteration"]) for row in metrics] == expected_iterations)
    hands = [int(row["hands"]) for row in metrics]
    check("metrics_hands_strict", all(b > a for a, b in zip([SOURCE_HANDS, *hands[:-1]], hands)))
    check("metrics_final_hands", bool(hands) and hands[-1] == final_hands)
    check("metrics_finite", all(
        math.isfinite(float(value)) for row in metrics for value in row.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ))

    previous = None
    provenance_ok = True
    refs_ok = True
    selections: Counter[str] = Counter()
    for iteration, row in zip(expected_iterations, provenance, strict=True):
        lg = row.get("lg004") or {}
        expected = expected_assignment(iteration)
        provenance_ok &= int(row.get("applies_to_iteration", -1)) == iteration
        provenance_ok &= row.get("previous_record_sha256") == previous
        provenance_ok &= row.get("record_sha256") == canonical_record_sha256(row)
        provenance_ok &= lg.get("registration_token") == TOKEN
        provenance_ok &= lg.get("registration_sha256") == PREREG_SHA256
        provenance_ok &= lg.get("assignment_rule") == "LG003_ASSIGNMENT_V1"
        provenance_ok &= int(lg.get("assignment_seed", -1)) == ASSIGNMENT_SEED
        provenance_ok &= lg.get("conditional_weights_by_member_id") == {str(k): v for k, v in sorted(WEIGHTS.items())}
        for key, expected_value in expected.items():
            actual = lg.get(key)
            if isinstance(expected_value, float):
                provenance_ok &= math.isclose(float(actual), expected_value, rel_tol=0, abs_tol=1e-15)
            else:
                provenance_ok &= actual == expected_value
        refs = row.get("pool_snapshot_refs") or []
        refs_ok &= [int(ref.get("snapshot_id", -1)) for ref in refs] == POOL_ORDER
        selections[str(lg.get("selected_member_id"))] += 1
        previous = row.get("record_sha256")
    check("provenance_chain_and_selector", provenance_ok)
    check("provenance_pool_refs", refs_ok)
    check("all_expected_selection_classes_observed", set(selections) == {"None", "81", "109", "115", "120", "129"})

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    check("checkpoint_iteration", int(checkpoint.get("iteration", -1)) == final_iteration)
    check("checkpoint_hands", int(checkpoint.get("total_hands", -1)) == final_hands)
    check("checkpoint_run_id", checkpoint.get("run_id") == expected_run_id)
    lg = checkpoint.get("lg004") or {}
    check("checkpoint_lg004_arm", lg.get("arm") == "treatment_membership")
    check("checkpoint_lg004_registration", lg.get("registration_sha256") == PREREG_SHA256)
    check("checkpoint_lg004_source", lg.get("source_checkpoint_sha256") == SOURCE_SHA256)
    check("checkpoint_provenance_tail", lg.get("assignment_provenance_tail_sha256") == previous)
    pool_rows = checkpoint.get("pool_snapshots") or []
    check("checkpoint_pool_order", [int(row.get("id", -1)) for row in pool_rows] == POOL_ORDER)
    observed_hashes = {int(row["id"]): state_dict_sha256(row["state_dict"]) for row in pool_rows}
    check("checkpoint_pool_hashes", observed_hashes == POOL_HASHES)
    check("checkpoint_all_tensors_finite", tensors_finite(checkpoint.get("model")) and tensors_finite(checkpoint.get("optimizer")))
    check("checkpoint_snapshot_addition_disabled", len(pool_rows) == 5 and 103 not in observed_hashes)

    artifacts = {
        str(path): {"sha256": sha256_path(path), "bytes": path.stat().st_size}
        for path in (checkpoint_path, manifest_path, metrics_path, provenance_path, stdout_log, stderr_log)
    }
    failed = sorted(name for name, value in checks.items() if not value)
    report = {
        "schema_version": "v5.lg004.window_audit.v1",
        "classification": "LG004_STAGE_A_TREATMENT_WINDOW_AUDIT_PASS" if not failed else "LG004_STAGE_A_TREATMENT_WINDOW_AUDIT_FAIL_CLOSED",
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks": checks, "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "checks_failed": failed, "measurements": {
            "source_hands": SOURCE_HANDS, "final_hands": final_hands,
            "new_hands": final_hands - SOURCE_HANDS, "iterations": expected_rows,
            "metrics_rows": len(metrics), "provenance_rows": len(provenance),
            "selection_counts": dict(selections), "checkpoint_sha256": sha256_path(checkpoint_path),
            "pool_state_sha256": {str(k): v for k, v in sorted(observed_hashes.items())},
            "provenance_tail_sha256": previous,
        },
        "artifacts": artifacts,
        "authority": {
            "checkpoint_external_evaluation_eligible": not failed,
            "mandatory_next_if_pass": "ONE_REGISTERED_GREEDY_DIRECT_4X1250_QUICK5K",
            "strength_claim": "FORBIDDEN",
        },
    }
    write_json(output, report)
    print(json.dumps({"overall": report["overall"], "checks": f"{report['checks_passed']}/{report['checks_total']}",
                      "checkpoint_sha256": report["measurements"]["checkpoint_sha256"], "out": str(output)}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
