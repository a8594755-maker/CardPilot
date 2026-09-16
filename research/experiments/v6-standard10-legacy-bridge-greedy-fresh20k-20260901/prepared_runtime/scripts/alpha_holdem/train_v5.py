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
   an ablation and opt-in elo-kbest runs deterministic mirrored survivor
   tournaments matching the paper's competition/ELO selection mechanism.
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
from alpha_holdem.train_mp3_hybrid_h1 import (
    compute_gae,
    temperature_policy_distribution,
    trinal_clip_ppo_update,
)
try:
    from counterfactual_q_replay import (
        decayed_replay_coefficient,
        load_counterfactual_q_replay,
        replay_checkpoint_state,
        restore_replay_progress,
        validate_replay_metadata_contract,
        validate_replay_training_config,
    )
except ModuleNotFoundError:
    from scripts.alpha_holdem.counterfactual_q_replay import (
        decayed_replay_coefficient,
        load_counterfactual_q_replay,
        replay_checkpoint_state,
        restore_replay_progress,
        validate_replay_metadata_contract,
        validate_replay_training_config,
    )
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

ACTOR_EMA_PREFIXES = ('policy_head.', 'preflop_policy_head.')

PROCEDURAL_OPPONENT_VERSION = 'per_hand_style_v1'
PROCEDURAL_OPPONENT_PROFILES = (
    # name, looseness, aggression, bluff rate, preferred raise slot, size spread
    ('tight_passive', 0.24, 0.16, 0.03, 3.0, 0.85),
    ('loose_passive', 0.82, 0.18, 0.07, 3.0, 1.05),
    ('tight_aggressive', 0.30, 0.74, 0.11, 6.0, 1.10),
    ('loose_aggressive', 0.78, 0.78, 0.20, 5.0, 1.35),
    ('small_ball', 0.62, 0.54, 0.14, 2.0, 0.70),
    ('polarized', 0.40, 0.84, 0.31, 7.0, 1.15),
    ('pressure', 0.70, 0.90, 0.27, 8.0, 1.35),
    ('balanced_random', 0.52, 0.50, 0.13, 4.0, 1.80),
)


def actor_ema_parameter_names(model: nn.Module) -> tuple[str, ...]:
    """Return the deployment actor-head parameters tracked by terminal EMA."""
    return tuple(
        name
        for name, _ in model.named_parameters()
        if name.startswith(ACTOR_EMA_PREFIXES)
    )


def initialize_actor_ema(model: nn.Module) -> dict[str, torch.Tensor]:
    """Create a CPU, bitwise-exact snapshot of the current actor heads."""
    names = actor_ema_parameter_names(model)
    if not names:
        raise ValueError('actor EMA requires actor-head parameters')
    parameters = dict(model.named_parameters())
    return {
        name: parameters[name].detach().cpu().clone()
        for name in names
    }


def update_actor_ema(
    model: nn.Module,
    state: dict[str, torch.Tensor],
    decay: float,
) -> None:
    """Apply one post-PPO exponential moving-average update in place."""
    if not 0.0 <= float(decay) < 1.0:
        raise ValueError('actor EMA decay must be in [0, 1)')
    names = actor_ema_parameter_names(model)
    if set(state) != set(names):
        raise ValueError('actor EMA state keys do not match model actor heads')
    parameters = dict(model.named_parameters())
    with torch.no_grad():
        for name in names:
            current = parameters[name].detach().cpu()
            if state[name].shape != current.shape:
                raise ValueError(f'actor EMA shape mismatch: {name}')
            state[name].mul_(decay).add_(current, alpha=1.0 - decay)


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


def procedural_opponent_hand_seed(worker_seed: int, hand_index: int) -> int:
    """Stable independent RNG seed for one worker-local procedural hand."""
    payload = (
        f'{PROCEDURAL_OPPONENT_VERSION}:{int(worker_seed)}:{int(hand_index)}'
    ).encode('ascii')
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big')


def sample_procedural_opponent_style(rng: random.Random) -> dict:
    """Sample a continuous style around one of eight broad poker archetypes."""
    profile_id = int(rng.randrange(len(PROCEDURAL_OPPONENT_PROFILES)))
    name, loose, aggressive, bluff, size_center, size_spread = (
        PROCEDURAL_OPPONENT_PROFILES[profile_id]
    )

    def clipped(value, low=0.0, high=1.0):
        return min(high, max(low, float(value)))

    return {
        'profile_id': profile_id,
        'profile_name': name,
        'looseness': clipped(loose + rng.uniform(-0.09, 0.09)),
        'aggression': clipped(aggressive + rng.uniform(-0.09, 0.09)),
        'bluff_rate': clipped(bluff + rng.uniform(-0.04, 0.04)),
        'raise_slot_center': clipped(
            size_center + rng.uniform(-0.65, 0.65), 2.0, 8.0
        ),
        'raise_slot_spread': clipped(
            size_spread + rng.uniform(-0.20, 0.20), 0.45, 2.25
        ),
    }


def procedural_preflop_strength(hole_cards) -> float:
    """Cheap monotone private-card signal; it is not a solver or benchmark rule."""
    c0, c1 = (int(card) for card in hole_cards)
    r0, r1 = c0 // 4, c1 // 4
    high, low = max(r0, r1), min(r0, r1)
    if high == low:
        score = 0.57 + 0.37 * (high / 12.0)
    else:
        score = 0.17 + 0.38 * (high / 12.0) + 0.18 * (low / 12.0)
        if c0 % 4 == c1 % 4:
            score += 0.08
        gap = high - low
        if gap <= 1:
            score += 0.07
        elif gap == 2:
            score += 0.035
    return min(0.98, max(0.02, float(score)))


def procedural_public_equity_signal(state, player: int, rng: random.Random,
                                    samples: int = 8) -> float:
    """Estimate equity using only the acting player's cards and public board."""
    hole = tuple(int(card) for card in state.hole_cards[int(player)])
    board = [int(card) for card in state.board]
    if not board:
        return procedural_preflop_strength(hole)
    from deep_cfr.hand_eval import compare_hands

    used = set(hole) | set(board)
    unseen = [card for card in range(52) if card not in used]
    runout_count = 5 - len(board)
    wins = 0.0
    for _ in range(max(1, int(samples))):
        draw = rng.sample(unseen, 2 + runout_count)
        opponent_hole = (draw[0], draw[1])
        complete_board = board + draw[2:]
        comparison = compare_hands(hole, opponent_hole, complete_board)
        wins += 1.0 if comparison > 0 else (0.5 if comparison == 0 else 0.0)
    return wins / max(1, int(samples))


def procedural_opponent_action(env, player: int, legal_mask, style: dict,
                               rng: random.Random, equity_samples: int = 8) -> int:
    """Sample one legal action from a per-hand style and visible-card signal."""
    legal_mask = np.asarray(legal_mask, dtype=np.float64).reshape(-1)
    legal = np.flatnonzero(legal_mask > 0)
    if len(legal) == 0:
        raise ValueError('procedural opponent received an empty legal mask')
    if len(legal) == 1:
        return int(legal[0])

    strength = procedural_public_equity_signal(
        env.state, player, rng, samples=equity_samples
    )
    state = env.state
    committed = state.street_committed
    to_call = max(
        float(committed[1 - int(player)] - committed[int(player)]), 0.0
    )
    pot_odds = to_call / max(float(state.pot) + to_call, 1e-9)
    facing_bet = bool(legal_mask[0] > 0)
    looseness = float(style['looseness'])
    aggression = float(style['aggression'])

    weights = np.zeros(len(legal_mask), dtype=np.float64)
    if facing_bet:
        fold_threshold = pot_odds + 0.22 * (0.5 - looseness)
        weights[0] = math.exp(min(4.0, max(-4.0, 7.0 * (fold_threshold - strength))))
    if legal_mask[1] > 0:
        call_edge = strength - pot_odds + 0.20 * (looseness - 0.5)
        weights[1] = math.exp(min(3.0, max(-3.0, 2.5 * call_edge))) * (
            0.55 + 1.25 * (1.0 - aggression)
        )

    bluff = rng.random() < float(style['bluff_rate']) * max(0.0, 1.0 - strength)
    value_pressure = max(0.0, strength - 0.48) * 2.4
    raise_mass = aggression * (0.10 + value_pressure + (0.95 if bluff else 0.0))
    if facing_bet and strength < pot_odds and not bluff:
        raise_mass *= 0.35
    center = float(style['raise_slot_center'])
    spread = float(style['raise_slot_spread'])
    for slot in range(2, len(legal_mask)):
        if legal_mask[slot] > 0:
            distance = (float(slot) - center) / spread
            weights[slot] = max(1e-4, raise_mass * math.exp(-0.5 * distance * distance))

    # Every legal action retains a small exploration floor. This keeps the
    # population broad without injecting noise into the trainable hero policy.
    weights[legal] += 0.01
    total = float(weights[legal].sum())
    if not math.isfinite(total) or total <= 0.0:
        return int(legal[0])
    draw = rng.random() * total
    cumulative = 0.0
    for slot in legal:
        cumulative += float(weights[int(slot)])
        if draw <= cumulative:
            return int(slot)
    return int(legal[-1])


def procedural_opponent_metrics_template() -> dict:
    return {
        'hands': 0,
        'decisions': 0,
        'inference_bypasses': 0,
        'style_counts': [0 for _ in PROCEDURAL_OPPONENT_PROFILES],
        'action_counts': [0 for _ in range(NUM_ACTIONS)],
    }


def procedural_opponent_metrics_nonzero(metrics: dict) -> bool:
    return int(metrics.get('hands', 0)) > 0 or int(metrics.get('decisions', 0)) > 0


def procedural_opponent_metrics_add(dst: dict, src: dict) -> None:
    for key in ('hands', 'decisions', 'inference_bypasses'):
        dst[key] += int(src.get(key, 0) or 0)
    for key in ('style_counts', 'action_counts'):
        values = list(src.get(key) or [])
        if len(values) != len(dst[key]):
            raise ValueError(f'procedural metric {key} has the wrong length')
        for index, value in enumerate(values):
            dst[key][index] += int(value)


def encode_opponent_private_cards(state, *, player: int) -> np.ndarray:
    """Training-only one-hot opponent hole cards for a centralized critic."""
    if int(player) not in (0, 1):
        raise ValueError('player must be 0 or 1')
    if state is None or state.hole_cards[1 - int(player)] is None:
        raise ValueError('centralized critic requires dealt opponent cards')
    result = np.zeros(52, dtype=np.float32)
    cards = [int(card) for card in state.hole_cards[1 - int(player)]]
    if len(cards) != 2 or len(set(cards)) != 2 or any(
        card < 0 or card >= 52 for card in cards
    ):
        raise ValueError('invalid opponent private cards')
    result[cards] = 1.0
    return result


def position_adapter_trainable_prefixes(
    training_seat: str,
    include_action_q: bool = False,
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
    prefixes = actor_prefixes + (
        'value_head.',
        'position_value_adapters.',
    )
    if include_action_q:
        prefixes = prefixes + ('action_q_head.',)
    return prefixes


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
                                     rng=None,
                                     pool_weights=None):
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

    if pool_weights is not None:
        weights = [float(value) for value in pool_weights]
        if len(weights) != pool_size:
            raise ValueError('pool_weights length must equal pool_size')
        if any(not math.isfinite(value) or value < 0.0 for value in weights):
            raise ValueError('pool_weights must be finite and nonnegative')
        if sum(weights) <= 0.0:
            raise ValueError('pool_weights must have positive total mass')
        pool_opponents = rng.choices(
            range(pool_size),
            weights=weights,
            k=len(pool_groups),
        )
    elif len(pool_groups) <= pool_size:
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


def adaptive_hardness_weights(
    mean_rewards: list[float],
    temperature_bb: float,
    minimum_probability: float,
) -> list[float]:
    """Convert hero rewards into a floor-mixed hard-opponent distribution."""
    if not mean_rewards:
        return []
    if temperature_bb <= 0.0:
        raise ValueError('temperature_bb must be positive')
    count = len(mean_rewards)
    if minimum_probability < 0.0 or minimum_probability * count >= 1.0:
        raise ValueError(
            'minimum_probability must be nonnegative and below 1/pool_size'
        )
    rewards = np.asarray(mean_rewards, dtype=np.float64)
    if not np.isfinite(rewards).all():
        raise ValueError('mean_rewards must be finite')
    logits = -rewards / float(temperature_bb)
    logits -= float(logits.max())
    softmax = np.exp(logits)
    softmax /= float(softmax.sum())
    residual = 1.0 - minimum_probability * count
    probabilities = minimum_probability + residual * softmax
    probabilities /= float(probabilities.sum())
    return [float(value) for value in probabilities]


def reconcile_adaptive_league_state(
    old_snapshot_ids,
    new_snapshot_ids,
    mean_rewards,
    observations,
):
    """Carry adaptive league evidence across dynamic pool membership changes.

    Local pool indices are not stable under K-best pruning.  Snapshot ids are,
    so retained opponents keep their EMA/observation state while newly admitted
    snapshots start unobserved at neutral reward.  Removed snapshots disappear.
    Sampling weights are deliberately recomputed by the caller from the returned
    state instead of being copied by local index.
    """
    old_ids = [int(value) for value in old_snapshot_ids]
    new_ids = [int(value) for value in new_snapshot_ids]
    if len(old_ids) != len(set(old_ids)) or len(new_ids) != len(set(new_ids)):
        raise ValueError('snapshot ids must be unique')
    if len(mean_rewards) != len(old_ids) or len(observations) != len(old_ids):
        raise ValueError('adaptive state length must match old snapshot ids')
    prior = {
        snapshot_id: (float(mean_rewards[index]), int(observations[index]))
        for index, snapshot_id in enumerate(old_ids)
    }
    next_rewards = []
    next_observations = []
    for snapshot_id in new_ids:
        reward, count = prior.get(snapshot_id, (0.0, 0))
        if not math.isfinite(reward) or count < 0:
            raise ValueError('adaptive state must be finite and nonnegative')
        next_rewards.append(float(reward))
        next_observations.append(int(count))
    return next_rewards, next_observations


def build_assignment_provenance_record(*, run_id: str, applies_to_iteration: int,
                                       total_hands: int, assignment_mode: str,
                                       assignments, pool_snapshots,
                                       group_metadata=None,
                                       pool_sampling_weights=None,
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
    if pool_sampling_weights is not None:
        weights = [float(value) for value in pool_sampling_weights]
        if len(weights) != len(refs):
            raise ValueError('pool sampling weights must match pool size')
        if any(not math.isfinite(value) or value < 0.0 for value in weights):
            raise ValueError('pool sampling weights must be finite and nonnegative')
        if sum(weights) <= 0.0:
            raise ValueError('pool sampling weights must have positive total mass')
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
        'pool_sampling_weights': (
            [float(value) for value in pool_sampling_weights]
            if pool_sampling_weights is not None
            else None
        ),
        'workers': workers,
        'group_metadata': group_metadata,
        'previous_record_sha256': previous_record_sha256,
    }
    canonical = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    record['record_sha256'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return record


def restore_group_assignment_rng_from_evidence(
    provenance_records,
    metric_records,
    *,
    rng,
    seed: int,
    worker_count: int,
    pool_size: int,
    group_count: int,
    self_play_fraction: float,
    checkpoint_iteration: int,
    checkpoint_total_hands: int,
    pool_snapshot_ids=None,
):
    """Rebuild assignment RNG state and recover an already-recorded next assignment.

    The per-group assignment routine consumes a deterministic number of Python
    RNG draws. Adaptive weights for assignment N are recorded in metric N-1,
    so the complete provenance + metric chain can reproduce every historical
    assignment exactly. This avoids both duplicating the pending provenance
    row and restarting the assignment stream after a process interruption.
    """
    if not provenance_records:
        raise ValueError('assignment provenance is empty')
    metrics_by_iteration = {
        int(row['iteration']): row
        for row in metric_records
        if 'iteration' in row
    }
    # Older adaptive-league provenance did not always serialize the explicit
    # weights for assignment 1.  Those records used weighted ``choices`` with
    # a uniform initial distribution.  Non-adaptive fixed pools, however, use
    # the native uniform branch in build_group_opponent_assignments (sample
    # without replacement when possible, otherwise randrange).  Treating a
    # null weight field as uniform weighted choices changes RNG consumption
    # and makes valid non-adaptive evidence impossible to replay.
    legacy_adaptive_evidence = any(
        bool(row.get('adaptive_opponent_league'))
        for row in metric_records
    )
    rng.seed(int(seed))
    previous_sha = None
    expected_iteration = 1
    tail_assignments = None
    for record in provenance_records:
        applies_to = int(record.get('applies_to_iteration', -1))
        if applies_to != expected_iteration:
            raise ValueError(
                f'assignment provenance is not contiguous: expected '
                f'{expected_iteration}, got {applies_to}'
            )
        if record.get('previous_record_sha256') != previous_sha:
            raise ValueError(
                f'assignment provenance hash link mismatch at {applies_to}'
            )
        claimed_sha = str(record.get('record_sha256') or '')
        canonical_record = dict(record)
        canonical_record.pop('record_sha256', None)
        canonical = json.dumps(
            canonical_record,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
        actual_sha = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        if claimed_sha != actual_sha:
            raise ValueError(
                f'assignment provenance record hash mismatch at {applies_to}'
            )
        if int(record.get('worker_count', -1)) != int(worker_count):
            raise ValueError('assignment provenance worker count mismatch')
        record_pool_size = int(record.get('pool_size', -1))
        snapshot_refs = record.get('pool_snapshot_refs') or []
        if record_pool_size <= 0 or len(snapshot_refs) != record_pool_size:
            raise ValueError(
                f'assignment provenance pool membership invalid at {applies_to}'
            )
        snapshot_ids = [int(row['snapshot_id']) for row in snapshot_refs]
        if len(snapshot_ids) != len(set(snapshot_ids)):
            raise ValueError(
                f'assignment provenance snapshot ids duplicate at {applies_to}'
            )
        workers = record.get('workers') or []
        if [int(row.get('worker_id', -1)) for row in workers] != list(
            range(int(worker_count))
        ):
            raise ValueError(
                f'assignment provenance worker ordering mismatch at {applies_to}'
            )
        recorded_weights = record.get('pool_sampling_weights')
        if recorded_weights is not None:
            weights = [float(value) for value in recorded_weights]
            if len(weights) != record_pool_size:
                raise ValueError(
                    f'assignment provenance weights incomplete at {applies_to}'
                )
        elif not legacy_adaptive_evidence:
            weights = None
        elif applies_to == 1:
            weights = [
                1.0 / record_pool_size for _ in range(record_pool_size)
            ]
        else:
            prior_metric = metrics_by_iteration.get(applies_to - 1)
            if prior_metric is None:
                raise ValueError(
                    f'missing training metric for assignment {applies_to}'
                )
            league_rows = prior_metric.get('adaptive_opponent_league') or []
            league_by_id = {
                int(row['opponent_id']): row for row in league_rows
            }
            if set(league_by_id) != set(range(record_pool_size)):
                raise ValueError(
                    f'adaptive league weights incomplete before assignment '
                    f'{applies_to}'
                )
            weights = [
                float(league_by_id[index]['next_sampling_probability'])
                for index in range(record_pool_size)
            ]
        generated, _ = build_group_opponent_assignments(
            worker_count=worker_count,
            pool_size=record_pool_size,
            group_count=group_count,
            self_play_fraction=self_play_fraction,
            rng=rng,
            pool_weights=weights,
        )
        recorded = [
            int(row['opponent']['local_index']) for row in workers
        ]
        generated_list = (
            generated.tolist()
            if hasattr(generated, 'tolist')
            else list(generated)
        )
        if generated_list != recorded:
            raise ValueError(
                f'assignment RNG replay mismatch at iteration {applies_to}'
            )
        tail_assignments = recorded
        previous_sha = claimed_sha
        expected_iteration += 1

    tail = provenance_records[-1]
    tail_iteration = int(tail['applies_to_iteration'])
    if tail_iteration not in {
        int(checkpoint_iteration),
        int(checkpoint_iteration) + 1,
    }:
        raise ValueError(
            f'assignment provenance tail {tail_iteration} is incompatible '
            f'with checkpoint iteration {checkpoint_iteration}'
        )
    pending = None
    if tail_iteration == int(checkpoint_iteration) + 1:
        # A pending assignment was generated after the checkpoint boundary and
        # will be reused verbatim, so it must address the checkpoint's current
        # post-snapshot pool exactly. A consumed tail at checkpoint_iteration
        # may legitimately describe the pre-snapshot pool used by that update.
        if int(tail.get('pool_size', -1)) != int(pool_size):
            raise ValueError('assignment provenance tail pool size mismatch')
        if pool_snapshot_ids is not None:
            tail_ids = [
                int(row['snapshot_id'])
                for row in (tail.get('pool_snapshot_refs') or [])
            ]
            if tail_ids != [int(value) for value in pool_snapshot_ids]:
                raise ValueError(
                    'assignment provenance tail pool membership mismatch'
                )
        if int(tail.get('total_hands_before_iteration', -1)) != int(
            checkpoint_total_hands
        ):
            raise ValueError(
                'pending assignment total-hands boundary does not match checkpoint'
            )
        pending = tail_assignments
    return {
        'records_verified': len(provenance_records),
        'tail_iteration': tail_iteration,
        'tail_sha256': previous_sha,
        'pending_assignments': pending,
    }


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


def elo_expected_score(rating_a: float, rating_b: float) -> float:
    """Standard base-10 ELO expected score for competitor A."""
    return 1.0 / (1.0 + 10.0 ** ((float(rating_b) - float(rating_a)) / 400.0))


def update_elo_pair(
    rating_a: float,
    rating_b: float,
    *,
    wins_a: int,
    draws: int,
    losses_a: int,
    k_factor: float,
) -> tuple[float, float, dict]:
    """Apply one deterministic block ELO update from mirrored pair outcomes."""
    wins_a = int(wins_a)
    draws = int(draws)
    losses_a = int(losses_a)
    total = wins_a + draws + losses_a
    if total <= 0:
        raise ValueError('ELO result block must contain at least one pair')
    if min(wins_a, draws, losses_a) < 0:
        raise ValueError('ELO result counts must be nonnegative')
    if not math.isfinite(float(k_factor)) or float(k_factor) <= 0.0:
        raise ValueError('ELO k-factor must be finite and positive')
    actual = (wins_a + 0.5 * draws) / float(total)
    expected = elo_expected_score(rating_a, rating_b)
    delta = float(k_factor) * (actual - expected)
    next_a = float(rating_a) + delta
    next_b = float(rating_b) - delta
    return next_a, next_b, {
        'actual_score_a': float(actual),
        'expected_score_a': float(expected),
        'rating_delta_a': float(delta),
    }


def elo_match_seed(
    base_seed: int,
    tournament_index: int,
    competitor_a_id: int,
    competitor_b_id: int,
) -> int:
    """Stable match seed independent of process/global RNG state."""
    low, high = sorted((int(competitor_a_id), int(competitor_b_id)))
    material = (
        f'cardpilot.elo-kbest.v1|{int(base_seed)}|{int(tournament_index)}|'
        f'{low}|{high}'
    ).encode('ascii')
    return int.from_bytes(hashlib.sha256(material).digest()[:8], 'big')


def hash_chained_elo_records(history: list[dict]) -> list[dict]:
    """Return canonical hash-chained tournament evidence records."""
    output = []
    previous = None
    for source in history:
        record = copy.deepcopy(source)
        record.pop('record_sha256', None)
        record['previous_record_sha256'] = previous
        canonical = json.dumps(
            record,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False,
        )
        record['record_sha256'] = hashlib.sha256(
            canonical.encode('utf-8')
        ).hexdigest()
        previous = record['record_sha256']
        output.append(record)
    return output


def write_elo_tournament_evidence(path: Path, history: list[dict]) -> None:
    """Atomically mirror checkpoint-backed ELO history into JSONL evidence."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + '.tmp')
    records = hash_chained_elo_records(history)
    with temp_path.open('w', encoding='utf-8', newline='\n') as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def run_elo_survivor_tournament(
    *,
    competitors: list[dict],
    pairs: int,
    base_seed: int,
    tournament_index: int,
    starting_stack: float,
    device: str,
    k_factor: float,
) -> dict:
    """Run a fixed-order greedy mirrored round robin and update ELO ratings.

    Each competitor dict requires id, model, rating, and state_sha256. Models
    are evaluated in-place and their prior train/eval modes are restored. The
    tournament consumes no training RNG or environment-hand accounting.
    """
    if int(pairs) <= 0:
        raise ValueError('ELO tournament pairs must be positive')
    ids = [int(row['id']) for row in competitors]
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ValueError('ELO tournament requires at least two unique ids')
    ordered = sorted(competitors, key=lambda row: int(row['id']))
    ratings = {
        int(row['id']): float(row.get('rating', 1500.0))
        for row in ordered
    }
    if not all(math.isfinite(value) for value in ratings.values()):
        raise ValueError('ELO ratings must be finite')

    try:
        from alpha_holdem.v5_mirror_eval import Policy, summarize_anchor
    except ModuleNotFoundError:
        from scripts.alpha_holdem.v5_mirror_eval import Policy, summarize_anchor

    prior_modes = {int(row['id']): bool(row['model'].training) for row in ordered}
    policies = {}
    for row in ordered:
        competitor_id = int(row['id'])
        row['model'].eval()
        policies[competitor_id] = Policy(
            label=f'elo_snapshot_{competitor_id}',
            path=Path(f'elo_snapshot_{competitor_id}.pt'),
            sha256=str(row['state_sha256']),
            checkpoint={},
            model=row['model'],
            env_version='v55preflopv2v4obs',
            obs_version='v4',
            emulate_raise_cap1_legality=False,
            device=str(device),
        )

    matches = []
    total_ood_nodes = 0
    try:
        for a_index in range(len(ordered)):
            for b_index in range(a_index + 1, len(ordered)):
                a_id = int(ordered[a_index]['id'])
                b_id = int(ordered[b_index]['id'])
                match_seed = elo_match_seed(
                    base_seed, tournament_index, a_id, b_id
                )
                result = summarize_anchor(
                    candidate=policies[a_id],
                    anchor=policies[b_id],
                    pairs=int(pairs),
                    seed=int(match_seed),
                    starting_stack=float(starting_stack),
                    include_pair_outcomes=False,
                )
                rating_a_before = ratings[a_id]
                rating_b_before = ratings[b_id]
                ratings[a_id], ratings[b_id], update = update_elo_pair(
                    rating_a_before,
                    rating_b_before,
                    wins_a=int(result['pair_wins']),
                    draws=int(result['pair_draws']),
                    losses_a=int(result['pair_losses']),
                    k_factor=float(k_factor),
                )
                ood_nodes = int(sum(result.get('ood_nodes', {}).values()))
                total_ood_nodes += ood_nodes
                matches.append({
                    'competitor_a_id': a_id,
                    'competitor_b_id': b_id,
                    'seed': int(match_seed),
                    'pairs': int(pairs),
                    'hands': int(pairs) * 2,
                    'a_pair_wins': int(result['pair_wins']),
                    'pair_draws': int(result['pair_draws']),
                    'a_pair_losses': int(result['pair_losses']),
                    'a_bb100': float(result['candidate_bb100']),
                    'a_ci95_bb100': float(result['candidate_ci95_bb100']),
                    'rating_a_before': float(rating_a_before),
                    'rating_b_before': float(rating_b_before),
                    'rating_a_after': float(ratings[a_id]),
                    'rating_b_after': float(ratings[b_id]),
                    'ood_nodes': ood_nodes,
                    **update,
                })
    finally:
        for row in ordered:
            row['model'].train(prior_modes[int(row['id'])])

    return {
        'schema': 'cardpilot.elo_kbest_tournament.v1',
        'tournament_index': int(tournament_index),
        'pairs_per_match': int(pairs),
        'k_factor': float(k_factor),
        'base_seed': int(base_seed),
        'competitors': [
            {
                'id': int(row['id']),
                'state_sha256': str(row['state_sha256']),
                'rating_before': float(row.get('rating', 1500.0)),
                'rating_after': float(ratings[int(row['id'])]),
            }
            for row in ordered
        ],
        'matches': matches,
        'evaluation_hands': int(len(matches) * int(pairs) * 2),
        'total_ood_nodes': int(total_ood_nodes),
        'ratings': {str(key): float(value) for key, value in sorted(ratings.items())},
    }


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


def split_complete_hand_blocks(transitions) -> list[list]:
    """Split a contiguous rollout stream into complete poker-hand blocks.

    A modern worker marks exactly one terminal trajectory per poker hand with
    transition field 11.  Self-play hands can contain a second, unmarked
    trajectory immediately after the marked one.  Keeping that pair together
    is required when replaying data because GAE must never cross a hand or
    splice trajectories from different deals.

    Legacy transition tuples without field 11 are treated conservatively as
    one complete block per done-terminated trajectory.
    """
    if not transitions:
        return []

    trajectories = []
    current = []
    for transition in transitions:
        current.append(transition)
        if float(transition[8]) > 0.5:
            trajectories.append(current)
            current = []
    if current:
        raise ValueError('replay source ends with an incomplete trajectory')

    if all(len(trajectory[-1]) <= 11 for trajectory in trajectories):
        return trajectories

    blocks = []
    current_block = None
    for trajectory in trajectories:
        terminal = trajectory[-1]
        marker = len(terminal) > 11 and float(terminal[11]) > 0.5
        if marker:
            if current_block is not None:
                blocks.append(current_block)
            current_block = list(trajectory)
        else:
            if current_block is None:
                raise ValueError(
                    'unmarked replay trajectory does not follow a marked trajectory'
                )
            current_block.extend(trajectory)
            blocks.append(current_block)
            current_block = None
    if current_block is not None:
        blocks.append(current_block)

    for block in blocks:
        validate_stream_message(block)
    return blocks


def sample_replay_hand_blocks(replay_entries, target_rows: int, rng) -> tuple[list, dict]:
    """Sample whole historical hands without replacement up to ``target_rows``.

    ``replay_entries`` contains dictionaries with ``iteration`` and ``blocks``.
    Sampling uses a dedicated RNG so enabling replay does not perturb opponent
    assignment or deal streams in a matched control.
    """
    target_rows = int(target_rows)
    if target_rows <= 0 or not replay_entries:
        return [], {
            'rows': 0,
            'hands': 0,
            'source_iterations': [],
            'available_rows': sum(
                len(block)
                for entry in replay_entries
                for block in entry.get('blocks', [])
            ),
        }

    candidates = [
        (int(entry['iteration']), block)
        for entry in replay_entries
        for block in entry.get('blocks', [])
    ]
    order = list(range(len(candidates)))
    rng.shuffle(order)
    sampled = []
    sampled_blocks = 0
    source_iterations = set()
    for index in order:
        source_iteration, block = candidates[index]
        sampled.extend(block)
        sampled_blocks += 1
        source_iterations.add(source_iteration)
        if len(sampled) >= target_rows:
            break
    return sampled, {
        'rows': len(sampled),
        'hands': sampled_blocks,
        'sampled_blocks': sampled_blocks,
        'source_iterations': sorted(source_iterations),
        'available_rows': sum(len(block) for _, block in candidates),
    }


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
    if len(t) > 13:
        h.update(struct.pack('<d', float(t[13])))
    if len(t) > 14:
        h.update(struct.pack('<d', float(t[14])))
    if len(t) > 15:
        h.update(np.asarray(t[15], dtype=np.float32).tobytes())
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
        'paired_seat_average_pairs': 0,
        'paired_seat_average_terminal_rows': 0,
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
    if hasattr(env, 'reset_with_deck'):
        return env.reset_with_deck(deck)
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


def paired_seat_average_actor_reward_blocks(
    source_block,
    mirror_block,
    *,
    source_rewards=None,
    mirror_rewards=None,
):
    """Attach actor-only terminal rewards averaged over opposite seats.

    Transition field 13 is the engine player/seat.  A mirrored deck swaps the
    two private hands, so source player ``p`` owns the same cards as mirror
    player ``1-p``.  Field 6 remains the realized raw reward used by the critic;
    optional field 14 is the actor-only reward override.
    """
    source_block = [tuple(row) for row in source_block]
    mirror_block = [tuple(row) for row in mirror_block]
    def terminal_rewards(block, label):
        rewards = {}
        for row in block:
            if len(row) <= 13:
                raise ValueError(f'{label} transition lacks player metadata')
            if float(row[8]) <= 0.5:
                continue
            player = int(row[13])
            if player not in (0, 1):
                raise ValueError(f'{label} transition has invalid player metadata')
            if player in rewards:
                raise ValueError(f'{label} block has duplicate player terminal')
            rewards[player] = float(row[6])
        return rewards

    if source_rewards is None and mirror_rewards is None:
        source_rewards = terminal_rewards(source_block, 'source')
        mirror_rewards = terminal_rewards(mirror_block, 'mirror')
        if not source_rewards or not mirror_rewards:
            raise ValueError(
                'implicit paired rewards require terminal rows in both blocks'
            )
        expected_mirror_players = {1 - player for player in source_rewards}
        if set(mirror_rewards) != expected_mirror_players:
            raise ValueError(
                'source/mirror player sets do not form an opposite-seat bijection'
            )
    elif source_rewards is None or mirror_rewards is None:
        raise ValueError('source and mirror reward mappings must be supplied together')
    else:
        source_rewards = {
            int(player): float(reward)
            for player, reward in source_rewards.items()
        }
        mirror_rewards = {
            int(player): float(reward)
            for player, reward in mirror_rewards.items()
        }
        if set(source_rewards) != {0, 1} or set(mirror_rewards) != {0, 1}:
            raise ValueError(
                'explicit source/mirror rewards must cover both engine players'
            )
    paired_by_source_player = {
        player: 0.5 * (reward + mirror_rewards[1 - player])
        for player, reward in source_rewards.items()
    }

    def attach(block, *, mirror):
        result = []
        terminal_rows = 0
        for row in block:
            values = list(row)
            while len(values) <= 14:
                values.append(float('nan'))
            if float(row[8]) > 0.5:
                player = int(row[13])
                source_player = 1 - player if mirror else player
                values[14] = paired_by_source_player[source_player]
                terminal_rows += 1
            else:
                values[14] = float('nan')
            result.append(tuple(values))
        return result, terminal_rows

    paired_source, source_terminals = attach(source_block, mirror=False)
    paired_mirror, mirror_terminals = attach(mirror_block, mirror=True)
    return paired_source, paired_mirror, source_terminals + mirror_terminals


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

ENVIRONMENT_HAND_ACCOUNTING_SCHEMA = 'cardpilot.completed_environment_hands.v1'
PROCEDURAL_OPPONENT_ACCOUNTING_SCHEMA = (
    'cardpilot.procedural_opponent_accounting.v1'
)
PROCEDURAL_COUNTER_STRIDE = (
    3 + len(PROCEDURAL_OPPONENT_PROFILES) + NUM_ACTIONS
)


def initial_environment_hand_accounting(checkpoint, *, reset_hand_counter, run_id):
    if checkpoint is None or reset_hand_counter:
        return {
            'schema': ENVIRONMENT_HAND_ACCOUNTING_SCHEMA,
            'completed_hands': 0,
            'no_trainable_decision_hands': 0,
            'prefix_complete': True,
            'unknown_prefix_training_marker_hands': 0,
            'origin_run_id': run_id,
        }
    previous = checkpoint.get('environment_hand_accounting')
    if previous is not None:
        if previous.get('schema') != ENVIRONMENT_HAND_ACCOUNTING_SCHEMA:
            raise ValueError('unsupported environment-hand accounting schema')
        return dict(previous)
    return {
        'schema': ENVIRONMENT_HAND_ACCOUNTING_SCHEMA,
        'completed_hands': 0,
        'no_trainable_decision_hands': 0,
        'prefix_complete': False,
        'unknown_prefix_training_marker_hands': int(checkpoint.get('total_hands', 0)),
        'origin_run_id': run_id,
    }


def count_completed_environment_hand(counters, worker_id, *, has_trainable_decision):
    if counters is None:
        return
    with counters.get_lock():
        counters[2 * worker_id] += 1
        if not has_trainable_decision:
            counters[2 * worker_id + 1] += 1


def environment_hand_accounting_snapshot(base, counters, legacy_training_hands):
    if counters is None:
        worker_counts = []
    else:
        with counters.get_lock():
            worker_counts = list(counters[:])
    session_completed = sum(worker_counts[0::2])
    session_no_decision = sum(worker_counts[1::2])
    result = {
        **base,
        'completed_hands': int(base['completed_hands']) + session_completed,
        'no_trainable_decision_hands': (
            int(base['no_trainable_decision_hands']) + session_no_decision
        ),
        'session_completed_hands': session_completed,
        'session_no_trainable_decision_hands': session_no_decision,
        'legacy_training_marker_hands': int(legacy_training_hands),
        'counter_scope': 'completed_terminal_hands_including_unconsumed_worker_tails',
        'session_worker_counts': [
            {'worker_id': index // 2, 'completed_hands': worker_counts[index],
             'no_trainable_decision_hands': worker_counts[index + 1]}
            for index in range(0, len(worker_counts), 2)
        ],
    }
    validate_environment_hand_accounting(result)
    return result


def validate_environment_hand_accounting(accounting):
    if accounting.get('schema') != ENVIRONMENT_HAND_ACCOUNTING_SCHEMA:
        raise ValueError('unsupported environment-hand accounting schema')
    if not isinstance(accounting.get('prefix_complete'), bool):
        raise ValueError('environment-hand prefix completeness must be boolean')
    completed = int(accounting['completed_hands'])
    no_decision = int(accounting['no_trainable_decision_hands'])
    legacy = int(accounting.get('legacy_training_marker_hands', 0))
    if completed < 0 or not 0 <= no_decision <= completed or legacy < 0:
        raise ValueError('invalid environment-hand counts')
    if accounting['prefix_complete'] and legacy > completed - no_decision:
        raise ValueError('training markers exceed physical decision-bearing hands')


def environment_training_target_reached(*, legacy_hands, legacy_target,
                                        environment_target, accounting):
    if environment_target > 0:
        if not accounting['prefix_complete']:
            raise ValueError('physical-hand target requires a known environment-hand prefix')
        return int(accounting['completed_hands']) >= int(environment_target)
    return int(legacy_hands) >= int(legacy_target)


def initial_procedural_opponent_accounting(checkpoint, *, reset_hand_counter):
    empty = {
        'schema': PROCEDURAL_OPPONENT_ACCOUNTING_SCHEMA,
        'hands': 0,
        'decisions': 0,
        'inference_bypasses': 0,
        'style_counts': [0 for _ in PROCEDURAL_OPPONENT_PROFILES],
        'action_counts': [0 for _ in range(NUM_ACTIONS)],
        'prefix_complete': True,
    }
    if checkpoint is None or reset_hand_counter:
        return empty
    previous = checkpoint.get('procedural_opponent_accounting')
    if previous is not None:
        validate_procedural_opponent_accounting(previous)
        return dict(previous)
    previous_fraction = float(
        (checkpoint.get('config') or {}).get('procedural_opponent_fraction', 0.0)
    )
    if previous_fraction == 0.0:
        return empty
    return {**empty, 'prefix_complete': False}


def count_completed_procedural_hand(counters, worker_id, *, profile_id,
                                    action_counts):
    if counters is None:
        return
    action_counts = [int(value) for value in action_counts]
    if len(action_counts) != NUM_ACTIONS or any(value < 0 for value in action_counts):
        raise ValueError('invalid procedural per-hand action counts')
    profile_id = int(profile_id)
    if not 0 <= profile_id < len(PROCEDURAL_OPPONENT_PROFILES):
        raise ValueError('invalid procedural profile id')
    offset = int(worker_id) * PROCEDURAL_COUNTER_STRIDE
    decisions = sum(action_counts)
    with counters.get_lock():
        counters[offset] += 1
        counters[offset + 1] += decisions
        counters[offset + 2] += decisions
        counters[offset + 3 + profile_id] += 1
        action_offset = offset + 3 + len(PROCEDURAL_OPPONENT_PROFILES)
        for slot, count in enumerate(action_counts):
            counters[action_offset + slot] += count


def procedural_opponent_accounting_snapshot(base, counters):
    if counters is None:
        raw = []
    else:
        with counters.get_lock():
            raw = list(counters[:])
    session_hands = 0
    session_decisions = 0
    session_bypasses = 0
    session_styles = [0 for _ in PROCEDURAL_OPPONENT_PROFILES]
    session_actions = [0 for _ in range(NUM_ACTIONS)]
    worker_counts = []
    for worker_offset in range(0, len(raw), PROCEDURAL_COUNTER_STRIDE):
        values = raw[worker_offset:worker_offset + PROCEDURAL_COUNTER_STRIDE]
        styles = values[3:3 + len(PROCEDURAL_OPPONENT_PROFILES)]
        actions = values[3 + len(PROCEDURAL_OPPONENT_PROFILES):]
        session_hands += int(values[0])
        session_decisions += int(values[1])
        session_bypasses += int(values[2])
        session_styles = [a + int(b) for a, b in zip(session_styles, styles)]
        session_actions = [a + int(b) for a, b in zip(session_actions, actions)]
        worker_counts.append({
            'worker_id': worker_offset // PROCEDURAL_COUNTER_STRIDE,
            'hands': int(values[0]),
            'decisions': int(values[1]),
        })
    result = {
        **base,
        'hands': int(base['hands']) + session_hands,
        'decisions': int(base['decisions']) + session_decisions,
        'inference_bypasses': (
            int(base['inference_bypasses']) + session_bypasses
        ),
        'style_counts': [
            int(a) + int(b)
            for a, b in zip(base['style_counts'], session_styles)
        ],
        'action_counts': [
            int(a) + int(b)
            for a, b in zip(base['action_counts'], session_actions)
        ],
        'session_hands': session_hands,
        'session_decisions': session_decisions,
        'session_inference_bypasses': session_bypasses,
        'session_style_counts': session_styles,
        'session_action_counts': session_actions,
        'session_worker_counts': worker_counts,
        'counter_scope': 'completed_procedural_hands_including_unconsumed_worker_tails',
        'version': PROCEDURAL_OPPONENT_VERSION,
        'profile_names': [profile[0] for profile in PROCEDURAL_OPPONENT_PROFILES],
    }
    validate_procedural_opponent_accounting(result)
    return result


def validate_procedural_opponent_accounting(accounting):
    if accounting.get('schema') != PROCEDURAL_OPPONENT_ACCOUNTING_SCHEMA:
        raise ValueError('unsupported procedural-opponent accounting schema')
    if not isinstance(accounting.get('prefix_complete'), bool):
        raise ValueError('procedural-opponent prefix completeness must be boolean')
    hands = int(accounting['hands'])
    decisions = int(accounting['decisions'])
    bypasses = int(accounting['inference_bypasses'])
    styles = [int(value) for value in accounting['style_counts']]
    actions = [int(value) for value in accounting['action_counts']]
    if len(styles) != len(PROCEDURAL_OPPONENT_PROFILES):
        raise ValueError('invalid procedural style accounting length')
    if len(actions) != NUM_ACTIONS:
        raise ValueError('invalid procedural action accounting length')
    if min([hands, decisions, bypasses, *styles, *actions]) < 0:
        raise ValueError('negative procedural-opponent accounting value')
    if sum(styles) != hands or sum(actions) != decisions or bypasses != decisions:
        raise ValueError('inconsistent procedural-opponent accounting totals')


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
    paired_seat_average_returns=False,
    allin_runout_ev=False,
    allin_runout_ev_max_runouts=EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
    fixed_training_deal_stream=False,
    fixed_training_deal_start_index=0,
    showdown_ev_value_targets=False,
    showdown_ev_value_target_max_runouts=H2_MAX_RUNOUTS,
    showdown_ev_value_target_seed=H2_TARGET_SEED,
    hero_preflop_strategy='model',
    centralized_critic=False,
    environment_hand_counters=None,
    procedural_opponent_fraction=0.0,
    procedural_opponent_counters=None,
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
    if env_version == 'v6':
        from alpha_holdem.environment_v6 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}
    elif env_version == 'v4':
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
    hands_played = int(fixed_training_deal_start_index)
    local_transitions = []
    local_metrics = exp003_metrics_template()
    local_procedural_metrics = procedural_opponent_metrics_template()
    local_league_hands = {}
    local_league_reward_sums = {}
    pending_mirror_deck = None
    pending_mirror_identity = None
    pending_mirror_opponent_id = None
    pending_pair_block = None
    source_deal_index = int(fixed_training_deal_start_index)

    try:
        while not stop_event.is_set():
            # Read this hand's opponent assignment (main writes per iter; we only read).
            # EXP-003 mirrored replay is always self-play and keeps the original board order.
            is_mirror_replay = pending_mirror_deck is not None
            if is_mirror_replay:
                current_opp_id = (
                    int(pending_mirror_opponent_id)
                    if paired_seat_average_returns
                    else -1
                )
                obs = exp003_reset_env_with_deck(env, pending_mirror_deck)
                pending_mirror_deck = None
                deal_identity = pending_mirror_identity
                pending_mirror_identity = None
                pending_mirror_opponent_id = None
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
                if (
                    paired_seat_average_returns
                    or (mirror_self_play_deals and current_opp_id == -1)
                ):
                    mirror_deck = exp003_mirrored_deck_from_env(env)
                    if mirror_deck is not None:
                        pending_mirror_deck = mirror_deck
                        pending_mirror_identity = f'{deal_identity}:mirror'
                        pending_mirror_opponent_id = int(current_opp_id)
                        local_metrics['mirror_source_hands'] += 1
            is_self_play = (current_opp_id == -1)

            done = False
            hero_player = hands_played % 2
            procedural_rng = None
            procedural_style = None
            procedural_hand_action_counts = [0 for _ in range(NUM_ACTIONS)]
            if not is_self_play and procedural_opponent_fraction > 0.0:
                procedural_rng = _random.Random(
                    procedural_opponent_hand_seed(worker_seed, hands_played)
                )
                if procedural_rng.random() < procedural_opponent_fraction:
                    procedural_style = sample_procedural_opponent_style(
                        procedural_rng
                    )

            # V5.0: per-player buffers for both-player collect
            hand_buffers = {0: [], 1: []}
            last_actor = None

            while not done and not stop_event.is_set():
                player = obs['player']
                is_hero = (player == hero_player)

                ci = obs['card_info'].flatten()
                ai = obs['action_info'].flatten()
                ei = pack_position_extra(
                    obs['extra_info'],
                    player=player,
                )
                lm = obs['legal_mask']

                if procedural_style is not None and not is_hero:
                    action_idx = procedural_opponent_action(
                        env,
                        player,
                        lm,
                        procedural_style,
                        procedural_rng,
                    )
                    log_prob = 0.0
                    value = 0.0
                    local_procedural_metrics['decisions'] += 1
                    local_procedural_metrics['inference_bypasses'] += 1
                    local_procedural_metrics['action_counts'][action_idx] += 1
                    procedural_hand_action_counts[action_idx] += 1
                else:
                    # V5.0: which model serves this inference?
                    # - self-play: hero model for both sides
                    # - opp-mode: hero model when is_hero, pool model otherwise
                    req_model = (
                        HERO_MODEL_ID
                        if (is_self_play or is_hero)
                        else current_opp_id
                    )
                    obs_buf[:CARD_SIZE] = ci
                    obs_buf[CARD_SIZE:CARD_SIZE + ACTION_SIZE] = ai
                    obs_buf[
                        CARD_SIZE + ACTION_SIZE:
                        CARD_SIZE + ACTION_SIZE + EXTRA_SIZE
                    ] = ei
                    obs_buf[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE:] = lm

                    request_buf[0] = req_model
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

            count_completed_environment_hand(
                environment_hand_counters, worker_id,
                has_trainable_decision=any(hand_buffers.values()),
            )

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
            hero_reward = float(rewards_per_player.get(hero_player, 0.0))
            if procedural_style is not None:
                count_completed_procedural_hand(
                    procedural_opponent_counters,
                    worker_id,
                    profile_id=int(procedural_style['profile_id']),
                    action_counts=procedural_hand_action_counts,
                )
                local_procedural_metrics['hands'] += 1
                local_procedural_metrics['style_counts'][
                    int(procedural_style['profile_id'])
                ] += 1
            else:
                opponent_key = str(int(current_opp_id))
                local_league_hands[opponent_key] = (
                    int(local_league_hands.get(opponent_key, 0)) + 1
                )
                local_league_reward_sums[opponent_key] = (
                    float(local_league_reward_sums.get(opponent_key, 0.0))
                    + hero_reward
                )

            # Legacy total_hands marks transition-bearing hands only. Physical
            # terminal hands, including no-decision hands, are counted above.
            hand_transition_start = len(local_transitions)
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
                    if centralized_critic:
                        transition = transition + (
                            float('nan'),
                            encode_opponent_private_cards(
                                env.state,
                                player=p,
                            ),
                        )
                    local_transitions.append(transition)

            if h2_hand_has_target:
                local_metrics['h2_showdown_hands'] += 1

            if paired_seat_average_returns:
                completed_block = list(
                    local_transitions[hand_transition_start:]
                )
                del local_transitions[hand_transition_start:]
                if is_mirror_replay:
                    if pending_pair_block is None:
                        raise RuntimeError(
                            'mirror hand completed without a pending source block'
                        )
                    (
                        source_block,
                        source_rewards,
                        source_hero_player,
                        source_opponent_id,
                    ) = pending_pair_block
                    if int(source_opponent_id) != int(current_opp_id):
                        raise RuntimeError(
                            'source/mirror opponent identity changed inside pair'
                        )
                    if (
                        int(current_opp_id) != -1
                        and int(hero_player) != 1 - int(source_hero_player)
                    ):
                        raise RuntimeError(
                            'external source/mirror hero seats are not opposite'
                        )
                    (
                        paired_source,
                        paired_mirror,
                        terminal_rows,
                    ) = paired_seat_average_actor_reward_blocks(
                        source_block,
                        completed_block,
                        source_rewards=source_rewards,
                        mirror_rewards=rewards_per_player,
                    )
                    local_transitions.extend(paired_source)
                    local_transitions.extend(paired_mirror)
                    pending_pair_block = None
                    local_metrics['paired_seat_average_pairs'] += 1
                    local_metrics[
                        'paired_seat_average_terminal_rows'
                    ] += int(terminal_rows)
                else:
                    if pending_pair_block is not None:
                        raise RuntimeError(
                            'new source hand arrived before its mirror completed'
                        )
                    pending_pair_block = (
                        completed_block,
                        dict(rewards_per_player),
                        int(hero_player),
                        int(current_opp_id),
                    )

            hands_played += 1

            if hands_played % 50 == 0 and local_transitions:
                try:
                    transition_pipe.send(local_transitions)
                    transition_pipe.send({
                        'type': 'league_metrics',
                        'hands': local_league_hands,
                        'hero_reward_sums': local_league_reward_sums,
                    })
                    local_league_hands = {}
                    local_league_reward_sums = {}
                    if exp003_metrics_nonzero(local_metrics):
                        transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
                        local_metrics = exp003_metrics_template()
                    if procedural_opponent_metrics_nonzero(local_procedural_metrics):
                        transition_pipe.send({
                            'type': 'procedural_opponent_metrics',
                            **local_procedural_metrics,
                        })
                        local_procedural_metrics = procedural_opponent_metrics_template()
                except BrokenPipeError:
                    break
                local_transitions = []

        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
                if local_league_hands:
                    transition_pipe.send({
                        'type': 'league_metrics',
                        'hands': local_league_hands,
                        'hero_reward_sums': local_league_reward_sums,
                    })
                if exp003_metrics_nonzero(local_metrics):
                    transition_pipe.send({'type': 'exp003_metrics', **local_metrics})
                if procedural_opponent_metrics_nonzero(local_procedural_metrics):
                    transition_pipe.send({
                        'type': 'procedural_opponent_metrics',
                        **local_procedural_metrics,
                    })
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
    paired_seat_average_returns=False,
    allin_runout_ev=False,
    allin_runout_ev_max_runouts=EXP003_DEFAULT_ALLIN_RUNOUT_EV_MAX_RUNOUTS,
    fixed_training_deal_stream=False,
    fixed_training_deal_start_index=0,
    showdown_ev_value_targets=False,
    showdown_ev_value_target_max_runouts=H2_MAX_RUNOUTS,
    showdown_ev_value_target_seed=H2_TARGET_SEED,
    hero_preflop_strategy='model',
    centralized_critic=False,
    environment_hand_counters=None,
):
    """
    EXP-002 multi-env worker. Owns M environments; slot s = worker_id*M + e.

    INVARIANTS (ledger EXP-002):
    - Each completed poker hand is appended to local_transitions as ONE contiguous
      block (both players' trajectories, each done-terminated), never interleaved
      with other envs' decisions. compute_gae depends on this.
    - hand_marker: one transition per decision-bearing hand has marker=1.0.
      Physical completed hands are counted independently, including empty buffers.
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
    if env_version == 'v6':
        from alpha_holdem.environment_v6 import HUNLEnvironment
        env_kwargs = {'starting_stack': starting_stack}
    elif env_version == 'v4':
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
        s.hands_played = int(fixed_training_deal_start_index)
        s.current_opp = -1
        s.pending = None
        s.terminal_reward = 0.0
        s.mirror_deck = None
        s.mirror_identity = None
        s.deal_identity = None
        s.deal_index = int(fixed_training_deal_start_index)
        slots.append(s)

    local_transitions = []
    local_metrics = exp003_metrics_template()
    local_league_hands = {}
    local_league_reward_sums = {}
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
        hero_player = s.hands_played % 2
        hero_reward = float(rewards_per_player.get(hero_player, 0.0))
        opponent_key = str(int(s.current_opp))
        local_league_hands[opponent_key] = (
            int(local_league_hands.get(opponent_key, 0)) + 1
        )
        local_league_reward_sums[opponent_key] = (
            float(local_league_reward_sums.get(opponent_key, 0.0))
            + hero_reward
        )

        count_completed_environment_hand(
            environment_hand_counters, worker_id,
            has_trainable_decision=any(s.buffers.values()),
        )
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
                if centralized_critic:
                    transition = transition + (
                        float('nan'),
                        encode_opponent_private_cards(
                            env.state,
                            player=p,
                        ),
                    )
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
                            transition_pipe.send({
                                'type': 'league_metrics',
                                'hands': local_league_hands,
                                'hero_reward_sums': local_league_reward_sums,
                            })
                            local_league_hands = {}
                            local_league_reward_sums = {}
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
                if local_league_hands:
                    transition_pipe.send({
                        'type': 'league_metrics',
                        'hands': local_league_hands,
                        'hero_reward_sums': local_league_reward_sums,
                    })
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
    hero_policy_temperature: float = 1.0,
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
        temperature = (
            float(hero_policy_temperature)
            if int(mid) == HERO_MODEL_ID and hero_policy_mode == 'sample'
            else 1.0
        )
        probs, dist = temperature_policy_distribution(logits, temperature)
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
    Trinal-Clip selection loss. ``elo-kbest`` keeps the highest ratings supplied
    by deterministic mirrored survivor tournaments.
    """

    def __init__(self, k=5, strategy='loss-kbest', history_limit=200):
        if strategy not in ('latest', 'loss-kbest', 'elo-kbest'):
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

    def add(
        self,
        model_state,
        *,
        hands=0,
        iteration=None,
        selection_loss=None,
        selection_score=None,
        score_components=None,
    ) -> dict:
        loss = self._finite_or_none(selection_loss)
        score = self._finite_or_none(selection_score)
        if score is None:
            score = (
                1500.0
                if self.strategy == 'elo-kbest'
                else (-loss if loss is not None else None)
            )
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
        if self.strategy == 'elo-kbest':
            return (
                f'deterministic mirrored ELO-selected historical self-play '
                f'snapshots (K={self.k})'
            )
        return (
            f'loss-selected K-best historical self-play snapshots (K={self.k}); '
            'selection_score=-selection_loss proxy, not full ELO'
        )


# ===========================================================
# Main
# ===========================================================

def configure_preflop_head_only_training(model):
    """Freeze policy execution outside the dedicated preflop/value heads."""
    trainable_prefixes = ('preflop_policy_head.', 'value_head.')
    for name, parameter in model.named_parameters():
        parameter.requires_grad = name.startswith(trainable_prefixes)
    return [parameter for parameter in model.parameters() if parameter.requires_grad]


def main():
    parser = argparse.ArgumentParser(
        description='AlphaHoldem V5 clean-from-zero self-play trainer',
    )
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=2_700_000_000,
                        help='Legacy transition-bearing hand target; not a full physical hand count.')
    parser.add_argument('--total-environment-hands', type=int, default=0,
                        help='Optional physical completed-hand target, checked at PPO boundaries; overrides the legacy target.')
    parser.add_argument('--starting-stack', type=float, default=200.0)
    parser.add_argument('--env-version', choices=('v6', 'v55', 'v4', 'v55cap1', 'v55cap1v4obs', 'v55v4obs', 'v55pfv2v4obs', 'v55preflopv2v4obs'), default='v55',
                        help='Training environment. v55 fixes the legacy V4/V5 action-history and raise-cap bugs.')
    parser.add_argument('--v6-rebind-legacy-weights', action='store_true',
                        help='Explicit NEW experiment migration: v6 contract, reset optimizer and all hand counters; never a legacy run resume.')
    parser.add_argument('--norm-layer', choices=('bn', 'gn'), default='bn',
                        help='Network normalization. Use gn for GN BC/imitation checkpoints.')
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--ppo-target-kl', type=float, default=0.0,
                        help='H6: after each completed PPO epoch, skip remaining epochs when '
                             'that epoch mean approx_kl is strictly greater than this value. '
                             '0 disables early-stop and preserves baseline behavior.')
    parser.add_argument(
        '--policy-advantage-clip',
        type=float,
        default=0.0,
        help=(
            'Symmetrically winsorize normalized actor advantages to this '
            'absolute bound after normalization. Zero preserves baseline.'
        ),
    )
    parser.add_argument(
        '--policy-advantage-normalization',
        choices=('global', 'action', 'action_rms'),
        default='global',
        help=(
            "'action' whitens each sufficiently observed sampled action. "
            "'action_rms' equalizes action-wise RMS magnitude while preserving "
            "bounded between-action mean information."
        ),
    )
    parser.add_argument(
        '--action-normalization-min-rows',
        type=int,
        default=32,
    )
    parser.add_argument(
        '--greedy-advantage-margin-coef',
        type=float,
        default=0.0,
        help=(
            'Default-off actor auxiliary loss: on positive-advantage sampled '
            'actions that differ from legal argmax, push the sampled logit '
            'above the current greedy logit by --greedy-advantage-margin.'
        ),
    )
    parser.add_argument(
        '--greedy-advantage-margin',
        type=float,
        default=0.1,
    )
    parser.add_argument(
        '--source-greedy-margin-coef',
        type=float,
        default=0.0,
        help=(
            'Default-off source-policy argmax preservation loss. Preserve '
            'the frozen source legal-argmax margin unless a different sampled '
            'action exceeds --source-greedy-margin-release-advantage.'
        ),
    )
    parser.add_argument(
        '--source-greedy-margin-max',
        type=float,
        default=0.1,
    )
    parser.add_argument(
        '--source-greedy-margin-release-advantage',
        type=float,
        default=1.0,
    )
    parser.add_argument('--action-q-hidden', type=int, default=0)
    parser.add_argument('--action-q-advantage', action='store_true')
    parser.add_argument('--action-q-loss-coef', type=float, default=1.0)
    parser.add_argument('--action-q-dueling', action='store_true')
    parser.add_argument(
        '--action-q-residual-l2-coef',
        type=float,
        default=0.0,
    )
    parser.add_argument(
        '--action-q-support-prior-rows',
        type=float,
        default=0.0,
        help=(
            'Shrink action-Q policy credit for sparsely sampled action slots '
            'by n_action/(n_action+prior_rows); Q fitting is unchanged.'
        ),
    )
    parser.add_argument(
        '--action-q-policy-mix',
        type=float,
        default=1.0,
        help=(
            'Fraction of delayed Action-Q advantage used by the PPO actor. '
            'The default 1 preserves existing runs; values below 1 blend in '
            'on-policy GAE to stabilize imperfect Q credit.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-dataset',
        default=None,
        help=(
            'Balanced BB/SB x flop/turn NPZ containing all-legal-action Q '
            'targets. Only its stratified training split enters optimization.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-dataset-sha256',
        default=None,
        help='Required immutable SHA256 for the counterfactual replay NPZ.',
    )
    parser.add_argument(
        '--restart-counterfactual-replay-state',
        action='store_true',
        help=(
            'Explicit research branch: when preserving a resumed optimizer, '
            'replace the inherited counterfactual dataset with a different '
            'immutable dataset and restart only its cursor, draw counter, and '
            'loss-decay clock at the current lineage hand count. Model weights, '
            'optimizer state, and environment-hand accounting remain continuous.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-loss-coef',
        type=float,
        default=0.0,
        help=(
            'Weight on centered all-legal-action Q replay loss. Zero keeps '
            'all existing training behavior unchanged.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-loss-decay-hands',
        type=int,
        default=0,
        help=(
            'Linearly decay replay loss to zero over this many new '
            'environment hands. Zero keeps a constant coefficient.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-policy-loss-coef',
        type=float,
        default=0.0,
        help=(
            'Weight on bounded soft all-action policy distillation from the '
            'same held-out-safe replay training split. Zero preserves all '
            'existing behavior.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-policy-target-clip',
        type=float,
        default=1.5,
        help=(
            'Absolute clip on per-state RMS-normalized Q target logits before '
            'softmax; keeps every legal action at nonzero target probability.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-policy-temperature',
        type=float,
        default=1.0,
    )
    parser.add_argument(
        '--action-q-counterfactual-policy-reliability-mode',
        choices=('target_and_row', 'row_only'),
        default='target_and_row',
        help=(
            'target_and_row preserves historical per-action confidence '
            'renormalization. row_only keeps robust Q policy ordering intact '
            'and uses uncertainty only to weight each replay row.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-target-mode',
        choices=('mean', 'advantage_lcb'),
        default='mean',
        help='Target semantics used by both Q and soft-policy replay losses.',
    )
    parser.add_argument(
        '--action-q-counterfactual-lcb-z',
        type=float,
        default=1.96,
        help='One-sided alternative-action uncertainty penalty.',
    )
    parser.add_argument(
        '--action-q-counterfactual-batch-size',
        type=int,
        default=512,
    )
    parser.add_argument(
        '--action-q-counterfactual-max-batches-per-update',
        type=int,
        default=0,
        help=(
            'Maximum counterfactual replay minibatches in one PPO update. '
            'Zero preserves the historical every-minibatch behavior; a '
            'positive cap prevents a small offline dataset from being '
            'implicitly multiplied by the on-policy minibatch count.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-split-seed',
        type=int,
        default=20260824,
    )
    parser.add_argument(
        '--action-q-counterfactual-validation-fraction',
        type=float,
        default=0.2,
    )
    parser.add_argument(
        '--action-q-counterfactual-test-fraction',
        type=float,
        default=0.2,
    )
    parser.add_argument(
        '--action-q-counterfactual-stratify-trajectory-opponent',
        action='store_true',
        help=(
            'Split every BB/SB x flop/turn x trajectory-opponent stratum '
            'independently so each observed opponent style remains present '
            'in train, validation, and test.'
        ),
    )
    parser.add_argument(
        '--action-q-counterfactual-uncertainty-floor-bb',
        type=float,
        default=0.25,
    )
    parser.add_argument(
        '--action-q-counterfactual-max-weight-ratio',
        type=float,
        default=20.0,
    )
    parser.add_argument('--source-policy-kl-coef', type=float, default=0.0,
                        help='Discovery mode: forward-KL regularization toward the exact '
                             'resume policy on rollout states. Requires --resume.')
    parser.add_argument(
        '--source-policy-kl-temperature',
        type=float,
        default=None,
        help=(
            'Optional positive temperature used only by source-policy KL. '
            'Omission inherits --hero-policy-temperature for exact compatibility.'
        ),
    )
    parser.add_argument('--gradient-diagnostic-minibatches', type=int, default=0,
                        help='Non-mutating component-gradient probes on this many '
                             'initial minibatches per PPO epoch (0 disables).')
    parser.add_argument('--gradient-noise-hand-groups', type=int, default=0,
                        help='Opt-in fixed-weight actor-gradient probes on equal whole-hand groups; '
                             'requires native all-policy-heads-only fresh fp32 training (0 disables).')
    parser.add_argument(
        '--source-policy-reference-checkpoint',
        default=None,
        help=(
            'Optional fixed checkpoint used only as the source-policy KL '
            'reference. This lets a repaired/resumed run preserve its original '
            'trust-region anchor while loading optimizer/model state from a '
            'later --resume checkpoint.'
        ),
    )
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
        '--policy-street-min',
        type=int,
        choices=(1, 2, 3),
        default=1,
        help=(
            'Lowest postflop street receiving policy gradients and a '
            'position-adapter residual: 1=flop, 2=turn, 3=river.'
        ),
    )
    parser.add_argument(
        '--policy-street-max',
        type=int,
        choices=(1, 2, 3),
        default=3,
        help=(
            'Highest postflop street receiving policy gradients and a '
            'position-adapter residual: 1=flop, 2=turn, 3=river.'
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
        '--all-policy-heads-only-training',
        action='store_true',
        help=(
            'Freeze the shared card/action/extra trunk; update the postflop '
            'policy head, dedicated preflop policy head, and value head. '
            'Requires --separate-preflop-head and permits all-street PPO plus '
            'source-policy KL without representation drift.'
        ),
    )
    parser.add_argument(
        '--preflop-head-only-training',
        action='store_true',
        help=(
            'Freeze the shared trunk and postflop policy head; update only '
            'the dedicated preflop policy head and value head. Requires '
            '--separate-preflop-head and preserves postflop policy logits.'
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
        '--flat-sequence-policy-adapter-hidden',
        type=int,
        default=0,
        help=(
            'Add a zero-output all-street residual policy that encodes the '
            'complete flattened action tensor and routes by public HU seat.'
        ),
    )
    parser.add_argument(
        '--causal-sequence-policy-adapter-hidden',
        type=int,
        default=0,
        help=(
            'Add a zero-output all-street residual policy that encodes the '
            'ordered action tokens with a causal dilated convolution stack '
            'and routes by public HU seat.'
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
        '--flat-sequence-adapter-only-training',
        action='store_true',
        help=(
            'Freeze the source actor and train only the flat-sequence '
            'encoder/residual experts plus the value head.'
        ),
    )
    parser.add_argument(
        '--causal-sequence-adapter-only-training',
        action='store_true',
        help=(
            'Freeze the source actor and train only the causal sequence '
            'encoder/residual experts plus the value head.'
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
    parser.add_argument(
        '--ppo-replay-buffer-iterations',
        type=int,
        default=0,
        help=(
            'Default-off AlphaHoldem replay experiment: retain this many '
            'previous complete rollout iterations for off-policy PPO. New '
            'checkpoints serialize the complete-hand buffer and replay RNG.'
        ),
    )
    parser.add_argument(
        '--ppo-replay-ratio',
        type=float,
        default=0.0,
        help=(
            'Historical replay rows requested per fresh rollout row. Replay '
            'samples only complete poker-hand blocks; 0 disables replay.'
        ),
    )
    parser.add_argument(
        '--acknowledge-ephemeral-ppo-replay-resume',
        action='store_true',
        help=(
            'Recovery-only acknowledgement for an older checkpoint that has '
            'replay enabled but predates replay-buffer serialization. The '
            'first resumed update uses no historical replay and the boundary '
            'is recorded in checkpoints/metrics.'
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
    parser.add_argument(
        '--pool-strategy',
        choices=('latest', 'loss-kbest', 'elo-kbest'),
        default='loss-kbest',
        help=(
            'Historical opponent selection. loss-kbest keeps the K snapshots '
            'with lowest Trinal-Clip selection loss; elo-kbest keeps the K '
            'highest-rated snapshots from deterministic mirrored round-robin '
            'tournaments; latest preserves FIFO recency for ablations.'
        ),
    )
    parser.add_argument('--pool-history-limit', type=int, default=200,
                        help='Metadata-only candidate history entries to retain in checkpoints/manifests.')
    parser.add_argument(
        '--elo-tournament-pairs',
        type=int,
        default=0,
        help='Mirrored deal pairs per round-robin match for elo-kbest.',
    )
    parser.add_argument('--elo-k-factor', type=float, default=32.0)
    parser.add_argument('--elo-tournament-seed', type=int, default=2026085201)
    parser.add_argument(
        '--elo-tournament-provenance-file',
        default='',
        help=(
            'Required elo-kbest hash-chained JSONL mirror. The checkpoint is '
            'authoritative and rewrites this file atomically after each save.'
        ),
    )
    parser.add_argument('--fixed-opponent-checkpoint', default='',
                        help='Discovery mode: replace the historical pool with one frozen opponent '
                             'checkpoint. May be mixed with hero self-play through '
                             '--self-play-fraction.')
    parser.add_argument('--fixed-opponent-checkpoints', nargs='+', default=[],
                        help='Discovery mode: frozen opponent ensemble. May be combined with '
                             '--fixed-opponent-checkpoint and hero self-play.')
    parser.add_argument(
        '--initial-opponent-checkpoints',
        nargs='+',
        default=[],
        help=(
            'Seed a historical opponent pool from frozen checkpoints while '
            'keeping periodic learned snapshot insertion enabled. Unlike '
            '--fixed-opponent-checkpoints, membership may change under the '
            'selected K-best strategy.'
        ),
    )
    parser.add_argument('--hero-policy-mode', choices=('sample', 'greedy'), default='sample',
                        help='Hero action selection during rollout. Training normally samples; '
                             'greedy with lr=0 provides a fast local fixed-opponent screen.')
    parser.add_argument(
        '--hero-policy-temperature',
        type=float,
        default=1.0,
        help=(
            'Positive stochastic hero temperature used identically by rollout '
            'behavior and PPO likelihoods. One preserves existing behavior.'
        ),
    )
    parser.add_argument('--archive-checkpoint-every', type=int, default=0,
                        help='Also save checkpoint_iterXXXXXX.pt every N PPO updates. '
                             '0 disables archival checkpoints.')
    parser.add_argument('--self-play-fraction', type=float, default=0.2,
                        help='Probability of hero-vs-hero instead of a pool opponent.')
    parser.add_argument(
        '--procedural-opponent-fraction',
        type=float,
        default=0.0,
        help=(
            'Single-rollout research mode: among external-opponent hands, '
            'replace this fraction with independently seeded per-hand '
            'procedural styles. Hero PPO action sampling is unchanged.'
        ),
    )
    parser.add_argument('--opponent-assignment', choices=('per-iteration', 'per-group', 'per-worker'),
                        default='per-iteration',
                        help='per-iteration keeps all workers on one sampled mode/snapshot for larger '
                             'inference batches; per-group is EXP-005 balanced group mixtures; '
                             'per-worker is the original independent sampler.')
    parser.add_argument('--opponent-groups', type=int, default=5,
                        help='EXP-005: balanced worker groups used by --opponent-assignment per-group.')
    parser.add_argument(
        '--adaptive-opponent-league',
        action='store_true',
        help=(
            'Update fixed or seeded historical-opponent sampling probabilities '
            'from EMA hero reward, emphasizing opponents with lower hero EV.'
        ),
    )
    parser.add_argument(
        '--adaptive-league-ema',
        type=float,
        default=0.9,
        help='EMA retention for per-opponent hero reward.',
    )
    parser.add_argument(
        '--adaptive-league-temperature-bb',
        type=float,
        default=2.0,
        help='Softmax temperature for negative hero mean reward in BB/hand.',
    )
    parser.add_argument(
        '--adaptive-league-min-probability',
        type=float,
        default=0.05,
        help='Minimum fixed-opponent probability before normalization.',
    )
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
    parser.add_argument(
        '--fixed-training-deal-start-index',
        type=int,
        default=0,
        help=(
            'Recovery-only per-worker/env deal cursor offset. Set to at least '
            'the inherited global hand count when an older checkpoint did not '
            'serialize worker cursors, preventing overlap with earlier decks.'
        ),
    )
    parser.add_argument(
        '--resume-assignment-state-from-provenance',
        action='store_true',
        help=(
            'Recovery-only: verify and replay the complete per-group adaptive '
            'assignment evidence chain, restore Python RNG state, and reuse an '
            'already-recorded pending next-iteration assignment.'
        ),
    )
    parser.add_argument('--trace-transitions-file', default=None,
                        help='EXP-002 debug: write one sha256 digest per transition in arrival order '
                             '(equivalence testing only; adds overhead).')
    parser.add_argument('--validate-stream', action='store_true',
                        help='EXP-002 debug: assert hand-block structure of every received pipe '
                        'message (GAE contiguity invariant). Use in smokes/validation only.')
    parser.add_argument('--mirror-self-play-deals', action='store_true',
                        help='EXP-003: in self-play only, replay each shuffled deal once with '
                             'P0/P1 hole cards swapped and the same future board order.')
    parser.add_argument(
        '--paired-seat-average-returns',
        action='store_true',
        help=(
            'Replay every fixed-stream deal against the same opponent with '
            'private cards swapped, and use the two-seat mean only as the '
            'actor terminal reward. Raw realized rewards remain critic targets.'
        ),
    )
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
    parser.add_argument(
        '--centralized-critic-hidden',
        type=int,
        default=0,
        help=(
            'Add a training-only critic of this width over the public trunk '
            'and a 52-way opponent-private-card encoding.'
        ),
    )
    parser.add_argument(
        '--centralized-critic',
        action='store_true',
        help=(
            'Attach privileged opponent cards to fresh transitions, recompute '
            'centralized rollout baselines before GAE, and train the '
            'centralized value head. The deployed actor remains decentralized.'
        ),
    )
    parser.add_argument(
        '--actor-ema-decay',
        type=float,
        default=0.0,
        help=(
            'Track a checkpointed post-PPO EMA of policy_head and '
            'preflop_policy_head parameters. 0 disables it.'
        ),
    )
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
    parser.add_argument(
        '--preserve-resumed-optimizer-lr',
        action='store_true',
        help=(
            'When resuming with --no-reset-optimizer, retain the learning rates '
            'stored in the checkpoint instead of applying a new target-relative '
            'linear schedule. This keeps a scale-control continuation continuous '
            'at the source endpoint learning rate.'
        ),
    )
    parser.add_argument(
        '--checkpoint-milestone-hands',
        action='append',
        type=int,
        default=[],
        help=(
            'Save a content-complete checkpoint at the first completed update '
            'crossing this total-hand threshold. May be repeated.'
        ),
    )
    parser.add_argument('--reset-hand-counter', action='store_true', default=False,
                        help='Start total_hands at 0 even if resume ckpt has higher (for V5 fresh schedule)')
    args = parser.parse_args()
    if args.total_environment_hands < 0:
        parser.error('--total-environment-hands must be non-negative')
    if args.preserve_resumed_optimizer_lr and (
        not args.resume
        or not args.allow_resume
        or args.reset_optimizer
        or args.reset_hand_counter
    ):
        parser.error(
            '--preserve-resumed-optimizer-lr requires --resume, '
            '--allow-resume, --no-reset-optimizer and an inherited hand counter'
        )
    if any(value <= 0 for value in args.checkpoint_milestone_hands):
        parser.error('--checkpoint-milestone-hands values must be positive')
    args.checkpoint_milestone_hands = sorted(
        set(args.checkpoint_milestone_hands)
    )
    fixed_opponent_paths = [
        path for path in (
            ([args.fixed_opponent_checkpoint] if args.fixed_opponent_checkpoint else [])
            + list(args.fixed_opponent_checkpoints)
        )
        if path
    ]
    fixed_opponent_active = bool(fixed_opponent_paths)
    initial_opponent_paths = [
        path for path in args.initial_opponent_checkpoints if path
    ]
    initial_opponent_active = bool(initial_opponent_paths)
    if fixed_opponent_active and initial_opponent_active:
        parser.error(
            '--fixed-opponent-checkpoints and --initial-opponent-checkpoints '
            'are mutually exclusive'
        )
    if initial_opponent_active and len(initial_opponent_paths) > args.k_best:
        parser.error('--k-best must be at least the initial opponent count')
    if args.pool_strategy == 'elo-kbest':
        if args.k_best <= 0:
            parser.error('--k-best must be positive for elo-kbest')
        if args.elo_tournament_pairs <= 0:
            parser.error('--elo-tournament-pairs must be positive for elo-kbest')
        if not math.isfinite(args.elo_k_factor) or args.elo_k_factor <= 0.0:
            parser.error('--elo-k-factor must be finite and positive')
        if not args.elo_tournament_provenance_file:
            parser.error(
                '--elo-tournament-provenance-file is required for elo-kbest'
            )
        if args.save_interval != 1:
            parser.error(
                '--save-interval must be 1 for checkpoint-synchronous '
                'elo-kbest evidence'
            )
        if args.snapshot_every <= 0:
            parser.error('--snapshot-every must be positive for elo-kbest')
        if fixed_opponent_active:
            parser.error(
                'elo-kbest requires learned snapshot insertion and is '
                'incompatible with fixed-opponent mode'
            )
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
    if args.ppo_replay_buffer_iterations < 0:
        parser.error('--ppo-replay-buffer-iterations must be >= 0')
    if args.greedy_advantage_margin_coef < 0.0:
        parser.error('--greedy-advantage-margin-coef must be nonnegative')
    if args.greedy_advantage_margin <= 0.0:
        parser.error('--greedy-advantage-margin must be positive')
    if args.greedy_advantage_margin_coef > 0.0 and args.hero_policy_mode != 'sample':
        parser.error('greedy advantage margin requires sampled hero rollouts')
    if args.source_greedy_margin_coef < 0.0:
        parser.error('--source-greedy-margin-coef must be nonnegative')
    if args.source_greedy_margin_max <= 0.0:
        parser.error('--source-greedy-margin-max must be positive')
    if args.source_greedy_margin_release_advantage < 0.0:
        parser.error('--source-greedy-margin-release-advantage must be nonnegative')
    if args.source_greedy_margin_coef > 0.0 and args.hero_policy_mode != 'sample':
        parser.error('source greedy margin requires sampled hero rollouts')
    if args.hero_policy_temperature <= 0.0:
        parser.error('--hero-policy-temperature must be positive')
    if args.hero_policy_mode != 'sample' and args.hero_policy_temperature != 1.0:
        parser.error('non-unit hero policy temperature requires sampled hero rollouts')
    if (
        args.source_greedy_margin_coef > 0.0
        and not args.source_policy_reference_checkpoint
    ):
        parser.error(
            'source greedy margin requires --source-policy-reference-checkpoint'
        )
    if args.ppo_replay_ratio < 0.0:
        parser.error('--ppo-replay-ratio must be >= 0')
    if (args.ppo_replay_buffer_iterations > 0) != (args.ppo_replay_ratio > 0.0):
        parser.error(
            '--ppo-replay-buffer-iterations and --ppo-replay-ratio must both '
            'be positive, or both zero'
        )
    if args.acknowledge_ephemeral_ppo_replay_resume and (
        not args.resume or args.ppo_replay_buffer_iterations <= 0
    ):
        parser.error(
            '--acknowledge-ephemeral-ppo-replay-resume requires --resume and '
            'enabled PPO replay'
        )
    if args.fixed_training_deal_start_index < 0:
        parser.error('--fixed-training-deal-start-index must be nonnegative')
    if args.fixed_training_deal_start_index and not args.fixed_training_deal_stream:
        parser.error(
            '--fixed-training-deal-start-index requires '
            '--fixed-training-deal-stream'
        )
    if args.resume_assignment_state_from_provenance and (
        not args.resume
        or not args.opponent_assignment_provenance_file
        or args.opponent_assignment != 'per-group'
        or not args.adaptive_opponent_league
    ):
        parser.error(
            '--resume-assignment-state-from-provenance requires --resume, '
            'adaptive per-group assignment, and a provenance file'
        )
    if not 0.0 <= args.self_play_fraction <= 1.0:
        parser.error('--self-play-fraction must be in [0, 1]')
    if not 0.0 <= args.procedural_opponent_fraction <= 1.0:
        parser.error('--procedural-opponent-fraction must be in [0, 1]')
    if args.procedural_opponent_fraction > 0.0:
        if args.rollout_mode != 'single':
            parser.error(
                '--procedural-opponent-fraction currently requires '
                '--rollout-mode single'
            )
        if args.worker_seed_base is None:
            parser.error(
                '--procedural-opponent-fraction requires --worker-seed-base '
                'for independently replayable per-hand assignments'
            )
        if args.adaptive_opponent_league:
            parser.error(
                '--procedural-opponent-fraction is incompatible with '
                '--adaptive-opponent-league'
            )
        if args.paired_seat_average_returns:
            parser.error(
                '--procedural-opponent-fraction is incompatible with '
                '--paired-seat-average-returns'
            )
    if args.adaptive_opponent_league:
        if not (fixed_opponent_active or initial_opponent_active):
            parser.error(
                '--adaptive-opponent-league requires fixed or initial opponents'
            )
        if not 0.0 <= args.adaptive_league_ema < 1.0:
            parser.error('--adaptive-league-ema must be in [0, 1)')
        if args.adaptive_league_temperature_bb <= 0.0:
            parser.error(
                '--adaptive-league-temperature-bb must be positive'
            )
        if (
            args.adaptive_league_min_probability < 0.0
            or args.adaptive_league_min_probability
            * (
                len(fixed_opponent_paths)
                if fixed_opponent_active
                else args.k_best
            )
            >= 1.0
        ):
            parser.error(
                '--adaptive-league-min-probability must be nonnegative '
                'and below 1/maximum-pool-size'
            )
    if args.rollout_mode == 'single' and args.rollout_envs_per_worker != 1:
        parser.error('--rollout-mode single requires --rollout-envs-per-worker 1 '
                     '(use --rollout-mode multi for M > 1)')
    if args.paired_seat_average_returns:
        if args.rollout_mode != 'single':
            parser.error(
                '--paired-seat-average-returns currently requires '
                '--rollout-mode single'
            )
        if not args.mirror_self_play_deals:
            parser.error(
                '--paired-seat-average-returns requires '
                '--mirror-self-play-deals'
            )
        if not args.fixed_training_deal_stream:
            parser.error(
                '--paired-seat-average-returns requires '
                '--fixed-training-deal-stream'
            )
        if args.ppo_replay_ratio > 0.0:
            parser.error(
                '--paired-seat-average-returns is incompatible with PPO replay'
            )
        if args.allin_runout_ev or args.showdown_ev_value_targets:
            parser.error(
                '--paired-seat-average-returns isolates actor credit and cannot '
                'combine with reward or critic-target replacement'
            )
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
    if args.policy_advantage_clip < 0.0:
        parser.error('--policy-advantage-clip must be >= 0')
    if args.action_normalization_min_rows < 2:
        parser.error('--action-normalization-min-rows must be >= 2')
    if args.action_q_hidden < 0:
        parser.error('--action-q-hidden must be >= 0')
    if args.action_q_advantage and args.action_q_hidden <= 0:
        parser.error('--action-q-advantage requires --action-q-hidden > 0')
    if args.action_q_loss_coef < 0.0:
        parser.error('--action-q-loss-coef must be >= 0')
    if args.action_q_residual_l2_coef < 0.0:
        parser.error('--action-q-residual-l2-coef must be >= 0')
    if args.action_q_support_prior_rows < 0.0:
        parser.error('--action-q-support-prior-rows must be >= 0')
    if not 0.0 <= args.action_q_policy_mix <= 1.0:
        parser.error('--action-q-policy-mix must be in [0, 1]')
    if args.action_q_policy_mix < 1.0 and not args.action_q_advantage:
        parser.error(
            '--action-q-policy-mix below 1 requires --action-q-advantage'
        )
    counterfactual_replay_enabled = bool(
        args.action_q_counterfactual_dataset
        or args.action_q_counterfactual_dataset_sha256
        or args.action_q_counterfactual_loss_coef > 0.0
        or args.action_q_counterfactual_policy_loss_coef > 0.0
    )
    counterfactual_q_replay_enabled = bool(
        args.action_q_counterfactual_loss_coef > 0.0
    )
    if counterfactual_q_replay_enabled and not args.action_q_advantage:
        parser.error(
            'counterfactual Q-value replay requires --action-q-advantage'
        )
    if args.restart_counterfactual_replay_state and (
        not args.resume
        or not args.allow_resume
        or args.reset_optimizer
        or args.reset_hand_counter
        or not counterfactual_replay_enabled
    ):
        parser.error(
            '--restart-counterfactual-replay-state requires --resume, '
            '--allow-resume, --no-reset-optimizer, an inherited hand counter, '
            'and enabled counterfactual replay'
        )
    if counterfactual_replay_enabled and (
        not args.action_q_counterfactual_dataset
        or not args.action_q_counterfactual_dataset_sha256
        or (
            args.action_q_counterfactual_loss_coef <= 0.0
            and args.action_q_counterfactual_policy_loss_coef <= 0.0
        )
    ):
        parser.error(
            'counterfactual Action-Q replay requires dataset, SHA256, and a '
            'positive Q or soft-policy loss coefficient'
        )
    if (
        args.action_q_advantage
        and args.action_q_policy_mix > 0.0
        and args.action_q_loss_coef <= 0.0
        and args.action_q_counterfactual_loss_coef <= 0.0
    ):
        parser.error(
            'positive --action-q-policy-mix requires chosen-action or '
            'counterfactual Q supervision'
        )
    if args.action_q_counterfactual_loss_coef < 0.0:
        parser.error('--action-q-counterfactual-loss-coef must be nonnegative')
    if args.action_q_counterfactual_policy_loss_coef < 0.0:
        parser.error(
            '--action-q-counterfactual-policy-loss-coef must be nonnegative'
        )
    if args.action_q_counterfactual_policy_target_clip <= 0.0:
        parser.error(
            '--action-q-counterfactual-policy-target-clip must be positive'
        )
    if args.action_q_counterfactual_policy_temperature <= 0.0:
        parser.error(
            '--action-q-counterfactual-policy-temperature must be positive'
        )
    if args.action_q_counterfactual_lcb_z < 0.0:
        parser.error('--action-q-counterfactual-lcb-z must be nonnegative')
    if args.action_q_counterfactual_loss_decay_hands < 0:
        parser.error(
            '--action-q-counterfactual-loss-decay-hands must be nonnegative'
        )
    if (
        args.action_q_counterfactual_loss_decay_hands > 0
        and not counterfactual_replay_enabled
    ):
        parser.error(
            '--action-q-counterfactual-loss-decay-hands requires replay data'
        )
    if args.action_q_counterfactual_batch_size <= 0:
        parser.error('--action-q-counterfactual-batch-size must be positive')
    if args.action_q_counterfactual_max_batches_per_update < 0:
        parser.error(
            '--action-q-counterfactual-max-batches-per-update must be '
            'nonnegative'
        )
    if args.action_q_counterfactual_uncertainty_floor_bb <= 0.0:
        parser.error(
            '--action-q-counterfactual-uncertainty-floor-bb must be positive'
        )
    if args.action_q_counterfactual_max_weight_ratio < 1.0:
        parser.error(
            '--action-q-counterfactual-max-weight-ratio must be at least one'
        )
    if (
        args.action_q_counterfactual_validation_fraction <= 0.0
        or args.action_q_counterfactual_test_fraction <= 0.0
        or args.action_q_counterfactual_validation_fraction
        + args.action_q_counterfactual_test_fraction
        >= 0.8
    ):
        parser.error(
            'counterfactual validation/test fractions must be positive and '
            'sum to less than 0.8'
        )
    if (
        args.action_q_support_prior_rows > 0.0
        and not args.action_q_advantage
    ):
        parser.error(
            '--action-q-support-prior-rows requires --action-q-advantage'
        )
    if args.action_q_dueling and not args.action_q_advantage:
        parser.error('--action-q-dueling requires --action-q-advantage')
    if (
        args.action_q_residual_l2_coef > 0.0
        and not args.action_q_dueling
    ):
        parser.error(
            '--action-q-residual-l2-coef requires --action-q-dueling'
        )
    if args.action_q_advantage and args.critic_head_only_gradient:
        parser.error(
            '--action-q-advantage cannot combine with '
            '--critic-head-only-gradient'
        )
    if args.source_policy_kl_coef < 0.0:
        parser.error('--source-policy-kl-coef must be >= 0')
    if (
        args.source_policy_kl_temperature is not None
        and args.source_policy_kl_temperature <= 0.0
    ):
        parser.error('--source-policy-kl-temperature must be positive')
    if args.gradient_diagnostic_minibatches < 0:
        parser.error('--gradient-diagnostic-minibatches must be >= 0')
    if args.gradient_noise_hand_groups < 0 or args.gradient_noise_hand_groups == 1:
        parser.error('--gradient-noise-hand-groups must be zero or >=2')
    if args.gradient_noise_hand_groups and (
        not args.all_policy_heads_only_training or args.ppo_replay_ratio > 0
        or args.policy_postflop_only or args.action_q_advantage or args.preflop_teacher_coef
        or args.postflop_action_prior_coef or args.preflop_action_prior_coef
        or args.preflop_sb_open_action_prior_coef or args.preflop_bb_vs_open_action_prior_coef
        or args.action_q_counterfactual_policy_loss_coef
    ):
        parser.error('Hand-noise probes require native all-policy-heads-only fresh fp32 ordinary PPO')
    if (
        args.source_policy_kl_coef > 0.0
        or args.source_greedy_margin_coef > 0.0
    ) and not args.resume:
        parser.error('source-policy regularization requires --resume')
    if (
        args.source_policy_reference_checkpoint
        and args.source_policy_kl_coef <= 0.0
        and args.source_greedy_margin_coef <= 0.0
    ):
        parser.error(
            '--source-policy-reference-checkpoint requires positive source '
            'KL or source greedy margin coefficient'
        )
    if args.policy_position_only != 'all' and not args.policy_postflop_only:
        parser.error(
            '--policy-position-only bb/sb requires --policy-postflop-only'
        )
    if args.policy_street_max < 3 and not args.policy_postflop_only:
        parser.error(
            '--policy-street-max below3 requires --policy-postflop-only'
        )
    if args.policy_street_min > 1 and not args.policy_postflop_only:
        parser.error(
            '--policy-street-min above1 requires --policy-postflop-only'
        )
    if args.policy_street_min > args.policy_street_max:
        parser.error(
            '--policy-street-min must be <= --policy-street-max'
        )
    if args.preflop_teacher_coef < 0.0:
        parser.error('--preflop-teacher-coef must be >= 0')
    if args.preflop_head_lr < 0.0:
        parser.error('--preflop-head-lr must be >= 0')
    if args.preflop_head_lr > 0.0 and not args.separate_preflop_head:
        parser.error('positive --preflop-head-lr requires --separate-preflop-head')
    if args.all_policy_heads_only_training and not args.separate_preflop_head:
        parser.error(
            '--all-policy-heads-only-training requires '
            '--separate-preflop-head'
        )
    if args.preflop_head_only_training and not args.separate_preflop_head:
        parser.error(
            '--preflop-head-only-training requires --separate-preflop-head'
        )
    if args.postflop_adapter_hidden < 0:
        parser.error('--postflop-adapter-hidden must be >= 0')
    if args.position_adapter_hidden < 0:
        parser.error('--position-adapter-hidden must be >= 0')
    if args.flat_sequence_policy_adapter_hidden < 0:
        parser.error('--flat-sequence-policy-adapter-hidden must be >= 0')
    if args.causal_sequence_policy_adapter_hidden < 0:
        parser.error('--causal-sequence-policy-adapter-hidden must be >= 0')
    if args.centralized_critic_hidden < 0:
        parser.error('--centralized-critic-hidden must be >= 0')
    if args.centralized_critic and args.centralized_critic_hidden <= 0:
        parser.error('--centralized-critic requires --centralized-critic-hidden > 0')
    if args.centralized_critic and args.critic_contract != CRITIC_V2:
        parser.error('--centralized-critic requires --critic-contract critic_v2')
    if args.centralized_critic and not args.all_policy_heads_only_training:
        parser.error(
            '--centralized-critic requires --all-policy-heads-only-training'
        )
    if args.centralized_critic and (
        args.ppo_replay_ratio > 0 or args.ppo_replay_buffer_iterations > 0
    ):
        parser.error('--centralized-critic does not support PPO replay')
    if not 0.0 <= args.actor_ema_decay < 1.0:
        parser.error('--actor-ema-decay must be in [0, 1)')
    if args.actor_ema_decay > 0.0 and not args.all_policy_heads_only_training:
        parser.error(
            '--actor-ema-decay requires --all-policy-heads-only-training'
        )
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
        args.flat_sequence_adapter_only_training
        and args.flat_sequence_policy_adapter_hidden <= 0
    ):
        parser.error(
            '--flat-sequence-adapter-only-training requires '
            '--flat-sequence-policy-adapter-hidden > 0'
        )
    if (
        args.causal_sequence_adapter_only_training
        and args.causal_sequence_policy_adapter_hidden <= 0
    ):
        parser.error(
            '--causal-sequence-adapter-only-training requires '
            '--causal-sequence-policy-adapter-hidden > 0'
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
            args.flat_sequence_adapter_only_training,
            args.causal_sequence_adapter_only_training,
            args.head_only_training,
            args.all_policy_heads_only_training,
            args.preflop_head_only_training,
        )
    )
    if exclusive_training_modes > 1:
        parser.error(
            '--adapter-only-training, --position-adapter-only-training and '
            '--flat-sequence-adapter-only-training, '
            '--causal-sequence-adapter-only-training, --head-only-training and '
            '--all-policy-heads-only-training and '
            '--preflop-head-only-training are '
            'mutually exclusive'
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
        flat_sequence_policy_adapter_hidden=(
            args.flat_sequence_policy_adapter_hidden
        ),
        causal_sequence_policy_adapter_hidden=(
            args.causal_sequence_policy_adapter_hidden
        ),
        centralized_critic_hidden=args.centralized_critic_hidden,
        position_value_adapter_hidden=(
            args.position_value_adapter_hidden
        ),
        position_adapter_postflop_only=(
            bool(args.policy_postflop_only)
            and int(args.position_adapter_hidden) > 0
        ),
        position_adapter_min_street=int(args.policy_street_min),
        position_adapter_max_street=int(args.policy_street_max),
        action_q_hidden=args.action_q_hidden,
        action_q_dueling=args.action_q_dueling,
    ).to(device)
    dc = torch.zeros(1, 6, 4, 13, device=device)
    da = torch.zeros(1, 25, 4, 5, device=device)
    de = torch.zeros(1, EXTRA_SIZE, device=device)
    model(dc, da, de)
    print(f'Parameters: {count_parameters(model):,}')

    if args.causal_sequence_adapter_only_training:
        trainable_prefixes = (
            'causal_sequence_token.',
            'causal_sequence_convs.',
            'causal_sequence_trunk_norm.',
            'causal_sequence_policy_adapters.',
            'value_head.',
        )
        for name, parameter in model.named_parameters():
            parameter.requires_grad = name.startswith(trainable_prefixes)
        trainable_count = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )
        optimizer = torch.optim.Adam(
            [parameter for parameter in model.parameters() if parameter.requires_grad],
            lr=args.lr,
        )
        print(
            f'Causal-sequence-adapter-only training: {trainable_count:,} '
            'trainable parameters (18 actor tensors + value head)'
        )
    elif args.flat_sequence_adapter_only_training:
        trainable_prefixes = (
            'flat_sequence_encoder.',
            'flat_sequence_trunk_norm.',
            'flat_sequence_policy_adapters.',
            'value_head.',
        )
        for name, parameter in model.named_parameters():
            parameter.requires_grad = name.startswith(trainable_prefixes)
        trainable_count = sum(
            parameter.numel()
            for parameter in model.parameters()
            if parameter.requires_grad
        )
        optimizer = torch.optim.Adam(
            [parameter for parameter in model.parameters() if parameter.requires_grad],
            lr=args.lr,
        )
        print(
            f'Flat-sequence-adapter-only training: {trainable_count:,} '
            'trainable parameters (14 actor tensors + value head)'
        )
    elif args.position_adapter_only_training:
        trainable_prefixes = position_adapter_trainable_prefixes(
            args.position_adapter_training_seat,
            include_action_q=args.action_q_advantage,
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
    elif args.preflop_head_only_training:
        trainable_parameters = configure_preflop_head_only_training(model)
        trainable_count = sum(parameter.numel() for parameter in trainable_parameters)
        optimizer = torch.optim.Adam(trainable_parameters, lr=args.lr)
        print(
            f'Preflop-head-only training: {trainable_count:,} trainable '
            'parameters (dedicated preflop policy + public value head)'
        )
    elif args.all_policy_heads_only_training:
        trainable_prefixes = (
            (
                'policy_head.',
                'preflop_policy_head.',
                'centralized_value_head.',
            )
            if args.centralized_critic
            else (
                'policy_head.',
                'preflop_policy_head.',
                'value_head.',
            )
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
            f'All-policy-heads-only training: {trainable_count:,} trainable '
            'parameters (postflop policy + preflop policy + '
            f'{"centralized" if args.centralized_critic else "public"} value head)'
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
                'loss-kbest is a single-GPU proxy for paper K-best/ELO '
                'survivor selection; validate with internal probes and Slumbot gates.'
                if args.pool_strategy == 'loss-kbest'
                else (
                    'elo-kbest implements paper-mechanism competition/ELO '
                    'survivor selection with a deterministic mirrored small '
                    'tournament; it does not claim paper-scale tournament compute.'
                    if args.pool_strategy == 'elo-kbest'
                    else 'latest-K FIFO is an ablation/deviation from paper '
                    'K-best/ELO survivor selection.'
                )
            ),
            'action_space': '9 discrete actions: fold, check/call, six pot-fraction raises, all-in',
            'actual_hand_accounting': True,
            'training_hand_counter_semantics': 'transition_bearing_hands_v1',
            'physical_hand_counter_schema': ENVIRONMENT_HAND_ACCOUNTING_SCHEMA,
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

    from alpha_holdem.policy_contract_v6 import training_metadata as v6_training_metadata, validate_resume as v6_validate_resume
    v6_metadata = v6_training_metadata(args)
    obs_version = (
        'v4'
        if args.env_version in (
            'v4',
            'v55cap1v4obs',
            'v55v4obs',
            'v55pfv2v4obs',
            'v55preflopv2v4obs',
        )
        else ('v6' if args.env_version == 'v6' else 'v55')
    )
    resume_source = args.resume
    actor_ema_state = None
    actor_ema_updates = 0
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
    action_q_counterfactual_replay = None
    ppo_replay_entries = deque(
        maxlen=max(1, int(args.ppo_replay_buffer_iterations))
    )
    ppo_replay_rng = random.Random(
        (int(args.seed) ^ 0xA17A5EED5EED) & ((1 << 64) - 1)
    )
    ppo_replay_cumulative_rows = 0
    ppo_replay_recovery_boundaries = []
    elo_tournament_history = []
    environment_hand_counters = None
    procedural_opponent_counters = None
    environment_accounting_base = initial_environment_hand_accounting(
        None, reset_hand_counter=False, run_id=args.run_id
    )
    procedural_accounting_base = initial_procedural_opponent_accounting(
        None, reset_hand_counter=False
    )

    def current_environment_hand_accounting():
        return environment_hand_accounting_snapshot(
            environment_accounting_base, environment_hand_counters, total_hands
        )

    def current_procedural_opponent_accounting():
        return procedural_opponent_accounting_snapshot(
            procedural_accounting_base, procedural_opponent_counters
        )

    def training_target_reached():
        return environment_training_target_reached(
            legacy_hands=total_hands, legacy_target=args.total_hands,
            environment_target=args.total_environment_hands,
            accounting=current_environment_hand_accounting(),
        )

    def checkpoint_payload() -> dict:
        payload = {
            'model': model.state_dict(),
            'optimizer': optimizer.state_dict(),
            'total_hands': total_hands,
            'training_hand_counter_semantics': 'transition_bearing_hands_v1',
            'environment_hand_accounting': current_environment_hand_accounting(),
            'procedural_opponent_accounting': (
                current_procedural_opponent_accounting()
            ),
            'iteration': iteration,
            'pool_snapshots': pool.snapshots,
            'pool_strategy': pool.strategy,
            'pool_active_metadata': pool.active_metadata(),
            'pool_candidate_history': pool.candidate_history,
            'elo_tournament_history': copy.deepcopy(elo_tournament_history),
            'elo_tournament_evaluation_hands': int(sum(
                int(row.get('evaluation_hands', 0))
                for row in elo_tournament_history
            )),
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
            **v6_metadata,
            'actual_hand_accounting': True,
            'critic_contract': args.critic_contract,
            'norm_layer': args.norm_layer,
            'separate_preflop_head': bool(args.separate_preflop_head),
            'postflop_adapter_hidden': int(args.postflop_adapter_hidden),
            'position_adapter_hidden': int(args.position_adapter_hidden),
            'flat_sequence_policy_adapter_hidden': int(
                args.flat_sequence_policy_adapter_hidden
            ),
            'causal_sequence_policy_adapter_hidden': int(
                args.causal_sequence_policy_adapter_hidden
            ),
            'centralized_critic_hidden': int(args.centralized_critic_hidden),
            'centralized_critic': bool(args.centralized_critic),
            'actor_ema_decay': float(args.actor_ema_decay),
            'actor_ema_updates': int(actor_ema_updates),
            'actor_ema_parameter_names': (
                list(actor_ema_state) if actor_ema_state is not None else []
            ),
            'position_value_adapter_hidden': int(
                args.position_value_adapter_hidden
            ),
            'position_adapter_postflop_only': (
                bool(args.policy_postflop_only)
                and int(args.position_adapter_hidden) > 0
            ),
            'position_adapter_min_street': int(args.policy_street_min),
            'position_adapter_max_street': int(args.policy_street_max),
            'adapter_only_training': bool(args.adapter_only_training),
            'all_policy_heads_only_training': bool(
                args.all_policy_heads_only_training
            ),
            'preflop_head_only_training': bool(
                args.preflop_head_only_training
            ),
            'position_adapter_only_training': bool(
                args.position_adapter_only_training
            ),
            'flat_sequence_adapter_only_training': bool(
                args.flat_sequence_adapter_only_training
            ),
            'causal_sequence_adapter_only_training': bool(
                args.causal_sequence_adapter_only_training
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
            'adaptive_opponent_ema_rewards': list(
                adaptive_opponent_ema_rewards
            ),
            'adaptive_opponent_weights': list(
                adaptive_opponent_weights
            ),
            'adaptive_opponent_observations': list(
                adaptive_opponent_observations
            ),
            'action_q_counterfactual_replay_state': (
                replay_checkpoint_state(action_q_counterfactual_replay)
            ),
            'ppo_replay_entries': list(ppo_replay_entries),
            'ppo_replay_rng_state': ppo_replay_rng.getstate(),
            'ppo_replay_cumulative_rows': int(
                ppo_replay_cumulative_rows
            ),
            'ppo_replay_recovery_boundaries': list(
                ppo_replay_recovery_boundaries
            ),
        }
        if actor_ema_state is not None:
            payload['actor_ema_state'] = {
                name: value.clone()
                for name, value in actor_ema_state.items()
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
            'training_hand_counter_semantics': 'transition_bearing_hands_v1',
            'environment_hand_accounting': current_environment_hand_accounting(),
            'procedural_opponent_accounting': (
                current_procedural_opponent_accounting()
            ),
        }
        # Terminal and resume-boundary writes do not recompute iteration
        # metrics.  Preserve the last complete metrics snapshot instead of
        # silently deleting replay exposure and other live diagnostics.
        if 'latest_metrics' not in extra and manifest_path.is_file():
            try:
                prior_manifest = json.loads(
                    manifest_path.read_text(encoding='utf-8-sig')
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                prior_manifest = {}
            if isinstance(prior_manifest.get('latest_metrics'), dict):
                manifest['latest_metrics'] = prior_manifest['latest_metrics']
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, sort_keys=True)

    total_hands = 0
    iteration = 0
    ckpt = None
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        v6_validate_resume(args, ckpt)
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
                source_has_flat_sequence_adapter = (
                    'flat_sequence_policy_adapters.0.0.weight' in source_actor
                )
                adding_flat_sequence_adapter = (
                    args.flat_sequence_policy_adapter_hidden > 0
                    and not source_has_flat_sequence_adapter
                )
                source_has_causal_sequence_adapter = (
                    'causal_sequence_policy_adapters.0.0.weight' in source_actor
                )
                adding_causal_sequence_adapter = (
                    args.causal_sequence_policy_adapter_hidden > 0
                    and not source_has_causal_sequence_adapter
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
                if adding_flat_sequence_adapter:
                    allowed_new_actor_keys.update({
                        f'flat_sequence_encoder.{layer}.{parameter}'
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                    allowed_new_actor_keys.update({
                        f'flat_sequence_trunk_norm.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    allowed_new_actor_keys.update({
                        f'flat_sequence_policy_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if adding_causal_sequence_adapter:
                    allowed_new_actor_keys.update({
                        f'causal_sequence_token.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    allowed_new_actor_keys.update({
                        f'causal_sequence_convs.{layer}.{parameter}'
                        for layer in (0, 1, 2)
                        for parameter in ('weight', 'bias')
                    })
                    allowed_new_actor_keys.update({
                        f'causal_sequence_trunk_norm.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    allowed_new_actor_keys.update({
                        f'causal_sequence_policy_adapters.{seat}.{layer}.{parameter}'
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
                if adding_flat_sequence_adapter:
                    print(
                        'Initialized zero-output flat-sequence policy adapter '
                        'during critic_v2 reset'
                    )
                if adding_causal_sequence_adapter:
                    print(
                        'Initialized zero-output causal-sequence policy adapter '
                        'during critic_v2 reset'
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
            source_has_flat_sequence_adapter = (
                'flat_sequence_policy_adapters.0.0.weight' in ckpt['model']
            )
            adding_flat_sequence_adapter = (
                args.flat_sequence_policy_adapter_hidden > 0
                and not source_has_flat_sequence_adapter
            )
            source_has_causal_sequence_adapter = (
                'causal_sequence_policy_adapters.0.0.weight' in ckpt['model']
            )
            adding_causal_sequence_adapter = (
                args.causal_sequence_policy_adapter_hidden > 0
                and not source_has_causal_sequence_adapter
            )
            source_has_centralized_critic = (
                'centralized_value_head.0.weight' in ckpt['model']
            )
            adding_centralized_critic = (
                args.centralized_critic_hidden > 0
                and not source_has_centralized_critic
            )
            source_has_action_q = (
                'action_q_head.0.weight' in ckpt['model']
            )
            adding_action_q = (
                args.action_q_hidden > 0
                and not source_has_action_q
            )
            if (
                adding_preflop_head
                or adding_postflop_adapter
                or adding_position_adapter
                or adding_position_value_adapter
                or adding_flat_sequence_adapter
                or adding_causal_sequence_adapter
                or adding_centralized_critic
                or adding_action_q
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
                if adding_flat_sequence_adapter:
                    expected_missing.update({
                        f'flat_sequence_encoder.{layer}.{parameter}'
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                    expected_missing.update({
                        f'flat_sequence_trunk_norm.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    expected_missing.update({
                        f'flat_sequence_policy_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if adding_causal_sequence_adapter:
                    expected_missing.update({
                        f'causal_sequence_token.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    expected_missing.update({
                        f'causal_sequence_convs.{layer}.{parameter}'
                        for layer in (0, 1, 2)
                        for parameter in ('weight', 'bias')
                    })
                    expected_missing.update({
                        f'causal_sequence_trunk_norm.{parameter}'
                        for parameter in ('weight', 'bias')
                    })
                    expected_missing.update({
                        f'causal_sequence_policy_adapters.{seat}.{layer}.{parameter}'
                        for seat in (0, 1)
                        for layer in (0, 2)
                        for parameter in ('weight', 'bias')
                    })
                if adding_centralized_critic:
                    expected_missing.update({
                        f'centralized_value_head.{layer}.{parameter}'
                        for layer in (0, 2, 4)
                        for parameter in ('weight', 'bias')
                    })
                if adding_action_q:
                    expected_missing.update({
                        f'action_q_head.{layer}.{parameter}'
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
                if adding_flat_sequence_adapter:
                    print(
                        'Initialized zero-output flat-sequence policy adapter'
                    )
                if adding_causal_sequence_adapter:
                    print(
                        'Initialized zero-output causal-sequence policy adapter'
                    )
                if adding_centralized_critic:
                    print('Initialized training-only centralized value head')
                if adding_action_q:
                    print(
                        'Initialized zero-output action-conditioned Q head'
                    )
            else:
                model.load_state_dict(ckpt['model'])
            if not args.reset_optimizer:
                if (
                    adding_preflop_head
                    or adding_postflop_adapter
                    or adding_position_adapter
                    or adding_position_value_adapter
                    or adding_flat_sequence_adapter
                    or adding_causal_sequence_adapter
                    or adding_centralized_critic
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
        environment_accounting_base = initial_environment_hand_accounting(
            ckpt, reset_hand_counter=args.reset_hand_counter, run_id=args.run_id
        )
        procedural_accounting_base = initial_procedural_opponent_accounting(
            ckpt, reset_hand_counter=args.reset_hand_counter
        )
        if args.total_environment_hands > 0:
            if training_target_reached():  # Also fails on unknown historical prefixes.
                raise ValueError('physical-hand target already reached; no training started')

        if args.ppo_replay_buffer_iterations > 0:
            serialized_replay = ckpt.get('ppo_replay_entries')
            if serialized_replay is not None:
                for entry in list(serialized_replay)[
                    -int(args.ppo_replay_buffer_iterations):
                ]:
                    ppo_replay_entries.append(entry)
                if ckpt.get('ppo_replay_rng_state') is None:
                    raise RuntimeError(
                        'serialized PPO replay buffer has no RNG state'
                    )
                ppo_replay_rng.setstate(ckpt['ppo_replay_rng_state'])
                ppo_replay_cumulative_rows = int(
                    ckpt.get('ppo_replay_cumulative_rows', 0)
                )
                ppo_replay_recovery_boundaries = list(
                    ckpt.get('ppo_replay_recovery_boundaries') or []
                )
                print(
                    'Restored serialized complete-hand PPO replay state: '
                    f'entries={len(ppo_replay_entries)} '
                    f'cumulative_rows={ppo_replay_cumulative_rows:,}'
                )
            else:
                if not args.acknowledge_ephemeral_ppo_replay_resume:
                    raise RuntimeError(
                        'resumed checkpoint predates PPO replay serialization; '
                        'pass --acknowledge-ephemeral-ppo-replay-resume only '
                        'after documenting the cold-start boundary'
                    )
                if (
                    args.fixed_training_deal_stream
                    and int(args.fixed_training_deal_start_index)
                    < int(total_hands)
                ):
                    raise RuntimeError(
                        'recovery deal start index must be at least the '
                        'inherited global hand count to prevent deck overlap'
                    )
                prior_metrics_path = run_dir / 'h1_training_metrics.jsonl'
                prior_metrics = []
                if prior_metrics_path.is_file():
                    prior_metrics = [
                        json.loads(line)
                        for line in prior_metrics_path.read_text(
                            encoding='utf-8'
                        ).splitlines()
                        if line.strip()
                    ]
                boundary_metric = next(
                    (
                        row for row in reversed(prior_metrics)
                        if int(row.get('iteration', -1)) == int(iteration)
                        and int(row.get('hands', -1)) == int(total_hands)
                    ),
                    None,
                )
                if boundary_metric is None:
                    raise RuntimeError(
                        'cannot recover PPO replay cumulative accounting: '
                        'checkpoint boundary metric is missing'
                    )
                ppo_replay_cumulative_rows = int(
                    boundary_metric.get('ppo_replay_cumulative_rows', 0)
                )
                recovery_boundary = {
                    'iteration': int(iteration),
                    'hands': int(total_hands),
                    'reason': (
                        'legacy_checkpoint_missing_complete_hand_replay_state'
                    ),
                    'first_resumed_update_replay_rows': 0,
                }
                ppo_replay_recovery_boundaries.append(recovery_boundary)
                ppo_replay_rng.seed(
                    (
                        int(args.seed)
                        ^ 0xA17A5EED5EED
                        ^ int(total_hands)
                    )
                    & ((1 << 64) - 1)
                )
                print(
                    'Acknowledged PPO replay cold-start recovery boundary: '
                    f'iteration={iteration} hands={total_hands:,}; '
                    'model/optimizer/accounting remain continuous'
                )

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
        if 'pool_snapshots' in ckpt and not args.v6_rebind_legacy_weights:
            pool.load_from_checkpoint(
                ckpt.get('pool_snapshots') or [],
                candidate_history=ckpt.get('pool_candidate_history'),
            )
        if args.pool_strategy == 'elo-kbest' and str(
            ckpt.get('run_id') or ''
        ) == str(args.run_id):
            if 'elo_tournament_history' not in ckpt and int(iteration) > 0:
                raise RuntimeError(
                    'same-run elo-kbest checkpoint is missing tournament history'
                )
            elo_tournament_history = copy.deepcopy(
                ckpt.get('elo_tournament_history') or []
            )
            print(
                'Restored checkpoint-backed ELO tournament history: '
                f'tournaments={len(elo_tournament_history)} '
                f'evaluation_hands={sum(int(row.get("evaluation_hands", 0)) for row in elo_tournament_history):,}'
            )
        print(
            f'Resumed: {total_hands:,} hands, pool={pool.size()} '
            f'(strategy={pool.strategy}, active_ids={pool.active_ids()}, '
            f'fresh_from_zero_lineage={fresh_from_zero_lineage})'
        )

    resume_is_same_run = bool(
        ckpt is not None and str(ckpt.get('run_id') or '') == str(args.run_id)
    )
    seed_initial_pool = bool(
        initial_opponent_active and not resume_is_same_run
    )
    if fixed_opponent_active or seed_initial_pool:
        seed_paths = (
            fixed_opponent_paths
            if fixed_opponent_active
            else initial_opponent_paths
        )
        pool = OpponentPool(
            k=(len(seed_paths) if fixed_opponent_active else args.k_best),
            strategy=('latest' if fixed_opponent_active else args.pool_strategy),
            history_limit=(
                len(seed_paths)
                if fixed_opponent_active
                else args.pool_history_limit
            ),
        )
        for fixed_path_text in seed_paths:
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
                    'kind': (
                        'fixed_external_opponent'
                        if fixed_opponent_active
                        else 'initial_external_opponent'
                    ),
                    'checkpoint': str(fixed_path),
                    'checkpoint_sha256': sha256_path(fixed_path),
                    'norm_layer': fixed_norm_layer,
                    'position_adapter_postflop_only': bool(
                        fixed_checkpoint.get(
                            'position_adapter_postflop_only'
                        )
                        or (
                            fixed_checkpoint.get('config') or {}
                        ).get('position_adapter_postflop_only')
                    ),
                    'position_adapter_min_street': int(
                        fixed_checkpoint.get(
                            'position_adapter_min_street'
                        )
                        or (
                            fixed_checkpoint.get('config') or {}
                        ).get('position_adapter_min_street')
                        or 1
                    ),
                    'position_adapter_max_street': int(
                        fixed_checkpoint.get(
                            'position_adapter_max_street'
                        )
                        or (
                            fixed_checkpoint.get('config') or {}
                        ).get('position_adapter_max_street')
                        or 3
                    ),
                },
            )
            print(
                f'{"Fixed" if fixed_opponent_active else "Initial"} '
                f'opponent loaded: {fixed_path} '
                f'(norm={fixed_norm_layer})'
            )

    adaptive_opponent_ema_rewards = [0.0 for _ in range(pool.size())]
    adaptive_opponent_weights = [
        1.0 / max(pool.size(), 1)
        for _ in range(pool.size())
    ]
    adaptive_opponent_observations = [0 for _ in range(pool.size())]
    if args.adaptive_opponent_league and resume_is_same_run:
        saved_rewards = ckpt.get('adaptive_opponent_ema_rewards') or []
        saved_weights = ckpt.get('adaptive_opponent_weights') or []
        saved_observations = ckpt.get(
            'adaptive_opponent_observations'
        ) or []
        if (
            len(saved_rewards) == pool.size()
            and len(saved_weights) == pool.size()
            and len(saved_observations) == pool.size()
        ):
            adaptive_opponent_ema_rewards = [
                float(value) for value in saved_rewards
            ]
            adaptive_opponent_weights = [
                float(value) for value in saved_weights
            ]
            adaptive_opponent_observations = [
                int(value) for value in saved_observations
            ]
            print('Restored adaptive opponent-league state')

    reference_policy = None
    if (
        args.source_policy_kl_coef > 0.0
        or args.source_greedy_margin_coef > 0.0
    ):
        reference_policy = copy.deepcopy(model).to(device)
        reference_label = 'exact resume actor'
        if args.source_policy_reference_checkpoint:
            reference_path = Path(
                args.source_policy_reference_checkpoint
            ).resolve()
            if not reference_path.is_file():
                raise FileNotFoundError(
                    f'source-policy reference checkpoint not found: '
                    f'{reference_path}'
                )
            reference_checkpoint = torch.load(
                reference_path,
                map_location=device,
                weights_only=False,
            )
            reference_state = reference_checkpoint.get(
                'model',
                reference_checkpoint,
            )
            target_reference_state = reference_policy.state_dict()
            missing_reference_keys = (
                set(target_reference_state) - set(reference_state)
            )
            unexpected_reference_keys = (
                set(reference_state) - set(target_reference_state)
            )
            behavior_neutral_missing_prefixes = (
                'position_policy_adapters.',
                'position_value_adapters.',
                'flat_sequence_encoder.',
                'flat_sequence_trunk_norm.',
                'flat_sequence_policy_adapters.',
                'causal_sequence_token.',
                'causal_sequence_convs.',
                'causal_sequence_trunk_norm.',
                'causal_sequence_policy_adapters.',
                'centralized_value_head.',
                'action_q_head.',
            )
            disallowed_missing = {
                name
                for name in missing_reference_keys
                if not name.startswith(behavior_neutral_missing_prefixes)
            }
            if disallowed_missing or unexpected_reference_keys:
                raise RuntimeError(
                    'source-policy reference architecture mismatch: '
                    f'disallowed_missing={sorted(disallowed_missing)[:8]} '
                    f'unexpected={sorted(unexpected_reference_keys)[:8]}'
                )
            materialized_reference_state = {}
            for name, target_tensor in target_reference_state.items():
                if name in reference_state:
                    source_tensor = reference_state[name]
                    if source_tensor.shape != target_tensor.shape:
                        raise RuntimeError(
                            'source-policy reference tensor shape mismatch: '
                            f'{name} source={tuple(source_tensor.shape)} '
                            f'target={tuple(target_tensor.shape)}'
                        )
                    materialized_reference_state[name] = source_tensor
                else:
                    # Position residuals have zero-output initialization and
                    # Action-Q is training-only. Zeroing every absent tensor
                    # reconstructs an actor exactly equivalent to the older
                    # source while avoiding dependence on a later resume
                    # checkpoint's learned residuals.
                    materialized_reference_state[name] = torch.zeros_like(
                        target_tensor
                    )
            reference_policy.load_state_dict(
                materialized_reference_state,
                strict=True,
            )
            if missing_reference_keys:
                print(
                    'Materialized behavior-neutral zero source-policy '
                    'reference keys: '
                    f'{len(missing_reference_keys)}'
                )
            reference_label = (
                f'fixed checkpoint {reference_path} '
                f'sha256={sha256_path(reference_path)}'
            )
        reference_policy.eval()
        for parameter in reference_policy.parameters():
            parameter.requires_grad_(False)
        print(
            'Source-policy reference enabled: '
            f'kl_coef={args.source_policy_kl_coef:g} '
            f'greedy_margin_coef={args.source_greedy_margin_coef:g} '
            f'({reference_label})'
        )

    if args.action_q_counterfactual_dataset:
        inherited_replay_state = (
            ckpt.get('action_q_counterfactual_replay_state')
            if args.resume
            else None
        )
        resumed_replay_state = inherited_replay_state
        if args.restart_counterfactual_replay_state:
            if not inherited_replay_state:
                raise RuntimeError(
                    'counterfactual replay restart requested but the resumed '
                    'checkpoint has no inherited replay state'
                )
            inherited_sha = str(
                inherited_replay_state.get('dataset_sha256') or ''
            ).lower()
            requested_sha = str(
                args.action_q_counterfactual_dataset_sha256 or ''
            ).lower()
            if not inherited_sha or inherited_sha == requested_sha:
                raise RuntimeError(
                    'counterfactual replay restart requires a different '
                    'immutable dataset identity: '
                    f'source={inherited_sha} requested={requested_sha}'
                )
            resumed_replay_state = None
            print(
                'Restarting counterfactual replay state on a fresh dataset: '
                f'source_sha256={inherited_sha} '
                f'requested_sha256={requested_sha} '
                f'start_lineage_hands={total_hands:,}; model and optimizer '
                'state remain continuous'
            )
        if resumed_replay_state:
            try:
                validate_replay_training_config(
                    ckpt.get('config') or {},
                    vars(args),
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        try:
            (
                initial_replay_cursor,
                replay_start_hands,
                initial_replay_total_draws,
            ) = restore_replay_progress(
                resumed_replay_state,
                requested_sha256=(
                    args.action_q_counterfactual_dataset_sha256
                ),
                current_lineage_hands=total_hands,
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        action_q_counterfactual_replay = load_counterfactual_q_replay(
            args.action_q_counterfactual_dataset,
            expected_sha256=args.action_q_counterfactual_dataset_sha256,
            device=device,
            effective_stack_divisor=(
                args.h1_effective_stack_divisor
                if args.critic_contract == CRITIC_V2
                else 1.0
            ),
            split_seed=args.action_q_counterfactual_split_seed,
            validation_fraction=(
                args.action_q_counterfactual_validation_fraction
            ),
            test_fraction=args.action_q_counterfactual_test_fraction,
            uncertainty_floor_bb=(
                args.action_q_counterfactual_uncertainty_floor_bb
            ),
            max_weight_ratio=(
                args.action_q_counterfactual_max_weight_ratio
            ),
            target_mode=args.action_q_counterfactual_target_mode,
            lcb_z=args.action_q_counterfactual_lcb_z,
            initial_cursor=initial_replay_cursor,
            initial_total_draws=initial_replay_total_draws,
            stratify_trajectory_opponent=(
                args.action_q_counterfactual_stratify_trajectory_opponent
            ),
        )
        if resumed_replay_state:
            try:
                validate_replay_metadata_contract(
                    resumed_replay_state,
                    action_q_counterfactual_replay['metadata'],
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
        action_q_counterfactual_replay['metadata'][
            'start_lineage_training_hands'
        ] = replay_start_hands
        replay_meta = action_q_counterfactual_replay['metadata']
        print(
            'Loaded held-out-safe all-action Q replay: '
            f"train={replay_meta['training_rows']:,} "
            f"validation={replay_meta['validation_rows_held_out']:,} "
            f"test={replay_meta['test_rows_held_out']:,} "
            f"sha256={replay_meta['dataset_sha256']} "
            f"cursor={action_q_counterfactual_replay['cursor']}"
        )

    if args.actor_ema_decay > 0.0:
        if ckpt is not None and not args.reset_hand_counter:
            serialized_actor_ema = ckpt.get('actor_ema_state')
            if serialized_actor_ema is None:
                raise RuntimeError(
                    'true actor-EMA resume requires serialized actor_ema_state'
                )
            source_decay = float(ckpt.get('actor_ema_decay', 0.0))
            if source_decay != float(args.actor_ema_decay):
                raise RuntimeError(
                    'actor-EMA resume decay mismatch: '
                    f'source={source_decay} requested={args.actor_ema_decay}'
                )
            expected_names = set(actor_ema_parameter_names(model))
            if set(serialized_actor_ema) != expected_names:
                raise RuntimeError('serialized actor EMA parameter keys mismatch')
            actor_ema_state = {
                name: value.detach().cpu().clone()
                for name, value in serialized_actor_ema.items()
            }
            actor_ema_updates = int(ckpt.get('actor_ema_updates', -1))
            if actor_ema_updates < 0:
                raise RuntimeError('serialized actor EMA update count is missing')
            print(
                f'Restored actor EMA: decay={args.actor_ema_decay:g} '
                f'updates={actor_ema_updates}'
            )
        else:
            actor_ema_state = initialize_actor_ema(model)
            actor_ema_updates = 0
            print(
                f'Initialized actor EMA from current source actor: '
                f'decay={args.actor_ema_decay:g} '
                f'tensors={len(actor_ema_state)}'
            )

    if not args.resume:
        init_path = run_dir / 'init.pt'
        if args.overwrite or not init_path.exists():
            torch.save({
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'total_hands': 0,
                'training_hand_counter_semantics': 'transition_bearing_hands_v1',
                'environment_hand_accounting': current_environment_hand_accounting(),
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
                **v6_metadata,
                'actual_hand_accounting': True,
            }, init_path)
    elif not out_path.exists() or args.overwrite:
        torch.save(checkpoint_payload(), args.out)
        print(
            f'  [Save] initial resume checkpoint {args.out} '
            f'({total_hands:,} hands, iter={iteration})'
        )

    write_manifest('initialized', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))
    if args.pool_strategy == 'elo-kbest':
        write_elo_tournament_evidence(
            Path(args.elo_tournament_provenance_file),
            elo_tournament_history,
        )

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

    # Prevent resumed workers from starting their first hand against the
    # temporary -1 sentinel while the full evidence-chain verification runs
    # below. A checkpoint can either have an exact pending next-iteration row,
    # or end after a consumed row and a pool-changing snapshot. In the latter
    # case a private replayed RNG generates the same assignment that the fully
    # verified global RNG will persist below.
    early_resume_assignment = None
    if args.resume_assignment_state_from_provenance:
        early_provenance_path = Path(
            args.opponent_assignment_provenance_file
        )
        early_records = [
            json.loads(line)
            for line in early_provenance_path.read_text(
                encoding='utf-8'
            ).splitlines()
            if line.strip()
        ]
        if not early_records:
            raise RuntimeError('resume assignment provenance is empty')
        early_metrics = [
            json.loads(line)
            for line in h1_metrics_jsonl_path.read_text(
                encoding='utf-8'
            ).splitlines()
            if line.strip()
        ]
        early_rng = random.Random(0)
        early_restored = restore_group_assignment_rng_from_evidence(
            early_records,
            early_metrics,
            rng=early_rng,
            seed=args.seed,
            worker_count=W,
            pool_size=pool.size(),
            pool_snapshot_ids=pool.active_ids(),
            group_count=args.opponent_groups,
            self_play_fraction=args.self_play_fraction,
            checkpoint_iteration=iteration,
            checkpoint_total_hands=total_hands,
        )
        early_resume_assignment = early_restored['pending_assignments']
        if early_resume_assignment is None:
            early_resume_assignment, _ = build_group_opponent_assignments(
                worker_count=W,
                pool_size=pool.size(),
                group_count=args.opponent_groups,
                self_play_fraction=args.self_play_fraction,
                rng=early_rng,
                pool_weights=adaptive_opponent_weights,
            )
            early_resume_assignment = early_resume_assignment.tolist()
        assigned_np[:] = early_resume_assignment

    epsilon_val = mp.Value('d', args.epsilon)
    stop_event = mp.Event()
    environment_hand_counters = mp.Array('q', 2 * W, lock=True)
    procedural_opponent_counters = mp.Array(
        'q', PROCEDURAL_COUNTER_STRIDE * W, lock=True
    )

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
                      args.mirror_self_play_deals,
                      args.paired_seat_average_returns,
                      args.allin_runout_ev,
                      args.allin_runout_ev_max_runouts,
                      args.fixed_training_deal_stream,
                      args.fixed_training_deal_start_index,
                      args.showdown_ev_value_targets,
                      args.showdown_ev_value_target_max_runouts,
                      args.showdown_ev_value_target_seed,
                      args.hero_preflop_strategy,
                      args.centralized_critic,
                      environment_hand_counters),
                daemon=True,
            )
        else:
            p = mp.Process(
                target=worker_process_v5,
                args=(w, obs_shm.name, result_shm.name, status_shm.name,
                      assigned_shm.name, request_shm.name,
                      child_conn, stop_event, epsilon_val, args.starting_stack,
                      args.env_version, w_seed,
                      args.mirror_self_play_deals,
                      args.paired_seat_average_returns,
                      args.allin_runout_ev,
                      args.allin_runout_ev_max_runouts,
                      args.fixed_training_deal_stream,
                      args.fixed_training_deal_start_index,
                      args.showdown_ev_value_targets,
                      args.showdown_ev_value_target_max_runouts,
                      args.showdown_ev_value_target_seed,
                      args.hero_preflop_strategy,
                      args.centralized_critic,
                      environment_hand_counters,
                      args.procedural_opponent_fraction,
                      procedural_opponent_counters),
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
    if args.total_environment_hands > 0:
        print(f'Physical completed-environment target: {args.total_environment_hands:,} hands (PPO boundaries)')
    print(f'Environment: {args.env_version} (obs={obs_version})')
    print(
        f'Procedural opponent: version={PROCEDURAL_OPPONENT_VERSION} '
        f'fraction={args.procedural_opponent_fraction} '
        f'profiles={len(PROCEDURAL_OPPONENT_PROFILES)}'
    )
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
                flat_sequence_policy_adapter_hidden=(
                    int(
                        snapshot_state[
                            'flat_sequence_policy_adapters.0.0.weight'
                        ].shape[0]
                    )
                    if 'flat_sequence_policy_adapters.0.0.weight' in snapshot_state
                    else 0
                ),
                causal_sequence_policy_adapter_hidden=(
                    int(
                        snapshot_state[
                            'causal_sequence_policy_adapters.0.0.weight'
                        ].shape[0]
                    )
                    if 'causal_sequence_policy_adapters.0.0.weight' in snapshot_state
                    else 0
                ),
                centralized_critic_hidden=(
                    int(
                        snapshot_state[
                            'centralized_value_head.0.weight'
                        ].shape[0]
                    )
                    if 'centralized_value_head.0.weight' in snapshot_state
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
                position_adapter_postflop_only=bool(
                    (snap.get('score_components') or {}).get(
                        'position_adapter_postflop_only',
                        False,
                    )
                ),
                position_adapter_min_street=int(
                    (snap.get('score_components') or {}).get(
                        'position_adapter_min_street',
                        1,
                    )
                ),
                position_adapter_max_street=int(
                    (snap.get('score_components') or {}).get(
                        'position_adapter_max_street',
                        3,
                    )
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
    iter_league_hands = [0 for _ in range(pool.size())]
    iter_league_reward_sums = [0.0 for _ in range(pool.size())]
    iter_start = time.time()
    inference_batch_sizes = []
    iter_exp003_metrics = exp003_metrics_template()
    iter_procedural_metrics = procedural_opponent_metrics_template()

    # Cumulative metrics for cross-iter aggregation
    cum_decisions = 0
    cum_inferences = 0

    assignment_provenance_fh = None
    assignment_provenance_records = []
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
            assignment_provenance_records = [
                json.loads(line)
                for line in provenance_path.read_text(
                    encoding='utf-8'
                ).splitlines()
                if line.strip()
            ]
            last_record = assignment_provenance_records[-1]
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
                assigned_np[:] = (
                    random.choices(
                        range(pool.size()),
                        weights=adaptive_opponent_weights,
                        k=1,
                    )[0]
                    if args.adaptive_opponent_league
                    else random.randint(0, pool.size() - 1)
                )
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
                pool_weights=(
                    adaptive_opponent_weights
                    if args.adaptive_opponent_league
                    else None
                ),
            )
            assigned_np[:] = assignments
            group_metadata = group_summary['groups']
        else:
            for w in range(W):
                if random.random() < args.self_play_fraction:
                    assigned_np[w] = -1
                else:
                    assigned_np[w] = (
                        random.choices(
                            range(pool.size()),
                            weights=adaptive_opponent_weights,
                            k=1,
                        )[0]
                        if args.adaptive_opponent_league
                        else random.randint(0, pool.size() - 1)
                    )
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
                pool_sampling_weights=(
                    adaptive_opponent_weights
                    if args.adaptive_opponent_league
                    else None
                ),
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

    pending_assignment = None
    if args.resume_assignment_state_from_provenance:
        metric_records = [
            json.loads(line)
            for line in h1_metrics_jsonl_path.read_text(
                encoding='utf-8'
            ).splitlines()
            if line.strip()
        ]
        restored_assignment = restore_group_assignment_rng_from_evidence(
            assignment_provenance_records,
            metric_records,
            rng=random,
            seed=args.seed,
            worker_count=W,
            pool_size=pool.size(),
            pool_snapshot_ids=pool.active_ids(),
            group_count=args.opponent_groups,
            self_play_fraction=args.self_play_fraction,
            checkpoint_iteration=iteration,
            checkpoint_total_hands=total_hands,
        )
        pending_assignment = restored_assignment['pending_assignments']
        print(
            'Restored assignment RNG from evidence: '
            f"records={restored_assignment['records_verified']} "
            f"tail_iter={restored_assignment['tail_iteration']} "
            f"pending={pending_assignment is not None}"
        )
    if pending_assignment is not None:
        assigned_np[:] = pending_assignment
        print(
            f'Reused recorded pending opponent assignment for '
            f'iteration {iteration + 1}'
        )
    else:
        assign_opponents()
    if early_resume_assignment is not None and assigned_np.tolist() != list(
        early_resume_assignment
    ):
        raise RuntimeError(
            'early resume assignment differs from fully verified assignment'
        )

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
    preserved_optimizer_lrs = [
        float(group['lr']) for group in optimizer.param_groups
    ]
    pending_checkpoint_milestones = [
        value
        for value in args.checkpoint_milestone_hands
        if value > total_hands
    ]
    if args.preserve_resumed_optimizer_lr:
        print(
            'Preserving resumed optimizer learning rates: '
            f'{preserved_optimizer_lrs}'
        )

    try:
        model.eval()
        last_inference_t = 0.0
        last_serve_ts = time.time()
        min_slots = args.inference_min_batch_slots
        deadline_s = max(0.0, args.inference_batch_deadline_us) / 1e6
        global_start = time.time()
        continue_training = not training_target_reached()
        while continue_training:
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
                    hero_policy_temperature=args.hero_policy_temperature,
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
                        if (
                            isinstance(data, dict)
                            and data.get('type') == 'procedural_opponent_metrics'
                        ):
                            procedural_opponent_metrics_add(
                                iter_procedural_metrics, data
                            )
                            continue
                        if isinstance(data, dict) and data.get('type') == 'league_metrics':
                            for key, value in (data.get('hands') or {}).items():
                                opponent_id = int(key)
                                if 0 <= opponent_id < pool.size():
                                    iter_league_hands[opponent_id] += int(value)
                            for key, value in (
                                data.get('hero_reward_sums') or {}
                            ).items():
                                opponent_id = int(key)
                                if 0 <= opponent_id < pool.size():
                                    iter_league_reward_sums[opponent_id] += float(
                                        value
                                    )
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

                progress = (
                    current_environment_hand_accounting()['completed_hands'] / args.total_environment_hands
                    if args.total_environment_hands > 0
                    else total_hands / args.total_hands
                )
                progress = min(progress, 1.0)
                # V5.0 default epsilon stays at 0 (no decay needed). Honor user override.
                if args.epsilon > 0.0:
                    eps_decay = max(0.0, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))
                    epsilon_val.value = eps_decay
                else:
                    eps_decay = 0.0

                # V5.0 LR schedule: linear decay over V5's own training span.
                # Start lr = args.lr (default 1e-4 ~= V4 end LR), decay to lr/3 in 2nd half.
                if progress >= 0.5 and not args.preserve_resumed_optimizer_lr:
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
                fresh_hand_blocks = split_complete_hand_blocks(iter_transitions)
                replay_transitions, ppo_replay_info = sample_replay_hand_blocks(
                    ppo_replay_entries,
                    round(len(iter_transitions) * args.ppo_replay_ratio),
                    ppo_replay_rng,
                )
                ppo_transitions = list(iter_transitions)
                ppo_transitions.extend(replay_transitions)
                if replay_transitions:
                    validate_stream_message(ppo_transitions)
                mix = action_mix(iter_transitions)
                phase_mix = action_mix_by_phase(iter_transitions)
                counterfactual_replay_elapsed_hands = 0
                effective_counterfactual_loss_coef = float(
                    args.action_q_counterfactual_loss_coef
                )
                effective_counterfactual_policy_loss_coef = float(
                    args.action_q_counterfactual_policy_loss_coef
                )
                if action_q_counterfactual_replay is not None:
                    replay_start_hands = int(
                        action_q_counterfactual_replay['metadata'][
                            'start_lineage_training_hands'
                        ]
                    )
                    (
                        effective_counterfactual_loss_coef,
                        counterfactual_replay_elapsed_hands,
                    ) = decayed_replay_coefficient(
                        args.action_q_counterfactual_loss_coef,
                        current_lineage_hands=total_hands,
                        start_lineage_hands=replay_start_hands,
                        decay_hands=(
                            args.action_q_counterfactual_loss_decay_hands
                        ),
                    )
                    effective_counterfactual_policy_loss_coef, policy_elapsed = (
                        decayed_replay_coefficient(
                            args.action_q_counterfactual_policy_loss_coef,
                            current_lineage_hands=total_hands,
                            start_lineage_hands=replay_start_hands,
                            decay_hands=(
                                args.action_q_counterfactual_loss_decay_hands
                            ),
                        )
                    )
                    if policy_elapsed != counterfactual_replay_elapsed_hands:
                        raise RuntimeError(
                            'counterfactual Q/policy replay decay clocks diverged'
                        )
                stats = trinal_clip_ppo_update(
                    model, optimizer, ppo_transitions, device,
                    epochs=args.ppo_epochs,
                    mini_batch_size=args.mini_batch_size,
                    delta1=args.delta1,
                    gamma=args.gamma,
                    gae_lambda=args.gae_lambda,
                    critic_contract=args.critic_contract,
                    effective_stack_divisor=args.h1_effective_stack_divisor,
                    value_coef=args.value_coef,
                    critic_head_only_gradient=args.critic_head_only_gradient,
                    centralized_critic=args.centralized_critic,
                    policy_advantage_clip=args.policy_advantage_clip,
                    policy_advantage_normalization=(
                        args.policy_advantage_normalization
                    ),
                    action_normalization_min_rows=(
                        args.action_normalization_min_rows
                    ),
                    greedy_advantage_margin_coef=(
                        args.greedy_advantage_margin_coef
                    ),
                    greedy_advantage_margin=args.greedy_advantage_margin,
                    source_greedy_margin_coef=(
                        args.source_greedy_margin_coef
                    ),
                    source_greedy_margin_max=(
                        args.source_greedy_margin_max
                    ),
                    source_greedy_margin_release_advantage=(
                        args.source_greedy_margin_release_advantage
                    ),
                    policy_temperature=args.hero_policy_temperature,
                    action_q_advantage=args.action_q_advantage,
                    action_q_loss_coef=args.action_q_loss_coef,
                    action_q_residual_l2_coef=(
                        args.action_q_residual_l2_coef
                    ),
                    action_q_support_prior_rows=(
                        args.action_q_support_prior_rows
                    ),
                    action_q_policy_mix=args.action_q_policy_mix,
                    action_q_counterfactual_replay=(
                        action_q_counterfactual_replay
                        if (
                            effective_counterfactual_loss_coef > 0.0
                            or effective_counterfactual_policy_loss_coef > 0.0
                        )
                        else None
                    ),
                    action_q_counterfactual_loss_coef=(
                        effective_counterfactual_loss_coef
                    ),
                    action_q_counterfactual_policy_loss_coef=(
                        effective_counterfactual_policy_loss_coef
                    ),
                    action_q_counterfactual_policy_target_clip=(
                        args.action_q_counterfactual_policy_target_clip
                    ),
                    action_q_counterfactual_policy_temperature=(
                        args.action_q_counterfactual_policy_temperature
                    ),
                    action_q_counterfactual_policy_reliability_mode=(
                        args.action_q_counterfactual_policy_reliability_mode
                    ),
                    action_q_counterfactual_batch_size=(
                        args.action_q_counterfactual_batch_size
                    ),
                    action_q_counterfactual_max_batches_per_update=(
                        args.action_q_counterfactual_max_batches_per_update
                    ),
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
                    reference_policy_temperature=(
                        args.source_policy_kl_temperature
                    ),
                    gradient_diagnostic_minibatches=args.gradient_diagnostic_minibatches,
                    gradient_noise_hand_groups=args.gradient_noise_hand_groups,
                    gradient_noise_hand_lengths=(
                        [len(block) for block in fresh_hand_blocks]
                        if args.gradient_noise_hand_groups else None
                    ),
                    policy_postflop_only=args.policy_postflop_only,
                    policy_position_only=args.policy_position_only,
                    policy_street_min=args.policy_street_min,
                    policy_street_max=args.policy_street_max,
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
                if actor_ema_state is not None:
                    update_actor_ema(
                        model,
                        actor_ema_state,
                        args.actor_ema_decay,
                    )
                    actor_ema_updates += 1
                stats['action_q_counterfactual_base_loss_coef'] = float(
                    args.action_q_counterfactual_loss_coef
                )
                stats[
                    'action_q_counterfactual_policy_base_loss_coef'
                ] = float(args.action_q_counterfactual_policy_loss_coef)
                stats['action_q_counterfactual_loss_decay_hands'] = int(
                    args.action_q_counterfactual_loss_decay_hands
                )
                stats['action_q_counterfactual_replay_elapsed_hands'] = int(
                    counterfactual_replay_elapsed_hands
                )
                stats['ppo_replay_rows'] = int(ppo_replay_info['rows'])
                stats['ppo_replay_hands'] = int(ppo_replay_info['hands'])
                stats['ppo_replay_available_rows'] = int(
                    ppo_replay_info['available_rows']
                )
                stats['ppo_replay_source_iterations'] = list(
                    ppo_replay_info['source_iterations']
                )
                stats['ppo_replay_buffer_iterations'] = int(
                    args.ppo_replay_buffer_iterations
                )
                stats['ppo_replay_ratio'] = float(args.ppo_replay_ratio)
                ppo_replay_cumulative_rows += int(ppo_replay_info['rows'])
                stats['ppo_replay_cumulative_rows'] = int(
                    ppo_replay_cumulative_rows
                )
                stats['ppo_replay_recovery_boundaries'] = list(
                    ppo_replay_recovery_boundaries
                )
                if action_q_counterfactual_replay is not None:
                    replay_training_rows = int(
                        action_q_counterfactual_replay['metadata'][
                            'training_rows'
                        ]
                    )
                    replay_total_draws = int(
                        action_q_counterfactual_replay.get('total_draws', 0)
                    )
                    stats['action_q_counterfactual_replay_total_draws'] = (
                        replay_total_draws
                    )
                    stats['action_q_counterfactual_replay_dataset_epochs'] = (
                        replay_total_draws / max(replay_training_rows, 1)
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
                    'actor_reward_override_rows': int(
                        stats.get('actor_reward_override_rows', 0)
                    ),
                    'actor_reward_override_terminal_only': bool(
                        stats.get('actor_reward_override_terminal_only', True)
                    ),
                    'raw_terminal_reward_variance': float(
                        stats.get('raw_terminal_reward_variance', 0.0)
                    ),
                    'actor_terminal_reward_variance': float(
                        stats.get('actor_terminal_reward_variance', 0.0)
                    ),
                    'actor_terminal_reward_variance_ratio': float(
                        stats.get('actor_terminal_reward_variance_ratio', 0.0)
                    ),
                    'critic_contract': args.critic_contract,
                    'position_adapter_postflop_only': (
                        bool(args.policy_postflop_only)
                        and int(args.position_adapter_hidden) > 0
                    ),
                    'position_adapter_min_street': int(
                        args.policy_street_min
                    ),
                    'position_adapter_max_street': int(
                        args.policy_street_max
                    ),
                    'advantage_by_action_slot': stats.get(
                        'advantage_by_action_slot',
                        {},
                    ),
                    'raw_advantage_by_action_slot': stats.get(
                        'raw_advantage_by_action_slot',
                        {},
                    ),
                    'advantage_by_position_street_action_slot': stats.get(
                        'advantage_by_position_street_action_slot',
                        {},
                    ),
                    'raw_advantage_by_position_street_action_slot': stats.get(
                        'raw_advantage_by_position_street_action_slot',
                        {},
                    ),
                    'policy_advantage_clip': float(
                        stats.get('policy_advantage_clip', 0.0)
                    ),
                    'policy_advantage_clip_fraction': float(
                        stats.get('policy_advantage_clip_fraction', 0.0)
                    ),
                    'greedy_advantage_margin_loss': float(
                        stats.get('greedy_advantage_margin_loss', 0.0)
                    ),
                    'greedy_advantage_margin_coef': float(
                        stats.get('greedy_advantage_margin_coef', 0.0)
                    ),
                    'greedy_advantage_margin': float(
                        stats.get('greedy_advantage_margin', 0.1)
                    ),
                    'greedy_advantage_margin_eligible_rows': int(
                        stats.get('greedy_advantage_margin_eligible_rows', 0)
                    ),
                    'greedy_advantage_margin_positive_rows': int(
                        stats.get('greedy_advantage_margin_positive_rows', 0)
                    ),
                    'greedy_advantage_margin_eligible_fraction': float(
                        stats.get('greedy_advantage_margin_eligible_fraction', 0.0)
                    ),
                    'source_greedy_margin_loss': float(
                        stats.get('source_greedy_margin_loss', 0.0)
                    ),
                    'source_greedy_margin_coef': float(
                        stats.get('source_greedy_margin_coef', 0.0)
                    ),
                    'source_greedy_margin_max': float(
                        stats.get('source_greedy_margin_max', 0.1)
                    ),
                    'source_greedy_margin_release_advantage': float(
                        stats.get('source_greedy_margin_release_advantage', 1.0)
                    ),
                    'source_greedy_margin_eligible_rows': int(
                        stats.get('source_greedy_margin_eligible_rows', 0)
                    ),
                    'source_greedy_margin_released_rows': int(
                        stats.get('source_greedy_margin_released_rows', 0)
                    ),
                    'source_greedy_margin_violation_rows': int(
                        stats.get('source_greedy_margin_violation_rows', 0)
                    ),
                    'source_greedy_margin_violation_fraction': float(
                        stats.get('source_greedy_margin_violation_fraction', 0.0)
                    ),
                    'policy_advantage_normalization': stats.get(
                        'policy_advantage_normalization',
                        'global',
                    ),
                    'hero_policy_temperature': float(
                        stats.get('policy_temperature', args.hero_policy_temperature)
                    ),
                    'policy_rows': int(
                        stats.get('policy_rows', len(ppo_transitions))
                    ),
                    'policy_street_max': int(
                        stats.get('policy_street_max', args.policy_street_max)
                    ),
                    'policy_street_min': int(
                        stats.get('policy_street_min', args.policy_street_min)
                    ),
                    'action_q_advantage': bool(
                        stats.get('action_q_advantage', False)
                    ),
                    'action_q_policy_mix': float(
                        stats.get('action_q_policy_mix', 1.0)
                    ),
                    'action_q_loss': float(
                        stats.get('action_q_loss', 0.0)
                    ),
                    'action_q_fit_loss': float(
                        stats.get('action_q_fit_loss', 0.0)
                    ),
                    'action_q_residual_l2': float(
                        stats.get('action_q_residual_l2', 0.0)
                    ),
                    'action_q_counterfactual_loss': float(
                        stats.get('action_q_counterfactual_loss', 0.0)
                    ),
                    'action_q_counterfactual_loss_coef': float(
                        stats.get(
                            'action_q_counterfactual_loss_coef',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_policy_loss': float(
                        stats.get(
                            'action_q_counterfactual_policy_loss',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_policy_loss_coef': float(
                        stats.get(
                            'action_q_counterfactual_policy_loss_coef',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_policy_target_entropy': float(
                        stats.get(
                            'action_q_counterfactual_policy_target_entropy',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_policy_target_max_probability': float(
                        stats.get(
                            'action_q_counterfactual_policy_target_max_probability',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_batch_size': int(
                        stats.get(
                            'action_q_counterfactual_batch_size',
                            0,
                        )
                    ),
                    'action_q_counterfactual_max_batches_per_update': int(
                        stats.get(
                            'action_q_counterfactual_max_batches_per_update',
                            0,
                        )
                    ),
                    'action_q_counterfactual_batches_applied': int(
                        stats.get(
                            'action_q_counterfactual_batches_applied',
                            0,
                        )
                    ),
                    'action_q_counterfactual_training_rows': int(
                        stats.get(
                            'action_q_counterfactual_training_rows',
                            0,
                        )
                    ),
                    'action_q_counterfactual_base_loss_coef': float(
                        stats.get(
                            'action_q_counterfactual_base_loss_coef',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_policy_base_loss_coef': float(
                        stats.get(
                            'action_q_counterfactual_policy_base_loss_coef',
                            0.0,
                        )
                    ),
                    'action_q_counterfactual_loss_decay_hands': int(
                        stats.get(
                            'action_q_counterfactual_loss_decay_hands',
                            0,
                        )
                    ),
                    'action_q_counterfactual_replay_elapsed_hands': int(
                        stats.get(
                            'action_q_counterfactual_replay_elapsed_hands',
                            0,
                        )
                    ),
                    'action_q_counterfactual_replay_total_draws': int(
                        stats.get(
                            'action_q_counterfactual_replay_total_draws',
                            0,
                        )
                    ),
                    'action_q_counterfactual_replay_dataset_epochs': float(
                        stats.get(
                            'action_q_counterfactual_replay_dataset_epochs',
                            0.0,
                        )
                    ),
                    'action_q_support_prior_rows': float(
                        stats.get('action_q_support_prior_rows', 0.0)
                    ),
                    'action_q_support_counts': stats.get(
                        'action_q_support_counts',
                        {},
                    ),
                    'action_q_support_weights': stats.get(
                        'action_q_support_weights',
                        {},
                    ),
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
                iteration_environment_accounting = current_environment_hand_accounting()
                trainable_decisions = len(iter_transitions)
                cum_decisions += trainable_decisions

                league_iteration_rows = []
                if args.adaptive_opponent_league:
                    for opponent_id in range(pool.size()):
                        hand_count = int(iter_league_hands[opponent_id])
                        reward_sum = float(
                            iter_league_reward_sums[opponent_id]
                        )
                        observed_mean = (
                            reward_sum / hand_count
                            if hand_count > 0
                            else None
                        )
                        if observed_mean is not None:
                            if adaptive_opponent_observations[opponent_id] == 0:
                                adaptive_opponent_ema_rewards[
                                    opponent_id
                                ] = observed_mean
                            else:
                                retention = float(args.adaptive_league_ema)
                                adaptive_opponent_ema_rewards[
                                    opponent_id
                                ] = (
                                    retention
                                    * adaptive_opponent_ema_rewards[opponent_id]
                                    + (1.0 - retention) * observed_mean
                                )
                            adaptive_opponent_observations[
                                opponent_id
                            ] += hand_count
                    adaptive_opponent_weights = adaptive_hardness_weights(
                        adaptive_opponent_ema_rewards,
                        args.adaptive_league_temperature_bb,
                        args.adaptive_league_min_probability,
                    )
                    league_iteration_rows = [
                        {
                            'opponent_id': int(opponent_id),
                            'iteration_hands': int(
                                iter_league_hands[opponent_id]
                            ),
                            'iteration_hero_reward_mean': (
                                float(
                                    iter_league_reward_sums[opponent_id]
                                    / iter_league_hands[opponent_id]
                                )
                                if iter_league_hands[opponent_id] > 0
                                else None
                            ),
                            'ema_hero_reward': float(
                                adaptive_opponent_ema_rewards[opponent_id]
                            ),
                            'next_sampling_probability': float(
                                adaptive_opponent_weights[opponent_id]
                            ),
                            'cumulative_hands': int(
                                adaptive_opponent_observations[opponent_id]
                            ),
                        }
                        for opponent_id in range(pool.size())
                    ]

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
                ppo_replay_log = (
                    f"replay={ppo_replay_info['rows']}/{len(iter_transitions)} "
                    f"rb={len(ppo_replay_entries)}/{args.ppo_replay_buffer_iterations} "
                    if args.ppo_replay_ratio > 0.0
                    else ""
                )

                log_line = (
                    f"[{iteration:5d}] "
                    f"hands={total_hands:,} "
                    f"envhands={iteration_environment_accounting['completed_hands']:,} "
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
                    f"{ppo_replay_log}"
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
                        'training_hand_counter_semantics': 'transition_bearing_hands_v1',
                        'environment_hand_accounting': iteration_environment_accounting,
                        'procedural_opponent_accounting': (
                            current_procedural_opponent_accounting()
                        ),
                        'hands_per_second': h_per_s, 'entropy': float(stats['entropy']),
                        'reward_per_hand': float(avg_rew),
                        'reward_window_100': float(rew100),
                        'terminal_trajectories': int(iter_terminal_trajectories),
                        'actor_reward_override_rows': int(
                            stats.get('actor_reward_override_rows', 0)
                        ),
                        'actor_reward_override_terminal_only': bool(
                            stats.get('actor_reward_override_terminal_only', True)
                        ),
                        'raw_terminal_reward_variance': float(
                            stats.get('raw_terminal_reward_variance', 0.0)
                        ),
                        'actor_terminal_reward_variance': float(
                            stats.get('actor_terminal_reward_variance', 0.0)
                        ),
                        'actor_terminal_reward_variance_ratio': float(
                            stats.get('actor_terminal_reward_variance_ratio', 0.0)
                        ),
                        'critic_contract': args.critic_contract, 'value_coef': args.value_coef,
                        'centralized_critic': bool(
                            stats.get('centralized_critic', False)
                        ),
                        'preupdate_critic_mse': float(
                            stats.get('preupdate_critic_mse', 0.0)
                        ),
                        'actor_ema_decay': float(args.actor_ema_decay),
                        'actor_ema_updates': int(actor_ema_updates),
                        'approx_kl': float(stats.get('approx_kl', 0.0)),
                        'gradient_diagnostics': stats.get('gradient_diagnostics', []),
                        'hand_gradient_noise': stats.get('hand_gradient_noise'),
                        'reference_policy_kl': float(stats.get('reference_policy_kl', 0.0)),
                        'reference_policy_kl_coef': float(
                            stats.get('reference_policy_kl_coef', args.source_policy_kl_coef)
                        ),
                        'reference_policy_temperature': float(
                            stats.get(
                                'reference_policy_temperature',
                                args.source_policy_kl_temperature
                                if args.source_policy_kl_temperature is not None
                                else args.hero_policy_temperature,
                            )
                        ),
                        'advantage_by_action_slot': stats.get(
                            'advantage_by_action_slot',
                            {},
                        ),
                        'raw_advantage_by_action_slot': stats.get(
                            'raw_advantage_by_action_slot',
                            {},
                        ),
                        'advantage_by_position_street_action_slot': stats.get(
                            'advantage_by_position_street_action_slot',
                            {},
                        ),
                        'raw_advantage_by_position_street_action_slot': stats.get(
                            'raw_advantage_by_position_street_action_slot',
                            {},
                        ),
                        'policy_advantage_clip': float(
                            stats.get('policy_advantage_clip', 0.0)
                        ),
                        'policy_advantage_clip_fraction': float(
                            stats.get('policy_advantage_clip_fraction', 0.0)
                        ),
                        'greedy_advantage_margin_loss': float(
                            stats.get('greedy_advantage_margin_loss', 0.0)
                        ),
                        'greedy_advantage_margin_coef': float(
                            stats.get('greedy_advantage_margin_coef', 0.0)
                        ),
                        'greedy_advantage_margin': float(
                            stats.get('greedy_advantage_margin', 0.1)
                        ),
                        'greedy_advantage_margin_eligible_rows': int(
                            stats.get('greedy_advantage_margin_eligible_rows', 0)
                        ),
                        'greedy_advantage_margin_positive_rows': int(
                            stats.get('greedy_advantage_margin_positive_rows', 0)
                        ),
                        'greedy_advantage_margin_eligible_fraction': float(
                            stats.get('greedy_advantage_margin_eligible_fraction', 0.0)
                        ),
                        'source_greedy_margin_loss': float(
                            stats.get('source_greedy_margin_loss', 0.0)
                        ),
                        'source_greedy_margin_coef': float(
                            stats.get('source_greedy_margin_coef', 0.0)
                        ),
                        'source_greedy_margin_max': float(
                            stats.get('source_greedy_margin_max', 0.1)
                        ),
                        'source_greedy_margin_release_advantage': float(
                            stats.get('source_greedy_margin_release_advantage', 1.0)
                        ),
                        'source_greedy_margin_eligible_rows': int(
                            stats.get('source_greedy_margin_eligible_rows', 0)
                        ),
                        'source_greedy_margin_released_rows': int(
                            stats.get('source_greedy_margin_released_rows', 0)
                        ),
                        'source_greedy_margin_violation_rows': int(
                            stats.get('source_greedy_margin_violation_rows', 0)
                        ),
                        'source_greedy_margin_violation_fraction': float(
                            stats.get('source_greedy_margin_violation_fraction', 0.0)
                        ),
                        'policy_advantage_normalization': stats.get(
                            'policy_advantage_normalization',
                            'global',
                        ),
                        'hero_policy_temperature': float(
                            stats.get('policy_temperature', args.hero_policy_temperature)
                        ),
                        'policy_rows': int(
                            stats.get('policy_rows', len(ppo_transitions))
                        ),
                        'fresh_policy_rows': int(trainable_decisions),
                        'ppo_replay_rows': int(stats['ppo_replay_rows']),
                        'ppo_replay_hands': int(stats['ppo_replay_hands']),
                        'ppo_replay_available_rows': int(
                            stats['ppo_replay_available_rows']
                        ),
                        'ppo_replay_source_iterations': list(
                            stats['ppo_replay_source_iterations']
                        ),
                        'ppo_replay_buffer_iterations': int(
                            stats['ppo_replay_buffer_iterations']
                        ),
                        'ppo_replay_ratio': float(stats['ppo_replay_ratio']),
                        'ppo_replay_cumulative_rows': int(
                            stats['ppo_replay_cumulative_rows']
                        ),
                        'ppo_replay_recovery_boundaries': list(
                            stats['ppo_replay_recovery_boundaries']
                        ),
                        'policy_street_max': int(
                            stats.get(
                                'policy_street_max',
                                args.policy_street_max,
                            )
                        ),
                        'policy_street_min': int(
                            stats.get(
                                'policy_street_min',
                                args.policy_street_min,
                            )
                        ),
                        'action_q_advantage': bool(
                            stats.get('action_q_advantage', False)
                        ),
                        'action_q_policy_mix': float(
                            stats.get('action_q_policy_mix', 1.0)
                        ),
                        'action_q_loss': float(
                            stats.get('action_q_loss', 0.0)
                        ),
                        'action_q_fit_loss': float(
                            stats.get('action_q_fit_loss', 0.0)
                        ),
                        'action_q_residual_l2': float(
                            stats.get('action_q_residual_l2', 0.0)
                        ),
                        'action_q_counterfactual_loss': float(
                            stats.get(
                                'action_q_counterfactual_loss',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_loss_coef': float(
                            stats.get(
                                'action_q_counterfactual_loss_coef',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_policy_loss': float(
                            stats.get(
                                'action_q_counterfactual_policy_loss',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_policy_loss_coef': float(
                            stats.get(
                                'action_q_counterfactual_policy_loss_coef',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_policy_target_entropy': float(
                            stats.get(
                                'action_q_counterfactual_policy_target_entropy',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_policy_target_max_probability': float(
                            stats.get(
                                'action_q_counterfactual_policy_target_max_probability',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_batch_size': int(
                            stats.get(
                                'action_q_counterfactual_batch_size',
                                0,
                            )
                        ),
                        'action_q_counterfactual_max_batches_per_update': int(
                            stats.get(
                                'action_q_counterfactual_max_batches_per_update',
                                0,
                            )
                        ),
                        'action_q_counterfactual_batches_applied': int(
                            stats.get(
                                'action_q_counterfactual_batches_applied',
                                0,
                            )
                        ),
                        'action_q_counterfactual_training_rows': int(
                            stats.get(
                                'action_q_counterfactual_training_rows',
                                0,
                            )
                        ),
                        'action_q_counterfactual_base_loss_coef': float(
                            stats.get(
                                'action_q_counterfactual_base_loss_coef',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_policy_base_loss_coef': float(
                            stats.get(
                                'action_q_counterfactual_policy_base_loss_coef',
                                0.0,
                            )
                        ),
                        'action_q_counterfactual_loss_decay_hands': int(
                            stats.get(
                                'action_q_counterfactual_loss_decay_hands',
                                0,
                            )
                        ),
                        'action_q_counterfactual_replay_elapsed_hands': int(
                            stats.get(
                                'action_q_counterfactual_replay_elapsed_hands',
                                0,
                            )
                        ),
                        'action_q_counterfactual_replay_total_draws': int(
                            stats.get(
                                'action_q_counterfactual_replay_total_draws',
                                0,
                            )
                        ),
                        'action_q_counterfactual_replay_dataset_epochs': float(
                            stats.get(
                                'action_q_counterfactual_replay_dataset_epochs',
                                0.0,
                            )
                        ),
                        'action_q_support_prior_rows': float(
                            stats.get('action_q_support_prior_rows', 0.0)
                        ),
                        'action_q_support_counts': stats.get(
                            'action_q_support_counts',
                            {},
                        ),
                        'action_q_support_weights': stats.get(
                            'action_q_support_weights',
                            {},
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
                        'adaptive_opponent_league': league_iteration_rows,
                        'procedural_opponent_metrics': {
                            **iter_procedural_metrics,
                            'version': PROCEDURAL_OPPONENT_VERSION,
                            'profile_names': [
                                profile[0]
                                for profile in PROCEDURAL_OPPONENT_PROFILES
                            ],
                        },
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
                        'gradient_diagnostics': stats.get('gradient_diagnostics', []),
                        'hand_gradient_noise': stats.get('hand_gradient_noise'),
                        'reference_policy_kl': stats.get('reference_policy_kl', 0.0),
                        'reference_policy_kl_coef': stats.get(
                            'reference_policy_kl_coef', args.source_policy_kl_coef
                        ),
                        'reference_policy_temperature': stats.get(
                            'reference_policy_temperature',
                            args.source_policy_kl_temperature
                            if args.source_policy_kl_temperature is not None
                            else args.hero_policy_temperature,
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
                        'action_q_counterfactual_replay_total_draws': stats.get(
                            'action_q_counterfactual_replay_total_draws',
                            0,
                        ),
                        'action_q_counterfactual_replay_dataset_epochs': stats.get(
                            'action_q_counterfactual_replay_dataset_epochs',
                            0.0,
                        ),
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
                        'actor_reward_override_rows': stats.get(
                            'actor_reward_override_rows', 0
                        ),
                        'actor_reward_override_terminal_only': stats.get(
                            'actor_reward_override_terminal_only', True
                        ),
                        'raw_terminal_reward_variance': stats.get(
                            'raw_terminal_reward_variance', 0.0
                        ),
                        'actor_terminal_reward_variance': stats.get(
                            'actor_terminal_reward_variance', 0.0
                        ),
                        'actor_terminal_reward_variance_ratio': stats.get(
                            'actor_terminal_reward_variance_ratio', 0.0
                        ),
                        'fresh_policy_rows': trainable_decisions,
                        'ppo_update_rows': len(ppo_transitions),
                        'ppo_replay_rows': stats['ppo_replay_rows'],
                        'ppo_replay_hands': stats['ppo_replay_hands'],
                        'ppo_replay_available_rows': stats[
                            'ppo_replay_available_rows'
                        ],
                        'ppo_replay_source_iterations': stats[
                            'ppo_replay_source_iterations'
                        ],
                        'ppo_replay_cumulative_rows': stats[
                            'ppo_replay_cumulative_rows'
                        ],
                        'ppo_replay_recovery_boundaries': stats[
                            'ppo_replay_recovery_boundaries'
                        ],
                        'action_mix': mix,
                        'action_mix_by_phase': phase_mix,
                        'exp003_metrics': dict(iter_exp003_metrics),
                        'procedural_opponent_metrics': {
                            **iter_procedural_metrics,
                            'version': PROCEDURAL_OPPONENT_VERSION,
                            'profile_names': [
                                profile[0]
                                for profile in PROCEDURAL_OPPONENT_PROFILES
                            ],
                        },
                        'pool_size': pool.size(),
                        'pool_strategy': pool.strategy,
                        'pool_active_ids': pool.active_ids(),
                        'pool_active_metadata': pool.active_metadata(),
                        'selection_loss': selection_loss,
                        'adaptive_opponent_league': (
                            league_iteration_rows
                        ),
                        'advantage_by_position_street_action_slot': stats.get(
                            'advantage_by_position_street_action_slot',
                            {},
                        ),
                        'raw_advantage_by_position_street_action_slot': stats.get(
                            'raw_advantage_by_position_street_action_slot',
                            {},
                        ),
                    },
                )

                # Snapshot
                if (
                    iteration % args.snapshot_every == 0
                    and not lg002_recovery_active
                    and not fixed_opponent_active
                ):
                    prior_pool_ids = pool.active_ids()
                    candidate_state = {
                        key: value.detach().cpu()
                        for key, value in model.state_dict().items()
                    }
                    if args.pool_strategy == 'elo-kbest':
                        candidate_id = int(pool.next_id)
                        competitors = [
                            {
                                'id': int(snapshot['id']),
                                'model': opp_models[index],
                                'rating': float(
                                    snapshot.get('selection_score') or 1500.0
                                ),
                                'state_sha256': lg002_state_dict_sha256(
                                    snapshot['state_dict']
                                ),
                            }
                            for index, snapshot in enumerate(pool.snapshots)
                        ]
                        competitors.append({
                            'id': candidate_id,
                            'model': model,
                            'rating': 1500.0,
                            'state_sha256': lg002_state_dict_sha256(
                                candidate_state
                            ),
                        })
                        tournament = run_elo_survivor_tournament(
                            competitors=competitors,
                            pairs=args.elo_tournament_pairs,
                            base_seed=args.elo_tournament_seed,
                            tournament_index=len(elo_tournament_history) + 1,
                            starting_stack=args.starting_stack,
                            device=device,
                            k_factor=args.elo_k_factor,
                        )
                        if int(tournament['total_ood_nodes']) != 0:
                            raise RuntimeError(
                                'elo-kbest tournament encountered '
                                f'{tournament["total_ood_nodes"]} OOD nodes'
                            )
                        ratings = {
                            int(key): float(value)
                            for key, value in tournament['ratings'].items()
                        }
                        for snapshot in pool.snapshots:
                            snapshot_id = int(snapshot['id'])
                            snapshot['selection_score'] = ratings[snapshot_id]
                            snapshot['score_components'] = {
                                **(snapshot.get('score_components') or {}),
                                'elo_rating': ratings[snapshot_id],
                                'elo_tournament_index': int(
                                    tournament['tournament_index']
                                ),
                            }
                        snap = pool.add(
                            candidate_state,
                            hands=total_hands,
                            iteration=iteration,
                            selection_loss=selection_loss,
                            selection_score=ratings[candidate_id],
                            score_components={
                                **score_components,
                                'elo_rating': ratings[candidate_id],
                                'elo_tournament_index': int(
                                    tournament['tournament_index']
                                ),
                            },
                        )
                        tournament.update({
                            'iteration': int(iteration),
                            'training_hands': int(total_hands),
                            'candidate_id': candidate_id,
                            'active_ids_before': list(prior_pool_ids),
                            'selected_ids': pool.active_ids(),
                            'candidate_selected': (
                                candidate_id in pool.active_ids()
                            ),
                        })
                        elo_tournament_history.append(tournament)
                        print(
                            '  [ELO] '
                            f'tournament={tournament["tournament_index"]} '
                            f'matches={len(tournament["matches"])} '
                            f'eval_hands={tournament["evaluation_hands"]:,} '
                            f'candidate_rating={ratings[candidate_id]:.2f}'
                        )
                    else:
                        snap = pool.add(
                            candidate_state,
                            hands=total_hands,
                            iteration=iteration,
                            selection_loss=selection_loss,
                            score_components=score_components,
                        )
                    if args.adaptive_opponent_league:
                        (
                            adaptive_opponent_ema_rewards,
                            adaptive_opponent_observations,
                        ) = reconcile_adaptive_league_state(
                            prior_pool_ids,
                            pool.active_ids(),
                            adaptive_opponent_ema_rewards,
                            adaptive_opponent_observations,
                        )
                        adaptive_opponent_weights = adaptive_hardness_weights(
                            adaptive_opponent_ema_rewards,
                            args.adaptive_league_temperature_bb,
                            args.adaptive_league_min_probability,
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

                # The checkpoint must represent the buffer available to the
                # next update, so append the just-completed fresh blocks before
                # serializing model/optimizer/replay state.
                if args.ppo_replay_buffer_iterations > 0:
                    ppo_replay_entries.append({
                        'iteration': int(iteration),
                        'blocks': fresh_hand_blocks,
                        'rows': int(len(iter_transitions)),
                        'hands': int(len(fresh_hand_blocks)),
                    })

                # Save
                if iteration % args.save_interval == 0:
                    torch.save(checkpoint_payload(), args.out)
                    if args.pool_strategy == 'elo-kbest':
                        write_elo_tournament_evidence(
                            Path(args.elo_tournament_provenance_file),
                            elo_tournament_history,
                        )
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
                while (
                    pending_checkpoint_milestones
                    and total_hands >= pending_checkpoint_milestones[0]
                ):
                    milestone = pending_checkpoint_milestones.pop(0)
                    archive_dir = run_dir / 'checkpoints'
                    archive_dir.mkdir(parents=True, exist_ok=True)
                    milestone_path = archive_dir / (
                        f'milestone_hands{milestone:012d}_'
                        f'actual{total_hands:012d}_iter{iteration:06d}.pt'
                    )
                    torch.save(checkpoint_payload(), milestone_path)
                    print(
                        f'  [Milestone] {milestone_path} '
                        f'(threshold={milestone:,}, actual={total_hands:,})'
                    )

                # Reset for next iter. Do not emit provenance for an assignment
                # that will never be consumed after the fixed actual-hand budget.
                continue_training = not training_target_reached()
                if continue_training:
                    assign_opponents()
                iter_transitions = []
                iter_reward = 0.0
                iter_hands = 0
                iter_terminal_trajectories = 0
                iter_league_hands = [0 for _ in range(pool.size())]
                iter_league_reward_sums = [
                    0.0 for _ in range(pool.size())
                ]
                inference_batch_sizes = []
                iter_exp003_metrics = exp003_metrics_template()
                iter_procedural_metrics = procedural_opponent_metrics_template()
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
    if args.pool_strategy == 'elo-kbest':
        write_elo_tournament_evidence(
            Path(args.elo_tournament_provenance_file),
            elo_tournament_history,
        )
    write_manifest('finished', total_hands=total_hands, iteration=iteration, checkpoint=str(out_path))
    print(f'Done! {total_hands:,} hands. Saved to {args.out}')


if __name__ == '__main__':
    mp.set_start_method('spawn')
    main()
