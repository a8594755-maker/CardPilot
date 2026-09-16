"""Draft executor offline admission, raw accounting and audit failure tests."""
import copy
import importlib.util
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('actor_route_runner_tests', Path(__file__).with_name('run_pair.py'))
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
            'policy_seed': item['policy_seed'], 'model_sha256': 'seed1_detached_model'}


def raw_path(base):
    path = base / 'sessions/seed1_detached/s01/hands.jsonl'
    path.parent.mkdir(parents=True)
    return path


def test_incremental_counter_counts_complete_lines_once(tmp_path):
    path = raw_path(tmp_path)
    first, second = json.dumps(raw_row(1)).encode(), json.dumps(raw_row(2)).encode()
    path.write_bytes(first + b'\n' + second[:20])
    counter = r.RawCounter(tmp_path, {arm: arm + '_model' for arm in r.protocol.ARMS})
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
        r.RawCounter(tmp_path, {arm: arm + '_model' for arm in r.protocol.ARMS}).refresh()


def test_raw_truncation_is_not_a_counter_reset(tmp_path):
    path = raw_path(tmp_path)
    path.write_text(json.dumps(raw_row()) + '\n')
    counter = r.RawCounter(tmp_path, {arm: arm + '_model' for arm in r.protocol.ARMS})
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
        reports[arm] = {'status': 'PASS', 'sessions': 8, 'successful_hands': 20000,
                        'model_sha256': models[arm], 'token_chains_disjoint': True, 'results': rows}
    return reports, models


def test_detached_four_arm_token_audit_and_no_server_rng_claim():
    reports, models = audits()
    result = r.verify_audits(reports, models, {'old_token'})
    assert result['status'] == 'PASS' and result['hands'] == 80000 and result['sessions'] == 32
    assert result['server_rng_independence_proven'] is False


@pytest.mark.parametrize('fault', ['missing', 'partial', 'pending', 'no_replay', 'cross_token', 'prior_token'])
def test_invalid_or_reused_evidence_is_not_rescued(fault):
    reports, models = audits()
    old = {'old_token'}
    target = reports['seed1_connected']['results'][0]
    if fault == 'missing':
        reports['seed1_connected']['results'].pop()
    elif fault == 'partial':
        target['successful_hands'] -= 1
    elif fault == 'pending':
        target['pending_request_id'] = 'unfinished'
    elif fault == 'no_replay':
        target['policy_draws_verified'] -= 1
    elif fault == 'cross_token':
        target['token_sha256'] = reports['seed1_detached']['results'][0]['token_sha256']
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
    seats = {arm: {seat: [[offset + index] * (index + 2) for index in range(8)]
                   for seat in (0, 1)} for arm, offset in [(arm, 10 if arm.endswith('connected') else 0) for arm in r.protocol.ARMS]}
    result = r.seat_report(seats)
    assert result['by_arm']['seed1_detached']['0']['hands'] == sum(range(2, 10))
    assert result['by_arm']['seed1_detached']['0']['session_hand_counts'] == list(range(2, 10))
    assert result['connected_minus_detached_by_seed_and_seat']['1']['0']['bb_per_100'] == 10
    assert result['descriptive_only']


def test_prior_initial_tokens_cover_failed_audit_sessions(tmp_path):
    old = tmp_path / 'old/sessions/s01/hands.jsonl'
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({'session_token_sha256': 'old_initial_token', 'session_id': 'old_session', 'policy_seed': 42}) + '\n')
    current = tmp_path / 'current/sessions/seed1_detached/s01/hands.jsonl'
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
    counter = r.RawCounter(tmp_path, {arm: arm + '_model' for arm in r.protocol.ARMS})
    with pytest.raises(json.JSONDecodeError):
        counter.refresh()
    assert sum(counter.counts.values()) == 2


def full_row(item, index, holes):
    chips = (10 if item['arm'].endswith('connected') else 0) + (100 if index % 2 else -100)
    return {'successful_hand': index, 'attempted_hand': index, 'session_id': item['session_id'],
        'policy_seed': item['policy_seed'], 'model_sha256': item['arm'] + '_model',
        'strict_policy_execution': True, 'policy_mode': 'greedy', 'policy_temperature': 0,
        'terminal_validation': {'status': 'PASS'}, 'winnings_chips': chips, 'winnings_bb': chips / 100,
        'terminal_response': {'client_pos': index % 2, 'hole_cards': holes},
        'decisions': [{'policy_mode': 'greedy', 'temperature': 0, 'observation_bridge_contract': r.protocol.BRIDGE,
                       'selected_action_slot': 1, 'greedy_action_slot': 1,
                       'behavior_action_probability': 1, 'direct_increment': 100, 'v6_action_table': [0, 100]}]}


def test_detached_synthetic_cohort_parsing_and_cross_stream_check(tmp_path):
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
    assert all(sum(len(group) for group in seats[arm][seat]) == 10000 for arm in models for seat in (0, 1))
    assert streams['status'] == 'PASS' and len(streams['cross_arm_same_position_hero_hole_checks']) == 384
    assert r.protocol.summarize_four(groups, evidence_valid=True)['connected_minus_detached_by_seed']['1']['independent_raw_hands']['ordinary']['bb_per_100'] == 10


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
        r.parse_raw(tmp_path, {arm: arm + '_model' for arm in r.protocol.ARMS})


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


def source_report_fixture():
    return {'passed': True, 'phase': 'FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW',
        'all_recorded_processes_terminal': True, 'observed_child_identities_checked': 112,
        'accounting': {'new_training_hands': 4203389, 'evaluation_hands': 262144,
                       'slumbot_hands': 0, 'final_qualification_hands': 0},
        'unknown_additional_worker_tail_hands': None,
        'statistical_not_bitwise_worker_continuation': True,
        'input_sha256': {str(path): digest for path, digest in r.EXPECTED_MODELS.values()},
        'training_health_and_realized_update_dose': {
            arm + '_stage2': {'cumulative_physical_hands': r.EXPECTED_HANDS[arm],
                             'frozen_endpoint_sha256': digest}
            for arm, (path, digest) in r.EXPECTED_MODELS.items()}}


def test_four_exact_final_endpoints_and_completed_review_bound():
    assert set(r.EXPECTED_MODELS) == set(r.protocol.ARMS)
    assert r.TRAINING.name == 'v6-preflop-actor-trunk-two-seed-geometric-20260906'
    assert r.REPORT_SHA == '4a244d2f06991c2bab1657f295d1b2fa218758f46827f888555ff35cb770bced'
    assert r.EXPECTED_HANDS == {'seed1_detached': 11547070, 'seed1_connected': 11551174,
                                'seed3_detached': 11542774, 'seed3_connected': 11543121}
    for arm, (path, digest) in r.EXPECTED_MODELS.items():
        assert path == r.TRAINING / (arm + '_stage2/latest.pt')
        assert len(digest) == 64
    r.validate_training_report(source_report_fixture())


@pytest.mark.parametrize('fault', ['passed', 'phase', 'terminal', 'children', 'train',
                                  'eval', 'slumbot', 'final', 'sha', 'dose'])
def test_training_report_corruption_refused(fault):
    value = source_report_fixture()
    if fault == 'passed': value['passed'] = False
    elif fault == 'phase': value['phase'] = 'RUNNING'
    elif fault == 'terminal': value['all_recorded_processes_terminal'] = False
    elif fault == 'children': value['observed_child_identities_checked'] -= 1
    elif fault in ('train', 'eval', 'slumbot', 'final'):
        key = {'train':'new_training_hands', 'eval':'evaluation_hands',
               'slumbot':'slumbot_hands', 'final':'final_qualification_hands'}[fault]
        value['accounting'][key] += 1
    elif fault == 'sha':
        value['input_sha256'][str(r.EXPECTED_MODELS['seed3_connected'][0])] = 'other'
    else:
        value['training_health_and_realized_update_dose']['seed3_connected_stage2']['cumulative_physical_hands'] -= 1
    with pytest.raises(ValueError):
        r.validate_training_report(value)


@pytest.mark.parametrize('arm', r.protocol.ARMS)
def test_missing_any_arm_or_wrong_eight_session_coverage_refused(arm):
    reports, models = audits()
    missing = copy.deepcopy(reports)
    missing.pop(arm)
    with pytest.raises(ValueError, match='four-arm'):
        r.verify_audits(missing, models, set())
    reports[arm]['sessions'] = 16
    with pytest.raises(ValueError, match='incomplete'):
        r.verify_audits(reports, models, set())


@pytest.mark.parametrize('failed_launch', [None, 3])
def test_controller_failure_drains_launched_wave_and_never_restarts(tmp_path, failed_launch):
    runner = object.__new__(r.Runner)
    runner.base, runner.children, runner.handles = tmp_path, [], []
    runner.started = r.time.monotonic()
    runner.execution = {'children': [], 'waves': []}
    runner.counter = SimpleNamespace(refresh=lambda: 0, counts={})
    runner.runtime = tmp_path / 'runtime/scripts'
    runner.last_count = 0
    runner.prepare = lambda: None
    runner.verify_inputs = lambda: None
    runner.tick = lambda **kwargs: None
    runner.log = lambda *args: None
    launches, waits = [], []
    def launch(argv, role, output, **extra):
        launches.append(role)
        if failed_launch and len(launches) == failed_launch:
            raise OSError('synthetic launch failure')
        child = SimpleNamespace(poll=lambda: None, wait=lambda: waits.append(role) or 1)
        row = {'role': role, 'exit_code': None}
        runner.children.append((child, row))
        return child, row, SimpleNamespace(close=lambda: None)
    runner.launch = launch
    runner.wait_jobs = lambda jobs: (_ for _ in ()).throw(ValueError('synthetic wave failure'))
    with pytest.raises(SystemExit) as error:
        runner.run()
    assert error.value.code == 1
    assert len(launches) == (failed_launch or 8)
    assert len(waits) == (failed_launch - 1 if failed_launch else 8)
    assert len(runner.execution['waves']) == 1
    assert r.read(tmp_path / 'failure.json')['automatic_retry'] is False
    assert r.read(tmp_path / 'execution.json')['status'] == 'FAILED_PRESERVED'


@pytest.mark.parametrize('fault', ['passed', 'checkpoint_sha256', 'missing_normal_termination_evidence',
    'exit_code', 'cause', 'unknown_additional_worker_tail_hands', 'original_process_identities_absent',
    'other_python_processes_at_audit'])
def test_recovery_exception_is_narrow_and_preserves_unknowns(fault):
    value = dict(passed=True, checkpoint_sha256=r.PARTIAL_SHA, missing_normal_termination_evidence=True,
        exit_code=None, cause=None, unknown_additional_worker_tail_hands=None,
        original_process_identities_absent=True, other_python_processes_at_audit=[])
    r.validate_interruption(value)
    value[fault] = {'passed': False, 'checkpoint_sha256': 'wrong',
        'missing_normal_termination_evidence': False, 'exit_code': 0, 'cause': 'assumed',
        'unknown_additional_worker_tail_hands': 0, 'original_process_identities_absent': False,
        'other_python_processes_at_audit': [999]}[fault]
    with pytest.raises(ValueError, match='unqualified interruption'):
        r.validate_interruption(value)


@pytest.mark.parametrize('field,value', [('unknown_additional_worker_tail_hands', 0),
    ('statistical_not_bitwise_worker_continuation', False)])
def test_training_uncertainty_cannot_be_relabelled(field, value):
    report = source_report_fixture()
    report[field] = value
    with pytest.raises(ValueError, match='uncertainty'):
        r.validate_training_report(report)
