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
import copy
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

from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2, count_parameters
from alpha_holdem.environment import NUM_ACTIONS

# Reuse V4 PPO + GAE math (unchanged in V5.0; V5.2 introduces all-in EV / pot-norm value)
from alpha_holdem.train_mp3_hybrid_h1 import compute_gae, trinal_clip_ppo_update
from v5_hybrid_h1_critic import migrate_v1_checkpoint_to_v2
from v5_hybrid_h2_targets import H2_MAX_RUNOUTS, H2_TARGET_SEED, h2_showdown_critic_target_pairs
from v5_exp_w1_value_warmup import run_value_head_warmup, sha256_path, write_immutable_report

# ===========================================================
# Shared Memory Layout
# ===========================================================

CARD_SIZE = 6 * 4 * 13       # 312
ACTION_SIZE = 25 * 4 * 5     # 500
BASE_EXTRA_SIZE = 2
# Preserve the legacy two normalized-stack values and append the player's
# public HU seat: 0=BB/OOP, 1=SB/button/IP. Networks without a position
# adapter slice the first two values, so their policy output is unchanged.
EXTRA_SIZE = 3
MASK_SIZE = NUM_ACTIONS       # 9
OBS_SIZE = CARD_SIZE + ACTION_SIZE + EXTRA_SIZE + MASK_SIZE  # 824
RESULT_SIZE = 3  # action_idx, log_prob, value

IDLE = 0
WAITING = 1
READY = 2

HERO_MODEL_ID = -1  # request_model_id sentinel for "use hero model"


def pack_position_extra(
    legacy_extra: np.ndarray,
    *,
    player: int,
) -> np.ndarray:
    """Append the engine's fixed HU seat (P0=BB, P1=SB)."""
    base = np.asarray(legacy_extra, dtype=np.float32).reshape(-1)
    if base.shape != (BASE_EXTRA_SIZE,):
        raise ValueError(
            f'legacy extra_info must have shape ({BASE_EXTRA_SIZE},), '
            f'got {base.shape}'
        )
    if int(player) not in (0, 1):
        raise ValueError('player must be 0 or 1')
    return np.concatenate(
        (
            base,
            np.asarray([float(int(player))], dtype=np.float32),
        )
    )


def position_adapter_trainable_prefixes(
    training_seat: str,
) -> tuple[str, ...]:
    """Return the actor/value parameter prefixes for a seat-isolated update."""
    seat = str(training_seat).lower()
    if seat == 'all':
        actor_prefixes = ('position_policy_adapters.',)
    elif seat == 'bb':
        actor_prefixes = ('position_policy_adapters.0.',)
    elif seat == 'sb':
        actor_prefixes = ('position_policy_adapters.1.',)
    else:
        raise ValueError("training_seat must be one of: all, bb, sb")
    return actor_prefixes + (
        'value_head.',
        'position_value_adapters.',
    )


def linear_decay_group_lrs(progress: float, base_lrs) -> list[float]:
    """Preserve each optimizer group's LR ratio during the second-half decay."""
    if progress < 0.5:
        return [float(value) for value in base_lrs]
    decay_frac = min(1.0, max(0.0, (float(progress) - 0.5) / 0.5))
    factor = 1.0 - decay_frac * (1.0 - 1.0 / 3.0)
    return [float(value) * factor for value in base_lrs]


def heuristic_v4_preflop_action(env, player: int, legal_mask) -> int:
    """Return the deterministic v4 range action for an engine preflop state."""
    from alpha_holdem.heuristic_policy_v4 import choose_action
    from deep_cfr.game_state import ActionType

    state = env.state
    if state is None or int(state.street) != 0:
        raise ValueError('heuristic_v4_preflop_action requires a live preflop state')

    ranks = '23456789TJQKA'
    suits = 'cdhs'

    def card_string(card: int) -> str:
        return ranks[int(card) // 4] + suits[int(card) % 4]

    def action_code(action) -> str:
        if action.type == ActionType.FOLD:
            return 'f'
        if action.type == ActionType.CHECK:
            return 'k'
        if action.type == ActionType.CALL:
            return 'c'
        return 'b'

    street_actions = [
        [
            (action_code(action), int(who), float(action.amount))
            for who, action in actions
        ]
        for actions in state.get_actions_by_street()
    ]
    committed = state.street_committed
    payload = {
        'st': 0,
        'to_call': max(float(committed[1 - player] - committed[player]), 0.0),
        'street_actions': street_actions,
        'total_last_bet_to': max(float(committed[0]), float(committed[1])),
    }
    hole_cards = [card_string(card) for card in state.hole_cards[player]]
    return int(choose_action(
        hole_cards,
        [],
        payload,
        int(player),
        legal_mask,
    ))


def pokerskill_preflop_action(env, player: int, legal_mask) -> int:
    """Deterministic 200bb HU preflop teacher on the corrected size grid."""
    from alpha_holdem.heuristic_policy_v3 import _hand_notation
    from alpha_holdem.heuristic_policy_v4 import PREFLOP_PERCENTILE
    from deep_cfr.game_state import ActionType

    state = env.state
    if state is None or int(state.street) != 0:
        raise ValueError('pokerskill_preflop_action requires live preflop')

    ranks = '23456789TJQKA'
    suits = 'cdhs'

    def card_string(card: int) -> str:
        return ranks[int(card) // 4] + suits[int(card) % 4]

    def action_code(action) -> str:
        if action.type == ActionType.FOLD:
            return 'f'
        if action.type == ActionType.CHECK:
            return 'k'
        if action.type == ActionType.CALL:
            return 'c'
        return 'b'

    def pick(*slots: int) -> int:
        for slot in slots:
            if (
                0 <= int(slot) < len(legal_mask)
                and bool(legal_mask[int(slot)] > 0)
            ):
                return int(slot)
        legal = np.flatnonzero(np.asarray(legal_mask) > 0)
        return int(legal[0]) if len(legal) else 0

    hole_cards = [
        card_string(card)
        for card in state.hole_cards[int(player)]
    ]
    percentile = float(
        PREFLOP_PERCENTILE[_hand_notation(hole_cards)]
    )
    actions = [
        (action_code(action), int(who))
        for who, action in state.get_actions_by_street()[0]
    ]
    action_count = len(actions)
    hero_is_sb = int(player) == 1

    if hero_is_sb and action_count == 0:
        if percentile < 0.65:
            return pick(5, 6, 7, 1)
        if percentile < 0.935:
            return pick(1, 0)
        return pick(0, 1)

    if not hero_is_sb and action_count == 1:
        if actions[0][0] == 'c':
            return pick(7, 6, 5, 1) if percentile < 0.32 else pick(1, 0)
        if actions[0][0] == 'b':
            if percentile < 0.19:
                return pick(7, 6, 5, 1, 0)
            if percentile < 0.72:
                return pick(1, 0)
            return pick(0, 1)

    if hero_is_sb and action_count == 2:
        if percentile < 0.08:
            return pick(7, 6, 1, 0)
        if percentile < 0.45:
            return pick(1, 0)
        return pick(0, 1)

    if percentile < 0.06:
        return pick(7, 6, 1, 0)
    if percentile < 0.25:
        return pick(1, 0)
    return pick(0, 1)


LG002_RECOVERY_TOKEN = '2320b32682e51ba0e3781407b92d3d75'
LG002_RECOVERY_PREREG_SHA256 = 'ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9'
LG002_RECOVERY_ASSIGNMENT_SEED = 2026072203
LG002_RECOVERY_SOURCE_SHA256 = '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13'
LG002_RECOVERY_CHECKPOINT_ORDER = (109, 115, 120, 129, 103)
LG002_RECOVERY_MEMBER_STATE_SHA256 = {
    103: 'cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1',
    109: 'aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953',
    115: 'ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1',
    120: '86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e',
    129: '9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255',
}
LG002_RECOVERY_CONDITIONAL_WEIGHTS = {
    'control_uniform': {103: 0.2, 109: 0.2, 115: 0.2, 120: 0.2, 129: 0.2},
    'treatment_diversity': {
        103: 0.151331630996897,
        109: 0.272679451627751,
        115: 0.062503368673781,
        120: 0.325118010944971,
        129: 0.1883675377566,
    },
}


def lg002_state_dict_sha256(state_dict) -> str:
    """Canonical tensor-state identity used by the frozen LG002 registration."""
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        ).encode('utf-8')
        digest.update(len(metadata).to_bytes(8, 'big'))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes(order='C'))
    return digest.hexdigest()


def lg002_assignment_u64(absolute_iteration: int,
                          token: str = LG002_RECOVERY_TOKEN,
                          seed: int = LG002_RECOVERY_ASSIGNMENT_SEED) -> int:
    payload = f'LG002R_ASSIGNMENT_V1|{token}|{int(seed)}|{int(absolute_iteration)}'
    return int.from_bytes(hashlib.sha256(payload.encode('utf-8')).digest()[:8], 'big')


def lg002_select_from_u64(arm: str, u64: int, pool_snapshots):
    """Pure frozen selector; consumes no module or process RNG state."""
    if arm not in LG002_RECOVERY_CONDITIONAL_WEIGHTS:
        raise ValueError(f'unknown LG002 recovery arm: {arm}')
    if not 0 <= int(u64) < (1 << 64):
        raise ValueError('LG002 assignment u64 outside uint64 range')
    ids = [int(snapshot.get('id')) for snapshot in pool_snapshots]
    if tuple(ids) != LG002_RECOVERY_CHECKPOINT_ORDER or len(set(ids)) != len(ids):
        raise ValueError(f'LG002 frozen pool identity/order mismatch: {ids}')

    unit = int(u64) / float(1 << 64)
    weights = LG002_RECOVERY_CONDITIONAL_WEIGHTS[arm]
    selected_member_id = None
    local_index = HERO_MODEL_ID
    conditional_unit = None
    if unit >= 0.2:
        conditional_unit = (unit - 0.2) / 0.8
        cumulative = 0.0
        for member_id in sorted(weights):
            cumulative += weights[member_id]
            if conditional_unit < cumulative:
                selected_member_id = member_id
                break
        if selected_member_id is None:
            # Float round-off at the mathematical upper endpoint maps to the last bin.
            selected_member_id = max(weights)
        local_index = ids.index(selected_member_id)

    return local_index, {
        'assignment_rule': 'LG002R_ASSIGNMENT_V1',
        'assignment_seed': LG002_RECOVERY_ASSIGNMENT_SEED,
        'u64': int(u64),
        'unit_interval': unit,
        'conditional_unit_interval': conditional_unit,
        'arm': arm,
        'self_probability': 0.2,
        'conditional_weights_by_member_id': {str(k): v for k, v in sorted(weights.items())},
        'selected_kind': 'self_play' if local_index == HERO_MODEL_ID else 'pool_snapshot',
        'selected_local_index': int(local_index),
        'selected_member_id': selected_member_id,
        'selected_member_state_sha256': (
            None if selected_member_id is None
            else LG002_RECOVERY_MEMBER_STATE_SHA256[selected_member_id]
        ),
    }


def lg002_select_opponent(arm: str, absolute_iteration: int, pool_snapshots):
    return lg002_select_from_u64(
        arm, lg002_assignment_u64(absolute_iteration), pool_snapshots,
    )


def lg002_enrich_provenance_record(record: dict, assignment: dict) -> dict:
    enriched = dict(record)
    enriched.pop('record_sha256', None)
    enriched['schema_version'] = 'v5.lg002.recovery.opponent_assignment_provenance.v1'
    enriched['lg002_recovery'] = {
        'registration_sha256': LG002_RECOVERY_PREREG_SHA256,
        'registration_token': LG002_RECOVERY_TOKEN,
        **assignment,
    }
    canonical = json.dumps(
        enriched, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    )
    enriched['record_sha256'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return enriched


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
    if len(t) > 12:
        h.update(struct.pack('<d', float(t[12])))
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
        'h2_showdown_hands': 0,
        'h2_critic_target_rows': 0,
        'h2_critic_target_unique_boards': 0,
        'h2_critic_target_runouts': 0,
        'h2_critic_target_exact_rows': 0,
        'h2_critic_target_sampled_rows': 0,
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
    showdown_ev_value_targets=False,
    showdown_ev_value_target_max_runouts=H2_MAX_RUNOUTS,
    showdown_ev_value_target_seed=H2_TARGET_SEED,
    hero_preflop_strategy='model',
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
    elif env_version == 'v55v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
        }
    elif env_version == 'v55pfv2v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
            'raise_action_mapping': 'pot_fraction_v2',
        }
    elif env_version == 'v55preflopv2v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
            'raise_action_mapping': 'preflop_pot_fraction_v2',
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
    pending_mirror_identity = None
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
                deal_identity = pending_mirror_identity
                pending_mirror_identity = None
                local_metrics['mirror_replay_hands'] += 1
            else:
                current_opp_id = int(assigned_buf[0])
                if fixed_training_deal_stream:
                    deal_index = source_deal_index
                    obs = exp003_reset_env_with_deck(
                        env, fixed_training_deck(worker_seed, 0, deal_index)
                    )
                    source_deal_index += 1
                    deal_identity = f'w{worker_id}:e0:d{deal_index}'
                else:
                    obs = env.reset()
                    deal_identity = f'w{worker_id}:e0:runtime{hands_played}'
                if mirror_self_play_deals and current_opp_id == -1:
                    mirror_deck = exp003_mirrored_deck_from_env(env)
                    if mirror_deck is not None:
                        pending_mirror_deck = mirror_deck
                        pending_mirror_identity = f'{deal_identity}:mirror'
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
                ei = pack_position_extra(
                    obs['extra_info'],
                    player=player,
                )
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
                if (
                    is_hero
                    and hero_preflop_strategy in (
                        'heuristic-v4',
                        'pokerskill-v1',
                    )
                    and env.state is not None
                    and int(env.state.street) == 0
                ):
                    action_idx = (
                        pokerskill_preflop_action(env, player, lm)
                        if hero_preflop_strategy == 'pokerskill-v1'
                        else heuristic_v4_preflop_action(env, player, lm)
                    )

                # V5.0: collect for both players when self-play, else only hero
                acted_by_trainable_model = is_self_play or is_hero
                if acted_by_trainable_model:
                    row_board = (
                        tuple(env.state.board)
                        if showdown_ev_value_targets and env.state is not None
                        else None
                    )
                    hand_buffers[player].append((
                        ci.copy(), ai.copy(), ei.copy(), lm.copy(),
                        action_idx, log_prob, value, row_board,
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
            h2_hand_has_target = False
            committed = (chips[0], chips[1])
            h2_target_cache = (
                h2_showdown_critic_target_pairs(
                    env.state,
                    row_boards=[row[7] or () for buf in hand_buffers.values() for row in buf],
                    deal_identity=deal_identity,
                    committed=committed,
                    max_runouts=showdown_ev_value_target_max_runouts,
                    target_seed=showdown_ev_value_target_seed,
                )
                if showdown_ev_value_targets else {}
            )
            h2_counted_boards = set()
            for p in (0, 1):
                buf = hand_buffers[p]
                if not buf:
                    continue
                pr = rewards_per_player.get(p, 0.0)
                p_chips = chips[p]
                v_chips = chips[1 - p]
                for i, row in enumerate(buf):
                    ci_s, ai_s, ei_s, lm_s, act, lp, val = row[:7]
                    row_board = row[7] if len(row) > 7 else None
                    is_last = (i == len(buf) - 1)
                    hand_marker = 1.0 if is_last and not counted_hand else 0.0
                    if hand_marker:
                        counted_hand = True
                    transition = (
                        ci_s, ai_s, ei_s, lm_s, act, lp,
                        pr if is_last else 0.0,
                        val,
                        1.0 if is_last else 0.0,
                        p_chips,
                        v_chips,
                        hand_marker,
                    )
                    if showdown_ev_value_targets:
                        board_key = tuple(row_board or ())
                        target = h2_target_cache[board_key]
                        target_bb = float('nan') if target is None else float(target['target_bb'][p])
                        transition = transition + (target_bb,)
                        if target is not None:
                            h2_hand_has_target = True
                            local_metrics['h2_critic_target_rows'] += 1
                            if board_key not in h2_counted_boards:
                                h2_counted_boards.add(board_key)
                                local_metrics['h2_critic_target_unique_boards'] += 1
                                local_metrics['h2_critic_target_runouts'] += int(target['runouts'])
                                if target['exhaustive']:
                                    local_metrics['h2_critic_target_exact_rows'] += 1
                                else:
                                    local_metrics['h2_critic_target_sampled_rows'] += 1
                    else:
                        transition = transition + (float('nan'),)
                    # Player 0 is BB/OOP and player 1 is BTN/SB/IP in the
                    # native HUNL engine. Keep this as training metadata only;
                    # it does not change the deployed observation contract.
                    transition = transition + (float(p),)
                    local_transitions.append(transition)

            if h2_hand_has_target:
                local_metrics['h2_showdown_hands'] += 1

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
    showdown_ev_value_targets=False,
    showdown_ev_value_target_max_runouts=H2_MAX_RUNOUTS,
    showdown_ev_value_target_seed=H2_TARGET_SEED,
    hero_preflop_strategy='model',
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
    elif env_version == 'v55v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
        }
    elif env_version == 'v55pfv2v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
            'raise_action_mapping': 'pot_fraction_v2',
        }
    elif env_version == 'v55preflopv2v4obs':
        from alpha_holdem.environment_v55 import HUNLEnvironment
        env_kwargs = {
            'starting_stack': starting_stack,
            'action_history_style': 'v4',
            'raise_action_mapping': 'preflop_pot_fraction_v2',
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
                     'mirror_identity', 'deal_identity', 'deal_index')

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
        s.mirror_identity = None
        s.deal_identity = None
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
            s.deal_identity = s.mirror_identity
            s.mirror_identity = None
            local_metrics['mirror_replay_hands'] += 1
        else:
            s.current_opp = int(assigned_buf[0])
            if fixed_training_deal_stream:
                deal_index = s.deal_index
                s.obs = exp003_reset_env_with_deck(
                    s.env, fixed_training_deck(worker_seed, e, deal_index)
                )
                s.deal_index += 1
                s.deal_identity = f'w{worker_id}:e{e}:d{deal_index}'
            else:
                s.obs = s.env.reset()
                s.deal_identity = f'w{worker_id}:e{e}:runtime{s.hands_played}'
            if mirror_self_play_deals and s.current_opp == -1:
                mirror_deck = exp003_mirrored_deck_from_env(s.env)
                if mirror_deck is not None:
                    s.mirror_deck = mirror_deck
                    s.mirror_identity = f'{s.deal_identity}:mirror'
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
        ei = pack_position_extra(
            o['extra_info'],
            player=player,
        )
        lm = o['legal_mask']

        row = obs_buf[e]
        row[:CARD_SIZE] = ci
        row[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
        row[CARD_SIZE + ACTION_SIZE:CARD_SIZE + ACTION_SIZE + EXTRA_SIZE] = ei
        row[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

        collect = is_self_play or is_hero
        if collect:
            row_board = (
                tuple(s.env.state.board)
                if showdown_ev_value_targets and s.env.state is not None
                else None
            )
            s.pending = (player, is_hero, collect,
                         ci.copy(), ai.copy(), ei.copy(), lm.copy(), row_board)
        else:
            # Non-trainable decision: only lm is needed (epsilon fallback).
            s.pending = (player, is_hero, collect, None, None, None, lm.copy(), None)
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
        h2_hand_has_target = False
        committed = (chips[0], chips[1])
        h2_target_cache = (
            h2_showdown_critic_target_pairs(
                env.state,
                row_boards=[row[7] or () for buf in s.buffers.values() for row in buf],
                deal_identity=s.deal_identity,
                committed=committed,
                max_runouts=showdown_ev_value_target_max_runouts,
                target_seed=showdown_ev_value_target_seed,
            )
            if showdown_ev_value_targets else {}
        )
        h2_counted_boards = set()
        for p in (0, 1):
            buf = s.buffers[p]
            if not buf:
                continue
            pr = rewards_per_player.get(p, 0.0)
            p_chips = chips[p]
            v_chips = chips[1 - p]
            for i, row in enumerate(buf):
                ci_s, ai_s, ei_s, lm_s, act, lp, val = row[:7]
                row_board = row[7] if len(row) > 7 else None
                is_last = (i == len(buf) - 1)
                hand_marker = 1.0 if is_last and not counted_hand else 0.0
                if hand_marker:
                    counted_hand = True
                transition = (
                    ci_s, ai_s, ei_s, lm_s, act, lp,
                    pr if is_last else 0.0,
                    val,
                    1.0 if is_last else 0.0,
                    p_chips,
                    v_chips,
                    hand_marker,
                )
                if showdown_ev_value_targets:
                    board_key = tuple(row_board or ())
                    target = h2_target_cache[board_key]
                    target_bb = float('nan') if target is None else float(target['target_bb'][p])
                    transition = transition + (target_bb,)
                    if target is not None:
                        h2_hand_has_target = True
                        local_metrics['h2_critic_target_rows'] += 1
                        if board_key not in h2_counted_boards:
                            h2_counted_boards.add(board_key)
                            local_metrics['h2_critic_target_unique_boards'] += 1
                            local_metrics['h2_critic_target_runouts'] += int(target['runouts'])
                            if target['exhaustive']:
                                local_metrics['h2_critic_target_exact_rows'] += 1
                            else:
                                local_metrics['h2_critic_target_sampled_rows'] += 1
                else:
                    transition = transition + (float('nan'),)
                # Player 0 is BB/OOP and player 1 is BTN/SB/IP.
                transition = transition + (float(p),)
                local_transitions.append(transition)
        if h2_hand_has_target:
            local_metrics['h2_showdown_hands'] += 1
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

                (player, is_hero, collect, ci, ai, ei, lm, row_board) = s.pending
                s.pending = None

                eps = epsilon_value.value
                if is_hero and eps > 0.0 and _random.random() < eps:
                    legal = _np.where(lm > 0)[0]
                    if len(legal) > 0:
                        action_idx = int(_random.choice(legal))
                if (
                    is_hero
                    and hero_preflop_strategy in (
                        'heuristic-v4',
                        'pokerskill-v1',
                    )
                    and s.env.state is not None
                    and int(s.env.state.street) == 0
                ):
                    action_idx = (
                        pokerskill_preflop_action(s.env, player, lm)
                        if hero_preflop_strategy == 'pokerskill-v1'
                        else heuristic_v4_preflop_action(
                            s.env,
                            player,
                            lm,
                        )
                    )

                if collect:
                    s.buffers[player].append((ci, ai, ei, lm,
                                              action_idx, log_prob, value, row_board))
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
    hero_value_output_scale: float = 1.0,
    hero_policy_mode: str = 'sample',
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
        sampled = (
            torch.argmax(probs, dim=-1)
            if int(mid) == HERO_MODEL_ID and hero_policy_mode == 'greedy'
            else dist.sample()
        )
        log_probs = dist.log_prob(sampled)

        s_np = sampled.cpu().numpy()
        lp_np = log_probs.cpu().numpy()
        v_np = values.squeeze(-1).cpu().numpy()
        if int(mid) == HERO_MODEL_ID and hero_value_output_scale != 1.0:
            v_np = v_np * float(hero_value_output_scale)

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
    parser.add_argument('--env-version', choices=('v55', 'v4', 'v55cap1', 'v55cap1v4obs', 'v55v4obs', 'v55pfv2v4obs', 'v55preflopv2v4obs'), default='v55',
                        help='Training environment. v55 fixes the legacy V4/V5 action-history and raise-cap bugs.')
    parser.add_argument('--norm-layer', choices=('bn', 'gn'), default='bn',
                        help='Network normalization. Use gn for GN BC/imitation checkpoints.')
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--ppo-target-kl', type=float, default=0.0,
                        help='H6: after each completed PPO epoch, skip remaining epochs when '
                             'that epoch mean approx_kl is strictly greater than this value. '
                             '0 disables early-stop and preserves baseline behavior.')
    parser.add_argument('--source-policy-kl-coef', type=float, default=0.0,
                        help='Discovery mode: forward-KL regularization toward the exact '
                             'resume policy on rollout states. Requires --resume.')
    parser.add_argument(
        '--policy-postflop-only',
        action='store_true',
        help=(
            'Apply PPO policy and entropy gradients only to postflop rows. '
            'Source-policy KL covers both postflop seats; dedicated/frozen '
            'preflop parameters preserve preflop behavior.'
        ),
    )
    parser.add_argument(
        '--policy-position-only',
        choices=('all', 'bb', 'sb'),
        default='all',
        help=(
            'Optional postflop PPO seat filter. bb selects player 0 (OOP), '
            'sb selects player 1 (BTN/IP). Requires --policy-postflop-only; '
            'source-policy KL continues to anchor both postflop seats.'
        ),
    )
    parser.add_argument(
        '--head-only-training',
        action='store_true',
        help=(
            'Freeze the shared card/action/extra trunk and any dedicated '
            'preflop head; update only the postflop policy head and value '
            'head. This prevents postflop PPO from changing preflop logits '
            'through shared features.'
        ),
    )
    parser.add_argument(
        '--postflop-adapter-hidden',
        type=int,
        default=0,
        help='Add a zero-initialized residual postflop policy adapter of this width.',
    )
    parser.add_argument(
        '--position-adapter-hidden',
        type=int,
        default=0,
        help=(
            'Add two zero-initialized residual policy experts of this width, '
            'selected by the public HU seat feature (0=BB, 1=SB).'
        ),
    )
    parser.add_argument(
        '--position-value-adapter-hidden',
        type=int,
        default=0,
        help=(
            'Add two zero-initialized residual value experts of this width, '
            'selected by the public HU seat feature. This tests whether a '
            'shared critic aliases BB/OOP and SB/IP credit assignment.'
        ),
    )
    parser.add_argument(
        '--adapter-only-training',
        action='store_true',
        help=(
            'Freeze the source representation and policy heads; update only the '
            'postflop residual adapter and value head.'
        ),
    )
    parser.add_argument(
        '--position-adapter-only-training',
        action='store_true',
        help=(
            'Freeze the source actor; update only the two position residual '
            'experts and value head.'
        ),
    )
    parser.add_argument(
        '--position-adapter-training-seat',
        choices=('all', 'bb', 'sb'),
        default='all',
        help=(
            'When position-adapter-only training is enabled, update both '
            'seat experts (all) or isolate actor updates to BB/SB. The value '
            'head remains trainable in every mode.'
        ),
    )
    parser.add_argument(
        '--hero-preflop-strategy',
        choices=('model', 'heuristic-v4', 'pokerskill-v1'),
        default='model',
        help=(
            'Rollout policy for designated-hero preflop decisions. '
            'heuristic-v4 supplies position- and hand-dependent ranges; combine '
            'it with --policy-postflop-only and --preflop-teacher-coef > 0.'
        ),
    )
    parser.add_argument(
        '--preflop-teacher-coef',
        type=float,
        default=0.0,
        help=(
            'Cross-entropy coefficient on preflop rollout actions, used to '
            'distill a deterministic hero preflop teacher into the model.'
        ),
    )
    parser.add_argument(
        '--separate-preflop-head',
        action='store_true',
        help=(
            'Use a dedicated preflop policy head on detached trunk features. '
            'This lets the preflop teacher change greedy preflop play without '
            'rewriting the source postflop policy or its shared features.'
        ),
    )
    parser.add_argument(
        '--preflop-head-lr',
        type=float,
        default=0.0,
        help=(
            'Optional learning rate for the dedicated preflop head. '
            '0 uses --lr. Requires --separate-preflop-head when positive.'
        ),
    )
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.0)
    parser.add_argument('--gamma', type=float, default=0.999)
    parser.add_argument(
        '--gae-lambda',
        type=float,
        default=0.95,
        help=(
            'GAE lambda. Use 1.0 for Monte-Carlo actor advantages when adapting '
            'a policy whose inherited critic is untrained or stale.'
        ),
    )
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
    parser.add_argument('--fixed-opponent-checkpoint', default='',
                        help='Discovery mode: replace the historical pool with one frozen opponent '
                             'checkpoint. May be mixed with hero self-play through '
                             '--self-play-fraction.')
    parser.add_argument('--fixed-opponent-checkpoints', nargs='+', default=[],
                        help='Discovery mode: frozen opponent ensemble. May be combined with '
                             '--fixed-opponent-checkpoint and hero self-play.')
    parser.add_argument('--hero-policy-mode', choices=('sample', 'greedy'), default='sample',
                        help='Hero action selection during rollout. Training normally samples; '
                             'greedy with lr=0 provides a fast local fixed-opponent screen.')
    parser.add_argument('--archive-checkpoint-every', type=int, default=0,
                        help='Also save checkpoint_iterXXXXXX.pt every N PPO updates. '
                             '0 disables archival checkpoints.')
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
    parser.add_argument('--showdown-ev-value-targets', action='store_true',
                        help='H2: replace only eligible critic returns with deterministic '
                             'all-showdown K-runout line-value targets. Actor rewards and '
                             'advantages remain unchanged.')
    parser.add_argument('--showdown-ev-value-target-max-runouts', type=int, default=H2_MAX_RUNOUTS)
    parser.add_argument('--showdown-ev-value-target-seed', type=int, default=H2_TARGET_SEED)
    parser.add_argument('--h2-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h2-preregistration', default='')
    parser.add_argument('--h2-preregistration-sha256', default='')
    parser.add_argument('--h2-design-lock', default='')
    parser.add_argument('--h2-design-lock-sha256', default='')
    parser.add_argument('--h6-window-arm', choices=('none', 'treatment'), default='none')
    parser.add_argument('--h6-preregistration', default='')
    parser.add_argument('--h6-preregistration-sha256', default='')
    parser.add_argument('--h6-design-lock', default='')
    parser.add_argument('--h6-design-lock-sha256', default='')
    parser.add_argument('--h7-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h7-preregistration', default='')
    parser.add_argument('--h7-preregistration-sha256', default='')
    parser.add_argument('--h7-design-lock', default='')
    parser.add_argument('--h7-design-lock-sha256', default='')
    parser.add_argument('--h8-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h8-value-head-catchup-after-kl-stop', action='store_true')
    parser.add_argument('--h8-preregistration', default='')
    parser.add_argument('--h8-preregistration-sha256', default='')
    parser.add_argument('--h8-design-lock', default='')
    parser.add_argument('--h8-design-lock-sha256', default='')
    parser.add_argument('--h9-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h9-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h9-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h9-preregistration', default='')
    parser.add_argument('--h9-preregistration-sha256', default='')
    parser.add_argument('--h9-design-lock', default='')
    parser.add_argument('--h9-design-lock-sha256', default='')
    parser.add_argument('--h10-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h10-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h10-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h10-preregistration', default='')
    parser.add_argument('--h10-preregistration-sha256', default='')
    parser.add_argument('--h10-design-lock', default='')
    parser.add_argument('--h10-design-lock-sha256', default='')
    parser.add_argument('--h11-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h11-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h11-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h11-preregistration', default='')
    parser.add_argument('--h11-preregistration-sha256', default='')
    parser.add_argument('--h11-design-lock', default='')
    parser.add_argument('--h11-design-lock-sha256', default='')
    parser.add_argument('--h12-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h12-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h12-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h12-preregistration', default='')
    parser.add_argument('--h12-preregistration-sha256', default='')
    parser.add_argument('--h12-design-lock', default='')
    parser.add_argument('--h12-design-lock-sha256', default='')
    parser.add_argument('--h13-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h13-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h13-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h13-preregistration', default='')
    parser.add_argument('--h13-preregistration-sha256', default='')
    parser.add_argument('--h13-design-lock', default='')
    parser.add_argument('--h13-design-lock-sha256', default='')
    parser.add_argument('--h14-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h14-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h14-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h14-preregistration', default='')
    parser.add_argument('--h14-preregistration-sha256', default='')
    parser.add_argument('--h14-design-lock', default='')
    parser.add_argument('--h14-design-lock-sha256', default='')
    parser.add_argument('--h15-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h15-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h15-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h15-preregistration', default='')
    parser.add_argument('--h15-preregistration-sha256', default='')
    parser.add_argument('--h15-design-lock', default='')
    parser.add_argument('--h15-design-lock-sha256', default='')
    parser.add_argument('--h16-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h16-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h16-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h16-preregistration', default='')
    parser.add_argument('--h16-preregistration-sha256', default='')
    parser.add_argument('--h16-design-lock', default='')
    parser.add_argument('--h16-design-lock-sha256', default='')
    parser.add_argument('--h17-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h17-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h17-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h17-preregistration', default='')
    parser.add_argument('--h17-preregistration-sha256', default='')
    parser.add_argument('--h17-design-lock', default='')
    parser.add_argument('--h17-design-lock-sha256', default='')
    parser.add_argument('--h18-window-arm', choices=('none', 'control', 'treatment'), default='none')
    parser.add_argument('--h18-catchup-loss', choices=('mse', 'smooth_l1'), default='mse')
    parser.add_argument('--h18-catchup-smooth-l1-beta', type=float, default=1.0)
    parser.add_argument('--h18-preregistration', default='')
    parser.add_argument('--h18-preregistration-sha256', default='')
    parser.add_argument('--h18-design-lock', default='')
    parser.add_argument('--h18-design-lock-sha256', default='')
    parser.add_argument(
        '--lg002-recovery-arm',
        choices=('none', 'control_uniform', 'treatment_diversity'),
        default='none',
    )
    parser.add_argument('--lg002-recovery-preregistration', default='')
    parser.add_argument('--lg002-recovery-preregistration-sha256', default='')
    parser.add_argument('--lg002-recovery-contract-probe', action='store_true')
    parser.add_argument('--exp-w1-value-warmup-epochs', type=int, default=0,
                        help='EXP-W1 single variable: extra value-head-only epochs on the first '
                             'normal rollout batch. 0 is the exact control arm.')
    parser.add_argument('--exp-w1-value-warmup-at-iteration', type=int, default=0)
    parser.add_argument('--exp-w1-value-warmup-heldout-fraction', type=float, default=0.20)
    parser.add_argument('--exp-w1-value-warmup-min-relative-mse-reduction', type=float, default=0.02)
    parser.add_argument('--exp-w1-value-warmup-split-seed', type=int, default=2026071101)
    parser.add_argument('--exp-w1-value-warmup-report', default='',
                        help='Immutable treatment gate artifact. Required when warmup is enabled.')
    parser.add_argument('--exp-w1-design-lock', default='')
    parser.add_argument('--exp-w1-design-lock-sha256', default='')
    parser.add_argument('--critic-contract', choices=(CRITIC_V1, CRITIC_V2), default=CRITIC_V1)
    parser.add_argument('--h1-effective-stack-divisor', type=float, default=200.0)
    parser.add_argument('--h1-critic-init-seed', type=int, default=2026071102)
    parser.add_argument('--value-coef', type=float, default=0.5)
    parser.add_argument(
        '--autonomous-critic-v2-reset',
        action='store_true',
        help=(
            'Discovery-mode critic_v1 to critic_v2 migration: copy the actor '
            'exactly, initialize a fresh normalized critic_v2, and require a '
            'fresh optimizer. This bypasses legacy preregistration artifacts.'
        ),
    )
    parser.add_argument(
        '--autonomous-critic-v2-continue',
        action='store_true',
        help=(
            'Discovery-mode continuation from an existing critic_v2 checkpoint. '
            'Load actor and critic weights exactly while allowing either a fresh '
            'or preserved optimizer without legacy H1 governance artifacts.'
        ),
    )
    parser.add_argument(
        '--critic-head-only-gradient',
        action='store_true',
        help=(
            'Train the value head while blocking critic-loss gradients from '
            'the shared policy trunk. Actor losses still update the full '
            'trainable policy network.'
        ),
    )
    parser.add_argument('--h1-preregistration', default='')
    parser.add_argument('--h1-preregistration-sha256', default='')
    parser.add_argument('--h1-migration-report', default='')
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
    fixed_opponent_paths = [
        path for path in (
            ([args.fixed_opponent_checkpoint] if args.fixed_opponent_checkpoint else [])
            + list(args.fixed_opponent_checkpoints)
        )
        if path
    ]
    fixed_opponent_active = bool(fixed_opponent_paths)
    lg002_recovery_active = args.lg002_recovery_arm != 'none'
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
    if not 0.0 <= args.self_play_fraction <= 1.0:
        parser.error('--self-play-fraction must be in [0, 1]')
    if args.rollout_mode == 'single' and args.rollout_envs_per_worker != 1:
        parser.error('--rollout-mode single requires --rollout-envs-per-worker 1 '
                     '(use --rollout-mode multi for M > 1)')
    if args.allin_runout_ev_max_runouts < 0:
        parser.error('--allin-runout-ev-max-runouts must be >= 0')
    if args.showdown_ev_value_target_max_runouts <= 0:
        parser.error('--showdown-ev-value-target-max-runouts must be > 0')
    if args.showdown_ev_value_targets:
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H2 showdown targets require exact fixed deal stream and worker-seed-base 73000')
        if args.showdown_ev_value_target_max_runouts != H2_MAX_RUNOUTS:
            parser.error(f'H2 showdown targets require exact max runouts {H2_MAX_RUNOUTS}')
        if args.showdown_ev_value_target_seed != H2_TARGET_SEED:
            parser.error(f'H2 showdown targets require exact target seed {H2_TARGET_SEED}')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5:
            parser.error('H2 showdown targets require critic_v1 and value_coef 0.5')
        if args.opponent_assignment != 'per-iteration':
            parser.error('H2 showdown targets require per-iteration opponent assignment')
        if not args.opponent_assignment_provenance_file:
            parser.error('H2 showdown targets require assignment provenance')
    if args.h2_window_arm != 'none':
        expected_enabled = args.h2_window_arm == 'treatment'
        if bool(args.showdown_ev_value_targets) != expected_enabled:
            parser.error('H2 arm identity and showdown-target flag disagree')
        for label, path_value, hash_value in (
            ('preregistration', args.h2_preregistration, args.h2_preregistration_sha256),
            ('design lock', args.h2_design_lock, args.h2_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H2 {args.h2_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H2 immutable {label} identity/hash mismatch')
        if not args.resume or not args.allow_resume or not args.reset_optimizer:
            parser.error('H2 arms require --resume --allow-resume with optimizer reset')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H2 arms require fixed deal stream and worker-seed-base 73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H2 arms require per-iteration assignment provenance')
    if args.ppo_target_kl < 0.0:
        parser.error('--ppo-target-kl must be >= 0')
    if args.source_policy_kl_coef < 0.0:
        parser.error('--source-policy-kl-coef must be >= 0')
    if args.source_policy_kl_coef > 0.0 and not args.resume:
        parser.error('positive --source-policy-kl-coef requires --resume')
    if args.policy_position_only != 'all' and not args.policy_postflop_only:
        parser.error(
            '--policy-position-only bb/sb requires --policy-postflop-only'
        )
    if args.preflop_teacher_coef < 0.0:
        parser.error('--preflop-teacher-coef must be >= 0')
    if args.preflop_head_lr < 0.0:
        parser.error('--preflop-head-lr must be >= 0')
    if args.preflop_head_lr > 0.0 and not args.separate_preflop_head:
        parser.error('positive --preflop-head-lr requires --separate-preflop-head')
    if args.postflop_adapter_hidden < 0:
        parser.error('--postflop-adapter-hidden must be >= 0')
    if args.position_adapter_hidden < 0:
        parser.error('--position-adapter-hidden must be >= 0')
    if args.position_value_adapter_hidden < 0:
        parser.error('--position-value-adapter-hidden must be >= 0')
    if args.adapter_only_training and args.postflop_adapter_hidden <= 0:
        parser.error('--adapter-only-training requires --postflop-adapter-hidden > 0')
    if (
        args.position_adapter_only_training
        and args.position_adapter_hidden <= 0
    ):
        parser.error(
            '--position-adapter-only-training requires '
            '--position-adapter-hidden > 0'
        )
    if (
        args.position_adapter_training_seat != 'all'
        and not args.position_adapter_only_training
    ):
        parser.error(
            '--position-adapter-training-seat bb/sb requires '
            '--position-adapter-only-training'
        )
    exclusive_training_modes = sum(
        bool(value)
        for value in (
            args.adapter_only_training,
            args.position_adapter_only_training,
            args.head_only_training,
        )
    )
    if exclusive_training_modes > 1:
        parser.error(
            '--adapter-only-training, --position-adapter-only-training and '
            '--head-only-training are mutually exclusive'
        )
    if args.hero_preflop_strategy != 'model':
        if not args.policy_postflop_only:
            parser.error(
                '--hero-preflop-strategy teacher requires '
                '--policy-postflop-only'
            )
        if args.preflop_teacher_coef <= 0.0:
            parser.error(
                '--hero-preflop-strategy teacher requires '
                '--preflop-teacher-coef > 0'
            )
        if args.self_play_fraction > 0.0:
            parser.error(
                '--hero-preflop-strategy teacher requires '
                '--self-play-fraction 0 so all trainable preflop rows carry '
                'teacher actions'
            )
    if args.archive_checkpoint_every < 0:
        parser.error('--archive-checkpoint-every must be >= 0')
    # Discovery training may use ordinary PPO KL early stopping without a
    # historical H6-H14 governance identity.  The arm-specific branches below
    # still enforce their exact legacy contracts when explicitly selected.
    if args.h6_window_arm == 'treatment':
        if args.ppo_target_kl != 0.03:
            parser.error('H6 treatment requires exact --ppo-target-kl 0.03')
        if args.h2_window_arm != 'none' or args.showdown_ev_value_targets:
            parser.error('H6 must not bundle or reopen H2')
        for label, path_value, hash_value in (
            ('preregistration', args.h6_preregistration, args.h6_preregistration_sha256),
            ('design lock', args.h6_design_lock, args.h6_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H6 treatment requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H6 immutable {label} identity/hash mismatch')
        if not args.resume or not args.allow_resume or not args.reset_optimizer:
            parser.error('H6 treatment requires --resume --allow-resume with optimizer reset')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H6 treatment requires fixed deal stream and worker-seed-base 73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H6 treatment requires per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5:
            parser.error('H6 treatment requires critic_v1 and value_coef 0.5')
        if args.h7_window_arm != 'none' or args.h8_window_arm != 'none' or args.h9_window_arm != 'none' or args.h10_window_arm != 'none':
            parser.error('H6/H7/H8/H9/H10 identities are mutually exclusive')
    if args.h7_window_arm != 'none':
        expected_target = 0.03 if args.h7_window_arm == 'treatment' else 0.0
        if args.ppo_target_kl != expected_target:
            parser.error(f'H7 {args.h7_window_arm} requires exact --ppo-target-kl {expected_target}')
        if (
            args.h2_window_arm != 'none'
            or args.h6_window_arm != 'none'
            or args.h8_window_arm != 'none'
            or args.h9_window_arm != 'none'
            or args.h10_window_arm != 'none'
            or args.showdown_ev_value_targets
        ):
            parser.error('H7 must not bundle or reopen H2/H6/H8/H9/H10')
        for label, path_value, hash_value in (
            ('preregistration', args.h7_preregistration, args.h7_preregistration_sha256),
            ('design lock', args.h7_design_lock, args.h7_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H7 {args.h7_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H7 immutable {label} identity/hash mismatch')
        if not args.resume or not args.allow_resume or not args.reset_optimizer:
            parser.error('H7 arms require --resume --allow-resume with optimizer reset')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H7 arms require fixed deal stream and worker-seed-base 73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H7 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5:
            parser.error('H7 arms require critic_v1 and value_coef 0.5')
    if (
        args.h8_window_arm == 'none'
        and args.h9_window_arm == 'none'
        and args.h10_window_arm == 'none'
        and args.h11_window_arm == 'none'
        and args.h12_window_arm == 'none'
        and args.h13_window_arm == 'none'
        and args.h14_window_arm == 'none'
        and args.h15_window_arm == 'none'
        and args.h16_window_arm == 'none'
        and args.h17_window_arm == 'none'
        and args.h18_window_arm == 'none'
        and not lg002_recovery_active
        and args.h8_value_head_catchup_after_kl_stop
    ):
        parser.error('value-head catch-up flag requires a registered H8/H9/H10/H11/H12/H13/H14/H15/H16/H17/H18 arm')
    if args.h8_window_arm != 'none':
        if args.ppo_target_kl != 0.03:
            parser.error('H8 arms require exact --ppo-target-kl 0.03')
        expected_catchup = args.h8_window_arm == 'treatment'
        if bool(args.h8_value_head_catchup_after_kl_stop) != expected_catchup:
            parser.error(
                f'H8 {args.h8_window_arm} value-head catch-up identity mismatch'
            )
        if (
            args.h2_window_arm != 'none'
            or args.h6_window_arm != 'none'
            or args.h7_window_arm != 'none'
            or args.h9_window_arm != 'none'
            or args.h10_window_arm != 'none'
            or args.showdown_ev_value_targets
        ):
            parser.error('H8 must not bundle or reopen H2/H6/H7/H9/H10/showdown targets')
        for label, path_value, hash_value in (
            ('preregistration', args.h8_preregistration, args.h8_preregistration_sha256),
            ('design lock', args.h8_design_lock, args.h8_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H8 {args.h8_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H8 immutable {label} identity/hash mismatch')
        try:
            h8_prereg = json.loads(Path(args.h8_preregistration).read_text(encoding='utf-8-sig'))
            h8_arm = h8_prereg['arms'][args.h8_window_arm]
            h8_source = h8_prereg['source']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H8 preregistration content invalid: {exc}')
        if h8_prereg.get('experiment_id') != 'H8' or h8_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H8 preregistration authority mismatch')
        if args.run_id != h8_arm.get('run_id') or args.total_hands != int(h8_arm.get('target_endpoint_hands', -1)):
            parser.error('H8 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H8 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        if (
            resume_path != Path(h8_source.get('path', '')).resolve()
            or sha256_path(resume_path) != h8_source.get('sha256', '').lower()
        ):
            parser.error('H8 exact source checkpoint identity/hash mismatch')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H8 arms require fixed deal stream and worker-seed-base 73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H8 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5:
            parser.error('H8 arms require critic_v1 and value_coef 0.5')
        if args.ppo_epochs != 4:
            parser.error('H8 arms require exactly four maximum PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H8 arms require the frozen EXP-003 retained configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H8 arms require frozen 0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H8 arms must preserve the source hand counter')
    if args.h9_window_arm == 'none':
        if args.h9_catchup_loss != 'mse' or args.h9_catchup_smooth_l1_beta != 1.0:
            parser.error('H9 catch-up loss options require a registered H9 arm')
    else:
        if args.h8_window_arm != 'none' or args.h7_window_arm != 'none' or args.h6_window_arm != 'none' or args.h2_window_arm != 'none' or args.h10_window_arm != 'none':
            parser.error('H9 must not bundle or reopen H2/H6/H7/H8/H10')
        if args.showdown_ev_value_targets:
            parser.error('H9 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H9 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h9_window_arm == 'control' else 'smooth_l1'
        if args.h9_catchup_loss != expected_loss or args.h9_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H9 {args.h9_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h9_preregistration, args.h9_preregistration_sha256),
            ('design lock', args.h9_design_lock, args.h9_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H9 {args.h9_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H9 immutable {label} identity/hash mismatch')
        try:
            h9_prereg = json.loads(Path(args.h9_preregistration).read_text(encoding='utf-8-sig'))
            h9_source = h9_prereg['source']
            h9_arms = h9_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H9 preregistration content invalid: {exc}')
        if h9_prereg.get('experiment_id') != 'H9' or h9_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H9 preregistration authority mismatch')
        run_key = 'control_run_id' if args.h9_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h9_arms.get(run_key) or args.total_hands != int(h9_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H9 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H9 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        if (
            resume_path != Path(h9_source.get('checkpoint_path', '')).resolve()
            or sha256_path(resume_path) != h9_source.get('checkpoint_sha256', '').lower()
        ):
            parser.error('H9 exact source checkpoint identity/hash mismatch')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H9 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H9 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H9 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H9 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H9 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H9 arms must preserve the source hand counter')
    if args.h10_window_arm == 'none':
        if args.h10_catchup_loss != 'mse' or args.h10_catchup_smooth_l1_beta != 1.0:
            parser.error('H10 catch-up loss options require a registered H10 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h11_window_arm,
            args.h12_window_arm,
        )):
            parser.error('H10 must not bundle or reopen H2/H6/H7/H8/H9/H11/H12')
        if args.showdown_ev_value_targets:
            parser.error('H10 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H10 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h10_window_arm == 'control' else 'smooth_l1'
        if args.h10_catchup_loss != expected_loss or args.h10_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H10 {args.h10_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h10_preregistration, args.h10_preregistration_sha256),
            ('design lock', args.h10_design_lock, args.h10_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H10 {args.h10_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H10 immutable {label} identity/hash mismatch')
        try:
            h10_prereg = json.loads(Path(args.h10_preregistration).read_text(encoding='utf-8-sig'))
            h10_lock = json.loads(Path(args.h10_design_lock).read_text(encoding='utf-8-sig'))
            h10_source = h10_prereg['source']
            h10_arms = h10_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H10 immutable registration content invalid: {exc}')
        if h10_prereg.get('experiment_id') != 'H10' or h10_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H10 preregistration authority mismatch')
        if h10_lock.get('design_id') != 'H10' or h10_lock.get('status') != 'LOCKED':
            parser.error('H10 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h10_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h10_arms.get(run_key) or args.total_hands != int(h10_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H10 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H10 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h10_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h10_source.get('checkpoint_sha256', '').lower():
            parser.error('H10 exact canonical source checkpoint identity/hash mismatch')
        forbidden_paths = {
            Path(item.get('path', '')).resolve()
            for item in h10_prereg.get('forbidden_sources', [])
            if item.get('path')
        }
        if resume_path in forbidden_paths:
            parser.error('H10 forbidden H9/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H10 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H10 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H10 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H10 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H10 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H10 arms must preserve the source hand counter')
    if args.h11_window_arm == 'none':
        if args.h11_catchup_loss != 'mse' or args.h11_catchup_smooth_l1_beta != 1.0:
            parser.error('H11 catch-up loss options require a registered H11 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h12_window_arm,
        )):
            parser.error('H11 must not bundle or reopen H2/H6/H7/H8/H9/H10/H12')
        if args.showdown_ev_value_targets:
            parser.error('H11 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H11 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h11_window_arm == 'control' else 'smooth_l1'
        if args.h11_catchup_loss != expected_loss or args.h11_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H11 {args.h11_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h11_preregistration, args.h11_preregistration_sha256),
            ('design lock', args.h11_design_lock, args.h11_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H11 {args.h11_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H11 immutable {label} identity/hash mismatch')
        try:
            h11_prereg = json.loads(Path(args.h11_preregistration).read_text(encoding='utf-8-sig'))
            h11_lock = json.loads(Path(args.h11_design_lock).read_text(encoding='utf-8-sig'))
            h11_source = h11_prereg['source']
            h11_arms = h11_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H11 immutable registration content invalid: {exc}')
        if h11_prereg.get('experiment_id') != 'H11' or h11_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H11 preregistration authority mismatch')
        if h11_lock.get('design_id') != 'H11' or h11_lock.get('status') != 'LOCKED':
            parser.error('H11 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h11_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h11_arms.get(run_key) or args.total_hands != int(h11_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H11 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H11 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h11_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h11_source.get('checkpoint_sha256', '').lower():
            parser.error('H11 exact canonical source checkpoint identity/hash mismatch')
        forbidden_paths = {
            Path(item.get('path', '')).resolve()
            for item in h11_prereg.get('forbidden_sources', [])
            if item.get('path')
        }
        if resume_path in forbidden_paths:
            parser.error('H11 forbidden H9/H10/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H11 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H11 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H11 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H11 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H11 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H11 arms must preserve the source hand counter')
    if args.h12_window_arm == 'none':
        if args.h12_catchup_loss != 'mse' or args.h12_catchup_smooth_l1_beta != 1.0:
            parser.error('H12 catch-up loss options require a registered H12 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm,
        )):
            parser.error('H12 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11')
        if args.showdown_ev_value_targets:
            parser.error('H12 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H12 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h12_window_arm == 'control' else 'smooth_l1'
        if args.h12_catchup_loss != expected_loss or args.h12_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H12 {args.h12_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h12_preregistration, args.h12_preregistration_sha256),
            ('design lock', args.h12_design_lock, args.h12_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H12 {args.h12_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H12 immutable {label} identity/hash mismatch')
        try:
            h12_prereg = json.loads(Path(args.h12_preregistration).read_text(encoding='utf-8-sig'))
            h12_lock = json.loads(Path(args.h12_design_lock).read_text(encoding='utf-8-sig'))
            h12_source = h12_prereg['source']
            h12_arms = h12_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H12 immutable registration content invalid: {exc}')
        if h12_prereg.get('experiment_id') != 'H12' or h12_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H12 preregistration authority mismatch')
        if h12_lock.get('design_id') != 'H12' or h12_lock.get('status') != 'LOCKED':
            parser.error('H12 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h12_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h12_arms.get(run_key) or args.total_hands != int(h12_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H12 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H12 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h12_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h12_source.get('checkpoint_sha256', '').lower():
            parser.error('H12 exact canonical source checkpoint identity/hash mismatch')
        forbidden_paths = {
            Path(item.get('path', '')).resolve()
            for item in h12_prereg.get('forbidden_sources', [])
            if item.get('path')
        }
        if resume_path in forbidden_paths:
            parser.error('H12 forbidden H9/H10/H11/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H12 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H12 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H12 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H12 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H12 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H12 arms must preserve the source hand counter')
    if args.h13_window_arm == 'none':
        if args.h13_catchup_loss != 'mse' or args.h13_catchup_smooth_l1_beta != 1.0:
            parser.error('H13 catch-up loss options require a registered H13 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm,
        )):
            parser.error('H13 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12')
        if args.showdown_ev_value_targets:
            parser.error('H13 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H13 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h13_window_arm == 'control' else 'smooth_l1'
        if args.h13_catchup_loss != expected_loss or args.h13_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H13 {args.h13_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h13_preregistration, args.h13_preregistration_sha256),
            ('design lock', args.h13_design_lock, args.h13_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H13 {args.h13_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H13 immutable {label} identity/hash mismatch')
        try:
            h13_prereg = json.loads(Path(args.h13_preregistration).read_text(encoding='utf-8-sig'))
            h13_lock = json.loads(Path(args.h13_design_lock).read_text(encoding='utf-8-sig'))
            h13_source = h13_prereg['source']
            h13_arms = h13_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H13 immutable registration content invalid: {exc}')
        if h13_prereg.get('experiment_id') != 'H13' or h13_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H13 preregistration authority mismatch')
        if h13_lock.get('design_id') != 'H13' or h13_lock.get('status') != 'LOCKED':
            parser.error('H13 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h13_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h13_arms.get(run_key) or args.total_hands != int(h13_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H13 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H13 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h13_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h13_source.get('checkpoint_sha256', '').lower():
            parser.error('H13 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H13 forbidden H9/H10/H11/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H13 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H13 arms require per-iteration assignment provenance')
    if args.h14_window_arm == 'none':
        if args.h14_catchup_loss != 'mse' or args.h14_catchup_smooth_l1_beta != 1.0:
            parser.error('H14 catch-up loss options require a registered H14 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
        )):
            parser.error('H14 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12/H13')
        if args.showdown_ev_value_targets:
            parser.error('H14 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H14 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h14_window_arm == 'control' else 'smooth_l1'
        if args.h14_catchup_loss != expected_loss or args.h14_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H14 {args.h14_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h14_preregistration, args.h14_preregistration_sha256),
            ('design lock', args.h14_design_lock, args.h14_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H14 {args.h14_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H14 immutable {label} identity/hash mismatch')
        try:
            h14_prereg = json.loads(Path(args.h14_preregistration).read_text(encoding='utf-8-sig'))
            h14_lock = json.loads(Path(args.h14_design_lock).read_text(encoding='utf-8-sig'))
            h14_source = h14_prereg['source']
            h14_arms = h14_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H14 immutable registration content invalid: {exc}')
        if h14_prereg.get('experiment_id') != 'H14' or h14_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H14 preregistration authority mismatch')
        if h14_lock.get('design_id') != 'H14' or h14_lock.get('status') != 'LOCKED':
            parser.error('H14 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h14_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h14_arms.get(run_key) or args.total_hands != int(h14_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H14 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H14 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h14_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h14_source.get('checkpoint_sha256', '').lower():
            parser.error('H14 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'v5_hybrid_h13_', 'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H14 forbidden H9/H10/H11/H12/H13/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H14 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H14 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H13 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H13 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H13 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H13 arms must preserve the source hand counter')
    if args.h15_window_arm == 'none':
        if args.h15_catchup_loss != 'mse' or args.h15_catchup_smooth_l1_beta != 1.0:
            parser.error('H15 catch-up loss options require a registered H15 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
            args.h14_window_arm,
        )):
            parser.error('H15 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12/H13/H14')
        if args.showdown_ev_value_targets:
            parser.error('H15 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H15 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h15_window_arm == 'control' else 'smooth_l1'
        if args.h15_catchup_loss != expected_loss or args.h15_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H15 {args.h15_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h15_preregistration, args.h15_preregistration_sha256),
            ('design lock', args.h15_design_lock, args.h15_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H15 {args.h15_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H15 immutable {label} identity/hash mismatch')
        try:
            h15_prereg = json.loads(Path(args.h15_preregistration).read_text(encoding='utf-8-sig'))
            h15_lock = json.loads(Path(args.h15_design_lock).read_text(encoding='utf-8-sig'))
            h15_source = h15_prereg['source']
            h15_arms = h15_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H15 immutable registration content invalid: {exc}')
        if h15_prereg.get('experiment_id') != 'H15' or h15_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H15 preregistration authority mismatch')
        if h15_lock.get('design_id') != 'H15' or h15_lock.get('status') != 'LOCKED':
            parser.error('H15 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h15_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h15_arms.get(run_key) or args.total_hands != int(h15_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H15 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H15 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h15_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h15_source.get('checkpoint_sha256', '').lower():
            parser.error('H15 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'v5_hybrid_h13_', 'v5_hybrid_h14_',
            'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H15 forbidden H9/H10/H11/H12/H13/CAL source path (H14 terminal partial also forbidden)')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H15 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H15 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H15 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H15 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H15 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H15 arms must preserve the source hand counter')
    if args.h16_window_arm == 'none':
        if args.h16_catchup_loss != 'mse' or args.h16_catchup_smooth_l1_beta != 1.0:
            parser.error('H16 catch-up loss options require a registered H16 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
            args.h14_window_arm, args.h15_window_arm, args.h17_window_arm,
        )):
            parser.error('H16 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12/H13/H14/H15')
        if args.showdown_ev_value_targets:
            parser.error('H16 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H16 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h16_window_arm == 'control' else 'smooth_l1'
        if args.h16_catchup_loss != expected_loss or args.h16_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H16 {args.h16_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h16_preregistration, args.h16_preregistration_sha256),
            ('design lock', args.h16_design_lock, args.h16_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H16 {args.h16_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H16 immutable {label} identity/hash mismatch')
        try:
            h16_prereg = json.loads(Path(args.h16_preregistration).read_text(encoding='utf-8-sig'))
            h16_lock = json.loads(Path(args.h16_design_lock).read_text(encoding='utf-8-sig'))
            h16_source = h16_prereg['source']
            h16_arms = h16_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H16 immutable registration content invalid: {exc}')
        if h16_prereg.get('experiment_id') != 'H16' or h16_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H16 preregistration authority mismatch')
        if h16_lock.get('design_id') != 'H16' or h16_lock.get('status') != 'LOCKED':
            parser.error('H16 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h16_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h16_arms.get(run_key) or args.total_hands != int(h16_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H16 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H16 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h16_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h16_source.get('checkpoint_sha256', '').lower():
            parser.error('H16 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'v5_hybrid_h13_', 'v5_hybrid_h14_', 'v5_hybrid_h15_',
            'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H16 forbidden H9/H10/H11/H12/H13/H14/H15/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H16 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H16 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H16 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H16 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H16 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H16 arms must preserve the source hand counter')
    if args.h17_window_arm == 'none':
        if args.h17_catchup_loss != 'mse' or args.h17_catchup_smooth_l1_beta != 1.0:
            parser.error('H17 catch-up loss options require a registered H17 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
            args.h14_window_arm, args.h15_window_arm, args.h16_window_arm,
            args.h18_window_arm,
        )):
            parser.error('H17 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12/H13/H14/H15/H16')
        if args.showdown_ev_value_targets:
            parser.error('H17 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H17 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h17_window_arm == 'control' else 'smooth_l1'
        if args.h17_catchup_loss != expected_loss or args.h17_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H17 {args.h17_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h17_preregistration, args.h17_preregistration_sha256),
            ('design lock', args.h17_design_lock, args.h17_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H17 {args.h17_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H17 immutable {label} identity/hash mismatch')
        try:
            h17_prereg = json.loads(Path(args.h17_preregistration).read_text(encoding='utf-8-sig'))
            h17_lock = json.loads(Path(args.h17_design_lock).read_text(encoding='utf-8-sig'))
            h17_source = h17_prereg['source']
            h17_arms = h17_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H17 immutable registration content invalid: {exc}')
        if h17_prereg.get('experiment_id') != 'H17' or h17_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H17 preregistration authority mismatch')
        if h17_lock.get('design_id') != 'H17' or h17_lock.get('status') != 'LOCKED':
            parser.error('H17 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h17_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h17_arms.get(run_key) or args.total_hands != int(h17_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H17 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H17 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h17_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h17_source.get('checkpoint_sha256', '').lower():
            parser.error('H17 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'v5_hybrid_h13_', 'v5_hybrid_h14_', 'v5_hybrid_h15_',
            'v5_hybrid_h16_', 'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H17 forbidden H9/H10/H11/H12/H13/H14/H15/H16/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H17 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H17 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H17 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H17 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H17 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H17 arms must preserve the source hand counter')
    if args.h18_window_arm == 'none':
        if args.h18_catchup_loss != 'mse' or args.h18_catchup_smooth_l1_beta != 1.0:
            parser.error('H18 catch-up loss options require a registered H18 arm')
    else:
        if any(arm != 'none' for arm in (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
            args.h14_window_arm, args.h15_window_arm, args.h16_window_arm,
            args.h17_window_arm,
        )):
            parser.error('H18 must not bundle or reopen H2/H6/H7/H8/H9/H10/H11/H12/H13/H14/H15/H16/H17')
        if args.showdown_ev_value_targets:
            parser.error('H18 must not bundle showdown target behavior')
        if args.ppo_target_kl != 0.03 or not args.h8_value_head_catchup_after_kl_stop:
            parser.error('H18 arms require target-KL0.03 and value-head catch-up enabled')
        expected_loss = 'mse' if args.h18_window_arm == 'control' else 'smooth_l1'
        if args.h18_catchup_loss != expected_loss or args.h18_catchup_smooth_l1_beta != 1.0:
            parser.error(f'H18 {args.h18_window_arm} catch-up loss identity mismatch')
        for label, path_value, hash_value in (
            ('preregistration', args.h18_preregistration, args.h18_preregistration_sha256),
            ('design lock', args.h18_design_lock, args.h18_design_lock_sha256),
        ):
            if not path_value or not hash_value:
                parser.error(f'H18 {args.h18_window_arm} requires {label} path and SHA256')
            bound_path = Path(path_value)
            if not bound_path.is_file() or sha256_path(bound_path) != hash_value.lower():
                parser.error(f'H18 immutable {label} identity/hash mismatch')
        try:
            h18_prereg = json.loads(Path(args.h18_preregistration).read_text(encoding='utf-8-sig'))
            h18_lock = json.loads(Path(args.h18_design_lock).read_text(encoding='utf-8-sig'))
            h18_source = h18_prereg['source']
            h18_arms = h18_prereg['arms']
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'H18 immutable registration content invalid: {exc}')
        if h18_prereg.get('experiment_id') != 'H18' or h18_prereg.get('status') != 'REGISTERED_NO_LAUNCH':
            parser.error('H18 preregistration authority mismatch')
        if h18_lock.get('design_id') != 'H18' or h18_lock.get('status') != 'LOCKED':
            parser.error('H18 design-lock authority mismatch')
        run_key = 'control_run_id' if args.h18_window_arm == 'control' else 'treatment_run_id'
        if args.run_id != h18_arms.get(run_key) or args.total_hands != int(h18_arms.get('minimum_endpoint_hands', -1)):
            parser.error('H18 arm run_id or fixed endpoint mismatch')
        if not args.resume or not args.allow_resume or args.reset_optimizer:
            parser.error('H18 arms require --resume --allow-resume and --no-reset-optimizer')
        resume_path = Path(args.resume).resolve()
        canonical_source = Path(h18_source.get('checkpoint_path', '')).resolve()
        if resume_path != canonical_source or sha256_path(resume_path) != h18_source.get('checkpoint_sha256', '').lower():
            parser.error('H18 exact canonical source checkpoint identity/hash mismatch')
        normalized_resume = str(resume_path).replace('\\', '/').lower()
        if any(token in normalized_resume for token in (
            'v5_hybrid_h9_', 'v5_hybrid_h10_', 'v5_hybrid_h11_treatment_',
            'v5_hybrid_h12_', 'v5_hybrid_h13_', 'v5_hybrid_h14_', 'v5_hybrid_h15_',
            'v5_hybrid_h16_', 'v5_hybrid_h17_', 'cal-ext-', 'cal_ext_', 'benchmark',
        )):
            parser.error('H18 forbidden H9/H10/H11/H12/H13/H14/H15/H16/H17/CAL source path')
        if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
            parser.error('H18 arms require fixed deal stream and worker-seed-base73000')
        if args.opponent_assignment != 'per-iteration' or not args.opponent_assignment_provenance_file:
            parser.error('H18 arms require per-iteration assignment provenance')
        if args.critic_contract != CRITIC_V1 or args.value_coef != 0.5 or args.ppo_epochs != 4:
            parser.error('H18 arms require critic_v1,value_coef0.5 and four PPO epochs')
        if not args.mirror_self_play_deals or not args.allin_runout_ev or args.allin_runout_ev_max_runouts != 200:
            parser.error('H18 arms require the frozen retained EXP-003 configuration')
        if (
            args.preflop_action_prior_coef != 0.01
            or args.postflop_action_prior_coef != 0.02
            or args.preflop_sb_open_action_prior_coef != 0.0
            or args.preflop_bb_vs_open_action_prior_coef != 0.0
        ):
            parser.error('H18 arms require frozen0.01/0.02 generic priors only')
        if args.reset_hand_counter:
            parser.error('H18 arms must preserve the source hand counter')
    if args.inference_min_batch_slots > args.workers * args.rollout_envs_per_worker:
        parser.error(f'--inference-min-batch-slots ({args.inference_min_batch_slots}) '
                     f'exceeds total slots W*M='
                     f'{args.workers * args.rollout_envs_per_worker}; it could never be met '
                     f'and every serve would wait for the deadline.')
    if args.fixed_training_deal_stream and args.worker_seed_base is None:
        parser.error('--fixed-training-deal-stream requires --worker-seed-base')
    if args.exp_w1_value_warmup_epochs < 0:
        parser.error('--exp-w1-value-warmup-epochs must be >= 0')
    if args.exp_w1_value_warmup_at_iteration > 0:
        if not args.exp_w1_design_lock or not args.exp_w1_design_lock_sha256:
            parser.error('EXP-W1 arms require design-lock path and expected SHA256')
        lock_path = Path(args.exp_w1_design_lock)
        if (
            not lock_path.exists()
            or sha256_path(lock_path) != args.exp_w1_design_lock_sha256.lower()
        ):
            parser.error('EXP-W1 immutable design-lock identity/hash mismatch')
    if args.exp_w1_value_warmup_epochs > 0:
        if not args.resume or args.reset_optimizer:
            parser.error('EXP-W1 treatment requires --resume, --allow-resume and --no-reset-optimizer')
        if not args.fixed_training_deal_stream or args.worker_seed_base is None:
            parser.error('EXP-W1 treatment requires a fixed training deal stream and worker seed base')
        if args.opponent_assignment != 'per-iteration':
            parser.error('EXP-W1 treatment requires per-iteration opponent assignment')
        if not args.opponent_assignment_provenance_file:
            parser.error('EXP-W1 treatment requires assignment provenance')
        if args.exp_w1_value_warmup_at_iteration <= 0:
            parser.error('EXP-W1 treatment requires an exact positive warmup iteration')
        if not 0.05 <= args.exp_w1_value_warmup_heldout_fraction <= 0.5:
            parser.error('EXP-W1 heldout fraction must be in [0.05, 0.5]')
        if not 0.0 < args.exp_w1_value_warmup_min_relative_mse_reduction < 1.0:
            parser.error('EXP-W1 minimum relative MSE reduction must be in (0, 1)')
        if not args.exp_w1_value_warmup_report:
            parser.error('EXP-W1 treatment requires an immutable report path')
    if not 0.0 <= args.gae_lambda <= 1.0:
        parser.error('--gae-lambda must be in [0, 1]')

    if args.autonomous_critic_v2_reset and args.critic_contract != CRITIC_V2:
        parser.error('--autonomous-critic-v2-reset requires --critic-contract critic_v2')
    if args.autonomous_critic_v2_continue and args.critic_contract != CRITIC_V2:
        parser.error('--autonomous-critic-v2-continue requires --critic-contract critic_v2')
    if args.autonomous_critic_v2_reset and args.autonomous_critic_v2_continue:
        parser.error(
            '--autonomous-critic-v2-reset and '
            '--autonomous-critic-v2-continue are mutually exclusive'
        )
    if args.critic_contract == CRITIC_V2:
        if args.h1_effective_stack_divisor != 200.0:
            parser.error('H1 critic_v2 requires exact --h1-effective-stack-divisor 200')
        if args.h1_critic_init_seed != 2026071102:
            parser.error('H1 critic_v2 requires exact initialization seed 2026071102')
        if args.value_coef != 1.0:
            parser.error('H1 critic_v2 requires exact --value-coef 1.0')
        if args.autonomous_critic_v2_reset:
            if not args.resume or not args.allow_resume:
                parser.error(
                    'autonomous critic_v2 mode requires --resume and --allow-resume'
                )
            if args.exp_w1_value_warmup_epochs != 0 or args.exp_w1_value_warmup_at_iteration != 0:
                parser.error('autonomous critic_v2 reset cannot combine with EXP-W1 warmup')
        elif args.autonomous_critic_v2_continue:
            if not args.resume or not args.allow_resume:
                parser.error(
                    'autonomous critic_v2 continuation requires '
                    '--resume and --allow-resume'
                )
            if (
                args.exp_w1_value_warmup_epochs != 0
                or args.exp_w1_value_warmup_at_iteration != 0
            ):
                parser.error(
                    'autonomous critic_v2 continuation cannot combine '
                    'with EXP-W1 warmup'
                )
        else:
            if not args.resume or args.reset_optimizer:
                parser.error('H1 critic_v2 requires --resume --allow-resume --no-reset-optimizer')
            if args.exp_w1_value_warmup_epochs != 0 or args.exp_w1_value_warmup_at_iteration != 0:
                parser.error('H1 must not reopen EXP-W1 warmup')
            if not args.fixed_training_deal_stream or args.worker_seed_base != 73000:
                parser.error('H1 requires exact fixed deal stream and worker-seed-base 73000')
            if args.opponent_assignment != 'per-iteration':
                parser.error('H1 requires per-iteration opponent assignment')
            if not args.h1_preregistration or not args.h1_preregistration_sha256:
                parser.error('H1 requires preregistration path and SHA256')
            prereg = Path(args.h1_preregistration)
            if not prereg.is_file() or sha256_path(prereg) != args.h1_preregistration_sha256.lower():
                parser.error('H1 preregistration identity/hash mismatch')
            if not args.h1_migration_report:
                parser.error('H1 critic_v2 requires a migration report path')
    else:
        if args.value_coef < 0.0:
            parser.error('--value-coef must be >= 0')
        if args.critic_head_only_gradient and args.value_coef <= 0.0:
            parser.error('--critic-head-only-gradient requires --value-coef > 0')

    lg002_contract = None
    if args.lg002_recovery_contract_probe and not lg002_recovery_active:
        parser.error('LG002 recovery contract probe requires an active LG002 arm')
    if lg002_recovery_active:
        workspace = Path(__file__).resolve().parents[2]
        expected_preregistration = (
            workspace / 'reports'
            / f'v5_lg002_recovery_preregistration_{LG002_RECOVERY_TOKEN}_20260722.json'
        ).resolve()
        preregistration_path = Path(args.lg002_recovery_preregistration)
        if not preregistration_path.is_absolute() or preregistration_path.resolve() != expected_preregistration:
            parser.error('LG002 recovery preregistration must use the canonical absolute Windows path')
        if (
            args.lg002_recovery_preregistration_sha256.lower() != LG002_RECOVERY_PREREG_SHA256
            or not expected_preregistration.is_file()
            or sha256_path(expected_preregistration) != LG002_RECOVERY_PREREG_SHA256
        ):
            parser.error('LG002 recovery preregistration identity/hash mismatch')
        try:
            lg002_prereg = json.loads(expected_preregistration.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parser.error(f'LG002 recovery preregistration content invalid: {exc}')
        if (
            lg002_prereg.get('schema_version') != 'v5.lg002.recovery.preregistration.v1'
            or lg002_prereg.get('registration_token') != LG002_RECOVERY_TOKEN
            or lg002_prereg.get('design_id')
            != 'LG002_RECOVERY_ACTUAL_TRAIN_V5_FROZEN_DIVERSITY_WEIGHTED_LEAGUE'
        ):
            parser.error('LG002 recovery preregistration authority mismatch')

        legacy_arms = [
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm, args.h12_window_arm, args.h13_window_arm,
            args.h14_window_arm, args.h15_window_arm, args.h16_window_arm,
            args.h17_window_arm, args.h18_window_arm,
        ]
        legacy_paths = [
            value
            for prefix in ('h2', 'h6', 'h7', 'h8', 'h9', 'h10', 'h11', 'h12',
                           'h13', 'h14', 'h15', 'h16', 'h17', 'h18')
            for value in (
                getattr(args, f'{prefix}_preregistration'),
                getattr(args, f'{prefix}_preregistration_sha256'),
                getattr(args, f'{prefix}_design_lock'),
                getattr(args, f'{prefix}_design_lock_sha256'),
            )
        ]
        if any(arm != 'none' for arm in legacy_arms) or any(legacy_paths):
            parser.error('LG002 recovery forbids every legacy H2/H6-H18 arm identity and path')
        if any((args.h1_preregistration, args.h1_preregistration_sha256,
                args.h1_migration_report, args.exp_w1_design_lock,
                args.exp_w1_design_lock_sha256, args.exp_w1_value_warmup_report)):
            parser.error('LG002 recovery forbids H1 and EXP-W1 identities')
        if args.exp_w1_value_warmup_epochs != 0 or args.exp_w1_value_warmup_at_iteration != 0:
            parser.error('LG002 recovery forbids EXP-W1 warmup behavior')
        if args.showdown_ev_value_targets:
            parser.error('LG002 recovery forbids H2 showdown target behavior')

        exact_common = {
            'device': 'cuda', 'workers': 22, 'hands_per_iter': 16384, 'starting_stack': 200.0,
            'env_version': 'v55', 'lr': 0.0003, 'ppo_epochs': 4,
            'ppo_target_kl': 0.03, 'mini_batch_size': 1024, 'epsilon': 0.0,
            'gamma': 0.999, 'entropy_coef': 0.05, 'entropy_floor': 0.3,
            'k_best': 5, 'pool_strategy': 'loss-kbest', 'pool_history_limit': 200,
            'self_play_fraction': 0.2,
            'opponent_assignment': 'per-iteration', 'opponent_groups': 5,
            'rollout_mode': 'multi', 'rollout_envs_per_worker': 16,
            'inference_min_batch_slots': 256, 'inference_batch_deadline_us': 1000.0,
            'worker_seed_base': 73000, 'allin_runout_ev_max_runouts': 200,
            'preflop_action_prior_coef': 0.01, 'postflop_action_prior_coef': 0.02,
            'preflop_sb_open_action_prior_coef': 0.0,
            'preflop_bb_vs_open_action_prior_coef': 0.0,
            'critic_contract': CRITIC_V1, 'value_coef': 0.5,
            'snapshot_every': 200, 'save_interval': 1, 'seed': 20260703,
            'max_runtime_seconds': 10800.0,
        }
        mismatches = {
            name: {'actual': getattr(args, name), 'expected': expected}
            for name, expected in exact_common.items()
            if getattr(args, name) != expected
        }
        if mismatches:
            parser.error(f'LG002 recovery common training mismatch: {mismatches}')
        if not all((args.fixed_training_deal_stream, args.mirror_self_play_deals,
                    args.allin_runout_ev, args.h8_value_head_catchup_after_kl_stop)):
            parser.error('LG002 recovery retained deal/EV/MSE-catchup flags are incomplete')
        if not args.resume or not args.allow_resume or args.reset_optimizer or args.reset_hand_counter:
            parser.error('LG002 recovery requires exact resume with optimizer and hand counter preserved')
        if not args.opponent_assignment_provenance_file:
            parser.error('LG002 recovery requires hash-chained assignment provenance')
        if args.overwrite or args.trace_transitions_file or args.validate_stream:
            parser.error('LG002 recovery forbids overwrite, trace and validation debug behavior')
        if args.total_hands not in (581021901, 596021901):
            parser.error('LG002 recovery target hands are outside frozen Stage A/Stage B endpoints')

        source_path = Path(args.resume)
        registered_source = Path(lg002_prereg['source_checkpoint']['path']).resolve()
        if (
            not source_path.is_absolute()
            or source_path.resolve() != registered_source
            or sha256_path(source_path) != LG002_RECOVERY_SOURCE_SHA256
        ):
            parser.error('LG002 recovery exact source checkpoint identity/hash mismatch')
        checkpoint = torch.load(source_path, map_location='cpu', weights_only=False)
        if (
            int(checkpoint.get('iteration', -1)) != 35051
            or int(checkpoint.get('total_hands', -1)) != 576021901
            or 'model' not in checkpoint
            or 'optimizer' not in checkpoint
        ):
            parser.error('LG002 recovery source model/optimizer/hand/iteration contract mismatch')
        snapshots = checkpoint.get('pool_snapshots') or []
        snapshot_ids = tuple(int(row.get('id', -1)) for row in snapshots)
        if snapshot_ids != LG002_RECOVERY_CHECKPOINT_ORDER:
            parser.error(f'LG002 recovery frozen pool order mismatch: {snapshot_ids}')
        for row in snapshots:
            member_id = int(row['id'])
            if lg002_state_dict_sha256(row['state_dict']) != LG002_RECOVERY_MEMBER_STATE_SHA256[member_id]:
                parser.error(f'LG002 recovery frozen member state mismatch: {member_id}')

        output_root = Path(lg002_prereg['fresh_paths']['output_root']).resolve()
        for label, raw_path in (
            ('run-dir', args.run_dir), ('out', args.out),
            ('provenance', args.opponent_assignment_provenance_file),
        ):
            path = Path(raw_path or '')
            if not path.is_absolute():
                parser.error(f'LG002 recovery {label} must be an absolute Windows child path')
            try:
                path.resolve().relative_to(output_root)
            except ValueError:
                parser.error(f'LG002 recovery {label} escapes the registered output root')

        lg002_contract = {
            'registration_token': LG002_RECOVERY_TOKEN,
            'registration_sha256': LG002_RECOVERY_PREREG_SHA256,
            'source_checkpoint_sha256': LG002_RECOVERY_SOURCE_SHA256,
            'source_iteration': 35051,
            'source_total_hands': 576021901,
            'pool_checkpoint_order': list(LG002_RECOVERY_CHECKPOINT_ORDER),
            'member_state_sha256': {
                str(k): v for k, v in sorted(LG002_RECOVERY_MEMBER_STATE_SHA256.items())
            },
            'conditional_weights': {
                str(k): v for k, v in sorted(
                    LG002_RECOVERY_CONDITIONAL_WEIGHTS[args.lg002_recovery_arm].items()
                )
            },
            'assignment_seed': LG002_RECOVERY_ASSIGNMENT_SEED,
            'pool_mutation_disabled': True,
        }
        if args.lg002_recovery_contract_probe:
            if output_root.exists():
                parser.error('LG002 recovery zero-output probe requires absent registered output root')
            probe_iterations = (35052, 35053, 35054, 35055)
            probe = {
                'schema_version': 'v5.lg002.recovery.contract_probe.v1',
                'status': 'PASS',
                'arm': args.lg002_recovery_arm,
                'contract': lg002_contract,
                'selector_samples': [
                    {
                        'absolute_iteration': absolute_iteration,
                        **lg002_select_opponent(
                            args.lg002_recovery_arm, absolute_iteration, snapshots,
                        )[1],
                    }
                    for absolute_iteration in probe_iterations
                ],
                'target_kl': args.ppo_target_kl,
                'value_head_catchup': args.h8_value_head_catchup_after_kl_stop,
                'value_head_catchup_loss': 'mse',
                'global_rng_consumption': 0,
                'files_written': 0,
                'gpu_initialized': False,
            }
            print(json.dumps(probe, sort_keys=True, separators=(',', ':')))
            return
    run_id = args.run_id or f"v5_hybrid_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
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

    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=args.norm_layer,
        critic_contract=args.critic_contract,
        critic_init_seed=args.h1_critic_init_seed,
        separate_preflop_head=args.separate_preflop_head,
        postflop_adapter_hidden=args.postflop_adapter_hidden,
        position_adapter_hidden=args.position_adapter_hidden,
        position_value_adapter_hidden=(
            args.position_value_adapter_hidden
        ),
    ).to(device)
    dc = torch.zeros(1, 6, 4, 13, device=device)
    da = torch.zeros(1, 25, 4, 5, device=device)
    de = torch.zeros(1, EXTRA_SIZE, device=device)
    model(dc, da, de)
    print(f'Parameters: {count_parameters(model):,}')

    if args.position_adapter_only_training:
        trainable_prefixes = position_adapter_trainable_prefixes(
            args.position_adapter_training_seat
        )
        for name, parameter in model.named_parameters():
            parameter.requires_grad = name.startswith(trainable_prefixes)
        trainable_count = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )
        optimizer = torch.optim.Adam(
            [
                parameter
                for parameter in model.parameters()
                if parameter.requires_grad
            ],
            lr=args.lr,
        )
        print(
            f'Position-adapter-only training: {trainable_count:,} trainable '
            f'parameters (actor seat={args.position_adapter_training_seat} '
            '+ value head)'
        )
    elif args.adapter_only_training:
        trainable_prefixes = ('postflop_policy_adapter.', 'value_head.')
        for name, parameter in model.named_parameters():
            parameter.requires_grad = name.startswith(trainable_prefixes)
        trainable_count = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )
        optimizer = torch.optim.Adam(
            [
                parameter
                for parameter in model.parameters()
                if parameter.requires_grad
            ],
            lr=args.lr,
        )
        print(
            f'Adapter-only training: {trainable_count:,} trainable parameters '
            '(postflop residual adapter + value head)'
        )
    elif args.head_only_training:
        trainable_prefixes = ('policy_head.', 'value_head.')
        for name, parameter in model.named_parameters():
            parameter.requires_grad = name.startswith(trainable_prefixes)
        trainable_count = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )
        optimizer = torch.optim.Adam(
            [
                parameter
                for parameter in model.parameters()
                if parameter.requires_grad
            ],
            lr=args.lr,
        )
        print(
            f'Head-only training: {trainable_count:,} trainable parameters '
            '(policy_head + value_head)'
        )
    elif args.separate_preflop_head and args.preflop_head_lr > 0.0:
        preflop_parameters = list(model.preflop_policy_head.parameters())
        preflop_parameter_ids = {id(parameter) for parameter in preflop_parameters}
        shared_parameters = [
            parameter
            for parameter in model.parameters()
            if id(parameter) not in preflop_parameter_ids
        ]
        optimizer = torch.optim.Adam(
            [
                {'params': shared_parameters, 'lr': args.lr},
                {'params': preflop_parameters, 'lr': args.preflop_head_lr},
            ],
            lr=args.lr,
        )
        print(
            f'Dedicated preflop-head learning rate: '
            f'{args.preflop_head_lr:g} (shared={args.lr:g})'
        )
    else:
        optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    pool = OpponentPool(k=args.k_best, strategy=args.pool_strategy, history_limit=args.pool_history_limit)

    goal_spec = {
        'project': 'AlphaHoldem HYBRID H1',
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
            'h1_critic_contract': {
                'contract': args.critic_contract,
                'effective_stack_divisor': args.h1_effective_stack_divisor if args.critic_contract == CRITIC_V2 else 1.0,
                'value_coef': args.value_coef,
                'critic_init_seed': args.h1_critic_init_seed,
                'popart': False,
                'value_gradient_to_shared_trunk': args.critic_contract != CRITIC_V2,
                'route': 'HYBRID',
                'official_hands_authorized': 0,
            },
            'h2_showdown_critic_targets': {
                'enabled': bool(args.showdown_ev_value_targets),
                'scope': 'critic_return_only_for_nonfold_showdown_rows_before_complete_river',
                'max_runouts': int(args.showdown_ev_value_target_max_runouts),
                'target_seed': int(args.showdown_ev_value_target_seed),
                'actor_rewards_unchanged': True,
                'actor_gae_advantages_unchanged': True,
                'estimand': 'conditional line value holding terminal committed chips fixed',
                'counterfactual_action_ev': False,
                'official_hands_authorized': 0,
            },
            'h6_ppo_kl_early_stop': {
                'enabled': args.h6_window_arm == 'treatment',
                'target_kl': float(args.ppo_target_kl),
                'comparison': 'strict_greater_than_epoch_mean',
                'ppo_epochs_max': int(args.ppo_epochs),
                'official_hands_authorized': 0,
            },
            'h7_contemporaneous_ppo_kl_early_stop': {
                'arm': args.h7_window_arm,
                'enabled': args.h7_window_arm == 'treatment',
                'target_kl': float(args.ppo_target_kl),
                'resource_isolation': 'no_endpoint_evaluation_while_either_arm_trainer_active',
                'official_hands_authorized': 0,
            },
            'h8_value_head_only_catchup': {
                'arm': args.h8_window_arm,
                'enabled': bool(args.h8_value_head_catchup_after_kl_stop),
                'target_kl': float(args.ppo_target_kl),
                'optimizer_preserved': not bool(args.reset_optimizer),
                'actor_update_after_kl_stop': False,
                'resource_isolation': 'no_endpoint_evaluation_while_either_arm_trainer_active',
                'official_hands_authorized': 0,
            },
            'h9_robust_value_head_catchup': {
                'arm': args.h9_window_arm,
                'catchup_loss': args.h9_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h9_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'official_hands_authorized': 0,
            },
            'h10_clean_robust_value_head_catchup': {
                'arm': args.h10_window_arm,
                'catchup_loss': args.h10_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h10_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'canonical_h8_only_h9_partial_and_cal_copy_forbidden',
                'official_hands_authorized': 0,
            },
            'h11_clean_robust_value_head_catchup': {
                'arm': args.h11_window_arm,
                'catchup_loss': args.h11_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h11_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'canonical_h8_only_h9_h10_partial_and_cal_copy_forbidden',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h12_resource_matched_robust_value_head_catchup': {
                'arm': args.h12_window_arm,
                'catchup_loss': args.h12_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h12_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_h9_h10_h11_partials_and_cal_copy_forbidden',
                'pre_arm_perf_calibration': 'required_loss_and_common_mse_ratio_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h13_clean_robust_value_head_catchup': {
                'arm': args.h13_window_arm,
                'catchup_loss': args.h13_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h13_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_and_cal_copies_forbidden',
                'pre_arm_perf_calibration': 'required_loss_and_common_mse_ratio_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h14_clean_robust_value_head_catchup': {
                'arm': args.h14_window_arm,
                'catchup_loss': args.h14_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h14_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_and_cal_copies_forbidden',
                'pre_arm_perf_calibration': 'required_loss_and_common_mse_ratio_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h15_cpv004_validated_robust_value_head_catchup': {
                'arm': args.h15_window_arm,
                'catchup_loss': args.h15_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h15_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_cal_copies_and_cpv_dummy_assets_forbidden',
                'lifecycle_prerequisite': 'CPV004_PASS',
                'pre_arm_perf_calibration': 'required_loss_and_common_mse_ratio_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h16_representative_perf_cal_robust_value_head_catchup': {
                'arm': args.h16_window_arm,
                'catchup_loss': args.h16_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h16_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_cal_copies_and_cpv_dummy_assets_forbidden',
                'pre_arm_perf_calibration': 'representative_full_ppo_update_ratio_min_0.85_and_mse_stability_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h17_deterministic_trigger_robust_value_head_catchup': {
                'arm': args.h17_window_arm,
                'catchup_loss': args.h17_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h17_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_cal_copies_and_pcv_assets_forbidden',
                'pre_arm_perf_calibration': 'offset10_full_ppo_update_ratio_min_0.85_and_mse_stability_min_0.95',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'h18_tolerance_gpu_event_robust_value_head_catchup': {
                'arm': args.h18_window_arm,
                'catchup_loss': args.h18_catchup_loss,
                'smooth_l1_beta_raw_bb': float(args.h18_catchup_smooth_l1_beta),
                'standard_ppo_critic_loss': 'mse',
                'target_kl': float(args.ppo_target_kl),
                'source_policy': 'exact_h11_control_only_all_terminal_partials_cal_copies_and_pcv_assets_forbidden',
                'pre_arm_perf_calibration': 'offset10_cuda_event_ratio_min_0.85_mse_stability_min_0.95_model_tol_1e-6_optimizer_tol_1e-8',
                'active_arm_observer_policy': 'no_parent_or_delegated_commands',
                'official_hands_authorized': 0,
            },
            'exp_w1_value_head_warmup': {
                'epochs': int(args.exp_w1_value_warmup_epochs),
                'at_iteration': int(args.exp_w1_value_warmup_at_iteration),
                'heldout_fraction': float(args.exp_w1_value_warmup_heldout_fraction),
                'minimum_relative_mse_reduction': float(
                    args.exp_w1_value_warmup_min_relative_mse_reduction
                ),
                'status': 'control_disabled' if args.exp_w1_value_warmup_epochs == 0 else 'treatment_pending',
            },
        },
    }

    obs_version = (
        'v4'
        if args.env_version in (
            'v4',
            'v55cap1v4obs',
            'v55v4obs',
            'v55pfv2v4obs',
            'v55preflopv2v4obs',
        )
        else 'v55'
    )
    resume_source = args.resume
    lineage_parent_checkpoint = args.resume
    fresh_from_zero_lineage = not bool(args.resume)
    lineage_root_run_id = args.run_id
    exp_w1_warmup_state = {
        'status': 'DISABLED' if args.exp_w1_value_warmup_epochs == 0 else 'PENDING',
        'epochs': int(args.exp_w1_value_warmup_epochs),
        'at_iteration': int(args.exp_w1_value_warmup_at_iteration),
        'report_path': args.exp_w1_value_warmup_report or None,
        'report_sha256': None,
    }
    assignment_provenance_last_sha = None
    assignment_provenance_last_iteration = None

    def checkpoint_payload() -> dict:
        payload = {
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
            'action_space_version': (
                '9slot_pot_fraction_v2'
                if args.env_version == 'v55pfv2v4obs'
                else (
                    '9slot_preflop_pot_fraction_v2'
                    if args.env_version == 'v55preflopv2v4obs'
                    else '9slot_v5'
                )
            ),
            'raise_action_mapping': (
                'pot_fraction_v2'
                if args.env_version == 'v55pfv2v4obs'
                else (
                    'preflop_pot_fraction_v2'
                    if args.env_version == 'v55preflopv2v4obs'
                    else 'legacy_total_over_pot'
                )
            ),
            'starting_stack_bb': args.starting_stack,
            'actual_hand_accounting': True,
            'critic_contract': args.critic_contract,
            'norm_layer': args.norm_layer,
            'separate_preflop_head': bool(args.separate_preflop_head),
            'postflop_adapter_hidden': int(args.postflop_adapter_hidden),
            'position_adapter_hidden': int(args.position_adapter_hidden),
            'position_value_adapter_hidden': int(
                args.position_value_adapter_hidden
            ),
            'adapter_only_training': bool(args.adapter_only_training),
            'position_adapter_only_training': bool(
                args.position_adapter_only_training
            ),
            'position_adapter_training_seat': str(
                args.position_adapter_training_seat
            ),
            'effective_stack_divisor': args.h1_effective_stack_divisor if args.critic_contract == CRITIC_V2 else 1.0,
            'value_coef': args.value_coef,
            'h2_showdown_ev_value_targets': bool(args.showdown_ev_value_targets),
            'h2_showdown_ev_value_target_max_runouts': int(args.showdown_ev_value_target_max_runouts),
            'h2_showdown_ev_value_target_seed': int(args.showdown_ev_value_target_seed),
            'h2_window_arm': args.h2_window_arm,
            'h2_preregistration_sha256': args.h2_preregistration_sha256 or None,
            'h2_design_lock_sha256': args.h2_design_lock_sha256 or None,
            'h6_window_arm': args.h6_window_arm,
            'h6_preregistration_sha256': args.h6_preregistration_sha256 or None,
            'h6_design_lock_sha256': args.h6_design_lock_sha256 or None,
            'h7_window_arm': args.h7_window_arm,
            'h7_preregistration_sha256': args.h7_preregistration_sha256 or None,
            'h7_design_lock_sha256': args.h7_design_lock_sha256 or None,
            'h8_window_arm': args.h8_window_arm,
            'h8_value_head_catchup_after_kl_stop': bool(
                args.h8_value_head_catchup_after_kl_stop
            ),
            'h8_preregistration_sha256': args.h8_preregistration_sha256 or None,
            'h8_design_lock_sha256': args.h8_design_lock_sha256 or None,
            'h9_window_arm': args.h9_window_arm,
            'h9_catchup_loss': args.h9_catchup_loss,
            'h9_catchup_smooth_l1_beta': float(args.h9_catchup_smooth_l1_beta),
            'h9_preregistration_sha256': args.h9_preregistration_sha256 or None,
            'h9_design_lock_sha256': args.h9_design_lock_sha256 or None,
            'h10_window_arm': args.h10_window_arm,
            'h10_catchup_loss': args.h10_catchup_loss,
            'h10_catchup_smooth_l1_beta': float(args.h10_catchup_smooth_l1_beta),
            'h10_preregistration_sha256': args.h10_preregistration_sha256 or None,
            'h10_design_lock_sha256': args.h10_design_lock_sha256 or None,
            'h11_window_arm': args.h11_window_arm,
            'h11_catchup_loss': args.h11_catchup_loss,
            'h11_catchup_smooth_l1_beta': float(args.h11_catchup_smooth_l1_beta),
            'h11_preregistration_sha256': args.h11_preregistration_sha256 or None,
            'h11_design_lock_sha256': args.h11_design_lock_sha256 or None,
            'h12_window_arm': args.h12_window_arm,
            'h12_catchup_loss': args.h12_catchup_loss,
            'h12_catchup_smooth_l1_beta': float(args.h12_catchup_smooth_l1_beta),
            'h12_preregistration_sha256': args.h12_preregistration_sha256 or None,
            'h12_design_lock_sha256': args.h12_design_lock_sha256 or None,
            'h13_window_arm': args.h13_window_arm,
            'h13_catchup_loss': args.h13_catchup_loss,
            'h13_catchup_smooth_l1_beta': float(args.h13_catchup_smooth_l1_beta),
            'h13_preregistration_sha256': args.h13_preregistration_sha256 or None,
            'h13_design_lock_sha256': args.h13_design_lock_sha256 or None,
            'h14_window_arm': args.h14_window_arm,
            'h14_catchup_loss': args.h14_catchup_loss,
            'h14_catchup_smooth_l1_beta': float(args.h14_catchup_smooth_l1_beta),
            'h14_preregistration_sha256': args.h14_preregistration_sha256 or None,
            'h14_design_lock_sha256': args.h14_design_lock_sha256 or None,
            'h15_window_arm': args.h15_window_arm,
            'h15_catchup_loss': args.h15_catchup_loss,
            'h15_catchup_smooth_l1_beta': float(args.h15_catchup_smooth_l1_beta),
            'h15_preregistration_sha256': args.h15_preregistration_sha256 or None,
            'h15_design_lock_sha256': args.h15_design_lock_sha256 or None,
            'h16_window_arm': args.h16_window_arm,
            'h16_catchup_loss': args.h16_catchup_loss,
            'h16_catchup_smooth_l1_beta': float(args.h16_catchup_smooth_l1_beta),
            'h16_preregistration_sha256': args.h16_preregistration_sha256 or None,
            'h16_design_lock_sha256': args.h16_design_lock_sha256 or None,
            'h17_window_arm': args.h17_window_arm,
            'h17_catchup_loss': args.h17_catchup_loss,
            'h17_catchup_smooth_l1_beta': float(args.h17_catchup_smooth_l1_beta),
            'h17_preregistration_sha256': args.h17_preregistration_sha256 or None,
            'h17_design_lock_sha256': args.h17_design_lock_sha256 or None,
            'h18_window_arm': args.h18_window_arm,
            'h18_catchup_loss': args.h18_catchup_loss,
            'h18_catchup_smooth_l1_beta': float(args.h18_catchup_smooth_l1_beta),
            'h18_preregistration_sha256': args.h18_preregistration_sha256 or None,
            'h18_design_lock_sha256': args.h18_design_lock_sha256 or None,
            'ppo_target_kl': float(args.ppo_target_kl),
            'route_identity': 'HYBRID',
            'h1_preregistration_sha256': args.h1_preregistration_sha256 or None,
            'exp_w1_value_warmup': exp_w1_warmup_state,
        }
        if lg002_recovery_active:
            payload['lg002_recovery'] = {
                **lg002_contract,
                'arm': args.lg002_recovery_arm,
                'assignment_provenance_tail_sha256': assignment_provenance_last_sha,
                'pool_membership_frozen': True,
                'new_snapshot_addition_disabled': True,
            }
        return payload

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
        source_critic_contract = str(
            ckpt.get('critic_contract')
            or (ckpt.get('config') or {}).get('critic_contract')
            or CRITIC_V1
        )
        if args.critic_contract == CRITIC_V2 and source_critic_contract == CRITIC_V1:
            if args.autonomous_critic_v2_continue:
                raise RuntimeError(
                    'autonomous critic_v2 continuation requires a critic_v2 source'
                )
            if args.autonomous_critic_v2_reset:
                if not args.reset_optimizer:
                    raise RuntimeError(
                        'autonomous critic_v1->critic_v2 migration requires '
                        '--reset-optimizer'
                    )
                source_actor = {
                    name: value
                    for name, value in ckpt['model'].items()
                    if not name.startswith('value_head.')
                }
                target_state = model.state_dict()
                target_actor_keys = {
                    name
                    for name in target_state
                    if not name.startswith('value_head.')
                }
                source_has_preflop_head = (
                    'preflop_policy_head.weight' in source_actor
                    and 'preflop_policy_head.bias' in source_actor
                )
                adding_preflop_head = (
                    args.separate_preflop_head and not source_has_preflop_head
                )
                source_has_postflop_adapter = (
                    'postflop_policy_adapter.0.weight' in source_actor
                )
                adding_postflop_adapter = (
                    args.postflop_adapter_hidden > 0
                    and not source_has_postflop_adapter
                )
                source_has_position_adapter = (
                    'position_policy_adapters.0.0.weight' in source_actor
                )
                adding_position_adapter = (
                    args.position_adapter_hidden > 0
                    and not source_has_position_adapter
                )
                source_has_position_value_adapter = (
                    'position_value_adapters.0.0.weight' in source_actor
                )
                adding_position_value_adapter = (
                    args.position_value_adapter_hidden > 0
                    and not source_has_position_value_adapter
                )
                allowed_new_actor_keys = set()
                if adding_preflop_head:
                    allowed_new_actor_keys.update({
                        'preflop_policy_head.weight',
                        'preflop_policy_head.bias',
                    })
                if adding_postflop_adapter:
                    allowed_new_actor_keys.update({
                        'postflop_policy_adapter.0.weight',
                        'postflop_policy_adapter.0.bias',
                        'postflop_policy_adapter.2.weight',
                        'postflop_policy_adapter.2.bias',
                    })
                if adding_position_adapter:
                    allowed_new_actor_keys.update({
                        f'position_policy_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if adding_position_value_adapter:
                    allowed_new_actor_keys.update({
                        f'position_value_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                missing_actor_keys = target_actor_keys - set(source_actor)
                extra_actor_keys = set(source_actor) - target_actor_keys
                if (
                    missing_actor_keys != allowed_new_actor_keys
                    or extra_actor_keys
                ):
                    missing = sorted(missing_actor_keys)
                    extra = sorted(set(source_actor) - target_actor_keys)
                    raise RuntimeError(
                        'autonomous critic_v2 actor keys mismatch: '
                        f'missing={missing[:5]} extra={extra[:5]}'
                    )
                for name, value in source_actor.items():
                    if target_state[name].shape != value.shape:
                        raise RuntimeError(
                            f'autonomous critic_v2 actor shape mismatch: {name}'
                        )
                loaded = model.load_state_dict(source_actor, strict=False)
                expected_missing = {
                    name
                    for name in target_state
                    if name.startswith('value_head.')
                }
                expected_missing.update(allowed_new_actor_keys)
                if (
                    set(loaded.missing_keys) != expected_missing
                    or loaded.unexpected_keys
                ):
                    raise RuntimeError(
                        'autonomous critic_v2 load mismatch: '
                        f'missing={loaded.missing_keys} '
                        f'unexpected={loaded.unexpected_keys}'
                    )
                if adding_preflop_head:
                    with torch.no_grad():
                        model.preflop_policy_head.weight.copy_(
                            model.policy_head.weight
                        )
                        model.preflop_policy_head.bias.copy_(
                            model.policy_head.bias
                        )
                    print(
                        'Initialized separate preflop head from exact source '
                        'policy head during critic_v2 reset'
                    )
                if adding_postflop_adapter:
                    print(
                        'Initialized zero residual postflop policy adapter '
                        'during critic_v2 reset'
                    )
                if adding_position_adapter:
                    print(
                        'Initialized zero residual BB/SB position policy '
                        'adapters during critic_v2 reset'
                    )
                if adding_position_value_adapter:
                    print(
                        'Initialized zero residual BB/SB position value '
                        'adapters during critic_v2 reset'
                    )
                current = model.state_dict()
                changed_actor = [
                    name
                    for name in sorted(source_actor)
                    if not torch.equal(
                        current[name].detach().cpu(),
                        source_actor[name].detach().cpu(),
                    )
                ]
                if changed_actor:
                    raise RuntimeError(
                        'autonomous critic_v2 actor copy is not bitwise exact: '
                        f'{changed_actor[:5]}'
                    )
                print(
                    'Autonomous critic_v1->critic_v2 shared-actor-exact '
                    'migration PASS; behavior-neutral new adapters, fresh '
                    'optimizer and critic'
                )
            else:
                migration = migrate_v1_checkpoint_to_v2(
                    model=model, optimizer=optimizer, checkpoint=ckpt, device=device,
                )
                migration.update({
                    'source_checkpoint': str(Path(args.resume).resolve()),
                    'source_checkpoint_sha256': sha256_path(Path(args.resume)),
                    'preregistration_sha256': args.h1_preregistration_sha256.lower(),
                    'critic_init_seed': args.h1_critic_init_seed,
                    'effective_stack_divisor': args.h1_effective_stack_divisor,
                    'value_coef': args.value_coef,
                })
                migration_path = Path(args.h1_migration_report)
                migration_path.parent.mkdir(parents=True, exist_ok=True)
                with migration_path.open('x', encoding='utf-8', newline='\n') as handle:
                    json.dump(migration, handle, indent=2, sort_keys=True)
                    handle.write('\n')
                print('H1 critic_v1->critic_v2 actor/optimizer migration PASS')
        else:
            if source_critic_contract != args.critic_contract:
                raise RuntimeError(
                    f'critic contract mismatch source={source_critic_contract} target={args.critic_contract}'
                )
            source_has_preflop_head = (
                'preflop_policy_head.weight' in ckpt['model']
                and 'preflop_policy_head.bias' in ckpt['model']
            )
            adding_preflop_head = (
                args.separate_preflop_head and not source_has_preflop_head
            )
            source_has_postflop_adapter = (
                'postflop_policy_adapter.0.weight' in ckpt['model']
            )
            adding_postflop_adapter = (
                args.postflop_adapter_hidden > 0
                and not source_has_postflop_adapter
            )
            source_has_position_adapter = (
                'position_policy_adapters.0.0.weight' in ckpt['model']
            )
            adding_position_adapter = (
                args.position_adapter_hidden > 0
                and not source_has_position_adapter
            )
            source_has_position_value_adapter = (
                'position_value_adapters.0.0.weight' in ckpt['model']
            )
            adding_position_value_adapter = (
                args.position_value_adapter_hidden > 0
                and not source_has_position_value_adapter
            )
            if (
                adding_preflop_head
                or adding_postflop_adapter
                or adding_position_adapter
                or adding_position_value_adapter
            ):
                load_result = model.load_state_dict(ckpt['model'], strict=False)
                expected_missing = set()
                if adding_preflop_head:
                    expected_missing.update({
                        'preflop_policy_head.weight',
                        'preflop_policy_head.bias',
                    })
                if adding_postflop_adapter:
                    expected_missing.update({
                        'postflop_policy_adapter.0.weight',
                        'postflop_policy_adapter.0.bias',
                        'postflop_policy_adapter.2.weight',
                        'postflop_policy_adapter.2.bias',
                    })
                if adding_position_adapter:
                    expected_missing.update({
                        f'position_policy_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if adding_position_value_adapter:
                    expected_missing.update({
                        f'position_value_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if set(load_result.missing_keys) != expected_missing or load_result.unexpected_keys:
                    raise RuntimeError(
                        'unexpected state mismatch while adding policy adapters: '
                        f'missing={load_result.missing_keys}, '
                        f'unexpected={load_result.unexpected_keys}'
                    )
                if adding_preflop_head:
                    with torch.no_grad():
                        model.preflop_policy_head.weight.copy_(model.policy_head.weight)
                        model.preflop_policy_head.bias.copy_(model.policy_head.bias)
                    print('Initialized separate preflop head from exact source policy head')
                if adding_postflop_adapter:
                    print('Initialized zero residual postflop policy adapter')
                if adding_position_adapter:
                    print(
                        'Initialized zero residual BB/SB position policy '
                        'adapters'
                    )
                if adding_position_value_adapter:
                    print(
                        'Initialized zero residual BB/SB position value '
                        'adapters'
                    )
            else:
                model.load_state_dict(ckpt['model'])
            if not args.reset_optimizer:
                if (
                    adding_preflop_head
                    or adding_postflop_adapter
                    or adding_position_adapter
                    or adding_position_value_adapter
                ):
                    raise RuntimeError(
                        'adding a policy head/adapter requires --reset-optimizer'
                    )
                optimizer.load_state_dict(ckpt['optimizer'])
                print('Loaded checkpoint optimizer state')
            else:
                print('Optimizer reset (fresh Adam moments)')
        # Terminal EXP-W1 state is never imported into H1 authority.
        exp_w1_warmup_state = {
            'status': 'DISABLED', 'epochs': 0, 'at_iteration': 0,
            'report_path': None, 'report_sha256': None,
        }

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

    if fixed_opponent_active:
        pool = OpponentPool(
            k=len(fixed_opponent_paths),
            strategy='latest',
            history_limit=len(fixed_opponent_paths),
        )
        for fixed_path_text in fixed_opponent_paths:
            fixed_path = Path(fixed_path_text).resolve()
            if not fixed_path.is_file():
                raise FileNotFoundError(fixed_path)
            fixed_checkpoint = torch.load(
                fixed_path, map_location='cpu', weights_only=False
            )
            fixed_norm_layer = str(fixed_checkpoint.get('norm_layer', 'bn'))
            pool.add(
                fixed_checkpoint['model'],
                hands=int(fixed_checkpoint.get('total_hands') or 0),
                iteration=fixed_checkpoint.get('iteration'),
                selection_loss=0.0,
                score_components={
                    'kind': 'fixed_external_opponent',
                    'checkpoint': str(fixed_path),
                    'checkpoint_sha256': sha256_path(fixed_path),
                    'norm_layer': fixed_norm_layer,
                },
            )
            print(
                f'Fixed opponent loaded: {fixed_path} '
                f'(norm={fixed_norm_layer})'
            )

    reference_policy = None
    if args.source_policy_kl_coef > 0.0:
        reference_policy = copy.deepcopy(model).to(device)
        reference_policy.eval()
        for parameter in reference_policy.parameters():
            parameter.requires_grad_(False)
        print(
            f'Source-policy KL enabled: coef={args.source_policy_kl_coef:g} '
            f'(frozen exact resume actor)'
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
                'action_space_version': (
                    '9slot_pot_fraction_v2'
                    if args.env_version == 'v55pfv2v4obs'
                    else (
                        '9slot_preflop_pot_fraction_v2'
                        if args.env_version == 'v55preflopv2v4obs'
                        else '9slot_v5'
                    )
                ),
                'raise_action_mapping': (
                    'pot_fraction_v2'
                    if args.env_version == 'v55pfv2v4obs'
                    else (
                        'preflop_pot_fraction_v2'
                        if args.env_version == 'v55preflopv2v4obs'
                        else 'legacy_total_over_pot'
                    )
                ),
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
    h1_metrics_jsonl_path = run_dir / 'h1_training_metrics.jsonl'

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
                      args.fixed_training_deal_stream,
                      args.showdown_ev_value_targets,
                      args.showdown_ev_value_target_max_runouts,
                      args.showdown_ev_value_target_seed,
                      args.hero_preflop_strategy),
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
                      args.fixed_training_deal_stream,
                      args.showdown_ev_value_targets,
                      args.showdown_ev_value_target_max_runouts,
                      args.showdown_ev_value_target_seed,
                      args.hero_preflop_strategy),
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
    print(
        f'PPO: eps_clip=0.2, delta1={args.delta1}, gamma={args.gamma}, '
        f'gae_lambda={args.gae_lambda}'
    )
    print(
        f'Hero preflop: strategy={args.hero_preflop_strategy} '
        f'teacher_coef={args.preflop_teacher_coef:g} '
        f'policy_postflop_only={args.policy_postflop_only} '
        f'policy_position_only={args.policy_position_only}'
    )
    print(
        f'EXP-003 variance reduction: mirror_self_play_deals={args.mirror_self_play_deals} '
        f'allin_runout_ev={args.allin_runout_ev} '
        f'allin_runout_ev_max_runouts={args.allin_runout_ev_max_runouts}'
    )
    print(
        f'H2 critic targets: enabled={args.showdown_ev_value_targets} '
        f'max_runouts={args.showdown_ev_value_target_max_runouts} '
        f'target_seed={args.showdown_ev_value_target_seed} actor_reward_and_gae_unchanged=True'
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
            snapshot_state = snap['state_dict']
            recorded_norm = (snap.get('score_components') or {}).get(
                'norm_layer'
            )
            if recorded_norm in {'bn', 'gn'}:
                opponent_norm = recorded_norm
            else:
                # Historical pools can contain BN opponents inside a GN hero
                # checkpoint.  BatchNorm is unambiguously identified by its
                # running-stat buffers; GroupNorm has no such state.
                opponent_norm = (
                    'bn'
                    if any(
                        key.endswith('running_mean')
                        or key.endswith('running_var')
                        for key in snapshot_state
                    )
                    else args.norm_layer
                )
            m = AlphaHoldemNet(
                num_actions=NUM_ACTIONS,
                norm_layer=opponent_norm,
                critic_contract=(
                    CRITIC_V2
                    if 'value_head.0.weight' in snapshot_state
                    else CRITIC_V1
                ),
                separate_preflop_head=(
                    'preflop_policy_head.weight' in snapshot_state
                ),
                postflop_adapter_hidden=(
                    int(snapshot_state['postflop_policy_adapter.0.weight'].shape[0])
                    if 'postflop_policy_adapter.0.weight' in snapshot_state
                    else 0
                ),
                position_adapter_hidden=(
                    int(
                        snapshot_state[
                            'position_policy_adapters.0.0.weight'
                        ].shape[0]
                    )
                    if 'position_policy_adapters.0.0.weight' in snapshot_state
                    else 0
                ),
                position_value_adapter_hidden=(
                    int(
                        snapshot_state[
                            'position_value_adapters.0.0.weight'
                        ].shape[0]
                    )
                    if 'position_value_adapters.0.0.weight' in snapshot_state
                    else 0
                ),
            ).to(device)
            m(dc, da, de)
            m.load_state_dict(snapshot_state)
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
        lg002_assignment = None
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
            if lg002_recovery_active:
                selected_local_index, lg002_assignment = lg002_select_opponent(
                    args.lg002_recovery_arm, int(iteration) + 1, pool.snapshots,
                )
                assigned_np[:] = selected_local_index
            elif random.random() < args.self_play_fraction:
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
            if lg002_recovery_active:
                record = lg002_enrich_provenance_record(record, lg002_assignment)
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

    if (
        args.separate_preflop_head
        and args.preflop_head_lr > 0.0
        and len(optimizer.param_groups) == 2
    ):
        optimizer_group_base_lrs = [args.lr, args.preflop_head_lr]
    else:
        optimizer_group_base_lrs = [
            args.lr for _ in optimizer.param_groups
        ]

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
                    hero_value_output_scale=(
                        args.h1_effective_stack_divisor
                        if args.critic_contract == CRITIC_V2 else 1.0
                    ),
                    hero_policy_mode=args.hero_policy_mode,
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
                    new_group_lrs = linear_decay_group_lrs(
                        progress,
                        optimizer_group_base_lrs,
                    )
                    for pg, new_lr in zip(
                        optimizer.param_groups,
                        new_group_lrs,
                    ):
                        pg['lr'] = new_lr

                t1 = time.time()
                if (
                    args.exp_w1_value_warmup_epochs > 0
                    and exp_w1_warmup_state.get('status') == 'PENDING'
                ):
                    if iteration != args.exp_w1_value_warmup_at_iteration:
                        raise RuntimeError(
                            f'EXP-W1 warmup missed exact iteration: live={iteration} '
                            f'locked={args.exp_w1_value_warmup_at_iteration}'
                        )
                    warmup_result = run_value_head_warmup(
                        model=model,
                        optimizer=optimizer,
                        transitions=iter_transitions,
                        device=device,
                        compute_gae_fn=compute_gae,
                        epochs=args.exp_w1_value_warmup_epochs,
                        mini_batch_size=args.mini_batch_size,
                        gamma=args.gamma,
                        heldout_fraction=args.exp_w1_value_warmup_heldout_fraction,
                        min_relative_mse_reduction=args.exp_w1_value_warmup_min_relative_mse_reduction,
                        split_seed=args.exp_w1_value_warmup_split_seed,
                    )
                    warmup_result['run_id'] = args.run_id
                    warmup_result['iteration'] = int(iteration)
                    warmup_result['starting_hands'] = int(total_hands)
                    report_path = Path(args.exp_w1_value_warmup_report)
                    report_sha = write_immutable_report(report_path, warmup_result)
                    exp_w1_warmup_state = dict(warmup_result)
                    exp_w1_warmup_state.update({'report_path': str(report_path), 'report_sha256': report_sha})
                    if warmup_result['status'] != 'PASS':
                        raise RuntimeError('EXP-W1 value-head warmup gate FAIL; refusing PPO continuation')
                mix = action_mix(iter_transitions)
                phase_mix = action_mix_by_phase(iter_transitions)
                stats = trinal_clip_ppo_update(
                    model, optimizer, iter_transitions, device,
                    epochs=args.ppo_epochs,
                    mini_batch_size=args.mini_batch_size,
                    delta1=args.delta1,
                    gamma=args.gamma,
                    gae_lambda=args.gae_lambda,
                    critic_contract=args.critic_contract,
                    effective_stack_divisor=args.h1_effective_stack_divisor,
                    value_coef=args.value_coef,
                    critic_head_only_gradient=args.critic_head_only_gradient,
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
                    target_kl=args.ppo_target_kl,
                    reference_policy=reference_policy,
                    reference_policy_kl_coef=args.source_policy_kl_coef,
                    policy_postflop_only=args.policy_postflop_only,
                    policy_position_only=args.policy_position_only,
                    preflop_teacher_coef=args.preflop_teacher_coef,
                    value_head_catchup=args.h8_value_head_catchup_after_kl_stop,
                    value_head_catchup_loss=(
                        args.h18_catchup_loss
                        if args.h18_window_arm != 'none'
                        else args.h17_catchup_loss
                        if args.h17_window_arm != 'none'
                        else args.h16_catchup_loss
                        if args.h16_window_arm != 'none'
                        else args.h15_catchup_loss
                        if args.h15_window_arm != 'none'
                        else args.h14_catchup_loss
                        if args.h14_window_arm != 'none'
                        else args.h13_catchup_loss
                        if args.h13_window_arm != 'none'
                        else args.h12_catchup_loss
                        if args.h12_window_arm != 'none'
                        else args.h11_catchup_loss
                        if args.h11_window_arm != 'none'
                        else args.h10_catchup_loss
                        if args.h10_window_arm != 'none'
                        else args.h9_catchup_loss
                    ),
                    value_head_catchup_smooth_l1_beta=(
                        args.h18_catchup_smooth_l1_beta
                        if args.h18_window_arm != 'none'
                        else args.h17_catchup_smooth_l1_beta
                        if args.h17_window_arm != 'none'
                        else args.h16_catchup_smooth_l1_beta
                        if args.h16_window_arm != 'none'
                        else args.h15_catchup_smooth_l1_beta
                        if args.h15_window_arm != 'none'
                        else args.h14_catchup_smooth_l1_beta
                        if args.h14_window_arm != 'none'
                        else args.h13_catchup_smooth_l1_beta
                        if args.h13_window_arm != 'none'
                        else args.h12_catchup_smooth_l1_beta
                        if args.h12_window_arm != 'none'
                        else args.h11_catchup_smooth_l1_beta
                        if args.h11_window_arm != 'none'
                        else args.h10_catchup_smooth_l1_beta
                        if args.h10_window_arm != 'none'
                        else args.h9_catchup_smooth_l1_beta
                    ),
                )
                ppo_time = time.time() - t1
                # Keep loss-kbest in raw-BB-equivalent units.
                selection_stats = dict(stats)
                selection_stats['value_loss'] = stats['value_loss_raw_bb_equivalent']
                selection_loss = selection_loss_from_stats(selection_stats)
                score_components = {
                    'policy_loss': float(stats['policy_loss']),
                    'value_loss': float(stats['value_loss_raw_bb_equivalent']),
                    'normalized_value_loss': float(stats['value_loss']),
                    'critic_contract': args.critic_contract,
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
                    'preflop_teacher_loss': float(stats.get('preflop_teacher_loss', 0.0)),
                    'preflop_teacher_coef': float(stats.get('preflop_teacher_coef', 0.0)),
                    'formula': f'policy_loss + {args.value_coef:g}*log1p(value_loss)',
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
                    f"vloss={stats['value_loss']:.6f} "
                    f"vloss_bb2={stats['value_loss_raw_bb_equivalent']:.4f} "
                    f"ent={stats['entropy']:.4f} "
                    f"kl={stats.get('approx_kl', 0.0):.4f} "
                    f"refkl={stats.get('reference_policy_kl', 0.0):.4f} "
                    f"pft={stats.get('preflop_teacher_loss', 0.0):.4f} "
                    f"ep={stats.get('ppo_epochs_completed', args.ppo_epochs)}/{args.ppo_epochs} "
                    f"klstop={int(bool(stats.get('kl_early_stop_triggered', False)))} "
                    f"vhcatch={stats.get('value_head_catchup_epochs', 0)} "
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
                with h1_metrics_jsonl_path.open('a', encoding='utf-8', newline='\n') as f:
                    f.write(json.dumps({
                        'schema_version': 'v5.hybrid.h1.training_metric.v1',
                        'recorded_at': datetime.now(timezone.utc).isoformat(),
                        'run_id': args.run_id, 'iteration': iteration, 'hands': total_hands,
                        'hands_per_second': h_per_s, 'entropy': float(stats['entropy']),
                        'reward_per_hand': float(avg_rew),
                        'reward_window_100': float(rew100),
                        'terminal_trajectories': int(iter_terminal_trajectories),
                        'critic_contract': args.critic_contract, 'value_coef': args.value_coef,
                        'approx_kl': float(stats.get('approx_kl', 0.0)),
                        'reference_policy_kl': float(stats.get('reference_policy_kl', 0.0)),
                        'reference_policy_kl_coef': float(
                            stats.get('reference_policy_kl_coef', args.source_policy_kl_coef)
                        ),
                        'clip_frac': float(stats.get('clip_frac', 0.0)),
                        'ppo_epochs_completed': int(stats.get('ppo_epochs_completed', args.ppo_epochs)),
                        'kl_early_stop_triggered': bool(stats.get('kl_early_stop_triggered', False)),
                        'kl_early_stop_epoch': int(stats.get('kl_early_stop_epoch', 0)),
                        'ppo_target_kl': float(stats.get('ppo_target_kl', args.ppo_target_kl)),
                        'value_head_catchup_enabled': bool(stats.get('value_head_catchup_enabled', False)),
                        'value_head_catchup_loss_mode': stats.get('value_head_catchup_loss_mode', 'mse'),
                        'value_head_catchup_smooth_l1_beta': stats.get('value_head_catchup_smooth_l1_beta', 1.0),
                        'value_head_catchup_epochs': int(stats.get('value_head_catchup_epochs', 0)),
                        'value_head_catchup_minibatches': int(stats.get('value_head_catchup_minibatches', 0)),
                        'value_head_catchup_loss': float(stats.get('value_head_catchup_loss', 0.0)),
                        'value_head_catchup_actor_state_unchanged': bool(
                            stats.get('value_head_catchup_actor_state_unchanged', True)
                        ),
                    }, sort_keys=True) + '\n')
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
                        'value_loss_raw_bb_equivalent': stats['value_loss_raw_bb_equivalent'],
                        'critic_contract': args.critic_contract,
                        'effective_stack_divisor': stats['effective_stack_divisor'],
                        'value_coef': args.value_coef,
                        'reference_policy_kl': stats.get('reference_policy_kl', 0.0),
                        'reference_policy_kl_coef': stats.get(
                            'reference_policy_kl_coef', args.source_policy_kl_coef
                        ),
                        'h2_critic_target_override_rows': stats.get('h2_critic_target_override_rows', 0),
                        'h2_critic_target_override_fraction': stats.get('h2_critic_target_override_fraction', 0.0),
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
                        'ppo_epochs_completed': stats.get('ppo_epochs_completed', args.ppo_epochs),
                        'kl_early_stop_triggered': stats.get('kl_early_stop_triggered', False),
                        'kl_early_stop_epoch': stats.get('kl_early_stop_epoch', 0),
                        'ppo_target_kl': stats.get('ppo_target_kl', args.ppo_target_kl),
                        'value_head_catchup_enabled': stats.get('value_head_catchup_enabled', False),
                        'value_head_catchup_loss_mode': stats.get('value_head_catchup_loss_mode', 'mse'),
                        'value_head_catchup_smooth_l1_beta': stats.get('value_head_catchup_smooth_l1_beta', 1.0),
                        'value_head_catchup_epochs': stats.get('value_head_catchup_epochs', 0),
                        'value_head_catchup_minibatches': stats.get('value_head_catchup_minibatches', 0),
                        'value_head_catchup_loss': stats.get('value_head_catchup_loss', 0.0),
                        'value_head_catchup_actor_state_unchanged': stats.get(
                            'value_head_catchup_actor_state_unchanged', True
                        ),
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
                if (
                    iteration % args.snapshot_every == 0
                    and not lg002_recovery_active
                    and not fixed_opponent_active
                ):
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
                elif iteration % args.snapshot_every == 0:
                    reason = (
                        'fixed external opponent'
                        if fixed_opponent_active
                        else 'LG002 frozen membership'
                    )
                    print(f'  [Pool] {reason}: snapshot addition disabled')

                # Save
                if iteration % args.save_interval == 0:
                    torch.save(checkpoint_payload(), args.out)
                    print(f'  [Save] {args.out} ({total_hands:,} hands)')
                if (
                    args.archive_checkpoint_every > 0
                    and iteration % args.archive_checkpoint_every == 0
                ):
                    archive_dir = run_dir / 'checkpoints'
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    archive_path = archive_dir / (
                        f'checkpoint_iter{iteration:06d}_hands{total_hands:012d}.pt'
                    )
                    torch.save(checkpoint_payload(), archive_path)
                    print(f'  [Archive] {archive_path}')

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
        time.sleep(0.25)
        shutdown_deadline = time.monotonic() + 5.0
        for p in procs:
            p.join(timeout=max(0.0, shutdown_deadline - time.monotonic()))
        for p in procs:
            if p.is_alive():
                p.terminate()
        for p in procs:
            p.join(timeout=1.0)
        for shm in (obs_shm, result_shm, status_shm, assigned_shm, request_shm):
            shm.close()
            shm.unlink()

    torch.save(checkpoint_payload(), args.out)
    write_manifest('finished', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))
    print(f'Done! {total_hands:,} hands. Saved to {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
