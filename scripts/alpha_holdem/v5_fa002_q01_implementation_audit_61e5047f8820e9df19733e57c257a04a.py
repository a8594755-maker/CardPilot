"""Independent prequalification implementation audit for FA002 Q01.

Runs exactly two registered launcher-bound ContractProbe children. The probes and all
in-process scientific self-tests are zero-file; this script prints its audit JSON to
stdout and does not write the eventual immutable audit artifact itself.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

PROJECT = Path(__file__).resolve().parents[2]
PREREG = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_61e5047f8820e9df19733e57c257a04a_20260722.json"
PREREG_AUDIT = PROJECT / "reports" / "v5_fa002_unified_candidate_preregistration_audit_61e5047f8820e9df19733e57c257a04a_20260722.json"
RUNNER = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_61e5047f8820e9df19733e57c257a04a.py"
LAUNCHER = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_launcher_61e5047f8820e9df19733e57c257a04a.ps1"
AUDITOR = PROJECT / "scripts" / "alpha_holdem" / "v5_fa002_q01_audit_61e5047f8820e9df19733e57c257a04a.py"
OUTPUT = PROJECT / "reports" / "v5_fa002_q01_61e5047f8820e9df19733e57c257a04a_20260722"
ASSET_ROOT = PROJECT / "data" / "v5_fa002_teacher_61e5047f8820e9df19733e57c257a04a_20260722"
BC_ROOT = PROJECT / "models" / "alpha_holdem_v5_fa002" / "fa002_bc_61e5047f8820e9df19733e57c257a04a_20260722"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG_SHA256 = "18765838ce043a6f560162770aeeb665eebac6a42b53f580934f6c69d6d849a7"
PREREG_AUDIT_SHA256 = "004090c0ab90388c9e494cf503f572a463fda38eaf65e6a41af886846db6e5f7"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"
PROBE_NONCES = ("FA002_Q01_PROBE_A_2032972233", "FA002_Q01_PROBE_B_2033972233")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).resolve(strict=False).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module_spec_failure:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scoped_snapshot() -> dict[str, tuple[int, int]]:
    records: dict[str, tuple[int, int]] = {}
    for root in (PROJECT / "scripts" / "alpha_holdem", PROJECT / "reports"):
        for path in root.rglob("*"):
            if path.is_file():
                stat = path.stat()
                records[str(path.resolve(strict=False))] = (int(stat.st_size), int(stat.st_mtime_ns))
    for root in (OUTPUT, ASSET_ROOT, BC_ROOT):
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    stat = path.stat()
                    records[str(path.resolve(strict=False))] = (int(stat.st_size), int(stat.st_mtime_ns))
    return records


def relevant_processes() -> list[dict[str, Any]]:
    patterns = ("train_v5", "play_slumbot", "bench_v55", "--mode qualification", "v5_slumbot_benchmark")
    found: list[dict[str, Any]] = []
    for process in psutil.process_iter(("pid", "name", "cmdline")):
        if process.pid == os.getpid():
            continue
        try:
            command = " ".join(process.info.get("cmdline") or []).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "cardpilot" in command and any(pattern in command for pattern in patterns):
            found.append({"pid": process.pid, "name": process.info.get("name"), "command": command})
    return found


def probe(nonce: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], int, int]:
    before = scoped_snapshot()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-Mode",
            "ContractProbe",
            "-ProbeNonce",
            nonce,
        ],
        cwd=str(PROJECT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    after = scoped_snapshot()
    if before != after:
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(path for path in set(before) & set(after) if before[path] != after[path])
        raise RuntimeError(f"probe_filesystem_diff:{nonce}:added={added}:removed={removed}:changed={changed}")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"probe_stdout_line_count:{nonce}:{lines!r}:{completed.stderr!r}")
    payload = json.loads(lines[0])
    return completed, payload, len(before), len(after)


def main() -> int:
    started = time.perf_counter()
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("prereg_exists", PREREG.is_file())
    check("prereg_hash_exact", sha256_file(PREREG) == PREREG_SHA256)
    check("prereg_audit_exists", PREREG_AUDIT.is_file())
    check("prereg_audit_hash_exact", sha256_file(PREREG_AUDIT) == PREREG_AUDIT_SHA256)
    check("runner_exists", RUNNER.is_file())
    check("launcher_exists", LAUNCHER.is_file())
    check("auditor_exists", AUDITOR.is_file())
    check("powershell_exists", POWERSHELL.is_file())
    check("python_exists", PYTHON.is_file())
    check("python_hash_exact", sha256_file(PYTHON) == PYTHON_SHA256)
    check("paths_absolute", all(path.is_absolute() for path in (PREREG, PREREG_AUDIT, RUNNER, LAUNCHER, AUDITOR, OUTPUT, ASSET_ROOT, BC_ROOT, POWERSHELL, PYTHON)))
    check("output_root_absent", not OUTPUT.exists())
    check("asset_root_absent", not ASSET_ROOT.exists())
    check("bc_root_absent", not BC_ROOT.exists())
    check("relevant_processes_zero_before", len(relevant_processes()) == 0)
    check("torch_absent_before", "torch" not in sys.modules)

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check("prereg_schema_exact", prereg.get("schema_version") == "v5.fa002.unified_candidate_preregistration.v1")
    check("prereg_candidate_exact", prereg.get("candidate", {}).get("candidate_id") == "FA002_EXACT_V55_CFR_BC_TEACHER_WARM_START")
    check("prereg_program_exact", prereg.get("candidate", {}).get("program_id") == "FA002_61e5047f8820e9df19733e57c257a04a")
    check("prereg_audit_pass", prereg_audit.get("overall") == "PASS" and prereg_audit.get("pass_count") == 161 and prereg_audit.get("fail_count") == 0)
    check("frozen_input_count17", len(prereg.get("frozen_inputs", [])) == 17)
    for index, item in enumerate(prereg.get("frozen_inputs", []), start=1):
        path = Path(item["path"])
        check(f"input_{index:02d}_exists", path.is_file())
        check(f"input_{index:02d}_bytes", path.stat().st_size == int(item["bytes"]))
        check(f"input_{index:02d}_sha256", sha256_file(path) == item["sha256"])

    runner_source = RUNNER.read_text(encoding="utf-8")
    auditor_source = AUDITOR.read_text(encoding="utf-8")
    launcher_source = LAUNCHER.read_text(encoding="utf-8")
    compile(runner_source, str(RUNNER), "exec")
    compile(auditor_source, str(AUDITOR), "exec")
    check("runner_compile", True)
    check("auditor_compile", True)
    runner_tree = ast.parse(runner_source)
    auditor_tree = ast.parse(auditor_source)
    runner_imports = {
        alias.name
        for node in ast.walk(runner_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    auditor_imports = {
        alias.name
        for node in ast.walk(auditor_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    forbidden_import_fragments = ("torch", "v5_phase_fa_revision006_q006", "v5_pcv019", "pcv019")
    check("runner_forbidden_imports_absent", not any(fragment in name for name in runner_imports for fragment in forbidden_import_fragments))
    check("auditor_forbidden_imports_absent", not any(fragment in name for name in auditor_imports for fragment in forbidden_import_fragments))
    check("runner_no_subprocess", "subprocess" not in runner_imports)
    check("runner_no_network_imports", not ({"requests", "urllib", "socket", "http", "aiohttp"} & runner_imports))
    check("runner_exclusive_writes", 'open("x"' in runner_source and "mkdir(parents=False, exist_ok=False)" in runner_source)
    check("runner_modes_exact", 'choices=("ContractProbe", "Qualification")' in runner_source)
    check("runner_output_absence_gate", 'if paths["output"].exists()' in runner_source)
    check("runner_implementation_audit_gate", "implementation_audit_classification_mismatch" in runner_source and "implementation_hash_not_bound_by_audit" in runner_source)
    check("runner_24_context_formula", "for depth in DEPTHS for street in STREETS for actor in (0, 1)" in runner_source)
    check("runner_hidden_resampling", "replay_determinized_infoset" in runner_source and "common" not in "")
    check("runner_4x8_constants", "BATCHES = 4" in runner_source and "ROLLOUTS_PER_BATCH = 8" in runner_source and "ROLLOUTS_PER_ACTION = 32" in runner_source)
    check("runner_counts_exact", "ACCEPTED_TOTAL = 120_000" in runner_source and "QUALITY_TOTAL = 6_144" in runner_source and "REPEATS_TOTAL = 768" in runner_source)
    check("runner_workers8", "WORKERS = 8" in runner_source)
    check("runner_resource_bounds", "WALL_SECONDS_MAX = 21_600.0" in runner_source and "RSS_MB_MAX = 4_096.0" in runner_source and "PROJECTED_WALL_HOURS_MAX = 168.0" in runner_source)
    check("runner_hidden_diversity28", 'if len(set(hidden_pair_hashes)) < 28' in runner_source)
    check("runner_diagnostic_only", runner_source.count("FORBIDDEN_DIAGNOSTIC_ONLY") >= 4)
    check("runner_zero_behavior_outputs", '"teacher_rows": 0' in runner_source and '"training_hands": 0' in runner_source and '"checkpoints": 0' in runner_source and '"official_hands": 0' in runner_source)
    check("auditor_independent_no_runner_import", not any("fa002_q01_61e5047" in name for name in auditor_imports))
    check("auditor_checks_all_rows", "reached_states.jsonl.gz" in auditor_source and "quality_rows.jsonl.gz" in auditor_source and "quality_summary_recomputed_exact" in auditor_source)
    check("auditor_recomputes_resource", "recomputed_projected_seconds" in auditor_source and "resource_projected_compressed_recomputed" in auditor_source)
    check("auditor_exclusive_result", 'write_json_exclusive(audit_path' in auditor_source)

    check("launcher_modes_exact", "[ValidateSet('ContractProbe', 'Qualification', 'Audit')]" in launcher_source)
    check("launcher_only_mode_nonce_parameters", launcher_source.count("[Parameter(") == 2 and "OutputRoot" not in launcher_source.split("Set-StrictMode", 1)[0])
    check("launcher_hardcoded_output", str(OUTPUT) in launcher_source)
    check("launcher_hardcoded_inputs", str(PREREG) in launcher_source and str(PREREG_AUDIT) in launcher_source)
    check("launcher_cpu_contract", "$env:CUDA_VISIBLE_DEVICES = '-1'" in launcher_source and "$env:FA002_Q01_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'" in launcher_source)
    check("launcher_probe_nonce_allowlist", all(nonce in launcher_source for nonce in PROBE_NONCES))
    check("launcher_qualification_no_path_override", "--output $OutputRoot" in launcher_source and "--implementation-audit-sha256 $ImplementationAuditSha256" in launcher_source)
    check("launcher_audit_owned", "& $Python $Auditor" in launcher_source and "--root $OutputRoot" in launcher_source)

    runner = load_module("fa002_q01_runner_implementation_audit", RUNNER)
    auditor = load_module("fa002_q01_result_auditor_implementation_audit", AUDITOR)
    runner_self_test = runner.self_test()
    auditor_self_test = auditor.self_test()
    check("runner_self_test_30_of_30", runner_self_test.get("pass_count") == runner_self_test.get("check_count") == 30)
    check("auditor_self_test_7_of_7", auditor_self_test.get("pass_count") == auditor_self_test.get("check_count") == 7)
    check("runner_program_id", runner.PROGRAM_ID == "FA002_61e5047f8820e9df19733e57c257a04a")
    check("runner_qualification_id", runner.QUALIFICATION_ID == "FA002_Q01_61e5047f8820e9df19733e57c257a04a")
    check("runner_prereg_hashes", runner.PREREG_SHA256 == PREREG_SHA256 and runner.PREREG_AUDIT_SHA256 == PREREG_AUDIT_SHA256)
    check("runner_seeds_exact", (runner.DEAL_SEED, runner.COMPONENT_SEED, runner.ACTION_SEED, runner.DETERMINIZATION_SEED, runner.ROLLOUT_SEED, runner.SHARD_ASSIGNMENT_SEED) == (2026072233, 2026972233, 2027972233, 2028972233, 2029972233, 2030972233))
    check("runner_future_roots_exact", runner.EXPECTED_OUTPUT.resolve(strict=False) == OUTPUT.resolve(strict=False))
    check("runner_probe_nonces_exact", tuple(runner.PROBE_NONCES) == PROBE_NONCES)
    check("torch_absent_after_self_tests", "torch" not in sys.modules)
    check("output_root_absent_after_self_tests", not OUTPUT.exists())

    probe_results: list[dict[str, Any]] = []
    for ordinal, nonce in enumerate(PROBE_NONCES, start=1):
        completed, payload, before_count, after_count = probe(nonce)
        check(f"probe_{ordinal}_exit0", completed.returncode == 0)
        check(f"probe_{ordinal}_stderr_empty", completed.stderr.strip() == "")
        check(f"probe_{ordinal}_schema", payload.get("schema_version") == "v5.fa002.q01.contract_probe.v1")
        check(f"probe_{ordinal}_program", payload.get("program_id") == "FA002_61e5047f8820e9df19733e57c257a04a")
        check(f"probe_{ordinal}_qualification", payload.get("qualification_id") == "FA002_Q01_61e5047f8820e9df19733e57c257a04a")
        check(f"probe_{ordinal}_nonce", payload.get("FA002_Q01_CONTRACT_NONCE") == nonce)
        check(f"probe_{ordinal}_cuda_minus1", payload.get("CUDA_VISIBLE_DEVICES") == "-1")
        check(f"probe_{ordinal}_device_mode", payload.get("FA002_Q01_DEVICE_MODE") == "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK")
        check(f"probe_{ordinal}_python", payload.get("python_sha256") == PYTHON_SHA256 and Path(payload.get("python_executable", "")).resolve(strict=False) == PYTHON.resolve(strict=False))
        check(f"probe_{ordinal}_runner_hash", payload.get("runner_sha256") == sha256_file(RUNNER))
        check(f"probe_{ordinal}_prereg_hashes", payload.get("preregistration_sha256") == PREREG_SHA256 and payload.get("preregistration_audit_sha256") == PREREG_AUDIT_SHA256)
        check(f"probe_{ordinal}_torch_absent", payload.get("torch_in_sys_modules") is False)
        check(f"probe_{ordinal}_output_absent", payload.get("output_root_exists") is False and not OUTPUT.exists())
        check(f"probe_{ordinal}_files_written_zero", payload.get("files_written") == 0 and before_count == after_count)
        probe_results.append({
            "ordinal": ordinal,
            "nonce": nonce,
            "exit_code": completed.returncode,
            "payload": payload,
            "scoped_snapshot_before": before_count,
            "scoped_snapshot_after": after_count,
            "scoped_diff": 0,
        })

    check("exactly_two_contract_probes", len(probe_results) == 2)
    check("probe_nonces_unique", len({result["nonce"] for result in probe_results}) == 2)
    check("output_root_absent_after_probes", not OUTPUT.exists())
    check("asset_root_absent_after_probes", not ASSET_ROOT.exists())
    check("bc_root_absent_after_probes", not BC_ROOT.exists())
    check("relevant_processes_zero_after", len(relevant_processes()) == 0)
    check("torch_absent_after", "torch" not in sys.modules)

    failures = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.fa002.q01.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "classification": "PASS / FA002_Q01_IMPLEMENTATION_AUDIT_PASS_ONE_QUALIFICATION_READY_ONLY" if not failures else "FAIL_CLOSED / FA002_Q01_IMPLEMENTATION_AUDIT_NO_AUTHORITY",
        "overall": "PASS" if not failures else "FAIL_CLOSED",
        "program_id": "FA002_61e5047f8820e9df19733e57c257a04a",
        "qualification_id": "FA002_Q01_61e5047f8820e9df19733e57c257a04a",
        "authority": {
            "preregistration_sha256": PREREG_SHA256,
            "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
            "frozen_inputs": "17_OF_17_EXIST_BYTES_SHA256_EXACT",
        },
        "implementation": {
            "runner_path": str(RUNNER),
            "runner_bytes": RUNNER.stat().st_size,
            "runner_sha256": sha256_file(RUNNER),
            "launcher_path": str(LAUNCHER),
            "launcher_bytes": LAUNCHER.stat().st_size,
            "launcher_sha256": sha256_file(LAUNCHER),
            "auditor_path": str(AUDITOR),
            "auditor_bytes": AUDITOR.stat().st_size,
            "auditor_sha256": sha256_file(AUDITOR),
            "implementation_auditor_path": str(Path(__file__).resolve(strict=False)),
            "implementation_auditor_bytes": Path(__file__).stat().st_size,
            "implementation_auditor_sha256": sha256_file(__file__),
            "python_path": str(PYTHON),
            "python_sha256": PYTHON_SHA256,
        },
        "scientific_self_tests": {"runner": runner_self_test, "result_auditor": auditor_self_test},
        "contract_probes": probe_results,
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(checks.values()),
        "fail_count": len(failures),
        "failures": failures,
        "audit_wall_seconds": time.perf_counter() - started,
        "execution_census": {
            "contract_probes": len(probe_results),
            "probe_files_written": 0,
            "qualification_attempts": 0,
            "output_root_exists": OUTPUT.exists(),
            "data_rows": 0,
            "training_hands": 0,
            "gpu_workloads": 0,
            "checkpoints": 0,
            "evaluation_or_slumbot_hands": 0,
            "official_hands": 0,
        },
        "next_if_pass": "ONE_FA002_Q01_QUALIFICATION_ATTEMPT_THROUGH_EXACT_LAUNCHER_THEN_ONE_LAUNCHER_OWNED_RESULT_AUDIT_AND_EXACT_JUDGMENT_STOP",
        "current_authority": {
            "qualification": "ONE_ATTEMPT_LATER_ONLY" if not failures else "NONE",
            "asset": "NONE",
            "training_or_gpu": "NONE",
            "checkpoint": "NONE",
            "evaluation_or_slumbot": "NONE",
            "official_hands": 0,
            "strength": "L0",
        },
        "terminal_stop": True,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
