import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "research/experiments/v6-journaled-client-readiness-20260831")]

spec = importlib.util.spec_from_file_location("entropy_smoke", BASE / "run_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
from alpha_holdem.v6_mirror_eval import play_pair
from offline_fixture import ToyPolicy


def test_treatment_command_has_only_registered_entropy_pressure():
    command = smoke.train_command(BASE / "frozen")
    assert command[command.index("--entropy-coef") + 1] == "-.005"
    assert command[command.index("--entropy-floor") + 1] == "0"
    assert command[command.index("--seed") + 1] == "20261042"
    assert command[command.index("--worker-seed-base") + 1] == "2026104200"
    assert "--actor-ema-decay" in command and "--fixed-training-deal-stream" in command
    assert "--centralized-critic" not in command and "--ppo-replay-ratio" not in command


def test_negative_entropy_coefficient_is_a_penalty_in_actor_loss():
    source = (ROOT / "scripts/alpha_holdem/train_mp3_hybrid_h1.py").read_text(encoding="utf-8")
    assert "actor_loss = ploss - ec_t * entropy" in source
    assert float("-.005") < 0


def test_greedy_mirror_pair_is_action_rng_invariant():
    model = ToyPolicy().eval()
    deck = list(range(52))
    first = play_pair(model, model, deck, 1, 0, "cpu", "greedy")
    second = play_pair(model, model, deck, 999, 0, "cpu", "greedy")
    assert first["rewards_bb"] == second["rewards_bb"]
    assert first["decisions"] == second["decisions"]


def test_evaluator_cli_records_policy_mode():
    source = (ROOT / "scripts/alpha_holdem/v6_mirror_eval.py").read_text(encoding="utf-8")
    assert "choices=['sample', 'greedy']" in source
    assert "policy_mode=args.policy_mode" in source
