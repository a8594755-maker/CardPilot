import copy
import json
import os

import psutil
import pytest
import summarize_geometric_control as report


def summary(mean=0, half=3):
    value = {'bb100': mean, 'ci95_halfwidth_bb100': half, 'samples': 2048}
    return {'pooled': {**value, 'samples': 8192},
            'by_anchor': {a: dict(value) for a in report.ev.ANCHORS},
            'by_seat': {str(s): dict(value) for s in (0, 1)}}


def test_variances_add_not_widths_and_not_new_paired_sample():
    result = report.independent_stage_difference(summary(2, 3)['pooled'], summary(8, 4)['pooled'])
    assert result['bb100'] == 6
    assert result['ci95_halfwidth_bb100'] == 5
    assert result['descriptive_ci95_low_bb100'] == 1
    assert result['descriptive_ci95_high_bb100'] == 11
    assert result['earlier_cohort_samples'] == result['later_cohort_samples'] == 8192
    assert result['direct_paired_stage1_vs_stage2_hands'] == 0


@pytest.mark.parametrize('bad', [{'bb100': float('nan')}, {'ci95_halfwidth_bb100': -1}, {'samples': 1}])
def test_invalid_statistics_rejected(bad):
    value = summary()['pooled'] | bad
    with pytest.raises(ValueError):
        report.independent_stage_difference(value, summary()['pooled'])


def test_both_seats_and_every_anchor_required():
    earlier, later = summary(), summary(2)
    assert set(report.difference_summary(earlier, later)['by_seat']) == {'0', '1'}
    del later['by_anchor']['cfr4']
    with pytest.raises(ValueError, match='breadth'):
        report.difference_summary(earlier, later)


def test_live_owner_blocks_post_analysis_before_any_result_read(tmp_path):
    proc = psutil.Process(os.getpid())
    (tmp_path / 'ownership.json').write_text(json.dumps({'pid': proc.pid, 'create_time': proc.create_time()}))
    assert not report.readiness(tmp_path)['ready']
    with pytest.raises(ValueError, match='controller is live'):
        report.build_report(tmp_path)


def test_geometric_stages_required_and_package_not_cadence_claim():
    stage = {'endpoint_minus_original4M': {'static': summary(), 'moving256': summary()},
             'moving_minus_static': summary()}
    with pytest.raises(ValueError):
        report.geometric_report({1: stage})
    stages = {1: stage, 2: copy.deepcopy(stage)}
    stages[2]['endpoint_minus_original4M']['moving256'] = summary(5)
    result = report.geometric_report(stages)
    assert result['endpoint_minus_original4M_slope_change']['moving256']['pooled']['bb100'] == 5
    assert result['initial_reference_rebasing_is_part_of_treatment']
    assert not result['automatic_promotion']


def run(arm, stage, number):
    return {'arm': arm, 'stage': stage, 'namespace': str(number), 'new_physical_hands': 100,
            'new_transition_hands': 80, 'new_replay_rows': 900, 'new_no_decision_hands': 15,
            'residual_worker_tail_hands': 5, 'unknown_crash_suffix_hands': 0,
            'subprocess_wall_seconds': 10}


def test_shared_parent_not_added_for_each_fork_or_stage():
    runs = [run(arm, stage, i) for i, (arm, stage) in enumerate(report.ctl.ORDER)]
    counts = report.accounting_from_runs(runs)
    assert counts['new_training_hands'] == 400
    assert counts['known_local_lineage_union_physical_hands'] == report.ctl.INITIAL_PHYSICAL + 400
    assert counts['largest_single_endpoint_local_lineage_hands'] == report.ctl.INITIAL_PHYSICAL + 200
    assert counts['new_replay_rows_not_new_hands'] == 3600
    runs[-1]['namespace'] = runs[0]['namespace']
    with pytest.raises(ValueError, match='namespace'):
        report.accounting_from_runs(runs)
