"""Independent pre-network implementation audit for RS009 quick5k."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "3923624abb5ec15db4dca9ba20e36895c"
IDENTITY = "3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs009_quick5k_preregistration_{TOKEN}_20260723.json"
SESSION = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_quick5k_session_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_quick5k_launcher_{TOKEN}.ps1"
OUTPUT = ROOT / "reports" / f"v5_rs009_quick5k_implementation_audit_{TOKEN}_20260723.json"
QUICK_ROOT = ROOT / "models" / "bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723"

EXPECTED = {
    PREREG: (7387, "00f334383231d1ecb1655796498dd5e020e28d031b21a94ea9045c076e31672c"),
    SESSION: (20848, "d2eedf7bbfaab6ef8ba3a7bf4e67e6843adbce3f94ca942e0345d119bdf67afa"),
    LAUNCHER: (5291, "5427c34d85f154f9d69f6cefc4be7dd41a06d0c9156ba406fd0eeca8ae664f77"),
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("implementation_audit_output_already_exists")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, digest) in EXPECTED.items():
        actual = {
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha_file(path) if path.is_file() else None,
        }
        check(f"source_identity:{path.name}", actual == {"bytes": size, "sha256": digest}, actual)

    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    check("registration_identity", registration["identity"]["sha256"] == IDENTITY)
    frozen_failures = []
    for item in registration["frozen_inputs"]:
        path = Path(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != int(item["bytes"])
            or sha_file(path) != item["sha256"]
        ):
            frozen_failures.append(item["role"])
    check("all6_frozen_inputs_exact", len(registration["frozen_inputs"]) == 6 and not frozen_failures, frozen_failures)
    check("quick5k_root_absent", not QUICK_ROOT.exists())
    check("implementation_audit_output_absent", not OUTPUT.exists())

    session_text = SESSION.read_text(encoding="utf-8")
    session_tree = ast.parse(session_text)
    check("session_ast_valid", isinstance(session_tree, ast.Module))
    check("no_direct_requests_post", "requests.post" not in session_text)
    check("no_policy_sampling", "Categorical" not in session_text and "multinomial" not in session_text)
    check("no_cpu_fallback", "cpu_fallback" not in session_text and '"cpu"' not in session_text)
    check(
        "session_budget_exact",
        'hands != 1250 or max_attempts != 1500' in session_text
        and 'successful != hands' in session_text
        and 'policy_mode="greedy"' in session_text,
    )
    check(
        "complete_raw_outputs",
        all(
            text in session_text
            for text in (
                '_hands.jsonl',
                '_dump.jsonl',
                '_resolver_decisions.jsonl',
                '_errors.jsonl',
                '_result.json',
            )
        ),
    )
    check(
        "resolver_contract_emitted",
        all(
            text in session_text
            for text in (
                '"resolver_attempted"',
                '"error_fallback"',
                '"contract_violations"',
                '"baseline_slot"',
                '"selected_slot"',
                '"decision_trace_sha256"',
            )
        ),
    )

    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    check("launcher_four_parts", "for ($Part = 1; $Part -le 4; $Part++)" in launcher_text)
    check(
        "launcher_budget_exact",
        "'--hands', '1250'" in launcher_text and "'--max-attempts', '1500'" in launcher_text,
    )
    check(
        "launcher_audit_gate_before_root",
        launcher_text.index("implementation_audit_nonpass")
        < launcher_text.index("quick5k_root_collision")
        < launcher_text.index("New-Item -ItemType Directory"),
    )
    check(
        "launcher_hidden_processes",
        launcher_text.count("Start-Process") == 1 and "-WindowStyle Hidden" in launcher_text,
    )
    check("launcher_no_output_overwrite", "Remove-Item" not in launcher_text and "Force" not in launcher_text)

    env = os.environ.copy()
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "CUDA_VISIBLE_DEVICES": "0",
            "RS007_DEVICE_MODE": "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK",
            "RS007_NONCE": "RS009_QUICK5K_CONTRACT_TEST_NO_NETWORK",
        }
    )
    completed = subprocess.run(
        [str(PYTHON), str(SESSION), "--mode", "ContractTest"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    contract: dict[str, Any] | None = None
    if completed.returncode == 0:
        try:
            contract = json.loads(completed.stdout.strip())
        except json.JSONDecodeError:
            contract = None
    check(
        "no_network_contract_test_exit0",
        completed.returncode == 0,
        {"returncode": completed.returncode, "stderr": completed.stderr[-2000:]},
    )
    check(
        "contract_test_exact",
        contract
        == {
            "classification": "PASS / RS009_QUICK5K_NO_NETWORK_CONTRACT_TEST",
            "identity_sha256": IDENTITY,
            "source_rows": 29878,
            "hero_rows": 12564,
            "roundtrip_exact": 29878,
            "witness_exact": 29878,
            "live_table_exact": 12564,
            "live_observation_exact": 12564,
            "network_calls": 0,
            "files_written": 0,
        },
        contract,
    )
    check("quick5k_root_still_absent", not QUICK_ROOT.exists())
    check("checkpoint_unchanged", sha_file(Path(registration["frozen_inputs"][3]["path"])) == registration["frozen_inputs"][3]["sha256"])

    passed = all(item["pass"] for item in checks)
    output = {
        "schema_version": "v5.rs009.quick5k.implementation_audit.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS009_QUICK5K_IMPLEMENTATION_AUDIT_PASS_NETWORK_READY"
            if passed
            else "FAIL_CLOSED / RS009_QUICK5K_IMPLEMENTATION_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "network_calls": 0,
        "official_hands": 0,
        "quick5k_root_exists_after_audit": QUICK_ROOT.exists(),
        "source_sha256": {
            "session": sha_file(SESSION),
            "launcher": sha_file(LAUNCHER),
        },
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(output, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
