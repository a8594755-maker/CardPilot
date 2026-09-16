"""Frozen learned-weight inference shared by v6 mirror and external deployment."""
from __future__ import annotations

import hashlib
from pathlib import Path
import numpy as np
import torch

from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, validate_metadata, observation, from_external


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_policy(path, device='cpu'):
    from alpha_holdem.v5_mirror_eval import init_model
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    for key in ['policy_logit_bias', 'policy_range_override', 'policy_context_override', 'preflop_strategy_profile']:
        if checkpoint.get(key) is not None:
            raise ValueError(f'v6 learned-only execution forbids {key}')
    model = init_model(checkpoint, device)
    model.eval()
    return model, checkpoint, sha256_file(path)


@torch.no_grad()
def decide(model, state, *, uniform, device='cpu', policy_mode='sample'):
    if not 0 <= uniform < 1:
        raise ValueError('Uniform variate must be in [0,1)')
    if policy_mode not in ('sample', 'greedy'):
        raise ValueError('policy_mode must be sample or greedy')
    include_position = bool(getattr(model, 'requires_position_feature', False)) or any(
        int(getattr(model, key, 0)) > 0 for key in ('position_adapter_hidden', 'position_value_adapter_hidden'))
    obs, table = observation(state, include_position=include_position)
    tensors = [torch.as_tensor(obs[key], dtype=torch.float32, device=device).unsqueeze(0)
               for key in ['card_info', 'action_info', 'extra_info', 'legal_mask']]
    logits, _ = model(*tensors)
    values = logits[0].detach().cpu().numpy().astype(np.float64)
    legal = np.flatnonzero(obs['legal_mask'])
    if values.shape != (9,) or not np.isfinite(values[legal]).all():
        raise ValueError('Invalid policy logits')
    probs = np.zeros(9, dtype=np.float64)
    weights = np.exp(values[legal]-np.max(values[legal]))
    probs[legal] = weights/weights.sum()
    greedy = int(legal[np.argmax(values[legal])])
    if policy_mode == 'sample':
        selected = int(legal[min(np.searchsorted(np.cumsum(probs[legal]), uniform, side='right'), len(legal)-1)])
        behavior_probs = probs
        temperature = 1.0
    else:
        selected = greedy
        behavior_probs = np.zeros(9, dtype=np.float64)
        behavior_probs[selected] = 1.0
        temperature = 0.0
    info = dict(policy_contract=CONTRACT_VERSION, policy_mode=policy_mode, temperature=temperature,
                legal_mask=obs['legal_mask'].tolist(), action_table=table,
                behavior_probs=behavior_probs.tolist(), behavior_action_probability=float(behavior_probs[selected]),
                selected_action_slot=selected, direct_increment=table[selected],
                greedy_action_slot=greedy, uniform=float(uniform))
    if policy_mode == 'greedy':
        info['model_probs'] = probs.tolist()
    return table[selected], info


def external_decision(model, response, *, uniform, device='cpu', policy_mode='sample'):
    state = from_external(response['action'], response['hole_cards'], response.get('board', []), response['client_pos'])
    return decide(model, state, uniform=uniform, device=device, policy_mode=policy_mode)
