import importlib.util
from pathlib import Path
import statistics
import json
import copy

import pytest

spec = importlib.util.spec_from_file_location('four_policy_external_review_tests', Path(__file__).with_name('review_completed.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def execution():
    children = [{'role': 'offline_prerun_tests', 'pid': 200, 'create_time': 456, 'exit_code': 0}]
    for item in m.r.protocol.schedule():
        children.append({'role': item['session_id'], 'pid': 200 + len(children), 'create_time': 456,
            'exit_code': 0, 'arm': item['arm'], 'wave': item['wave'], 'session_index': item['index'],
            'command': [m.sys.executable, '-u', *m.r.protocol.session_command(item, m.BASE, m.BASE / 'runtime/scripts')]})
    for arm in m.r.protocol.ARMS:
        for suffix in ('_combined_audit', '_independence_stdout'):
            children.append({'role': arm + suffix, 'pid': 200 + len(children),
                             'create_time': 456, 'exit_code': 0})
    return {'pid': 123, 'create_time': 456, 'status': 'COMPLETED_PENDING_REVIEW',
        'children': children, 'evaluation_hands': 80000, 'slumbot_hands': 80000,
        'waves': [{'wave': i, 'finished_at': '2026-09-06T08:00:00+00:00'} for i in range(4)]}


def test_live_owner_blocks_before_any_outcomes(monkeypatch):
    reads = []
    def read(path):
        reads.append(path.name)
        assert path.name == 'execution.json'
        return {'pid': 123, 'create_time': 456}
    monkeypatch.setattr(m.r, 'read', read)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: True)
    assert m.readiness()['ready'] is False
    with pytest.raises(ValueError, match='not ready'):
        m.build_report()
    assert reads == ['execution.json', 'execution.json']


def test_live_child_blocks(monkeypatch):
    monkeypatch.setattr(m.r, 'read', lambda path: execution())
    monkeypatch.setattr(m.r, 'live_identity', lambda row: row['pid'] == 200)
    assert m.readiness()['ready'] is False


def test_failed_execution_blocks(monkeypatch):
    value = execution()
    value['status'] = 'FAILED_PRESERVED'
    monkeypatch.setattr(m.r, 'read', lambda path: value)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    assert m.readiness()['ready'] is False


@pytest.mark.parametrize('bad', ['jobs', 'exit', 'hands', 'slumbot', 'waves', 'wave_end'])
def test_incomplete_evidence_rejected(monkeypatch, bad):
    value = execution()
    if bad == 'jobs':
        value['children'].pop()
    elif bad == 'exit':
        value['children'][0]['exit_code'] = 1
    elif bad == 'hands':
        value['evaluation_hands'] -= 1
    elif bad == 'slumbot':
        value['slumbot_hands'] -= 1
    elif bad == 'waves':
        value['waves'].pop()
    else:
        value['waves'][0]['finished_at'] = None
    monkeypatch.setattr(m.r, 'read', lambda path: value)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    with pytest.raises(ValueError):
        m.readiness()


def test_exact_terminal_evidence_ready(monkeypatch):
    monkeypatch.setattr(m.r, 'read', lambda path: execution())
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    assert m.readiness() == {'ready': True}


def test_integer_moments_matches_independent_statistics():
    values = [-20000, -100, 0, 50, 1200, 20000]
    result = m.integer_moments(values)
    assert result['bb_per_100'] == statistics.mean(values)
    assert result['variance_chips2'] == pytest.approx(statistics.variance(values))
    assert result['sum_chips'] == sum(values)


@pytest.mark.parametrize('values', [[0], [0, float('nan')], [0, 20001], [True, 0]])
def test_moments_rejects_invalid_physical_chips(values):
    with pytest.raises(ValueError):
        m.integer_moments(values)


@pytest.mark.parametrize('fault', ['role', 'duplicate', 'model', 'hands', 'arm', 'wave', 'index', 'wave_order'])
def test_wrong_job_or_executed_contract_not_admitted(monkeypatch, fault):
    value = execution()
    client = value['children'][1]
    if fault == 'role': client['role'] = 'unregistered'
    elif fault == 'duplicate': client['role'] = value['children'][2]['role']
    elif fault in ('model', 'hands'):
        argv = client['command']
        argv[argv.index('--' + fault) + 1] = 'wrong'
    elif fault == 'arm': client['arm'] = 'winner'
    elif fault == 'wave': client['wave'] = 3
    elif fault == 'index': client['session_index'] = 8
    else: value['waves'].reverse()
    monkeypatch.setattr(m.r, 'read', lambda path: value)
    monkeypatch.setattr(m.r, 'live_identity', lambda row: False)
    with pytest.raises(ValueError):
        m.readiness()


def test_four_arm_fixture_total_and_moments():
    values = {arm: [(-100 if i % 2 else 200) + offset for i in range(20000)]
              for offset, arm in enumerate(m.r.protocol.ARMS)}
    assert sum(m.integer_moments(v)['hands'] for v in values.values()) == 80000
    for arm, v in values.items():
        expected = m.r.protocol.arm_summary([v[i:i+2500] for i in range(0, 20000, 2500)])
        measured = m.integer_moments(v)
        assert measured['bb_per_100'] == expected['bb_per_100']
        assert measured['raw_ci95'] == pytest.approx(expected['raw_hand_ci95'])


@pytest.fixture(scope='module')
def audited_fixture(tmp_path_factory):
    base = tmp_path_factory.mktemp('four_policy_raw_review')
    models = {arm: {'sha256': 'synthetic_' + arm} for arm in m.r.protocol.ARMS}
    spec = {'models': models, 'schedule': m.r.protocol.schedule()}
    (base / 'launch_spec.json').write_text(json.dumps(spec))
    for arm in m.r.protocol.ARMS:
        results = []
        for item in [row for row in spec['schedule'] if row['arm'] == arm]:
            session = base / 'sessions' / arm / f"s{item['index']:02d}"
            session.mkdir(parents=True)
            chips = 10 if arm.endswith('half') else -5
            (session / 'journal.jsonl').write_text('{"synthetic":true}\n')
            with (session / 'hands.jsonl').open('w') as handle:
                for i in range(1, 2501):
                    row = {'successful_hand': i, 'attempted_hand': i,
                        'session_id': item['session_id'], 'policy_seed': item['policy_seed'],
                        'model_sha256': models[arm]['sha256'], 'policy_mode': 'greedy',
                        'policy_temperature': 0, 'strict_policy_execution': True,
                        'terminal_validation': {'status': 'PASS'}, 'winnings_bb': chips / 100,
                        'winnings_chips': chips,
                        'decisions': [{'observation_bridge_contract': m.r.protocol.BRIDGE}]}
                    handle.write(json.dumps(row) + '\n')
            results.append({'directory': str(session), 'status': 'PASS', 'session_id': item['session_id'],
                'model_sha256': models[arm]['sha256'], 'policy_seed': item['policy_seed'],
                'successful_hands': 2500, 'attempted_hands': 2500, 'target_hands': 2500,
                'pending_request_id': None, 'protocol_failures': 0, 'committed_without_raw': 0,
                'partial_journal': False, 'partial_hands': False, 'decision_replays': 2500,
                'policy_draws_verified': 2500, 'cumulative_chips': chips * 2500,
                'hands_sha256': m.r.sha(session / 'hands.jsonl'),
                'journal_sha256': m.r.sha(session / 'journal.jsonl')})
        audit = {'status': 'PASS', 'model_sha256': models[arm]['sha256'], 'sessions': 8,
                 'successful_hands': 20000, 'results': results}
        (base / f'{arm}_combined_audit.json').write_text(json.dumps(audit))
    return base


def test_full_raw_review_hash_accounting_fixture(audited_fixture):
    inputs = {}
    groups, moments, replays = m.reviewed_groups(audited_fixture, inputs)
    assert replays == 80000
    assert len(inputs) == 69  # launch spec + four audits + 64 journal/raw hashes
    assert sum(row['hands'] for row in moments.values()) == 80000
    for arm in m.r.protocol.ARMS:
        assert len(groups[arm]) == 8
        assert moments[arm]['bb_per_100'] == (10 if arm.endswith('half') else -5)


@pytest.mark.parametrize('fault', ['model', 'old16', 'path', 'pending', 'replay', 'payout', 'raw_hash', 'journal_hash'])
def test_review_rejects_substituted_or_incomplete_audit(audited_fixture, monkeypatch, fault):
    path = audited_fixture / 'seed1_full_combined_audit.json'
    original_read = m.r.read
    value = copy.deepcopy(original_read(path))
    target = value['results'][0]
    if fault == 'model': value['model_sha256'] = 'wrong'
    elif fault == 'old16': value['sessions'] = 16
    elif fault == 'path': target['directory'] = str(audited_fixture / 'other')
    elif fault == 'pending': target['pending_request_id'] = 'uncommitted'
    elif fault == 'replay': target['policy_draws_verified'] -= 1
    elif fault == 'payout': target['cumulative_chips'] += 1
    elif fault == 'raw_hash': target['hands_sha256'] = 'wrong'
    else: target['journal_sha256'] = 'wrong'
    monkeypatch.setattr(m.r, 'read', lambda p: value if p == path else original_read(p))
    with pytest.raises(ValueError):
        m.reviewed_groups(audited_fixture, {})
