"""RS007C1 corrected implementation audit.

The sole correction is a structural AST check for the policy-to-public delegate.
Every successful parent check is rebound; this file owns the still-unused deep
self-test and exactly two launcher-bound probes.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
PARENT_TOKEN = "bf43f304c4709f356af131d60ef6e35a"
TOKEN = "ac09e2283fc6459f887b83e1d1e22b6d"
CONTROL_ID = "ac09e2283fc6459f887b83e1d1e22b6d1375d5d03339a8a41d73225f1e344129"
SCIENCE_ID = "bf43f304c4709f356af131d60ef6e35a52a7456d215987abce8180419c4ed6d0"
PREREG = ROOT / "reports" / f"v5_rs007c1_quote_insensitive_auditor_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs007c1_quote_insensitive_auditor_preregistration_audit_{TOKEN}_20260723.json"
PARENT_RESULT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_implementation_audit_{PARENT_TOKEN}_20260723.json"
FAILURE_AUDIT = ROOT / "reports" / f"v5_rs007_implementation_audit_failure_audit_{PARENT_TOKEN}_20260723.json"
PARENT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_implementation_audit_{PARENT_TOKEN}.py"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_{PARENT_TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_launcher_{PARENT_TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_audit_{PARENT_TOKEN}.py"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
PARENT_PREREG = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_preregistration_{PARENT_TOKEN}_20260723.json"
RESULT = ROOT / "reports" / f"v5_rs007c1_quote_insensitive_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_qualification_{PARENT_TOKEN}_20260723"
QUICK_ROOT = ROOT / "models" / f"bench_v55_rs007_{PARENT_TOKEN}_greedy_quick5k_20260723"
PROBES = ("RS007_PROBE_A_2034972299", "RS007_PROBE_B_2035972299")
SELFTEST = "RS007_SELFTEST_2033972299"

EXPECTED = {
    PREREG: (6539, "b8c87ab024c4b5dfdd92f3f49b50da51d52046d8bd61c0868dc6b9b0ec4bdc7b"),
    PREREG_AUDIT: (3856, "c78692d55ab25c07c3940884ac1e17fc2263438673be860893f6dc3561885347"),
    PARENT_RESULT: (12647, "775ca45d51f916e83e4ab54eb3d8fd76197e33bdc2ae7a89d9e4fecba65ecfee"),
    FAILURE_AUDIT: (2323, "410b735c6f6a63b84e24573d91bcca330285576cb3c2a2531de00fdb0323030c"),
    PARENT_AUDITOR: (21413, "fd36dfac482b3ecd581902f4223c5db0300be1658b822021714e1489fa4edd1e"),
    RUNNER: (64961, "049d779556fd89fc0e93f5bbb32f5e1a1a9594372cece2dcfa0c526ba46a5e94"),
    LAUNCHER: (1848, "c91f91397e770af5d2cd0c684c778944720e9b374743603065d618e976f74477"),
    RESULT_AUDITOR: (13133, "bce42611096975a958ac4bcd131b2fcca355a771f9fd26749d285d7685e9d4ba"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_child(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_json_missing")


def snapshot() -> dict[str, Any]:
    files = {}
    for base in (ROOT / "reports", ROOT / "scripts" / "alpha_holdem", ROOT / "models"):
        for token in (PARENT_TOKEN, TOKEN):
            for path in base.rglob(f"*{token}*"):
                if path.is_file() and path.resolve() != RESULT.resolve():
                    files[str(path.resolve())] = {
                        "bytes": path.stat().st_size,
                        "sha256": sha_file(path),
                    }
    return {
        "files": dict(sorted(files.items())),
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK_ROOT.exists(),
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }


def delegate_structure_exact(tree: ast.Module) -> dict[str, Any]:
    methods = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply_policy_slot"
    ]
    matches = []
    for method in methods:
        for node in ast.walk(method):
            if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            target = call.func
            exact_target = (
                isinstance(target, ast.Attribute)
                and target.attr == "apply_public_increment"
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            )
            exact_args = (
                len(call.args) == 2
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id == "increment"
                and isinstance(call.args[1], ast.Constant)
                and call.args[1].value == "POLICY_SLOT"
                and not call.keywords
            )
            if exact_target and exact_args:
                matches.append({"lineno": node.lineno, "target": "self.apply_public_increment", "constant": "POLICY_SLOT"})
    return {"method_count": len(methods), "matches": matches, "exact": len(methods) == 1 and len(matches) == 1}


def main() -> int:
    if RESULT.exists() or QUAL_ROOT.exists() or QUICK_ROOT.exists():
        raise RuntimeError("fresh_boundary_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, expected_sha) in EXPECTED.items():
        observed = {
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha_file(path) if path.is_file() else None,
        }
        check(f"bound_exact:{path.name}", observed == {
            "exists": True, "bytes": size, "sha256": expected_sha,
        }, observed)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    parent = json.loads(PARENT_RESULT.read_text(encoding="utf-8"))
    failure = json.loads(FAILURE_AUDIT.read_text(encoding="utf-8"))
    check("control_identity_exact", prereg["identity"]["sha256"] == CONTROL_ID and prereg["identity"]["token"] == TOKEN)
    check("science_identity_exact", prereg["terminal_parent"]["science_identity_sha256"] == SCIENCE_ID)
    check("preregistration_audit_pass", audit["classification"] == "PASS / RS007C1_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_CORRECTED_AUDITOR_ONLY")
    failed_parent_checks = [item["name"] for item in parent["checks"] if not item["pass"]]
    check(
        "parent_exactly_one_quote_sensitive_failure",
        parent["classification"] == "FAIL_CLOSED / RS007_IMPLEMENTATION_AUDIT_FAILURE"
        and parent["pass_count"] == 24 and parent["check_count"] == 25
        and failed_parent_checks == ["policy_api_exact_delegate"]
        and parent["deep_self_test"] is None and parent["contract_probes"] == [],
        failed_parent_checks,
    )
    check(
        "failure_independently_classified_prechild",
        failure["classification"] == "PASS / RS007_IMPLEMENTATION_AUDIT_FAIL_CLOSED_PRECHILD_CHECKER_QUOTE_SENSITIVITY"
        and failure["execution_census"]["deep_selftests"] == 0
        and failure["execution_census"]["contract_probes"] == 0
        and failure["execution_census"]["qualification_attempts"] == 0,
    )
    parent_prereg = json.loads(PARENT_PREREG.read_text(encoding="utf-8"))
    changed_inputs = []
    for item in parent_prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            changed_inputs.append(item["role"])
    check("all22_parent_inputs_exact", len(parent_prereg["frozen_authority_inputs"]) == 22 and not changed_inputs, changed_inputs)
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"), filename=str(RUNNER))
    structural = delegate_structure_exact(tree)
    check("corrected_quote_insensitive_delegate_structure", structural["exact"], structural)
    check("qualification_and_quick_roots_fresh", not QUAL_ROOT.exists() and not QUICK_ROOT.exists())
    if not all(item["pass"] for item in checks):
        raise RuntimeError(f"corrected_preflight_failure:{[item['name'] for item in checks if not item['pass']]}")

    before = snapshot()
    selftest = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER), "-Mode", "SelfTest", "-Nonce", SELFTEST, "-Level", "deep",
        ],
        capture_output=True, text=True, timeout=600,
    )
    try:
        self_payload = parse_child(selftest.stdout)
    except Exception as exc:
        self_payload = {"parse_error": str(exc)}
    check("deep_selftest_exit0", selftest.returncode == 0, {"stdout": selftest.stdout[-4000:], "stderr": selftest.stderr[-4000:]})
    deep_checks = self_payload.get("checks", {})
    check(
        "deep_selftest_full_contract_pass",
        self_payload.get("classification") == "RS007_DEEP_SELFTEST_PASS"
        and self_payload.get("files_written") == 0
        and deep_checks.get("source_transition_rows") == 29878
        and deep_checks.get("boundary_rows") == 4096
        and deep_checks.get("boundary_cells") == 128
        and deep_checks.get("terminal_rows") == 1280
        and deep_checks.get("terminal_cells") == 20
        and deep_checks.get("terminal_exact") is True
        and all(value == 8192 for value in deep_checks.get("comparator", {}).values()),
        self_payload,
    )
    probes = []
    for nonce in PROBES:
        child = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(LAUNCHER), "-Mode", "ContractProbe", "-Nonce", nonce,
            ],
            capture_output=True, text=True, timeout=300,
        )
        try:
            payload = parse_child(child.stdout)
        except Exception as exc:
            payload = {"parse_error": str(exc)}
        probes.append({
            "nonce": nonce, "exit_code": child.returncode, "payload": payload,
            "stdout": child.stdout[-2000:], "stderr": child.stderr[-2000:],
        })
    after = snapshot()
    check("exactly_two_probes", [item["nonce"] for item in probes] == list(PROBES))
    for index, item in enumerate(probes):
        payload = item["payload"]
        check(f"probe_{index + 1}_exit0", item["exit_code"] == 0, item)
        check(
            f"probe_{index + 1}_exact",
            payload.get("classification") == "RS007_CONTRACT_PROBE_PASS"
            and payload.get("identity_sha256") == SCIENCE_ID
            and payload.get("nonce") == PROBES[index]
            and payload.get("device_mode") == "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK"
            and payload.get("cuda_visible_devices") == "0"
            and payload.get("torch_imported") is False
            and payload.get("files_written") == 0,
            payload,
        )
    check("children_zero_file_diff", before == after, {"before": before, "after": after})
    check("checkpoint_unchanged", sha_file(CHECKPOINT) == EXPECTED[CHECKPOINT][1])
    passed = all(item["pass"] for item in checks)
    result = {
        "schema_version": "v5.rs007c1.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "control_identity_sha256": CONTROL_ID,
        "science_identity_sha256": SCIENCE_ID,
        "classification": (
            "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
            if passed else "FAIL_CLOSED / RS007C1_IMPLEMENTATION_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "structural_delegate_evidence": structural,
        "deep_self_test": {
            "exit_code": selftest.returncode, "payload": self_payload,
            "stdout": selftest.stdout[-4000:], "stderr": selftest.stderr[-4000:],
        },
        "contract_probes": probes,
        "snapshot_before": before,
        "snapshot_after": after,
        "qualification_authority_envelope": "PERMITTED" if passed else "NONE",
        "qualification_attempts": 0,
        "quick5k_authority": "NONE",
        "network_or_slumbot_hands": 0,
    }
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
