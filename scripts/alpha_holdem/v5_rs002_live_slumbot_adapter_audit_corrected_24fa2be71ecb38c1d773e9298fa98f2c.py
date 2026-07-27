"""Single fresh correction for the terminal RS002 prelaunch auditor NameError.

The frozen parent auditor is not modified or rerun.  This wrapper verifies the
terminal bundle, injects only the missing Python literal binding ``true = True``,
and writes to a fresh content-addressed result path.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(r"C:\Users\a8594\CardPilot")
IDENTITY_SHA256 = "24fa2be71ecb38c1d773e9298fa98f2c839327b8c8501182b10428415208b38c"
TOKEN = "24fa2be71ecb38c1d773e9298fa98f2c"
PARENT_ADAPTER = ROOT / "scripts" / "alpha_holdem" / "v5_rs002_live_slumbot_adapter_81b61579f99755eb755d8c3c1905c22f.py"
PARENT_ADAPTER_SHA256 = "4a96685662d12837337a8bf89be464454204c59b4f55687271ff535ccfd8c009"
PARENT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / "v5_rs002_live_slumbot_adapter_audit_81b61579f99755eb755d8c3c1905c22f.py"
PARENT_AUDITOR_SHA256 = "b8e82a4e98c42e3a8fb391f9cfbc2a7514f97699a975fb6230d33ffdb6fb58b1"
CENSURE = ROOT / "reports" / "v5_rs002_live_adapter_prelaunch_audit_preoutput_failure_censure_81b61579f99755eb755d8c3c1905c22f_20260722.json"
CENSURE_SHA256 = "d30fab0ae4b427c003504022b8c004af2c1a10fcbb1f25e42c8fa62e42fa08d3"
OLD_RESULT = ROOT / "reports" / "v5_rs002_live_slumbot_adapter_prelaunch_audit_81b61579f99755eb755d8c3c1905c22f_20260722.json"
RESULT = ROOT / "reports" / f"v5_rs002_live_slumbot_adapter_prelaunch_audit_corrected_{TOKEN}_20260722.json"


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_parent():
    if sha256_file(PARENT_ADAPTER) != PARENT_ADAPTER_SHA256:
        raise RuntimeError("parent_adapter_hash_mismatch")
    if sha256_file(PARENT_AUDITOR) != PARENT_AUDITOR_SHA256:
        raise RuntimeError("parent_auditor_hash_mismatch")
    if sha256_file(CENSURE) != CENSURE_SHA256:
        raise RuntimeError("parent_censure_hash_mismatch")
    if OLD_RESULT.exists():
        raise RuntimeError("terminal_parent_result_must_remain_absent")


def load_parent():
    spec = importlib.util.spec_from_file_location("rs002_terminal_parent_auditor", PARENT_AUDITOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("parent_auditor_import_spec_failure")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.true = True
    return module


def write_exclusive(path, value):
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    with Path(path).open("xb") as handle:
        handle.write(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("Preflight", "Execute"), required=True)
    args = parser.parse_args()
    verify_parent()
    parent = load_parent()
    if args.mode == "Preflight":
        print(canonical_json({
            "classification": "PASS_CORRECTED_IDENTITY_PREFLIGHT",
            "identity_sha256": IDENTITY_SHA256,
            "sole_correction": "INJECT_PARENT_GLOBAL_TRUE_EQUALS_PYTHON_TRUE",
            "old_result_exists": OLD_RESULT.exists(),
            "new_result_exists": RESULT.exists(),
            "files_written": 0,
            "network_calls": 0,
        }))
        return 0
    if RESULT.exists():
        raise RuntimeError("corrected_result_already_exists")
    value, scientific_pass = parent.run_audit()
    value["correction_identity"] = {
        "basis": "RS002_LIVE_ADAPTER_PRELAUNCH_AUDIT_CORRECTION|4a96685662d12837337a8bf89be464454204c59b4f55687271ff535ccfd8c009|b8e82a4e98c42e3a8fb391f9cfbc2a7514f97699a975fb6230d33ffdb6fb58b1|d30fab0ae4b427c003504022b8c004af2c1a10fcbb1f25e42c8fa62e42fa08d3",
        "sha256": IDENTITY_SHA256,
        "token": TOKEN,
        "terminal_parent_censure_sha256": CENSURE_SHA256,
        "sole_correction": "INJECT_PARENT_GLOBAL_TRUE_EQUALS_PYTHON_TRUE",
        "scientific_logic_changed": False,
        "parent_result_remains_absent": not OLD_RESULT.exists(),
    }
    value["corrected_auditor"] = {
        "path": str(Path(__file__).resolve()),
        "bytes": Path(__file__).stat().st_size,
        "sha256": sha256_file(__file__),
    }
    write_exclusive(RESULT, value)
    print(canonical_json({
        "classification": value["classification"],
        "audit_integrity": value["audit_integrity"],
        "mismatch_rows": value["witnessed_boundary_census"]["mismatch_rows"],
        "minimum_fallback_rate": value["witnessed_boundary_census"]["minimum_fail_closed_fallback_rate"],
        "quick5k_launch_authority": value["registered_judgment"]["quick5k_launch_authority"],
    }))
    return 0 if scientific_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
