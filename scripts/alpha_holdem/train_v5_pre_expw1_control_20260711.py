#!/usr/bin/env python3
"""
AlphaHoldem V5 trainer — EXP-002 batched multi-env rollout candidate.

This file is the EXP-002 development copy of train_v5.py (live trainer left
untouched on disk per the ledger invariant). Differences vs train_v5.py:

1. --rollout-mode multi + --rollout-envs-per-worker M: each worker owns M
   environments and batches their pending decisions (W x M shm slots) so GPU
   inference batch size rises from ~10 to hundreds. Default remains the old
   single-env path.
2. GAE trajectory-contiguity invariant (ledger EXP-002 blocker 1): multi-env
   workers buffer per env and emit each completed poker hand as ONE contiguous
   block into the transition stream. Decisions from different envs never
   interleave inside a hand block; hand_marker accounting is unchanged.
3. Deterministic seeding (ledger EXP-002 blocker 2, option a): --worker-seed-base
   seeds random/numpy inside every worker (both rollout modes) as base+worker_id,
   enabling the registered W=1/M=1 byte-equivalence gate on CPU.
4. Request accumulation window (ledger EXP-002 blocker 3):
   --inference-min-batch-slots N + --inference-batch-deadline-us D make the main
   loop wait for N pending slots (or D microseconds since the last serve) before
   dispatching inference, so large batches actually form.
5. --trace-transitions-file: debug hook writing one sha256 digest per transition
   in arrival order, used by the equivalence test only.

Cutover to this trainer is gate-boundary-only, owned by Codex, after EXP-004
step-1 judgment, per reports/v5_experiment_ledger.md.

---- original train_v5.py header follows ----
AlphaHoldem V5.0 trainer — quick wins on top of V4 (train_mp3.py).

V5.0 changes vs V4:
1. epsilon=0 default (no epsilon-greedy noise -> clean PPO ratio)
2. Both-player transition collection in self-play hands (~2x trainable_decisions/sec)
3. Action table cache in worker (eliminate duplicate state.legal_actions())
4. Flat obs view for inference (no list->array->tensor triple copy)
5. Loss-selected K-best opponent pool by default; latest-K remains available as
   an ablation until a full ELO survivor tournament is wired in.
6. Split shm: assigned_opp_id (main writes once/iter) vs request_model_id (worker writes/action)
   Fixes V4 race condition where worker overwrote main's opponent assignment.
7. New monitoring metrics: trainable_decisions/sec, inference_batch_size_mean,
   ppo_time, collect_time, advantage_std

V4 baseline preserved untouched: train_mp3.py / alpha_holdem_v4_final.pt.

Typical resume from V4 final:
  python scripts/alpha_holdem/train_v5.py \\
    --resume models/alpha_holdem_v4_final.pt \\
    --out models/alpha_holdem_v5.pt \\
    --device cuda --workers 28 \\
    --total-hands 1100000000 \\
    --lr 1e-4 --epsilon 0
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import time
import math
import random
import multiprocessing as mp
from multiprocessing import shared_memory
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from itertools import combinations
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment import NUM_ACTIONS

# Reuse V4 PPO + GAE math (unchanged in V5.0; V5.2 introduces all-in EV / pot-norm value)
from alpha_holdem.train_mp3 import compute_gae, trinal_clip_ppo_update

# ===========================================================
# Shared Memory Layout
# ===========================================================

CARD_SIZE = 6 * 4 * 13       # 312
ACTION_SIZE = 25 * 4 * 5     # 500
EXTRA_SIZE = 2
MASK_SIZE = NUM_ACTIONS       # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 823
RESULT_SIZE = 3  # action_idx, log_prob, value

IDLE = 0
WAITING = 1
READY = 2

HERO_MODEL_ID = -1  # request_model_id sentinel for "use hero model"


def build_group_opponent_assignments(worker_count: int, pool_size: int,
                                     group_count: int = 5,
                                     self_play_fraction: float = 0.2,
                                     rng=None):
    """Build EXP-005 balanced per-group opponent assignments.

    Worker membership is reshuffled on every call, groups differ in size by at
    most one, and a rounded fraction of groups is forced to hero self-play.
    Pool groups receive distinct snapshots whenever the pool is large enough.
    The returned metadata is intentionally testable and can be logged without
    exposing mutable shared-memory state.
    """
    if worker_count <= 0:
        raise ValueError('worker_count must be positive')
    if pool_size <= 0:
        raise ValueError('pool_size must be positive')
    if group_count <= 0:
        raise ValueError('group_count must be positive')
    if not 0.0 <= self_play_fraction <= 1.0:
        raise ValueError('self_play_fraction must be in [0, 1]')

    rng = rng or random
    group_count = min(int(group_count), int(worker_count))
    worker_ids = list(range(int(worker_count)))
    rng.shuffle(worker_ids)
    groups = [worker_ids[i::group_count] for i in range(group_count)]

    self_play_group_count = int(round(group_count * self_play_fraction))
    self_play_group_count = max(0, min(group_count, self_play_group_count))
    self_play_groups = set(rng.sample(range(group_count), self_play_group_count))
    pool_groups = [i for i in range(group_count) if i not in self_play_groups]

    if len(pool_groups) <= pool_size:
        pool_opponents = rng.sample(range(pool_size), len(pool_groups))
    else:
        pool_opponents = [rng.randrange(pool_size) for _ in pool_groups]
    pool_assignment = dict(zip(pool_groups, pool_opponents))

    assignments = np.empty(worker_count, dtype=np.int64)
    group_metadata = []
    for group_id, members in enumerate(groups):
        opponent_id = HERO_MODEL_ID if group_id in self_play_groups else pool_assignment[group_id]
        assignments[members] = opponent_id
        group_metadata.append({
            'group_id': group_id,
            'workers': list(members),
            'opponent_id': int(opponent_id),
        })

    metadata = {
        'group_count': group_count,
        'groups': group_metadata,
        'self_play_group_count': self_play_group_count,
        'self_play_worker_count': int(np.sum(assignments == HERO_MODEL_ID)),
        'distinct_pool_opponents': len(set(int(x) for x in assignments if int(x) >= 0)),
    }
    return assignments, metadata


def build_assignment_provenance_record(*, run_id: str, applies_to_iteration: int,
                                       total_hands: int, assignment_mode: str,
                                       assignments, pool_snapshots,
                                       group_metadata=None,
                                       worker_seed_base=None,
                                       previous_record_sha256: str | None = None):
    """Build one hash-chained, reporting-only opponent assignment record."""
    refs = []
    for local_index, snapshot in enumerate(pool_snapshots):
        refs.append({
            'local_index': int(local_index),
            'snapshot_id': int(snapshot.get('id')),
            'snapshot_hands': int(snapshot.get('hands') or 0),
            'snapshot_iteration': snapshot.get('iteration'),
        })
    workers = []
    for worker_id, local_index_raw in enumerate(assignments):
        local_index = int(local_index_raw)
        if local_index == HERO_MODEL_ID:
            opponent = {'kind': 'self_play', 'local_index': HERO_MODEL_ID}
        else:
            if local_index < 0 or local_index >= len(refs):
                raise ValueError(f'assignment local index {local_index} outside pool size {len(refs)}')
            ref = refs[local_index]
            opponent = {
                'kind': 'pool_snapshot',
                'local_index': local_index,
                'snapshot_id': ref['snapshot_id'],
                'snapshot_hands': ref['snapshot_hands'],
                'snapshot_iteration': ref['snapshot_iteration'],
            }
        workers.append({'worker_id': int(worker_id), 'opponent': opponent})
    record = {
        'schema_version': 'v5.opponent_assignment_provenance.v1',
        'run_id': str(run_id),
        'applies_to_iteration': int(applies_to_iteration),
        'total_hands_before_iteration': int(total_hands),
        'assignment_mode': str(assignment_mode),
        'worker_seed_base': worker_seed_base,
        'worker_count': len(workers),
        'pool_size': len(refs),
        'pool_snapshot_refs': refs,
        'workers': workers,
        'group_metadata': group_metadata,
        'previous_record_sha256': previous_record_sha256,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    record['record_sha256'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return record


def action_mix(transitions) -> dict:
    """Return fold/call/raise/all-in frequencies for trainable decisions."""
    n = len(transitions)
    if n <= 0:
        return {'fold': 0.0, 'call': 0.0, 'raise': 0.0, 'allin': 0.0}
    fold = call = raise_ = allin = 0
    for t in transitions:
        action_idx = int(t[4])
        if action_idx == 0:
            fold += 1
        elif action_idx == 1:
            call += 1
        elif action_idx == 8:
            allin += 1
        else:
            raise_ += 1
    denom = float(n)
    return {
        'fold': fold / denom,
        'call': call / denom,
        'raise': raise_ / denom,
        'allin': allin / denom,
    }


def is_preflop_transition(transition) -> bool:
    """Infer preflop from the card tensor: public-card channel is empty."""
    try:
        cards = np.asarray(transition[0], dtype=np.float32).reshape(6, 4, 13)
    except Exception:
        return False
    return float(cards[4].sum()) <= 1e-6


def action_mix_by_phase(transitions) -> dict:
    """Return action mix split by preflop vs postflop trainable decisions."""
    preflop = []
    postflop = []
    for transition in transitions:
        if is_preflop_transition(transition):
            preflop.append(transition)
        else:
            postflop.append(transition)
    return {
        'preflop': action_mix(preflop),
        'postflop': action_mix(postflop),
        'preflop_decisions': len(preflop),
        'postflop_decisions': len(postflop),
    }


def selection_loss_from_stats(stats: dict) -> float:
    """Proxy model-selection loss for loss-kbest pool selection.

    The paper selects strong historical versions using competition/ELO and notes
    that lower Trinal-Clip loss is a useful model-selection signal. A full ELO
    tournament during every snapshot is too expensive for this single-GPU run, so
    loss-kbest uses a cheap monotonic proxy and logs the deviation explicitly.
    """
    policy_loss = float(stats.get('policy_loss', 0.0) or 0.0)
    value_loss = max(0.0, float(stats.get('value_loss', 0.0) or 0.0))
    return policy_loss + 0.5 * math.log1p(value_loss)


def validate_stream_message(data) -> None:
    """
    EXP-002 blocker-1 runtime assertion: verify a pipe message is a sequence of
    whole poker hands, each hand = 1-2 contiguous done-terminated trajectories
    with exactly one hand_marker, rewards only on terminals. Raises AssertionError.
    """
    assert len(data) > 0, 'empty stream message'
    assert float(data[-1][8]) > 0.5, 'message does not end at a trajectory terminal'
    trajs = []  # list of (has_marker, length)
    cur_len, cur_marker = 0, False
    for t in data:
        cur_len += 1
        done = float(t[8]) > 0.5
        marker = len(t) > 11 and float(t[11]) > 0.5
        if marker:
            assert done, 'hand_marker on a non-terminal transition'
            cur_marker = True
        if not done:
            assert abs(float(t[6])) < 1e-12, 'nonzero reward on non-terminal transition'
        if done:
            trajs.append((cur_marker, cur_len))
            cur_len, cur_marker = 0, False
    assert cur_len == 0, 'trailing incomplete trajectory in message'
    prev_marker = None
    for has_marker, _ in trajs:
        if not has_marker:
            assert prev_marker is True, (
                'non-marker trajectory not immediately preceded by a marker trajectory '
                '(hand blocks interleaved or marker lost)'
            )
            prev_marker = False  # a hand has at most 2 trajectories
        else:
            prev_marker = True


def transition_digest(t) -> str:
    """Stable sha256 digest of one transition tuple (equivalence testing only)."""
    h = hashlib.sha256()
    h.update(np.asarray(t[0], dtype=np.float32).tobytes())
    h.update(np.asarray(t[1], dtype=np.float32).tobytes())
    h.update(np.asarray(t[2], dtype=np.float32).tobytes())
    h.update(np.asarray(t[3], dtype=np.float32).tobytes())
    marker = float(t[11]) if len(t) > 11 else 0.0
    h.update(struct.pack(
        '<q5d',
        int(t[4]), float(t[5]), float(t[6]), float(t[7]),
        float(t[8]), float(t[9]),
    ) + struct.pack('<2d', float(t[10]), marker))
    return h.hexdigest()


def parse_action_prior_target(text: str) -> list[float]:
    parts = [part.strip() for part in str(text).split(',') if part.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "expected four comma-separated class weights: fold,call,raise,allin"
        )
    try:
        values = [float(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if any(value < 0.0 for value in values):
        raise argparse.ArgumentTypeError("action-prior weights must be non-negative")
    if sum(values) <= 0.0:
        raise argparse.ArgumentTypeError("at least one action-prior weight must be positive")
    total = float(sum(values))
    return [value / total for value in values]


def exp003_metrics_template() -> dict:
    return {
        'mirror_source_hands': 0,
        'mirror_replay_hands': 0,
        'allin_ev_replacements': 0,
        'allin_ev_runouts': 0,
        'allin_ev_skipped_hands': 0,
        'allin_ev_skipped_runouts': 0,
    }


def exp003_metrics_nonzero(metrics: dict) -> bool:
    return any(int(v) != 0 for v in metrics.values())


def exp003_metrics_add(dst: dict, src: dict) -> None:
    for k in dst:
        dst[k] += int(src.get(k, 0) or 0)


EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS = 200


def exp003_mirrored_deck_from_env(env):
    """Return a deck with P0/P1 hole cards swapped and future board order kept."""
    state = getattr(env, 'state', None)
    deck = list(getattr(state, 'deck', []) or [])
    if len(deck) < 4:
        return None
    return [deck[2], deck[3], deck[0], deck[1], *deck[4:]]


def exp003_reset_env_with_deck(env, deck):
    """
    Reset env, then replace the shuffled deck with a registered mirrored deck.
    This avoids changing environment_v55 defaults used by live eval/watchers.
    """
    env.reset()
    deck = list(deck)
    state = env.state
    state.deck = deck.copy()
    state.hole_cards = [(deck[0], deck[1]), (deck[2], deck[3])]
    if getattr(state.config, 'include_preflop', True):
        state.board = []
    else:
        state.board = [deck[4], deck[5], deck[6]]
    env._legal_calls_this_hand = 0
    return env._get_obs()


def fixed_training_deck(worker_seed: int, env_index: int, deal_index: int) -> list[int]:
    """Deterministic per-worker/env/deal deck for controlled same-start arms."""
    if worker_seed is None:
        raise ValueError('fixed training deal stream requires worker_seed')
    material = f'v5.fixed.training.deal.v1:{int(worker_seed)}:{int(env_index)}:{int(deal_index)}'
    seed = int.from_bytes(hashlib.sha256(material.encode('utf-8')).digest()[:16], 'big')
    deck = list(range(52))
    random.Random(seed).shuffle(deck)
    return deck


@lru_cache(maxsize=200000)
def exp003_exact_showdown_counts(hole0, hole1, board_tuple):
    """Exact P0 win/loss/tie counts over all missing board runouts."""
    from deep_cfr.hand_eval import compare_hands

    board = list(board_tuple)
    used = set(hole0) | set(hole1) | set(board)
    remaining = [c for c in range(52) if c not in used]
    need = 5 - len(board)
    if need < 0:
        raise ValueError('board has more than 5 cards')
    p0_win = p0_loss = ties = total = 0
    for runout in combinations(remaining, need):
        cmp = compare_hands(hole0, hole1, board + list(runout))
        if cmp > 0:
            p0_win += 1
        elif cmp < 0:
            p0_loss += 1
        else:
            ties += 1
        total += 1
    return p0_win, p0_loss, ties, total


def exp003_sampled_showdown_counts(hole0, hole1, board_tuple, sample_runouts: int):
    """Deterministic bounded-K P0 win/loss/tie counts over missing board runouts."""
    from deep_cfr.hand_eval import compare_hands

    board = list(board_tuple)
    used = set(hole0) | set(hole1) | set(board)
    remaining = [c for c in range(52) if c not in used]
    need = 5 - len(board)
    if need < 0:
        raise ValueError('board has more than 5 cards')
    total_runouts = math.comb(len(remaining), need)
    target = min(max(int(sample_runouts), 0), int(total_runouts))
    if target <= 0:
        return 0, 0, 0, 0

    seed_payload = (
        f"h0={','.join(map(str, hole0))};"
        f"h1={','.join(map(str, hole1))};"
        f"b={','.join(map(str, board_tuple))};"
        f"need={need};total={total_runouts}"
    ).encode('ascii')
    rng = random.Random(int.from_bytes(hashlib.sha256(seed_payload).digest()[:8], 'big'))

    sampled = []
    seen = set()
    attempts = 0
    max_attempts = max(100, target * 20)
    while len(sampled) < target and attempts < max_attempts:
        attempts += 1
        runout = tuple(sorted(rng.sample(remaining, need)))
        if runout in seen:
            continue
        seen.add(runout)
        sampled.append(runout)

    if len(sampled) < target:
        for runout in combinations(remaining, need):
            runout = tuple(runout)
            if runout in seen:
                continue
            sampled.append(runout)
            if len(sampled) >= target:
                break

    p0_win = p0_loss = ties = total = 0
    for runout in sampled:
        cmp = compare_hands(hole0, hole1, board + list(runout))
        if cmp > 0:
            p0_win += 1
        elif cmp < 0:
            p0_loss += 1
        else:
            ties += 1
        total += 1
    return p0_win, p0_loss, ties, total


def exp003_allin_ev_reward(
    state,
    acting_player: int,
    pre_board,
    max_runouts: int = EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
) -> tuple[float, int, bool] | None:
    """
    Replace sampled all-in runout payoff with exact or bounded-K EV.

    The reward remains in the trainer's existing profit units: win earns the
    opponent's invested chips, loss loses own invested chips, tie contributes 0.
    """
    if state is None or getattr(state, 'folded_player', -1) >= 0:
        return None
    if not getattr(state, 'is_done', False) or len(getattr(state, 'board', [])) != 5:
        return None
    pre_board = tuple(pre_board or ())
    if len(pre_board) >= 5:
        return None
    if state.hole_cards[0] is None or state.hole_cards[1] is None:
        return None
    if state.stacks[0] > 1e-9 and state.stacks[1] > 1e-9:
        return None

    hole0 = tuple(sorted(state.hole_cards[0]))
    hole1 = tuple(sorted(state.hole_cards[1]))
    board_key = tuple(sorted(pre_board))
    used = set(hole0) | set(hole1) | set(board_key)
    need = 5 - len(board_key)
    if need < 0:
        return None
    total_runouts = math.comb(52 - len(used), need)
    if max_runouts > 0 and total_runouts > max_runouts:
        p0_win, p0_loss, _ties, total = exp003_sampled_showdown_counts(
            hole0,
            hole1,
            board_key,
            max_runouts,
        )
    else:
        p0_win, p0_loss, _ties, total = exp003_exact_showdown_counts(hole0, hole1, board_key)
    if total <= 0:
        return None

    invested = [
        float(state.config.effective_stack - state.stacks[0]),
        float(state.config.effective_stack - state.stacks[1]),
    ]
    p = int(acting_player)
    if p == 0:
        win_prob = p0_win / total
        loss_prob = p0_loss / total
    else:
        win_prob = p0_loss / total
        loss_prob = p0_win / total
    ev = win_prob * invested[1 - p] - loss_prob * invested[p]
    return ev, total, False


# ===========================================================
# Worker (V5.0): both-player collection + action cache + split shm
# ===========================================================

def worker_process_v5(
    worker_id,
    obs_shm_name,
    result_shm_name,
    status_shm_name,
    assigned_opp_shm_name,    # V5.0: read-only for worker (main writes per iter)
    request_model_shm_name,   # V5.0: write-only for worker (per inference)
    transition_pipe,
    stop_event,
    epsilon_value,
    starting_stack,
    env_version,
    worker_seed=None,         # EXP-002: deterministic per-worker seeding
    mirror_self_play_deals=False,
    allin_runout_ev=False,
    allin_runout_ev_max_runouts=EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
    fixed_training_deal_stream=False,
):
    """
    Persistent self-play worker.
    V5.0: collects transitions for BOTH players when current_opp_id == -1 (self-play).
    """
    import sys as _sys
    import os as _os
    import time as _time
    import random as _random
    import numpy as _np
    from multiprocessing import shared_memory as _shm

    if worker_seed is not None:
        _random.seed(worker_seed)
        _np.random.seed(worker_seed % (2**32))

    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    if env_version == 'v4':
        from alpha_holdem.environment import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}
    elif env_version == 'v55cap1':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack, 'raise_cap_per_street': 1}
    elif env_version == 'v55cap1v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'raise_cap_per_street': 1,
            'action_history_style': 'v4',
        }
    else:
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}

    obs_shm = _shm.SharedMemory(name=obs_shm_name)
    result_shm = _shm.SharedMemory(name=result_shm_name)
    status_shm = _shm.SharedMemory(name=status_shm_name)
    assigned_shm = _shm.SharedMemory(name=assigned_opp_shm_name)
    request_shm = _shm.SharedMemory(name=request_model_shm_name)

    obs_buf = _np.ndarray(
        (OBS_SIZE,), dtype=_np.float32,
        buffer=obs_shm.buf[worker_id * OBS_SIZE * 4:(worker_id + 1) * OBS_SIZE * 4],
    )
    result_buf = _np.ndarray(
        (RESULT_SIZE,), dtype=_np.float32,
        buffer=result_shm.buf[worker_id * RESULT_SIZE * 4:(worker_id + 1) * RESULT_SIZE * 4],
    )
    status_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=status_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    assigned_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=assigned_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    request_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=request_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )

    env = HUNLEnvironment(**env_kwargs)
    hands_played = 0
    local_transitions = []
    local_metrics = exp003_metrics_template()
    pending_mirror_deck = None
    source_deal_index = 0

    try:
        while not stop_event.is_set():
            # Read this hand's opponent assignment (main writes per iter; we only read).
            # EXP-003 mirrored replay is always self-play and keeps the original board order.
            is_mirror_replay = pending_mirror_deck is not None
            if is_mirror_replay:
                current_opp_id = -1
                obs = exp003_reset_env_with_deck(env, pending_mirror_deck)
                pending_mirror_deck = None
                local_metrics['mirror_replay_hands'] += 1
            else:
                current_opp_id = int(assigned_buf[0])
                if fixed_training_deal_stream:
                    obs = exp003_reset_env_with_deck(
                        env, fixed_training_deck(worker_seed, 0, source_deal_index)
                    )
                    source_deal_index += 1
                else:
                    obs = env.reset()
                if mirror_self_play_deals and current_opp_id == -1:
                    mirror_deck = exp003_mirrored_deck_from_env(env)
                    if mirror_deck is not None:
                        pending_mirror_deck = mirror_deck
                        local_metrics['mirror_source_hands'] += 1
            is_self_play = (current_opp_id == -1)

            done = False
            hero_player = hands_played % 2

            # V5.0: per-player buffers for both-player collect
            hand_buffers = {0: [], 1: []}
            last_actor = None

            while not done and not stop_event.is_set():
                player = obs['player']
                is_hero = (player == hero_player)

                # V5.0: which model serves this inference?
                # - self-play: hero model for both sides
                # - opp-mode: hero model when is_hero, opp pool model otherwise
                req_model = HERO_MODEL_ID if (is_self_play or is_hero) else current_opp_id

                ci = obs['card_info'].flatten()
                ai = obs['action_info'].flatten()
                ei = obs['extra_info']
                lm = obs['legal_mask']

                obs_buf[:CARD_SIZE] = ci
                obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
                obs_buf[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
                obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

                request_buf[0] = req_model     # V5.0: separate from assigned_buf
                status_buf[0] = WAITING

                while status_buf[0] != READY:
                    if stop_event.is_set():
                        break
                    _time.sleep(0.000001)

                if stop_event.is_set():
                    break

                action_idx = int(result_buf[0])
                log_prob = float(result_buf[1])
                value = float(result_buf[2])
                status_buf[0] = IDLE

                eps = epsilon_value.value
                if is_hero and eps > 0.0 and _random.random() < eps:
                    # V5.0 default eps=0 so this branch is normally dead.
                    # Kept gated for backwards-compat / ablation.
                    legal = _np.where(lm > 0)[0]
                    if len(legal) > 0:
                        action_idx = int(_random.choice(legal))

                # V5.0: collect for both players when self-play, else only hero
                acted_by_trainable_model = is_self_play or is_hero
                if acted_by_trainable_model:
                    hand_buffers[player].append((
                        ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                        action_idx, log_prob, value,
                    ))

                last_actor = player
                pre_board = tuple(env.state.board) if allin_runout_ev and env.state is not None else None
                obs, reward, done = env.step(action_idx)
                if done and allin_runout_ev:
                    ev_result = exp003_allin_ev_reward(
                        env.state,
                        player,
                        pre_board,
                        allin_runout_ev_max_runouts,
                    )
                    if ev_result is not None:
                        ev_reward, runouts, skipped = ev_result
                        if skipped:
                            local_metrics['allin_ev_skipped_hands'] += 1
                            local_metrics['allin_ev_skipped_runouts'] += int(runouts)
                        else:
                            reward = ev_reward
                            local_metrics['allin_ev_replacements'] += 1
                            local_metrics['allin_ev_runouts'] += int(runouts)

            # EXP-002 hygiene: if we were stopped mid-hand, drop the incomplete
            # hand instead of emitting a fake terminal (live train_v5.py emits it;
            # only affects shutdown garbage, never counted hands).
            if not done:
                break

            # Hand terminal: chips_committed for Trinal-Clip dynamic value bounds
            chips = {
                0: env.chips_committed(0),
                1: env.chips_committed(1),
            }

            # Reward is from last_actor's perspective. Convert per player.
            rewards_per_player = {}
            if last_actor is not None:
                rewards_per_player[last_actor] = reward
                rewards_per_player[1 - last_actor] = -reward

            # Build transitions per player. The final field marks exactly one
            # transition per poker hand so total_hands stays aligned with the
            # paper's hand count even when collecting both players' trajectories.
            counted_hand = False
            for p in (0, 1):
                buf = hand_buffers[p]
                if not buf:
                    continue
                pr = rewards_per_player.get(p, 0.0)
                p_chips = chips[p]
                v_chips = chips[1 - p]
                for i, (ci_s, ai_s, ei_s, lm_s, act, lp, val) in enumerate(buf):
                    is_last = (i == len(buf) - 1)
                    hand_marker = 1.0 if is_last and not counted_hand else 0.0
                    if hand_marker:
                        counted_hand = True
                    local_transitions.append((
                        ci_s, ai_s, ei_s, lm_s, act, lp,
                        pr if is_last else 0.0,
                        val,
                        1.0 if is_last else 0.0,
                        p_chips,
                        v_chips,
                        hand_marker,
                    ))

            hands_played += 1

            if hands_played % 50 == 0 and local_transitions:
                try:
                    transition_pipe.send(local_transitions)
                    if exp003_metrics_nonzero(local_metrics):
                        transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
                        local_metrics = exp003_metrics_template()
                except BrokenPipeError:
                    break
                local_transitions = []

        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
                if exp003_metrics_nonzero(local_metrics):
                    transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
            except BrokenPipeError:
                pass

        try:
            transition_pipe.send(None)
        except BrokenPipeError:
            pass

    finally:
        obs_shm.close()
        result_shm.close()
        status_shm.close()
        assigned_shm.close()
        request_shm.close()


# ===========================================================
# EXP-002 Worker: M environments per worker, batched requests
# ===========================================================

def worker_process_v5_multi(
    worker_id,
    envs_per_worker,
    obs_shm_name,
    result_shm_name,
    status_shm_name,
    assigned_opp_shm_name,
    request_model_shm_name,
    transition_pipe,
    stop_event,
    epsilon_value,
    starting_stack,
    env_version,
    worker_seed=None,
    mirror_self_play_deals=False,
    allin_runout_ev=False,
    allin_runout_ev_max_runouts=EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
    fixed_training_deal_stream=False,
):
    """
    EXP-002 multi-env worker. Owns M environments; slot s = worker_id*M + e.

    INVARIANTS (ledger EXP-002):
    - Each completed poker hand is appended to local_transitions as ONE contiguous
      block (both players' trajectories, each done-terminated), never interleaved
      with other envs' decisions. compute_gae depends on this.
    - hand_marker: exactly one transition per poker hand carries marker=1.0.
    - Opponent assignment is read once per hand at hand start (same as single path).
    - Incomplete hands at shutdown are discarded, never emitted.
    """
    import sys as _sys
    import os as _os
    import time as _time
    import random as _random
    import numpy as _np
    from multiprocessing import shared_memory as _shm

    if worker_seed is not None:
        _random.seed(worker_seed)
        _np.random.seed(worker_seed % (2**32))

    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..'))
    if env_version == 'v4':
        from alpha_holdem.environment import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}
    elif env_version == 'v55cap1':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack, 'raise_cap_per_street': 1}
    elif env_version == 'v55cap1v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'raise_cap_per_street': 1,
            'action_history_style': 'v4',
        }
    else:
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}

    M = int(envs_per_worker)
    obs_shm = _shm.SharedMemory(name=obs_shm_name)
    result_shm = _shm.SharedMemory(name=result_shm_name)
    status_shm = _shm.SharedMemory(name=status_shm_name)
    assigned_shm = _shm.SharedMemory(name=assigned_opp_shm_name)
    request_shm = _shm.SharedMemory(name=request_model_shm_name)

    base = worker_id * M
    obs_buf = _np.ndarray(
        (M, OBS_SIZE), dtype=_np.float32,
        buffer=obs_shm.buf[base * OBS_SIZE * 4:(base + M) * OBS_SIZE * 4],
    )
    result_buf = _np.ndarray(
        (M, RESULT_SIZE), dtype=_np.float32,
        buffer=result_shm.buf[base * RESULT_SIZE * 4:(base + M) * RESULT_SIZE * 4],
    )
    status_buf = _np.ndarray(
        (M,), dtype=_np.int32,
        buffer=status_shm.buf[base * 4:(base + M) * 4],
    )
    assigned_buf = _np.ndarray(
        (1,), dtype=_np.int32,
        buffer=assigned_shm.buf[worker_id * 4:(worker_id + 1) * 4],
    )
    request_buf = _np.ndarray(
        (M,), dtype=_np.int32,
        buffer=request_shm.buf[base * 4:(base + M) * 4],
    )

    class _Slot:
        __slots__ = ('env', 'obs', 'buffers', 'last_actor', 'hands_played',
                     'current_opp', 'pending', 'terminal_reward', 'mirror_deck',
                     'deal_index')

    slots = []
    for _e in range(M):
        s = _Slot()
        s.env = HUNLEnvironment(**env_kwargs)
        s.obs = None
        s.buffers = {0: [], 1: []}
        s.last_actor = None
        s.hands_played = 0
        s.current_opp = -1
        s.pending = None
        s.terminal_reward = 0.0
        s.mirror_deck = None
        s.deal_index = 0
        slots.append(s)

    local_transitions = []
    local_metrics = exp003_metrics_template()
    hands_since_send = 0

    def start_hand(e):
        s = slots[e]
        if s.mirror_deck is not None:
            s.current_opp = -1
            s.obs = exp003_reset_env_with_deck(s.env, s.mirror_deck)
            s.mirror_deck = None
            local_metrics['mirror_replay_hands'] += 1
        else:
            s.current_opp = int(assigned_buf[0])
            if fixed_training_deal_stream:
                s.obs = exp003_reset_env_with_deck(
                    s.env, fixed_training_deck(worker_seed, e, s.deal_index)
                )
                s.deal_index += 1
            else:
                s.obs = s.env.reset()
            if mirror_self_play_deals and s.current_opp == -1:
                mirror_deck = exp003_mirrored_deck_from_env(s.env)
                if mirror_deck is not None:
                    s.mirror_deck = mirror_deck
                    local_metrics['mirror_source_hands'] += 1
        s.buffers = {0: [], 1: []}
        s.last_actor = None

    def submit(e):
        """Write env e's observation + request. Status write is LAST (release)."""
        s = slots[e]
        o = s.obs
        player = o['player']
        hero_player = s.hands_played % 2
        is_self_play = (s.current_opp == -1)
        is_hero = (player == hero_player)
        req = HERO_MODEL_ID if (is_self_play or is_hero) else s.current_opp

        ci = o['card_info'].flatten()
        ai = o['action_info'].flatten()
        ei = o['extra_info']
        lm = o['legal_mask']

        row = obs_buf[e]
        row[:CARD_SIZE] = ci
        row[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
        row[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
        row[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

        collect = is_self_play or is_hero
        if collect:
            s.pending = (player, is_hero, collect,
                         ci.copy(), ai.copy(), ei.copy(), lm.copy())
        else:
            # Non-trainable decision: only lm is needed (epsilon fallback).
            s.pending = (player, is_hero, collect, None, None, None, lm.copy())
        request_buf[e] = req
        status_buf[e] = WAITING

    def finalize_hand(e):
        """Emit the completed hand as one contiguous block. Returns True."""
        nonlocal hands_since_send
        s = slots[e]
        env = s.env
        chips = {0: env.chips_committed(0), 1: env.chips_committed(1)}
        rewards_per_player = {}
        if s.last_actor is not None:
            rewards_per_player[s.last_actor] = s.terminal_reward
            rewards_per_player[1 - s.last_actor] = -s.terminal_reward

        counted_hand = False
        for p in (0, 1):
            buf = s.buffers[p]
            if not buf:
                continue
            pr = rewards_per_player.get(p, 0.0)
            p_chips = chips[p]
            v_chips = chips[1 - p]
            for i, (ci_s, ai_s, ei_s, lm_s, act, lp, val) in enumerate(buf):
                is_last = (i == len(buf) - 1)
                hand_marker = 1.0 if is_last and not counted_hand else 0.0
                if hand_marker:
                    counted_hand = True
                local_transitions.append((
                    ci_s, ai_s, ei_s, lm_s, act, lp,
                    pr if is_last else 0.0,
                    val,
                    1.0 if is_last else 0.0,
                    p_chips,
                    v_chips,
                    hand_marker,
                ))
        s.hands_played += 1
        hands_since_send += 1
        return True

    try:
        for e in range(M):
            start_hand(e)
            submit(e)

        while not stop_event.is_set():
            progressed = False
            for e in range(M):
                if status_buf[e] != READY:
                    continue
                progressed = True
                s = slots[e]
                action_idx = int(result_buf[e, 0])
                log_prob = float(result_buf[e, 1])
                value = float(result_buf[e, 2])
                status_buf[e] = IDLE

                (player, is_hero, collect, ci, ai, ei, lm) = s.pending
                s.pending = None

                eps = epsilon_value.value
                if is_hero and eps > 0.0 and _random.random() < eps:
                    legal = _np.where(lm > 0)[0]
                    if len(legal) > 0:
                        action_idx = int(_random.choice(legal))

                if collect:
                    s.buffers[player].append((ci, ai, ei, lm,
                                              action_idx, log_prob, value))
                s.last_actor = player
                pre_board = tuple(s.env.state.board) if allin_runout_ev and s.env.state is not None else None
                obs, reward, done = s.env.step(action_idx)

                if done:
                    if allin_runout_ev:
                        ev_result = exp003_allin_ev_reward(
                            s.env.state,
                            player,
                            pre_board,
                            allin_runout_ev_max_runouts,
                        )
                        if ev_result is not None:
                            ev_reward, runouts, skipped = ev_result
                            if skipped:
                                local_metrics['allin_ev_skipped_hands'] += 1
                                local_metrics['allin_ev_skipped_runouts'] += int(runouts)
                            else:
                                reward = ev_reward
                                local_metrics['allin_ev_replacements'] += 1
                                local_metrics['allin_ev_runouts'] += int(runouts)
                    s.terminal_reward = reward
                    finalize_hand(e)
                    if hands_since_send >= 50 and local_transitions:
                        try:
                            transition_pipe.send(local_transitions)
                            if exp003_metrics_nonzero(local_metrics):
                                transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
                                local_metrics = exp003_metrics_template()
                        except BrokenPipeError:
                            # Main is gone or pipe broken: exit THIS worker only
                            # (matches single-path behavior; do not stop the world).
                            return
                        local_transitions = []
                        hands_since_send = 0
                    start_hand(e)
                    submit(e)
                else:
                    s.obs = obs
                    submit(e)

            if not progressed:
                _time.sleep(0.000001)

        # Shutdown: flush only COMPLETED hands (incomplete hands discarded).
        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
                if exp003_metrics_nonzero(local_metrics):
                    transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
            except BrokenPipeError:
                pass
        try:
            transition_pipe.send(None)
        except BrokenPipeError:
            pass

    finally:
        obs_shm.close()
        result_shm.close()
        status_shm.close()
        assigned_shm.close()
        request_shm.close()


# ===========================================================
# Inference (V5.0): flat-view group-by request_model_id
# ===========================================================

@torch.no_grad()
def run_inference_v5(
    hero_model: AlphaHoldemNet,
    opp_models: list,
    obs_np, result_np, status_np, request_model_np,
    num_slots: int,           # EXP-002: W in single mode, W*M in multi mode
    device: str,
    batch_size_log: list,  # caller's list to push observed batch sizes for metrics
) -> int:
    """
    V5.0: build group masks via vectorized numpy ops, slice flat obs view directly.

    obs_np shape (num_slots*OBS_SIZE,), reshape to (num_slots, OBS_SIZE) view (no copy).
    """
    waiting_mask = (status_np == WAITING)
    if not waiting_mask.any():
        return 0

    obs_view = obs_np.reshape(num_slots, OBS_SIZE)
    waiting_idx = np.flatnonzero(waiting_mask)
    rm = request_model_np[waiting_idx]

    # Group: hero (-1) vs each opp idx
    total = 0
    unique_models = np.unique(rm)
    for mid in unique_models:
        sel = waiting_idx[rm == mid]
        if sel.size == 0:
            continue
        model = hero_model if int(mid) == HERO_MODEL_ID else opp_models[int(mid) % len(opp_models)]

        batch_np = obs_view[sel]                        # (B, OBS_SIZE), no copy
        # Split into card / action / extra / mask without re-allocating
        batch_t = torch.from_numpy(np.ascontiguousarray(batch_np)).to(device, non_blocking=True)
        cards_t = batch_t[:, :CARD_SIZE].view(-1, 6, 4, 13)
        actions_t = batch_t[:, CARD_SIZE:CARD_SIZE + ACTION_SIZE].view(-1, 25, 4, 5)
        extras_t = batch_t[:, CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE]
        masks_t = batch_t[:, CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:]

        logits, values = model(cards_t, actions_t, extras_t, masks_t)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)
        sampled = dist.sample()
        log_probs = dist.log_prob(sampled)

        s_np = sampled.cpu().numpy()
        lp_np = log_probs.cpu().numpy()
        v_np = values.squeeze(-1).cpu().numpy()

        for i, w in enumerate(sel):
            r_off = int(w) * RESULT_SIZE
            result_np[r_off] = s_np[i]
            result_np[r_off + 1] = lp_np[i]
            result_np[r_off + 2] = v_np[i]
            status_np[int(w)] = READY

        batch_size_log.append(int(sel.size))
        total += int(sel.size)

    return total


# ===========================================================
# Opponent pool
# ===========================================================

class OpponentPool:
    """Historical opponent pool with explicit selection policy.

    ``latest`` preserves the original FIFO behavior for ablations and old-run
    continuity. ``loss-kbest`` keeps the K snapshots with the lowest recorded
    Trinal-Clip selection loss, which is a cheap paper-inspired approximation of
    K-best survivor selection until a full ELO tournament is wired in.
    """

    def __init__(self, k=5, strategy='loss-kbest', history_limit=200):
        if strategy not in ('latest', 'loss-kbest'):
            raise ValueError(f'unknown pool strategy: {strategy}')
        self.k = int(k)
        self.strategy = strategy
        self.history_limit = int(history_limit)
        self.snapshots = []  # active list of {state_dict, id, hands, selection_*}
        self.candidate_history = []  # metadata only; no tensors
        self.next_id = 0

    @staticmethod
    def _clone_state(model_state):
        return {
            kk: vv.detach().cpu().clone() if hasattr(vv, 'detach') else vv.clone()
            for kk, vv in model_state.items()
        }

    @staticmethod
    def _finite_or_none(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _metadata(snap: dict) -> dict:
        return {
            'id': snap.get('id'),
            'hands': snap.get('hands'),
            'iteration': snap.get('iteration'),
            'pool_strategy': snap.get('pool_strategy'),
            'selection_loss': snap.get('selection_loss'),
            'selection_score': snap.get('selection_score'),
            'score_components': snap.get('score_components'),
        }

    def _prune(self):
        if self.k <= 0:
            self.snapshots = []
            return
        if len(self.snapshots) <= self.k:
            return
        if self.strategy == 'latest':
            self.snapshots.sort(key=lambda s: int(s.get('id', 0)))
            self.snapshots = self.snapshots[-self.k:]
            return

        def score_key(snap: dict):
            score = self._finite_or_none(snap.get('selection_score'))
            if score is None:
                score = float('-inf')
            return (
                score,
                int(snap.get('hands') or 0),
                int(snap.get('id') or 0),
            )

        self.snapshots.sort(key=score_key, reverse=True)
        self.snapshots = self.snapshots[:self.k]

    def _trim_history(self):
        if self.history_limit <= 0:
            self.candidate_history = []
        elif len(self.candidate_history) > self.history_limit:
            self.candidate_history = self.candidate_history[-self.history_limit:]

    def add(self, model_state, *, hands=0, iteration=None, selection_loss=None, score_components=None) -> dict:
        loss = self._finite_or_none(selection_loss)
        score = -loss if loss is not None else None
        snap = {
            'state_dict': self._clone_state(model_state),
            'id': self.next_id,
            'hands': int(hands or 0),
            'iteration': int(iteration) if iteration is not None else None,
            'pool_strategy': self.strategy,
            'selection_loss': loss,
            'selection_score': score,
            'score_components': score_components or {},
        }
        self.next_id += 1
        self.snapshots.append(snap)
        self._prune()

        active_ids = self.active_ids()
        meta = self._metadata(snap)
        meta['selected'] = snap['id'] in active_ids
        meta['active_ids_after'] = active_ids
        self.candidate_history.append(meta)
        self._trim_history()
        return snap

    def load_from_checkpoint(self, snapshots, candidate_history=None):
        self.snapshots = []
        self.next_id = 0
        for idx, snap in enumerate(snapshots or []):
            if not isinstance(snap, dict) or 'state_dict' not in snap:
                continue
            snap_id = snap.get('id', idx)
            selection_loss = self._finite_or_none(snap.get('selection_loss'))
            selection_score = self._finite_or_none(snap.get('selection_score'))
            if selection_score is None and selection_loss is not None:
                selection_score = -selection_loss
            item = {
                'state_dict': self._clone_state(snap['state_dict']),
                'id': int(snap_id),
                'hands': int(snap.get('hands') or 0),
                'iteration': snap.get('iteration'),
                'pool_strategy': snap.get('pool_strategy') or self.strategy,
                'selection_loss': selection_loss,
                'selection_score': selection_score,
                'score_components': snap.get('score_components') or {},
            }
            self.snapshots.append(item)
            self.next_id = max(self.next_id, int(snap_id) + 1)
        self._prune()

        if isinstance(candidate_history, list):
            self.candidate_history = [
                item for item in candidate_history if isinstance(item, dict)
            ][-self.history_limit:]
        else:
            self.candidate_history = [self._metadata(snap) for snap in self.snapshots]
        self._trim_history()

    def get_opponent(self, idx: int):
        if not self.snapshots:
            return None
        return self.snapshots[idx % len(self.snapshots)]['state_dict']

    def size(self):
        return len(self.snapshots)

    def active_ids(self):
        return [int(s.get('id')) for s in self.snapshots]

    def active_metadata(self):
        return [self._metadata(snap) for snap in self.snapshots]

    def description(self):
        if self.strategy == 'latest':
            return f'latest-K FIFO historical self-play snapshots (K={self.k})'
        return (
            f'loss-selected K-best historical self-play snapshots (K={self.k}); '
            'selection_score=-selection_loss proxy, not full ELO'
        )


# ===========================================================
# Main
# ===========================================================

def main():
    parser = argparse.ArgumentParser(
        description='AlphaHoldem V5 clean-from-zero self-play trainer',
    )
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=2_700_000_000,
                        help='V5 target hands. Default matches the AlphaHoldem paper scale.')
    parser.add_argument('--starting-stack', type=float, default=200.0)
    parser.add_argument('--env-version', choices=('v55', 'v4', 'v55cap1', 'v55cap1v4obs'), default='v55',
                        help='Training environment. v55 fixes the legacy V4/V5 action-history and raise-cap bugs.')
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.0)
    parser.add_argument('--gamma', type=float, default=0.999)
    parser.add_argument('--delta1', type=float, default=3.0)
    parser.add_argument('--entropy-coef', type=float, default=0.05)
    parser.add_argument('--entropy-floor', type=float, default=0.3)
    parser.add_argument('--postflop-action-prior-coef', type=float, default=0.0,
                        help='Optional experimental class-prior regularizer for postflop decisions. '
                             '0 disables it and preserves baseline Trinal-Clip PPO.')
    parser.add_argument('--postflop-action-prior-target', default='0.15,0.30,0.52,0.03',
                        help='Comma-separated fold,call/check,raise,all-in class target used when '
                             '--postflop-action-prior-coef > 0. Targets are renormalized over legal classes.')
    parser.add_argument('--preflop-action-prior-coef', type=float, default=0.0,
                        help='Optional experimental class-prior regularizer for preflop decisions. '
                             '0 disables it and preserves baseline Trinal-Clip PPO.')
    parser.add_argument('--preflop-action-prior-target', default='0.30,0.25,0.43,0.02',
                        help='Comma-separated fold,call/check,raise,all-in class target used when '
                             '--preflop-action-prior-coef > 0. Targets are renormalized over legal classes.')
    parser.add_argument('--preflop-sb-open-action-prior-coef', type=float, default=0.0,
                        help='Optional context-specific preflop prior for SB first action. '
                             'Use only after hand-log evidence shows SB open fold/limp/raise imbalance.')
    parser.add_argument('--preflop-sb-open-action-prior-target', default='0.15,0.20,0.63,0.02',
                        help='Comma-separated fold,call/check,raise,all-in class target for SB first action.')
    parser.add_argument('--preflop-bb-vs-open-action-prior-coef', type=float, default=0.0,
                        help='Optional context-specific preflop prior for BB facing one aggressive open. '
                             'Use only after hand-log evidence shows BB defend selector collapse.')
    parser.add_argument('--preflop-bb-vs-open-action-prior-target', default='0.25,0.55,0.18,0.02',
                        help='Comma-separated fold,call/check,raise,all-in class target for BB facing an open.')
    parser.add_argument('--k-best', type=int, default=5)
    parser.add_argument('--pool-strategy', choices=('latest', 'loss-kbest'), default='loss-kbest',
                        help='Historical opponent selection. loss-kbest keeps the K snapshots with '
                             'lowest Trinal-Clip selection loss; latest preserves FIFO recency for ablations.')
    parser.add_argument('--pool-history-limit', type=int, default=200,
                        help='Metadata-only candidate history entries to retain in checkpoints/manifests.')
    parser.add_argument('--self-play-fraction', type=float, default=0.2,
                        help='Probability of hero-vs-hero instead of a pool opponent.')
    parser.add_argument('--opponent-assignment', choices=('per-iteration', 'per-group', 'per-worker'),
                        default='per-iteration',
                        help='per-iteration keeps all workers on one sampled mode/snapshot for larger '
                             'inference batches; per-group is EXP-005 balanced group mixtures; '
                             'per-worker is the original independent sampler.')
    parser.add_argument('--opponent-groups', type=int, default=5,
                        help='EXP-005: balanced worker groups used by --opponent-assignment per-group.')
    parser.add_argument('--opponent-assignment-provenance-file', default='',
                        help='Reporting-only hash-chained JSONL of the actual worker opponent '
                             'assignment applied to every iteration. EXP005-C arms require it.')
    parser.add_argument('--rollout-mode', choices=('single', 'multi'), default='single',
                        help='EXP-002: single preserves the original one-env-per-worker path; '
                             'multi runs --rollout-envs-per-worker envs per worker with batched requests.')
    parser.add_argument('--rollout-envs-per-worker', type=int, default=1,
                        help='EXP-002: M environments per worker (multi mode). Must be 1 in single mode.')
    parser.add_argument('--inference-min-batch-slots', type=int, default=0,
                        help='EXP-002: wait until at least this many slots are pending before GPU '
                             'inference (0 disables the accumulation window).')
    parser.add_argument('--inference-batch-deadline-us', type=float, default=700.0,
                        help='EXP-002: serve whatever is pending once this many microseconds passed '
                             'since the last serve, even below --inference-min-batch-slots.')
    parser.add_argument('--worker-seed-base', type=int, default=None,
                        help='EXP-002: if set, worker i seeds random/numpy with base+i in BOTH rollout '
                             'modes. Required for the deterministic equivalence gate.')
    parser.add_argument('--fixed-training-deal-stream', action='store_true',
                        help='Controlled-arm mode: derive each source deck from '
                             '(worker_seed, env_index, deal_index). Requires worker seed base.')
    parser.add_argument('--trace-transitions-file', default=None,
                        help='EXP-002 debug: write one sha256 digest per transition in arrival order '
                             '(equivalence testing only; adds overhead).')
    parser.add_argument('--validate-stream', action='store_true',
                        help='EXP-002 debug: assert hand-block structure of every received pipe '
                        'message (GAE contiguity invariant). Use in smokes/validation only.')
    parser.add_argument('--mirror-self-play-deals', action='store_true',
                        help='EXP-003: in self-play only, replay each shuffled deal once with '
                             'P0/P1 hole cards swapped and the same future board order.')
    parser.add_argument('--allin-runout-ev', action='store_true',
                        help='EXP-003: replace all-in-before-river sampled runout payoff with '
                             'exact or bounded-K showdown EV in existing profit units.')
    parser.add_argument('--allin-runout-ev-max-runouts', type=int,
                        default=EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
                        help='EXP-003 bounded-K runouts per all-in EV replacement. If the '
                             'exact missing-board runout count exceeds K, sample K deterministic '
                             'runouts instead of skipping replacement. Set 0 only for explicit '
                             'exhaustive enumeration; default 200 is the live-cutover-safe mode.')
    parser.add_argument('--snapshot-every', type=int, default=200)
    parser.add_argument('--save-interval', type=int, default=100)
    parser.add_argument('--run-id', default=None,
                        help='Stable run id. Defaults to v5_zero_<UTC timestamp>.')
    parser.add_argument('--run-dir', default=None,
                        help='Artifact directory. Defaults to models/alpha_holdem_v5_from_zero/<run-id>.')
    parser.add_argument('--out', default=None,
                        help='Checkpoint path. Defaults to <run-dir>/latest.pt.')
    parser.add_argument('--overwrite', action='store_true',
                        help='Allow overwriting an existing output checkpoint.')
    parser.add_argument('--seed', type=int, default=20260703)
    parser.add_argument('--max-runtime-seconds', type=float, default=0.0,
                        help='Optional wall-clock guard for smoke/debug runs. 0 disables it.')
    parser.add_argument('--resume', default=None)
    parser.add_argument('--allow-resume', action='store_true',
                        help='Explicitly allow --resume. Default V5 contract is fresh random init.')
    parser.add_argument('--reset-optimizer', action='store_true', default=True)
    parser.add_argument('--no-reset-optimizer', dest='reset_optimizer', action='store_false')
    parser.add_argument('--reset-hand-counter', action='store_true', default=False,
                        help='Start total_hands at 0 even if resume ckpt has higher (for V5 fresh schedule)')
    args = parser.parse_args()
    try:
        args.postflop_action_prior_target_values = parse_action_prior_target(args.postflop_action_prior_target)
        args.preflop_action_prior_target_values = parse_action_prior_target(args.preflop_action_prior_target)
        args.preflop_sb_open_action_prior_target_values = parse_action_prior_target(
            args.preflop_sb_open_action_prior_target
        )
        args.preflop_bb_vs_open_action_prior_target_values = parse_action_prior_target(
            args.preflop_bb_vs_open_action_prior_target
        )
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    if args.resume and not args.allow_resume:
        raise SystemExit(
            'Refusing to resume: V5 is clean-from-zero by default. '
            'Pass --allow-resume only for an explicit ablation.'
        )

    if args.rollout_envs_per_worker < 1:
        parser.error('--rollout-envs-per-worker must be >= 1')
    if args.rollout_mode == 'single' and args.rollout_envs_per_worker != 1:
        parser.error('--rollout-mode single requires --rollout-envs-per-worker 1 '
                     '(use --rollout-mode multi for M > 1)')
    if args.allin_runout_ev_max_runouts < 0:
        parser.error('--allin-runout-ev-max-runouts must be >= 0')
    if args.inference_min_batch_slots > args.workers * args.rollout_envs_per_worker:
        parser.error(f'--inference-min-batch-slots ({args.inference_min_batch_slots}) '
                     f'exceeds total slots W*M='
                     f'{args.workers * args.rollout_envs_per_worker}; it could never be met '
                     f'and every serve would wait for the deadline.')
    if args.fixed_training_deal_stream and args.worker_seed_base is None:
        parser.error('--fixed-training-deal-stream requires --worker-seed-base')

    run_id = args.run_id or f"v5_zero_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = Path(args.run_dir or Path('models') / 'alpha_holdem_v5_from_zero' / run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    args.run_id = run_id
    args.run_dir = str(run_dir)
    if args.out is None:
        args.out = str(run_dir / 'latest.pt')
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.resume and not args.overwrite:
        raise SystemExit(f'Refusing to overwrite existing checkpoint: {out_path}. Pass --overwrite for smoke/debug.')

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    device = args.device
    W = args.workers
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    dc = torch.zeros(1, 6, 4, 13, device=device)
    da = torch.zeros(1, 25, 4, 5, device=device)
    de = torch.zeros(1, 2, device=device)
    model(dc, da, de)
    print(f'Parameters: {count_parameters(model):,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    pool = OpponentPool(k=args.k_best, strategy=args.pool_strategy, history_limit=args.pool_history_limit)

    goal_spec = {
        'project': 'AlphaHoldem V5 from zero',
        'reference': {
            'paper': 'Zhao et al., AlphaHoldem: High-Performance Artificial Intelligence for Heads-Up No-Limit Poker via End-to-End Reinforcement Learning, AAAI 2022',
            'aaai_url': 'https://ojs.aaai.org/index.php/AAAI/article/view/20394',
            'pdf_url': 'https://cdn.aaai.org/ojs/20394/20394-13-24407-1-2-20220628.pdf',
        },
        'primary_target': {
            'opponent': 'Slumbot',
            'stack_depth_bb': 200,
            'formal_gate': '100k+ hands, bb/100 > 0, 95% CI lower bound > 0',
            'l6_target': 'approximately +11.1 bb/100 vs Slumbot',
            'paper_claim_vs_slumbot_mbb_per_hand': 111.56,
            'paper_claim_vs_slumbot_bb_per_100': 11.156,
        },
        'method': {
            'family': 'end-to-end self-play reinforcement learning',
            'network': 'pseudo-Siamese card/action/extra branches with policy and value heads',
            'loss': 'Trinal-Clip PPO',
            'opponent_pool': pool.description(),
            'opponent_pool_deviation': (
                'loss-kbest is a single-GPU proxy for paper K-best/ELO survivor selection; '
                'validate with internal probes and Slumbot gates.'
                if args.pool_strategy == 'loss-kbest'
                else 'latest-K FIFO is an ablation/deviation from paper K-best/ELO survivor selection.'
            ),
            'action_space': '9 discrete actions: fold, check/call, six pot-fraction raises, all-in',
            'actual_hand_accounting': True,
            'environment_version': args.env_version,
            'postflop_action_prior': {
                'coef': args.postflop_action_prior_coef,
                'target_fold_call_raise_allin': args.postflop_action_prior_target_values,
                'scope': 'postflop trainable decisions only; targets renormalized over legal classes',
                'status': 'disabled' if args.postflop_action_prior_coef <= 0.0 else 'experimental_deviation',
            },
            'preflop_action_prior': {
                'coef': args.preflop_action_prior_coef,
                'target_fold_call_raise_allin': args.preflop_action_prior_target_values,
                'scope': 'preflop trainable decisions only; targets renormalized over legal classes',
                'status': 'disabled' if args.preflop_action_prior_coef <= 0.0 else 'experimental_deviation',
            },
            'preflop_context_action_priors': {
                'sb_open': {
                    'coef': args.preflop_sb_open_action_prior_coef,
                    'target_fold_call_raise_allin': args.preflop_sb_open_action_prior_target_values,
                    'scope': 'preflop rows with no prior street actions; targets renormalized over legal classes',
                    'status': (
                        'disabled'
                        if args.preflop_sb_open_action_prior_coef <= 0.0
                        else 'experimental_deviation_context_conditioned'
                    ),
                },
                'bb_vs_open': {
                    'coef': args.preflop_bb_vs_open_action_prior_coef,
                    'target_fold_call_raise_allin': args.preflop_bb_vs_open_action_prior_target_values,
                    'scope': (
                        'preflop rows with exactly one prior opponent aggressive action; '
                        'targets renormalized over legal classes'
                    ),
                    'status': (
                        'disabled'
                        if args.preflop_bb_vs_open_action_prior_coef <= 0.0
                        else 'experimental_deviation_context_conditioned'
                    ),
                },
                'interaction': (
                    'When a context prior is active, the global preflop prior is applied only '
                    'to other preflop rows so context targets do not double-count.'
                ),
            },
            'exp003_variance_reduction': {
                'mirrored_self_play_deals': bool(args.mirror_self_play_deals),
                'allin_runout_ev': bool(args.allin_runout_ev),
                'allin_runout_ev_max_runouts': int(args.allin_runout_ev_max_runouts),
                'status': (
                    'experimental_deviation'
                    if (args.mirror_self_play_deals or args.allin_runout_ev)
                    else 'disabled'
                ),
                'notes': (
                    'Mirrored deals duplicate self-play shuffled deals with seats swapped; '
                    'all-in EV replaces sampled runout payoff with exact EV when cheap, '
                    'otherwise deterministic bounded-K runout EV.'
                ),
            },
        },
    }

    obs_version = 'v4' if args.env_version in ('v4', 'v55cap1v4obs') else 'v55'
    resume_source = args.resume
    lineage_parent_checkpoint = args.resume
    fresh_from_zero_lineage = not bool(args.resume)
    lineage_root_run_id = args.run_id

    def checkpoint_payload() -> dict:
        return {
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict(),
            'total_hands': total_hands,
            'iteration': iteration,
            'pool_snapshots': pool.snapshots,
            'pool_strategy': pool.strategy,
            'pool_active_metadata': pool.active_metadata(),
            'pool_candidate_history': pool.candidate_history,
            'version': 'v5.zero',
            'run_id': args.run_id,
            'config': vars(args),
            'goal': goal_spec,
            'resume': resume_source,
            'fresh_from_zero_lineage': fresh_from_zero_lineage,
            'lineage_root_run_id': lineage_root_run_id,
            'lineage_parent_checkpoint': lineage_parent_checkpoint,
            'env_version': args.env_version,
            'obs_version': obs_version,
            'action_space_version': '9slot_v5',
            'starting_stack_bb': args.starting_stack,
            'actual_hand_accounting': True,
        }

    manifest_path = run_dir / 'run_manifest.json'

    def write_manifest(status: str, **extra):
        manifest = {
            'run_id': args.run_id,
            'process_id': os.getpid(),
            'status': status,
            'created_or_updated_at': datetime.now(timezone.utc).isoformat(),
            'fresh_from_zero': not bool(args.resume),
            'fresh_from_zero_lineage': fresh_from_zero_lineage,
            'lineage_root_run_id': lineage_root_run_id,
            'lineage_parent_checkpoint': lineage_parent_checkpoint,
            'config': vars(args),
            'goal': goal_spec,
            **extra,
        }
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    total_hands = 0
    iteration = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        fresh_from_zero_lineage = bool(ckpt.get(
            'fresh_from_zero_lineage',
            ckpt.get('version') == 'v5.zero' and ckpt.get('resume') is None,
        ))
        lineage_root_run_id = ckpt.get('lineage_root_run_id') or ckpt.get('run_id') or args.run_id
        lineage_parent_checkpoint = args.resume
        model.load_state_dict(ckpt['model'])
        if not args.reset_optimizer:
            optimizer.load_state_dict(ckpt['optimizer'])
            print('Loaded checkpoint optimizer state')
        else:
            print('V5.0: optimizer reset (fresh Adam moments)')

        if not args.reset_hand_counter:
            total_hands = ckpt.get('total_hands', 0)
            iteration = ckpt.get('iteration', 0)

        source_pool_strategy = (
            ckpt.get('pool_strategy')
            or (ckpt.get('config') or {}).get('pool_strategy')
            or 'latest'
        )
        if source_pool_strategy != pool.strategy:
            print(
                f'Pool strategy switch on resume: source={source_pool_strategy} '
                f'-> active={pool.strategy}'
            )

        # Convert older KBest/latest snapshots into the active V5 pool form.
        if 'pool_snapshots' in ckpt:
            pool.load_from_checkpoint(
                ckpt.get('pool_snapshots') or [],
                candidate_history=ckpt.get('pool_candidate_history'),
            )
        print(
            f'Resumed: {total_hands:,} hands, pool={pool.size()} '
            f'(strategy={pool.strategy}, active_ids={pool.active_ids()}, '
            f'fresh_from_zero_lineage={fresh_from_zero_lineage})'
        )

    if not args.resume:
        init_path = run_dir / 'init.pt'
        if args.overwrite or not init_path.exists():
            torch.save({
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'total_hands': 0,
                'iteration': 0,
                'pool_snapshots': [],
                'pool_strategy': pool.strategy,
                'pool_active_metadata': [],
                'pool_candidate_history': [],
                'version': 'v5.zero',
                'run_id': args.run_id,
                'config': vars(args),
                'goal': goal_spec,
                'resume': None,
                'fresh_from_zero_lineage': True,
                'lineage_root_run_id': args.run_id,
                'lineage_parent_checkpoint': None,
                'env_version': args.env_version,
                'obs_version': obs_version,
                'action_space_version': '9slot_v5',
                'starting_stack_bb': args.starting_stack,
                'actual_hand_accounting': True,
            }, init_path)
    elif not out_path.exists() or args.overwrite:
        torch.save(checkpoint_payload(), args.out)
        print(
            f'  [Save] initial resume checkpoint {args.out} '
            f'({total_hands:,} hands, iter={iteration})'
        )

    write_manifest('initialized', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))

    log_path = str(out_path.with_suffix('.log'))
    train_log_path = str(out_path.with_name(out_path.stem + '_train.log'))

    # EXP-002: request/obs/result/status shm are sized per SLOT (W*M); the
    # opponent assignment stays per WORKER (read once per hand, as before).
    M = args.rollout_envs_per_worker
    NUM_SLOTS = W * M

    # Allocate shared memory (split: assigned + request)
    obs_shm = shared_memory.SharedMemory(create=True, size=NUM_SLOTS * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=NUM_SLOTS * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=NUM_SLOTS * 4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=W * 4)   # V5.0 (per worker)
    request_shm = shared_memory.SharedMemory(create=True, size=NUM_SLOTS * 4)

    obs_np = np.ndarray((NUM_SLOTS * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((NUM_SLOTS * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((NUM_SLOTS,), dtype=np.int32, buffer=status_shm.buf)
    assigned_np = np.ndarray((W,), dtype=np.int32, buffer=assigned_shm.buf)
    request_np = np.ndarray((NUM_SLOTS,), dtype=np.int32, buffer=request_shm.buf)

    obs_np[:] = 0
    result_np[:] = 0
    status_np[:] = IDLE
    assigned_np[:] = -1
    request_np[:] = HERO_MODEL_ID

    epsilon_val = mp.Value('d', args.epsilon)
    stop_event = mp.Event()

    pipes = []
    procs = []
    for w in range(W):
        parent_conn, child_conn = mp.Pipe()
        pipes.append(parent_conn)
        w_seed = (args.worker_seed_base + w) if args.worker_seed_base is not None else None
        if args.rollout_mode == 'multi':
            p = mp.Process(
                target=worker_process_v5_multi,
                args=(w, M, obs_shm.name, result_shm.name, status_shm.name,
                      assigned_shm.name, request_shm.name,
                      child_conn, stop_event, epsilon_val, args.starting_stack,
                      args.env_version, w_seed,
                      args.mirror_self_play_deals, args.allin_runout_ev,
                      args.allin_runout_ev_max_runouts,
                      args.fixed_training_deal_stream),
                daemon=True,
            )
        else:
            p = mp.Process(
                target=worker_process_v5,
                args=(w, obs_shm.name, result_shm.name, status_shm.name,
                      assigned_shm.name, request_shm.name,
                      child_conn, stop_event, epsilon_val, args.starting_stack,
                      args.env_version, w_seed,
                      args.mirror_self_play_deals, args.allin_runout_ev,
                      args.allin_runout_ev_max_runouts,
                      args.fixed_training_deal_stream),
                daemon=True,
            )
        p.start()
        child_conn.close()
        procs.append(p)

    print(f'\nV5 clean-from-zero trainer: {W} workers @ {args.starting_stack} BB')
    print(f'EXP-002 rollout: mode={args.rollout_mode} M={M} slots={NUM_SLOTS} '
          f'min_batch_slots={args.inference_min_batch_slots} '
          f'deadline_us={args.inference_batch_deadline_us} '
          f'worker_seed_base={args.worker_seed_base}')
    print(f'Run id: {args.run_id}')
    print(f'Run dir: {run_dir}')
    print(f'Target: {args.total_hands:,} hands')
    print(f'Environment: {args.env_version} (obs={obs_version})')
    print(f'PPO: eps_clip=0.2, delta1={args.delta1}, gamma={args.gamma}')
    print(
        f'EXP-003 variance reduction: mirror_self_play_deals={args.mirror_self_play_deals} '
        f'allin_runout_ev={args.allin_runout_ev} '
        f'allin_runout_ev_max_runouts={args.allin_runout_ev_max_runouts}'
    )
    print(
        f'V5: fresh_from_zero={not bool(args.resume)}, epsilon={args.epsilon}, '
        f'both-player collect=ON, pool={pool.description()}'
    )
    assignment_detail = (
        f', groups={args.opponent_groups}' if args.opponent_assignment == 'per-group' else ''
    )
    print(
        f'Opponent assignment: {args.opponent_assignment}'
        f'{assignment_detail} (self_play_fraction={args.self_play_fraction})'
    )
    print('-' * 80)

    # Build opp_models from pool
    opp_models = []
    def rebuild_opp_models():
        opp_models.clear()
        for snap in pool.snapshots:
            m = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
            m(dc, da, de)
            m.load_state_dict(snap['state_dict'])
            m.eval()
            opp_models.append(m)
    rebuild_opp_models()

    reward_window = deque(maxlen=100)
    iter_transitions = []
    iter_reward = 0.0
    iter_hands = 0
    iter_terminal_trajectories = 0
    iter_start = time.time()
    inference_batch_sizes = []
    iter_exp003_metrics = exp003_metrics_template()

    # Cumulative metrics for cross-iter aggregation
    cum_decisions = 0
    cum_inferences = 0

    assignment_provenance_fh = None
    assignment_provenance_last_sha = None
    assignment_provenance_last_iteration = None
    if args.opponent_assignment_provenance_file:
        provenance_path = Path(args.opponent_assignment_provenance_file)
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        if provenance_path.exists() and provenance_path.stat().st_size > 0:
            last_line = next(
                (line for line in reversed(provenance_path.read_text(encoding='utf-8').splitlines()) if line.strip()),
                None,
            )
            if last_line is None:
                raise RuntimeError('assignment provenance file is non-empty but has no JSON record')
            last_record = json.loads(last_line)
            assignment_provenance_last_sha = last_record.get('record_sha256')
            assignment_provenance_last_iteration = int(last_record.get('applies_to_iteration'))
            if not assignment_provenance_last_sha:
                raise RuntimeError('assignment provenance tail has no record_sha256')
        assignment_provenance_fh = open(provenance_path, 'a', encoding='utf-8', buffering=1)

    def assign_opponents():
        """Assign hero-vs-hero or pool opponents. Main writes assigned_np; workers only read."""
        nonlocal assignment_provenance_last_sha, assignment_provenance_last_iteration
        group_metadata = None
        if pool.size() == 0:
            assigned_np[:] = -1
            group_metadata = [{
                'group_id': 0,
                'workers': list(range(W)),
                'opponent_id': HERO_MODEL_ID,
            }]
        elif args.opponent_assignment == 'per-iteration':
            # Preserve the long-run self-play/pool mix while keeping each rollout
            # iteration on one requested model so GPU inference remains batched.
            if random.random() < args.self_play_fraction:
                assigned_np[:] = -1
            else:
                assigned_np[:] = random.randint(0, pool.size() - 1)
            group_metadata = [{
                'group_id': 0,
                'workers': list(range(W)),
                'opponent_id': int(assigned_np[0]),
            }]
        elif args.opponent_assignment == 'per-group':
            assignments, group_summary = build_group_opponent_assignments(
                worker_count=W,
                pool_size=pool.size(),
                group_count=args.opponent_groups,
                self_play_fraction=args.self_play_fraction,
                rng=random,
            )
            assigned_np[:] = assignments
            group_metadata = group_summary['groups']
        else:
            for w in range(W):
                if random.random() < args.self_play_fraction:
                    assigned_np[w] = -1
                else:
                    assigned_np[w] = random.randint(0, pool.size() - 1)
            group_metadata = [
                {'group_id': int(w), 'workers': [int(w)], 'opponent_id': int(assigned_np[w])}
                for w in range(W)
            ]

        if assignment_provenance_fh is not None:
            applies_to_iteration = int(iteration) + 1
            if (
                assignment_provenance_last_iteration is not None
                and applies_to_iteration <= assignment_provenance_last_iteration
            ):
                raise RuntimeError(
                    f'assignment provenance iteration {applies_to_iteration} is not after '
                    f'tail {assignment_provenance_last_iteration}'
                )
            record = build_assignment_provenance_record(
                run_id=args.run_id,
                applies_to_iteration=applies_to_iteration,
                total_hands=total_hands,
                assignment_mode=args.opponent_assignment,
                assignments=assigned_np.tolist(),
                pool_snapshots=pool.snapshots,
                group_metadata=group_metadata,
                worker_seed_base=args.worker_seed_base,
                previous_record_sha256=assignment_provenance_last_sha,
            )
            assignment_provenance_fh.write(
                json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
            )
            assignment_provenance_fh.flush()
            os.fsync(assignment_provenance_fh.fileno())
            assignment_provenance_last_sha = record['record_sha256']
            assignment_provenance_last_iteration = applies_to_iteration

    assign_opponents()

    trace_fh = None
    if args.trace_transitions_file:
        Path(args.trace_transitions_file).parent.mkdir(parents=True, exist_ok=True)
        trace_fh = open(args.trace_transitions_file, 'w')

    try:
        model.eval()
        last_inference_t = 0.0
        last_serve_ts = time.time()
        min_slots = args.inference_min_batch_slots
        deadline_s = max(0.0, args.inference_batch_deadline_us) / 1e6
        global_start = time.time()
        while total_hands < args.total_hands:
            if args.max_runtime_seconds > 0 and (time.time() - global_start) >= args.max_runtime_seconds:
                print(f"Reached max runtime guard ({args.max_runtime_seconds:.1f}s); stopping cleanly.")
                break

            # EXP-002 accumulation window: let requests pile up so inference
            # batches actually form; the deadline guarantees stragglers are
            # served even when few slots are pending.
            serve = True
            if min_slots > 0:
                waiting_count = int((status_np == WAITING).sum())
                if waiting_count == 0:
                    serve = False
                elif waiting_count < min_slots and (time.time() - last_serve_ts) < deadline_s:
                    serve = False

            n_inf = 0
            if serve:
                t_inf = time.time()
                n_inf = run_inference_v5(
                    model, opp_models,
                    obs_np, result_np, status_np, request_np,
                    NUM_SLOTS, device, inference_batch_sizes,
                )
                cum_inferences += n_inf
                last_inference_t += time.time() - t_inf
                if n_inf > 0:
                    last_serve_ts = time.time()

            # Drain pipes
            for pipe in pipes:
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            continue
                        if isinstance(data, dict) and data.get('type') == 'exp003_metrics':
                            exp003_metrics_add(iter_exp003_metrics, data)
                            continue
                        if args.validate_stream:
                            validate_stream_message(data)
                        for t in data:
                            iter_transitions.append(t)
                            if trace_fh is not None:
                                marker = int(t[11]) if len(t) > 11 else 0
                                trace_fh.write(f'{transition_digest(t)} {marker}\n')
                            if t[8] > 0.5:
                                iter_reward += t[6]
                                iter_terminal_trajectories += 1
                            if len(t) > 11 and t[11] > 0.5:
                                iter_hands += 1
                            elif len(t) <= 11 and t[8] > 0.5:
                                # Backward-compatible fallback for older transition tuples.
                                iter_hands += 1
                except (BrokenPipeError, EOFError):
                    pass

            # PPO update when enough hands accumulated
            if iter_hands >= args.hands_per_iter and len(iter_transitions) > 0:
                iteration += 1
                collect_time = time.time() - iter_start

                progress = total_hands / args.total_hands
                # V5.0 default epsilon stays at 0 (no decay needed). Honor user override.
                if args.epsilon > 0.0:
                    eps_decay = max(0.0, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))
                    epsilon_val.value = eps_decay
                else:
                    eps_decay = 0.0

                # V5.0 LR schedule: linear decay over V5's own training span.
                # Start lr = args.lr (default 1e-4 ~= V4 end LR), decay to lr/3 in 2nd half.
                if progress >= 0.5:
                    decay_frac = (progress - 0.5) / 0.5
                    new_lr = args.lr * (1 - decay_frac * (1 - 1/3))
                    for pg in optimizer.param_groups:
                        pg['lr'] = new_lr

                t1 = time.time()
                mix = action_mix(iter_transitions)
                phase_mix = action_mix_by_phase(iter_transitions)
                stats = trinal_clip_ppo_update(
                    model, optimizer, iter_transitions, device,
                    epochs=args.ppo_epochs,
                    mini_batch_size=args.mini_batch_size,
                    delta1=args.delta1,
                    gamma=args.gamma,
                    entropy_coef=args.entropy_coef,
                    entropy_floor=args.entropy_floor,
                    action_prior_coef=args.postflop_action_prior_coef,
                    action_prior_target=args.postflop_action_prior_target_values,
                    action_prior_postflop_only=True,
                    preflop_action_prior_coef=args.preflop_action_prior_coef,
                    preflop_action_prior_target=args.preflop_action_prior_target_values,
                    preflop_sb_open_action_prior_coef=args.preflop_sb_open_action_prior_coef,
                    preflop_sb_open_action_prior_target=args.preflop_sb_open_action_prior_target_values,
                    preflop_bb_vs_open_action_prior_coef=args.preflop_bb_vs_open_action_prior_coef,
                    preflop_bb_vs_open_action_prior_target=args.preflop_bb_vs_open_action_prior_target_values,
                )
                ppo_time = time.time() - t1
                selection_loss = selection_loss_from_stats(stats)
                score_components = {
                    'policy_loss': float(stats['policy_loss']),
                    'value_loss': float(stats['value_loss']),
                    'entropy': float(stats['entropy']),
                    'action_prior_loss': float(stats.get('action_prior_loss', 0.0)),
                    'action_prior_coef': float(stats.get('action_prior_coef', 0.0)),
                    'postflop_action_prior_loss': float(stats.get('postflop_action_prior_loss', 0.0)),
                    'postflop_action_prior_coef': float(stats.get('postflop_action_prior_coef', 0.0)),
                    'preflop_action_prior_loss': float(stats.get('preflop_action_prior_loss', 0.0)),
                    'preflop_action_prior_coef': float(stats.get('preflop_action_prior_coef', 0.0)),
                    'preflop_sb_open_action_prior_loss': float(stats.get('preflop_sb_open_action_prior_loss', 0.0)),
                    'preflop_sb_open_action_prior_coef': float(stats.get('preflop_sb_open_action_prior_coef', 0.0)),
                    'preflop_bb_vs_open_action_prior_loss': float(stats.get('preflop_bb_vs_open_action_prior_loss', 0.0)),
                    'preflop_bb_vs_open_action_prior_coef': float(stats.get('preflop_bb_vs_open_action_prior_coef', 0.0)),
                    'formula': 'policy_loss + 0.5*log1p(value_loss)',
                }

                total_hands += iter_hands
                trainable_decisions = len(iter_transitions)
                cum_decisions += trainable_decisions

                avg_rew = iter_reward / max(iter_terminal_trajectories, 1)
                reward_window.append(avg_rew)
                rew100 = np.mean(reward_window)

                h_per_s = iter_hands / max(collect_time, 1e-6)
                tdec_per_s = trainable_decisions / max(collect_time, 1e-6)
                infer_bs_mean = (sum(inference_batch_sizes) / len(inference_batch_sizes)
                                 if inference_batch_sizes else 0.0)

                # V5.0 advantage_std (post-normalize is always 1.0; we want pre-norm)
                # trinal_clip_ppo_update doesn't surface this; placeholder for V5.1.
                adv_std_placeholder = 0.0
                action_prior_log = (
                    f"aprior={stats.get('action_prior_loss', 0.0):.4f} "
                    if (
                        args.postflop_action_prior_coef > 0.0
                        or args.preflop_action_prior_coef > 0.0
                        or args.preflop_sb_open_action_prior_coef > 0.0
                        or args.preflop_bb_vs_open_action_prior_coef > 0.0
                    )
                    else ""
                )
                exp003_log = (
                    f"mirror={iter_exp003_metrics['mirror_replay_hands']}/"
                    f"{iter_exp003_metrics['mirror_source_hands']} "
                    f"aiev={iter_exp003_metrics['allin_ev_replacements']}:"
                    f"{iter_exp003_metrics['allin_ev_runouts']} "
                    f"aiev_skip={iter_exp003_metrics['allin_ev_skipped_hands']}:"
                    f"{iter_exp003_metrics['allin_ev_skipped_runouts']} "
                    if (args.mirror_self_play_deals or args.allin_runout_ev)
                    else ""
                )

                log_line = (
                    f"[{iteration:5d}] "
                    f"hands={total_hands:,} "
                    f"rew={avg_rew:+.3f} "
                    f"rew100={rew100:+.3f} "
                    f"ploss={stats['policy_loss']:.4f} "
                    f"vloss={stats['value_loss']:.4f} "
                    f"ent={stats['entropy']:.4f} "
                    f"kl={stats.get('approx_kl', 0.0):.4f} "
                    f"clipfrac={stats.get('clip_frac', 0.0):.3f} "
                    f"d1bite={stats.get('delta1_bite_frac', 0.0):.3f} "
                    f"{action_prior_log}"
                    f"r50={stats.get('ratio_p50', 0.0):.2f}/"
                    f"r95={stats.get('ratio_p95', 0.0):.2f}/"
                    f"r99={stats.get('ratio_p99', 0.0):.2f}/"
                    f"rmax={stats.get('ratio_max', 0.0):.2f} "
                    f"eps={eps_decay:.3f} "
                    f"pool={pool.size()} "
                    f"{exp003_log}"
                    f"trans={trainable_decisions} "
                    f"terms={iter_terminal_trajectories} "
                    f"mix=F{mix['fold']:.3f}/C{mix['call']:.3f}/R{mix['raise']:.3f}/A{mix['allin']:.3f} "
                    f"pmix=F{phase_mix['preflop']['fold']:.3f}/C{phase_mix['preflop']['call']:.3f}/R{phase_mix['preflop']['raise']:.3f}/A{phase_mix['preflop']['allin']:.3f} "
                    f"xmix=F{phase_mix['postflop']['fold']:.3f}/C{phase_mix['postflop']['call']:.3f}/R{phase_mix['postflop']['raise']:.3f}/A{phase_mix['postflop']['allin']:.3f} "
                    f"h/s={h_per_s:.0f} "
                    f"tdec/s={tdec_per_s:.0f} "      # V5.0 NEW
                    f"inf_bs={infer_bs_mean:.1f} "    # V5.0 NEW
                    f"collect={collect_time:.1f}s "
                    f"ppo={ppo_time:.1f}s"
                )
                print(log_line)
                with open(train_log_path, 'a') as f:
                    f.write(log_line + '\n')
                write_manifest(
                    'running',
                    total_hands=total_hands,
                    iteration=iteration,
                    checkpoint=str(out_path),
                    latest_metrics={
                        'reward_per_hand': avg_rew,
                        'reward_window_100': rew100,
                        'policy_loss': stats['policy_loss'],
                        'value_loss': stats['value_loss'],
                        'entropy': stats['entropy'],
                        'action_prior_loss': stats.get('action_prior_loss', 0.0),
                        'action_prior_coef': stats.get('action_prior_coef', 0.0),
                        'postflop_action_prior_loss': stats.get('postflop_action_prior_loss', 0.0),
                        'postflop_action_prior_coef': stats.get('postflop_action_prior_coef', 0.0),
                        'preflop_action_prior_loss': stats.get('preflop_action_prior_loss', 0.0),
                        'preflop_action_prior_coef': stats.get('preflop_action_prior_coef', 0.0),
                        'preflop_sb_open_action_prior_loss': stats.get('preflop_sb_open_action_prior_loss', 0.0),
                        'preflop_sb_open_action_prior_coef': stats.get('preflop_sb_open_action_prior_coef', 0.0),
                        'preflop_bb_vs_open_action_prior_loss': stats.get('preflop_bb_vs_open_action_prior_loss', 0.0),
                        'preflop_bb_vs_open_action_prior_coef': stats.get('preflop_bb_vs_open_action_prior_coef', 0.0),
                        'approx_kl': stats.get('approx_kl', 0.0),
                        'clip_frac': stats.get('clip_frac', 0.0),
                        'delta1_bite_frac': stats.get('delta1_bite_frac', 0.0),
                        'ratio_p50': stats.get('ratio_p50', 0.0),
                        'ratio_p95': stats.get('ratio_p95', 0.0),
                        'ratio_p99': stats.get('ratio_p99', 0.0),
                        'ratio_max': stats.get('ratio_max', 0.0),
                        'hands_per_second': h_per_s,
                        'trainable_decisions_per_second': tdec_per_s,
                        'terminal_trajectories': iter_terminal_trajectories,
                        'action_mix': mix,
                        'action_mix_by_phase': phase_mix,
                        'exp003_metrics': dict(iter_exp003_metrics),
                        'pool_size': pool.size(),
                        'pool_strategy': pool.strategy,
                        'pool_active_ids': pool.active_ids(),
                        'pool_active_metadata': pool.active_metadata(),
                        'selection_loss': selection_loss,
                    },
                )

                # Snapshot
                if iteration % args.snapshot_every == 0:
                    snap = pool.add(
                        {k: v.cpu() for k, v in model.state_dict().items()},
                        hands=total_hands,
                        iteration=iteration,
                        selection_loss=selection_loss,
                        score_components=score_components,
                    )
                    rebuild_opp_models()
                    print(
                        f"  [Pool] +snapshot id={snap['id']} "
                        f"selected={snap['id'] in pool.active_ids()} "
                        f"size={pool.size()} strategy={pool.strategy} "
                        f"active_ids={pool.active_ids()}"
                    )

                # Save
                if iteration % args.save_interval == 0:
                    torch.save(checkpoint_payload(), args.out)
                    print(f'  [Save] {args.out} ({total_hands:,} hands)')

                # Reset for next iter. Do not emit provenance for an assignment
                # that will never be consumed after the fixed actual-hand budget.
                if total_hands < args.total_hands:
                    assign_opponents()
                iter_transitions = []
                iter_reward = 0.0
                iter_hands = 0
                iter_terminal_trajectories = 0
                inference_batch_sizes = []
                iter_exp003_metrics = exp003_metrics_template()
                iter_start = time.time()
                last_inference_t = 0.0
                model.eval()

            time.sleep(0.00001)

    except KeyboardInterrupt:
        print('\nInterrupted.')
    finally:
        if assignment_provenance_fh is not None:
            assignment_provenance_fh.flush()
            assignment_provenance_fh.close()
        if trace_fh is not None:
            trace_fh.flush()
            trace_fh.close()
        stop_event.set()
        time.sleep(1)
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
        for shm in (obs_shm, result_shm, status_shm, assigned_shm, request_shm):
            shm.close()
            shm.unlink()

    torch.save(checkpoint_payload(), args.out)
    write_manifest('finished', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))
    print(f'Done! {total_hands:,} hands. Saved to {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
