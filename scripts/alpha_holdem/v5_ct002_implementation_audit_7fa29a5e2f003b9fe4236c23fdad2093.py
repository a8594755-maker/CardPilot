"""Independent implementation audit for the registered CT002 corrected bundle."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "7fa29a5e2f003b9fe4236c23fdad2093"
IDENTITY_SHA256 = "7fa29a5e2f003b9fe4236c23fdad20933388345b669b982437c570437cb480f1"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
PREREGISTRATION = ROOT / "reports" / f"v5_ct002_corrected_preregistration_{TOKEN}_20260722.json"
PREREGISTRATION_SHA256 = "4c21f92dc37b668a57e850a07ab279ebe90f3115b22b7aff48f66b8f674ac1b2"
PREREGISTRATION_AUDIT = ROOT / "reports" / f"v5_ct002_corrected_preregistration_audit_{TOKEN}_20260722.json"
PREREGISTRATION_AUDIT_SHA256 = "7dc738ce349008fee8f08b79ffc3c094b314ed1f2280f70a62a6f93755b4233a"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_ct002_runner_{TOKEN}.py"
TEST = ROOT / "scripts" / "alpha_holdem" / f"test_v5_ct002_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_ct002_launcher_{TOKEN}.ps1"
AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_ct002_implementation_audit_{TOKEN}.py"
RESULT = ROOT / "reports" / f"v5_ct002_implementation_audit_result_{TOKEN}_20260722.json"
OUTPUT_ROOT = ROOT / "models" / "alpha_holdem_v5_hybrid" / f"v5_ct002_{TOKEN}_20260722"
EXPECTED_IMPLEMENTATION_HASHES = {
    RUNNER: "1a2ade05051eb4fd1ac3a5bec0e5e151dc1ccdf19a8fe8bdd6977ce6d5f81fd5",
    TEST: "4eeb6e4b9904130b1a4a1886c7636d3ba9afe0b013396776a27762f592c5b2f5",
}
PROBES = (
    ("control_selfplay_calibration", 2026972214),
    ("treatment_opponent_mix_calibration", 2027972214),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def workspace_snapshot() -> dict[str, tuple[int, int]]:
    result = {}
    for directory, names, files in os.walk(ROOT):
        names[:] = [name for name in names if name not in {".git"}]
        for filename in files:
            path = Path(directory) / filename
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            result[str(path.relative_to(ROOT)).lower()] = (int(stat.st_size), int(stat.st_mtime_ns))
    return result


def main() -> int:
    checks: list[dict] = []
    probe_results: list[dict] = []

    def check(check_id: str, passed: bool, detail: object) -> bool:
        checks.append({"id": check_id, "pass": bool(passed), "detail": detail})
        return bool(passed)

    def safe_hash_check(check_id: str, path: Path, wanted: str, wanted_bytes: int | None = None) -> bool:
        try:
            observed_hash = sha256_file(path)
            observed_bytes = path.stat().st_size
            passed = observed_hash == wanted and (wanted_bytes is None or observed_bytes == wanted_bytes)
            return check(check_id, passed, {
                "path": str(path), "sha256": observed_hash, "bytes": observed_bytes,
                "expected_sha256": wanted, "expected_bytes": wanted_bytes,
            })
        except Exception as exc:
            return check(check_id, False, {"path": str(path), "error": f"{type(exc).__name__}: {exc}"})

    if RESULT.exists():
        raise RuntimeError("registered implementation audit result already exists")
    check("result_absent_before_audit", not RESULT.exists(), str(RESULT))
    check("output_root_absent_before_audit", not OUTPUT_ROOT.exists(), str(OUTPUT_ROOT))
    safe_hash_check("python_runtime_exact", PYTHON, PYTHON_SHA256)
    safe_hash_check("preregistration_exact", PREREGISTRATION, PREREGISTRATION_SHA256)
    safe_hash_check("preimplementation_audit_exact", PREREGISTRATION_AUDIT, PREREGISTRATION_AUDIT_SHA256)

    registration = load_json(PREREGISTRATION)
    preaudit = load_json(PREREGISTRATION_AUDIT)
    basis = registration["identity"]["basis"]
    derived_identity = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    check("identity_basis_rederived", derived_identity == IDENTITY_SHA256, derived_identity)
    check("identity_token_rederived", derived_identity[:32] == TOKEN, derived_identity[:32])
    check("preimplementation_audit_pass70", preaudit.get("pass_count") == 70 and preaudit.get("fail_count") == 0,
          {"pass_count": preaudit.get("pass_count"), "fail_count": preaudit.get("fail_count")})
    check("implementation_now_authorized_later", preaudit.get("authority", {}).get("next_implementation") == "ONE_NEW_CLEAN_ROOM_BUNDLE_LATER_ONLY",
          preaudit.get("authority"))

    authority_inputs = registration["frozen_authority_inputs"]
    check("authority_input_count_10", len(authority_inputs) == 10, len(authority_inputs))
    authority_ok = True
    for index, item in enumerate(authority_inputs):
        authority_ok &= safe_hash_check(
            f"authority_input_{index:02d}_{item['role']}", Path(item["path"]), item["sha256"], int(item["bytes"])
        )
    check("authority_inputs_all_exact", authority_ok, "10/10 expected")

    canonical_registration = next(item for item in authority_inputs if item["role"] == "canonical_scientific_preregistration")
    canonical_payload = load_json(Path(canonical_registration["path"]))
    transitive_inputs = list(canonical_payload["frozen_inputs"]) + list(canonical_payload["evaluation_tools"])
    check("transitive_scientific_input_count_28", len(transitive_inputs) == 28, len(transitive_inputs))
    transitive_ok = True
    for index, item in enumerate(transitive_inputs):
        transitive_ok &= safe_hash_check(
            f"transitive_input_{index:02d}_{item['role'] if 'role' in item else Path(item['path']).stem}",
            Path(item["path"]), item["sha256"], int(item["bytes"]),
        )
    check("transitive_scientific_inputs_all_exact", transitive_ok, "28/28 expected")

    canonical_audit_item = next(item for item in authority_inputs if item["role"] == "canonical_scientific_preregistration_audit")
    canonical_audit = load_json(Path(canonical_audit_item["path"]))
    check("canonical_scientific_audit_pass52", canonical_audit.get("pass_count") == 52 and canonical_audit.get("fail_count") == 0,
          {"pass_count": canonical_audit.get("pass_count"), "fail_count": canonical_audit.get("fail_count")})
    check("scientific_identity_preserved", registration["scientific_design_lock"]["inheritance_rule"].startswith("EVERY_SCIENTIFIC_FIELD_IS_EXACTLY_INHERITED"),
          registration["scientific_design_lock"]["inheritance_rule"])
    check("fresh_override_allowlist_exact", registration["fresh_realization_overrides"]["allowed_override_class"] ==
          "IDENTITY_PATH_SEED_AND_PROBE_NONCE_ONLY_NO_SCIENTIFIC_THRESHOLD_BUDGET_ALGORITHM_OR_MODEL_CHANGE",
          registration["fresh_realization_overrides"]["allowed_override_class"])

    for path, wanted in EXPECTED_IMPLEMENTATION_HASHES.items():
        safe_hash_check(f"implementation_hash_{path.stem}", path, wanted)
    check("launcher_exists", LAUNCHER.is_file(), str(LAUNCHER))
    check("auditor_exists", AUDITOR.is_file(), str(AUDITOR))
    check("registered_implementation_paths_exact", {
        "runner": str(RUNNER), "test": str(TEST), "launcher": str(LAUNCHER), "auditor": str(AUDITOR)
    } == {
        "runner": registration["new_absolute_paths"]["future_runner"],
        "test": registration["new_absolute_paths"]["future_test"],
        "launcher": registration["new_absolute_paths"]["future_launcher"],
        "auditor": registration["new_absolute_paths"]["future_implementation_auditor"],
    }, registration["new_absolute_paths"])

    runner_source = RUNNER.read_text(encoding="utf-8")
    test_source = TEST.read_text(encoding="utf-8")
    launcher_source = LAUNCHER.read_text(encoding="utf-8")
    auditor_source = AUDITOR.read_text(encoding="utf-8")
    for label, source in (("runner", runner_source), ("test", test_source), ("auditor", auditor_source)):
        try:
            ast.parse(source)
            check(f"ast_parse_{label}", True, "PASS")
        except SyntaxError as exc:
            check(f"ast_parse_{label}", False, str(exc))
    check("runner_forbidden_train_v5_absent", "train_v5.py" not in runner_source, "exact forbidden filename")
    check("runner_forbidden_parent_token_absent", "ae78e683c41a2abcff33eeae9fdad8ad" not in runner_source, "terminal parent token")
    check("runner_forbidden_league_descendants_absent", "lg001" not in runner_source.lower() and "lg002" not in runner_source.lower(),
          "forbidden descendant names")
    check("runner_only_approved_local_import", "alpha_holdem.train_v5_hybrid_h1" in runner_source and
          "alpha_holdem.network_hybrid_h1" in runner_source and "alpha_holdem.environment_v55" in runner_source,
          "three directly imported approved modules; PPO math is reached through approved trainer binding")
    check("runner_registered_seed_constants", all(fragment in runner_source for fragment in (
        "DEAL_SEED = 2026072214", "ACTION_SEED = 2026072215", "SHUFFLE_SEED = 2026072216",
        "TRAINING_SEED = 2026072217", "WORKER_SEED_BASE = 84000")), "five fresh realization seeds")
    check("runner_exact_counts", all(fragment in runner_source for fragment in (
        "TRAIN_ROWS = 250_000", "HELDOUT_ROWS = 50_000", "PPO_TARGET_HANDS = 581_021_901",
        "for epoch in range(4)", "range(0, TRAIN_ROWS, 1000)")), "rows, updates and PPO endpoint")
    check("runner_actor_freeze_gates", all(fragment in runner_source for fragment in (
        "source_non_value_hash", "4096", "policy-logit bitwise identity gate failed", "parameter.requires_grad_(name in VALUE_NAMES)")),
          "non-value state plus 4096 logits")
    check("runner_optimizer_transform_gate", "SOURCE_EXACT_ZERO_VALUE_HEAD_EXP_AVG_AND_EXP_AVG_SQ_ONLY" in runner_source,
          "source optimizer restored and value moments zeroed")
    check("runner_mechanism_thresholds", all(fragment in runner_source for fragment in (
        "opponent_ratio <= 0.90", "selfplay_ratio <= 1.10", "combined_ratio <= 0.98")), "0.90/1.10/0.98")
    check("runner_assignment_stream", "CT002_PPO_ASSIGNMENT_V1" in runner_source and "SOURCE_ITERATION + 1" in runner_source,
          "absolute-iteration SHA256 schedule")
    check("runner_target_kl_and_catchup", all(fragment in runner_source for fragment in (
        "PPO_TARGET_KL = 0.03", 'kwargs["value_head_catchup"] = True', 'kwargs["value_head_catchup_loss"] = "mse"')),
          "target KL .03, catch-up true, MSE")
    check("runner_pool_mutation_disabled", '"--snapshot-every", "1000000000"' in runner_source,
          "no snapshot addition within registered Stage-A window")
    check("probe_function_write_free_static", not any(fragment in ast.get_source_segment(runner_source, node) or ""
          for node in ast.walk(ast.parse(runner_source)) if isinstance(node, ast.FunctionDef) and node.name == "contract_probe"
          for fragment in ("mkdir(", "open(", "write_text(", "write_bytes(", "torch.save(")), "AST source segment")
    check("launcher_absolute_python", str(PYTHON) in launcher_source, str(PYTHON))
    check("launcher_runner_hash_exact", EXPECTED_IMPLEMENTATION_HASHES[RUNNER] in launcher_source, EXPECTED_IMPLEMENTATION_HASHES[RUNNER])
    check("launcher_cpu_contract", all(fragment in launcher_source for fragment in (
        "$env:CUDA_VISIBLE_DEVICES = '-1'", "$env:CT002_DEVICE_MODE = 'CPU_ONLY_NO_GPU_NO_OUTPUT'", "CT002_PROBE_NONCE")),
          "parent-to-child CPU device/token/nonce")
    check("launcher_gpu_contract", all(fragment in launcher_source for fragment in (
        "$env:CUDA_VISIBLE_DEVICES = '0'", "$env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'")),
          "single GPU, sequential, no fallback")
    check("launcher_bytecode_write_disabled", "@('-B', $Runner" in launcher_source, "python -B")

    compile_result = subprocess.run(
        [str(PYTHON), "-B", "-m", "py_compile", str(RUNNER), str(TEST), str(AUDITOR)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    check("python_compile", compile_result.returncode == 0,
          {"returncode": compile_result.returncode, "stdout": compile_result.stdout[-2000:], "stderr": compile_result.stderr[-2000:]})

    powershell_parse = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$null,[ref]$e)|Out-Null; "
         "if($e.Count -ne 0){$e|ForEach-Object{$_.ToString()}; exit 1}", str(LAUNCHER)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    check("powershell_parse", powershell_parse.returncode == 0,
          {"returncode": powershell_parse.returncode, "stdout": powershell_parse.stdout, "stderr": powershell_parse.stderr})

    test_result = subprocess.run(
        [str(PYTHON), "-B", str(TEST)], cwd=ROOT, capture_output=True, text=True, timeout=180,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    check("unit_tests_11_of_11", test_result.returncode == 0 and "Ran 11 tests" in test_result.stderr and "OK" in test_result.stderr,
          {"returncode": test_result.returncode, "stdout": test_result.stdout[-4000:], "stderr": test_result.stderr[-8000:]})

    preprobe_pass = all(item["pass"] for item in checks)
    check("preprobe_static_gate", preprobe_pass, f"{sum(item['pass'] for item in checks)}/{len(checks)}")
    if preprobe_pass:
        for arm, nonce in PROBES:
            before = workspace_snapshot()
            probe = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(LAUNCHER), "-Operation", "Probe", "-Arm", arm],
                cwd=ROOT, capture_output=True, text=True, timeout=180,
            )
            after = workspace_snapshot()
            lines = [line.strip() for line in probe.stdout.splitlines() if line.strip()]
            try:
                payload = json.loads(lines[-1]) if lines else {}
            except json.JSONDecodeError:
                payload = {}
            probe_ok = (
                probe.returncode == 0
                and len(lines) == 1
                and payload.get("status") == "PASS"
                and payload.get("identity_sha256") == IDENTITY_SHA256
                and payload.get("token") == TOKEN
                and payload.get("arm") == arm
                and payload.get("nonce") == nonce
                and payload.get("device_mode") == "CPU_ONLY_NO_GPU_NO_OUTPUT"
                and payload.get("cuda_visible_devices") == "-1"
                and payload.get("torch_cuda_available") is False
                and payload.get("files_written") == 0
            )
            check(f"probe_{arm}_child_contract", probe_ok, {
                "returncode": probe.returncode, "stdout": probe.stdout[-4000:], "stderr": probe.stderr[-4000:], "payload": payload,
            })
            changed = {
                key: {"before": before.get(key), "after": after.get(key)}
                for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)
            }
            check(f"probe_{arm}_workspace_zero_files", not changed, changed)
            check(f"probe_{arm}_output_absent", not OUTPUT_ROOT.exists(), str(OUTPUT_ROOT))
            check(f"probe_{arm}_audit_result_absent", not RESULT.exists(), str(RESULT))
            probe_results.append(payload)
    else:
        check("two_probe_execution", False, "skipped because preprobe static gate failed")

    check("exactly_two_fresh_probes", len(probe_results) == 2, len(probe_results))
    check("probe_nonces_exact_and_distinct", [item.get("nonce") for item in probe_results] == [item[1] for item in PROBES],
          [item.get("nonce") for item in probe_results])
    check("zero_data_training_gpu_checkpoint_evaluation_slumbot", not OUTPUT_ROOT.exists(),
          {"output_root_absent": not OUTPUT_ROOT.exists(), "data_rows": 0, "training_hands": 0, "slumbot_hands": 0})

    passed = all(item["pass"] for item in checks)
    implementation_hashes = {}
    for path in (RUNNER, TEST, LAUNCHER, AUDITOR):
        implementation_hashes[str(path)] = {
            "sha256": sha256_file(path), "bytes": path.stat().st_size,
        }
    result = {
        "schema_version": "v5.ct002.corrected_implementation_audit.v1",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "identity_sha256": IDENTITY_SHA256,
        "token": TOKEN,
        "registration_sha256": PREREGISTRATION_SHA256,
        "preimplementation_audit_sha256": PREREGISTRATION_AUDIT_SHA256,
        "classification": "PASS_CT002_CORRECTED_IMPLEMENTATION_AND_TWO_ZERO_OUTPUT_PROBES_DATA_GENERATION_READY_LATER_ONLY"
                          if passed else "FAIL_CLOSED_CT002_CORRECTED_IMPLEMENTATION_OR_PROBE_GATE",
        "implementation_files": implementation_hashes,
        "probe_results": probe_results,
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(item["pass"] for item in checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "authority": {
            "implementation": "FROZEN" if passed else "NONE",
            "data_generation": "ONE_SEPARATELY_LAUNCHED_GPU_ATTEMPT_LATER_ONLY" if passed else "NONE",
            "calibration": "NONE_THIS_BOUNDARY",
            "ppo": "NONE_THIS_BOUNDARY",
            "gpu": "NONE_THIS_BOUNDARY",
            "checkpoint": "NONE_THIS_BOUNDARY",
            "evaluation": "NONE",
            "slumbot": "NONE",
            "strength": "L0",
        },
        "route_exhausted": False,
        "official_hands": 0,
        "terminal_stop": "STOP_BEFORE_DATA_GENERATION_CALIBRATION_PPO_GPU_CHECKPOINT_EVALUATION_OR_SLUMBOT",
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({
        "result": str(RESULT), "sha256": sha256_file(RESULT), "classification": result["classification"],
        "pass_count": result["pass_count"], "check_count": result["check_count"],
    }, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise
