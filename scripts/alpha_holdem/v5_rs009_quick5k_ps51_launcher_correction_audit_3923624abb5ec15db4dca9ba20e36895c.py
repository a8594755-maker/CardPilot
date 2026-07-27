"""Deterministic audit of the sole PS5.1 quick5k launcher correction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "3923624abb5ec15db4dca9ba20e36895c"
IDENTITY = "3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70"
ORIGINAL_LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_quick5k_launcher_{TOKEN}.ps1"
CORRECTED_LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_quick5k_launcher_ps51_c1_{TOKEN}.ps1"
SESSION = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_quick5k_session_{TOKEN}.py"
ORIGINAL_AUDIT = ROOT / "reports" / f"v5_rs009_quick5k_implementation_audit_{TOKEN}_20260723.json"
OUTPUT = ROOT / "reports" / f"v5_rs009_quick5k_ps51_launcher_correction_audit_{TOKEN}_20260723.json"
QUICK_ROOT = ROOT / "models" / "bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723"

EXPECTED = {
    ORIGINAL_LAUNCHER: (5291, "5427c34d85f154f9d69f6cefc4be7dd41a06d0c9156ba406fd0eeca8ae664f77"),
    CORRECTED_LAUNCHER: (5746, "1bafc72e030cda0c2bbfd4e567b810c40d9834a0b0ad7106f0e19c752fac9d2b"),
    SESSION: (20848, "d2eedf7bbfaab6ef8ba3a7bf4e67e6843adbce3f94ca942e0345d119bdf67afa"),
    ORIGINAL_AUDIT: (3826, "374e16348a27b251ae0fbe0ab8a7306d10e06a5563dc417a6bb8f41f9f8806ca"),
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("correction_audit_output_already_exists")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, digest) in EXPECTED.items():
        actual = {
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha_file(path) if path.is_file() else None,
        }
        check(f"frozen_identity:{path.name}", actual == {"bytes": size, "sha256": digest}, actual)

    original_audit = json.loads(ORIGINAL_AUDIT.read_text(encoding="utf-8"))
    check(
        "unchanged_session_implementation_audit_pass",
        original_audit.get("identity_sha256") == IDENTITY
        and original_audit.get("classification")
        == "PASS / RS009_QUICK5K_IMPLEMENTATION_AUDIT_PASS_NETWORK_READY"
        and original_audit.get("pass_count") == 23
        and original_audit.get("fail_count") == 0
        and original_audit.get("network_calls") == 0
        and original_audit.get("official_hands") == 0,
    )
    corrected = CORRECTED_LAUNCHER.read_text(encoding="utf-8")
    check("powershell51_encoding_supported", corrected.count("-Encoding UTF8") == 2)
    check("unsupported_encoding_removed", "utf8NoBOM" not in corrected)
    check(
        "correction_audit_gate_before_root",
        corrected.index("correction_audit_nonpass")
        < corrected.index("quick5k_root_collision")
        < corrected.index("New-Item -ItemType Directory"),
    )
    check(
        "unchanged_session_audit_delegation",
        "374e16348a27b251ae0fbe0ab8a7306d10e06a5563dc417a6bb8f41f9f8806ca" in corrected
        and "'--implementation-audit-sha256', $SessionAuditSha256" in corrected,
    )
    check(
        "four_part_budget_unchanged",
        "for ($Part = 1; $Part -le 4; $Part++)" in corrected
        and "'--hands', '1250'" in corrected
        and "'--max-attempts', '1500'" in corrected,
    )
    check(
        "environment_contract_unchanged",
        all(
            text in corrected
            for text in (
                "CUDA_VISIBLE_DEVICES = '0'",
                "RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'",
                "PYTHONHASHSEED = '0'",
                "CUBLAS_WORKSPACE_CONFIG = ':4096:8'",
            )
        ),
    )
    check("no_destructive_commands", "Remove-Item" not in corrected and "Clear-Content" not in corrected)
    check("hidden_processes", corrected.count("Start-Process") == 1 and "-WindowStyle Hidden" in corrected)
    check("quick5k_root_absent", not QUICK_ROOT.exists())

    passed = all(item["pass"] for item in checks)
    output = {
        "schema_version": "v5.rs009.quick5k.ps51_launcher_correction_audit.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS009_QUICK5K_PS51_LAUNCHER_CORRECTION_AUDIT_PASS_NETWORK_READY"
            if passed
            else "FAIL_CLOSED / RS009_QUICK5K_PS51_LAUNCHER_CORRECTION_AUDIT_FAILURE"
        ),
        "correction": "WINDOWS_POWERSHELL_5_1_JSON_ENCODING_TOKEN_ONLY",
        "session_runner_changed": False,
        "scientific_design_changed": False,
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "network_calls": 0,
        "official_hands": 0,
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(output, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
