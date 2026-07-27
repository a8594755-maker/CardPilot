#!/usr/bin/env python3
"""Independent implementation auditor for canonical CT002 ae78.

The auditor never imports the candidate runner. It rehashes registered evidence,
parses candidate source, runs the no-output unit tests, and invokes exactly two
fresh launcher-bound CPU contract probes before writing one immutable audit result.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "ae78e683c41a2abcff33eeae9fdad8ad"
PREREG = ROOT / "reports" / f"v5_ct002_preregistration_{TOKEN}_20260722.json"
PREREG_SHA256 = "faef13eff5a57270bc59b43ff3272a3eb6bedf0fe43f0539494a2cd0993072da"
PREREG_AUDIT = ROOT / "reports" / f"v5_ct002_preregistration_audit_{TOKEN}_20260722.json"
PREREG_AUDIT_SHA256 = "2426ca7663d9f347d7884a0e6ebf36831924f110acc316a5326f80fcfa04860e"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_ct002_runner_{TOKEN}.py"
TEST = ROOT / "scripts" / "alpha_holdem" / f"test_v5_ct002_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_ct002_launcher_{TOKEN}.ps1"
AUDITOR = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_ct002_implementation_audit_result_{TOKEN}_20260722.json"
OUTPUT_ROOT = ROOT / "models" / "alpha_holdem_v5_hybrid" / f"v5_ct002_{TOKEN}_20260722"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
SOURCE = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "latest.pt"
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_MODEL_SHA256 = "19bf761296f16758f74bad4bc98192b8954319fcbd2bc3bb174363ea21736b10"
POOL_ORDER = [109, 115, 120, 129, 103]
POOL_HASHES = {
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
}
NONCES = {"control": "2026072213", "treatment": "2026072214"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.resolve(strict=True).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def state_dict_sha256(state_dict: dict[str, Any]) -> str:
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


def write_exclusive(path: Path, payload: Any) -> None:
    with path.resolve(strict=False).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def source_ast(path: Path) -> tuple[ast.AST, str]:
    text = path.read_text(encoding="utf-8")
    return ast.parse(text, filename=str(path)), text


def imports_from(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            result.add(node.module or "")
    return result


def defined_functions_and_classes(tree: ast.AST) -> set[str]:
    return {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def token_file_census() -> dict[str, str]:
    result: dict[str, str] = {}
    for root in (ROOT / "reports", ROOT / "scripts", ROOT / "models"):
        for path in root.rglob(f"*{TOKEN}*"):
            if path.is_file():
                result[str(path.resolve())] = sha256_file(path)
    return result


def parse_last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_stdout_missing_json")


def run_unit_tests() -> dict[str, Any]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [str(PYTHON), "-B", str(TEST)], cwd=ROOT, env=environment,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    payload = parse_last_json(completed.stdout)
    return {
        "exit_code": completed.returncode,
        "stdout_json": payload,
        "stderr": completed.stderr,
    }


def run_contract_probe(arm: str) -> dict[str, Any]:
    before = token_file_census()
    output_before = OUTPUT_ROOT.exists()
    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER), "-Mode", "ContractProbe", "-Arm", arm,
        ],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
    )
    after = token_file_census()
    output_after = OUTPUT_ROOT.exists()
    return {
        "arm": arm, "exit_code": completed.returncode,
        "stdout_json": parse_last_json(completed.stdout),
        "stderr": completed.stderr,
        "token_file_census_unchanged": before == after,
        "output_root_absent_before_after": not output_before and not output_after,
        "files_written_check": "NO_NEW_FILES" if before == after and not output_before and not output_after else "FAIL",
    }


def main() -> int:
    if RESULT.exists():
        raise RuntimeError("immutable_implementation_audit_result_exists")
    if OUTPUT_ROOT.exists():
        raise RuntimeError("registered_output_root_exists_before_implementation_audit")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
        raise RuntimeError("implementation_auditor_requires_cuda_visible_devices_minus_one")
    if sha256_file(PREREG) != PREREG_SHA256 or sha256_file(PREREG_AUDIT) != PREREG_AUDIT_SHA256:
        raise RuntimeError("canonical_registration_hash_mismatch")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))

    runner_tree, runner_text = source_ast(RUNNER)
    test_tree, _ = source_ast(TEST)
    runner_imports = imports_from(runner_tree)
    runner_definitions = defined_functions_and_classes(runner_tree)
    compile(runner_text, str(RUNNER), "exec")
    compile(TEST.read_text(encoding="utf-8"), str(TEST), "exec")
    launcher_text = LAUNCHER.read_text(encoding="utf-8")

    frozen_rehashes = []
    for item in prereg["frozen_inputs"]:
        path = Path(item["path"])
        actual_hash = sha256_file(path)
        actual_bytes = path.stat().st_size
        frozen_rehashes.append({
            "role": item["role"], "sha256": actual_hash, "bytes": actual_bytes,
            "match": actual_hash == item["sha256"] and actual_bytes == int(item["bytes"]),
        })
    evaluation_rehashes = []
    for item in prereg["evaluation_tools"]:
        path = Path(item["path"])
        actual_hash = sha256_file(path)
        actual_bytes = path.stat().st_size
        evaluation_rehashes.append({
            "path": str(path.resolve()), "sha256": actual_hash, "bytes": actual_bytes,
            "match": actual_hash == item["sha256"] and actual_bytes == int(item["bytes"]),
        })

    import torch
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    model_hash = state_dict_sha256(checkpoint.get("model") or {})
    pool_hashes = {int(item["id"]): state_dict_sha256(item["state_dict"]) for item in checkpoint.get("pool_snapshots", [])}

    unit_test = run_unit_tests()
    # These are the sole two contract-probe children for this implementation boundary.
    probes = [run_contract_probe("control"), run_contract_probe("treatment")]

    required_definitions = {
        "deterministic_deck", "action_u64", "inverse_cdf_index", "row_key",
        "calibration_order_key", "ppo_assignment", "inspect_source_checkpoint",
        "collect_split", "materialize_selected_shards", "build_datasets", "calibrate",
        "mechanism_gate", "AssignmentRandomFacade", "run_matched_ppo", "contract_probe",
    }
    checks: dict[str, bool] = {}
    checks["registration_hash"] = sha256_file(PREREG) == PREREG_SHA256
    checks["registration_audit_hash"] = sha256_file(PREREG_AUDIT) == PREREG_AUDIT_SHA256
    checks["registration_audit_pass52"] = prereg_audit.get("classification", "").startswith("PASS / CT002_REGISTERED") and prereg_audit.get("pass_count") == 52
    checks["frozen_inputs_20_of_20"] = len(frozen_rehashes) == 20 and all(item["match"] for item in frozen_rehashes)
    checks["evaluation_tools_8_of_8"] = len(evaluation_rehashes) == 8 and all(item["match"] for item in evaluation_rehashes)
    checks["python_identity"] = Path(sys.executable).resolve() == PYTHON.resolve() and sha256_file(PYTHON) == PYTHON_SHA256
    checks["source_checkpoint_hash"] = sha256_file(SOURCE) == SOURCE_SHA256
    checks["source_checkpoint_metadata"] = checkpoint.get("iteration") == 35051 and checkpoint.get("total_hands") == 576021901
    checks["source_v55_9slot_critic_v1"] = checkpoint.get("env_version") == "v55" and checkpoint.get("action_space_version") == "9slot_v5" and checkpoint.get("critic_contract") == "critic_v1"
    checks["source_optimizer_present"] = isinstance(checkpoint.get("optimizer"), dict) and bool(checkpoint["optimizer"].get("param_groups"))
    checks["source_model_state_hash"] = model_hash == SOURCE_MODEL_SHA256
    checks["source_pool_order"] = [int(item["id"]) for item in checkpoint.get("pool_snapshots", [])] == POOL_ORDER
    checks["source_pool_hashes_5_of_5"] = pool_hashes == POOL_HASHES
    checks["runner_compiles"] = True
    checks["test_compiles"] = True
    checks["runner_required_definitions"] = required_definitions <= runner_definitions
    checks["runner_no_direct_forbidden_train_v5_import"] = "train_v5" not in runner_imports
    checks["runner_no_lg_module_import"] = not any(name.startswith("v5_lg001") or name.startswith("v5_lg002") for name in runner_imports)
    checks["runner_uses_approved_clean_trainer"] = "train_v5_hybrid_h1" in runner_imports
    checks["runner_uses_approved_network_and_environment"] = "alpha_holdem.network_hybrid_h1" in runner_imports and "alpha_holdem.environment_v55" in runner_imports
    checks["runner_no_subprocess_to_forbidden_trainer"] = "subprocess" not in runner_imports and "FORBIDDEN_TRAINER" in runner_text
    checks["single_intervention_literal"] = "CRITIC_ONLY_CALIBRATION_DATA_DISTRIBUTION" in runner_text
    checks["dataset_arithmetic_literals"] = all(value in runner_text for value in ("TRAIN_ROWS = 250_000", "HELDOUT_ROWS = 50_000", "TRAIN_HANDS_PER_ARM = 50_000", "HELDOUT_HANDS_PER_ARM = 10_000"))
    checks["calibration_arithmetic_literals"] = all(value in runner_text for value in ("CALIBRATION_BATCH_SIZE = 1_000", "CALIBRATION_EPOCHS = 4", "CALIBRATION_UPDATES = 1_000"))
    checks["value_head_only_literals"] = all(value in runner_text for value in ("value_head.weight", "value_head.bias", "non_value_state_sha256"))
    checks["mechanism_thresholds"] = all(value in runner_text for value in ("opponent_ratio <= 0.90", "selfplay_ratio <= 1.10", "combined_ratio <= 0.98"))
    checks["stage_a_budget"] = "STAGE_A_TARGET_HANDS = 581_021_901" in runner_text and "STAGE_A_OVERSHOOT_MAX = 50_000" in runner_text
    checks["matched_assignment_facade"] = "CT002_PPO_ASSIGNMENT_V1" in runner_text and "AssignmentRandomFacade" in runner_text
    checks["no_pool_additions"] = '"--snapshot-every", "1000000"' in runner_text
    checks["launcher_absolute_paths"] = all(str(path) in launcher_text for path in (PYTHON, RUNNER, PREREG, PREREG_AUDIT, SOURCE, OUTPUT_ROOT))
    checks["launcher_modes_exact"] = all(mode in launcher_text for mode in ("ContractProbe", "BuildData", "Calibrate", "Mechanism", "Ppo"))
    checks["launcher_cpu_probe_contract"] = "CUDA_VISIBLE_DEVICES = '-1'" in launcher_text and "CPU_ONLY_NO_GPU_NO_OUTPUT" in launcher_text
    checks["launcher_cuda_no_fallback_contract"] = "CUDA_VISIBLE_DEVICES = '0'" in launcher_text and "CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK" in launcher_text
    checks["launcher_requires_implementation_audit_hash_for_execution"] = "ImplementationAuditSha256" in launcher_text and "ObservedAuditSha256" in launcher_text
    checks["unit_tests_pass_10"] = unit_test["exit_code"] == 0 and unit_test["stdout_json"] == {"errors": 0, "failures": 0, "passed": True, "schema_version": "v5.ct002.unit_test.v1", "tests_run": 10}
    checks["unit_test_stderr_only_test_runner"] = "FAILED" not in unit_test["stderr"] and "Traceback" not in unit_test["stderr"]
    checks["exactly_two_contract_probes"] = len(probes) == 2 and [probe["arm"] for probe in probes] == ["control", "treatment"]
    checks["both_probe_exit_zero"] = all(probe["exit_code"] == 0 for probe in probes)
    checks["both_probe_no_files"] = all(probe["files_written_check"] == "NO_NEW_FILES" for probe in probes)
    checks["both_probe_schema_token"] = all(probe["stdout_json"].get("schema_version") == "v5.ct002.contract_probe.v1" and probe["stdout_json"].get("token") == TOKEN for probe in probes)
    checks["both_probe_child_device_contract"] = all(probe["stdout_json"].get("CUDA_VISIBLE_DEVICES") == "-1" and probe["stdout_json"].get("CT002_DEVICE_MODE") == "CPU_ONLY_NO_GPU_NO_OUTPUT" and probe["stdout_json"].get("torch_cuda_available") is False for probe in probes)
    checks["probe_nonces_exact"] = all(probe["stdout_json"].get("nonce") == NONCES[probe["arm"]] == probe["stdout_json"].get("CT002_CONTRACT_NONCE") for probe in probes)
    checks["probe_python_exact"] = all(probe["stdout_json"].get("python_sha256") == PYTHON_SHA256 for probe in probes)
    checks["probe_source_exact"] = all(probe["stdout_json"].get("source", {}).get("model_state_sha256") == SOURCE_MODEL_SHA256 and len(probe["stdout_json"].get("source", {}).get("pool_members", [])) == 5 for probe in probes)
    checks["probe_deterministic_replay_equal"] = probes[0]["stdout_json"].get("deterministic_replay") == probes[1]["stdout_json"].get("deterministic_replay")
    checks["probe_files_written_zero"] = all(probe["stdout_json"].get("files_written") == 0 for probe in probes)
    checks["registered_output_root_absent"] = not OUTPUT_ROOT.exists()
    checks["no_behavior_execution"] = not any((OUTPUT_ROOT / name).exists() for name in ("calibration_data", "control", "treatment", "mechanism_result.json"))
    checks["implementation_result_absent_until_final_write"] = not RESULT.exists()

    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.ct002.implementation_audit.v1",
        "classification": "PASS / CT002_IMPLEMENTATION_AUDIT_PASS_TWO_ZERO_OUTPUT_PROBES_DATA_GENERATION_LATER_ONLY" if not failed else "FAIL_CLOSED / CT002_IMPLEMENTATION_AUDIT_FAILED_NO_EXECUTION",
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "token": TOKEN,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "runner_sha256": sha256_file(RUNNER),
        "test_sha256": sha256_file(TEST),
        "launcher_sha256": sha256_file(LAUNCHER),
        "auditor_sha256": sha256_file(AUDITOR),
        "python_sha256": PYTHON_SHA256,
        "checks": checks,
        "passed_checks": sum(1 for value in checks.values() if value),
        "total_checks": len(checks),
        "failed_checks": failed,
        "frozen_input_rehashes": frozen_rehashes,
        "evaluation_tool_rehashes": evaluation_rehashes,
        "source_checkpoint": {
            "sha256": SOURCE_SHA256, "iteration": checkpoint["iteration"],
            "total_hands": checkpoint["total_hands"], "model_state_sha256": model_hash,
            "pool_order": POOL_ORDER, "pool_state_sha256": pool_hashes,
        },
        "unit_test": unit_test,
        "contract_probes": probes,
        "authority": {
            "implementation": "PASS_IMPLEMENTATION_READY" if not failed else "NONE",
            "data_generation": "LATER_SEPARATE_EXACT_LAUNCH_ONLY" if not failed else "NONE",
            "calibration": "NONE_THIS_BOUNDARY", "ppo": "NONE_THIS_BOUNDARY",
            "gpu": "NONE_THIS_BOUNDARY", "checkpoint": "NONE_THIS_BOUNDARY",
            "evaluation_or_slumbot": "NONE_THIS_BOUNDARY", "official_hands": 0,
            "method_benefit": "UNTESTED", "strength": "L0", "route_exhausted": False,
        },
        "next_later_only": "ONE_EXACT_CANONICAL_AE78_BUILD_DATA_LAUNCH_AFTER_CONTROL_REFRESH_THEN_STOP_AT_IMMUTABLE_DATASET_BUNDLE_AUDIT_BOUNDARY" if not failed else "FREEZE_CT002_IMPLEMENTATION_FAILURE_NO_REPAIR_OR_EXECUTION",
        "terminal_stop": "STOP_BEFORE_DATA_GENERATION_CALIBRATION_PPO_GPU_CHECKPOINT_EVALUATION_OR_SLUMBOT",
    }
    write_exclusive(RESULT, payload)
    print(canonical_json({"overall": payload["overall"], "passed": payload["passed_checks"], "total": payload["total_checks"], "result": str(RESULT), "sha256": sha256_file(RESULT)}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
