"""Independent player-observable encoder; no private opponent information.

This module is not a trainer integration by itself. The network's value-input
route must explicitly call it, and resumed optimizers must register its new
parameters without replacing any existing parameter/state.
"""
import copy

import torch
from torch import nn


class ObservableValueEncoder(nn.Module):
    COMPONENTS = ('card_cnn', 'action_cnn', 'extra_fc', 'trunk')

    def __init__(self, source):
        super().__init__()
        if source.critic_contract != 'critic_v2':
            raise ValueError('independent encoder requires critic_v2')
        if source.trunk is None:
            raise ValueError('initialize source trunk before cloning')
        if source.norm_layer != 'gn':
            raise ValueError('initial qualification is restricted to GroupNorm')
        for name in self.COMPONENTS:
            self.add_module(name, copy.deepcopy(getattr(source, name)))
        # A prior scope may have frozen actor representations. The value tower
        # must nevertheless be trainable, without changing the source flags.
        self.requires_grad_(True)
        self.train(source.training)

    def forward(self, card_info, action_info, extra_info):
        return self.trunk(torch.cat((
            self.card_cnn(card_info), self.action_cnn(action_info),
            self.extra_fc(extra_info[:, :2]),
        ), dim=1))


def attach_encoder(model):
    """One-time architecture derivation. Existing parameter objects stay intact."""
    if hasattr(model, 'observable_value_encoder'):
        raise ValueError('value encoder already attached; load its state instead')
    if getattr(model, 'centralized_critic', False) or getattr(model, 'centralized_value_head', None) is not None:
        raise ValueError('privileged critic is outside this control')
    if getattr(model, 'position_value_adapters', None) is not None:
        raise ValueError('value adapters require separate qualification')
    model.add_module('observable_value_encoder', ObservableValueEncoder(model))
    return model.observable_value_encoder


def extend_optimizer(model, optimizer):
    """Append new encoder parameters to the existing single Adam group.

Call only after the original optimizer state has been restored. New parameters
have no moments until their first update; every existing state/object is retained.
"""
    if not isinstance(optimizer, torch.optim.Adam) or len(optimizer.param_groups) != 1:
        raise ValueError('qualification requires a single Adam parameter group')
    if not hasattr(model, 'observable_value_encoder'):
        raise ValueError('attach encoder before extending optimizer')
    existing = optimizer.param_groups[0]['params']
    expected = [p for n, p in model.named_parameters()
                if p.requires_grad and not n.startswith('observable_value_encoder.')]
    if len(existing) != len(expected) or any(a is not b for a, b in zip(existing, expected)):
        raise ValueError('existing optimizer order/scope differs or encoder already registered')
    new = list(model.observable_value_encoder.parameters())
    if any(p in optimizer.state for p in new):
        raise ValueError('new encoder unexpectedly has optimizer history')
    optimizer.param_groups[0]['params'] = list(existing) + new
    return {'retained_parameters': len(existing), 'new_parameters': len(new),
            'new_moments': 'lazy-zero-on-first-step',
            'lr': optimizer.param_groups[0]['lr']}
