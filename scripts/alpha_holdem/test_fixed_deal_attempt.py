from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.alpha_holdem.fixed_deal_attempt import (
    allocate_attempt, attempt_deal_identity, attempt_deck, load_attempt,
)


def allocate(root, namespace="a" * 32):
    return allocate_attempt(root, run_id="resume-test", training_seed=19,
                            worker_seed_base=700, workers=2, envs_per_worker=3,
                            parent_checkpoint_sha256="b" * 64, namespace=namespace)


def test_durable_roundtrip_and_single_use(tmp_path):
    result = allocate(tmp_path)
    assert load_attempt(Path(result["path"]), result["sha256"]) == result["receipt"]
    assert result["receipt"]["hand_count_increment"] == 0
    assert not result["receipt"]["bitwise_uninterrupted_equivalence"]
    with pytest.raises(FileExistsError):
        allocate(tmp_path)


def test_concurrent_claim_has_one_winner(tmp_path):
    def claim(_):
        try:
            allocate(tmp_path)
            return True
        except FileExistsError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(16))) == 1


def test_process_crash_does_not_release_namespace(tmp_path):
    code = (
        "import os,sys; from pathlib import Path; "
        "from scripts.alpha_holdem.fixed_deal_attempt import allocate_attempt; "
        "allocate_attempt(Path(sys.argv[1]),run_id='crash',training_seed=19,"
        "worker_seed_base=700,workers=2,envs_per_worker=3,"
        "parent_checkpoint_sha256=None,namespace='a'*32); os._exit(23)"
    )
    child = subprocess.run([sys.executable, "-c", code, str(tmp_path)],
                           cwd=Path(__file__).resolve().parents[2], timeout=20)
    assert child.returncode == 23
    raw = (tmp_path / ("attempt-" + "a" * 32 + ".json")).read_bytes()
    assert json.loads(raw)["namespace"] == "a" * 32
    with pytest.raises(FileExistsError):
        allocate(tmp_path)


def test_torn_receipt_is_not_reused(tmp_path):
    (tmp_path / ("attempt-" + "a" * 32 + ".json")).write_bytes(b'{"schema":')
    with pytest.raises(FileExistsError):
        allocate(tmp_path)


def test_tampering_rejected(tmp_path):
    result = allocate(tmp_path)
    path = Path(result["path"])
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA256"):
        load_attempt(path, result["sha256"])


def test_namespace_separates_same_seed_and_cursor(tmp_path):
    a = allocate(tmp_path, "a" * 32)["receipt"]["namespace"]
    b = allocate(tmp_path, "c" * 32)["receipt"]["namespace"]
    left, right = set(), set()
    for worker in range(2):
        for env in range(3):
            for deal in range(12):
                x = attempt_deck(700 + worker, env, deal, namespace=a)
                y = attempt_deck(700 + worker, env, deal, namespace=b)
                assert x == attempt_deck(700 + worker, env, deal, namespace=a)
                assert sorted(x) == sorted(y) == list(range(52))
                assert x != y
                left.add(attempt_deal_identity(a, 700 + worker, env, deal))
                right.add(attempt_deal_identity(b, 700 + worker, env, deal))
    assert left.isdisjoint(right)


def test_empty_namespace_preserves_legacy_source_function():
    # Import the unchanged production implementation only for deterministic parity.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scripts.alpha_holdem.train_v5 import fixed_training_deck
    for worker in (700, 701):
        for env in (0, 1):
            for deal in (0, 37, 38300000):
                assert attempt_deck(worker, env, deal) == fixed_training_deck(worker, env, deal)


def test_physical_v6_environment_replays_namespaced_decks():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from alpha_holdem.environment_v6 import HUNLEnvironment
    from scripts.alpha_holdem.train_v5 import exp003_reset_env_with_deck
    env = HUNLEnvironment(starting_stack=200.0)
    for index in range(8):
        deck = attempt_deck(700, 0, index, namespace="a" * 32)
        first = exp003_reset_env_with_deck(env, deck)
        holes = list(env.state.hole_cards)
        cards = first["card_info"].copy()
        second = exp003_reset_env_with_deck(env, deck)
        assert env.state.hole_cards == holes
        assert (cards == second["card_info"]).all()


@pytest.mark.parametrize("namespace", ["", "../escape", "A" * 32, "a" * 31])
def test_invalid_namespace_cannot_allocate(tmp_path, namespace):
    with pytest.raises(ValueError):
        allocate(tmp_path, namespace)
