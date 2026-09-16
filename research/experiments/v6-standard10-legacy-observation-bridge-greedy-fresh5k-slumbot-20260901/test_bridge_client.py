"""Offline journal/client/replay test for the default-off bridge mode."""
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "research/experiments/v6-journaled-client-readiness-20260831"),
]

from alpha_holdem import audit_slumbot_v6_session as audit  # noqa: E402
from alpha_holdem import play_slumbot_v6_journaled as client  # noqa: E402
from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    BRIDGE_CONTRACT,
    external_decision,
    load_policy,
)
from offline_fixture import Server  # noqa: E402

MODEL = ROOT / "models/baseline/standard10/latest.pt"
MODEL_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def test_bridge_journal_and_model_replay(tmp_path):
    torch.set_num_threads(1)
    policy = load_policy(MODEL, "cpu")
    assert policy.sha256 == MODEL_SHA
    server = Server("normal", "legacy_bridge")
    out = tmp_path / "session"
    summary = client.run_session(
        policy,
        MODEL,
        MODEL_SHA,
        hands=2,
        seed=2026090109,
        session_id="legacy_bridge_offline",
        out_dir=out,
        new_hand_fn=server.new_hand,
        act_fn=server.act,
        command=["offline_legacy_bridge_test"],
        policy_mode="greedy",
        decision_fn=external_decision,
        execution_metadata={
            "observation_bridge_contract": BRIDGE_CONTRACT,
            "model_obs_version": "v4",
        },
    )
    assert summary["status"] == "COMPLETED"
    assert summary["observation_bridge_contract"] == BRIDGE_CONTRACT
    report = audit.audit_session(
        out,
        model=policy,
        expected_model_sha256=MODEL_SHA,
        decision_fn=external_decision,
        expected_observation_bridge=BRIDGE_CONTRACT,
    )
    assert report["status"] == "PASS"
    assert report["successful_hands"] == 2
