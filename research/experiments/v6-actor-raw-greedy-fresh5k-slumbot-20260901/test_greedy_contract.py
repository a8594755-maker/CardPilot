import copy
import json
from pathlib import Path
import random
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "research/experiments/v6-journaled-client-readiness-20260831"
sys.path[:0] = [str(ROOT / "scripts"), str(FIXTURES)]
from alpha_holdem import audit_slumbot_v6_session as audit
from alpha_holdem import play_slumbot_v6_journaled as client
from alpha_holdem.execution_v6 import external_decision, sha256_file
from offline_fixture import Server, ToyPolicy


def run_case(tmp_path, mode, seed=101):
    model_path = tmp_path / f"{mode}.txt"
    model_path.write_text("OFFLINE TOY MODEL\n", encoding="utf-8")
    model = ToyPolicy().eval()
    server = Server("normal", f"{mode}_{seed}")
    output = tmp_path / f"session_{mode}_{seed}"
    client.run_session(
        model, model_path, sha256_file(model_path), hands=2, seed=seed,
        session_id=f"{mode}_{seed}", out_dir=output,
        new_hand_fn=server.new_hand, act_fn=server.act,
        command=["offline", mode, str(seed)], policy_mode=mode,
    )
    result = audit.audit_session(output, model=model, expected_model_sha256=sha256_file(model_path))
    rows = [json.loads(line) for line in (output / "hands.jsonl").read_text().splitlines()]
    decisions = [decision for row in rows for decision in row["decisions"]]
    return model, result, decisions


def test_greedy_is_deterministic_legal_argmax_and_audits(tmp_path):
    _, result, decisions = run_case(tmp_path, "greedy")
    assert result["status"] == "PASS" and decisions
    for decision in decisions:
        assert decision["policy_mode"] == "greedy" and decision["temperature"] == 0
        assert decision["selected_action_slot"] == decision["greedy_action_slot"]
        assert decision["behavior_action_probability"] == 1
        assert decision["behavior_probs"] == [float(index == decision["selected_action_slot"]) for index in range(9)]
        assert abs(sum(decision["model_probs"]) - 1) < 1e-12


def test_greedy_action_is_uniform_invariant():
    model = ToyPolicy().eval()
    response = Server("normal", "uniform").new_hand(None)
    first = external_decision(model, response, uniform=0.01, policy_mode="greedy")
    second = external_decision(model, response, uniform=0.99, policy_mode="greedy")
    assert first[0] == second[0]
    assert first[1]["selected_action_slot"] == second[1]["selected_action_slot"]
    assert first[1]["model_probs"] == second[1]["model_probs"]


def test_sample_default_remains_compatible(tmp_path):
    _, result, decisions = run_case(tmp_path, "sample")
    assert result["status"] == "PASS" and decisions
    assert all(decision["policy_mode"] == "sample" and decision["temperature"] == 1 for decision in decisions)
    assert all("model_probs" not in decision for decision in decisions)


def test_greedy_audit_rejects_argmax_tampering(tmp_path):
    model, _, decisions = run_case(tmp_path, "greedy")
    decision = copy.deepcopy(decisions[0])
    legal = [index for index, value in enumerate(decision["legal_mask"]) if value]
    wrong = next(index for index in legal if index != decision["selected_action_slot"])
    decision["behavior_probs"] = [float(index == wrong) for index in range(9)]
    decision["selected_action_slot"] = wrong
    decision["behavior_action_probability"] = 1.0
    with pytest.raises(ValueError, match="Greedy behavior"):
        audit.validate_decision(
            decision, decision["response"], random.Random(101), model, "greedy"
        )
