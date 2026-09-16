"""Synthetic review contracts only; never read or alter live poker evidence."""
import copy
import json
from pathlib import Path
import sys

import pytest
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import evaluate
import report_completed_pilot as report
import run_pilot


def config(coef):
    return dict(source_policy_kl_coef=coef, seed=20260907, worker_seed_base=2026090700,
        hands_per_iter=4096, total_environment_hands=262144, mini_batch_size=1024, lr=.00003,
        ppo_epochs=2, ppo_target_kl=.01, policy_advantage_clip=3., self_play_fraction=.25,
        all_policy_heads_only_training=True, separate_preflop_head=True, reset_optimizer=True,
        reset_hand_counter=True, starting_stack=200., fixed_training_deal_stream=True)


def metrics(coef):
    return [dict(iteration=i+1, fresh_policy_rows=n, policy_rows=n, ppo_epochs_completed=2,
        ppo_replay_rows=0, value_head_catchup_enabled=False, reference_policy_kl_coef=coef,
        reference_policy_kl=.001, approx_kl=.0001, clip_frac=0., entropy=.5,
        kl_early_stop_triggered=False, hands_per_second=100.) for i, n in enumerate([1001, 1025])]


def doc(digest, point=0., pairs=4096):
    return dict(seed=evaluate.SEED, pairs=pairs, policy_mode=evaluate.MODE,
        action_rng_schema=evaluate.RNG, starting_stack=200., candidate={'sha256': digest},
        gate=dict(anchor_ood_valid_threshold=.15, all_anchors_pass_ood_gate=True),
        execution={'status': 'COMPLETED'}, anchors=[dict(anchor=name,
        anchor_sha256=run_pilot.DIGESTS[i], action_rng=dict(seed=evaluate.SEED+i*1000003, schema=evaluate.RNG),
        pairs=pairs, hands=2*pairs, candidate_bb100=point*100, anchor_ood_valid=True,
        candidate_std_bb_per_hand_pair_mean=0., candidate_ci95_bb100=0.,
        unpaired_hand_bb100=point*100, unpaired_hand_ci95_bb100=0., total_candidate_bb=point*2*pairs,
        candidate_by_seat={seat: dict(hands=pairs, candidate_bb100=point*100, candidate_ci95_bb100=0.,
            candidate_std_bb_per_hand=0., total_candidate_bb=point*pairs) for seat in ['bb', 'sb']},
        pair_wins=pairs if 2*point > .01 else 0, pair_losses=pairs if 2*point < -.01 else 0,
        pair_draws=pairs if abs(2*point) <= .01 else 0,
        hand_wins=2*pairs if point > .01 else 0, hand_losses=2*pairs if point < -.01 else 0,
        hand_draws=2*pairs if abs(point) <= .01 else 0,
        decisions=4*pairs, policy_decisions={'candidate': 2*pairs, 'anchor': 2*pairs},
        ood_nodes={'candidate': 0, 'anchor': 0}, candidate_ood_node_rate=0., anchor_ood_node_rate=0.,
        anchor_ood_valid_threshold=.15, mirror_signal_valid=True,
        paired_outcomes=dict(overall_bb_per_hand=[point]*pairs,
            bb_bb_per_hand=[point]*pairs, sb_bb_per_hand=[point]*pairs))
        for i, name in enumerate(evaluate.NAMES)])


def test_independent_statistics_and_adjusted_gate():
    control, weak = doc('c', pairs=4), doc('w', pairs=4)
    for row in weak['anchors']:
        row['paired_outcomes']['overall_bb_per_hand'] = [0., .01, .02, .03]
    rows = report.compare(control, weak)
    expected = evaluate.compare(control, weak)
    report.assert_contrasts_match(rows, expected)
    assert rows[0]['delta_bb100'] == 1.5
    assert rows[0]['ci95_half_width'] == pytest.approx(1.96*(5/12)**.5)
    # Deliberately positive nominal lower, negative adjusted lower: reject.
    rows[0]['bonferroni_lower'] = rows[1]['bonferroni_lower'] = rows[2]['bonferroni_lower'] = -.01
    rows[0]['ci95_lower'] = .1
    assert not report.admission(rows, rows)


@pytest.mark.parametrize('kind', ['nan', 'bool', 'bound', 'missing', 'stream'])
def test_invalid_pair_evidence_rejected(kind):
    c, t = doc('c', pairs=4), doc('t', pairs=4)
    if kind == 'stream': t['anchors'][0]['action_rng']['seed'] += 1
    elif kind == 'missing': t['anchors'][0]['paired_outcomes']['overall_bb_per_hand'].pop()
    else: t['anchors'][0]['paired_outcomes']['overall_bb_per_hand'][0] = {'nan': float('nan'), 'bool': True, 'bound': 201}[kind]
    with pytest.raises(ValueError): report.compare(c, t)


@pytest.mark.parametrize('kind', ['coef', 'rows', 'seed', 'scope', 'health'])
def test_configuration_and_executed_coefficient_checked(kind):
    cfg, rows = config(.01), metrics(.01)
    report.validate_coefficient(cfg, rows, .01)
    if kind == 'coef': cfg['source_policy_kl_coef'] = 1.
    elif kind == 'rows': rows[-1]['reference_policy_kl_coef'] = 1.
    elif kind == 'seed': cfg['seed'] += 1
    elif kind == 'scope': cfg['all_policy_heads_only_training'] = False
    else: rows[-1]['entropy'] = float('nan')
    with pytest.raises(ValueError): report.validate_coefficient(cfg, rows, .01)


def test_actual_adam_steps_include_partial_batches():
    result = report.batch_accounting(metrics(1.), 1024)
    assert result['total_steps'] == 6 and result['partial_batch_steps'] == 4
    report.validate_steps(result, [6]*10)
    with pytest.raises(ValueError): report.validate_steps(result, [4]*10)


def test_changed_statistic_rejected():
    rows = report.compare(doc('c', pairs=4), doc('t', pairs=4))
    changed = copy.deepcopy(rows)
    changed[0]['bonferroni_upper'] += .01
    with pytest.raises(ValueError): report.assert_contrasts_match(rows, changed)


@pytest.mark.parametrize('kind', ['ci', 'seat_total', 'count', 'bool_count', 'bool_seat',
    'ood_rate', 'ood_bound', 'ood_valid', 'ood_threshold', 'aggregate_valid', 'decisions'])
def test_independent_cell_review_rejects_corruption(kind):
    document = doc('synthetic', point=.01, pairs=4)
    assert len(report.review_cell(document)) == 3
    row = document['anchors'][0]
    if kind == 'ci': row['candidate_ci95_bb100'] = .001
    elif kind == 'seat_total': row['candidate_by_seat']['bb']['total_candidate_bb'] += .1
    elif kind == 'count': row['pair_draws'] += 1
    elif kind == 'bool_count': row['hand_wins'] = False
    elif kind == 'bool_seat': row['paired_outcomes']['bb_bb_per_hand'][0] = True
    elif kind == 'ood_rate': row['anchor_ood_node_rate'] = .01
    elif kind == 'ood_bound': row['ood_nodes']['anchor'] = 9
    elif kind == 'ood_valid': row['anchor_ood_valid'] = 1
    elif kind == 'ood_threshold': row['anchor_ood_valid_threshold'] = 1.
    elif kind == 'aggregate_valid': document['gate']['all_anchors_pass_ood_gate'] = False
    else: row['decisions'] += 1
    with pytest.raises(ValueError): report.review_cell(document)


def test_ood_above_threshold_is_valid_evidence_but_not_admitted():
    document = doc('synthetic', pairs=4)
    row = document['anchors'][0]
    row['ood_nodes']['anchor'] = 2
    row['anchor_ood_node_rate'] = .25
    row['anchor_ood_valid'] = row['mirror_signal_valid'] = False
    document['gate']['all_anchors_pass_ood_gate'] = False
    assert not report.review_cell(document)[0]['anchor_ood_valid']


def test_independent_cell_moments_use_sample_variance():
    from raw_cell_review import moments
    mean, std, half = moments([0., 1., 2., 3.])
    assert mean == 1.5
    assert std == pytest.approx((5/3)**.5)
    assert half == pytest.approx(1.96*(5/12)**.5)


def test_full_synthetic_report_writes_and_refuses_overwrite(tmp_path, monkeypatch):
    """Exercise main end-to-end including real torch loading and script hashing.

    The fixture's session audit is synthetic. This checks the report workflow,
    not the auditor or training mechanics, and accounts for zero actual hands.
    """
    monkeypatch.setattr(report, 'BASE', tmp_path)
    monkeypatch.setattr(report, 'ensure_writer_finished', lambda: None)
    monkeypatch.setattr(report, 'verify_sources', lambda copies: None)
    (tmp_path/'execution_code').mkdir()
    (tmp_path/'execution_code/copy_manifest.json').write_text('[]')
    (tmp_path/'matrix').mkdir()
    model = {f'trunk.{i}': torch.ones(1) for i in range(76)}
    for group, n in [('policy_head', 2), ('preflop_policy_head', 2), ('value_head', 6)]:
        model.update({f'{group}.{i}': torch.ones(1) for i in range(n)})
    source = tmp_path/'SYNTHETIC_SOURCE.pt'
    torch.save({'model': model}, source)
    selection = {'source': dict(path=str(source), sha256=report.sha(source), physical_hands=0)}
    for arm, coef, delta in [('control', 1., .1), ('weak', .01, .2)]:
        run = tmp_path/arm
        run.mkdir()
        rows = metrics(coef)
        checkpoint = dict(model={k: v if k.startswith('trunk.') else v+delta for k, v in model.items()},
            iteration=2, total_hands=3000, optimizer=dict(param_groups=[{'lr': 0.}],
                state={i: dict(step=torch.tensor(6.), exp_avg=torch.ones(1), exp_avg_sq=torch.ones(1)) for i in range(10)}))
        torch.save(checkpoint, run/'latest.pt')
        selection[arm] = dict(path=str(run/'latest.pt'), sha256=report.sha(run/'latest.pt'), physical_hands=263000, iteration=2)
        manifest = dict(config=config(coef), iteration=2, total_hands=3000,
            environment_hand_accounting=dict(completed_hands=263000, prefix_complete=True))
        (run/'run_manifest.json').write_text(json.dumps(manifest))
        (run/'h1_training_metrics.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        (run/'opponent_assignments.jsonl').write_text('{"synthetic_only":true}\n')
        (run/'latest_train.log').write_text('[ 1] vloss=0.1 synthetic\n[ 2] vloss=0.2 synthetic\n')
        files = dict(assignments='opponent_assignments.jsonl', checkpoint='latest.pt', manifest='run_manifest.json',
                     metrics='h1_training_metrics.jsonl', train_log='latest_train.log')
        audit = dict(status='PASS', artifact_integrity={k: {'sha256': report.sha(run/v)} for k, v in files.items()})
        (tmp_path/f'{arm}_audit.json').write_text(json.dumps(audit))
    documents, hashes = {}, {}
    for name, candidate in selection.items():
        documents[name] = doc(candidate['sha256'], point=.01 if name == 'weak' else 0.)
        path = tmp_path/'matrix'/f'{name}.json'
        path.write_text(json.dumps(documents[name]))
        hashes[name] = report.sha(path)
        (tmp_path/'matrix'/f'{name}_execution.json').write_text('{"status":"COMPLETED"}')
    comparisons = {f'{a}_vs_{b}': evaluate.compare(documents[b], documents[a])
        for a, b in [('weak', 'control'), ('weak', 'source'), ('control', 'source')]}
    analysis = dict(status='PASS', evaluation_hands=73728, cell_hashes=hashes, comparisons=comparisons,
        admits_independent_confirmation=True)
    record = dict(metrics={'pilot_evaluation_complete': 1}, accounting={'evaluation_hands': 73728, 'new_training_hands': 526000})
    for name, value in [('experiment.json', record), ('pilot_analysis.json', analysis), ('checkpoint_selection.json', selection)]:
        (tmp_path/name).write_text(json.dumps(value))
    report.main()
    result = json.loads((tmp_path/'completed_analysis.json').read_text())
    assert result['decision'] == 'WEAK_SOURCE_KL_ADMITS_CONFIRMATION'
    assert result['arms']['weak']['unchanged_representation_tensors'] == 76
    assert result['review_script_sha256'] == report.sha(report.__file__)
    assert (tmp_path/'result_summary.md').exists()
    with pytest.raises(RuntimeError, match='overwrite'): report.main()
