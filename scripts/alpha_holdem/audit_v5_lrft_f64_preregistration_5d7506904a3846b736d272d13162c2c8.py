"""Independent preimplementation audit for LRFT-F64.

This audit reads only the registration and frozen inputs.  It does not import the
prospective solver, load Torch, create roots, or execute scientific kernels.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
PREREG = ROOT / "reports" / (
    "v5_lrft_f64_preregistration_"
    "5d7506904a3846b736d272d13162c2c8_20260723.json"
)
OUT = ROOT / "reports" / (
    "v5_lrft_f64_preregistration_audit_"
    "5d7506904a3846b736d272d13162c2c8_20260723.json"
)
EXPECTED_IDENTITY = (
    "5d7506904a3846b736d272d13162c2c8"
    "c995e36fa6fefbdf88029027a60c8f6b"
)
EXPECTED_INPUTS = {
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
    ROOT / "scripts" / "alpha_holdem" / "environment_v55.py": (
        "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de"
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, passed: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {
        "name": name,
        "pass": bool(passed),
        "observed": observed,
        "expected": expected,
    }


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite audit: {OUT}")
    raw = PREREG.read_bytes()
    registration = json.loads(raw)
    checks: list[dict[str, Any]] = []

    identity = registration["identity"]
    recomputed_identity = hashlib.sha256(identity["basis"].encode("utf-8")).hexdigest()
    agents_sha_in_basis = identity["basis"].split("|")[1]
    checks.append(
        check(
            "G1_identity_recomputes",
            recomputed_identity == identity["sha256"] == EXPECTED_IDENTITY,
            {
                "recomputed": recomputed_identity,
                "registered": identity["sha256"],
                "token": identity["token"],
            },
            {"identity": EXPECTED_IDENTITY, "token": EXPECTED_IDENTITY[:32]},
        )
    )
    checks.append(
        check(
            "G1_entry_authority_bound",
            registration["entry_authority"]["agents_sha256"] == agents_sha_in_basis
            and registration["entry_authority"]["family"]
            == "EXACT_V55_CFR_BC_TEACHER_WARM_START"
            and registration["entry_authority"]["rank"] == 1,
            registration["entry_authority"],
            {
                "agents_sha256": agents_sha_in_basis,
                "family": "EXACT_V55_CFR_BC_TEACHER_WARM_START",
                "rank": 1,
            },
        )
    )

    observed_hashes = {
        str(path): sha256_file(path) if path.is_file() else None
        for path in EXPECTED_INPUTS
    }
    checks.append(
        check(
            "G1_frozen_inputs_exist_and_hash",
            all(observed_hashes[str(path)] == digest for path, digest in EXPECTED_INPUTS.items()),
            observed_hashes,
            {str(path): digest for path, digest in EXPECTED_INPUTS.items()},
        )
    )
    claim_text = json.dumps(registration["claim_scope"], sort_keys=True)
    checks.append(
        check(
            "G1_claim_scope_fail_closed",
            registration["claim_scope"]["pass_authority"]
            == "LRFT_F64_FEASIBLE_FOR_LATER_TEACHER_ASSET_AND_BC_PREREGISTRATION_ONLY"
            and all(
                phrase in claim_text
                for phrase in (
                    "full-HUNL GTO or equilibrium",
                    "true NashConv or exploitability",
                    "quick5k, 20k, formal100k, L5, or L6",
                )
            ),
            registration["claim_scope"],
            "feasibility-only authority with explicit GTO/NashConv/strength prohibitions",
        )
    )

    policy = registration["canonical_h11_policy"]
    batch = policy["batch_contract"]
    checks.append(
        check(
            "G2_canonical_likelihood_and_behavior_coherent",
            batch["batch_size"] == 256
            and batch["row_position"] == "canonical global index modulo 256"
            and "duplicate the final real row" in batch["last_chunk_padding"]
            and "exact canonical chunk containing the actor's actual hole"
            in policy["root_generation_coherence"]
            and "bit-identical" in policy["root_generation_coherence"]
            and "arbitrary-order API" in policy["forbidden"],
            policy,
            "one canonical order, fixed batch256/index/padding, same chunk-row for behavior and likelihood",
        )
    )

    roots = registration["root_census"]
    belief = registration["belief_contract"]
    expected_roots = 4 * 2 * roots["roots_per_cell"]
    checks.append(
        check(
            "G3_root_and_joint_belief_contract",
            roots["complete_hands"] == 262144
            and roots["root_count"] == expected_roots == 64
            and "source hidden cards,outcome,reward" in roots["eligibility"][-1]
            and belief["normalization"].startswith("CPU float64 logsumexp")
            and belief["gates"]["joint_sum_abs_error_max"] == 1e-12
            and belief["gates"]["blocker_positive_entries"] == 0
            and "never multiply marginal ranges" in belief["normalization"],
            {
                "root_count": roots["root_count"],
                "recomputed_root_count": expected_roots,
                "belief_gates": belief["gates"],
            },
            "64 public-only roots and exact blocker-aware normalized joint law",
        )
    )

    game = registration["game_and_tree"]
    solver = registration["solver"]
    iterations = solver["iterations_per_root_replica"]
    traversals = roots["root_count"] * len(solver["replicas"]) * iterations * 2
    leaf_cap = traversals * 9
    update = solver["regret_update"]
    checks.append(
        check(
            "G4_external_sampling_mccfr_plus_defined",
            solver["algorithm"]
            == "EXTERNAL_SAMPLING_MCCFR_PLUS_WITH_OUTCOME_SAMPLED_H11_LEAVES"
            and game["decision_depth"] == 2
            and "sample exactly from frozen sigma_t"
            in solver["external_sampling"]["nontraverser"]
            and "enumerate every legal nonnull slot"
            in solver["external_sampling"]["traverser"]
            and solver["external_sampling"]["importance_weight"].startswith("none because")
            and update["cfr_plus"].startswith("R_(t+1)(I,a)=max(0")
            and solver["hard_work_caps"]["traversals"] == traversals == 8388608
            and solver["hard_work_caps"]["leaf_outcomes"] == leaf_cap == 75497472
            and not solver["hard_work_caps"]["adaptive_extension"],
            {
                "traversals": traversals,
                "leaf_cap": leaf_cap,
                "algorithm": solver["algorithm"],
                "update": update,
            },
            {
                "traversals": 8388608,
                "leaf_cap": 75497472,
                "algorithm": "external-sampling MCCFR+",
            },
        )
    )
    average = solver["root_average_only"]
    checks.append(
        check(
            "G4_root_average_is_reach_corrected_and_limited",
            "t*sigma_t(I_h,a)/m_i(h)" in average["update"]
            and average["actual_hole_visit_and_kish_ess_min_each_replica"] == 16
            and average["candidate"].startswith("fixed 0.5*")
            and "No full-tree average-strategy" in average["forbidden_claim"],
            average,
            "Horvitz-Thompson root-only linear average and no full-tree claim",
        )
    )

    banks = registration["evaluation_banks"]
    e0_tapes = roots["root_count"] * 2 * banks["E0"]["tapes_per_root_role"]
    e1_tapes = roots["root_count"] * 2 * banks["E1"]["tapes_per_root_role"]
    checks.append(
        check(
            "G5_E0_E1_banks_disjoint_and_sealed",
            e0_tapes == 524288
            and e1_tapes == 1048576
            and banks["E0"]["br_fit"] + banks["E0"]["evaluation"]
            == banks["E0"]["tapes_per_root_role"]
            and banks["E1"]["br_fit"] + banks["E1"]["evaluation"]
            == banks["E1"]["tapes_per_root_role"]
            and "exogenous keyed randomness only" in banks["materialization"]
            and "fresh confirmation process" in banks["E1"]["sealing"]
            and "distinct SHA-counter namespaces" in banks["disjointness"],
            {
                "E0_tapes_before_profile_reuse": e0_tapes,
                "E1_tapes_before_profile_reuse": e1_tapes,
                "sealing": banks["E1"]["sealing"],
            },
            {
                "E0_tapes_before_profile_reuse": 524288,
                "E1_tapes_before_profile_reuse": 1048576,
                "E1": "sealed until candidate freeze",
            },
        )
    )

    br = registration["sampled_br"]
    checks.append(
        check(
            "G6_infoset_consistent_split_sample_BR",
            "aggregate action values across all hidden realizations sharing the infoset key"
            in br["fit"]
            and "Freeze the complete pure BR map" in br["evaluation"]
            and br["gates"]["uncovered_eval_counterfactual_reach_max"] == 0.05
            and br["gates"]["each_compared_root_action_value_kish_ess_min"] == 128
            and "strictly below a clairvoyant per-deal maximum"
            in br["required_counterexample_test"]
            and "cannot certify equilibrium" in br["claim_limit"],
            br,
            "fit/eval split, one action per infoset, coverage/ESS gates, no NashConv claim",
        )
    )

    confidence = registration["selection_and_confidence"]
    checks.append(
        check(
            "G7_simultaneous_clustered_confidence",
            confidence["bootstrap"]["replicates"] == 100000
            and confidence["experimental_cluster"].startswith("source root")
            and confidence["E0"]["ordered_replicate_for_lcb"] == 834
            and confidence["E1"]["ordered_replicate_for_lcb"] == 2501
            and "six one-sided tests" in confidence["E0"]["quantities"]
            and "smallest T" in confidence["E0"]["selection"]
            and registration["heldout_value"]["primary_threshold_lcb"] == 0.20,
            confidence,
            "paired hierarchical root/tape bootstrap, fixed Bonferroni indices and smallest passing T",
        )
    )

    resource = registration["resource_admission"]
    measured = " ".join(resource["must_measure"])
    checks.append(
        check(
            "G8_resource_admission_precedes_science_and_is_complete",
            resource["position"].endswith(
                "before any census hand,root,belief,solver row or teacher row."
            )
            and all(
                term in measured
                for term in (
                    "canonical-chunk census inference",
                    "full canonical historical-likelihood",
                    "both-traverser",
                    "E0 BR",
                    "E1 BR",
                    "serialization",
                )
            )
            and resource["projection"].startswith("Use exact registered upper work counts")
            and resource["pass_gates"]["projected_total_wall_seconds_max"] == 21600
            and resource["global_scientific_abort"]["wall_seconds"] == 21600,
            resource,
            "zero-science exact-work admission with all stages and 21600s global cap",
        )
    )

    prospective = registration["prospective_paths"]
    prospective_absent = {
        name: not Path(path).exists() for name, path in prospective.items()
    }
    implementation = registration["implementation_and_audit"]
    counts = registration["preexecution_counts"]
    checks.append(
        check(
            "G9_no_outputs_or_execution_and_complete_audit_chain",
            all(prospective_absent.values())
            and all(value == 0 for value in counts.values())
            and implementation["independent_preimplementation_audit_required"]
            and implementation["independent_implementation_audit_required_before_resource_admission"]
            and implementation["independent_result_audit_required_before_judgment"]
            and "create-new semantics" in implementation["exclusive_writes"],
            {
                "prospective_absent": prospective_absent,
                "preexecution_counts": counts,
                "audit_chain": {
                    key: implementation[key]
                    for key in (
                        "independent_preimplementation_audit_required",
                        "independent_implementation_audit_required_before_resource_admission",
                        "independent_result_audit_required_before_judgment",
                    )
                },
            },
            "all prospective outputs absent, all counts zero, independent audits and exclusive writes fixed",
        )
    )

    passed = sum(1 for item in checks if item["pass"])
    result = {
        "schema_version": "v5.lrft_f64.preregistration_audit.v1",
        "identity": EXPECTED_IDENTITY,
        "status": (
            "LRFT_F64_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS"
            if passed == len(checks)
            else "LRFT_F64_REGISTERED_PREIMPLEMENTATION_AUDIT_NONPASS"
        ),
        "preregistration": {
            "path": str(PREREG),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "checks_passed": passed,
        "checks_total": len(checks),
        "checks": checks,
        "scientific_output": {
            "root_census_hands": 0,
            "selected_roots": 0,
            "belief_rows": 0,
            "solver_traversals": 0,
            "leaf_outcomes": 0,
            "teacher_rows": 0,
            "checkpoints": 0,
            "network_calls": 0,
            "slumbot_hands": 0,
            "official_hands": 0,
        },
        "authority": (
            "PASS authorizes fresh implementation and independent implementation "
            "audit only; resource admission must PASS before scientific execution."
        ),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    descriptor = os.open(OUT, flags)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "passed": passed, "total": len(checks)}))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
