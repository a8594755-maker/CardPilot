#!/usr/bin/env python3
"""
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
import json
import os
import sys
import time
import math
import random
import multiprocessing as mp
from multiprocessing import shared_memory
from collections import deque
from datetime import datetime, timezone
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

    try:
        while not stop_event.is_set():
            # Read this hand's opponent assignment (main writes per iter; we only read)
            current_opp_id = int(assigned_buf[0])
            is_self_play = (current_opp_id == -1)

            obs = env.reset()
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
                obs, reward, done = env.step(action_idx)

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
                except BrokenPipeError:
                    break
                local_transitions = []

        if local_transitions:
            try:
                transition_pipe.send(local_transitions)
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
    num_workers: int,
    device: str,
    batch_size_log: list,  # caller's list to push observed batch sizes for metrics
) -> int:
    """
    V5.0: build group masks via vectorized numpy ops, slice flat obs view directly.

    obs_np shape (W*OBS_SIZE,), reshape to (W, OBS_SIZE) view (no copy).
    """
    waiting_mask = (status_np == WAITING)
    if not waiting_mask.any():
        return 0

    obs_view = obs_np.reshape(num_workers, OBS_SIZE)
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
    parser.add_argument('--opponent-assignment', choices=('per-iteration', 'per-worker'),
                        default='per-iteration',
                        help='per-iteration keeps all workers on one sampled mode/snapshot for larger '
                             'inference batches; per-worker is the original independent sampler.')
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

    # Allocate shared memory (split: assigned + request)
    obs_shm = shared_memory.SharedMemory(create=True, size=W * OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=W * RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=W * 4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=W * 4)   # V5.0
    request_shm = shared_memory.SharedMemory(create=True, size=W * 4)    # V5.0

    obs_np = np.ndarray((W * OBS_SIZE,), dtype=np.float32, buffer=obs_shm.buf)
    result_np = np.ndarray((W * RESULT_SIZE,), dtype=np.float32, buffer=result_shm.buf)
    status_np = np.ndarray((W,), dtype=np.int32, buffer=status_shm.buf)
    assigned_np = np.ndarray((W,), dtype=np.int32, buffer=assigned_shm.buf)
    request_np = np.ndarray((W,), dtype=np.int32, buffer=request_shm.buf)

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
        p = mp.Process(
            target=worker_process_v5,
            args=(w, obs_shm.name, result_shm.name, status_shm.name,
                  assigned_shm.name, request_shm.name,
                  child_conn, stop_event, epsilon_val, args.starting_stack,
                  args.env_version),
            daemon=True,
        )
        p.start()
        child_conn.close()
        procs.append(p)

    print(f'\nV5 clean-from-zero trainer: {W} workers @ {args.starting_stack} BB')
    print(f'Run id: {args.run_id}')
    print(f'Run dir: {run_dir}')
    print(f'Target: {args.total_hands:,} hands')
    print(f'Environment: {args.env_version} (obs={obs_version})')
    print(f'PPO: eps_clip=0.2, delta1={args.delta1}, gamma={args.gamma}')
    print(
        f'V5: fresh_from_zero={not bool(args.resume)}, epsilon={args.epsilon}, '
        f'both-player collect=ON, pool={pool.description()}'
    )
    print(f'Opponent assignment: {args.opponent_assignment} (self_play_fraction={args.self_play_fraction})')
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

    # Cumulative metrics for cross-iter aggregation
    cum_decisions = 0
    cum_inferences = 0

    def assign_opponents():
        """Assign hero-vs-hero or pool opponents. Main writes assigned_np; workers only read."""
        if pool.size() == 0:
            assigned_np[:] = -1
            return

        if args.opponent_assignment == 'per-iteration':
            # Preserve the long-run self-play/pool mix while keeping each rollout
            # iteration on one requested model so GPU inference remains batched.
            if random.random() < args.self_play_fraction:
                assigned_np[:] = -1
            else:
                assigned_np[:] = random.randint(0, pool.size() - 1)
            return

        for w in range(W):
            if random.random() < args.self_play_fraction:
                assigned_np[w] = -1
            else:
                assigned_np[w] = random.randint(0, pool.size() - 1)

    assign_opponents()

    try:
        model.eval()
        last_inference_t = 0.0
        global_start = time.time()
        while total_hands < args.total_hands:
            if args.max_runtime_seconds > 0 and (time.time() - global_start) >= args.max_runtime_seconds:
                print(f"Reached max runtime guard ({args.max_runtime_seconds:.1f}s); stopping cleanly.")
                break

            t_inf = time.time()
            n_inf = run_inference_v5(
                model, opp_models,
                obs_np, result_np, status_np, request_np,
                W, device, inference_batch_sizes,
            )
            cum_inferences += n_inf
            last_inference_t += time.time() - t_inf

            # Drain pipes
            for pipe in pipes:
                try:
                    while pipe.poll():
                        data = pipe.recv()
                        if data is None:
                            continue
                        for t in data:
                            iter_transitions.append(t)
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

                # Reset for next iter
                assign_opponents()
                iter_transitions = []
                iter_reward = 0.0
                iter_hands = 0
                iter_terminal_trajectories = 0
                inference_batch_sizes = []
                iter_start = time.time()
                last_inference_t = 0.0
                model.eval()

            time.sleep(0.00001)

    except KeyboardInterrupt:
        print('\nInterrupted.')
    finally:
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
