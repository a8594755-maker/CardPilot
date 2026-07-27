#!/usr/bin/env python3
"""Fresh independent C1 preimplementation audit for LRFT-F8R4."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import statistics
import sys

from scipy.stats import t as student_t


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "165822f101c1da7589cb3a605d16abbc"
IDENTITY = TOKEN + "1c2da669f170591b0f9d2ee3c5cedbad"
PREREG = ROOT / "reports" / f"v5_lrft_f8r4_preregistration_{TOKEN}_20260723.json"
OUT = ROOT / "reports" / f"v5_lrft_f8r4_preregistration_audit_c1_{TOKEN}_20260723.json"
PREREG_SHA = "b72590708e3f13bf41044fcade01ff13b57a61fa5a9c29adcd267053cef6702c"
AUTHORITY = {
    "agents_sha256": (ROOT / "AGENTS.md", "6d8056b4d708d32867e8f75c59fbad291cd1813010901d1796bf269becd84419"),
    "f8r3_preregistration_sha256": (
        ROOT / "reports" / "v5_lrft_f8r3_preregistration_d47c166ce97cd20019b0ff31df8045a6_20260723.json",
        "66cfde7ae673d5caff748203f3d8aa88aa5bf011d362c5191d9b64adad709e46",
    ),
    "f8r3_failure_sha256": (
        ROOT / "reports" / "v5_lrft_f8r3_preimplementation_structural_design_failure_d47c166ce97cd20019b0ff31df8045a6_20260723.json",
        "b6313544da478498eab20520b296d537f34a0d9bf3932dccc332d6e3ec018529",
    ),
    "f8r1c1_resource_result_sha256": (
        ROOT / "reports" / "lrft_f8r1c1_80f4f9d2e7e6c7f4bc9f6dc82e7f2e89" / "resource_admission.json",
        "6783a63c3026303a4144b8b3a4b08cfa20ed5d91eb194d11f05348368fe3d367",
    ),
}
INPUTS = {
    "h11_checkpoint": (
        ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt",
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


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def gate(name: str, checks: dict[str, bool], evidence: object) -> dict[str, object]:
    checks = {key: bool(value) for key, value in checks.items()}
    return {"name": name, "pass": all(checks.values()), "predicates": checks, "evidence": evidence}


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    raw = PREREG.read_bytes()
    p = json.loads(raw)
    work = p["exact_science_work"]
    total = work["totals"]
    caps = p["hybrid_continuation"]["caps"]
    env = p["resource_admission"]["total_padding_envelope"]
    resource_path = AUTHORITY["f8r1c1_resource_result_sha256"][0]
    resource = json.loads(resource_path.read_text(encoding="utf-8"))

    roots, replicas, iterations, traversers, depth_cap = 8, 2, 2048, 2, 8
    solver_traversals = roots * replicas * iterations * traversers
    solver_outcomes = solver_traversals * 9
    e0_outcomes = roots * 2048 * 4
    e1_outcomes = roots * 4096 * 2
    outcomes = solver_outcomes + e0_outcomes + e1_outcomes
    base_actions = 28672 + (solver_outcomes + e0_outcomes + e1_outcomes) * depth_cap
    passive_outcomes = math.floor(outcomes * 0.05)
    passive_actions = passive_outcomes * 8
    scheduler_cap = base_actions + 288360 + 180225

    lane_balanced = True
    for logical in range(512):
        counts = [0] * 512
        for iteration in range(2048):
            counts[(logical + 73 * iteration) % 512] += 1
        lane_balanced &= set(counts) == {4}

    stages = {item["name"]: item["minimum_rates"] for item in resource["stages"]}
    fixed = (
        resource["projection"]["fixed_load_seconds"]
        + resource["projection"]["fixed_model_metamorphic_seconds"]
        + resource["projection"]["fixed_finalization"]["elapsed_seconds"]
    )
    stage_seconds = {
        "canonical": 29824 / stages["canonical_batch256_and_cpu_f64_cdf"]["canonical_calls"],
        "p256": (70784 - 29824) / stages["permanent512_two_chunk_p256_and_cpu_f64_cdf"]["p256_calls"],
        "scheduler": 6844416 / stages["fresh_exact_cent_vector_transitions"]["exact_cent_transitions"],
        "joint": max(
            12994800 / stages["joint_logsumexp_q_sampling_mu_over_q"]["joint_entries"],
            65536 / stages["joint_logsumexp_q_sampling_mu_over_q"]["proposal_samples"],
        ),
        "evidence": max(
            851968 / stages["exclusive_outcome_serialization_and_hash"]["outcome_records"],
            2147483648 / stages["exclusive_outcome_serialization_and_hash"]["artifact_bytes"],
        ),
    }
    projection = fixed + 1.25 * sum(stage_seconds.values())

    fixture_rows = [[0.0, 1.0, 2.0, 3.0] for _ in range(8)]
    means = [statistics.fmean(row) for row in fixture_rows]
    variances = [statistics.variance(row) for row in fixture_rows]
    theta = sum(means) / 8
    components = [value / (64 * 4) for value in variances]
    variance = sum(components)
    df = variance**2 / sum(value**2 / 3 for value in components)
    lcb = theta - float(student_t.ppf(0.95, df)) * math.sqrt(variance)

    auth_observed = {key: digest(path) for key, (path, _) in AUTHORITY.items()}
    input_observed = {key: digest(path) for key, (path, _) in INPUTS.items()}
    ri = p["runtime_inputs"]
    prospective = {key: Path(value).exists() for key, value in p["prospective_paths"].items()}
    zeros = p["preexecution_counts"]
    zero_keys = (
        "implementation_files", "model_calls", "resource_rows", "census_hands",
        "roots", "belief_rows", "traversals", "outcomes", "E0_tapes", "E1_tapes",
        "teacher_rows", "checkpoints", "slumbot_hands", "official_hands",
    )
    interpretation = {
        "E1_inaccessible": (
            "A process/call-graph isolation obligation: solver and E0 receive neither "
            "the E1 artifact path nor a seed reader. It is not a secrecy claim. The "
            "implementation audit must reject any read edge before the E1-open process."
        ),
        "rng_key_tuples": (
            "The preregistered identity-keyed counter construction and disjoint domains "
            "are sufficient before source exists; exact tuple schemas and phase-output "
            "schemas must be frozen in the audited implementation before any model or science."
        ),
        "root_average": (
            "S+=t*sigma occurs exactly once per root/replica/iteration before the simultaneous "
            "two-traverser update; it is the root actor policy stream and D=sum(1..2048)."
        ),
        "work_semantics": (
            "Network schedule is fixed/padded as registered. base_action_transitions, passive "
            "actions, chance operations and complete scheduler operations are conservative "
            "resource caps; result evidence records actual non-padding transitions and must "
            "not synthesize scientific no-op rows."
        ),
    }

    gates = [
        gate("G1_IDENTITY", {
            "prereg_sha": hashlib.sha256(raw).hexdigest() == PREREG_SHA,
            "identity": hashlib.sha256(p["identity"]["basis"].encode()).hexdigest() == IDENTITY == p["identity"]["sha256"],
            "token": p["identity"]["token"] == TOKEN,
            "schema_status": p["schema_version"] == "v5.lrft_f8r4.preregistration.v1"
            and p["status"] == "REGISTERED_PREIMPLEMENTATION_AUDIT_REQUIRED",
        }, {"prereg_sha256": hashlib.sha256(raw).hexdigest(), "identity": IDENTITY}),
        gate("G2_AUTHORITY_INPUTS", {
            "authority_registered": all(p["authority"][key] == expected for key, (_, expected) in AUTHORITY.items()),
            "authority_observed": all(auth_observed[key] == expected for key, (_, expected) in AUTHORITY.items()),
            "inputs_observed": all(input_observed[key] == expected for key, (_, expected) in INPUTS.items()),
            "inputs_registered": (
                ri["h11_checkpoint"]["sha256"] == INPUTS["h11_checkpoint"][1]
                and ri["network"]["sha256"] == INPUTS["network"][1]
                and ri["showdown"]["sha256"] == INPUTS["showdown"][1]
                and ri["encoder_oracle"]["sha256"] == INPUTS["encoder_oracle"][1]
            ),
        }, {"authority": auth_observed, "inputs": input_observed}),
        gate("G3_PATH_RUNTIME_ZERO", {
            "all_prospective_absent": all(not value for value in prospective.values()),
            "python": ".".join(map(str, sys.version_info[:3])) == ri["versions"]["python"],
            "numpy": importlib.metadata.version("numpy") == ri["versions"]["numpy"],
            "scipy": importlib.metadata.version("scipy") == ri["versions"]["scipy"],
            "torch_metadata": importlib.metadata.version("torch") == ri["versions"]["torch"],
            "all_zero": all(type(zeros.get(key)) is int and zeros[key] == 0 for key in zero_keys),
            "torch_not_imported": "torch" not in sys.modules,
        }, {"prospective_exists": prospective, "preexecution_counts": zeros}),
        gate("G4_SCIENCE_CAP_FORMULAS", {
            "solver_traversals": work["solver"]["traversals"] == solver_traversals == 65536,
            "solver_outcomes": work["solver"]["outcomes"] == solver_outcomes == 589824,
            "e0_outcomes": work["E0"]["outcomes"] == e0_outcomes == 65536,
            "e1_outcomes": work["E1"]["outcomes"] == e1_outcomes == 65536,
            "outcomes": total["outcomes"] == outcomes == 720896,
            "base_action_cap": total["base_action_transitions"] == base_actions == 5795840,
            "network_calls": total["network_calls"] == 66688,
            "network_rows": total["network_rows"] == total["network_calls"] * 256 == 17072128,
            "bootstrap_zero": total["bootstrap_draws"] == 0,
        }, {"outcomes": outcomes, "base_action_cap": base_actions}),
        gate("G5_COMPLETE_SCHEDULER_ENVELOPE", {
            "passive_outcomes": caps["passive_outcomes_PASS_max"] == passive_outcomes == 36044,
            "passive_actions": caps["passive_action_transitions_PASS_max"] == passive_actions == 288352,
            "terminal_passive_cap": caps["passive_action_transitions_terminal_cap"] == 288360,
            "terminal_chance_cap": caps["chance_operations_terminal_cap"] == 180225,
            "complete_cap": total["complete_scheduler_operation_terminal_cap"] == scheduler_cap == 6264425,
            "one_envelope": env["scheduler_operations_including_base_passive_and_chance"] == 6844416,
            "margin": env["scheduler_operations_including_base_passive_and_chance"] - scheduler_cap
            == env["margin_over_complete_science_scheduler_cap"] == 579991,
            "no_double_count": "must not be added again" in env["note"],
        }, {"scheduler_cap": scheduler_cap, "resource_envelope": 6844416, "margin": 579991}),
        gate("G6_FROZEN_RATE_PROJECTION", {
            "resource_identity": resource["identity"] == "80f4f9d2e7e6c7f4bc9f6dc82e7f2e896bd0c3ff56dd542eec58b239d1422619",
            "projection": math.isclose(projection, 5109.8081, abs_tol=5e-5, rel_tol=0),
            "registered_projection": math.isclose(p["resource_admission"]["projection_seconds"], projection, abs_tol=5e-5, rel_tol=0),
            "under_limit": projection < p["resource_admission"]["limits"]["wall_seconds"],
        }, {"stage_seconds": stage_seconds, "fixed_seconds": fixed, "projection_seconds": projection}),
        gate("G7_INFERENCE_LANES_PHASE_CONTRACTS", {
            "fixture_theta": math.isclose(theta, 1.5, abs_tol=1e-15),
            "fixture_variance": math.isclose(variance, 5 / 96, abs_tol=1e-15),
            "fixture_df": math.isclose(df, 24, abs_tol=1e-12),
            "fixture_lcb": math.isclose(lcb, 1.1095463715009375, abs_tol=1e-14),
            "degenerate_rule": "df=+inf,LCB=theta" in p["analytic_inference"]["degenerate"],
            "lane_balance": math.gcd(73, 512) == 1 and lane_balanced,
            "source_excluded_from_selection": "never affects selection" in p["roots_and_belief"]["source_hole"],
            "e0_mu_not_q": "sample opponent directly from mu" in p["E0"]["deal"] and "never q" in p["E0"]["deal"],
            "e1_pre_solver_seal": "before solver" in p["E1"]["sealed"],
            "root_average_once": p["solver"]["root_average"].startswith("Before update S+=t*sigma,D=2048*2049/2"),
        }, {"fixture": {"theta": theta, "V": variance, "df": df, "LCB": lcb}, "degenerate_df": "+inf", "interpretation": interpretation}),
    ]

    passed = sum(item["pass"] for item in gates)
    status = (
        "LRFT_F8R4_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_AUTHORIZED_ONLY"
        if passed == len(gates)
        else "LRFT_F8R4_REGISTERED_PREIMPLEMENTATION_AUDIT_NONPASS"
    )
    result = {
        "schema_version": "v5.lrft_f8r4.preregistration_audit_c1.v1",
        "identity": IDENTITY,
        "status": status,
        "preregistration_sha256": hashlib.sha256(raw).hexdigest(),
        "audit_source_sha256": digest(Path(__file__).resolve()),
        "parent_preoutput_failure": "LRFT_F8R4_PREREGISTRATION_AUDIT_PREOUTPUT_NONFINITE_FIXTURE_SERIALIZATION_FAILURE",
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_imports": 0,
        "checkpoint_loads": 0,
        "network_calls": 0,
        "resource_admission_runs": 0,
        "scientific_rows": 0,
        "authority": "PASS authorizes only fresh F8R4 implementation and independent no-model implementation audit.",
    }
    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": status, "passed": passed, "total": len(gates), "path": str(OUT)}))
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
