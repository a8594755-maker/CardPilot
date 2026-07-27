#!/usr/bin/env python3
"""Independent no-model preimplementation audit for LRFT-F8R4."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any

from scipy.stats import t as student_t


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "165822f101c1da7589cb3a605d16abbc"
IDENTITY = TOKEN + "1c2da669f170591b0f9d2ee3c5cedbad"
PREREG = ROOT / "reports" / (
    f"v5_lrft_f8r4_preregistration_{TOKEN}_20260723.json"
)
OUT = ROOT / "reports" / (
    f"v5_lrft_f8r4_preregistration_audit_{TOKEN}_20260723.json"
)
EXPECTED_PREREG_SHA = (
    "b72590708e3f13bf41044fcade01ff13b57a61fa5a9c29adcd267053cef6702c"
)

F8R3_PREREG = ROOT / "reports" / (
    "v5_lrft_f8r3_preregistration_"
    "d47c166ce97cd20019b0ff31df8045a6_20260723.json"
)
F8R3_FAILURE = ROOT / "reports" / (
    "v5_lrft_f8r3_preimplementation_structural_design_failure_"
    "d47c166ce97cd20019b0ff31df8045a6_20260723.json"
)
F8R1C1_RESOURCE = ROOT / "reports" / (
    "lrft_f8r1c1_80f4f9d2e7e6c7f4bc9f6dc82e7f2e89"
) / "resource_admission.json"

AUTHORITY_FILES = {
    "agents_sha256": (
        ROOT / "AGENTS.md",
        "6d8056b4d708d32867e8f75c59fbad291cd1813010901d1796bf269becd84419",
    ),
    "f8r3_preregistration_sha256": (
        F8R3_PREREG,
        "66cfde7ae673d5caff748203f3d8aa88aa5bf011d362c5191d9b64adad709e46",
    ),
    "f8r3_failure_sha256": (
        F8R3_FAILURE,
        "b6313544da478498eab20520b296d537f34a0d9bf3932dccc332d6e3ec018529",
    ),
    "f8r1c1_resource_result_sha256": (
        F8R1C1_RESOURCE,
        "6783a63c3026303a4144b8b3a4b08cfa20ed5d91eb194d11f05348368fe3d367",
    ),
}

INPUT_FILES = {
    "h11_checkpoint": (
        ROOT / "models" / "alpha_holdem_v5_hybrid"
        / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
        / "h11_control_endpoint.pt",
        "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13",
    ),
    "network": (
        ROOT / "scripts" / "alpha_holdem" / "network_hybrid_h1.py",
        "25f4520d31f4ce5ffcfd23fc0d56b8736fd3b5fad537706b9cd13ee270b4a171",
    ),
    "showdown": (
        ROOT / "scripts" / "deep_cfr" / "hand_eval.py",
        "fc30df48b0ae0091311f2ff40f8e320278bc47abba606c0c1f71fcce498f490d",
    ),
    "encoder_oracle": (
        ROOT / "scripts" / "alpha_holdem" / "environment_v55.py",
        "3ab591176a8119d21ac11e043bdfef72bd30b8842e34a9fea45cdd36b945f9de",
    ),
}

ZERO_KEYS = (
    "implementation_files",
    "model_calls",
    "resource_rows",
    "census_hands",
    "roots",
    "belief_rows",
    "traversals",
    "outcomes",
    "E0_tapes",
    "E1_tapes",
    "teacher_rows",
    "checkpoints",
    "slumbot_hands",
    "official_hands",
)


def sha256(path: Path) -> str:
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


def gate(name: str, predicates: dict[str, bool], evidence: Any) -> dict[str, Any]:
    native = {key: bool(value) for key, value in predicates.items()}
    return {
        "name": name,
        "pass": all(native.values()),
        "predicates": native,
        "evidence": evidence,
    }


def analytic_stats(samples: list[list[float]]) -> dict[str, float]:
    means = [statistics.fmean(row) for row in samples]
    variances = [statistics.variance(row) for row in samples]
    ns = [len(row) for row in samples]
    theta = sum(means) / 8.0
    components = [
        variances[index] / (64.0 * ns[index]) for index in range(8)
    ]
    variance = sum(components)
    if variance == 0.0:
        return {"theta": theta, "V": 0.0, "df": math.inf, "LCB": theta}
    denominator = sum(
        components[index] ** 2 / (ns[index] - 1) for index in range(8)
    )
    df = variance**2 / denominator
    lcb = theta - float(student_t.ppf(0.95, df)) * math.sqrt(variance)
    return {"theta": theta, "V": variance, "df": df, "LCB": lcb}


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")

    prereg_raw = PREREG.read_bytes()
    prereg = json.loads(prereg_raw)
    resource = read_json(F8R1C1_RESOURCE)
    identity = prereg["identity"]
    basis = identity["basis"]
    recomputed_identity = hashlib.sha256(basis.encode("utf-8")).hexdigest()

    authority_observed = {
        key: sha256(path) for key, (path, _expected) in AUTHORITY_FILES.items()
    }
    input_observed = {
        key: sha256(path) for key, (path, _expected) in INPUT_FILES.items()
    }
    prospective = {
        key: {"path": path, "exists": Path(path).exists()}
        for key, path in prereg["prospective_paths"].items()
    }

    work = prereg["exact_science_work"]
    totals = work["totals"]
    solver = prereg["solver"]
    e0 = prereg["E0"]
    e1 = prereg["E1"]
    hybrid = prereg["hybrid_continuation"]
    caps = hybrid["caps"]
    resource_registration = prereg["resource_admission"]
    envelope = resource_registration["total_padding_envelope"]

    roots = 8
    replicas = solver["replicas"]
    iterations = solver["iterations_per_replica"]
    traversers = solver["traversers"]
    cap = hybrid["P256_post_root_action_cap"]
    solver_traversals = roots * replicas * iterations * traversers
    solver_outcomes = solver_traversals * 9
    solver_actions = solver_outcomes * cap
    e0_outcomes = roots * e0["tapes_per_root"] * len(e0["profiles"])
    e1_outcomes = roots * e1["tapes_per_root"] * len(e1["profiles"])
    e0_actions = e0_outcomes * cap
    e1_actions = e1_outcomes * cap
    total_outcomes = solver_outcomes + e0_outcomes + e1_outcomes
    passive_outcomes = math.floor(total_outcomes * hybrid["rates"]["global_max"])
    passive_actions = passive_outcomes * caps["passive_actions_per_outcome_max"]
    base_actions = (
        work["census"]["base_actions"]
        + solver_actions
        + e0_actions
        + e1_actions
    )
    complete_scheduler_cap = (
        base_actions
        + caps["passive_action_transitions_terminal_cap"]
        + caps["chance_operations_terminal_cap"]
    )

    lane_counts_ok = True
    lane_min = 2048
    lane_max = 0
    for logical in range(512):
        counts = [0] * 512
        for iteration in range(iterations):
            counts[(logical + 73 * iteration) % 512] += 1
        lane_min = min(lane_min, min(counts))
        lane_max = max(lane_max, max(counts))
        lane_counts_ok &= set(counts) == {4}

    rates = {
        stage["name"]: stage["minimum_rates"] for stage in resource["stages"]
    }
    canonical_rate = rates["canonical_batch256_and_cpu_f64_cdf"]["canonical_calls"]
    p256_rate = rates[
        "permanent512_two_chunk_p256_and_cpu_f64_cdf"
    ]["p256_calls"]
    transition_rate = rates[
        "fresh_exact_cent_vector_transitions"
    ]["exact_cent_transitions"]
    joint_rates = rates["joint_logsumexp_q_sampling_mu_over_q"]
    evidence_rates = rates["exclusive_outcome_serialization_and_hash"]
    canonical_calls = work["census"]["calls"] + work["history"]["calls"]
    padded_p256_calls = envelope["network_calls"] - canonical_calls
    stage_projection = {
        "canonical_network": canonical_calls / canonical_rate,
        "p256_network": padded_p256_calls / p256_rate,
        "scheduler_operations": (
            envelope["scheduler_operations_including_base_passive_and_chance"]
            / transition_rate
        ),
        "joint_and_proposal": max(
            work["joint_entries"] / joint_rates["joint_entries"],
            work["proposal_samples"] / joint_rates["proposal_samples"],
        ),
        "evidence": max(
            envelope["outcomes"] / evidence_rates["outcome_records"],
            envelope["artifact_bytes"] / evidence_rates["artifact_bytes"],
        ),
    }
    fixed_projection = sum(
        (
            resource["projection"]["fixed_load_seconds"],
            resource["projection"]["fixed_model_metamorphic_seconds"],
            resource["projection"]["fixed_finalization"]["elapsed_seconds"],
        )
    )
    projection = fixed_projection + resource["projection"]["variable_safety_factor"] * sum(
        stage_projection.values()
    )

    fixture = analytic_stats([[0.0, 1.0, 2.0, 3.0] for _ in range(8)])
    degenerate_fixture = analytic_stats([[0.25, 0.25] for _ in range(8)])

    registered_inputs = prereg["runtime_inputs"]
    registered_authority = prereg["authority"]
    gates = [
        gate(
            "G1_IDENTITY_AND_PREREGISTRATION",
            {
                "sha_exact": hashlib.sha256(prereg_raw).hexdigest()
                == EXPECTED_PREREG_SHA,
                "schema": prereg["schema_version"]
                == "v5.lrft_f8r4.preregistration.v1",
                "status": prereg["status"]
                == "REGISTERED_PREIMPLEMENTATION_AUDIT_REQUIRED",
                "design": prereg["design_id"]
                == "LRFT_F8R4_FIXED8_COMPLETE_SCHEDULER_ENVELOPE_ANALYTIC_SCREEN",
                "identity_recomputed": recomputed_identity == IDENTITY,
                "identity_stored": identity["sha256"] == IDENTITY,
                "token": identity["token"] == TOKEN,
            },
            {
                "preregistration_sha256": hashlib.sha256(prereg_raw).hexdigest(),
                "basis": basis,
                "recomputed_identity": recomputed_identity,
            },
        ),
        gate(
            "G2_AUTHORITY_AND_INPUT_HASHES",
            {
                "authority_registered": all(
                    registered_authority[key] == expected
                    for key, (_path, expected) in AUTHORITY_FILES.items()
                ),
                "authority_observed": all(
                    authority_observed[key] == expected
                    for key, (_path, expected) in AUTHORITY_FILES.items()
                ),
                "inputs_registered": (
                    registered_inputs["h11_checkpoint"]["sha256"]
                    == INPUT_FILES["h11_checkpoint"][1]
                    and registered_inputs["network"]["sha256"]
                    == INPUT_FILES["network"][1]
                    and registered_inputs["showdown"]["sha256"]
                    == INPUT_FILES["showdown"][1]
                    and registered_inputs["encoder_oracle"]["sha256"]
                    == INPUT_FILES["encoder_oracle"][1]
                ),
                "inputs_observed": all(
                    input_observed[key] == expected
                    for key, (_path, expected) in INPUT_FILES.items()
                ),
                "f8r3_frozen": (
                    read_json(F8R3_FAILURE)["status"]
                    == "LRFT_F8R3_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_RESOURCE_PADDING_DOUBLE_COUNT"
                ),
            },
            {
                "authority_observed": authority_observed,
                "input_observed": input_observed,
            },
        ),
        gate(
            "G3_RUNTIME_AND_PROSPECTIVE_PATHS",
            {
                "python": ".".join(map(str, sys.version_info[:3]))
                == registered_inputs["versions"]["python"],
                "numpy": importlib.metadata.version("numpy")
                == registered_inputs["versions"]["numpy"],
                "scipy": importlib.metadata.version("scipy")
                == registered_inputs["versions"]["scipy"],
                "torch_metadata": importlib.metadata.version("torch")
                == registered_inputs["versions"]["torch"],
                "all_paths_absent": all(
                    not item["exists"] for item in prospective.values()
                ),
                "expected_path_count": len(prospective) == 12,
            },
            prospective,
        ),
        gate(
            "G4_EXACT_SCIENCE_FORMULAS",
            {
                "census_calls": work["census"]["calls"] == 4096 * 7,
                "census_rows": work["census"]["rows"]
                == work["census"]["calls"] * 256,
                "history_calls": work["history"]["calls"] == roots * 144,
                "history_rows": work["history"]["rows"]
                == work["history"]["calls"] * 256,
                "solver_calls": work["solver"]["calls"]
                == roots * replicas * iterations,
                "solver_rows": work["solver"]["rows"]
                == work["solver"]["calls"] * 256,
                "solver_traversals": work["solver"]["traversals"]
                == solver_traversals,
                "solver_outcomes": work["solver"]["outcomes"] == solver_outcomes,
                "solver_actions": work["solver"]["base_actions"] == solver_actions,
                "e0_outcomes": work["E0"]["outcomes"] == e0_outcomes,
                "e0_actions": work["E0"]["base_actions"] == e0_actions,
                "e1_outcomes": work["E1"]["outcomes"] == e1_outcomes,
                "e1_actions": work["E1"]["base_actions"] == e1_actions,
                "network_total": totals["network_calls"]
                == sum(work[key]["calls"] for key in ("census", "history", "solver", "E0", "E1")),
                "rows_total": totals["network_rows"]
                == sum(work[key]["rows"] for key in ("census", "history", "solver", "E0", "E1")),
                "outcomes_total": totals["outcomes"] == total_outcomes,
                "base_actions_total": totals["base_action_transitions"]
                == base_actions,
                "bootstrap_zero": totals["bootstrap_draws"] == 0,
            },
            {
                "solver_traversals": solver_traversals,
                "solver_outcomes": solver_outcomes,
                "E0_outcomes": e0_outcomes,
                "E1_outcomes": e1_outcomes,
                "total_outcomes": total_outcomes,
                "base_actions": base_actions,
            },
        ),
        gate(
            "G5_PASSIVE_CHANCE_AND_COMPLETE_SCHEDULER_CAP",
            {
                "passive_outcomes": caps["passive_outcomes_PASS_max"]
                == passive_outcomes == 36044,
                "passive_actions": caps["passive_action_transitions_PASS_max"]
                == passive_actions == 288352,
                "passive_terminal_cap": caps[
                    "passive_action_transitions_terminal_cap"
                ]
                == 288360,
                "chance_terminal_cap": caps["chance_operations_terminal_cap"]
                == 180225,
                "complete_cap_formula": complete_scheduler_cap == 6264425,
                "complete_cap_registered": totals[
                    "complete_scheduler_operation_terminal_cap"
                ]
                == complete_scheduler_cap,
                "no_unresolved_wager": "resolve wager before street advance"
                in hybrid["passive"],
                "fallback_caps_all": all(
                    value == 0.05 for value in hybrid["rates"].values()
                ),
            },
            {
                "passive_outcomes_floor": passive_outcomes,
                "passive_actions": passive_actions,
                "complete_scheduler_operation_terminal_cap": complete_scheduler_cap,
            },
        ),
        gate(
            "G6_SINGLE_RESOURCE_ENVELOPE_AND_PROJECTION",
            {
                "envelope_exact": envelope[
                    "scheduler_operations_including_base_passive_and_chance"
                ]
                == 6844416,
                "margin_formula": envelope[
                    "scheduler_operations_including_base_passive_and_chance"
                ]
                - complete_scheduler_cap
                == 579991,
                "margin_registered": envelope[
                    "margin_over_complete_science_scheduler_cap"
                ]
                == 579991,
                "no_double_count_note": envelope["note"]
                == (
                    "One total envelope. Passive and chance work are already included "
                    "and must not be added again. Extra capacity is resource-only and "
                    "cannot create scientific rows."
                ),
                "calls_padding": envelope["network_calls"] == 70784,
                "rows_padding": envelope["network_rows"]
                == envelope["network_calls"] * 256,
                "outcomes_padding": envelope["outcomes"] == 851968,
                "projection_recomputed": math.isclose(
                    projection, 5109.8081, rel_tol=0.0, abs_tol=5e-5
                ),
                "projection_registered": math.isclose(
                    resource_registration["projection_seconds"],
                    projection,
                    rel_tol=0.0,
                    abs_tol=5e-5,
                ),
                "under_limit": projection
                < resource_registration["limits"]["wall_seconds"],
                "rates_source_exact": resource["status"]
                == "LRFT_F8R1C1_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS",
            },
            {
                "stage_seconds": stage_projection,
                "fixed_seconds": fixed_projection,
                "safety_factor": resource["projection"]["variable_safety_factor"],
                "projection_seconds": projection,
                "margin": envelope[
                    "scheduler_operations_including_base_passive_and_chance"
                ]
                - complete_scheduler_cap,
            },
        ),
        gate(
            "G7_ANALYTIC_INFERENCE_FIXTURES",
            {
                "scipy_frozen": importlib.metadata.version("scipy") == "1.17.0",
                "theta": math.isclose(fixture["theta"], 1.5, abs_tol=1e-15),
                "variance": math.isclose(fixture["V"], 5 / 96, abs_tol=1e-15),
                "df": math.isclose(fixture["df"], 24.0, abs_tol=1e-12),
                "lcb": math.isclose(
                    fixture["LCB"], 1.1095463715009375, abs_tol=1e-14
                ),
                "degenerate_theta": degenerate_fixture["theta"] == 0.25,
                "degenerate_variance": degenerate_fixture["V"] == 0.0,
                "degenerate_df": math.isinf(degenerate_fixture["df"]),
                "degenerate_lcb": degenerate_fixture["LCB"] == 0.25,
                "registered_formula": prereg["analytic_inference"]["LCB"]
                == "theta-scipy.stats.t.ppf(.95,df)*sqrt(V)",
                "registered_fixed_strata": "never resample roots"
                in prereg["analytic_inference"]["scope"],
            },
            {"nondegenerate": fixture, "degenerate": degenerate_fixture},
        ),
        gate(
            "G8_LANE_SOURCE_AND_EVALUATION_CONTRACTS",
            {
                "lane_bijection": math.gcd(73, 512) == 1,
                "lane_balance": lane_counts_ok and lane_min == lane_max == 4,
                "source_not_selection": "never affects selection"
                in prereg["roots_and_belief"]["source_hole"],
                "full_joint_only": "full joint only"
                in prereg["roots_and_belief"]["joint_mu"],
                "rho_exact": "rho=1/8" in solver["proposal"],
                "weight_bound": "w<=8/7" in solver["proposal"],
                "e0_direct_mu": "sample opponent directly from mu"
                in e0["deal"],
                "e0_not_q": "never q" in e0["deal"],
                "e1_sealed": "before solver" in e1["sealed"],
                "e1_frozen_candidate": "binds candidate,A/B,E0 raw hashes"
                in e1["open"],
                "same_tape_pairing": "Same tape has same source/opponent holes"
                in prereg["rng_probability_lanes"]["evaluation_pairing"],
                "no_topup": solver["no_topup_restart_or_selection"] is True
                and e1["no_topup_reopen_candidate_or_root_change"] is True,
            },
            {
                "lane_min_count": lane_min,
                "lane_max_count": lane_max,
                "solver_iterations": iterations,
                "E0_tapes_per_root": e0["tapes_per_root"],
                "E1_tapes_per_root": e1["tapes_per_root"],
            },
        ),
        gate(
            "G9_ZERO_COUNTS_AND_NO_EXECUTION",
            {
                "all_counts_exact_zero": all(
                    type(prereg["preexecution_counts"].get(key)) is int
                    and prereg["preexecution_counts"][key] == 0
                    for key in ZERO_KEYS
                ),
                "no_model_import": "torch" not in sys.modules,
                "no_checkpoint_load": True,
                "no_network_calls": True,
                "no_resource_run": True,
                "no_science": True,
                "report_absent_before_create": not OUT.exists(),
            },
            {
                "preexecution_counts": prereg["preexecution_counts"],
                "model_imports": 0,
                "checkpoint_loads": 0,
                "network_calls": 0,
                "resource_runs": 0,
            },
        ),
    ]

    passed = sum(item["pass"] for item in gates)
    status = (
        "LRFT_F8R4_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_AUTHORIZED_ONLY"
        if passed == len(gates)
        else "LRFT_F8R4_REGISTERED_PREIMPLEMENTATION_AUDIT_NONPASS"
    )
    result = {
        "schema_version": "v5.lrft_f8r4.preregistration_audit.v1",
        "identity": IDENTITY,
        "status": status,
        "preregistration": {
            "path": str(PREREG),
            "sha256": hashlib.sha256(prereg_raw).hexdigest(),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_imports": 0,
        "checkpoint_loads": 0,
        "network_calls": 0,
        "resource_admission_runs": 0,
        "scientific_output": {
            key: 0 for key in ZERO_KEYS if key != "implementation_files"
        },
        "authority": (
            "PASS authorizes only one fresh F8R4 implementation followed by an "
            "independent no-model implementation audit. It authorizes no model load, "
            "resource admission, scientific row, checkpoint, Slumbot hand, or claim."
        ),
    }

    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({
        "status": status,
        "passed": passed,
        "total": len(gates),
        "path": str(OUT),
    }))
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
