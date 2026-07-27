"""Independent RS002 implementation audit and exactly-two probe owner."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "81b61579f99755eb755d8c3c1905c22f"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_{TOKEN}_20260722.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_audit_{TOKEN}_20260722.json"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs002_paired_mc32_lcb95_resolver_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs002_paired_mc32_lcb95_resolver_launcher_{TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs002_paired_mc32_lcb95_resolver_audit_{TOKEN}.py"
IMPLEMENTATION_AUDITOR = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_implementation_audit_{TOKEN}_20260722.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_qualification_{TOKEN}_20260722"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs002_{TOKEN}_greedy_quick5k_20260722"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
PREREG_SHA256 = "93316de07812e6801cd6c83ddb7082b21841b981115a11c42ec3215c6b4563c7"
PREREG_AUDIT_SHA256 = "e346a5b56ed4b5dd7239e6726ed2f5082d9e7a8e711cf26f2bd14e85661ea4bd"
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
PROBE_NONCES = ["RS002_PROBE_A_2034972294", "RS002_PROBE_B_2035972294"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)


def parse_last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_json_output_missing")


def token_scope_snapshot() -> dict[str, Any]:
    paths: list[Path] = []
    for base in (ROOT / "reports", ROOT / "scripts" / "alpha_holdem", ROOT / "models"):
        if not base.exists():
            continue
        for path in base.rglob(f"*{TOKEN}*"):
            if path.is_file() and path.resolve() != RESULT.resolve():
                paths.append(path)
    unique = sorted(set(paths), key=lambda path: str(path).lower())
    return {
        "files": {
            str(path.resolve()): {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in unique
        },
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "implementation_audit_result_exists": RESULT.exists(),
        "checkpoint_sha256": sha256_file(CHECKPOINT),
    }


def static_checks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    check("prereg_hash_exact", PREREG.is_file() and PREREG.stat().st_size == 20952 and sha256_file(PREREG) == PREREG_SHA256)
    check("prereg_audit_hash_exact", PREREG_AUDIT.is_file() and PREREG_AUDIT.stat().st_size == 10135 and sha256_file(PREREG_AUDIT) == PREREG_AUDIT_SHA256)
    check("python_hash_exact", PYTHON.is_file() and sha256_file(PYTHON) == PYTHON_SHA256)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    input_failures: list[str] = []
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha256_file(path) != item["sha256"]:
            input_failures.append(item["role"])
    check("all19_frozen_inputs_exact", len(prereg["frozen_authority_inputs"]) == 19 and not input_failures, input_failures)
    check("checkpoint_hash_exact", sha256_file(CHECKPOINT) == CHECKPOINT_SHA256)
    bound_files = [RUNNER, LAUNCHER, RESULT_AUDITOR, IMPLEMENTATION_AUDITOR]
    check("four_bound_files_present", all(path.is_file() for path in bound_files), [str(path) for path in bound_files])
    syntax_failures: list[str] = []
    for path in (RUNNER, RESULT_AUDITOR, IMPLEMENTATION_AUDITOR):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_failures.append(f"{path.name}:{exc}")
    check("python_ast_3_of_3", not syntax_failures, syntax_failures)
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    parse_script = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{str(LAUNCHER).replace("'", "''")}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count -gt 0){$errors|ForEach-Object{$_.ToString()};exit 1}else{'POWERSHELL_PARSE_PASS'}"
    )
    ps_parse = subprocess.run(["powershell.exe", "-NoProfile", "-Command", parse_script], capture_output=True, text=True, timeout=60)
    check("powershell_parse_pass", ps_parse.returncode == 0 and "POWERSHELL_PARSE_PASS" in ps_parse.stdout, {"stdout": ps_parse.stdout, "stderr": ps_parse.stderr})
    runner_text = RUNNER.read_text(encoding="utf-8")
    markers = [
        "PAIRED_MC32_LCB95_ROOT_RESOLVER",
        "itertools.combinations",
        "MC_SAMPLES = 32",
        "LCB_Z = 1.6448536269514722",
        "common_determinizations_across_root_actions",
        "POSITIVE_PAIRED_LCB95",
        "LCB_NO_CHANGE",
        "ROLLOUT_MAX_ACTIONS = 128",
        "H11Actor",
        "build_determinizations",
        "rollout_root_actions",
        "paired_statistics",
        "generate_synthetic_interface_states",
        "load_witness_states",
        "network_or_slumbot_calls\": 0",
    ]
    missing_markers = [marker for marker in markers if marker not in runner_text]
    check("runner_science_markers_complete", not missing_markers, missing_markers)
    check("runner_no_slumbot_http_call", "requests.post" not in runner_text and "slumbot.com" not in runner_text)
    check("result_auditor_independent", "import v5_rs002" not in RESULT_AUDITOR.read_text(encoding="utf-8"))
    launcher_markers = [str(PYTHON), str(RUNNER), str(RESULT_AUDITOR), str(RESULT), str(QUAL_ROOT), "CUDA_VISIBLE_DEVICES = '0'", "PYTHONDONTWRITEBYTECODE = '1'"]
    check("launcher_hardcoded_absolute_boundary", all(marker in launcher_text for marker in launcher_markers), [marker for marker in launcher_markers if marker not in launcher_text])
    check("future_outputs_fresh", not RESULT.exists() and not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists())
    return checks, {"preregistration": prereg, "bound_files": bound_files}


def run_launcher(mode: str, extra: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER), "-Mode", mode, *extra]
    return subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)


def execute() -> tuple[dict[str, Any], bool]:
    started = time.perf_counter()
    checks, context = static_checks()

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    if not all(item["pass"] for item in checks):
        value = {
            "schema_version": "v5.rs002.implementation_audit.v1",
            "classification": "FAIL_CLOSED / RS002_IMPLEMENTATION_AUDIT_STATIC_PREPROBE_FAILURE_NO_QUALIFICATION",
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "probe_children_launched": 0,
            "qualification_authority": "NONE",
        }
        return value, False
    before_selftest = token_scope_snapshot()
    selftest = run_launcher("SelfTest", ["-Level", "deep"], 1800)
    after_selftest = token_scope_snapshot()
    selftest_json: dict[str, Any] | None = None
    try:
        selftest_json = parse_last_json(selftest.stdout)
    except Exception:
        pass
    check("deep_selftest_exit0", selftest.returncode == 0, {"stdout": selftest.stdout[-8000:], "stderr": selftest.stderr[-8000:]})
    check("deep_selftest_pass_contract", isinstance(selftest_json, dict) and selftest_json.get("classification") == "PASS_RS002_SELF_TEST" and selftest_json.get("level") == "deep" and selftest_json.get("files_written") == 0, selftest_json)
    check("deep_selftest_zero_scope_diff", before_selftest == after_selftest)
    if not all(item["pass"] for item in checks):
        value = {
            "schema_version": "v5.rs002.implementation_audit.v1",
            "classification": "FAIL_CLOSED / RS002_IMPLEMENTATION_AUDIT_SELFTEST_PREPROBE_FAILURE_NO_QUALIFICATION",
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "probe_children_launched": 0,
            "qualification_authority": "NONE",
        }
        return value, False
    probe_before = token_scope_snapshot()
    probe_results: list[dict[str, Any]] = []
    for nonce in PROBE_NONCES:
        child = run_launcher("ContractProbe", ["-Nonce", nonce], 300)
        parsed: dict[str, Any] | None = None
        try:
            parsed = parse_last_json(child.stdout)
        except Exception:
            pass
        probe_results.append({
            "nonce": nonce,
            "exit_code": child.returncode,
            "stdout": child.stdout,
            "stderr": child.stderr,
            "parsed": parsed,
        })
    probe_after = token_scope_snapshot()
    check("exactly_two_probe_children", len(probe_results) == 2)
    check("probe_nonces_exact_order", [item["nonce"] for item in probe_results] == PROBE_NONCES)
    check("both_probes_exit0", all(item["exit_code"] == 0 for item in probe_results), [item["exit_code"] for item in probe_results])
    check("both_probes_contract_exact", all(
        isinstance(item["parsed"], dict)
        and item["parsed"].get("classification") == "PASS_ZERO_FILE_CONTRACT_PROBE"
        and item["parsed"].get("files_written") == 0
        and item["parsed"].get("authority_inputs_exact") == 19
        and item["parsed"].get("device", {}).get("nonce") == item["nonce"]
        and item["parsed"].get("device", {}).get("device_name") == "NVIDIA_GEFORCE_RTX_4070"
        and item["parsed"].get("device", {}).get("device_total_mib") == 12282
        for item in probe_results
    ), [item["parsed"] for item in probe_results])
    check("probe_scope_zero_diff", probe_before == probe_after)
    check("checkpoint_unchanged_after_probes", probe_after["checkpoint_sha256"] == CHECKPOINT_SHA256)
    check("qualification_and_quick5k_still_absent", not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists())
    implementation_hashes = {
        "runner": {"path": str(RUNNER), "bytes": RUNNER.stat().st_size, "sha256": sha256_file(RUNNER)},
        "launcher": {"path": str(LAUNCHER), "bytes": LAUNCHER.stat().st_size, "sha256": sha256_file(LAUNCHER)},
        "result_auditor": {"path": str(RESULT_AUDITOR), "bytes": RESULT_AUDITOR.stat().st_size, "sha256": sha256_file(RESULT_AUDITOR)},
        "implementation_auditor": {"path": str(IMPLEMENTATION_AUDITOR), "bytes": IMPLEMENTATION_AUDITOR.stat().st_size, "sha256": sha256_file(IMPLEMENTATION_AUDITOR)},
    }
    passed = all(item["pass"] for item in checks)
    value = {
        "schema_version": "v5.rs002.implementation_audit.v1",
        "classification": "PASS / RS002_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY" if passed else "FAIL_CLOSED / RS002_IMPLEMENTATION_AUDIT_FAILURE_NO_QUALIFICATION",
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "program_id": "RS002_PAIRED_MC32_LCB95_ROOT_RESOLVER",
        "token": TOKEN,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "implementation_files": implementation_hashes,
        "deep_selftest": selftest_json,
        "probe_results": probe_results,
        "probe_children_launched": len(probe_results),
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(item["pass"] for item in checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "wall_seconds": time.perf_counter() - started,
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "checkpoint_sha256_after": sha256_file(CHECKPOINT),
        "qualification_authority": "EXACTLY_ONE_LAUNCH_THROUGH_BOUND_LAUNCHER" if passed else "NONE",
        "quick5k_authority": "NONE_UNTIL_QUALIFICATION_AND_RESULT_AUDIT_PASS",
    }
    return value, passed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("Preflight", "Execute"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "Preflight":
        checks, _ = static_checks()
        passed = all(item["pass"] for item in checks)
        print(canonical_json({"classification": "PASS_PREPROBE_PREFLIGHT" if passed else "FAIL_PREPROBE_PREFLIGHT", "checks": checks, "files_written": 0, "probe_children_launched": 0}))
        return 0 if passed else 1
    if RESULT.exists():
        raise RuntimeError("implementation_audit_result_already_exists")
    value, passed = execute()
    write_exclusive(RESULT, value)
    print(canonical_json({"classification": value["classification"], "pass_count": value.get("pass_count", 0), "check_count": value.get("check_count", 0), "probe_children_launched": value.get("probe_children_launched", 0)}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
