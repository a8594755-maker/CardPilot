from pathlib import Path
import importlib.util
import math

import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
RUNNER = BASE / "run_tail.py"
SOURCE = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"


def load_runner():
    spec = importlib.util.spec_from_file_location("tail_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_resume_contract_is_complete():
    checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
    assert checkpoint["iteration"] == 27
    assert checkpoint["total_hands"] == 111390
    assert checkpoint["environment_hand_accounting"]["completed_hands"] == 132553
    assert checkpoint["environment_hand_accounting"]["prefix_complete"] is True
    assert len(checkpoint["optimizer"]["state"]) == 10
    assert len(checkpoint["optimizer"]["param_groups"]) == 1
    assert math.isclose(checkpoint["optimizer"]["param_groups"][0]["lr"], 1e-5, rel_tol=0, abs_tol=1e-15)
    assert checkpoint["actor_ema_updates"] == 27
    assert checkpoint["ppo_replay_entries"] == []


def test_training_command_preserves_resume_semantics(tmp_path):
    runner = load_runner()
    frozen = tmp_path / "frozen"
    run = tmp_path / "production" / "train"
    command = runner.training_command(frozen, run)
    joined = " ".join(command)
    assert "--allow-resume" in command
    assert "--no-reset-optimizer" in command
    assert "--preserve-resumed-optimizer-lr" in command
    assert "--resume-assignment-state-from-provenance" in command
    assert "--fixed-training-deal-start-index 132553" in joined
    assert "--total-environment-hands 262144" in joined
    assert "--reset-optimizer" not in command
    assert "--reset-hand-counter" not in command
    assert "--ppo-replay-buffer-iterations" not in command


def test_preregistration_demotes_training_matrix():
    text = (BASE / "preregistration.md").read_text(encoding="utf-8")
    assert "not held-out generalization evidence" in text
    assert "95% CI lower bound above" in text
    assert "zero Slumbot hands" in text
