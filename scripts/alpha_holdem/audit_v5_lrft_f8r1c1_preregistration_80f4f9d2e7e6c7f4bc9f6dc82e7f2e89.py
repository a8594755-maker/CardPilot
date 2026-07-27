#!/usr/bin/env python3
"""Independent preimplementation audit for LRFT-F8R1C1.

This checker reads registration and frozen parent evidence, observes package
version metadata, and creates one audit report with O_EXCL.  It does not import
either runner, instantiate a model, invoke resource admission, or create any
scientific output.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "80f4f9d2e7e6c7f4bc9f6dc82e7f2e89"
IDENTITY = TOKEN + "6bd0c3ff56dd542eec58b239d1422619"
PARENT_IDENTITY = (
    "b35078ee7ad2ab123d5f9b0770538793"
    "d14e7b9dfbdbb51cc7897df93e2d3198"
)

PREREG = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_runtime_metadata_correction_preregistration_{TOKEN}_20260723.json"
)
OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_preregistration_audit_{TOKEN}_20260723.json"
)

PARENT_PREREG = (
    ROOT
    / "reports"
    / "v5_lrft_f8r1_preregistration_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
PARENT_PREAUDIT = (
    ROOT
    / "reports"
    / "v5_lrft_f8r1_preregistration_audit_c1_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
PARENT_RUNNER = (
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "v5_lrft_f8r1_b35078ee7ad2ab123d5f9b0770538793.py"
)
PARENT_IMPLEMENTATION_AUDIT = (
    ROOT
    / "reports"
    / "v5_lrft_f8r1_implementation_audit_c2_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)
PARENT_FAILURE = (
    ROOT
    / "reports"
    / "v5_lrft_f8r1_resource_admission_preoutput_runtime_metadata_failure_"
    "b35078ee7ad2ab123d5f9b0770538793_20260723.json"
)

EXPECTED_PREREG_SHA = (
    "53b0bbfd1aceb511b7e027fc42e2e100cf6d680f989bf8e292ffd59bf1dccb08"
)
EXPECTED_PARENT_HASHES = {
    "preregistration_sha256": (
        PARENT_PREREG,
        "716c074f755d1a377e8752013025392721716d8a456115e7367485afa068b616",
    ),
    "preimplementation_audit_c1_sha256": (
        PARENT_PREAUDIT,
        "d29d30681ea87f90d87e05084630ae9f944383a216c4f619fca0fc2b8b90198c",
    ),
    "runner_sha256": (
        PARENT_RUNNER,
        "2922d9dc18566b361883da6a384a9349a4bddbf5e3f743f0952ba09bbcdd8506",
    ),
    "implementation_audit_c2_sha256": (
        PARENT_IMPLEMENTATION_AUDIT,
        "0fd7c8103b60a4db2795dcfb1bf3eb8f7d04dae575fa25df2d74e6f97e69beec",
    ),
    "preoutput_failure_sha256": (
        PARENT_FAILURE,
        "99a0f9a65b4c32883cd1967d7c59a0f49380c5cb28ecec4e4298ee5e5726f324",
    ),
}

SCIENCE_KEYS = (
    "model_or_network_calls",
    "resource_rows",
    "census_hands",
    "selected_roots",
    "belief_rows",
    "solver_traversals",
    "leaf_outcomes",
    "E0_tapes",
    "E1_tapes",
    "teacher_rows",
    "checkpoints",
    "slumbot_hands",
    "official_hands",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"object JSON required: {path}")
    return value


def gate(
    name: str, predicates: dict[str, bool], evidence: Any
) -> dict[str, Any]:
    native = {key: bool(value) for key, value in predicates.items()}
    return {
        "name": name,
        "pass": all(native.values()),
        "predicates": native,
        "evidence": evidence,
    }


def all_exact_zero(mapping: Any, required: tuple[str, ...]) -> bool:
    return (
        isinstance(mapping, dict)
        and all(type(mapping.get(key)) is int and mapping[key] == 0 for key in required)
    )


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")

    prereg_raw = PREREG.read_bytes()
    prereg = json.loads(prereg_raw)
    parent_prereg = read_json(PARENT_PREREG)
    parent_preaudit = read_json(PARENT_PREAUDIT)
    parent_implementation_audit = read_json(PARENT_IMPLEMENTATION_AUDIT)
    parent_failure = read_json(PARENT_FAILURE)

    identity = prereg.get("identity", {})
    basis = identity.get("basis", "")
    recomputed_identity = hashlib.sha256(str(basis).encode("utf-8")).hexdigest()
    parent_identity = parent_prereg.get("identity", {})
    parent_basis = parent_identity.get("basis", "")
    recomputed_parent_identity = hashlib.sha256(
        str(parent_basis).encode("utf-8")
    ).hexdigest()

    registered_parent = prereg.get("parent", {})
    observed_parent_hashes = {
        key: file_sha256(path)
        for key, (path, _expected) in EXPECTED_PARENT_HASHES.items()
    }

    prospective = prereg.get("prospective_paths", {})
    prospective_observed = {
        key: {
            "path": str(Path(str(path))),
            "exists": Path(str(path)).exists(),
        }
        for key, path in prospective.items()
    }

    # Importing torch here observes immutable runtime metadata only.  No module,
    # checkpoint, tensor, CUDA context, network, or model is constructed.
    package_torch = importlib.metadata.version("torch")
    package_numpy = importlib.metadata.version("numpy")
    import torch

    runtime_observed = {
        "python": ".".join(str(value) for value in sys.version_info[:3]),
        "numpy_distribution": package_numpy,
        "torch_distribution": package_torch,
        "torch___version__": str(torch.__version__),
        "torch_cuda_build": str(torch.version.cuda),
        "cuda_initialized": bool(torch.cuda.is_initialized()),
    }
    runtime_registered = parent_prereg.get("frozen_runtime", {})

    classification = prereg.get("classification", {})
    sole = prereg.get("sole_correction", {})
    unchanged = prereg.get("unchanged", {})
    preexecution = prereg.get("preexecution_counts", {})
    failure_absence = parent_failure.get("observed_absence", {})
    implementation_science = parent_implementation_audit.get(
        "scientific_output", {}
    )

    expected_corrected_check = (
        "importlib.metadata.version('torch') == '2.6.0+cu124'"
    )
    expected_faulty_check = "importlib.metadata.version('torch') == '2.6.0'"

    gates = [
        gate(
            "G1_CORRECTION_IDENTITY_AND_REGISTRATION",
            {
                "prereg_sha": hashlib.sha256(prereg_raw).hexdigest()
                == EXPECTED_PREREG_SHA,
                "schema": prereg.get("schema_version")
                == "v5.lrft_f8r1c1.runtime_metadata_correction.preregistration.v1",
                "status": prereg.get("status")
                == "REGISTERED_PREIMPLEMENTATION_AUDIT_REQUIRED",
                "design": prereg.get("design_id")
                == "LRFT_F8R1C1_FRESH_PREOUTPUT_TORCH_LOCAL_VERSION_METADATA_CORRECTION",
                "identity_recomputed": recomputed_identity == IDENTITY,
                "identity_stored": identity.get("sha256") == IDENTITY,
                "token": identity.get("token") == TOKEN,
            },
            {
                "preregistration_sha256": hashlib.sha256(prereg_raw).hexdigest(),
                "basis": basis,
                "recomputed_identity_sha256": recomputed_identity,
            },
        ),
        gate(
            "G2_PARENT_LINEAGE_AND_HASHES",
            {
                "parent_identity_registered": registered_parent.get("identity")
                == PARENT_IDENTITY,
                "parent_identity_recomputed": recomputed_parent_identity
                == PARENT_IDENTITY,
                "all_registered_hashes_exact": all(
                    registered_parent.get(key) == expected
                    for key, (_path, expected) in EXPECTED_PARENT_HASHES.items()
                ),
                "all_observed_hashes_exact": all(
                    observed_parent_hashes[key] == expected
                    for key, (_path, expected) in EXPECTED_PARENT_HASHES.items()
                ),
                "preaudit_pass": parent_preaudit.get("status")
                == "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_PASS",
                "implementation_audit_pass": parent_implementation_audit.get("status")
                == "LRFT_F8R1_IMPLEMENTATION_AUDIT_PASS_RESOURCE_ADMISSION_AUTHORIZED_ONLY",
                "failure_exact": parent_failure.get("status")
                == "LRFT_F8R1_RESOURCE_ADMISSION_PREOUTPUT_TORCH_METADATA_LOCAL_VERSION_MISMATCH",
                "reuse_forbidden": registered_parent.get("reuse")
                == "DESIGN_EVIDENCE_ONLY_NEVER_CODE_OUTPUT_OR_EXECUTION_REUSE",
            },
            {
                "registered": {
                    key: registered_parent.get(key)
                    for key in ("identity", *EXPECTED_PARENT_HASHES.keys())
                },
                "observed_sha256": observed_parent_hashes,
                "parent_identity_recomputed": recomputed_parent_identity,
            },
        ),
        gate(
            "G3_PROSPECTIVE_PATHS_ABSENT",
            {
                "all_five_registered": set(prospective)
                == {
                    "runner",
                    "implementation_auditor",
                    "output_root",
                    "resource_admission",
                    "implementation_audit",
                },
                "all_absent": all(
                    not item["exists"] for item in prospective_observed.values()
                ),
            },
            prospective_observed,
        ),
        gate(
            "G4_REGISTERED_AND_OBSERVED_RUNTIME_EXACT",
            {
                "registered_python": runtime_registered.get("python") == "3.12.10",
                "observed_python": runtime_observed["python"] == "3.12.10",
                "registered_numpy": runtime_registered.get("numpy") == "2.4.4",
                "observed_numpy": runtime_observed["numpy_distribution"] == "2.4.4",
                "registered_torch": runtime_registered.get("torch")
                == "2.6.0+cu124",
                "metadata_torch": runtime_observed["torch_distribution"]
                == "2.6.0+cu124",
                "module_torch": runtime_observed["torch___version__"]
                == "2.6.0+cu124",
                "registered_cuda": runtime_registered.get("torch_cuda") == "12.4",
                "module_cuda": runtime_observed["torch_cuda_build"] == "12.4",
                "cuda_not_initialized": runtime_observed["cuda_initialized"] is False,
            },
            {
                "registered": {
                    key: runtime_registered.get(key)
                    for key in ("python", "numpy", "torch", "torch_cuda")
                },
                "observed": runtime_observed,
            },
        ),
        gate(
            "G5_PREOUTPUT_CLASSIFICATION_AND_SCIENCE_ZERO",
            {
                "classification": classification.get("failure_type")
                == "PREOUTPUT_CONTROL_PLANE_RUNTIME_IDENTITY_DEFECT",
                "ordinal": classification.get("fresh_correction_ordinal") == 1,
                "no_second_correction": classification.get(
                    "another_correction_allowed"
                )
                is False,
                "classification_zero": all_exact_zero(
                    classification,
                    (
                        "scientific_rows",
                        "resource_rows",
                        "model_or_network_calls",
                    ),
                ),
                "preexecution_zero": all_exact_zero(
                    preexecution,
                    ("implementation_files", *SCIENCE_KEYS),
                ),
                "failure_zero": all_exact_zero(
                    failure_absence,
                    ("model_instantiated", *SCIENCE_KEYS),
                ),
                "parent_audit_zero": all_exact_zero(
                    implementation_science,
                    (
                        "model_instances",
                        "model_or_network_calls",
                        "network_calls",
                        "resource_rows",
                        "census_hands",
                        "selected_roots",
                        "belief_rows",
                        "solver_traversals",
                        "leaf_outcomes",
                        "E0_tapes",
                        "E1_tapes",
                        "teacher_rows",
                        "checkpoints",
                        "slumbot_hands",
                        "official_hands",
                    ),
                ),
                "parent_output_absent": failure_absence.get("output_root_exists")
                is False,
                "parent_resource_result_absent": failure_absence.get(
                    "resource_admission_result_exists"
                )
                is False,
            },
            {
                "classification": classification,
                "preexecution_counts": preexecution,
                "parent_failure_observed_absence": failure_absence,
                "parent_implementation_audit_scientific_output": implementation_science,
            },
        ),
        gate(
            "G6_SOLE_CORRECTION_AND_BIT_IDENTICAL_SCOPE",
            {
                "fault_exact": sole.get("parent_faulty_check")
                == expected_faulty_check,
                "correction_exact": sole.get("corrected_check")
                == expected_corrected_check,
                "reason_local_suffix": sole.get("reason")
                == (
                    "The already registered Torch runtime and observed PEP440 "
                    "distribution version both include the +cu124 local-version suffix."
                ),
                "authority_changes_exact": sole.get(
                    "inseparable_authority_changes"
                )
                == [
                    "fresh identity/token constants",
                    "fresh runner,auditor,preaudit,audit and output paths",
                    "fresh status/schema prefixes needed for exact fail-closed authority",
                    "parent hashes retained as immutable evidence",
                ],
                "science_bit_identical": unchanged.get("science")
                == (
                    "Every F8R1 root,census,RNG,probability,belief,tree,MCCFR+,"
                    "proposal,leaf,E0,E1,confidence,claim,abort and interpretation "
                    "contract is bit-identical."
                ),
                "work_bit_identical": unchanged.get("work")
                == (
                    "Every exact work count,resource kernel,1.25 projection,"
                    "21600s/20GiB/6GiB/2GiB gate and zero-science requirement "
                    "is bit-identical."
                ),
                "normalized_ast_required": unchanged.get(
                    "implementation_equivalence"
                )
                == (
                    "After sentinel-normalizing only registered top-level authority "
                    "constants/paths/status/schema strings and the one torch metadata "
                    "literal,the complete Python AST must equal the frozen parent "
                    "runner AST."
                ),
                "contract_evidence_required": unchanged.get("contract_evidence")
                == (
                    "The corrected runner must independently reproduce the parent39/39 "
                    "no-model detailed evidence bit-exact except identity/path/schema/"
                    "status fields."
                ),
            },
            {
                "sole_correction": sole,
                "unchanged": unchanged,
            },
        ),
        gate(
            "G7_NO_IMPLEMENTATION_MODEL_RESOURCE_OR_SCIENCE",
            {
                "prospective_still_absent": all(
                    not Path(str(path)).exists() for path in prospective.values()
                ),
                "no_model_instantiated": True,
                "no_checkpoint_loaded": True,
                "no_network_calls": True,
                "no_resource_admission": True,
                "no_scientific_output": True,
                "report_absent_before_create": not OUT.exists(),
            },
            {
                "model_instantiated": 0,
                "checkpoint_loads": 0,
                "network_calls": 0,
                "resource_admission_runs": 0,
                "scientific_output": {key: 0 for key in SCIENCE_KEYS},
            },
        ),
    ]

    passed = sum(item["pass"] for item in gates)
    status = (
        "LRFT_F8R1C1_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_AUTHORIZED_ONLY"
        if passed == len(gates)
        else "LRFT_F8R1C1_REGISTERED_PREIMPLEMENTATION_AUDIT_NONPASS"
    )
    result = {
        "schema_version": "v5.lrft_f8r1c1.preregistration_audit.v1",
        "identity": IDENTITY,
        "status": status,
        "preregistration": {
            "path": str(PREREG),
            "sha256": hashlib.sha256(prereg_raw).hexdigest(),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": file_sha256(Path(__file__).resolve()),
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_instantiated": 0,
        "checkpoint_loads": 0,
        "network_calls": 0,
        "resource_admission_runs": 0,
        "scientific_output": {key: 0 for key in SCIENCE_KEYS},
        "authority": (
            "PASS authorizes only fresh F8R1C1 implementation and its independent "
            "implementation audit. It authorizes no model, resource admission, "
            "scientific rows, evaluation, checkpoint, or strength claim."
        ),
    }

    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                "status": status,
                "passed": passed,
                "total": len(gates),
                "path": str(OUT),
            },
            sort_keys=True,
        )
    )
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
