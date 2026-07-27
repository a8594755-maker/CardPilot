"""Independent RS003 implementation audit and exactly-two probe owner."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "f7709e4bfba3febe0a829c10781054b5"
IDENTITY = "f7709e4bfba3febe0a829c10781054b557ead7d419428dc06736316980679fdb"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_{TOKEN}_20260722.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_audit_{TOKEN}_20260722.json"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs003_live_native_paired_mc32_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs003_live_native_paired_mc32_launcher_{TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs003_live_native_paired_mc32_audit_{TOKEN}.py"
IMPLEMENTATION_AUDITOR = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_implementation_audit_{TOKEN}_20260722.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_qualification_{TOKEN}_20260722"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs003_{TOKEN}_greedy_quick5k_20260722"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"

PREREG_SHA256 = "19a75a06e77919bf6cc9bc8bd871b70107a3ec2ee38cb3ccb8fad456788c706b"
PREREG_AUDIT_SHA256 = "f411bd44f0aa96d5692c0469db7a61f464939d9a340d3b5b72062bda10a0744e"
RUNNER_SHA256 = "0021463e9905a923d14f1c93f95ecd68f7294d907b963e016fb60b0f3eb1b334"
LAUNCHER_SHA256 = "a38a714185d702f5f9278c6bb2e078cb4a7b08ea044246085b7f0cfc5f57e1e8"
RESULT_AUDITOR_SHA256 = "b6a90a78b2bdf2bc2abe06d42f12badedefe59b5e90a9ed24c47420c9d35b787"
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
PYTHON_SHA256 = "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"

EXPECTED_BYTES = {
    PREREG: 25412,
    PREREG_AUDIT: 14686,
    RUNNER: 53531,
    LAUNCHER: 1814,
    RESULT_AUDITOR: 9700,
    PYTHON: 104952,
    CHECKPOINT: 261417230,
}
EXPECTED_SHA = {
    PREREG: PREREG_SHA256,
    PREREG_AUDIT: PREREG_AUDIT_SHA256,
    RUNNER: RUNNER_SHA256,
    LAUNCHER: LAUNCHER_SHA256,
    RESULT_AUDITOR: RESULT_AUDITOR_SHA256,
    PYTHON: PYTHON_SHA256,
    CHECKPOINT: CHECKPOINT_SHA256,
}
PROBE_NONCES = ["RS003_PROBE_A_2034972295", "RS003_PROBE_B_2035972295"]
SELFTEST_NONCE = "RS003_SELFTEST_2033972295"


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


def independent_dump_census(prereg: dict[str, Any]) -> dict[str, int]:
    dump_paths = [
        Path(item["path"])
        for item in prereg["frozen_authority_inputs"]
        if item["role"].startswith("h11_dump_part")
    ]
    by_hand: dict[int, list[int]] = defaultdict(list)
    prefixes: set[str] = set()
    rows = 0
    hero_rows = 0
    hero_postflop = 0
    for path in dump_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                rows += 1
                hand_idx = int(raw["hand_idx"])
                by_hand[hand_idx].append(int(raw["move_idx"]))
                prefixes.add(str(raw["action_str_before"]))
                if raw["who"] == "hero":
                    hero_rows += 1
                    if int(raw["street"]) > 0:
                        hero_postflop += 1
    transitions = 0
    ordered = True
    for values in by_hand.values():
        values.sort()
        transitions += max(0, len(values) - 1)
        ordered = ordered and values == list(range(len(values)))
    return {
        "dump_files": len(dump_paths),
        "rows": rows,
        "hands": len(by_hand),
        "prefixes": len(prefixes),
        "adjacent_transitions": transitions,
        "hero_rows": hero_rows,
        "hero_postflop": hero_postflop,
        "move_indices_contiguous": int(ordered),
    }


def static_checks() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path in EXPECTED_BYTES:
        check(
            f"bound_file_exact:{path.name}",
            path.is_file()
            and path.stat().st_size == EXPECTED_BYTES[path]
            and sha256_file(path) == EXPECTED_SHA[path],
            {
                "path": str(path),
                "expected_bytes": EXPECTED_BYTES[path],
                "expected_sha256": EXPECTED_SHA[path],
            },
        )
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check(
        "identity_exact",
        prereg.get("identity", {}).get("sha256") == IDENTITY
        and prereg.get("identity", {}).get("token") == TOKEN,
    )
    check(
        "preregistration_audit_pass97",
        prereg_audit.get("pass_count") == 97
        and prereg_audit.get("check_count") == 97
        and prereg_audit.get("fail_count") == 0,
    )
    input_failures: list[str] = []
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != int(item["bytes"])
            or sha256_file(path) != item["sha256"]
        ):
            input_failures.append(item["role"])
    check(
        "all22_frozen_inputs_exact",
        len(prereg["frozen_authority_inputs"]) == 22 and not input_failures,
        input_failures,
    )
    census = independent_dump_census(prereg)
    check(
        "independent_dump_census_exact",
        census
        == {
            "dump_files": 4,
            "rows": 29878,
            "hands": 5000,
            "prefixes": 584,
            "adjacent_transitions": 24878,
            "hero_rows": 12564,
            "hero_postflop": 6921,
            "move_indices_contiguous": 1,
        },
        census,
    )
    check(
        "four_fresh_implementation_files_present",
        all(path.is_file() for path in (RUNNER, LAUNCHER, RESULT_AUDITOR, IMPLEMENTATION_AUDITOR)),
    )
    syntax_failures: list[str] = []
    for path in (RUNNER, RESULT_AUDITOR, IMPLEMENTATION_AUDITOR):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_failures.append(f"{path.name}:{exc}")
    check("python_ast_3_of_3", not syntax_failures, syntax_failures)
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    escaped_launcher = str(LAUNCHER).replace("'", "''")
    parse_script = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_launcher}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count -gt 0){$errors|ForEach-Object{$_.ToString()};exit 1}else{'POWERSHELL_PARSE_PASS'}"
    )
    ps_parse = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", parse_script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    check(
        "powershell_parse_pass",
        ps_parse.returncode == 0 and "POWERSHELL_PARSE_PASS" in ps_parse.stdout,
        {"stdout": ps_parse.stdout, "stderr": ps_parse.stderr},
    )
    runner_text = RUNNER.read_text(encoding="utf-8")
    science_markers = [
        "class CentLedger",
        "def encode_history_exact",
        "def encode_extra_exact",
        "def live_action_table",
        "def mirror_from_ledger",
        "def assert_mirror_public",
        "MC = 32",
        "itertools.combinations",
        "PAIRED_LCB95_POSITIVE",
        "LCB_NO_CHANGE",
        "forbidden_source_field_read_count",
        "mirror_exact",
        "interface_exact",
        "synthetic_rows",
        "determinizations",
        "paired_stats",
    ]
    missing_science = [marker for marker in science_markers if marker not in runner_text]
    check("runner_science_markers_complete", not missing_science, missing_science)
    check(
        "runner_no_rs002_runtime_or_adapter_import",
        "import v5_rs002" not in runner_text
        and "from alpha_holdem.v5_rs002" not in runner_text
        and "from v5_rs002" not in runner_text,
    )
    check(
        "approximate_commitment_helper_reference_only",
        runner_text.count("live.compute_commitments(") == 1
        and "def reference_observation" in runner_text,
    )
    check(
        "runner_no_network_execution",
        "requests.post" not in runner_text and "slumbot.com" not in runner_text,
    )
    auditor_text = RESULT_AUDITOR.read_text(encoding="utf-8")
    check(
        "result_auditor_independent",
        "import v5_rs003" not in auditor_text and "from v5_rs003" not in auditor_text,
    )
    launcher_markers = [
        str(PYTHON),
        str(RUNNER),
        str(RESULT_AUDITOR),
        str(QUAL_ROOT),
        "$env:CUDA_VISIBLE_DEVICES = '0'",
        "$env:RS003_DEVICE_MODE = 'CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK'",
        "$env:PYTHONDONTWRITEBYTECODE = '1'",
        "$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'",
    ]
    check(
        "launcher_hardcoded_absolute_boundary",
        all(marker in launcher_text for marker in launcher_markers),
        [marker for marker in launcher_markers if marker not in launcher_text],
    )
    check(
        "future_outputs_fresh",
        not RESULT.exists() and not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists(),
    )
    return checks, {"preregistration": prereg, "census": census}


def run_launcher(mode: str, extra: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(LAUNCHER),
        "-Mode",
        mode,
        *extra,
    ]
    return subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def execute() -> tuple[dict[str, Any], bool]:
    started = time.perf_counter()
    checks, context = static_checks()

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    if not all(item["pass"] for item in checks):
        value = {
            "schema_version": "v5.rs003.implementation_audit.v1",
            "classification": "FAIL_CLOSED / RS003_IMPLEMENTATION_AUDIT_STATIC_PREPROBE_FAILURE_NO_QUALIFICATION",
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "probe_children_launched": 0,
            "qualification_authority": "NONE",
        }
        return value, False

    before_selftest = token_scope_snapshot()
    selftest = run_launcher(
        "SelfTest",
        ["-Nonce", SELFTEST_NONCE, "-Level", "deep"],
        1800,
    )
    after_selftest = token_scope_snapshot()
    selftest_json: dict[str, Any] | None = None
    try:
        selftest_json = parse_last_json(selftest.stdout)
    except Exception:
        pass
    check(
        "deep_selftest_exit0",
        selftest.returncode == 0,
        {"stdout": selftest.stdout[-8000:], "stderr": selftest.stderr[-8000:]},
    )
    check(
        "deep_selftest_contract_exact",
        isinstance(selftest_json, dict)
        and selftest_json.get("classification") == "RS003_SELF_TEST_PASS"
        and selftest_json.get("level") == "deep"
        and selftest_json.get("rows") == 29878
        and selftest_json.get("transitions") == 24878
        and selftest_json.get("live_checks") == 16
        and selftest_json.get("mirror_checks") == 8
        and selftest_json.get("files_written") == 0,
        selftest_json,
    )
    check("deep_selftest_zero_scope_diff", before_selftest == after_selftest)
    if not all(item["pass"] for item in checks):
        value = {
            "schema_version": "v5.rs003.implementation_audit.v1",
            "classification": "FAIL_CLOSED / RS003_IMPLEMENTATION_AUDIT_SELFTEST_PREPROBE_FAILURE_NO_QUALIFICATION",
            "overall": "FAIL_CLOSED",
            "checks": checks,
            "deep_selftest": selftest_json,
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
        probe_results.append(
            {
                "nonce": nonce,
                "exit_code": child.returncode,
                "stdout": child.stdout,
                "stderr": child.stderr,
                "parsed": parsed,
            }
        )
    probe_after = token_scope_snapshot()
    check("exactly_two_probe_children", len(probe_results) == 2)
    check("probe_nonces_exact_order", [item["nonce"] for item in probe_results] == PROBE_NONCES)
    check(
        "both_probes_exit0",
        all(item["exit_code"] == 0 for item in probe_results),
        [item["exit_code"] for item in probe_results],
    )
    check(
        "both_probes_contract_exact",
        all(
            isinstance(item["parsed"], dict)
            and item["parsed"].get("classification") == "RS003_CONTRACT_PROBE_PASS"
            and item["parsed"].get("identity_sha256") == IDENTITY
            and item["parsed"].get("device_mode") == "CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK"
            and item["parsed"].get("cuda_visible_devices") == "0"
            and item["parsed"].get("nonce") == item["nonce"]
            and item["parsed"].get("files_written") == 0
            for item in probe_results
        ),
        [item["parsed"] for item in probe_results],
    )
    check("probe_scope_zero_diff", probe_before == probe_after)
    check("checkpoint_unchanged_after_probes", probe_after["checkpoint_sha256"] == CHECKPOINT_SHA256)
    check(
        "qualification_and_quick5k_still_absent",
        not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists(),
    )
    implementation_hashes = {
        "runner": {
            "path": str(RUNNER),
            "bytes": RUNNER.stat().st_size,
            "sha256": sha256_file(RUNNER),
        },
        "launcher": {
            "path": str(LAUNCHER),
            "bytes": LAUNCHER.stat().st_size,
            "sha256": sha256_file(LAUNCHER),
        },
        "result_auditor": {
            "path": str(RESULT_AUDITOR),
            "bytes": RESULT_AUDITOR.stat().st_size,
            "sha256": sha256_file(RESULT_AUDITOR),
        },
        "implementation_auditor": {
            "path": str(IMPLEMENTATION_AUDITOR),
            "bytes": IMPLEMENTATION_AUDITOR.stat().st_size,
            "sha256": sha256_file(IMPLEMENTATION_AUDITOR),
        },
    }
    passed = all(item["pass"] for item in checks)
    value = {
        "schema_version": "v5.rs003.implementation_audit.v1",
        "classification": (
            "PASS / RS003_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
            if passed
            else "FAIL_CLOSED / RS003_IMPLEMENTATION_AUDIT_FAILURE_NO_QUALIFICATION"
        ),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "program_id": "RS003_LIVE_NATIVE_PAIRED_MC32_LCB95_ROOT_RESOLVER",
        "identity_sha256": IDENTITY,
        "token": TOKEN,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "implementation_files": implementation_hashes,
        "independent_dump_census": context["census"],
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
        "qualification_authority": (
            "EXACTLY_ONE_LAUNCH_THROUGH_BOUND_LAUNCHER"
            if passed
            else "NONE"
        ),
        "quick5k_authority": "NONE_UNTIL_QUALIFICATION_AND_RESULT_AUDIT_PASS",
        "network_or_slumbot_hands": 0,
        "strength": "L0",
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
        print(
            canonical_json(
                {
                    "classification": (
                        "RS003_PREPROBE_PREFLIGHT_PASS"
                        if passed
                        else "RS003_PREPROBE_PREFLIGHT_FAIL"
                    ),
                    "checks": checks,
                    "files_written": 0,
                    "probe_children_launched": 0,
                }
            )
        )
        return 0 if passed else 1
    if RESULT.exists():
        raise RuntimeError("implementation_audit_result_already_exists")
    value, passed = execute()
    write_exclusive(RESULT, value)
    print(
        canonical_json(
            {
                "classification": value["classification"],
                "pass_count": value.get("pass_count", 0),
                "check_count": value.get("check_count", 0),
                "probe_children_launched": value.get("probe_children_launched", 0),
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
