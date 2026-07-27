#!/usr/bin/env python3
"""Independent preimplementation audit for the VR003C1 mapping correction.

This audit does not import prospective code, create a model, or execute training.
It writes its create-new report only after every independently recomputed gate passes.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from pathlib import Path
from typing import Any

import torch


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "ad4f8d47e084a2e47c8f64efae465fd8"
IDENTITY = TOKEN + "16d5af5d7dc4448cbe8392a9498b6a3a"
PREREG = (
    ROOT
    / "reports"
    / f"v5_vr003c1_mapping_correction_preregistration_{TOKEN}_20260723.json"
)
PARENT = (
    ROOT
    / "reports"
    / "v5_vr003_resource_sized_qboost_preregistration_15c162514c345eec0ddeda67d97d3931_20260723.json"
)
FAILURE = (
    ROOT
    / "reports"
    / "v5_vr003_preimplementation_input_mapping_failure_15c162514c345eec0ddeda67d97d3931_20260723.json"
)
VR002 = (
    ROOT
    / "reports"
    / "v5_vr002_corrected_faithful_qboost_preregistration_dbc03bbf7d1d9cb0270c4b1f9d583a58_20260723.json"
)
VR002C1 = (
    ROOT
    / "reports"
    / "v5_vr002c1_cpu_default_generator_correction_preregistration_8d3cb2f1a897d1b9228b14ee7043db49_20260723.json"
)
CONTROL_AUDIT = (
    ROOT
    / "models"
    / "bench_v55_lg003c1_control_c1_dbdad6f2eb1cd2a7423992ffd9fe0a4e_20260723"
    / "result_audit.json"
)
OUT = (
    ROOT
    / "reports"
    / f"v5_vr003c1_mapping_correction_preregistration_audit_{TOKEN}_20260723.json"
)

EXPECTED_HASHES = {
    ROOT / "AGENTS.md": "fab1aea65dc2ee2d2e61a1fd1655f99107065e7c76eae1607495a065378c71ff",
    PARENT: "72bc18693aad9bd0c154cbdd5741240bf2043bae5dad53055727ba40dcab9a27",
    FAILURE: "2490ebfedca071e71e24744f4e93d922fadf40f37a2c15a7f2ce58294bfc4e6a",
    VR002: "029411e18760455197471a12f0c00c07d08e6d3123e3d8d62e4b51bc6b7b6fcd",
    VR002C1: "a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e",
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt": "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893.py": "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "v5_lg003c1_launcher_8bf8cedf78b6e8c8fe153802908ed893.ps1": "c20ebf0d3201b8fdb01a2a31945dbb2166defb646a2f1e410ca2e6d2e04b3d96",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "train_mp3_hybrid_h1.py": "69197b52baee7463d79e4a940f01f8bb241ed8e70975b51e043b99fd8a5cbc4d",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "network_hybrid_h1.py": "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "environment_v55.py": "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de",
    ROOT
    / "scripts"
    / "deep_cfr"
    / "game_state.py": "1500278c6a0fd2909c3bb7aa741aad1842651478b84a676e0783031aa27a6a8a",
    CONTROL_AUDIT: "27ac75084bd1ca769f4975fe2f3d497993f382358e4d97e7eadd5be2b0979b0f",
}
POOL_HASHES = {
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
}


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def state_dict_sha(state_dict: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def gate(name: str, predicates: dict[str, Any], evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "pass": all(bool(value) for value in predicates.values()),
        "predicates": {key: bool(value) for key, value in predicates.items()},
        "evidence": evidence,
    }


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    failure = json.loads(FAILURE.read_text(encoding="utf-8"))
    vr002 = json.loads(VR002.read_text(encoding="utf-8"))
    vr002c1 = json.loads(VR002C1.read_text(encoding="utf-8"))
    gates: list[dict[str, Any]] = []

    observed_hashes = {str(path): file_sha(path) for path in EXPECTED_HASHES}
    gates.append(
        gate(
            "authority_and_frozen_file_hashes",
            {
                str(path): observed_hashes[str(path)] == expected
                for path, expected in EXPECTED_HASHES.items()
            },
            observed_hashes,
        )
    )

    basis = prereg["identity"]["basis"]
    recomputed_identity = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    gates.append(
        gate(
            "fresh_identity_and_authority_binding",
            {
                "identity_recomputed": recomputed_identity == IDENTITY,
                "identity_registered": prereg["identity"]["sha256"] == IDENTITY,
                "token_exact": prereg["identity"]["token"] == TOKEN,
                "agents_bound": prereg["authority"]["agents_sha256"]
                == EXPECTED_HASHES[ROOT / "AGENTS.md"],
                "parent_bound": prereg["authority"]["parent_preregistration"]["sha256"]
                == EXPECTED_HASHES[PARENT],
                "failure_bound": prereg["authority"]["parent_failure"]["sha256"]
                == EXPECTED_HASHES[FAILURE],
                "sole_correction": prereg["authority"]["classification"]
                == "SOLE_FRESH_PREOUTPUT_CONTROL_PLANE_CORRECTION",
                "no_second_correction": prereg["authority"]["another_correction_allowed"]
                is False,
            },
            {"basis": basis, "recomputed_identity": recomputed_identity},
        )
    )

    corrected = prereg["corrected_mappings"]
    gates.append(
        gate(
            "corrected_path_to_sha_mappings",
            {
                "vr002_path": Path(
                    corrected["vr002_preregistration"]["path"]
                ).resolve()
                == VR002.resolve(),
                "vr002_sha": corrected["vr002_preregistration"]["sha256"]
                == EXPECTED_HASHES[VR002],
                "vr002c1_path": Path(
                    corrected["vr002c1_correction_preregistration"]["path"]
                ).resolve()
                == VR002C1.resolve(),
                "vr002c1_sha": corrected[
                    "vr002c1_correction_preregistration"
                ]["sha256"]
                == EXPECTED_HASHES[VR002C1],
                "vr002_self_identity": vr002["identity"]["sha256"]
                == "dbc03bbf7d1d9cb0270c4b1f9d583a586b82c23a655de48a4fb2139ac00a3fb1",
                "vr002c1_parent_sha": vr002c1["parent"]["preregistration_sha256"]
                == EXPECTED_HASHES[VR002],
            },
            corrected,
        )
    )

    c1_absence = {
        key: not Path(value).exists()
        for key, value in prereg["prospective_paths"].items()
    }
    parent_absence = {
        key: not Path(value).exists()
        for key, value in parent["prospective_paths"].items()
    }
    gates.append(
        gate(
            "all_parent_and_c1_prospective_paths_absent",
            {**{f"c1_{k}": v for k, v in c1_absence.items()},
             **{f"parent_{k}": v for k, v in parent_absence.items()}},
            {
                "c1": c1_absence,
                "terminal_parent": parent_absence,
            },
        )
    )

    failure_counts = failure["counts"]
    gates.append(
        gate(
            "parent_preoutput_zero_output_classification",
            {
                "status": failure["status"]
                == "VR003_PREIMPLEMENTATION_INPUT_PATH_SHA_MAPPING_FAILURE",
                "classification": failure["classification"]
                == "PREOUTPUT_CONTROL_PLANE_IDENTITY_DEFECT",
                "preregistration_bound": failure["preregistration_sha256"]
                == EXPECTED_HASHES[PARENT],
                "identity_bound": failure["identity"]
                == parent["identity"]["sha256"],
                "all_failure_counts_zero": all(
                    isinstance(value, int) and not isinstance(value, bool) and value == 0
                    for value in failure_counts.values()
                ),
                "no_science_effect": failure["science_effect"].startswith("None."),
            },
            {"counts": failure_counts, "science_effect": failure["science_effect"]},
        )
    )

    # C1 is an overlay, not a duplicate scientific registration.  Its exact parent
    # SHA supplies the inherited values.  A closed top-level schema and absence of
    # shadow behavior keys prove that only the declared correction can override it.
    allowed_top_level = {
        "schema_version",
        "registered_on",
        "design_id",
        "status",
        "identity",
        "authority",
        "corrected_mappings",
        "unchanged_contract",
        "prospective_paths",
        "audit_requirements",
        "after_audit_PASS",
        "preexecution_counts",
    }
    inherited_sections = {
        key: parent[key]
        for key in (
            "single_intervention",
            "exact_inherited_science_contract",
            "frozen_start",
            "fresh_seeds",
            "training_window",
            "resource_admission",
            "mechanism_gates",
            "mandatory_external",
            "external_judgment",
            "implementation_contract",
            "abort_rollback",
            "campaign",
        )
    }
    declarations = prereg["unchanged_contract"]
    gates.append(
        gate(
            "semantic_contract_exact_by_parent_binding_and_closed_overlay",
            {
                "closed_top_level_schema": set(prereg) == allowed_top_level,
                "no_behavior_shadow_keys": not (
                    set(prereg)
                    & {
                        "single_intervention",
                        "exact_inherited_science_contract",
                        "frozen_start",
                        "fresh_seeds",
                        "training_window",
                        "resource_admission",
                        "mechanism_gates",
                        "mandatory_external",
                        "external_judgment",
                        "implementation_contract",
                        "abort_rollback",
                        "campaign",
                    }
                ),
                "science_declared_exact": "remain exact" in declarations["science"],
                "resource_declared_exact": declarations["resource"].endswith(
                    "no new performance probe are exact."
                ),
                "seeds_declared_exact": declarations["seeds"].endswith("are exact."),
                "source_h11_only": "Exact H11 SHA96a007" in declarations["source"],
                "equivalence_rule_exact": "all remaining JSON values must be recursively exact"
                in declarations["equivalence_rule"],
                "parent_identity_terminal": parent["identity"]["sha256"]
                == failure["identity"],
            },
            {
                "parent_contract_projection_sha256": canonical_sha(inherited_sections),
                "inherited_section_names": sorted(inherited_sections),
                "closed_overlay_keys": sorted(prereg),
            },
        )
    )

    resource = parent["resource_admission"]
    with localcontext() as context:
        context.prec = 100
        hps = Decimal(resource["admitted_pure_hps_lower_bound"])
        overhead = Decimal(resource["frozen_overhead_seconds"])
        projected_exact = Decimal(1_900_000) / hps + overhead
        headroom_exact = Decimal(resource["runtime_limit_seconds"]) - projected_exact
        projected_registered = Decimal(resource["projected_bound_seconds"])
        headroom_registered = Decimal(resource["headroom_seconds"])
        projected_quantized = projected_exact.quantize(
            Decimal(1).scaleb(projected_registered.as_tuple().exponent),
            rounding=ROUND_HALF_EVEN,
        )
        headroom_quantized = headroom_exact.quantize(
            Decimal(1).scaleb(headroom_registered.as_tuple().exponent),
            rounding=ROUND_HALF_EVEN,
        )
    gates.append(
        gate(
            "independent_exact_decimal_resource_arithmetic",
            {
                "formula_exact": resource["formula"] == "1900000/HPS_LCB+overhead",
                "projected_rounds_exact": projected_quantized == projected_registered,
                "headroom_rounds_exact": headroom_quantized == headroom_registered,
                "headroom_positive": headroom_exact > 0,
                "projection_below_limit": projected_exact
                < Decimal(resource["runtime_limit_seconds"]),
                "registered_pass": resource["pass"] is True,
                "no_probe": resource["no_fresh_performance_probe"] is True,
            },
            {
                "projected_exact": str(projected_exact),
                "projected_registered": str(projected_registered),
                "headroom_exact": str(headroom_exact),
                "headroom_registered": str(headroom_registered),
            },
        )
    )

    checkpoint_path = Path(parent["frozen_start"]["checkpoint_path"])
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    snapshots = checkpoint.get("pool_snapshots") or []
    observed_pool = {
        int(row["id"]): state_dict_sha(row["state_dict"]) for row in snapshots
    }
    frozen = vr002["frozen_inputs"]
    gates.append(
        gate(
            "h11_modules_pool_and_control_authority",
            {
                "checkpoint_iteration": int(checkpoint.get("iteration", -1)) == 35051,
                "checkpoint_hands": int(checkpoint.get("total_hands", -1))
                == 576021901,
                "checkpoint_bytes": checkpoint_path.stat().st_size == 261417230,
                "pool_order": [int(row["id"]) for row in snapshots]
                == [109, 115, 120, 129, 103],
                "pool_content_hashes": observed_pool == POOL_HASHES,
                "vr002_pool_hashes": {
                    int(key): value
                    for key, value in frozen["pool"]["state_dict_sha256_by_id"].items()
                }
                == POOL_HASHES,
                "vr003_pool_order": parent["training_window"]["opponent_pool_order"]
                == [109, 115, 120, 129, 103],
                "pool_immutable": parent["training_window"]["pool_mutation"] is False,
                "control_hash_in_contract": parent["external_judgment"][
                    "frozen_control_audit_sha256"
                ]
                == EXPECTED_HASHES[CONTROL_AUDIT],
                "source_h11_in_contract": parent["frozen_start"]["checkpoint_sha256"]
                == EXPECTED_HASHES[checkpoint_path],
                "module_hashes_in_contract": (
                    frozen["ppo_module_sha256"]
                    == EXPECTED_HASHES[
                        ROOT / "scripts" / "alpha_holdem" / "train_mp3_hybrid_h1.py"
                    ]
                    and frozen["actor_network_sha256"]
                    == EXPECTED_HASHES[
                        ROOT / "scripts" / "alpha_holdem" / "network_hybrid_h1.py"
                    ]
                    and frozen["environment_v55_sha256"]
                    == EXPECTED_HASHES[
                        ROOT / "scripts" / "alpha_holdem" / "environment_v55.py"
                    ]
                    and frozen["game_state_sha256"]
                    == EXPECTED_HASHES[
                        ROOT / "scripts" / "deep_cfr" / "game_state.py"
                    ]
                ),
            },
            {
                "checkpoint_iteration": int(checkpoint.get("iteration", -1)),
                "checkpoint_total_hands": int(checkpoint.get("total_hands", -1)),
                "pool_state_dict_sha256_by_id": observed_pool,
                "control_audit_sha256": observed_hashes[str(CONTROL_AUDIT)],
            },
        )
    )
    del checkpoint

    c1_counts = prereg["preexecution_counts"]
    gates.append(
        gate(
            "zero_scientific_and_execution_counts_and_claim_state",
            {
                "all_c1_counts_zero": all(
                    isinstance(value, int) and not isinstance(value, bool) and value == 0
                    for value in c1_counts.values()
                ),
                "all_failure_counts_zero": all(value == 0 for value in failure_counts.values()),
                "formal_bar_preserved": vr002["exact_judgment"]["formal_claim_bar"]
                == "At least100000 complete official greedy-direct hands, bb/100>0, CI95 lower>0, complete independently audited hand-level bundle.",
                "route_not_exhausted": parent["campaign"]["route_exhausted"] is False,
                "strength_l0": parent["campaign"]["strength"] == "L0",
                "goal_active": parent["campaign"]["goal"] == "ACTIVE",
                "all_four_families_open_in_authority": "All four families\nremain open"
                in (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
                "external_complete_hands": parent["mandatory_external"]["complete_hands"]
                == 5000,
                "external_greedy_direct": parent["mandatory_external"]["policy"]
                == "greedy-direct",
            },
            {"c1_counts": c1_counts, "failure_counts": failure_counts},
        )
    )

    failures = [
        {"gate": row["name"], "predicates": row["predicates"]}
        for row in gates
        if not row["pass"]
    ]
    if failures:
        print(json.dumps({"status": "NONPASS_NO_REPORT_WRITTEN", "failures": failures}, indent=2))
        return 1

    report = {
        "schema_version": "v5.vr003c1.mapping_correction.preregistration_audit.v1",
        "identity": IDENTITY,
        "preregistration_sha256": file_sha(PREREG),
        "status": "VR003C1_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_AUTHORIZED_ONLY",
        "audit_scope": "Independent read-only authority, mapping, absence, semantic inheritance, Decimal resource, frozen-input, pool-content, control and zero-count verification.",
        "gate_summary": {
            "passed": len(gates),
            "total": len(gates),
            "all_pass": True,
        },
        "gates": gates,
        "scientific_output": {
            "implementation_files": 0,
            "model_loads_for_behavior": 0,
            "training_hands": 0,
            "generation_pure_hands": 0,
            "checkpoints": 0,
            "slumbot_hands": 0,
            "official_hands": 0,
        },
        "judgment": "The sole fresh mapping correction is valid. Fresh implementation is authorized, but execution remains forbidden until an independent implementation-audit PASS.",
    }
    OUT.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"status": report["status"], "report": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
