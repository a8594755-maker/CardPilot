"""Simplified independent C2 implementation audit for LRFT-F8R1.

The runner is never imported.  Exactly two fresh subprocesses invoke only its
zero-file ``contract-probe`` CLI.  Detailed deterministic evidence from each is
compared with independently implemented reference arithmetic in this file.
"""

from __future__ import annotations

import ast
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
IDENTITY = TOKEN + "d14e7b9dfbdbb51cc7897df93e2d3198"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1_{TOKEN}.py"
OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_implementation_audit_c2_{TOKEN}_20260723.json"
)
OUTPUT_ROOT = ROOT / "reports" / f"lrft_f8r1_{TOKEN}"
RUNNER_SHA = "2922d9dc18566b361883da6a384a9349a4bddbf5e3f743f0952ba09bbcdd8506"
RUNNER_BYTES = 87_748
PARENT_AUDITOR_SHA = (
    "f12a8d0e47ee0501ce9181d5fe19eb495127476a4e30b3f2496be6fec6c57a6e"
)
C1_AUDITOR_SHA = (
    "06ec4fe00bdec7a502a6c54ad9382de0ca9372699612746a0f995fd29905ef81"
)
FORBIDDEN = (
    "v5_lrft_f64_",
    "lrft_exact_cent_public_",
    "lrft_h11_likelihood_",
    "environment_v55",
    "HUNLGameState",
    "HUNLEnvironmentV55",
)
SCIENCE = {
    "model_instances": 0,
    "model_or_network_calls": 0,
    "network_calls": 0,
    "resource_rows": 0,
    "census_hands": 0,
    "selected_roots": 0,
    "belief_rows": 0,
    "solver_traversals": 0,
    "leaf_outcomes": 0,
    "E0_tapes": 0,
    "E1_tapes": 0,
    "teacher_rows": 0,
    "checkpoints": 0,
    "slumbot_hands": 0,
    "official_hands": 0,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def record(name: str, predicates: dict[str, bool], evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "pass": all(bool(value) for value in predicates.values()),
        "predicates": {key: bool(value) for key, value in predicates.items()},
        "evidence": evidence,
    }


def state_evidence(
    *,
    street: int,
    board: list[int],
    pot: int,
    stacks: list[int],
    street_put: list[int],
    total_put: list[int],
    actor: int | None,
    acted: list[bool],
    last_raise: int,
    chance: int,
    allin: bool,
    terminal: bool,
    folded: int | None,
    legal: list[int],
    history: list[list[list[int]]],
) -> dict[str, Any]:
    public = {
        "acted_since_full_raise": acted,
        "actor": actor,
        "allin_runout": allin,
        "board": board,
        "chance_count": chance,
        "folded": folded,
        "history": history,
        "last_full_raise": last_raise,
        "pot": pot,
        "stacks": stacks,
        "street": street,
        "street_put": street_put,
        "terminal": terminal,
        "total_put": total_put,
    }
    return {
        "street": street,
        "board": board,
        "pot": pot,
        "stacks": stacks,
        "street_put": street_put,
        "total_put": total_put,
        "actor": actor,
        "acted_since_full_raise": acted,
        "last_full_raise": last_raise,
        "chance_count": chance,
        "allin_runout": allin,
        "terminal": terminal,
        "folded": folded,
        "legal_vector": legal,
        "public_sha256": hashlib.sha256(canonical_bytes(public).rstrip(b"\n")).hexdigest(),
    }


def digest(master: str, domain: str, fields: tuple[Any, ...], counter: int = 0) -> bytes:
    message = "|".join((master, domain, *(str(value) for value in fields), str(counter)))
    return hashlib.sha256(message.encode("utf-8")).digest()


def bounded(master: str, domain: str, fields: tuple[Any, ...], n: int) -> tuple[int, int]:
    limit = (1 << 64) - ((1 << 64) % n)
    counter = 0
    while True:
        value = int.from_bytes(digest(master, domain, fields, counter)[:8], "big")
        if value < limit:
            return value % n, counter
        counter += 1


def probability_reference() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    logits = np.asarray(
        [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
        dtype=np.float32,
    )
    legal = np.asarray([1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool)
    values = logits[legal].astype(np.float64)
    weights = np.exp(values - np.max(values))
    probs = np.zeros(9, dtype=np.float64)
    probs[legal] = weights / np.sum(weights, dtype=np.float64)
    cdf = np.cumsum(probs, dtype=np.float64)
    cdf[int(np.flatnonzero(legal)[-1])] = np.float64(1.0)
    return logits, legal, probs, cdf


def exact_sample(cdf: np.ndarray, legal: np.ndarray, uniform: Fraction) -> int:
    for slot in np.flatnonzero(legal):
        numerator, denominator = float(cdf[slot]).as_integer_ratio()
        if numerator * uniform.denominator > uniform.numerator * denominator:
            return int(slot)
    raise AssertionError("no legal sample")


def independent_reference() -> dict[str, Any]:
    empty: list[list[list[int]]] = [[], [], [], []]
    limp_history = [[[1, 2, 0]], [], [], []]
    checked_history = [[[1, 2, 0], [0, 1, 0]], [], [], []]
    full_history = [
        [[1, 2, 0], [0, 1, 0]],
        [[0, 3, 132], [1, 4, 351]],
        [],
        [],
    ]
    short_history = [
        [[1, 2, 0], [0, 1, 0]],
        [[0, 3, 132], [1, 5, 150]],
        [],
        [],
    ]
    opponent_allin_history = [
        [[1, 2, 0], [0, 1, 0]],
        [[0, 3, 132], [1, 5, 19_800]],
        [],
        [],
    ]
    del empty
    exact_cent = {
        "sb_call": state_evidence(
            street=0,
            board=[],
            pot=200,
            stacks=[19_900, 19_900],
            street_put=[100, 100],
            total_put=[100, 100],
            actor=0,
            acted=[False, True],
            last_raise=100,
            chance=0,
            allin=False,
            terminal=False,
            folded=None,
            legal=[0, 1, 0, 0, 0, 0, 1, 1, 1],
            history=limp_history,
        ),
        "bb_check": state_evidence(
            street=0,
            board=[],
            pot=200,
            stacks=[19_900, 19_900],
            street_put=[100, 100],
            total_put=[100, 100],
            actor=None,
            acted=[True, True],
            last_raise=100,
            chance=3,
            allin=False,
            terminal=False,
            folded=None,
            legal=[0] * 9,
            history=checked_history,
        ),
        "full_raise": state_evidence(
            street=1,
            board=[0, 5, 10],
            pot=883,
            stacks=[19_668, 19_449],
            street_put=[132, 351],
            total_put=[332, 551],
            actor=0,
            acted=[False, True],
            last_raise=219,
            chance=0,
            allin=False,
            terminal=False,
            folded=None,
            legal=[1, 1, 0, 0, 0, 1, 1, 1, 1],
            history=full_history,
        ),
        "short_allin": state_evidence(
            street=1,
            board=[0, 5, 10],
            pot=20_332,
            stacks=[19_668, 0],
            street_put=[132, 150],
            total_put=[332, 20_000],
            actor=0,
            acted=[True, True],
            last_raise=132,
            chance=0,
            allin=False,
            terminal=False,
            folded=None,
            legal=[1, 1, 0, 0, 0, 0, 0, 0, 0],
            history=short_history,
        ),
        "opponent_allin": state_evidence(
            street=1,
            board=[0, 5, 10],
            pot=20_332,
            stacks=[19_668, 0],
            street_put=[132, 19_800],
            total_put=[332, 20_000],
            actor=0,
            acted=[False, True],
            last_raise=19_668,
            chance=0,
            allin=False,
            terminal=False,
            folded=None,
            legal=[1, 1, 0, 0, 0, 0, 0, 0, 0],
            history=opponent_allin_history,
        ),
        "opening_slot": 2,
        "full_raise_slot": 4,
    }

    master = IDENTITY
    deck = list(range(52))
    for index in range(51, 0, -1):
        swap, _ = bounded(master, "CENSUS_DECK", (23, index), index + 1)
        deck[index], deck[swap] = deck[swap], deck[index]
    cell, rejects = bounded(master, "CENSUS_CELL", (17,), 8)
    raw_digest = digest(master, "CENSUS_CELL", (17,), 0)

    logits, legal, probs, cdf = probability_reference()
    uniforms = (
        Fraction(1, 1 << 65),
        Fraction(1, 10),
        Fraction(1, 2),
        Fraction(999_999_999_999, 1_000_000_000_000),
        Fraction((1 << 65) - 1, 1 << 65),
    )

    mu = np.asarray([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
    source = np.asarray([False, True, False, False, True, False])
    m_star = np.sum(mu[source], dtype=np.float64)
    conditional = np.zeros_like(mu)
    conditional[source] = mu[source] / m_star
    q = np.float64(0.875) * mu + np.float64(0.125) * conditional
    importance = mu / q
    objective = np.asarray([-3.0, 2.5, 1.25, -0.75, 4.0, 0.5])
    sigma0 = np.asarray([0.2, 0.3, 0.5])
    sigma1 = np.asarray([0.6, 0.4])
    returns0 = np.asarray([1.5, -0.25, 2.0])
    returns1 = np.asarray([-1.0, 0.75])
    delta0 = importance[1] * (returns0 - np.dot(sigma0, returns0))
    delta1 = importance[3] * (returns1 - np.dot(sigma1, returns1))
    rnext0 = np.maximum(0.0, np.asarray([0.1, 0.0, 0.4]) + delta0)
    rnext1 = np.maximum(0.0, np.asarray([0.0, 0.2]) + delta1)

    weighted = np.zeros(9, dtype=np.float64)
    denominator = 0
    for iteration in range(1, 8193):
        raw = np.arange(1, 10, dtype=np.float64) + (iteration % 7)
        sigma = raw / raw.sum(dtype=np.float64)
        weighted += np.float64(iteration) * sigma
        denominator += iteration
    endpoint = weighted / np.float64(denominator)

    lane_counts = np.zeros((288, 512), dtype=np.uint16)
    for iteration in range(8192):
        for logical in range(288):
            lane_counts[logical, (logical + 73 * iteration) % 512] += 1
    lane_samples = {
        str(logical): [
            (logical + 73 * iteration) % 512
            for iteration in (0, 1, 2, 511, 512, 8191)
        ]
        for logical in (0, 17, 143, 287)
    }
    assignment_hashes: dict[str, str] = {}
    for iteration in (0, 1, 511, 512, 8191):
        assignment: list[int | None] = [None] * 512
        for logical in range(288):
            assignment[(logical + 73 * iteration) % 512] = logical
        assignment_hashes[str(iteration)] = hashlib.sha256(
            canonical_bytes(assignment)
        ).hexdigest()

    work = {
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
        "joint_entries_max": 8 * math.comb(52, 2) * math.comb(50, 2),
        "proposal_samples": 262_144,
        "e0_bootstrap_draws": 100_000 * 8 * 4_096,
        "e1_bootstrap_draws": 100_000 * 8 * 8_192,
    }
    return {
        "exact_cent": exact_cent,
        "rng": {
            "digest_hex": raw_digest.hex(),
            "uint64": int.from_bytes(raw_digest[:8], "big"),
            "bounded_cell": cell,
            "bounded_rejections": rejects,
            "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
            "open01_lower": [1, 1 << 65],
            "open01_upper": [(1 << 65) - 1, 1 << 65],
        },
        "probability": {
            "logits_f32_hex": [float(value).hex() for value in logits],
            "legal": [int(value) for value in legal],
            "probability_hex": [value.hex() for value in probs],
            "cdf_hex": [value.hex() for value in cdf],
            "samples": [exact_sample(cdf, legal, uniform) for uniform in uniforms],
            "sample_uniform_rationals": [
                [uniform.numerator, uniform.denominator] for uniform in uniforms
            ],
        },
        "importance": {
            "mu_hex": [value.hex() for value in mu],
            "source": [int(value) for value in source],
            "m_star_hex": m_star.hex(),
            "q_hex": [value.hex() for value in q],
            "weight_hex": [value.hex() for value in importance],
            "target_expectation_hex": np.float64(np.dot(mu, objective)).hex(),
            "proposal_expectation_hex": np.float64(
                np.dot(q, importance * objective)
            ).hex(),
        },
        "tiny_cfr": {
            "delta0_hex": [value.hex() for value in delta0],
            "delta1_hex": [value.hex() for value in delta1],
            "rnext0_hex": [value.hex() for value in rnext0],
            "rnext1_hex": [value.hex() for value in rnext1],
        },
        "root_average": {
            "denominator": denominator,
            "endpoint_hex": [value.hex() for value in endpoint],
            "direct_equal": True,
        },
        "lanes": {
            "samples": lane_samples,
            "count_min": int(lane_counts.min()),
            "count_max": int(lane_counts.max()),
            "count_sha256": hashlib.sha256(
                lane_counts.astype("<u2", copy=False).tobytes(order="C")
            ).hexdigest(),
            "assignment_hashes": assignment_hashes,
        },
        "canonical": {
            "hole_count": math.comb(49, 2),
            "chunk_count": math.ceil(math.comb(49, 2) / 256),
            "last_real_count": math.comb(49, 2) % 256,
            "last_padding_unique": 1,
        },
        "work": {
            "total_calls": work["total_network_calls"],
            "total_rows": work["total_network_rows"],
            "total_transitions": work["total_transitions"],
            "total_outcome_records": work["total_outcome_records"],
            "artifact_bytes": work["artifact_bytes"],
            "checks": {
                "history_formula": True,
                "solver_formula": True,
                "e0_formula": True,
                "e1_formula": True,
                "total_calls": True,
                "total_rows": True,
                "total_transitions": True,
                "outcomes": True,
            },
            "table": work,
        },
    }


def import_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return sorted(set(names))


def run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lrft_f8r1_c2_probe_") as directory:
        probe_root = Path(directory)
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(RUNNER),
                "--mode",
                "contract-probe",
                "--probe-root",
                str(probe_root),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        files = [path for path in probe_root.rglob("*") if path.is_file()]
        if completed.returncode != 0:
            raise RuntimeError(
                f"contract probe exit {completed.returncode}: {completed.stderr[-4000:]}"
            )
        payload = json.loads(completed.stdout.strip())
        return {
            "payload": payload,
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
        }


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    if OUTPUT_ROOT.exists():
        raise RuntimeError("F8R1 output root exists before implementation audit")
    if sha(RUNNER) != RUNNER_SHA or RUNNER.stat().st_size != RUNNER_BYTES:
        raise RuntimeError("runner identity mismatch")
    runner_source = RUNNER.read_text(encoding="utf-8")
    expected = independent_reference()
    probes = [run_probe(), run_probe()]  # Exactly two fresh CLI probes.
    gates: list[dict[str, Any]] = []

    imports = import_names(runner_source)
    gates.append(
        record(
            "G1_IDENTITY_FRESH_GRAPH_AND_LAZY_MODEL_BOUNDARY",
            {
                "runner_sha": sha(RUNNER) == RUNNER_SHA,
                "runner_bytes": RUNNER.stat().st_size == RUNNER_BYTES,
                "identity": IDENTITY in runner_source,
                "no_forbidden": not any(value in runner_source for value in FORBIDDEN),
                "imports_clean": not any(
                    forbidden.lower() in name.lower()
                    for forbidden in FORBIDDEN
                    for name in imports
                ),
                "lazy_model": "class FrozenH11" in runner_source
                and 'choices=("contract-probe", "no-model-contracts", "resource-admission")'
                in runner_source,
            },
            {"runner_sha256": sha(RUNNER), "imports": imports},
        )
    )

    for index, probe in enumerate(probes, start=1):
        payload = probe["payload"]
        gates.append(
            record(
                f"G{index + 1}_FRESH_ZERO_FILE_CLI_PROBE_{index}",
                {
                    "exit0": probe["returncode"] == 0,
                    "status": payload.get("status")
                    == "LRFT_F8R1_CONTRACT_PROBE_PASS",
                    "identity": payload.get("identity") == IDENTITY,
                    "pass39": payload.get("passed") == payload.get("total") == 39,
                    "checks": len(payload.get("checks", {})) == 39
                    and all(payload["checks"].values()),
                    "root_zero": payload.get("before") == payload.get("after")
                    == {"files": 0, "bytes": 0},
                    "process_zero": probe["files"] == probe["bytes"] == 0,
                    "torch_absent": payload.get("torch_loaded") is False,
                    "model0": payload.get("model_calls") == 0,
                    "created0": payload.get("files_created")
                    == payload.get("bytes_created")
                    == 0,
                    "stderr_empty": probe["stderr"] == "",
                },
                probe,
            )
        )

    actual0 = probes[0]["payload"]["evidence"]
    actual1 = probes[1]["payload"]["evidence"]
    sections = (
        "exact_cent",
        "rng",
        "probability",
        "importance",
        "tiny_cfr",
        "root_average",
        "lanes",
        "canonical",
        "work",
    )
    for offset, section in enumerate(sections, start=4):
        gates.append(
            record(
                f"G{offset}_{section.upper()}_INDEPENDENT_REFERENCE",
                {
                    "probe1_exact": actual0.get(section) == expected[section],
                    "probe2_exact": actual1.get(section) == expected[section],
                    "repeat": actual0.get(section) == actual1.get(section),
                },
                {
                    "expected": expected[section],
                    "observed": actual0.get(section),
                },
            )
        )

    gates.append(
        record(
            "G13_RESOURCE_MODE_NOT_RUN_AND_SCIENCE0",
            {
                "output_root_absent": not OUTPUT_ROOT.exists(),
                "model0": all(
                    probe["payload"].get("model_calls") == 0 for probe in probes
                ),
                "torch_absent": all(
                    probe["payload"].get("torch_loaded") is False for probe in probes
                ),
                "resource_cli_not_invoked": all(
                    "resource_admission" not in probe["payload"] for probe in probes
                ),
            },
            {
                "resource_admission_runs": 0,
                "scientific_output": SCIENCE,
            },
        )
    )

    passed = sum(item["pass"] for item in gates)
    result = {
        "schema_version": "v5.lrft_f8r1.implementation_audit.v1",
        "identity": IDENTITY,
        "status": (
            "LRFT_F8R1_IMPLEMENTATION_AUDIT_PASS_RESOURCE_ADMISSION_AUTHORIZED_ONLY"
            if passed == len(gates)
            else "LRFT_F8R1_IMPLEMENTATION_AUDIT_NONPASS"
        ),
        "runner": {
            "path": str(RUNNER.resolve()),
            "sha256": sha(RUNNER),
            "bytes": RUNNER.stat().st_size,
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha(Path(__file__).resolve()),
        },
        "correction_lineage": {
            "parent_auditor_sha256": PARENT_AUDITOR_SHA,
            "parent_failure": "PREOUTPUT_ISOLATED_IMPORT_PATH_FAILURE_NO_REPORT",
            "c1_auditor_sha256": C1_AUDITOR_SHA,
            "c1_failure": "REPEATED_PREOUTPUT_CUSTOM_RUNPY_FAILURE_NO_REPORT",
            "simplification": "DIRECT_RUNNER_CLI_ONLY_NO_RUNPY_NO_RUNNER_IMPORT",
            "scientific_design_changed": False,
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_instantiated": 0,
        "resource_admission_runs": 0,
        "scientific_output": SCIENCE,
        "authority": (
            "PASS authorizes exactly the registered F8R1 resource-admission run only; "
            "this audit contains no scientific evidence."
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
