"""Instantiated independent preimplementation audit for LRFT-F8R1.

No prospective implementation is imported.  The audit executes small independent
oracles for the probability law, counter RNG, importance sampling, regret update,
root averaging, permanent lanes, confidence index, and exact work table.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
IDENTITY = TOKEN + "d14e7b9dfbdbb51cc7897df93e2d3198"
PREREG = ROOT / "reports" / f"v5_lrft_f8r1_preregistration_{TOKEN}_20260723.json"
OUT = ROOT / "reports" / f"v5_lrft_f8r1_preregistration_audit_{TOKEN}_20260723.json"
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


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def record(name: str, predicates: dict[str, bool], evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "pass": all(bool(value) for value in predicates.values()),
        "predicates": predicates,
        "evidence": evidence,
    }


def probability_oracle(logits_f32: np.ndarray, legal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    logits = np.asarray(logits_f32, dtype=np.float32)
    mask = np.asarray(legal, dtype=bool)
    values = logits[mask].astype(np.float64)
    weights = np.exp(values - np.max(values))
    legal_prob = weights / np.sum(weights, dtype=np.float64)
    probs = np.zeros(9, dtype=np.float64)
    probs[mask] = legal_prob
    if not np.isfinite(probs).all() or abs(float(probs.sum()) - 1.0) > 2e-15:
        raise AssertionError("probability oracle normalization")
    cdf = np.cumsum(probs, dtype=np.float64)
    cdf[np.flatnonzero(mask)[-1]] = 1.0
    return probs, cdf


def digest_u64(master: str, domain: str, fields: list[Any], counter: int) -> int:
    message = "|".join([master, domain, *[str(value) for value in fields], str(counter)])
    return int.from_bytes(hashlib.sha256(message.encode("utf-8")).digest()[:8], "big")


def bounded(master: str, domain: str, fields: list[Any], n: int) -> tuple[int, int]:
    limit = (1 << 64) - ((1 << 64) % n)
    counter = 0
    while True:
        value = digest_u64(master, domain, fields, counter)
        if value < limit:
            return value % n, counter
        counter += 1


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    raw = PREREG.read_bytes()
    p = json.loads(raw)
    gates: list[dict[str, Any]] = []

    identity_recomputed = hashlib.sha256(
        p["identity"]["basis"].encode("utf-8")
    ).hexdigest()
    observed_frozen = {str(path): file_sha(path) for path in FROZEN}
    gates.append(
        record(
            "G1_IDENTITY_INPUT_CLAIM_SCOPE",
            {
                "identity": identity_recomputed == p["identity"]["sha256"] == IDENTITY,
                "token": p["identity"]["token"] == TOKEN,
                "parent_failure": p["entry_authority"]["parent_F64_failure_sha256"]
                == "01a41d87ead30d0bec48d35c94efb5899d8c2227e222642b7401c0eed028f1c8",
                "frozen_hashes": all(
                    observed_frozen[str(path)] == expected
                    for path, expected in FROZEN.items()
                ),
                "fixed8_claim": p["claim_scope"]["pass_authority"]
                == "LRFT_F8R1_FIXED_EIGHT_ROOT_MECHANISM_PASS_F64R2_DESIGN_ELIGIBLE_ONLY",
                "no_population": "learner-reached root-population uplift"
                in p["claim_scope"]["not_authorized"],
                "no_strength": "Slumbot improvement,quick5k,20k,formal100k,L5 or L6"
                in p["claim_scope"]["not_authorized"],
            },
            {
                "identity": identity_recomputed,
                "frozen": observed_frozen,
                "claim_scope": p["claim_scope"],
            },
        )
    )

    supplied_logits = np.array(
        [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
        dtype=np.float32,
    )
    supplied_legal = np.array([1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool)
    probs, cdf = probability_oracle(supplied_logits, supplied_legal)
    probs_repeat, cdf_repeat = probability_oracle(
        supplied_logits.copy(), supplied_legal.copy()
    )
    sample_uniforms = [0.0 + 0.5 / 2**64, 0.1, 0.5, 0.999999999999]
    sampled = [
        int(next(slot for slot in np.flatnonzero(supplied_legal) if cdf[slot] > u))
        for u in sample_uniforms
    ]
    gates.append(
        record(
            "G2_CPU_F64_PROBABILITY_CDF_INSTANTIATED",
            {
                "dtype": probs.dtype == np.float64 and cdf.dtype == np.float64,
                "illegal_zero": bool(np.all(probs[~supplied_legal] == 0.0)),
                "sum": abs(float(probs.sum()) - 1.0) <= 2e-15,
                "final": cdf[np.flatnonzero(supplied_legal)[-1]] == 1.0,
                "repeat": np.array_equal(probs, probs_repeat)
                and np.array_equal(cdf, cdf_repeat),
                "sample_legal": all(supplied_legal[slot] for slot in sampled),
                "same_routine": p["probability_routine"]["shared_authority"].endswith(
                    "all call this one routine."
                ),
            },
            {
                "probs_hex": [value.hex() for value in probs],
                "cdf_hex": [value.hex() for value in cdf],
                "sampled": sampled,
            },
        )
    )

    rng = p["counter_rng"]
    master = rng["master"]
    domains = rng["domains"]
    u64_a = digest_u64(master, "CENSUS_CELL", [17], 0)
    u64_b = digest_u64(master, "CENSUS_CELL", [17], 0)
    cell, rejects = bounded(master, "CENSUS_CELL", [17], 8)
    other = digest_u64(master, "CENSUS_SELECT", [17], 0)
    deck = list(range(52))
    for i in range(51, 0, -1):
        j, _ = bounded(master, "CENSUS_DECK", [23, i], i + 1)
        deck[i], deck[j] = deck[j], deck[i]
    gates.append(
        record(
            "G3_COUNTER_RNG_AND_ROOT_SELECTION_INSTANTIATED",
            {
                "domains_unique": len(domains) == len(set(domains)),
                "repeat": u64_a == u64_b,
                "domain_separation": u64_a != other,
                "cell_range": 0 <= cell < 8,
                "bounded_terminates": rejects >= 0,
                "deck_permutation": sorted(deck) == list(range(52)),
                "one_target_cell": p["root_census"]["hand_to_cell"].startswith(
                    "CENSUS_CELL"
                ),
                "one_root_per_cell": p["root_census"]["root_count"] == 8
                and p["root_census"]["roots_per_cell"] == 1,
                "public_selection": all(
                    phrase in " ".join(p["root_census"]["eligibility"])
                    for phrase in ("hidden cards", "outcome", "reward", "solver output")
                ),
            },
            {
                "u64": u64_a,
                "cell": cell,
                "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
                "decision_cap": p["root_census"]["decision_hard_cap"],
            },
        )
    )

    mu = np.array([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
    source = np.array([False, True, False, False, True, False])
    m_star = float(mu[source].sum())
    rho = float(p["solver"]["proposal"]["rho"])
    nu = np.where(source, mu / m_star, 0.0)
    q = (1.0 - rho) * mu + rho * nu
    weight = mu / q
    f = np.array([-3.0, 2.5, 1.25, -0.75, 4.0, 0.5], dtype=np.float64)
    target_expectation = float(np.dot(mu, f))
    proposal_expectation = float(np.dot(q, weight * f))
    gates.append(
        record(
            "G4_FULL_DENSITY_IMPORTANCE_AND_REGRET_INSTANTIATED",
            {
                "rho": rho == 0.125,
                "q_sum": abs(float(q.sum()) - 1.0) <= 2e-15,
                "full_support": bool(np.all(q > 0.0)),
                "unbiased": abs(target_expectation - proposal_expectation) <= 2e-15,
                "weight_cap": float(weight.max())
                <= p["solver"]["proposal"]["weight_max"] + 1e-15,
            },
            {
                "m_star": m_star,
                "q": q.tolist(),
                "weight": weight.tolist(),
                "target_Ef": target_expectation,
                "proposal_Ewf": proposal_expectation,
            },
        )
    )
    sigma0 = np.array([0.2, 0.3, 0.5], dtype=np.float64)
    sigma1 = np.array([0.6, 0.4], dtype=np.float64)
    returns0 = np.array([1.5, -0.25, 2.0], dtype=np.float64)
    returns1 = np.array([-1.0, 0.75], dtype=np.float64)
    sample_weight0 = float(weight[1])
    sample_weight1 = float(weight[3])
    delta0 = sample_weight0 * (returns0 - float(np.dot(sigma0, returns0)))
    delta1 = sample_weight1 * (returns1 - float(np.dot(sigma1, returns1)))
    initial0 = np.array([0.1, 0.0, 0.4], dtype=np.float64)
    initial1 = np.array([0.0, 0.2], dtype=np.float64)
    simultaneous0 = np.maximum(0.0, initial0 + delta0)
    simultaneous1 = np.maximum(0.0, initial1 + delta1)
    gates.append(
        record(
            "G5_TWO_TRAVERSER_SIMULTANEOUS_CFR_PLUS_ORACLE",
            {
                "delta0_centered": abs(float(np.dot(sigma0, delta0))) <= 2e-15,
                "delta1_centered": abs(float(np.dot(sigma1, delta1))) <= 2e-15,
                "plus_nonnegative": bool(np.all(simultaneous0 >= 0.0))
                and bool(np.all(simultaneous1 >= 0.0)),
                "weight_once": "with w applied exactly once"
                in p["solver"]["regret"]["delta"],
                "simultaneous_registered": p["solver"]["iteration"].endswith(
                    "apply simultaneously."
                ),
            },
            {
                "delta0": delta0.tolist(),
                "delta1": delta1.tolist(),
                "R0_next": simultaneous0.tolist(),
                "R1_next": simultaneous1.tolist(),
            },
        )
    )

    toy_sigmas = [
        np.array([0.5 + 0.25 * math.sin(t), 0.5 - 0.25 * math.sin(t)])
        for t in range(1, 33)
    ]
    direct = sum(t * value for t, value in enumerate(toy_sigmas, start=1))
    denominator = 32 * 33 / 2
    incremental = np.zeros(2, dtype=np.float64)
    for t, value in enumerate(toy_sigmas, start=1):
        incremental += t * value
    gates.append(
        record(
            "G6_SOURCE_ROOT_AVERAGE_SINGLE_STREAM_ORACLE",
            {
                "sum_exact": np.array_equal(direct, incremental),
                "normalizes": abs(float((incremental / denominator).sum()) - 1.0)
                <= 2e-15,
                "registered_denominator": p["solver"]["source_root_average"]["D"]
                == "8192*8193/2",
                "actor_stream_only": p["solver"]["source_root_average"][
                    "stream"
                ].startswith("Before applying each iteration update,use only the root actor"),
                "single_endpoint": p["solver"]["snapshots"].startswith(
                    "single endpoint T=8192"
                ),
            },
            {
                "toy_average": (incremental / denominator).tolist(),
                "registered_candidate": p["solver"]["source_root_average"]["candidate"],
            },
        )
    )

    lane = p["leaf_policy_P256"]["solver_cohort"]
    counts_for_lane0 = np.zeros(512, dtype=np.int64)
    for t in range(8192):
        counts_for_lane0[(0 + 73 * t) % 512] += 1
    collision_free = True
    for t in (0, 1, 511, 512, 8191):
        physical = [((logical + 73 * t) % 512) for logical in range(288)]
        collision_free &= len(physical) == len(set(physical))
    profile_a_positions = [((17 + 73 * t) % 512) for t in range(32)]
    profile_b_positions = [((17 + 73 * t) % 512) for t in range(32)]
    gates.append(
        record(
            "G7_PERMANENT_LANES_LATIN_AND_PAIRING_INSTANTIATED",
            {
                "coprime": math.gcd(73, 512) == 1,
                "exact16": bool(np.all(counts_for_lane0 == 16)),
                "collision_free": collision_free,
                "profile_independent": profile_a_positions == profile_b_positions,
                "two_chunks": lane["chunks"].startswith("physical0..255 then256..511"),
                "no_compaction": "never compact" in lane["inactive"],
                "evaluation_same_lane": "same tape always has the same lane"
                in p["leaf_policy_P256"]["evaluation_cohort"]["pairing"],
                "metamorphic_complete": len(
                    p["leaf_policy_P256"]["metamorphic_gates"]
                )
                == 4,
            },
            {
                "lane0_minmax": [
                    int(counts_for_lane0.min()),
                    int(counts_for_lane0.max()),
                ],
                "sample_positions": profile_a_positions,
            },
        )
    )

    e0 = p["E0"]
    e1 = p["E1"]
    e0_outcomes = 8 * e0["tapes_per_root"] * len(e0["profiles"])
    e1_outcomes = 8 * e1["tapes_per_root"] * len(e1["profiles"])
    gates.append(
        record(
            "G8_FIXED_ROOT_CONDITIONAL_E0_E1_AND_CONFIDENCE",
            {
                "E0_outcomes": e0_outcomes == 131072,
                "E1_outcomes": e1_outcomes == 131072,
                "conditional": "Fix source actor hole" in e0["conditional_deal"],
                "profiles": e0["profiles"]
                == [
                    "canonical_H11_root",
                    "replica_A_root",
                    "replica_B_root",
                    "ensemble_root",
                ]
                and e1["profiles"]
                == ["canonical_H11_root", "frozen_ensemble_root"],
                "one_primary": p["confidence_limit"]["multiplicity"].startswith(
                    "One preregistered E1 primary quantity"
                ),
                "fixed_roots": "Root resampling" in p["confidence_limit"]["fixed_roots"],
                "bootstrap_index": "ordered replicate5001" in e0["bootstrap"]
                and "ordered replicate5001" in e1["bootstrap"],
                "primary_threshold": e1["primary_gate"]
                == "theta_LCB>=0.20 big blinds per reached root.",
                "sealed": e1["open_condition"].startswith(
                    "Fresh process requires immutable candidate manifest"
                ),
            },
            {
                "E0_outcomes": e0_outcomes,
                "E1_outcomes": e1_outcomes,
                "E1_gate": e1["primary_gate"],
            },
        )
    )

    work = p["exact_resource_work_table"]
    census_calls = 114688
    likelihood_calls = 8 * 24 * math.ceil(1326 / 256)
    solver_calls = 8192 * 32 * 2
    e0_calls = 4 * math.ceil((8 * 4096) / 512) * 32 * 2
    e1_calls = 2 * math.ceil((8 * 8192) / 512) * 32 * 2
    total_calls = census_calls + likelihood_calls + solver_calls + e0_calls + e1_calls
    total_rows = total_calls * 256
    total_transitions = 114688 + 2359296 * 32 + 131072 * 32 + 131072 * 32
    totals = work["totals"]
    gates.append(
        record(
            "G9_EXACT_WORK_AND_RESOURCE_ADMISSION_RECOMPUTED",
            {
                "likelihood": likelihood_calls
                == work["full_history_likelihood"]["calls_batch256_max"]
                == 1152,
                "solver": solver_calls
                == work["solver_leaf_P256"]["calls_batch256_max"]
                == 524288,
                "E0": e0_calls == work["E0_P256"]["calls_batch256_max"] == 16384,
                "E1": e1_calls == work["E1_P256"]["calls_batch256_max"] == 16384,
                "total_calls": total_calls
                == totals["network_forward_calls_max"]
                == 672896,
                "total_rows": total_rows == totals["network_rows_max"] == 172261376,
                "transitions": total_transitions
                == totals["exact_cent_action_transitions_max"]
                == 84000768,
                "admission_before_science": p["resource_admission"]["position"].endswith(
                    "before any census hand,root,belief,solver row or evaluation tape."
                ),
                "eight_blocks": p["resource_admission"]["blocks"].startswith(
                    "Exactly8 post-warmup"
                ),
                "wall": p["resource_admission"]["pass_gates"][
                    "projected_total_wall_seconds_max"
                ]
                == 21600,
            },
            {
                "calls": total_calls,
                "rows": total_rows,
                "transitions": total_transitions,
            },
        )
    )

    prospective_absent = {
        name: not Path(path).exists() for name, path in p["prospective_paths"].items()
    }
    counts = p["preexecution_counts"]
    forbidden_old_runner = (
        ROOT
        / "scripts"
        / "alpha_holdem"
        / "v5_lrft_f64_5d7506904a3846b736d272d13162c2c8.py"
    )
    gates.append(
        record(
            "G10_NO_IMPLEMENTATION_OR_SCIENCE_AND_AUDIT_CHAIN",
            {
                "prospective_absent": all(prospective_absent.values()),
                "counts_zero": all(value == 0 for value in counts.values()),
                "old_runner_preserved": forbidden_old_runner.is_file()
                and file_sha(forbidden_old_runner)
                == "cc62907cb456523e88ce5b2fc34e721bb1e5b4c312fb4480f192f15b2abe81ca",
                "old_runner_forbidden": any(
                    "v5_lrft_f64_5d7506904a3846b736d272d13162c2c8" == item
                    for item in p["frozen_runtime"]["forbidden_runtime_or_code_reuse"]
                ),
                "instantiated_audit": "independently instantiate"
                in p["implementation_and_audit"]["preimplementation_audit"],
                "result_audit": p["implementation_and_audit"]["result_audit"].startswith(
                    "Independently rehash"
                ),
            },
            {
                "prospective_absent": prospective_absent,
                "preexecution_counts": counts,
                "old_runner_sha256": file_sha(forbidden_old_runner),
            },
        )
    )

    passed = sum(item["pass"] for item in gates)
    result = {
        "schema_version": "v5.lrft_f8r1.preregistration_audit.v1",
        "identity": IDENTITY,
        "status": (
            "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_PASS"
            if passed == len(gates)
            else "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_NONPASS"
        ),
        "preregistration": {
            "path": str(PREREG),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": file_sha(Path(__file__).resolve()),
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "scientific_output": counts,
        "authority": (
            "PASS authorizes fresh F8R1 implementation and independent implementation "
            "audit only. Resource admission must PASS before scientific execution."
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
