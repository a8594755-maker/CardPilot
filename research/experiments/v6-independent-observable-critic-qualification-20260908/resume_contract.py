"""Explicit independent-critic continuation boundaries for the isolated trainer."""
from observable_critic import attach_encoder, extend_optimizer

FLAG = 'independent_observable_critic'
VERSION = 'observable_value_encoder.v1'
PREFIX = 'observable_value_encoder.'


def extended_state(state):
    return any(k.startswith(PREFIX) for k in state)


def validate_config(config):
    if type(config.get(FLAG, False)) is not bool:
        raise ValueError('independent critic flag must be boolean')
    if not config.get(FLAG, False):
        return
    if not config.get('resume') or config.get('reset_optimizer') or config.get('reset_hand_counter'):
        raise ValueError('independent critic requires retained-state resume without resets')
    if config.get('critic_contract') != 'critic_v2' or config.get('norm_layer') != 'gn':
        raise ValueError('independent critic requires critic_v2 GroupNorm')
    forbidden = ('centralized_critic', 'critic_head_only_gradient',
        'h8_value_head_catchup_after_kl_stop', 'action_q_advantage',
        'all_policy_heads_only_training', 'preflop_head_only_training', 'adapter_only_training')
    if any(config.get(k, False) for k in forbidden):
        raise ValueError('unsupported independent-critic training route')


def before_load(model, optimizer, checkpoint, config):
    validate_config(config)
    enabled = config.get(FLAG, False)
    previous = checkpoint.get('config', {}).get(FLAG, False)
    if type(previous) is not bool:
        raise ValueError('invalid serialized critic flag')
    has_encoder = extended_state(checkpoint['model'])
    if previous != has_encoder:
        raise ValueError('critic metadata/state mismatch')
    if has_encoder and not enabled:
        raise ValueError('cannot silently discard independent critic')
    if has_encoder:
        if checkpoint.get('observable_critic_contract') != VERSION:
            raise ValueError('unknown serialized critic contract')
        attach_encoder(model)
        extend_optimizer(model, optimizer)


def after_load(model, optimizer, checkpoint, config):
    if config.get(FLAG, False) and not extended_state(checkpoint['model']):
        # Original model and Adam have now loaded. Copy trained features, not
        # the constructor's randomly initialized features.
        attach_encoder(model)
        extend_optimizer(model, optimizer)


def attach_snapshot(model, state):
    if extended_state(state):
        attach_encoder(model)


def strip_reference_encoder(model):
    # The frozen reference is used only for policy probabilities. Its existing
    # actor and public value head are untouched; it does not need the new tower.
    if hasattr(model, 'observable_value_encoder'):
        del model.observable_value_encoder
    return model
