import multiprocessing as mp
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    count_completed_environment_hand,
    environment_hand_accounting_snapshot,
    environment_training_target_reached,
    initial_environment_hand_accounting,
    validate_environment_hand_accounting,
)


def fresh():
    return initial_environment_hand_accounting(None, reset_hand_counter=False, run_id='test')


def test_completed_no_decision_hands_are_counted_independently():
    counters = mp.Array('q', 4, lock=True)
    count_completed_environment_hand(counters, 0, has_trainable_decision=True)
    count_completed_environment_hand(counters, 0, has_trainable_decision=False)
    count_completed_environment_hand(counters, 1, has_trainable_decision=True)
    result = environment_hand_accounting_snapshot(fresh(), counters, 2)
    assert result['completed_hands'] == 3
    assert result['no_trainable_decision_hands'] == 1
    assert result['legacy_training_marker_hands'] == 2
    assert result['session_worker_counts'][1]['completed_hands'] == 1


def test_resume_keeps_physical_prefix_and_does_not_double_count_session():
    counters = mp.Array('q', [5, 2], lock=True)
    previous = environment_hand_accounting_snapshot(fresh(), counters, 3)
    base = initial_environment_hand_accounting(
        {'total_hands': 3, 'environment_hand_accounting': previous},
        reset_hand_counter=False, run_id='resume',
    )
    resumed_counters = mp.Array('q', [2, 1], lock=True)
    result = environment_hand_accounting_snapshot(base, resumed_counters, 4)
    assert result['completed_hands'] == 7
    assert result['no_trainable_decision_hands'] == 3
    assert result['session_completed_hands'] == 2
    assert result['origin_run_id'] == 'test'


def test_legacy_unknown_prefix_is_explicit_and_physical_target_fails_closed():
    base = initial_environment_hand_accounting(
        {'total_hands': 1000}, reset_hand_counter=False, run_id='legacy-resume'
    )
    result = environment_hand_accounting_snapshot(base, mp.Array('q', [3, 1]), 1002)
    assert result['completed_hands'] == 3
    assert not result['prefix_complete']
    assert result['unknown_prefix_training_marker_hands'] == 1000
    with pytest.raises(ValueError, match='known environment-hand prefix'):
        environment_training_target_reached(
            legacy_hands=1002, legacy_target=2000, environment_target=2000, accounting=result
        )
    assert not environment_training_target_reached(
        legacy_hands=1002, legacy_target=2000, environment_target=0, accounting=result
    )


def test_explicit_new_run_reset_starts_a_complete_local_physical_counter():
    base = initial_environment_hand_accounting(
        {'total_hands': 1000}, reset_hand_counter=True, run_id='new-run'
    )
    result = environment_hand_accounting_snapshot(base, None, 0)
    assert result['completed_hands'] == 0
    assert result['prefix_complete']
    assert result['origin_run_id'] == 'new-run'


def test_physical_target_overrides_legacy_target_without_changing_counter():
    result = environment_hand_accounting_snapshot(fresh(), mp.Array('q', [10, 3]), 7)
    assert environment_training_target_reached(
        legacy_hands=7, legacy_target=100, environment_target=8, accounting=result
    )
    assert not environment_training_target_reached(
        legacy_hands=7, legacy_target=100, environment_target=0, accounting=result
    )
    assert result['legacy_training_marker_hands'] == 7


def test_invalid_or_overcounted_physical_evidence_is_rejected():
    with pytest.raises(ValueError, match='training markers exceed'):
        environment_hand_accounting_snapshot(fresh(), mp.Array('q', [3, 1]), 3)
    invalid = fresh()
    invalid['no_trainable_decision_hands'] = 1
    with pytest.raises(ValueError, match='invalid environment-hand counts'):
        validate_environment_hand_accounting(invalid)
