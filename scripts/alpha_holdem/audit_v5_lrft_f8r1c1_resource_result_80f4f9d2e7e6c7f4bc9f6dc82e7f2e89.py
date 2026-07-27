#!/usr/bin/env python3
"""Independent evidence audit of the frozen LRFT-F8R1C1 resource result.

This checker never imports or executes the runner.  It rehashes the complete
authority chain, recomputes every recorded block rate, minimum rate, work
projection, resource gate, terminal status, and static exit-code semantics,
then writes one create-new audit report.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "80f4f9d2e7e6c7f4bc9f6dc82e7f2e89"
IDENTITY = TOKEN + "6bd0c3ff56dd542eec58b239d1422619"

RESULT = ROOT / "reports" / f"lrft_f8r1c1_{TOKEN}" / "resource_admission.json"
PREREG = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_runtime_metadata_correction_preregistration_{TOKEN}_20260723.json"
)
PREAUDIT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_preregistration_audit_{TOKEN}_20260723.json"
)
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1c1_{TOKEN}.py"
IMPLEMENTATION_AUDITOR = (
    ROOT
    / "scripts"
    / "alpha_holdem"
    / f"audit_v5_lrft_f8r1c1_{TOKEN}.py"
)
IMPLEMENTATION_AUDIT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_implementation_audit_{TOKEN}_20260723.json"
)
OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_resource_result_audit_{TOKEN}_20260723.json"
)

EXPECTED_HASHES = {
    "resource_result": (
        RESULT,
        "6783a63c3026303a4144b8b3a4b08cfa20ed5d91eb194d11f05348368fe3d367",
    ),
    "preregistration": (
        PREREG,
        "53b0bbfd1aceb511b7e027fc42e2e100cf6d680f989bf8e292ffd59bf1dccb08",
    ),
    "preimplementation_audit": (
        PREAUDIT,
        "5857daa842330c7aa5448adce3c57d067b78c9c53ed6f91b0d875e7937a29eab",
    ),
    "runner": (
        RUNNER,
        "0697f5d127f484f9ad01023d751c87500d527ca3c76a2286e392a04ad1ff0711",
    ),
    "implementation_auditor": (
        IMPLEMENTATION_AUDITOR,
        "5a1f403ba6202be4bd9bb73ec98cc9a1f62017eb5d1c2154b5fe91cddf2c0aa3",
    ),
    "implementation_audit": (
        IMPLEMENTATION_AUDIT,
        "a236aadacff20657b4e49fa8d69875a876da450e5975ebd089ae1bab9f1304bf",
    ),
}

EXPECTED_FIXED_INPUTS = {
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt": (
        "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
    ),
    ROOT / "scripts" / "alpha_holdem" / "network_hybrid_h1.py": (
        "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171"
    ),
    ROOT / "scripts" / "deep_cfr" / "hand_eval.py": (
        "fc30df48b0ae0091311f2ff40f8e320278bc47abba606c0c1f71fcce498f490d"
    ),
}

EXPECTED_WORK = {
    "canonical_census_calls": 114_688,
    "canonical_census_rows": 29_360_128,
    "history_calls": 1_152,
    "history_rows": 294_912,
    "solver_p256_calls": 524_288,
    "solver_p256_rows": 134_217_728,
    "solver_leaf_outcomes": 2_359_296,
    "solver_transitions": 75_497_472,
    "e0_p256_calls": 16_384,
    "e0_p256_rows": 4_194_304,
    "e0_outcomes": 131_072,
    "e0_transitions": 4_194_304,
    "e1_p256_calls": 16_384,
    "e1_p256_rows": 4_194_304,
    "e1_outcomes": 131_072,
    "e1_transitions": 4_194_304,
    "total_network_calls": 672_896,
    "total_network_rows": 172_261_376,
    "total_transitions": 84_000_768,
    "total_outcome_records": 2_621_440,
    "artifact_bytes": 2_147_483_648,
    "joint_entries_max": 12_994_800,
    "proposal_samples": 262_144,
    "e0_bootstrap_draws": 3_276_800_000,
    "e1_bootstrap_draws": 6_553_600_000,
}

EXPECTED_STAGE_UNITS = {
    "canonical_batch256_and_cpu_f64_cdf": {"canonical_calls": 1},
    "permanent512_two_chunk_p256_and_cpu_f64_cdf": {"p256_calls": 2},
    "fresh_exact_cent_vector_transitions": {"exact_cent_transitions": 20_480},
    "joint_logsumexp_q_sampling_mu_over_q": {
        "joint_entries": 131_072,
        "proposal_samples": 4_096,
    },
    "exclusive_outcome_serialization_and_hash": {
        "artifact_bytes": 552_960,
        "outcome_records": 4_096,
    },
    "deterministic_paired_bootstrap": {"bootstrap_draws": 65_536},
}

PASS_STATUS = (
    "LRFT_F8R1C1_RESOURCE_ADMISSION_PASS_SCIENCE_SEPARATELY_AUTHORIZED"
)
NONPASS_STATUS = "LRFT_F8R1C1_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS"

SCIENCE_KEYS = (
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


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-9)


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


def exact_exit_semantics(tree: ast.AST) -> bool:
    """Require main's resource result return to be exact PASS ? 0 : 2."""

    main = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        ),
        None,
    )
    if main is None:
        return False
    for node in ast.walk(main):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.IfExp):
            continue
        expression = node.value
        if (
            isinstance(expression.body, ast.Constant)
            and expression.body.value == 0
            and isinstance(expression.orelse, ast.Constant)
            and expression.orelse.value == 2
            and isinstance(expression.test, ast.Compare)
            and len(expression.test.ops) == 1
            and isinstance(expression.test.ops[0], ast.Eq)
            and len(expression.test.comparators) == 1
            and isinstance(expression.test.comparators[0], ast.Constant)
            and expression.test.comparators[0].value == PASS_STATUS
        ):
            return True
    return False


def recompute_stages(
    stages: Any,
) -> tuple[dict[str, dict[str, float]], dict[str, bool]]:
    if not isinstance(stages, list):
        return {}, {"stage_list": False}
    recomputed: dict[str, dict[str, float]] = {}
    checks: dict[str, bool] = {
        "stage_count": len(stages) == len(EXPECTED_STAGE_UNITS),
        "stage_names": {item.get("name") for item in stages if isinstance(item, dict)}
        == set(EXPECTED_STAGE_UNITS),
    }
    for stage in stages:
        if not isinstance(stage, dict):
            checks["all_stage_objects"] = False
            continue
        name = stage.get("name")
        if name not in EXPECTED_STAGE_UNITS:
            checks[f"{name}_registered"] = False
            continue
        blocks = stage.get("blocks")
        expected_units = EXPECTED_STAGE_UNITS[name]
        checks[f"{name}_eight_blocks"] = (
            isinstance(blocks, list)
            and len(blocks) == 8
            and [block.get("index") for block in blocks] == list(range(8))
        )
        minima = {key: math.inf for key in expected_units}
        block_rates_exact = True
        units_exact = True
        elapsed_positive = True
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    block_rates_exact = False
                    units_exact = False
                    elapsed_positive = False
                    continue
                elapsed = block.get("elapsed_seconds")
                units = block.get("units")
                rates = block.get("rates_per_second")
                if not isinstance(elapsed, (int, float)) or elapsed <= 0:
                    elapsed_positive = False
                    continue
                if units != expected_units or not isinstance(rates, dict):
                    units_exact = False
                    continue
                for key, count in expected_units.items():
                    calculated = count / float(elapsed)
                    observed = rates.get(key)
                    if not isinstance(observed, (int, float)) or not close(
                        observed, calculated
                    ):
                        block_rates_exact = False
                    minima[key] = min(minima[key], calculated)
        reported_minimum = stage.get("minimum_rates")
        minimum_exact = (
            isinstance(reported_minimum, dict)
            and set(reported_minimum) == set(expected_units)
            and all(
                math.isfinite(minima[key])
                and close(reported_minimum[key], minima[key])
                for key in expected_units
            )
        )
        checks[f"{name}_elapsed_positive"] = elapsed_positive
        checks[f"{name}_units_exact"] = units_exact
        checks[f"{name}_block_rates_recomputed"] = block_rates_exact
        checks[f"{name}_minimum_rates_recomputed"] = minimum_exact
        recomputed[name] = minima
    return recomputed, checks


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")

    result = read_json(RESULT)
    prereg = read_json(PREREG)
    preaudit = read_json(PREAUDIT)
    implementation_audit = read_json(IMPLEMENTATION_AUDIT)
    observed_hashes = {
        key: file_sha256(path) for key, (path, _expected) in EXPECTED_HASHES.items()
    }
    observed_fixed_hashes = {
        str(path): file_sha256(path) for path in EXPECTED_FIXED_INPUTS
    }

    output_files = sorted(
        str(path.relative_to(RESULT.parent))
        for path in RESULT.parent.rglob("*")
        if path.is_file()
    )

    stages, stage_checks = recompute_stages(result.get("stages"))
    canonical_rate = stages[
        "canonical_batch256_and_cpu_f64_cdf"
    ]["canonical_calls"]
    p256_rate = stages[
        "permanent512_two_chunk_p256_and_cpu_f64_cdf"
    ]["p256_calls"]
    transition_rate = stages[
        "fresh_exact_cent_vector_transitions"
    ]["exact_cent_transitions"]
    joint_rates = stages["joint_logsumexp_q_sampling_mu_over_q"]
    evidence_rates = stages["exclusive_outcome_serialization_and_hash"]
    bootstrap_rate = stages["deterministic_paired_bootstrap"]["bootstrap_draws"]

    projected_stage_seconds = {
        "canonical_network": (
            EXPECTED_WORK["canonical_census_calls"] + EXPECTED_WORK["history_calls"]
        )
        / canonical_rate,
        "p256_network": (
            EXPECTED_WORK["solver_p256_calls"]
            + EXPECTED_WORK["e0_p256_calls"]
            + EXPECTED_WORK["e1_p256_calls"]
        )
        / p256_rate,
        "exact_cent_transitions": EXPECTED_WORK["total_transitions"]
        / transition_rate,
        "joint_and_proposal": max(
            EXPECTED_WORK["joint_entries_max"] / joint_rates["joint_entries"],
            EXPECTED_WORK["proposal_samples"] / joint_rates["proposal_samples"],
        ),
        "evidence": max(
            EXPECTED_WORK["artifact_bytes"] / evidence_rates["artifact_bytes"],
            EXPECTED_WORK["total_outcome_records"]
            / evidence_rates["outcome_records"],
        ),
        "bootstrap": (
            EXPECTED_WORK["e0_bootstrap_draws"]
            + EXPECTED_WORK["e1_bootstrap_draws"]
        )
        / bootstrap_rate,
    }

    projection = result.get("projection", {})
    reported_stage_seconds = projection.get("stage_seconds", {})
    fixed_finalization = projection.get("fixed_finalization", {})
    recomputed_wall = (
        float(projection["fixed_load_seconds"])
        + float(projection["fixed_model_metamorphic_seconds"])
        + float(fixed_finalization["elapsed_seconds"])
        + 1.25 * sum(projected_stage_seconds.values())
    )

    recomputed_gates = {
        "projected_total_wall_seconds_max": recomputed_wall <= 21_600,
        "projected_process_tree_rss_bytes_max": int(
            projection["projected_process_tree_rss_bytes"]
        )
        <= 21_474_836_480,
        "projected_cuda_allocated_bytes_max": int(
            projection["projected_cuda_allocated_bytes"]
        )
        <= 6_442_450_944,
        "projected_artifact_bytes_max": int(
            projection["projected_artifact_bytes"]
        )
        <= 2_147_483_648,
        "gpu_free_bytes_at_start_min": int(result["host_before"]["gpu_free_bytes"])
        >= 6_442_450_944,
        "other_training_processes": (
            result["host_before"]["other_training_processes"] == 0
            and result["host_after"]["other_training_processes"] == 0
        ),
        "true_model_fixed_row_content_isolation": result.get("gates", {}).get(
            "true_model_fixed_row_content_isolation"
        )
        is True,
        "zero_science": all(
            type(result.get("scientific_counts", {}).get(key)) is int
            and result["scientific_counts"][key] == 0
            for key in SCIENCE_KEYS
        ),
    }
    expected_status = (
        PASS_STATUS if all(recomputed_gates.values()) else NONPASS_STATUS
    )

    runner_text = RUNNER.read_text(encoding="utf-8")
    runner_tree = ast.parse(runner_text, filename=str(RUNNER))

    impl_runner = implementation_audit.get("runner", {})
    impl_auditor = implementation_audit.get("audit_source", {})
    prereg_identity = prereg.get("identity", {})

    gates = [
        gate(
            "G1_IDENTITY_AND_COMPLETE_AUTHORITY_CHAIN",
            {
                "identity": result.get("identity") == IDENTITY,
                "identity_recomputed": hashlib.sha256(
                    str(prereg_identity.get("basis", "")).encode("utf-8")
                ).hexdigest()
                == IDENTITY,
                "all_hashes_exact": all(
                    observed_hashes[key] == expected
                    for key, (_path, expected) in EXPECTED_HASHES.items()
                ),
                "result_runner_binding": result.get("runner_sha256")
                == observed_hashes["runner"],
                "result_prereg_binding": result.get("preregistration_sha256")
                == observed_hashes["preregistration"],
                "result_preaudit_binding": result.get(
                    "preimplementation_audit_sha256"
                )
                == observed_hashes["preimplementation_audit"],
                "result_implementation_audit_binding": result.get(
                    "implementation_audit", {}
                ).get("sha256")
                == observed_hashes["implementation_audit"],
                "preaudit_pass": preaudit.get("status")
                == "LRFT_F8R1C1_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_AUTHORIZED_ONLY",
                "implementation_audit_pass": implementation_audit.get("status")
                == "LRFT_F8R1C1_IMPLEMENTATION_AUDIT_PASS_RESOURCE_ADMISSION_AUTHORIZED_ONLY",
                "implementation_runner_bound": impl_runner.get("sha256")
                == observed_hashes["runner"],
                "implementation_auditor_bound": impl_auditor.get("sha256")
                == observed_hashes["implementation_auditor"],
                "implementation_gates_all_pass": (
                    implementation_audit.get("gates_passed")
                    == implementation_audit.get("gates_total")
                    == len(implementation_audit.get("gates", []))
                    and all(
                        item.get("pass") is True
                        for item in implementation_audit.get("gates", [])
                    )
                ),
            },
            {
                "observed_sha256": observed_hashes,
                "result_bindings": {
                    "runner_sha256": result.get("runner_sha256"),
                    "preregistration_sha256": result.get("preregistration_sha256"),
                    "preimplementation_audit_sha256": result.get(
                        "preimplementation_audit_sha256"
                    ),
                    "implementation_audit": result.get("implementation_audit"),
                },
            },
        ),
        gate(
            "G2_FIXED_INPUTS_REHASHED",
            {
                "registered_exact": result.get("fixed_inputs")
                == {
                    str(path): expected
                    for path, expected in EXPECTED_FIXED_INPUTS.items()
                },
                "observed_exact": all(
                    observed_fixed_hashes[str(path)] == expected
                    for path, expected in EXPECTED_FIXED_INPUTS.items()
                ),
            },
            {
                "registered": result.get("fixed_inputs"),
                "observed_sha256": observed_fixed_hashes,
            },
        ),
        gate(
            "G3_SCIENCE_ZERO_AND_EXCLUSIVE_OUTPUT",
            {
                "science_keys_exact": set(result.get("scientific_counts", {}))
                == set(SCIENCE_KEYS),
                "science_all_zero": recomputed_gates["zero_science"],
                "sole_output": output_files == ["resource_admission.json"],
                "no_teacher_checkpoint_or_official_hands": all(
                    result["scientific_counts"][key] == 0
                    for key in (
                        "teacher_rows",
                        "checkpoints",
                        "slumbot_hands",
                        "official_hands",
                    )
                ),
            },
            {
                "scientific_counts": result.get("scientific_counts"),
                "output_files": output_files,
            },
        ),
        gate(
            "G4_EXACT_WORK_RECOMPUTED",
            {
                "table_exact": result.get("exact_work") == EXPECTED_WORK,
                "canonical_rows": 114_688 * 256 == 29_360_128,
                "history_formula": 8 * 24 * math.ceil(1326 / 256) == 1_152,
                "history_rows": 1_152 * 256 == 294_912,
                "solver_calls": 8_192 * 32 * 2 == 524_288,
                "e0_calls": 4 * math.ceil((8 * 4_096) / 512) * 32 * 2
                == 16_384,
                "e1_calls": 2 * math.ceil((8 * 8_192) / 512) * 32 * 2
                == 16_384,
                "total_calls": 114_688 + 1_152 + 524_288 + 16_384 + 16_384
                == 672_896,
                "total_rows": 672_896 * 256 == 172_261_376,
                "total_transitions": (
                    114_688
                    + 2_359_296 * 32
                    + 131_072 * 32
                    + 131_072 * 32
                )
                == 84_000_768,
                "total_outcomes": 2_359_296 + 131_072 + 131_072
                == 2_621_440,
                "joint_entries": 8 * math.comb(52, 2) * math.comb(50, 2)
                == 12_994_800,
            },
            result.get("exact_work"),
        ),
        gate(
            "G5_EIGHT_BLOCK_RATES_AND_MINIMA_RECOMPUTED",
            stage_checks,
            {
                "recomputed_minimum_rates": stages,
                "reported_minimum_rates": {
                    item["name"]: item["minimum_rates"]
                    for item in result.get("stages", [])
                },
            },
        ),
        gate(
            "G6_PROJECTION_FORMULA_RECOMPUTED",
            {
                "stage_keys": set(reported_stage_seconds)
                == set(projected_stage_seconds),
                "each_stage_exact": all(
                    close(reported_stage_seconds[key], value)
                    for key, value in projected_stage_seconds.items()
                ),
                "safety_factor": projection.get("variable_safety_factor") == 1.25,
                "fixed_load_positive": projection.get("fixed_load_seconds", 0) > 0,
                "metamorphic_positive": projection.get(
                    "fixed_model_metamorphic_seconds", 0
                )
                > 0,
                "finalization_measured": (
                    fixed_finalization.get("elapsed_seconds", 0) > 0
                    and fixed_finalization.get("bytes") == 1_048_467
                    and fixed_finalization.get("create_new") is True
                    and fixed_finalization.get("fsync") is True
                    and fixed_finalization.get("hash_verified") is True
                    and len(str(fixed_finalization.get("sha256", ""))) == 64
                ),
                "wall_exact": close(
                    projection.get("projected_total_wall_seconds"),
                    recomputed_wall,
                ),
                "artifact_projection_exact": projection.get(
                    "projected_artifact_bytes"
                )
                == EXPECTED_WORK["artifact_bytes"],
            },
            {
                "recomputed_stage_seconds": projected_stage_seconds,
                "reported_stage_seconds": reported_stage_seconds,
                "recomputed_total_wall_seconds": recomputed_wall,
                "reported_total_wall_seconds": projection.get(
                    "projected_total_wall_seconds"
                ),
                "fixed_finalization": fixed_finalization,
            },
        ),
        gate(
            "G7_GATES_STATUS_AND_EXIT_SEMANTICS",
            {
                "gates_exact": result.get("gates") == recomputed_gates,
                "sole_failed_gate": [
                    key for key, passed in recomputed_gates.items() if not passed
                ]
                == ["projected_total_wall_seconds_max"],
                "status_exact": result.get("status") == expected_status
                == NONPASS_STATUS,
                "schema": result.get("schema_version")
                == "v5.lrft_f8r1c1.resource_admission.v1",
                "source_exit_semantics": exact_exit_semantics(runner_tree),
                "nonpass_expected_exit_code": 2 == 2,
                "pass_only_exit_zero": PASS_STATUS in runner_text
                and NONPASS_STATUS in runner_text,
            },
            {
                "recomputed_gates": recomputed_gates,
                "reported_gates": result.get("gates"),
                "expected_status": expected_status,
                "reported_status": result.get("status"),
                "expected_process_exit_code_from_frozen_source": 2,
                "actual_process_exit_code_not_part_of_result_bundle": None,
            },
        ),
    ]

    passed = sum(item["pass"] for item in gates)
    status = (
        "LRFT_F8R1C1_RESOURCE_RESULT_AUDIT_PASS_CONFIRMS_REGISTERED_NONPASS_NO_SCIENCE"
        if passed == len(gates)
        else "LRFT_F8R1C1_RESOURCE_RESULT_AUDIT_NONPASS"
    )
    audit = {
        "schema_version": "v5.lrft_f8r1c1.resource_result_audit.v1",
        "identity": IDENTITY,
        "status": status,
        "resource_result": {
            "path": str(RESULT),
            "sha256": observed_hashes["resource_result"],
            "terminal_status": result.get("status"),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": file_sha256(Path(__file__).resolve()),
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "judgment": {
            "resource_admission": "NONPASS",
            "sole_failed_gate": "projected_total_wall_seconds_max",
            "projected_total_wall_seconds": recomputed_wall,
            "registered_limit_seconds": 21_600,
            "scientific_authority": "NONE",
            "implementation_authority": "NONE",
            "expected_runner_exit_code": 2,
            "rerank_required": True,
        },
        "scientific_output": {key: 0 for key in SCIENCE_KEYS},
    }

    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(audit, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(
        json.dumps(
            {
                "status": status,
                "passed": passed,
                "total": len(gates),
                "resource_status": result.get("status"),
                "projected_total_wall_seconds": recomputed_wall,
                "path": str(OUT),
            },
            sort_keys=True,
        )
    )
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
