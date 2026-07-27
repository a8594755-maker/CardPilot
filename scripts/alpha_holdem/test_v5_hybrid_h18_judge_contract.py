from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "reports" / "v5_hybrid_h18_preregistration_20260719.json"
LOCK = sorted((ROOT / "reports").glob("v5_hybrid_h18_design_lock_v*_20260719.json"))[-1]
JUDGE = ROOT / "scripts" / "alpha_holdem" / "v5_hybrid_h18_judge.py"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assignment(tree: ast.AST, name: str) -> ast.AST:
    values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    ]
    assert len(values) == 1, (name, len(values))
    return values[0]


def test_h18_judge_is_the_exact_locked_tool() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8-sig"))
    assert sha(JUDGE) == lock["tools"]["scripts/alpha_holdem/v5_hybrid_h18_judge.py"]
    assert sha(PREREG) == lock["preregistration"]["sha256"]


def test_h18_lock_preserves_every_registered_gate_semantically() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8-sig"))
    lock = json.loads(LOCK.read_text(encoding="utf-8-sig"))
    prereg_gates = prereg["gates"]
    lock_gates = lock["gates"]
    direct = (
        "endpoint_mse_primary_reduction_point_min",
        "endpoint_mse_primary_ci95_lower_min",
        "source_anchor_degradation_point_max",
        "source_anchor_degradation_ci95_upper_max",
        "kl_p95_max",
        "kl_fraction_above_0_03_max",
        "early_stop_trigger_fraction_min",
        "first60_hps_ratio_min",
        "full_hps_ratio_min",
        "entropy_median_last200_min",
        "entropy_treatment_minus_control_min",
    )
    assert all(lock_gates[key] == prereg_gates[key] for key in direct)
    assert lock_gates["mirror_ci95_lower_min_bb100"] == prereg_gates["mirror_treatment_control_ci95_lower_min_bb100"]
    assert lock_gates["mirror_ci95_lower_min_bb100"] == prereg_gates["mirror_treatment_source_ci95_lower_min_bb100"]
    assert lock["measurement"]["mirror_pairs"] == prereg_gates["mirror_pairs"] == 40_000


def test_h18_terminal_checks_cover_all_registered_gates() -> None:
    source = JUDGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    checks_node = assignment(tree, "checks")
    assert isinstance(checks_node, ast.Dict)
    checks = {key.value: ast.unparse(value) for key, value in zip(checks_node.keys, checks_node.values)}
    expected = {
        "endpoint_mse_primary_point": ">= 0.075",
        "endpoint_mse_primary_ci_lower": ">= 0.0",
        "endpoint_mse_anchor_point": "<= 0.05",
        "endpoint_mse_anchor_ci_upper": "<= 0.1",
        "kl_p95": "<= 0.03",
        "kl_excursion_fraction": "<= 0.06044407894736842",
        "early_stop_trigger_fraction": ">= 0.05",
        "throughput_first60": ">= 0.85",
        "throughput_full": ">= 0.85",
        "entropy_floor": ">= 0.3",
        "entropy_noninferior": "- 0.1",
    }
    for name, token in expected.items():
        assert name in checks
        assert token in checks[name], (name, checks[name])
    assert "mirror_control.get('status') == 'PASS'" in checks["mirror_treatment_control"]
    assert "mirror_anchor.get('status') == 'PASS'" in checks["mirror_treatment_anchor"]
    assert "resource_isolation_violations" in checks["resource_isolation"]

    deterministic_node = assignment(tree, "deterministic_names")
    assert isinstance(deterministic_node, ast.Set)
    deterministic = {item.value for item in deterministic_node.elts}
    assert {
        "kl_p95",
        "kl_excursion_fraction",
        "early_stop_trigger_fraction",
        "throughput_first60",
        "throughput_full",
        "entropy_floor",
        "entropy_noninferior",
        "resource_isolation",
    } <= deterministic

    assert 'classification = "H18_FAIL_REGISTERED_GATE"' in source
    assert 'classification = "H18_PASS_ALL_REGISTERED_GATES"' in source
    assert 'classification = "H18_INCONCLUSIVE_FIXED_SAMPLE"' in source
    assert '"official_hands": 0' in source
    assert '"route_review_required": verdict in {"FAIL", "INCONCLUSIVE"}' in source
