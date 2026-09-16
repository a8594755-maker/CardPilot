"""Opt-in actor-only representation route; never silently change it on resume."""

FLAG = 'preflop_trunk_gradient'
ORIGIN = 'preflop_trunk_gradient_migration'
SCHEMA = 'cardpilot.preflop_actor_trunk_gradient.v1'


def strict_flag(config):
    value = config.get(FLAG, False)
    if type(value) is not bool:
        raise ValueError(f'{FLAG} must be a boolean')
    return value


def validate_config(config):
    if not strict_flag(config):
        return
    if config.get('separate_preflop_head') is not True:
        raise ValueError('preflop trunk gradient requires a separate preflop head')
    if config.get('hero_preflop_strategy', 'model') != 'model':
        raise ValueError('preflop trunk gradient requires learned model preflop')
    if config.get('preflop_teacher_coef', 0.0) != 0.0:
        raise ValueError('preflop trunk gradient is not admitted with teacher loss')
    if config.get('policy_postflop_only', False):
        raise ValueError('preflop trunk gradient requires preflop actor training')
    restricted = [key for key, value in config.items()
                  if key.endswith('only_training') and value]
    if restricted:
        raise ValueError('preflop trunk gradient requires full trainable scope: ' + ','.join(restricted))


def checkpoint_flag(checkpoint):
    config = checkpoint.get('config') or {}
    value = strict_flag(config)
    if FLAG in checkpoint and strict_flag(checkpoint) != value:
        raise ValueError('checkpoint gradient metadata/config disagree')
    return value


def validate_resume(config, checkpoint):
    validate_config(config)
    source = checkpoint_flag(checkpoint)
    if strict_flag(config) != source:
        raise ValueError('preflop gradient route changed on resume; use an explicitly derived, audited parent')
    if source:
        validate_config(checkpoint.get('config') or {})


def migration_metadata(source_path, source_sha256):
    if len(source_sha256) != 64 or any(c not in '0123456789abcdef' for c in source_sha256):
        raise ValueError('invalid source SHA256')
    return {'schema': SCHEMA, 'source_checkpoint': str(source_path),
            'source_checkpoint_sha256': source_sha256,
            'source_preflop_trunk_gradient': False, 'target_preflop_trunk_gradient': True,
            'weights_optimizer_replay_counters_rng_unchanged': True,
            'new_environment_hands': 0, 'forward_contract_changed': False,
            'critic_gradient_route_changed': False}
