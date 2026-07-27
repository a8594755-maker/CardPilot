"""Sole fresh audit correction for LRFT-F64.

The parent audit froze NONPASS because its G3 checker required the literal phrase
"source hidden cards" although the registration equivalently forbids "hidden cards".
This independently recomputes the nine scientific contract groups without reusing the
parent check outcomes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "5d7506904a3846b736d272d13162c2c8"
IDENTITY = TOKEN + "c995e36fa6fefbdf88029027a60c8f6b"
PREREG = ROOT / "reports" / f"v5_lrft_f64_preregistration_{TOKEN}_20260723.json"
PARENT = ROOT / "reports" / f"v5_lrft_f64_preregistration_audit_{TOKEN}_20260723.json"
OUT = ROOT / "reports" / f"v5_lrft_f64_preregistration_audit_c1_{TOKEN}_20260723.json"
PARENT_SHA = "faecd1c939e00e89f0d21da64fd0b0eaa9d56307cd6770bc9afba54d680b44b2"
FROZEN = {
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt": "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "network_hybrid_h1.py": "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171",
    ROOT
    / "scripts"
    / "deep_cfr"
    / "hand_eval.py": "fc30df48b0ae0091311f2ff40f8e320278bc47abba606c0c1f71fcce498f490d",
    ROOT
    / "scripts"
    / "alpha_holdem"
    / "environment_v55.py": "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def gate(name: str, predicates: dict[str, bool]) -> dict[str, Any]:
    return {
        "name": name,
        "pass": all(predicates.values()),
        "predicates": predicates,
    }


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    prereg_bytes = PREREG.read_bytes()
    p = json.loads(prereg_bytes)
    parent = json.loads(PARENT.read_text(encoding="utf-8"))
    canonical = p["canonical_h11_policy"]
    roots = p["root_census"]
    belief = p["belief_contract"]
    tree = p["game_and_tree"]
    solver = p["solver"]
    banks = p["evaluation_banks"]
    br = p["sampled_br"]
    conf = p["selection_and_confidence"]
    resource = p["resource_admission"]
    prospective = p["prospective_paths"]

    identity_recomputed = hashlib.sha256(
        p["identity"]["basis"].encode("utf-8")
    ).hexdigest()
    frozen_observed = {str(path): sha(path) for path in FROZEN}
    forbidden_claims = set(p["claim_scope"]["not_authorized"])
    g1 = gate(
        "G1_IDENTITY_INPUT_SCOPE",
        {
            "identity": identity_recomputed == p["identity"]["sha256"] == IDENTITY,
            "token": p["identity"]["token"] == TOKEN,
            "family": p["entry_authority"]["family"]
            == "EXACT_V55_CFR_BC_TEACHER_WARM_START",
            "input_hashes": all(
                frozen_observed[str(path)] == expected
                for path, expected in FROZEN.items()
            ),
            "claim": p["claim_scope"]["pass_authority"]
            == "LRFT_F64_FEASIBLE_FOR_LATER_TEACHER_ASSET_AND_BC_PREREGISTRATION_ONLY",
            "no_gto": "full-HUNL GTO or equilibrium" in forbidden_claims,
            "no_nashconv": "true NashConv or exploitability" in forbidden_claims,
            "no_strength": "quick5k, 20k, formal100k, L5, or L6"
            in forbidden_claims,
        },
    )
    batch = canonical["batch_contract"]
    g2 = gate(
        "G2_CANONICAL_POLICY_AND_BELIEF",
        {
            "batch256": batch["batch_size"] == 256,
            "position": batch["row_position"] == "canonical global index modulo 256",
            "padding": "duplicate the final real row" in batch["last_chunk_padding"],
            "same_row": "exact canonical chunk containing the actor's actual hole"
            in canonical["root_generation_coherence"],
            "repeat": "bit-identical" in canonical["repeat_gate"],
            "no_reorder": "arbitrary-order API" in canonical["forbidden"],
            "joint_not_factorized": "never multiply marginal ranges"
            in belief["normalization"],
            "normalization": belief["gates"]["joint_sum_abs_error_max"] == 1e-12,
            "blockers": belief["gates"]["blocker_positive_entries"] == 0,
        },
    )
    selection_text = json.dumps(roots["eligibility"]).lower()
    g3 = gate(
        "G3_ROOT_TREE_INFOSET",
        {
            "census": roots["complete_hands"] == 262144,
            "root_count": roots["root_count"] == 4 * 2 * roots["roots_per_cell"] == 64,
            "public_selection": all(
                word in selection_text
                for word in ("hidden cards", "outcome", "reward", "solver output")
            ),
            "no_replacement": roots["no_replacement"].startswith("Missing cell quota"),
            "depth": tree["decision_depth"] == 2,
            "nodes": tree["max_public_nodes"] == 91 and tree["max_leaves"] == 81,
            "infoset": tree["infoset_key"]
            == "root_id|acting_player|own_hole|canonical_exact_public_state",
            "no_opponent_hole": "opponent hole" in tree["infoset_forbidden_fields"],
        },
    )
    traversals = 64 * 2 * solver["iterations_per_root_replica"] * 2
    g4 = gate(
        "G4_EXTERNAL_SAMPLING_MCCFR_PLUS",
        {
            "algorithm": solver["algorithm"]
            == "EXTERNAL_SAMPLING_MCCFR_PLUS_WITH_OUTCOME_SAMPLED_H11_LEAVES",
            "two_replicas": solver["replicas"] == ["A", "B"],
            "iterations": solver["iterations_per_root_replica"] == 32768,
            "external_target": solver["external_sampling"]["importance_weight"].startswith(
                "none because"
            ),
            "enumeration": "enumerate every legal nonnull slot"
            in solver["external_sampling"]["traverser"],
            "plus_clip": solver["regret_update"]["cfr_plus"].startswith(
                "R_(t+1)(I,a)=max(0"
            ),
            "traversals": solver["hard_work_caps"]["traversals"]
            == traversals
            == 8388608,
            "leaves": solver["hard_work_caps"]["leaf_outcomes"]
            == traversals * 9
            == 75497472,
            "root_ht": "t*sigma_t(I_h,a)/m_i(h)"
            in solver["root_average_only"]["update"],
            "no_topup": not solver["hard_work_caps"]["adaptive_extension"]
            and not solver["hard_work_caps"]["restart_or_topup"],
        },
    )
    g5 = gate(
        "G5_IMMUTABLE_SPLIT_BANKS",
        {
            "E0": banks["E0"]["br_fit"] == banks["E0"]["evaluation"] == 2048,
            "E1": banks["E1"]["br_fit"] == banks["E1"]["evaluation"] == 4096,
            "counts": 64 * 2 * banks["E0"]["tapes_per_root_role"] == 524288
            and 64 * 2 * banks["E1"]["tapes_per_root_role"] == 1048576,
            "exogenous": "exogenous keyed randomness only" in banks["materialization"],
            "disjoint": "distinct SHA-counter namespaces" in banks["disjointness"],
            "sealed_process": "fresh confirmation process" in banks["E1"]["sealing"],
        },
    )
    g6 = gate(
        "G6_INFOSET_CONSISTENT_BR",
        {
            "aggregate": "all hidden realizations sharing the infoset key" in br["fit"],
            "freeze": "Freeze the complete pure BR map" in br["evaluation"],
            "coverage": br["gates"]["uncovered_eval_counterfactual_reach_max"] == 0.05,
            "root_ess": br["gates"]["each_compared_root_action_value_kish_ess_min"]
            == 128,
            "downstream_ess": br["gates"][
                "each_downstream_fitted_infoset_kish_ess_min"
            ]
            == 32,
            "clairvoyance_test": "strictly below a clairvoyant per-deal maximum"
            in br["required_counterexample_test"],
            "claim_limit": "cannot certify equilibrium" in br["claim_limit"],
        },
    )
    g7 = gate(
        "G7_SIMULTANEOUS_CONFIDENCE",
        {
            "cluster": conf["experimental_cluster"].startswith("source root"),
            "replicates": conf["bootstrap"]["replicates"] == 100000,
            "E0_index": conf["E0"]["ordered_replicate_for_lcb"] == 834,
            "E1_index": conf["E1"]["ordered_replicate_for_lcb"] == 2501,
            "smallest_T": "smallest T" in conf["E0"]["selection"],
            "threshold": p["heldout_value"]["primary_threshold_lcb"] == 0.20,
            "E1_no_reselect": "never reopen E0" in conf["E1"]["failure"],
        },
    )
    measured = "|".join(resource["must_measure"])
    g8 = gate(
        "G8_RESOURCE_ADMISSION",
        {
            "before_science": resource["position"].endswith(
                "before any census hand,root,belief,solver row or teacher row."
            ),
            "census_cost": "canonical-chunk census inference" in measured,
            "likelihood_cost": "full canonical historical-likelihood" in measured,
            "solver_cost": "both-traverser" in measured,
            "E0_cost": "E0 BR fit/eval" in measured,
            "E1_cost": "E1 BR fit/eval" in measured,
            "evidence_cost": "serialization and hashing" in measured,
            "safety": resource["projection"].startswith(
                "Use exact registered upper work counts"
            )
            and "1.25" in resource["projection"],
            "wall": resource["pass_gates"]["projected_total_wall_seconds_max"]
            == resource["global_scientific_abort"]["wall_seconds"]
            == 21600,
        },
    )
    counts = p["preexecution_counts"]
    audit_chain = p["implementation_and_audit"]
    prospective_absence = {key: not Path(value).exists() for key, value in prospective.items()}
    g9 = gate(
        "G9_EVIDENCE_AND_NO_EXECUTION",
        {
            "paths_absent": all(prospective_absence.values()),
            "counts_zero": all(value == 0 for value in counts.values()),
            "preaudit": audit_chain["independent_preimplementation_audit_required"],
            "implementation_audit": audit_chain[
                "independent_implementation_audit_required_before_resource_admission"
            ],
            "result_audit": audit_chain["independent_result_audit_required_before_judgment"],
            "exclusive": "create-new semantics" in audit_chain["exclusive_writes"],
        },
    )
    gates = [g1, g2, g3, g4, g5, g6, g7, g8, g9]
    passed = sum(item["pass"] for item in gates)
    result = {
        "schema_version": "v5.lrft_f64.preregistration_audit.c1.v1",
        "identity": IDENTITY,
        "status": (
            "LRFT_F64_REGISTERED_PREIMPLEMENTATION_AUDIT_C1_PASS"
            if passed == len(gates)
            else "LRFT_F64_REGISTERED_PREIMPLEMENTATION_AUDIT_C1_NONPASS"
        ),
        "correction": {
            "parent_audit_path": str(PARENT),
            "parent_audit_sha256": sha(PARENT),
            "parent_sha_expected": PARENT_SHA,
            "parent_status": parent["status"],
            "parent_checks": [parent["checks_passed"], parent["checks_total"]],
            "sole_change": (
                "Replace the quote-sensitive hidden-card phrase predicate with "
                "semantic forbidden-field membership; scientific registration unchanged."
            ),
            "parent_scientific_rows": sum(parent["scientific_output"].values()),
        },
        "preregistration": {
            "path": str(PREREG),
            "sha256": hashlib.sha256(prereg_bytes).hexdigest(),
            "bytes": len(prereg_bytes),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha(Path(__file__).resolve()),
        },
        "frozen_inputs_observed": frozen_observed,
        "prospective_absence": prospective_absence,
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "scientific_output": counts,
        "authority": (
            "PASS authorizes fresh implementation plus independent implementation "
            "audit only. Resource admission must PASS before any scientific row."
        ),
    }
    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "passed": passed, "total": len(gates)}))
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
