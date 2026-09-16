import json

import pytest

import cross_seed_summary as cross
from test_geometric_summary import summary


def stage(mean=0):
    return {'endpoint_minus_original4M': {'static': summary(), 'moving256': summary(mean)},
            'moving_minus_static': summary(mean)}


def test_equal_seeds_not_precision_or_deal_weighted():
    result = cross.equal_seed_stat({'seed1': {'bb100': 10, 'ci95_halfwidth_bb100': 3, 'samples': 10},
                                    'seed3': {'bb100': -2, 'ci95_halfwidth_bb100': 4, 'samples': 100000}})
    assert result['bb100'] == 4
    assert result['conditional_ci95_halfwidth_bb100'] == 2.5
    assert result['conditional_ci95_low_bb100'] == 1.5
    assert result['training_seed_count'] == 2
    assert result['training_seed_population_ci95'] is None
    assert not result['both_seed_point_estimates_positive']
    assert result['observed_seed_range_bb100'] == [-2, 10]


@pytest.mark.parametrize('change', [{'bb100': float('nan')}, {'ci95_halfwidth_bb100': -1}])
def test_bad_seed_stat_fails(change):
    values = {s: {'bb100': 0, 'ci95_halfwidth_bb100': 1} for s in cross.SEEDS}
    values['seed3'].update(change)
    with pytest.raises(ValueError):
        cross.equal_seed_stat(values)


def test_missing_seed_or_seat_cannot_be_pooled():
    with pytest.raises(ValueError):
        cross.equal_seed_stat({'seed1': summary()['pooled']})
    values = {s: summary() for s in cross.SEEDS}
    del values['seed3']['by_seat']['1']
    with pytest.raises(ValueError, match='breadth'):
        cross.equal_seed_breadth(values)


def test_geometric_change_requires_same_two_seed_coverage():
    data = {'seed1': {1: stage(2), 2: stage(8)}, 'seed3': {1: stage(10), 2: stage(12)}}
    result = cross.combine(data)
    assert result['by_stage'][2]['moving_minus_static']['pooled']['bb100'] == 10
    assert result['equal_seed_geometric_change']['moving_minus_static_contrast_change']['pooled']['bb100'] == 4
    assert not result['automatic_promotion']
    assert not result['method_superiority_established']
    del data['seed3'][2]
    result = cross.combine(data)
    assert set(result['by_stage']) == {1}
    assert result['equal_seed_geometric_change'] is None
    assert 'no imputed stage2' in result['missing_stage2_reason']


def test_live_owner_blocks_before_reading_source_outcomes(monkeypatch, tmp_path):
    monkeypatch.setattr(cross.report, 'readiness', lambda _: {'ready': False, 'reason': 'controller is live'})
    monkeypatch.setattr(cross.ev, 'sha', lambda _: pytest.fail('must not read outcomes before readiness'))
    with pytest.raises(ValueError, match='controller is live'):
        cross.build_report(tmp_path / 'does_not_exist.json')


def test_all_jobs_need_terminal_receipts_and_current_os_absence(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cross.ctl, 'owner_live', lambda owner: calls.append(owner) or False)
    for arm in ('static', 'moving256'):
        for prefix in ('', 'job_eval_', 'drift_'):
            directory = tmp_path / f'{prefix}{arm}_stage1'
            directory.mkdir()
            (directory / 'process.json').write_text(json.dumps({'pid': len(calls) + 101, 'create_time': 1.0}))
            (directory / 'command.json').write_text('[]')
            receipt = {'exit_code': 0, 'observer_errors': [], 'remaining_observed_child_pids': [],
                       'observed_children': {'201': 2.0}}
            (directory / 'termination.json').write_text(json.dumps(receipt))
    assert len(cross.report.verify_all_jobs(tmp_path, 1)) == 18
    assert len(calls) == 12
    monkeypatch.setattr(cross.ctl, 'owner_live', lambda owner: owner['pid'] == 201)
    with pytest.raises(ValueError, match='descendant still live'):
        cross.report.verify_all_jobs(tmp_path, 1)


def test_experiment_bindings_are_seed3():
    assert cross.ev.BASE == cross.ctl.BASE == cross.BASE
    assert cross.ctl.INITIAL_PHYSICAL == 4194908
    assert cross.ctl.INITIAL_ITERATION == 880


def test_unknown_interruption_cannot_be_reinterpreted_as_zero():
    from test_geometric_summary import run
    runs = [run(arm, stage, i) for i, (arm, stage) in enumerate(cross.ctl.ORDER)]
    runs[-1]['unknown_crash_suffix_hands'] = None
    with pytest.raises(ValueError, match='interrupted attempt'):
        cross.report.accounting_from_runs(runs)
