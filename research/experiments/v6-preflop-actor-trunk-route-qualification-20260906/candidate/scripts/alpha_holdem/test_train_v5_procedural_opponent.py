from __future__ import annotations

import multiprocessing as mp
import random
import sys
import time
from multiprocessing import shared_memory
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    ACTION_SIZE,
    CARD_SIZE,
    EXTRA_SIZE,
    HERO_MODEL_ID,
    IDLE,
    NUM_ACTIONS,
    OBS_SIZE,
    PROCEDURAL_COUNTER_STRIDE,
    PROCEDURAL_OPPONENT_PROFILES,
    READY,
    RESULT_SIZE,
    WAITING,
    procedural_opponent_action,
    procedural_opponent_hand_seed,
    procedural_opponent_accounting_snapshot,
    procedural_opponent_metrics_add,
    procedural_opponent_metrics_template,
    procedural_public_equity_signal,
    sample_procedural_opponent_style,
    initial_procedural_opponent_accounting,
    worker_process_v5,
)


def test_hand_seed_and_style_are_replayable_and_worker_separated():
    seed = procedural_opponent_hand_seed(91000, 17)
    assert seed == procedural_opponent_hand_seed(91000, 17)
    assert seed != procedural_opponent_hand_seed(91001, 17)
    assert seed != procedural_opponent_hand_seed(91000, 18)

    first = sample_procedural_opponent_style(random.Random(seed))
    second = sample_procedural_opponent_style(random.Random(seed))
    assert first == second


def test_style_sampler_covers_every_registered_profile_with_valid_parameters():
    observed = set()
    for hand_index in range(4096):
        rng = random.Random(procedural_opponent_hand_seed(92000, hand_index))
        style = sample_procedural_opponent_style(rng)
        observed.add(style['profile_id'])
        assert 0.0 <= style['looseness'] <= 1.0
        assert 0.0 <= style['aggression'] <= 1.0
        assert 0.0 <= style['bluff_rate'] <= 1.0
        assert 2.0 <= style['raise_slot_center'] <= 8.0
        assert 0.45 <= style['raise_slot_spread'] <= 2.25
    assert observed == set(range(len(PROCEDURAL_OPPONENT_PROFILES)))


def test_visible_card_equity_does_not_depend_on_actual_hidden_opponent_cards():
    common = dict(board=[16, 21, 34], street_committed=[2.0, 4.0], pot=7.5)
    state_a = SimpleNamespace(hole_cards=[(48, 49), (0, 1)], **common)
    state_b = SimpleNamespace(hole_cards=[(48, 49), (44, 45)], **common)
    first = procedural_public_equity_signal(
        state_a, 0, random.Random(12345), samples=32
    )
    second = procedural_public_equity_signal(
        state_b, 0, random.Random(12345), samples=32
    )
    assert first == second


def test_action_sampler_is_legal_replayable_and_broad():
    state = SimpleNamespace(
        hole_cards=[(8, 13), (40, 41)],
        board=[16, 21, 34],
        street_committed=[2.0, 4.0],
        pot=7.5,
    )
    env = SimpleNamespace(state=state)
    legal_mask = np.ones(NUM_ACTIONS, dtype=np.float32)
    actions = []
    for hand_index in range(2048):
        seed = procedural_opponent_hand_seed(93000, hand_index)
        rng = random.Random(seed)
        style = sample_procedural_opponent_style(rng)
        action = procedural_opponent_action(
            env, 0, legal_mask, style, rng, equity_samples=4
        )
        actions.append(action)
        replay_rng = random.Random(seed)
        replay_style = sample_procedural_opponent_style(replay_rng)
        assert action == procedural_opponent_action(
            env, 0, legal_mask, replay_style, replay_rng, equity_samples=4
        )
        assert legal_mask[action] > 0
    assert any(action == 0 for action in actions)
    assert any(action == 1 for action in actions)
    assert len({action for action in actions if action >= 2}) >= 5


def test_metrics_aggregation_preserves_style_and_action_counts():
    dst = procedural_opponent_metrics_template()
    src = procedural_opponent_metrics_template()
    src['hands'] = 3
    src['decisions'] = 7
    src['inference_bypasses'] = 7
    src['style_counts'][2] = 3
    src['action_counts'][1] = 4
    src['action_counts'][6] = 3
    procedural_opponent_metrics_add(dst, src)
    assert dst['hands'] == 3
    assert dst['decisions'] == dst['inference_bypasses'] == 7
    assert sum(dst['style_counts']) == 3
    assert sum(dst['action_counts']) == 7


def test_real_single_worker_bypasses_all_opponent_inference_requests():
    obs_shm = shared_memory.SharedMemory(create=True, size=OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=4)
    request_shm = shared_memory.SharedMemory(create=True, size=4)
    parent, child = mp.Pipe()
    stop = mp.Event()
    epsilon = mp.Value('d', 0.0)
    counters = mp.Array('q', 2, lock=True)
    procedural_counters = mp.Array('q', PROCEDURAL_COUNTER_STRIDE, lock=True)
    obs = np.ndarray((OBS_SIZE,), np.float32, buffer=obs_shm.buf)
    result = np.ndarray((RESULT_SIZE,), np.float32, buffer=result_shm.buf)
    status = np.ndarray((1,), np.int32, buffer=status_shm.buf)
    assigned = np.ndarray((1,), np.int32, buffer=assigned_shm.buf)
    request = np.ndarray((1,), np.int32, buffer=request_shm.buf)
    obs[:] = 0
    result[:] = 0
    status[:] = IDLE
    assigned[:] = 0
    request[:] = HERO_MODEL_ID

    process = mp.Process(
        target=worker_process_v5,
        args=(
            0,
            obs_shm.name,
            result_shm.name,
            status_shm.name,
            assigned_shm.name,
            request_shm.name,
            child,
            stop,
            epsilon,
            200.0,
            'v6',
            94000,
            False,
            False,
            False,
            200,
            True,
            0,
            False,
            200,
            2026082801,
            'model',
            False,
            counters,
            1.0,
            procedural_counters,
        ),
    )
    process.start()
    child.close()
    inference_requests = []
    aggregate = procedural_opponent_metrics_template()
    deadline = time.time() + 30.0
    try:
        while time.time() < deadline and aggregate['hands'] < 50:
            if status[0] == WAITING:
                inference_requests.append(int(request[0]))
                legal_mask = obs[
                    CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:
                ]
                legal = np.flatnonzero(legal_mask > 0)
                assert len(legal) > 0
                action = 1 if legal_mask[1] > 0 else int(legal[0])
                result[:] = (float(action), 0.0, 0.0)
                status[0] = READY
            while parent.poll():
                message = parent.recv()
                if (
                    isinstance(message, dict)
                    and message.get('type') == 'procedural_opponent_metrics'
                ):
                    procedural_opponent_metrics_add(aggregate, message)
            time.sleep(0.0001)
        assert aggregate['hands'] >= 50
        assert aggregate['decisions'] > 0
        assert aggregate['decisions'] == aggregate['inference_bypasses']
        assert sum(aggregate['style_counts']) == aggregate['hands']
        assert sum(aggregate['action_counts']) == aggregate['decisions']
        assert inference_requests
        assert set(inference_requests) == {HERO_MODEL_ID}
        assert int(counters[0]) >= aggregate['hands']
        exact = procedural_opponent_accounting_snapshot(
            initial_procedural_opponent_accounting(
                None, reset_hand_counter=False
            ),
            procedural_counters,
        )
        assert exact['session_hands'] >= aggregate['hands']
        assert exact['session_decisions'] == exact['session_inference_bypasses']
        assert sum(exact['session_style_counts']) == exact['session_hands']
        assert sum(exact['session_action_counts']) == exact['session_decisions']
    finally:
        stop.set()
        process.join(timeout=10.0)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5.0)
        parent.close()
        for segment in (
            obs_shm,
            result_shm,
            status_shm,
            assigned_shm,
            request_shm,
        ):
            segment.close()
            segment.unlink()
    assert process.exitcode == 0
