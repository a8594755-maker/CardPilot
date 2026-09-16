import pytest
import run_pilot as pilot


def test_original_source_and_immutable_helpers():
    assert pilot.sha(pilot.SOURCE) == pilot.SOURCE_SHA
    helper = pilot.load_helper()
    assert helper.SOURCE == pilot.SOURCE
    assert helper.PARENT_MODULE == pilot.PARENT


def test_fixed_fresh_contract():
    commands = [pilot.session_command(i) for i in range(1, 9)]
    assert len({pilot.session_id(i) for i in range(1, 9)}) == 8
    assert len({pilot.session_seed(i) for i in range(1, 9)}) == 8
    for command in commands:
        assert command[command.index('--hands') + 1] == '2500'
        assert command[command.index('--policy-mode') + 1] == 'greedy'
        assert command[-2:] == ['--observation-bridge', 'legacy-v4']
        assert 'gpu_current_recipe' not in ' '.join(command)


def test_development_never_auto_admits_even_positive_results():
    result = pilot.summarize([[100] * 2500 for _ in range(8)])
    assert result['bb_per_100'] == 100
    assert result['raw_hand_ci95'] == [100, 100]
    assert result['same_contract_standard10_bb_per_100'] == -24.5683
    assert not result['supports_separate_fresh100k']
    assert not result['goal_achieved'] and result['qualification_hands'] == 0
    saved = []
    pilot.development_write(lambda path, value: saved.append(value), 'completed_analysis.json',
                            {'decision': 'old_label', 'statistics': result})
    assert saved[0]['decision'] == 'EXTERNAL_DEVELOPMENT_CALIBRATION_REVIEW_REQUIRED'
    assert saved[0]['statistics'] == result


@pytest.mark.parametrize('sessions', [ [[0] * 2500] * 7, [[0] * 2499] * 8,
                                      [[20001] * 2500] * 8, [[0.5] * 2500] * 8 ])
def test_incomplete_or_invalid_samples_rejected(sessions):
    with pytest.raises(ValueError):
        pilot.summarize(sessions)
