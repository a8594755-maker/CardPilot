import importlib.util
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('strict_sampled_external_runner', BASE/'run_external.py')
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_client_is_fixed_native_sample_and_explicit_seed():
    item = dict(requested_hands=2500, policy_seed=2026091001, raw_hands='raw', dump='dump', result='result')
    args = run.client_args('script', 'model', item)
    assert '--strict-policy-execution' in args
    assert args[args.index('--hands')+1] == '2500'
    assert args[args.index('--policy-mode')+1] == 'sample'
    assert args[args.index('--temperature')+1] == '1'
    assert args[args.index('--policy-seed')+1] == '2026091001'
    dry = run.client_args('script', 'model', item, hands=0, result='dry')
    assert dry[dry.index('--hands')+1] == '0'
    assert '--hand-results-jsonl' not in dry and '--dump-slumbot' not in dry


def test_counter_buffers_incomplete_rows_and_does_not_double_count(tmp_path):
    path = tmp_path/'raw.jsonl'
    counter = run.RawCounter(path)
    assert counter.scan() == 0
    path.write_bytes(b'{"winnings_chips":5}\n{"winnings_ch')
    assert counter.scan() == 1 and counter.scan() == 1
    with path.open('ab') as stream:
        stream.write(b'ips":-5}\n')
    assert counter.scan() == 2 and counter.tail == b''
    path.write_bytes(b'')
    with pytest.raises(ValueError): counter.scan()


def test_counter_rejects_malformed_complete_row(tmp_path):
    path = tmp_path/'raw.jsonl'
    path.write_text('{bad}\n')
    with pytest.raises(ValueError): run.RawCounter(path).scan()


def audit(point):
    return dict(status='PASS', summary=dict(hands=20000, bb_per_100=point),
                sessions=[dict(hands=2500, total_chips=point*2500) for _ in range(8)])


@pytest.mark.parametrize('point,admitted', [(1., True), (0., False), (-1., False)])
def test_pilot_admission_does_not_claim_goal(point, admitted):
    result = run.summarize_audit(audit(point))
    assert result['admits_separate_fresh100k'] is admitted
    assert result['goal_achieved'] is False
    assert result['session_mean_t95']['point'] == point


def test_incomplete_counts_or_audit_fail_rejected():
    for change in ['status', 'hands', 'session_count', 'session_size', 'point_disagreement']:
        doc = audit(1.)
        if change == 'status': doc['status'] = 'FAIL'
        elif change == 'hands': doc['summary']['hands'] -= 1
        elif change == 'session_count': doc['sessions'].pop()
        elif change == 'session_size': doc['sessions'][0]['hands'] -= 1
        else: doc['summary']['bb_per_100'] += 1
        with pytest.raises(ValueError): run.summarize_audit(doc)


def test_session_sensitivity_keeps_primary_separate():
    doc = audit(2.)
    for index, row in enumerate(doc['sessions']):
        row['total_chips'] = (2+index-3.5)*2500
    result = run.summarize_audit(doc)
    assert result['raw']['bb_per_100'] == 2.
    assert result['session_mean_t95']['lower'] < 0 < result['session_mean_t95']['upper']


def confirmation_inputs():
    record = dict(status='COMPLETED', metrics={'post_exit_review_pass': 1}, accounting={'evaluation_hands': 147456})
    review = dict(status='PASS', replication_passed=True, decision='WEAK_KL_REPLICATION_PASSED',
        seed=20260909, evaluation_hands=147456, new_training_hands=0, slumbot_hands=0,
        candidate_hashes={'weak': run.DIGEST})
    readiness = dict(status='PASS', checkpoint_sha256=run.DIGEST, actual_slumbot_hands=0, network_calls_attempted=0)
    return record, review, readiness


def test_confirmation_gate_accepts_only_reviewed_frozen_endpoint():
    run.validate_confirmation(*confirmation_inputs())


@pytest.mark.parametrize('bad', ['running', 'unreviewed', 'incomplete', 'failed', 'wrong_seed',
    'wrong_checkpoint', 'training', 'readiness_network', 'readiness_checkpoint'])
def test_confirmation_gate_rejects_unqualified_external_launch(bad):
    record, review, readiness = confirmation_inputs()
    if bad == 'running': record['status'] = 'RUNNING'
    elif bad == 'unreviewed': record['metrics']['post_exit_review_pass'] = 0
    elif bad == 'incomplete': record['accounting']['evaluation_hands'] -= 1
    elif bad == 'failed': review['replication_passed'] = False
    elif bad == 'wrong_seed': review['seed'] = 20260908
    elif bad == 'wrong_checkpoint': review['candidate_hashes']['weak'] = 'different'
    elif bad == 'training': review['new_training_hands'] = 1
    elif bad == 'readiness_network': readiness['network_calls_attempted'] = 1
    else: readiness['checkpoint_sha256'] = 'different'
    with pytest.raises(ValueError): run.validate_confirmation(record, review, readiness)
