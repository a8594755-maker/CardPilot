import copy

import pytest

import curve_comparison as curve


def bucket(point):
    row = {'bb100': point, 'se_bb100': 2., 'paired_decks': 8192}
    return {'pooled': row.copy(), 'by_anchor': {key: row.copy() for key in ('s10', 'cfr4', 'iter16', 'mixed')},
            'by_seat': {str(seat): row.copy() for seat in (0, 1)}}


def fixture():
    report = {'passed': True, 'all_recorded_processes_terminal': True,
              'unique_new_evaluation_decks': 32768, 'accounting': {'evaluation_hands': 262144},
              'stages': {}, 'training_health_and_realized_update_dose': {}}
    for stage in (1, 2):
        report['stages'][str(stage)] = {}
        for seed in ('1', '3'):
            report['stages'][str(stage)][seed] = {
                'connected_minus_detached': bucket(-10. if stage == 1 else 5.),
                'endpoint_minus_parent': {arm: bucket(stage * (3 if arm == 'detached' else 4)) for arm in ('detached', 'connected')},
                'absolute_vs_anchors': {arm: bucket(-100. + stage) for arm in ('detached', 'connected')},
            }
            for arm in ('detached', 'connected'):
                report['training_health_and_realized_update_dose'][f'seed{seed}_{arm}_stage{stage}'] = {
                    'cumulative_physical_hands': 9000000 + stage * 1000,
                    'new_physical_hands_this_stage': 1000,
                    'actual_lr': 9.999999999999996e-05,
                    'gradient_route': {'preflop_actor_to_trunk': arm == 'connected',
                                       'critic_to_trunk': False, 'origin_preserved': True},
                }
    return report


def test_both_seeds_arms_seats_and_anchors_preserved_without_input_mutation():
    report = fixture()
    saved = copy.deepcopy(report)
    result = curve.summarize(report)
    assert set(result) == {'1', '3'}
    for seed in result.values():
        assert seed['connected_minus_detached_change']['pooled']['bb100'] == 15.
        assert seed['connected_minus_detached_change']['pooled']['se_bb100'] == pytest.approx(8 ** .5)
        assert set(seed['connected_minus_detached_change']['by_seat']) == {'0', '1'}
        assert len(seed['connected_minus_detached_change']['by_anchor']) == 4
        assert seed['endpoint_minus_original_parent_changes']['detached']['pooled']['bb100'] == 3.
        assert seed['endpoint_minus_original_parent_changes']['connected']['pooled']['bb100'] == 4.
        assert seed['absolute_vs_anchors_changes']['connected']['pooled']['bb100'] == 1.
        assert seed['physical_hands_between_endpoints'] == {'detached': 1000, 'connected': 1000}
    assert report == saved


@pytest.mark.parametrize('key,value', [('passed', False), ('all_recorded_processes_terminal', False),
                                      ('unique_new_evaluation_decks', 16384)])
def test_incomplete_evidence_rejected(key, value):
    report = fixture()
    report[key] = value
    with pytest.raises(ValueError):
        curve.summarize(report)


def test_missing_seed_or_stage_rejected():
    for stage, seed in [('2', None), ('1', '3')]:
        report = fixture()
        del (report['stages'] if seed is None else report['stages'][stage])[stage if seed is None else seed]
        with pytest.raises(ValueError, match='coverage'):
            curve.summarize(report)


def test_old_heads_arm_cannot_be_mislabeled_as_connected():
    report = fixture()
    arms = report['stages']['2']['3']['endpoint_minus_parent']
    arms['heads'] = arms.pop('connected')
    with pytest.raises(ValueError, match='gradient-route arms'):
        curve.summarize(report)


@pytest.mark.parametrize('key,value', [('actual_lr', .0003), ('new_physical_hands_this_stage', 999),
                                      ('cumulative_physical_hands', 8999000)])
def test_wrong_realized_training_contract_rejected(key, value):
    report = fixture()
    report['training_health_and_realized_update_dose']['seed1_connected_stage2'][key] = value
    with pytest.raises(ValueError):
        curve.summarize(report)


def test_live_owner_prevents_review_read_and_output(monkeypatch, tmp_path):
    reads = []
    def read(path):
        reads.append(path.name)
        assert path.name == 'ownership.json'
        return {'pid': 1, 'create_time': 2.}
    monkeypatch.setattr(curve, 'read', read)
    monkeypatch.setattr(curve, 'live', lambda *args: True)
    with pytest.raises(ValueError, match='controller still live'):
        curve.main(tmp_path)
    assert reads == ['ownership.json']
    assert not list(tmp_path.iterdir())


def test_independent_variance_is_not_ci_subtraction():
    early, late = bucket(-20.)['pooled'], bucket(-5.)['pooled']
    early['se_bb100'], late['se_bb100'] = 3., 4.
    result = curve.independent_change(early, late)
    assert result['se_bb100'] == 5.
    assert result['ci95'] == pytest.approx([5.2, 24.8])


def test_bucket_mismatch_and_nonfinite_statistic_fail_closed():
    earlier, later = bucket(0.), bucket(1.)
    del later['by_anchor']['s10']
    with pytest.raises(ValueError, match='bucket mismatch'):
        curve.bucket_changes(earlier, later)
    later = bucket(1.)
    later['pooled']['bb100'] = float('nan')
    with pytest.raises(ValueError, match='invalid stage'):
        curve.bucket_changes(earlier, later)
