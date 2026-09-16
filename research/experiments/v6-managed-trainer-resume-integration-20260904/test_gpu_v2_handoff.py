import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('gpu_v2_adapter', Path(__file__).with_name('gpu_qualification_v2_handoff.py'))
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def base(extra=()):
    return {'eligible': False, 'phase': 'STOPPED_FOR_RESEARCHER_ATTENTION',
            'blocked_by': [adapter.OLD_PHASE_BLOCK, *extra], 'input_hashes': {'original': 'a'}}


def handoff(qualified=True):
    return {'qualified': qualified, 'phase': 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS' if qualified else 'PREREGISTERED_FROZEN_EVALUATION',
            'blocked_by': [] if qualified else ['v2 owner still live'], 'input_hashes': {'new': 'b'}}


def documents():
    return ({'phase': 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS', 'active_child_pid': None},
            {'status': 'COMPLETED', 'accounting': {'evaluation_hands': 98304}},
            {'status': 'COMPLETED', 'schema': 'cardpilot.static_current_kl_4m_aggregate.v1',
             'evaluation_hands': 98304, 'offline_drift_states': 60000},
            {'status': 'COMPLETED', 'schema': 'cardpilot.static4m.deviation_aware_descriptive_report.v1',
             'evaluation_hands': 98304, 'aggregate': {'by_seed': {'1': {}, '2': {}, '3': {}}},
             'original_training_audit_passed': False, 'automatic_scaling_authorized': False, 'promote': False})


def test_releases_only_obsolete_phase_with_no_input_mutation():
    original = base()
    before = copy.deepcopy(original)
    result = adapter.combine_preflights(original, handoff())
    assert result['eligible']
    assert result['phase'] == 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS'
    assert result['input_hashes'] == {'original': 'a', 'new': 'b'}
    assert original == before


@pytest.mark.parametrize('block', ['production not integrated', 'other trainer live', 'checkpoint hash mismatch'])
def test_never_clears_other_original_blockers(block):
    result = adapter.combine_preflights(base([block]), handoff())
    assert not result['eligible']
    assert result['blocked_by'] == [block]


def test_live_successor_keeps_phase_block():
    result = adapter.combine_preflights(base(), handoff(False))
    assert not result['eligible']
    assert adapter.OLD_PHASE_BLOCK in result['blocked_by']


@pytest.mark.parametrize('mutation', ['phase', 'absent_objection', 'duplicate_objection', 'hash_conflict'])
def test_inconsistent_handoff_stops(mutation):
    original, successor = base(), handoff()
    if mutation == 'phase':
        original['phase'] = 'WAITING_FOR_NATURAL_TRAINING_BOUNDARY'
    elif mutation == 'absent_objection':
        original['blocked_by'] = []
    elif mutation == 'duplicate_objection':
        original['blocked_by'] *= 2
    else:
        successor['input_hashes']['original'] = 'changed'
    assert not adapter.combine_preflights(original, successor)['eligible']


def test_complete_evidence_does_not_require_favorable_poker_scores():
    values = documents()
    values[-1]['all_directional_gates_descriptively_pass'] = False
    assert all(adapter.verify_terminal_documents(*values).values())


@pytest.mark.parametrize('mutation', ['live_phase', 'child', 'record', 'accounting', 'budget',
                                    'drift', 'report', 'seed', 'rewritten_failure', 'auto_scale'])
def test_incomplete_terminal_documents_are_not_handoff(mutation):
    state, record, aggregate, report = documents()
    if mutation == 'live_phase':
        state['phase'] = 'PREREGISTERED_OFFLINE_DRIFT'
    elif mutation == 'child':
        state['active_child_pid'] = 123
    elif mutation == 'record':
        record['status'] = 'RUNNING'
    elif mutation == 'accounting':
        record['accounting']['evaluation_hands'] = 32768
    elif mutation == 'budget':
        aggregate['evaluation_hands'] = 98300
    elif mutation == 'drift':
        aggregate['offline_drift_states'] = 59999
    elif mutation == 'report':
        report['status'] = 'RUNNING'
    elif mutation == 'seed':
        report['aggregate']['by_seed'].pop('2')
    elif mutation == 'rewritten_failure':
        report['original_training_audit_passed'] = True
    else:
        report['automatic_scaling_authorized'] = True
    with pytest.raises(ValueError):
        adapter.verify_terminal_documents(state, record, aggregate, report)


def test_original_diagnostic_stays_hash_bound_and_unchanged():
    assert adapter.original.sha(adapter.BASE / 'run_gpu_resume_qualification.py') == adapter.ORIGINAL_RUNNER_SHA
    assert adapter.original.sha(adapter.BASE / 'gpu_qualification_protocol.md') == adapter.ORIGINAL_PROTOCOL_SHA
    assert adapter.original.ORDER == (('single1', 1), ('multi8', 1), ('multi8', 2), ('single1', 2))
    assert adapter.original.DELTA == 8192
    assert adapter.original.PARENT_SHA == '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'
