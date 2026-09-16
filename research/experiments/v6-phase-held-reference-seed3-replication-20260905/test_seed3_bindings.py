import pytest
import run_control as c
import control_evidence as e


@pytest.mark.parametrize('arm,stage', c.ORDER)
def test_seed3_does_not_inherit_gpu_helpers_seed1_defaults(arm, stage):
    args = c.training_command(arm, stage, c.PARENT, c.INITIAL_PHYSICAL)
    for option, value in {'--seed': '20263003', '--worker-seed-base': '2026300300',
            '--fixed-training-deal-start-index': '39300000',
            '--run-id': 'v6_nashpg_static_seed3_20260903'}.items():
        assert args.count(option) == 1 and args[args.index(option) + 1] == value
    assert '/seed3/latest.pt' in c.PARENT.as_posix()
    assert c.TARGETS == {1: 6292060, 2: 8389212}


def test_reference_activation_is_seed3_original880_not_seed1_882():
    assert c.INITIAL_ITERATION == 880
    assert e.reference_state.__defaults__ == (880,)
    state = {'iteration': 882, 'moving_source_policy_reference': {}}
    with pytest.raises(ValueError):
        e.reference_state(state)
