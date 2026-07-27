"""Derived RS009 qualification audit correction.

The frozen RS009 result auditor correctly verified every scientific artifact but
inherited the RS007 preregistration byte counts and hashes.  This reporting-only
correction preserves that failed audit, validates the two RS009 identities, and
independently rehashes the complete immutable qualification bundle.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "72e9bb6b8a4f4618aa6657710b66c5c9"
IDENTITY = "72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4"
QUAL_ROOT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_qualification_{TOKEN}_20260723"
PREREG = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_audit_{TOKEN}_20260723.json"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_implementation_audit_{TOKEN}_20260723.json"
CHECKPOINT = (
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt"
)
OUTPUT = QUAL_ROOT / "result_audit_derived_c1.json"

EXPECTED = {
    PREREG: (14797, "54b081b37171449d782b6b64ffaf84e9c553eea2c0bae426a00533790d229aea"),
    PREREG_AUDIT: (7135, "4d22631cdb6d58d8a4a3d543daf4fe30f0aa9ea474214af4336e7796963465c6"),
    IMPL_AUDIT: (20904, "f6bee04df309a6067af693da1712848585376f4014e69ee21f292890476a3729"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
    QUAL_ROOT / "invocation.json": (314, "d5925450f6a7840ce92a3b637cb2bb1ec9a1b3b102b2252f139d05e34df4ef70"),
    QUAL_ROOT / "metrics.json": (1220, "1bdbbbdf616234a629bd671d679297f9ed48f956a019858a0d7bf4d42b562ded"),
    QUAL_ROOT / "result.json": (4303, "48473c7b7796fa4c337c9838fdb6c419b811597a15f178bc43a7aff4e1cb1e92"),
    QUAL_ROOT / "result_audit.json": (7380, "d4b5d79f59ed5b674a4f654bf490c01d21d55226a5e436da944cfaff575b3b99"),
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> tuple[int, str]:
    rows = 0
    logical = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for line in handle:
            json.loads(line)
            logical.update(line)
            rows += 1
    return rows, logical.hexdigest()


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("derived_audit_output_already_exists")

    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, digest) in EXPECTED.items():
        actual = {
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha_file(path) if path.is_file() else None,
        }
        check(
            f"frozen_identity:{path.name}",
            actual == {"bytes": size, "sha256": digest},
            actual,
        )

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    implementation = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    invocation = json.loads((QUAL_ROOT / "invocation.json").read_text(encoding="utf-8"))
    result = json.loads((QUAL_ROOT / "result.json").read_text(encoding="utf-8"))
    failed_audit = json.loads((QUAL_ROOT / "result_audit.json").read_text(encoding="utf-8"))

    check("prereg_identity_exact", prereg.get("identity", {}).get("sha256") == IDENTITY)
    check(
        "prereg_audit_pass",
        prereg_audit.get("classification")
        == "PASS / RS009_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY",
    )
    check(
        "implementation_audit_pass",
        implementation.get("classification")
        == "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY",
    )
    check(
        "invocation_exact",
        invocation.get("identity_sha256") == IDENTITY
        and invocation.get("nonce") == "RS009_QUALIFICATION_2036972301"
        and invocation.get("implementation_audit_sha256") == EXPECTED[IMPL_AUDIT][1]
        and invocation.get("network_or_slumbot") == "FORBIDDEN",
    )
    check(
        "qualification_result_pass",
        result.get("identity_sha256") == IDENTITY
        and result.get("classification") == "PASS / RS007_DUAL_DOMAIN_QUALIFICATION_PASS"
        and result.get("pass_count") == 23
        and result.get("check_count") == 23
        and all(result.get("gates", {}).values())
        and result.get("network_or_slumbot_hands") == 0,
    )

    false_names = [item.get("name") for item in failed_audit.get("checks", []) if not item.get("pass")]
    true_count = sum(item.get("pass") is True for item in failed_audit.get("checks", []))
    check(
        "failed_audit_localized_exact",
        failed_audit.get("classification") == "FAIL_CLOSED / RS007_INDEPENDENT_RESULT_AUDIT_FAILURE"
        and failed_audit.get("check_count") == 48
        and failed_audit.get("fail_count") == 2
        and true_count == 46
        and false_names == ["preregistration_exact", "preregistration_audit_exact"],
        {"false_names": false_names, "true_count": true_count},
    )

    manifest = result.get("artifact_manifest", {})
    artifact_rows: dict[str, int] = {}
    for name, expected in sorted(manifest.items()):
        path = QUAL_ROOT / name
        rows, logical = load_rows(path)
        actual = {
            "bytes": path.stat().st_size,
            "file_sha256": sha_file(path),
            "logical_sha256": logical,
            "rows": rows,
        }
        artifact_rows[name] = rows
        check(f"raw_artifact_exact:{name}", actual == expected, actual)

    check(
        "raw_bundle_complete",
        artifact_rows
        == {
            "boundary_matrix_rows.jsonl.gz": 4096,
            "fault_rows.jsonl.gz": 128,
            "live_interface_rows.jsonl.gz": 6921,
            "repeat_rows.jsonl.gz": 192,
            "resolution_rows.jsonl.gz": 1280,
            "source_transition_rows.jsonl.gz": 29878,
            "terminal_utility_rows.jsonl.gz": 1280,
        },
        artifact_rows,
    )

    passed = all(item["pass"] for item in checks)
    output = {
        "schema_version": "v5.rs009.qualification.result_audit_derived_c1.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS009_DERIVED_RESULT_AUDIT_CORRECTION_PASS"
            if passed
            else "FAIL_CLOSED / RS009_DERIVED_RESULT_AUDIT_CORRECTION_FAILURE"
        ),
        "correction_scope": [
            "RS009_PREREGISTRATION_BYTES_AND_SHA256",
            "RS009_PREREGISTRATION_AUDIT_BYTES_AND_SHA256",
        ],
        "preserved_failed_audit_sha256": EXPECTED[QUAL_ROOT / "result_audit.json"][1],
        "qualification_classification": result.get("classification"),
        "quick5k_authority": "AUTHORIZED" if passed else "NONE",
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "network_or_slumbot_hands": 0,
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(output, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
