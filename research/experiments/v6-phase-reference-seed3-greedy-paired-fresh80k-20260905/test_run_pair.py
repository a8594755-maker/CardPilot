"""Draft executor offline admission, raw accounting and audit failure tests."""
import copy
import importlib.util
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('phase_pair_runner_tests', Path(__file__).with_name('run_pair.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_training_gate_is_read_only_and_precedes_external_spec(monkeypatch):
    seen = []
    def blocked():
        seen.append('training')
        raise ValueError('training experiment not finished')
    monkeypatch.setattr(r, 'training_ready', blocked)
    monkeypatch.setattr(r, 'read', lambda path: pytest.fail('external spec was read before training admission'))
    with pytest.raises(ValueError, match='not finished'):
        r.preflight(r.ROOT / 'research/experiments/not_created_external_draft')
    assert seen == ['training']


def test_running_training_record_is_not_admitted(monkeypatch):
    monkeypatch.setattr(r, 'read', lambda path: {'status': 'RUNNING'})
    with pytest.raises(ValueError, match='not finished'):
        r.training_ready()


def raw_row(index=1):
    item = r.protocol.schedule()[0]
    return {'successful_hand': index, 'attempted_hand': index, 'session_id': item['session_id'],
            'policy_seed': item['policy_seed'], 'model_sha256': 'static_model'}


def raw_path(base):
    path = base / 'sessions/static/s01/hands.jsonl'
    path.parent.mkdir(parents=True)
    return path


def test_incremental_counter_counts_complete_lines_once(tmp_path):
    path = raw_path(tmp_path)
    first, second = json.dumps(raw_row(1)).encode(), json.dumps(raw_row(2)).encode()
    path.write_bytes(first + b'\n' + second[:20])
    counter = r.RawCounter(tmp_path, {'static': 'static_model', 'moving256': 'moving_model'})
    assert counter.refresh() == counter.refresh() == 1
    with path.open('ab') as handle:
        handle.write(second[20:] + b'\n')
    assert counter.refresh() == counter.refresh() == 2


@pytest.mark.parametrize('fault', ['counter', 'seed', 'session', 'model', 'malformed'])
def test_raw_identity_and_corruption_fail_closed(tmp_path, fault):
    row = raw_row()
    if fault == 'counter':
        row['attempted_hand'] = 2
    elif fault == 'seed':
        row['policy_seed'] += 1
    elif fault == 'session':
        row['session_id'] += 'wrong'
    elif fault == 'model':
        row['model_sha256'] = 'other'
    path = raw_path(tmp_path)
    path.write_text('{bad}\n' if fault == 'malformed' else json.dumps(row) + '\n')
    with pytest.raises((ValueError, json.JSONDecodeError)):
        r.RawCounter(tmp_path, {'static': 'static_model', 'moving256': 'moving_model'}).refresh()


def test_raw_truncation_is_not_a_counter_reset(tmp_path):
    path = raw_path(tmp_path)
    path.write_text(json.dumps(raw_row()) + '\n')
    counter = r.RawCounter(tmp_path, {'static': 'static_model', 'moving256': 'moving_model'})
    assert counter.refresh() == 1
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='truncated'):
        counter.refresh()


def audits():
    models = {arm: arm + '_model' for arm in r.protocol.ARMS}
    reports = {}
    for arm in r.protocol.ARMS:
        rows = []
        for item in (row for row in r.protocol.schedule() if row['arm'] == arm):
            rows.append({'status': 'PASS', 'session_id': item['session_id'], 'policy_seed': item['policy_seed'],
                'model_sha256': models[arm], 'successful_hands': 2500, 'attempted_hands': 2500, 'target_hands': 2500,
                'pending_request_id': None, 'protocol_failures': 0, 'committed_without_raw': 0, 'partial_journal': False,
                'partial_hands': False, 'decision_replays': 5000, 'policy_draws_verified': 5000,
                'token_sha256': [f'{arm}_token_{item["index"]}']})
        reports[arm] = {'status': 'PASS', 'sessions': 16, 'successful_hands': 40000,
                        'model_sha256': models[arm], 'token_chains_disjoint': True, 'results': rows}
    return reports, models


def test_full_two_arm_token_audit_and_no_server_rng_claim():
    reports, models = audits()
    result = r.verify_audits(reports, models, {'old_token'})
    assert result['status'] == 'PASS' and result['hands'] == 80000 and result['sessions'] == 32
    assert result['server_rng_independence_proven'] is False


@pytest.mark.parametrize('fault', ['missing', 'partial', 'pending', 'no_replay', 'cross_token', 'prior_token'])
def test_invalid_or_reused_evidence_is_not_rescued(fault):
    reports, models = audits()
    old = {'old_token'}
    target = reports['moving256']['results'][0]
    if fault == 'missing':
        reports['moving256']['results'].pop()
    elif fault == 'partial':
        target['successful_hands'] -= 1
    elif fault == 'pending':
        target['pending_request_id'] = 'unfinished'
    elif fault == 'no_replay':
        target['policy_draws_verified'] -= 1
    elif fault == 'cross_token':
        target['token_sha256'] = reports['static']['results'][0]['token_sha256']
    else:
        old.update(target['token_sha256'])
    with pytest.raises(ValueError):
        r.verify_audits(reports, models, old)


def test_job_failure_has_no_implicit_retry(monkeypatch):
    runner = object.__new__(r.Runner)
    runner.tick = lambda **kwargs: None
    child = SimpleNamespace(poll=lambda: 1, wait=lambda: 1)
    closed = []
    handle = SimpleNamespace(close=lambda: closed.append(True))
    row = {'exit_code': None}
    with pytest.raises(ValueError, match='preserve without replacement'):
        runner.wait_jobs([(child, row, handle)])
    assert row['exit_code'] == 1 and closed == [True]


def test_seat_report_preserves_unequal_counts_and_units():
    seats = {arm: {seat: [[offset + index] * (index + 2) for index in range(16)]
                   for seat in (0, 1)} for arm, offset in [('static', 0), ('moving256', 10)]}
    result = r.seat_report(seats)
    assert result['by_arm']['static']['0']['hands'] == sum(range(2, 18))
    assert result['by_arm']['static']['0']['session_hand_counts'] == list(range(2, 18))
    assert result['moving_minus_static_by_seat']['0']['bb_per_100'] == 10
    assert result['descriptive_only']


def test_prior_initial_tokens_cover_failed_audit_sessions(tmp_path):
    old = tmp_path / 'old/sessions/s01/hands.jsonl'
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({'session_token_sha256': 'old_initial_token', 'session_id': 'old_session', 'policy_seed': 42}) + '\n')
    current = tmp_path / 'current/sessions/static/s01/hands.jsonl'
    current.parent.mkdir(parents=True)
    current.write_text(json.dumps({'session_token_sha256': 'new_token', 'session_id': 'new_session', 'policy_seed': 43}) + '\n')
    rows, unreadable = r.prior_initial_sessions(tmp_path, tmp_path / 'current')
    assert len(rows) == 1 and rows[0]['initial_token_sha256'] == 'old_initial_token' and not unreadable
    r.check_prior_prefixes(rows)
    r.check_unused_session_identifiers(rows)
    old.write_text('{}\n')
    with pytest.raises(ValueError, match='prefix changed'):
        r.check_prior_prefixes(rows)


@pytest.mark.parametrize('field', ['session_id', 'policy_seed'])
def test_previously_used_session_identifiers_refused(field):
    row = {'session_id': 'unused_old', 'policy_seed': 42}
    row[field] = r.protocol.schedule()[0][field]
    with pytest.raises(ValueError, match='already used'):
        r.check_unused_session_identifiers([row])


def test_valid_prefix_survives_a_later_bad_record(tmp_path):
    path = raw_path(tmp_path)
    path.write_text(json.dumps(raw_row(1)) + '\n' + json.dumps(raw_row(2)) + '\n{bad}\n')
    counter = r.RawCounter(tmp_path, {'static': 'static_model', 'moving256': 'moving_model'})
    with pytest.raises(json.JSONDecodeError):
        counter.refresh()
    assert sum(counter.counts.values()) == 2


def full_row(item, index, holes):
    chips = (10 if item['arm'] == 'moving256' else 0) + (100 if index % 2 else -100)
    return {'successful_hand': index, 'attempted_hand': index, 'session_id': item['session_id'],
        'policy_seed': item['policy_seed'], 'model_sha256': item['arm'] + '_model',
        'strict_policy_execution': True, 'policy_mode': 'greedy', 'policy_temperature': 0,
        'terminal_validation': {'status': 'PASS'}, 'winnings_chips': chips, 'winnings_bb': chips / 100,
        'terminal_response': {'client_pos': index % 2, 'hole_cards': holes},
        'decisions': [{'policy_mode': 'greedy', 'temperature': 0, 'observation_bridge_contract': r.protocol.BRIDGE,
                       'selected_action_slot': 1, 'greedy_action_slot': 1,
                       'behavior_action_probability': 1, 'direct_increment': 100, 'v6_action_table': [0, 100]}]}


def test_full_synthetic_cohort_parsing_and_cross_stream_check(tmp_path):
    models = {arm: arm + '_model' for arm in r.protocol.ARMS}
    for item in r.protocol.schedule():
        path = tmp_path / 'sessions' / item['arm'] / f's{item["index"]:02d}' / 'hands.jsonl'
        path.parent.mkdir(parents=True)
        rng = random.Random(item['policy_seed'])
        with path.open('w') as handle:
            for index in range(1, 2501):
                handle.write(json.dumps(full_row(item, index, rng.sample(range(52), 2))) + '\n')
    groups, seats, streams = r.parse_raw(tmp_path, models)
    assert sum(len(group) for arm in groups.values() for group in arm) == 80000
    assert all(sum(len(group) for group in seats[arm][seat]) == 20000 for arm in models for seat in (0, 1))
    assert streams['status'] == 'PASS' and len(streams['cross_arm_same_position_hero_hole_checks']) == 256
    assert r.protocol.summarize_pair(groups, evidence_valid=True)['moving_minus_static']['independent_raw_hands']['ordinary']['bb_per_100'] == 10


@pytest.mark.parametrize('fault', ['sampled', 'model', 'bridge', 'selected_slot', 'behavior_probability'])
def test_raw_execution_contract_corruption_refused(tmp_path, fault):
    item = r.protocol.schedule()[0]
    row = full_row(item, 1, [0, 1])
    if fault == 'sampled':
        row['policy_mode'] = 'sample'
    elif fault == 'model':
        row['model_sha256'] = 'different'
    elif fault == 'bridge':
        row['decisions'][0]['observation_bridge_contract'] = 'wrong'
    elif fault == 'selected_slot':
        row['decisions'][0]['selected_action_slot'] = 2
    else:
        row['decisions'][0]['behavior_action_probability'] = .5
    path = raw_path(tmp_path)
    path.write_text(json.dumps(row) + '\n')
    with pytest.raises(ValueError, match='execution mode|identity|decision mismatch'):
        r.parse_raw(tmp_path, {'static': 'static_model', 'moving256': 'moving256_model'})


def test_real_harmless_child_launch_and_receipt(tmp_path):
    runner = object.__new__(r.Runner)
    runner.base, runner.children, runner.handles = tmp_path, [], []
    runner.execution = {'children': []}
    runner.tick = lambda **kwargs: None
    commands = []
    runner.record = lambda argv: commands.append(argv)
    argv = [sys.executable, '-B', '-c', "import time; print('synthetic child',flush=True); time.sleep(.05)"]
    job = runner.launch(argv, 'offline_child_test', tmp_path / 'stdout.log')
    runner.wait_jobs([job])
    assert commands == [argv] and runner.execution['children'][0]['exit_code'] == 0
    assert not r.live_identity(runner.execution['children'][0])
    assert 'synthetic child' in (tmp_path / 'stdout.log').read_text()

# Seed3-specific admission checks supplement the unchanged executor regression suite.
def source_report_fixture():
    return {'schema': 'cardpilot.seed3.twice_recovered_two_seed_report.v1',
        'passed': True, 'phase': 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS',
        'accounting': {'per_arm_cumulative_physical_hands': dict(r.EXPECTED_HANDS),
            'evaluation_hands': 131072, 'slumbot_hands': 0, 'retained_training_hands': 8393542,
            'new_training_hands': 8397834, 'observed_uncheckpointed_training_hands': 4292,
            'recovered_unpublished_hands_already_in_retained': 5256,
            'unknown_additional_worker_tail_hands': None,
            'interrupted_attempts': [{'unknown_additional_worker_tail_hands': None} for _ in range(2)]},
        'input_sha256': {str(path): digest for path, digest in r.EXPECTED_MODELS.values()}}


def test_seed3_endpoint_paths_hashes_and_report_binding():
    assert r.TRAINING.name == 'v6-phase-held-reference-seed3-replication-20260905'
    assert r.REPORT.parent.name == 'recovery_20260905b'
    assert r.REPORT_SHA == '820862d4e74af6999260b14e0c05a6ba213edffc9d907060cf60d140f802a6d5'
    assert r.EXPECTED_HANDS == {'static': 8392377, 'moving256': 8390981}
    assert r.EXPECTED_MODELS['static'][0] == r.TRAINING / 'static_stage2/latest.pt'
    assert r.EXPECTED_MODELS['static'][1] == '36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69'
    assert r.EXPECTED_MODELS['moving256'][1] == 'da6d49c60eb73ceddb6a27ff8ff10de06b3306360f61dd49e49b82cd857f4b8c'
    r.validate_training_report(source_report_fixture())


def test_seed3_identifiers_change_only_identity_not_fixed_schedule():
    for row in r.protocol.schedule():
        assert row['policy_seed'] == (2026365100 if row['arm'] == 'static' else 2026365200) + row['index']
        assert row['session_id'] == f"v6_phase_reference_seed3_external_20260905_{row['arm']}_s{row['index']:02d}"
        assert row['hands'] == 2500
    assert sum(row['hands'] for row in r.protocol.schedule()) == 80000


@pytest.mark.parametrize('active_index', range(3))
def test_each_preserved_training_controller_must_be_terminal(monkeypatch, active_index):
    seen = []
    def fake_read(path):
        if path == r.TRAINING / 'experiment.json':
            return {'status': 'COMPLETED'}
        assert path.name == 'ownership.json', 'outcomes read before all owners were checked'
        index = r.TRAINING_ROOTS.index(path.parent)
        seen.append(index)
        return {'pid': index}
    monkeypatch.setattr(r, 'read', fake_read)
    monkeypatch.setattr(r, 'live_identity', lambda identity: identity['pid'] == active_index)
    with pytest.raises(ValueError, match='controller still live'):
        r.training_ready()
    assert seen == list(range(active_index + 1))


@pytest.mark.parametrize('fault', ['schema', 'passed', 'phase', 'dose', 'evaluation', 'external_hands',
                                  'retained', 'executed', 'lost', 'recovered', 'tail', 'partial_tail',
                                  'missing_interruption', 'model'])
def test_seed3_report_substitution_or_accounting_corruption_is_refused(fault):
    value = source_report_fixture()
    counts = value['accounting']
    if fault == 'schema':
        value['schema'] = 'old_report'
    elif fault == 'passed':
        value['passed'] = False
    elif fault == 'phase':
        value['phase'] = 'RUNNING'
    elif fault == 'dose':
        counts['per_arm_cumulative_physical_hands']['moving256'] -= 1
    elif fault == 'evaluation':
        counts['evaluation_hands'] -= 1
    elif fault == 'external_hands':
        counts['slumbot_hands'] = 1
    elif fault == 'retained':
        counts['retained_training_hands'] += 5256
    elif fault == 'executed':
        counts['new_training_hands'] = counts['retained_training_hands']
    elif fault == 'lost':
        counts['observed_uncheckpointed_training_hands'] = 0
    elif fault == 'recovered':
        counts['recovered_unpublished_hands_already_in_retained'] = 0
    elif fault == 'tail':
        counts['unknown_additional_worker_tail_hands'] = 0
    elif fault == 'partial_tail':
        counts['interrupted_attempts'][0]['unknown_additional_worker_tail_hands'] = 0
    elif fault == 'missing_interruption':
        counts['interrupted_attempts'].pop()
    else:
        value['input_sha256'][str(r.EXPECTED_MODELS['static'][0])] = 'wrong_model'
    with pytest.raises(ValueError):
        r.validate_training_report(value)
