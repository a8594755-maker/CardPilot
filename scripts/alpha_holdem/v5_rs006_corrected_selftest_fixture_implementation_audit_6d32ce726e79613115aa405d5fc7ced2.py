"""RS006 corrected-identity implementation audit and fresh probe owner."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "6d32ce726e79613115aa405d5fc7ced2"
IDENTITY = "6d32ce726e79613115aa405d5fc7ced2fd9291531f856ddbef4cc5e3e8c802bb"
PREREG = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_preregistration_audit_{TOKEN}_20260723.json"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs006_corrected_selftest_fixture_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs006_corrected_selftest_fixture_launcher_{TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs006_corrected_selftest_fixture_audit_{TOKEN}.py"
THIS_FILE = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_qualification_{TOKEN}_20260723"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs006_{TOKEN}_greedy_quick5k_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
EXPECTED = {
    PREREG: (7235, "f110b12a0d57c325d3b17f91d39a6a17afbfa7a979cec9f54a20c05f367fc43b"),
    PREREG_AUDIT: (3078, "ecf0a34f695cfde535c05d4640f4fc61ac45708c860ec10d7f0b13335321b04f"),
    RUNNER: (7063, "d83c4f3f7bbef6ab9faae235a31ae1aca288987848af980a45c7e539c8aa4c77"),
    LAUNCHER: (1903, "659bfcec8a2c389285e4b9d62ecb0d7a108c9b547d8c996926357726f9c1caa3"),
    RESULT_AUDITOR: (1868, "76b3c1d126d64f56aa67d14c98824731120ee0e106f3f6a0ae977cfdcc590af7"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
}
PROBES = ("RS006_PROBE_A_2034972298", "RS006_PROBE_B_2035972298")
SELFTEST = "RS006_SELFTEST_2033972298"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_json_missing")


def snapshot() -> dict[str, Any]:
    files = {}
    for base in (ROOT / "reports", ROOT / "scripts" / "alpha_holdem", ROOT / "models"):
        for path in base.rglob(f"*{TOKEN}*"):
            if path.is_file() and path.resolve() != RESULT.resolve():
                files[str(path.resolve())] = {"bytes": path.stat().st_size, "sha256": sha_file(path)}
    return {
        "files": dict(sorted(files.items())),
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "implementation_result_exists": RESULT.exists(),
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }


def main() -> int:
    if RESULT.exists() or QUAL_ROOT.exists() or QUICK5K_ROOT.exists():
        raise RuntimeError("rs006_freshness_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, digest) in EXPECTED.items():
        check(f"bound_file:{path.name}", path.is_file() and path.stat().st_size == size and sha_file(path) == digest)
    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check("identity_exact", registration["identity"]["sha256"] == IDENTITY)
    check("preregistration_audit_pass", audit["classification"] == "PASS / RS006_CORRECTION_PREREGISTRATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY")
    correction_failures = []
    for item in registration["frozen_correction_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            correction_failures.append(item["role"])
    check("all8_correction_inputs_exact", not correction_failures, correction_failures)
    inherited = json.loads(Path(registration["inherited_science_contract"]["preregistration_path"]).read_text(encoding="utf-8"))
    inherited_failures = []
    for item in inherited["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            inherited_failures.append(item["role"])
    check("all26_science_inputs_exact", len(inherited["frozen_authority_inputs"]) == 26 and not inherited_failures, inherited_failures)
    syntax_errors = []
    for path in (RUNNER, RESULT_AUDITOR, THIS_FILE):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}:{exc}")
    check("python_ast_3_of_3", not syntax_errors, syntax_errors)
    runner_text = RUNNER.read_text(encoding="utf-8")
    check("sole_fixture_correction_exact", '"b200b400c/kk/"' in runner_text and '"b200b600c/kk/"' not in runner_text)
    check(
        "science_source_frozen_import_exact",
        "spec_from_file_location" in runner_text
        and Path(registration["inherited_science_contract"]["runtime_source_path"]).name in runner_text,
    )
    check("fresh_seed_overrides_complete", all(str(value) in runner_text for value in (2026072298, 2026972298, 2027972298, 2028972298, 2029972298, 2030972298)))
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    check("launcher_absolute_boundary", all(value in launcher_text for value in (
        str(RUNNER), str(RESULT_AUDITOR), str(QUAL_ROOT),
        "$env:CUDA_VISIBLE_DEVICES = '0'",
        "$env:RS006_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'",
        "$env:PYTHONDONTWRITEBYTECODE = '1'",
    )))
    escaped = str(LAUNCHER).replace("'", "''")
    parsed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}else{{'PASS'}}"],
        capture_output=True, text=True, timeout=60,
    )
    check("powershell_parse_pass", parsed.returncode == 0 and "PASS" in parsed.stdout, {"stdout": parsed.stdout, "stderr": parsed.stderr})
    before = snapshot()
    selftest_child = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
         "-Mode", "SelfTest", "-Nonce", SELFTEST, "-Level", "deep"],
        capture_output=True, text=True, timeout=600,
    )
    try:
        selftest_json = last_json(selftest_child.stdout)
    except Exception as exc:
        selftest_json = {"parse_error": str(exc)}
    check("deep_selftest_exit0", selftest_child.returncode == 0, {"stdout": selftest_child.stdout[-4000:], "stderr": selftest_child.stderr[-4000:]})
    check("deep_selftest_exact_pass", selftest_json.get("classification") == "RS006_DEEP_SELF_TEST_PASS" and selftest_json.get("files_written") == 0, selftest_json)
    probe_results = []
    for nonce in PROBES:
        child = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
             "-Mode", "ContractProbe", "-Nonce", nonce],
            capture_output=True, text=True, timeout=300,
        )
        try:
            payload = last_json(child.stdout)
        except Exception as exc:
            payload = {"parse_error": str(exc)}
        probe_results.append({"nonce": nonce, "exit_code": child.returncode, "payload": payload, "stderr": child.stderr[-2000:]})
    after = snapshot()
    check("exactly_two_fresh_probes", len(probe_results) == 2 and [row["nonce"] for row in probe_results] == list(PROBES))
    for index, row in enumerate(probe_results):
        payload = row["payload"]
        check(f"probe{index + 1}_exit0", row["exit_code"] == 0, row)
        check(
            f"probe{index + 1}_contract_pass",
            payload.get("classification") == "RS005_CONTRACT_PROBE_PASS"
            and payload.get("identity_sha256") == IDENTITY
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
        "schema_version": "v5.rs006.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "identity_sha256": IDENTITY,
        "classification": "PASS / RS006_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY" if passed else "FAIL_CLOSED / RS006_IMPLEMENTATION_AUDIT_FAILURE",
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "bound_files": {str(path): {"bytes": path.stat().st_size, "sha256": sha_file(path)} for path in (*EXPECTED, THIS_FILE)},
        "deep_selftest": selftest_json,
        "contract_probes": probe_results,
        "snapshot_before": before,
        "snapshot_after": after,
        "qualification_authority": "ONE_ATTEMPT" if passed else "NONE",
        "quick5k_authority": "NONE",
        "network_or_slumbot_hands": 0
    }
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
