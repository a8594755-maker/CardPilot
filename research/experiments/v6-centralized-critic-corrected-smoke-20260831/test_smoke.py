import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import run_smoke


def load_parent_tests():
    path = ROOT / "research/experiments/v6-centralized-critic-matched-smoke-20260831/test_smoke.py"
    spec = importlib.util.spec_from_file_location("ctde_parent_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ctde_behavior_loader_and_real_ppo_contracts():
    tests = load_parent_tests()
    tests.test_private_card_encoder_is_opponent_only()
    tests.test_centralized_head_preserves_actor_and_loader_reconstructs()
    tests.test_centralized_ppo_recomputes_baselines_and_updates_only_registered_scope()
    tests.test_cli_flags_are_registered()


def test_corrected_new_seed_commands_do_not_reuse_parent_control():
    command = run_smoke.command("control", BASE / "frozen")
    assert command[command.index("--seed") + 1] == "20261041"
    assert command[command.index("--worker-seed-base") + 1] == "2026104100"
    assert command[command.index("--run-id") + 1] == "v6_ctde_corrected_control_20260831"


def test_training_metric_serializer_contains_preregistered_fields():
    source = (ROOT / "scripts/alpha_holdem/train_v5.py").read_text(encoding="utf-8")
    assert "'centralized_critic': bool(" in source
    assert "'preupdate_critic_mse': float(" in source
