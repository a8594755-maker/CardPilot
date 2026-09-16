import pytest
import run_control as run


@pytest.mark.parametrize('stage', [1, 2])
def test_fixed_budget_and_no_state_resets(stage):
    for arm in ('static', 'moving256'):
        argv = run.training_command(arm, stage, run.PARENT, run.INITIAL_PHYSICAL)
        assert int(argv[argv.index('--total-environment-hands') + 1]) == run.TARGETS[stage]
        assert argv[argv.index('--max-runtime-seconds') + 1] == '7200'
        assert argv[argv.index('--rollout-mode') + 1] == 'multi'
        assert argv[argv.index('--rollout-envs-per-worker') + 1] == '8'
        assert '--managed-deal-attempts' in argv and '--no-reset-optimizer' in argv
        assert '--preserve-resumed-optimizer-lr' in argv
        assert '--reset-optimizer' not in argv and '--reset-hand-counter' not in argv
        assert '--resume-assignment-state-from-provenance' in argv


def test_reference_package_is_explicit_not_falsely_cadence_only():
    static = run.training_command('static', 1, run.PARENT, run.INITIAL_PHYSICAL)
    moving = run.training_command('moving256', 1, run.PARENT, run.INITIAL_PHYSICAL)
    assert '--source-policy-reference-checkpoint' in static
    assert '--source-policy-reference-checkpoint' not in moving
    assert moving[moving.index('--source-policy-reference-refresh-updates') + 1] == '256'
    assert static[static.index('--source-policy-reference-refresh-updates') + 1] == '0'
    for option in ('--workers', '--hands-per-iter', '--source-policy-kl-coef',
                   '--source-policy-kl-direction', '--ppo-replay-ratio', '--self-play-fraction'):
        assert static[static.index(option) + 1] == moving[moving.index(option) + 1]


def test_stage2_uses_its_own_completed_parent():
    parent = run.stage_directory('moving256', 1) / 'latest.pt'
    argv = run.training_command('moving256', 2, parent, run.TARGETS[1] + 300)
    assert argv[argv.index('--resume') + 1] == str(parent)
    assert int(argv[argv.index('--total-environment-hands') + 1]) == run.TARGETS[2]


def test_unknown_arm_refused():
    with pytest.raises(ValueError):
        run.training_command('best_seed', 1, run.PARENT, run.INITIAL_PHYSICAL)
