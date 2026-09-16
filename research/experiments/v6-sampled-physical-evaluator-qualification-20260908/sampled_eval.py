"""Isolated physical-v6 evaluator, legal temperature-1 categorical execution."""
import hashlib
import math
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
from alpha_holdem.v6_elo_eval import _observation, greedy_action
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState


def action_uniform(seed, pair_index, player, decision_index):
    if player not in (0, 1) or pair_index < 0 or decision_index < 0:
        raise ValueError('invalid action random key')
    key = f'physical-v6-sampled-v1:{int(seed)}:{int(pair_index)}:{player}:{int(decision_index)}'
    bits = int.from_bytes(hashlib.sha256(key.encode('ascii')).digest()[:8], 'big') >> 11
    return bits / float(1 << 53)


def legal_slot(values, mask, uniform):
    values = np.asarray(values, dtype=np.float64)
    mask = np.asarray(mask)
    if values.shape != (9,) or mask.shape != (9,) or not np.isfinite(mask).all():
        raise ValueError('invalid logits or mask shape/value')
    if not np.isin(mask, [0, 1]).all() or not math.isfinite(uniform) or not 0 <= uniform < 1:
        raise ValueError('invalid mask or uniform')
    legal = np.flatnonzero(mask)
    if not len(legal) or not np.isfinite(values[legal]).all():
        raise ValueError('empty legal set or nonfinite legal logits')
    probabilities = np.exp(values[legal] - values[legal].max())
    probabilities /= probabilities.sum()
    index = min(int(np.searchsorted(np.cumsum(probabilities), uniform, side='right')), len(legal) - 1)
    return int(legal[index])


@torch.no_grad()
def sampled_action(model, state, *, observation_style, device, uniform):
    obs, table = _observation(model, state, observation_style)
    tensors = [torch.as_tensor(obs[k], dtype=torch.float32, device=device).unsqueeze(0)
               for k in ('card_info', 'action_info', 'extra_info', 'legal_mask')]
    logits, _ = model(*tensors)
    slot = legal_slot(logits[0].detach().cpu().numpy(), obs['legal_mask'], uniform)
    if table[slot] is None:
        raise ValueError('selected empty legal slot')
    return table[slot]


def play_hand(candidate, anchor, deck, *, candidate_seat, action_seed, pair_index,
              device='cpu', observation_style='legacy_v4', mode='sampled'):
    if mode not in ('sampled', 'greedy') or candidate_seat not in (0, 1):
        raise ValueError('invalid execution mode or seat')
    if len(deck) != 52 or set(deck) != set(range(52)):
        raise ValueError('deck must be a full permutation')
    state = ChipState.new(list(deck))
    counters = [0, 0]
    while not state.terminal:
        player = state.actor
        model = candidate if player == candidate_seat else anchor
        options = dict(observation_style=observation_style, device=device)
        if mode == 'sampled':
            action = sampled_action(model, state, **options,
                uniform=action_uniform(action_seed, pair_index, player, counters[player]))
        else:
            action = greedy_action(model, state, **options)
        counters[player] += 1
        state = apply_incr(state, action)
    return float(state.payoffs()[candidate_seat]) / 100.0, sum(counters)


def pair_outcome(candidate, anchor, deck, *, action_seed, pair_index, device='cpu', mode='sampled'):
    outcomes = [play_hand(candidate, anchor, deck, candidate_seat=seat,
                 action_seed=action_seed, pair_index=pair_index, device=device, mode=mode)
                for seat in (0, 1)]
    return dict(pair_index=pair_index, deck=list(deck), action_seed=action_seed,
                candidate_rewards_bb=[x[0] for x in outcomes],
                candidate_pair_mean_bb=sum(x[0] for x in outcomes)/2,
                decisions=[x[1] for x in outcomes], mode=mode)
