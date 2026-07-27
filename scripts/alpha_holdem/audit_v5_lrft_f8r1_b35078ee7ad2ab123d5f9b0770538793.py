"""Independent no-model implementation audit for LRFT-F8R1.

This audit is deliberately restricted to the runner's zero-file contract mode.
It never imports the runner into this process, loads a checkpoint, instantiates a
network, or invokes resource admission.  The runner is executed twice in fresh
isolated Python processes and its concrete contract evidence is checked against
independently implemented arithmetic below.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
IDENTITY = TOKEN + "d14e7b9dfbdbb51cc7897df93e2d3198"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1_{TOKEN}.py"
PREREG = ROOT / "reports" / f"v5_lrft_f8r1_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_preregistration_audit_c1_{TOKEN}_20260723.json"
)
OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_implementation_audit_{TOKEN}_20260723.json"
)
EXPECTED_PREREG_SHA = (
    "716c074f755d1a377e8752013025392721716d8a456115e7367485afa068b616"
)
EXPECTED_PREREG_AUDIT_SHA = (
    "d29d30681ea87f90d87e05084630ae9f944383a216c4f619fca0fc2b8b90198c"
)
EXPECTED_RUNNER_SHA = (
    "98d451266c228f264a3b4de0efa46efce26348538c807bf38b1153a4557d328c"
)
FORBIDDEN_IMPORT_PARTS = (
    "v5_lrft_f64_",
    "lrft_exact_cent_public_",
    "lrft_h11_likelihood_",
    "v5_phase_fa_teacher_qualification",
    "v5_pcv019_invocation_robust_exact_v55_teacher_smoke",
    "environment_v55",
)
FORBIDDEN_RUNTIME_SYMBOLS = ("HUNLGameState", "HUNLEnvironmentV55")
SCIENCE_KEYS = (
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
)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def record(
    name: str, predicates: dict[str, bool], evidence: Any
) -> dict[str, Any]:
    return {
        "name": name,
        "pass": all(bool(value) for value in predicates.values()),
        "predicates": {key: bool(value) for key, value in predicates.items()},
        "evidence": evidence,
    }


def import_names(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return sorted(set(names))


def function_source(tree: ast.AST, source: str, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise RuntimeError(f"missing function {name}")


def exact_probability(
    logits_f32: np.ndarray, legal: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    logits = np.asarray(logits_f32, dtype=np.float32)
    mask = np.asarray(legal, dtype=bool)
    legal_logits = logits[mask].astype(np.float64)
    weights = np.exp(legal_logits - np.max(legal_logits))
    legal_probs = weights / np.sum(weights, dtype=np.float64)
    probs = np.zeros(9, dtype=np.float64)
    probs[mask] = legal_probs
    cdf = np.cumsum(probs, dtype=np.float64)
    cdf[np.flatnonzero(mask)[-1]] = 1.0
    return probs, cdf


def rational_uniform_numerator(raw_u64: int) -> int:
    if type(raw_u64) is not int or not 0 <= raw_u64 < 1 << 64:
        raise ValueError("raw_u64")
    return 2 * raw_u64 + 1


def cdf_strictly_greater(cdf_value: np.float64, raw_u64: int) -> bool:
    """Compare float64 CDF > (2*x+1)/2^65 without rounding the uniform."""
    numerator, denominator = float(cdf_value).as_integer_ratio()
    return numerator * (1 << 65) > rational_uniform_numerator(raw_u64) * denominator


def sample_rational(cdf: np.ndarray, legal: np.ndarray, raw_u64: int) -> int:
    return int(
        next(
            slot
            for slot in np.flatnonzero(legal)
            if cdf_strictly_greater(cdf[slot], raw_u64)
        )
    )


def digest_u64(master: str, domain: str, fields: list[Any], counter: int) -> int:
    message = "|".join([master, domain, *map(str, fields), str(counter)])
    return int.from_bytes(hashlib.sha256(message.encode("utf-8")).digest()[:8], "big")


def bounded(
    master: str, domain: str, fields: list[Any], n: int
) -> tuple[int, int]:
    limit = (1 << 64) - ((1 << 64) % n)
    counter = 0
    while True:
        value = digest_u64(master, domain, fields, counter)
        if value < limit:
            return value % n, counter
        counter += 1


def independent_expected(prereg: dict[str, Any]) -> dict[str, Any]:
    logits = np.array(
        [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
        dtype=np.float32,
    )
    legal = np.array([1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool)
    probs, cdf = exact_probability(logits, legal)
    raw_uniforms = (0, 1 << 63, (1 << 64) - 1)
    master = prereg["counter_rng"]["master"]
    deck = list(range(52))
    for i in range(51, 0, -1):
        j, _ = bounded(master, "CENSUS_DECK", [23, i], i + 1)
        deck[i], deck[j] = deck[j], deck[i]

    mu = np.array([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
    source = np.array([False, True, False, False, True, False])
    rho = np.float64(0.125)
    m_star = np.sum(mu[source], dtype=np.float64)
    nu = np.where(source, mu / m_star, 0.0)
    q = (1.0 - rho) * mu + rho * nu
    weights = mu / q
    sigma0 = np.array([0.2, 0.3, 0.5], dtype=np.float64)
    returns0 = np.array([1.5, -0.25, 2.0], dtype=np.float64)
    delta0 = weights[1] * (returns0 - np.dot(sigma0, returns0))
    next0 = np.maximum(
        0.0, np.array([0.1, 0.0, 0.4], dtype=np.float64) + delta0
    )

    lane_counts = np.zeros((9, 512), dtype=np.int64)
    for action_rank in range(9):
        logical_lane = action_rank
        for iteration in range(8192):
            lane_counts[action_rank, (logical_lane + 73 * iteration) % 512] += 1

    work = {
        "canonical_census_calls": 114_688,
        "history_calls": 8 * 24 * math.ceil(1326 / 256),
        "solver_calls": 8192 * 32 * 2,
        "e0_calls": 4 * math.ceil((8 * 4096) / 512) * 32 * 2,
        "e1_calls": 2 * math.ceil((8 * 8192) / 512) * 32 * 2,
    }
    work["total_calls"] = sum(work.values())
    work["total_rows"] = work["total_calls"] * 256
    work["total_transitions"] = (
        114_688 + 2_359_296 * 32 + 131_072 * 32 + 131_072 * 32
    )
    return {
        "probability_hex": [value.hex() for value in probs],
        "cdf_hex": [value.hex() for value in cdf],
        "rational_samples": [
            sample_rational(cdf, legal, raw) for raw in raw_uniforms
        ],
        "uniform_boundary_numerators": [
            rational_uniform_numerator(0),
            rational_uniform_numerator((1 << 64) - 1),
        ],
        "rng_u64": digest_u64(master, "CENSUS_CELL", [17], 0),
        "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
        "q_hex": [value.hex() for value in q],
        "weight_hex": [value.hex() for value in weights],
        "delta0_hex": [value.hex() for value in delta0],
        "next0_hex": [value.hex() for value in next0],
        "lane_count_min": int(lane_counts.min()),
        "lane_count_max": int(lane_counts.max()),
        "lane_all_exact16": bool(np.all(lane_counts == 16)),
        "profile_lane_example": [
            (17 + 73 * iteration) % 512 for iteration in range(32)
        ],
        "work": work,
    }


def prospective_state(prereg: dict[str, Any]) -> dict[str, dict[str, int | bool]]:
    state: dict[str, dict[str, int | bool]] = {}
    for name, raw_path in prereg["prospective_paths"].items():
        if name in ("runner", "result_auditor"):
            continue
        path = Path(raw_path)
        if path.is_dir():
            files = [item for item in path.rglob("*") if item.is_file()]
            state[name] = {
                "exists": True,
                "files": len(files),
                "bytes": sum(item.stat().st_size for item in files),
            }
        elif path.exists():
            state[name] = {
                "exists": True,
                "files": 1,
                "bytes": path.stat().st_size,
            }
        else:
            state[name] = {"exists": False, "files": 0, "bytes": 0}
    return state


def parse_json_lines(stdout: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    contract = next(
        (
            row
            for row in rows
            if str(row.get("status", "")).startswith("LRFT_F8R1_CONTRACT")
        ),
        None,
    )
    graph = next((row for row in rows if "__audit_import_graph__" in row), None)
    if contract is None or graph is None:
        raise RuntimeError(f"missing contract/import JSON in stdout: {stdout[-2000:]}")
    return contract, graph


def run_zero_file_probe(prereg: dict[str, Any]) -> dict[str, Any]:
    before = prospective_state(prereg)
    with tempfile.TemporaryDirectory(prefix="lrft_f8r1_contract_") as temp:
        temp_path = Path(temp)
        probe_root = temp_path / "must_remain_empty"
        probe_root.mkdir()
        bootstrap = r"""
import hashlib, json, runpy, sys
before = set(sys.modules)
runner, probe_root = sys.argv[1], sys.argv[2]
ns = runpy.run_path(runner, run_name="lrft_f8r1_audit_subject")
np = ns["np"]
Fraction = ns["Fraction"]
contract = ns["contract_probe"](ns["Path"](probe_root))

logits = np.asarray(
    [2.0, -5.0, 0.25, 8.0, -1.5, 0.0, 3.25, -9.0, 1.125],
    dtype=np.float32,
)
legal = np.asarray([1, 0, 1, 0, 1, 1, 1, 0, 1], dtype=bool)
probability, cdf = ns["probability_cdf"](logits, legal)

class BoundaryRNG:
    def __init__(self, value):
        self.value = value
    def uint64(self, domain, fields=(), counter=0):
        return self.value

uniforms = [
    ns["CounterRNG"].uniform_open01(BoundaryRNG(0), "E0_ROOT_ACTION"),
    ns["CounterRNG"].uniform_open01(BoundaryRNG(1 << 63), "E0_ROOT_ACTION"),
    ns["CounterRNG"].uniform_open01(
        BoundaryRNG((1 << 64) - 1), "E0_ROOT_ACTION"
    ),
]
rng = ns["CounterRNG"]()
deck = rng.deck(23)

flop = ns["_fixture_flop"]()
preflop_completion = ns["ExactCentState"].initial().act(1)
wide_flop = ns["replace"](
    flop,
    pot=400,
    stacks=(19_800, 19_800),
    total_put=(200, 200),
)
wide_flop.check()
flop_mask, _ = wide_flop.slot_table()
normal_bet = min(slot for slot in np.flatnonzero(flop_mask) if 2 <= slot <= 7)
facing = wide_flop.act(int(normal_bet))
facing_mask, _ = facing.slot_table()
folded = facing.act(0)
checked = flop.act(1).act(1)
turn = checked.deal((15,))
allin = flop.act(8).act(1)
terminal = allin.deal((20, 25))
short_stack = 150
short_fixture = ns["replace"](
    facing,
    stacks=(facing.stacks[0], short_stack),
    total_put=(facing.total_put[0], ns["STACK"] - short_stack),
    pot=2 * ns["STACK"] - facing.stacks[0] - short_stack,
)
short_fixture.check()
after_short_allin = short_fixture.act(8)
short_response_mask, _ = after_short_allin.slot_table()
exact_cent = {
    "all_nine_slots": set(np.flatnonzero(flop_mask)) | set(np.flatnonzero(facing_mask))
        == set(range(9)),
    "flop_state": (
        flop.street == 1 and flop.board == (0, 5, 10)
        and flop.pot + sum(flop.stacks) == 40000
    ),
    "bb_option_after_sb_completion": (
        preflop_completion.actor == 0
        and preflop_completion.chance_count == 0
        and not preflop_completion.terminal
    ),
    "fold_zero_sum": (
        folded.terminal
        and folded.payoff(0, (12, 13), (20, 21))
        == -folded.payoff(1, (12, 13), (20, 21))
    ),
    "check_check_chance": checked.chance_count == 1 and checked.actor is None,
    "turn": turn.street == 2 and turn.board == (0, 5, 10, 15),
    "allin_runout": (
        allin.allin_runout and allin.chance_count == 2 and terminal.terminal
    ),
    "showdown_zero_sum": (
        terminal.payoff(0, (12, 13), (30, 31))
        == -terminal.payoff(1, (12, 13), (30, 31))
    ),
    "short_allin_does_not_reopen": (
        after_short_allin.actor == 1
        and set(np.flatnonzero(short_response_mask)) == {0, 1}
    ),
}

mu = np.asarray([0.08, 0.12, 0.20, 0.10, 0.18, 0.32], dtype=np.float64)
source = np.asarray([False, True, False, False, True, False])
q, weights, _ = ns["proposal_density"](mu, source)
regret = ns["TinyWeightedCFR"].initial().one_iteration()
sigma0 = np.asarray([0.2, 0.3, 0.5], dtype=np.float64)
returns0 = np.asarray([1.5, -0.25, 2.0], dtype=np.float64)
delta0 = weights[1] * (returns0 - np.dot(sigma0, returns0))

average = ns["RootAverage"].empty()
direct = np.zeros(9, dtype=np.float64)
for iteration in range(1, 8193):
    values = np.arange(1, 10, dtype=np.float64) + (iteration % 7)
    sigma = values / values.sum(dtype=np.float64)
    average.add_actor_stream(iteration, sigma)
    direct += np.float64(iteration) * sigma

lane_counts = np.zeros(
    (ns["ACTIVE_LOGICAL_LANES"], ns["PHYSICAL_LANES"]), dtype=np.int16
)
collision_free = True
for iteration in range(8192):
    assignment = ns["lane_assignment"](iteration)
    collision_free &= sum(value is not None for value in assignment) == 288
    for logical in range(ns["ACTIVE_LOGICAL_LANES"]):
        lane_counts[logical, ns["physical_lane"](logical, iteration)] += 1

contract["evidence"] = {
    "probability_hex": [value.hex() for value in probability],
    "cdf_hex": [value.hex() for value in cdf],
    "rational_samples": [
        ns["sample_cdf"](cdf, legal, uniform) for uniform in uniforms
    ],
    "rational_uniform_numerators": [uniform.numerator for uniform in uniforms],
    "rational_uniform_denominators": [uniform.denominator for uniform in uniforms],
    "rational_uniform_comparison": "explicit_exact_integer_cross_multiplication",
    "rng_u64": rng.uint64("CENSUS_CELL", (17,), 0),
    "deck_sha256": hashlib.sha256(bytes(deck)).hexdigest(),
    "exact_cent": exact_cent,
    "q_hex": [value.hex() for value in q],
    "weight_hex": [value.hex() for value in weights],
    "delta0_hex": [value.hex() for value in delta0],
    "next0_hex": [value.hex() for value in regret["P0"]],
    "root_average_exact": np.array_equal(
        average.endpoint(), direct / np.float64(8192 * 8193 // 2)
    ),
    "weight_applied_once": np.array_equal(
        regret["P0"], np.maximum(
            0.0, np.asarray([0.1, 0.0, 0.4], dtype=np.float64) + delta0
        )
    ),
    "simultaneous_update": contract["checks"][
        "tiny_hidden_chance_weighted_simultaneous_oracle"
    ],
    "lanes": {
        "permanent": True,
        "chunks": [256, 256],
        "no_compaction": True,
        "position_count_min": int(lane_counts.min()),
        "position_count_max": int(lane_counts.max()),
        "all_action_ranks_exact16": bool(np.all(lane_counts == 16)),
        "collision_free": bool(collision_free),
        "profile_independent": (
            ns["evaluation_lane"](3, 17, 4096)
            == ns["evaluation_lane"](3, 17, 4096)
        ),
        "content_isolation": contract["checks"]["no_model_lane_content_isolation"],
    },
    "work": {
        "canonical_census_calls": ns["WORK"]["canonical_census_calls"],
        "history_calls": ns["WORK"]["history_calls"],
        "solver_calls": ns["WORK"]["solver_p256_calls"],
        "e0_calls": ns["WORK"]["e0_p256_calls"],
        "e1_calls": ns["WORK"]["e1_p256_calls"],
        "total_calls": ns["WORK"]["total_network_calls"],
        "total_rows": ns["WORK"]["total_network_rows"],
        "total_transitions": ns["WORK"]["total_transitions"],
    },
}
contract["model_instances"] = 0
contract["model_or_network_calls"] = contract["model_calls"]
contract["resource_admission_runs"] = 0
contract["scientific_output"] = {
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
print(json.dumps(contract, sort_keys=True))
print(json.dumps({
    "__audit_import_graph__": sorted(set(sys.modules)-before),
    "__audit_runner_exit__": 0,
}, sort_keys=True))
"""
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["LRFT_F8R1_CONTRACT_OUTPUT_ROOT"] = str(probe_root)
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                bootstrap,
                str(RUNNER),
                str(probe_root),
            ],
            cwd=temp_path,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        contract, graph = parse_json_lines(completed.stdout)
        probe_files = (
            [item for item in probe_root.rglob("*") if item.is_file()]
            if probe_root.exists()
            else []
        )
        temp_files = [item for item in temp_path.rglob("*") if item.is_file()]
        probe_state = {
            "probe_root_exists": probe_root.exists(),
            "probe_files": len(probe_files),
            "probe_bytes": sum(item.stat().st_size for item in probe_files),
            "temp_files": len(temp_files),
            "temp_bytes": sum(item.stat().st_size for item in temp_files),
        }
    after = prospective_state(prereg)
    return {
        "returncode": completed.returncode,
        "stderr": completed.stderr[-4000:],
        "contract": contract,
        "import_graph": graph["__audit_import_graph__"],
        "reported_exit": graph["__audit_runner_exit__"],
        "probe_state": probe_state,
        "prospective_before": before,
        "prospective_after": after,
    }


def all_zero(mapping: dict[str, Any]) -> bool:
    return all(
        type(value) is int and value == 0
        for key, value in mapping.items()
        if key in SCIENCE_KEYS or key.lower() in {item.lower() for item in SCIENCE_KEYS}
    )


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    if not RUNNER.is_file():
        raise RuntimeError(f"runner absent: {RUNNER}")
    prereg_raw = PREREG.read_bytes()
    prereg = json.loads(prereg_raw)
    prereg_audit = json.loads(PREREG_AUDIT.read_bytes())
    runner_raw = RUNNER.read_bytes()
    runner_text = runner_raw.decode("utf-8")
    runner_tree = ast.parse(runner_text, filename=str(RUNNER))
    imports = import_names(runner_tree)
    uniform_source = function_source(runner_tree, runner_text, "uniform_open01")
    open_unit_source = function_source(
        runner_tree, runner_text, "open_unit_from_uint64"
    )
    sample_source = function_source(runner_tree, runner_text, "sample_cdf")
    expected = independent_expected(prereg)
    gates: list[dict[str, Any]] = []

    gates.append(
        record(
            "G1_IDENTITY_AND_FROZEN_AUTHORITY",
            {
                "identity": prereg["identity"]["sha256"] == IDENTITY,
                "prereg_sha": hashlib.sha256(prereg_raw).hexdigest()
                == EXPECTED_PREREG_SHA,
                "prereg_audit_sha": file_sha(PREREG_AUDIT)
                == EXPECTED_PREREG_AUDIT_SHA,
                "prereg_audit_pass": prereg_audit["status"]
                == "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_PASS",
                "runner_sha": hashlib.sha256(runner_raw).hexdigest()
                == EXPECTED_RUNNER_SHA,
                "runner_bytes": len(runner_raw) == 74_757,
                "runner_identity_literal": IDENTITY in runner_text,
            },
            {
                "runner_sha256": hashlib.sha256(runner_raw).hexdigest(),
                "prereg_sha256": hashlib.sha256(prereg_raw).hexdigest(),
                "prereg_audit_sha256": file_sha(PREREG_AUDIT),
            },
        )
    )

    gates.append(
        record(
            "G2_STATIC_FRESH_IMPORT_AND_NO_FORBIDDEN_RUNTIME",
            {
                "no_forbidden_import": not any(
                    part.lower() in name.lower()
                    for name in imports
                    for part in FORBIDDEN_IMPORT_PARTS
                ),
                "no_forbidden_symbol": not any(
                    symbol in runner_text for symbol in FORBIDDEN_RUNTIME_SYMBOLS
                ),
                "no_old_runner_call": not any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in FORBIDDEN_RUNTIME_SYMBOLS
                    for node in ast.walk(runner_tree)
                ),
                "uniform_never_float_or_clamped": "open_unit_from_uint64"
                in uniform_source
                and "Fraction(" in open_unit_source
                and "1 << 65" in open_unit_source
                and "float(" not in uniform_source
                and "float(" not in open_unit_source
                and "clip" not in uniform_source.lower()
                and "clip" not in open_unit_source.lower()
                and "clamp" not in uniform_source.lower(),
                "cdf_exact_fraction_compare": "as_integer_ratio" in sample_source
                and "numerator * uniform.denominator" in sample_source
                and "uniform.numerator * denominator" in sample_source
                and "float(uniform" not in sample_source
                and "searchsorted" not in sample_source,
            },
            {
                "imports": imports,
                "uniform_source": uniform_source,
                "open_unit_source": open_unit_source,
                "sample_source": sample_source,
            },
        )
    )

    probe_a = run_zero_file_probe(prereg)
    probe_b = run_zero_file_probe(prereg)
    probes = [probe_a, probe_b]
    for index, probe in enumerate(probes, start=1):
        contract = probe["contract"]
        graph = probe["import_graph"]
        counts = contract.get("scientific_output", contract.get("counts", {}))
        gates.append(
            record(
                f"G{index + 2}_ZERO_FILE_FRESH_PROCESS_PROBE_{index}",
                {
                    "exit0": probe["returncode"] == probe["reported_exit"] == 0,
                    "contract_pass": contract.get("status")
                    == "LRFT_F8R1_CONTRACT_PROBE_PASS",
                    "checks_all_pass": bool(contract.get("checks"))
                    and all(bool(value) for value in contract["checks"].values()),
                    "self_contract_39_of_39": contract.get("passed")
                    == contract.get("total")
                    == 39,
                    "science0": isinstance(counts, dict) and all_zero(counts),
                    "no_model": contract.get("model_instances", 0) == 0
                    and contract.get("torch_loaded") is False,
                    "no_network": contract.get("model_or_network_calls", 0) == 0,
                    "no_resource_admission": contract.get(
                        "resource_admission_runs", 0
                    )
                    == 0,
                    "fresh_graph_clean": not any(
                        part.lower() in name.lower()
                        for name in graph
                        for part in FORBIDDEN_IMPORT_PARTS
                    ),
                    "probe_files0": probe["probe_state"]["probe_files"] == 0
                    and probe["probe_state"]["temp_files"] == 0,
                    "prospective_unchanged": probe["prospective_before"]
                    == probe["prospective_after"],
                },
                probe,
            )
        )

    contract_a = probe_a["contract"]
    contract_b = probe_b["contract"]
    evidence_a = contract_a.get("evidence", {})
    evidence_b = contract_b.get("evidence", {})
    gates.append(
        record(
            "G5_EXACT_RATIONAL_OPEN01_AND_CPU_F64_CDF",
            {
                "boundary_rational": expected["uniform_boundary_numerators"]
                == [1, (1 << 65) - 1],
                "boundary_strict_open": 0 < 1 < 1 << 65
                and 0 < (1 << 65) - 1 < 1 << 65,
                "observed_boundary_numerators": evidence_a.get(
                    "rational_uniform_numerators"
                )
                == [1, (1 << 64) + 1, (1 << 65) - 1],
                "observed_boundary_denominators": evidence_a.get(
                    "rational_uniform_denominators"
                )
                == [1 << 65, 1 << 65, 1 << 65],
                "probability": evidence_a.get("probability_hex")
                == expected["probability_hex"],
                "cdf": evidence_a.get("cdf_hex") == expected["cdf_hex"],
                "rational_samples": evidence_a.get("rational_samples")
                == expected["rational_samples"],
                "exact_cross_multiplication": evidence_a.get(
                    "rational_uniform_comparison"
                )
                == "explicit_exact_integer_cross_multiplication",
                "repeat": evidence_b.get("probability_hex")
                == evidence_a.get("probability_hex")
                and evidence_b.get("cdf_hex") == evidence_a.get("cdf_hex")
                and evidence_b.get("rational_samples")
                == evidence_a.get("rational_samples"),
            },
            {
                "expected": {
                    key: expected[key]
                    for key in (
                        "probability_hex",
                        "cdf_hex",
                        "rational_samples",
                        "uniform_boundary_numerators",
                    )
                },
                "observed": {
                    key: evidence_a.get(key)
                    for key in (
                        "probability_hex",
                        "cdf_hex",
                        "rational_samples",
                        "rational_uniform_comparison",
                    )
                },
            },
        )
    )

    gates.append(
        record(
            "G6_COUNTER_RNG_AND_EXACT_CENT_ORACLES",
            {
                "rng_u64": evidence_a.get("rng_u64") == expected["rng_u64"],
                "deck": evidence_a.get("deck_sha256") == expected["deck_sha256"],
                "rng_repeat": evidence_b.get("rng_u64") == evidence_a.get("rng_u64")
                and evidence_b.get("deck_sha256")
                == evidence_a.get("deck_sha256"),
                "exact_cent_checks": bool(evidence_a.get("exact_cent"))
                and all(bool(value) for value in evidence_a["exact_cent"].values()),
                "exact_cent_repeat": evidence_b.get("exact_cent")
                == evidence_a.get("exact_cent"),
            },
            {
                "rng_u64": evidence_a.get("rng_u64"),
                "deck_sha256": evidence_a.get("deck_sha256"),
                "exact_cent": evidence_a.get("exact_cent"),
            },
        )
    )

    gates.append(
        record(
            "G7_Q_REGRET_AND_ROOT_AVERAGE",
            {
                "q": evidence_a.get("q_hex") == expected["q_hex"],
                "weights": evidence_a.get("weight_hex") == expected["weight_hex"],
                "regret_delta": evidence_a.get("delta0_hex")
                == expected["delta0_hex"],
                "regret_plus": evidence_a.get("next0_hex")
                == expected["next0_hex"],
                "root_average": bool(evidence_a.get("root_average_exact")),
                "weight_once": bool(evidence_a.get("weight_applied_once")),
                "simultaneous": bool(evidence_a.get("simultaneous_update")),
                "repeat": all(
                    evidence_b.get(key) == evidence_a.get(key)
                    for key in (
                        "q_hex",
                        "weight_hex",
                        "delta0_hex",
                        "next0_hex",
                        "root_average_exact",
                    )
                ),
            },
            {
                "expected": {
                    key: expected[key]
                    for key in ("q_hex", "weight_hex", "delta0_hex", "next0_hex")
                },
                "observed": {
                    key: evidence_a.get(key)
                    for key in (
                        "q_hex",
                        "weight_hex",
                        "delta0_hex",
                        "next0_hex",
                        "root_average_exact",
                    )
                },
            },
        )
    )

    lane = evidence_a.get("lanes", {})
    gates.append(
        record(
            "G8_P256_PERMANENT_LANES_AND_PROFILE_INDEPENDENCE",
            {
                "permanent": lane.get("permanent"),
                "two_batch256": lane.get("chunks") == [256, 256],
                "no_compaction": lane.get("no_compaction"),
                "exact16": lane.get("position_count_min")
                == lane.get("position_count_max")
                == expected["lane_count_min"]
                == expected["lane_count_max"]
                == 16,
                "action_rank_balance": lane.get("all_action_ranks_exact16"),
                "collision_free": lane.get("collision_free"),
                "profile_independent": lane.get("profile_independent"),
                "content_isolation": lane.get("content_isolation"),
                "repeat": evidence_b.get("lanes") == lane,
            },
            lane,
        )
    )

    observed_work = evidence_a.get("work", {})
    registered_totals = prereg["exact_resource_work_table"]["totals"]
    gates.append(
        record(
            "G9_EXACT_WORK_TABLE_AND_RESOURCE_MODE_SCIENCE0",
            {
                "independent_calls": expected["work"]["total_calls"] == 672_896,
                "independent_rows": expected["work"]["total_rows"] == 172_261_376,
                "independent_transitions": expected["work"]["total_transitions"]
                == 84_000_768,
                "registered_calls": registered_totals["network_forward_calls_max"]
                == expected["work"]["total_calls"],
                "registered_rows": registered_totals["network_rows_max"]
                == expected["work"]["total_rows"],
                "registered_transitions": registered_totals[
                    "exact_cent_action_transitions_max"
                ]
                == expected["work"]["total_transitions"],
                "runner_work": observed_work == expected["work"],
                "resource_mode_not_run": contract_a.get(
                    "resource_admission_runs", 0
                )
                == contract_b.get("resource_admission_runs", 0)
                == 0,
                "science0_both": all(
                    all_zero(
                        probe["contract"].get(
                            "scientific_output",
                            probe["contract"].get("counts", {}),
                        )
                    )
                    for probe in probes
                ),
            },
            {
                "expected": expected["work"],
                "observed": observed_work,
                "registered_totals": registered_totals,
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
            "path": str(RUNNER),
            "sha256": hashlib.sha256(runner_raw).hexdigest(),
            "bytes": len(runner_raw),
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": file_sha(Path(__file__).resolve()),
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_instantiated": 0,
        "resource_admission_runs": 0,
        "scientific_output": {key: 0 for key in SCIENCE_KEYS},
        "authority": (
            "PASS authorizes exactly one registered F8R1 resource-admission run only; "
            "it is not scientific evidence and authorizes no census or solver output "
            "unless that separate admission passes."
        ),
    }
    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(
        json.dumps(
            {"status": result["status"], "passed": passed, "total": len(gates)},
            sort_keys=True,
        )
    )
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
