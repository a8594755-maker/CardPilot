"""Add an explicit terminal-v2 handoff proof to the unchanged GPU diagnostic."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('unchanged_gpu_qualification', BASE / 'run_gpu_resume_qualification.py')
original = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(original)
original_preflight = original.preflight

OLD_PHASE_BLOCK = 'guarded phase not a qualified handoff: STOPPED_FOR_RESEARCHER_ATTENTION'
OLD_PRODUCTION_SHA = '594f1de70f9a6abdf8076fe129a18056b5a3bd84087ad4f6cc2f1498850a6956'
ORIGINAL_RUNNER_SHA = 'c9430179f702d3871c4297ad837decf9d1b4327fc12cf537a8ec4ad9ff2a262a'
ORIGINAL_PROTOCOL_SHA = '17fa287eca8ae8e67a760671d7667e171341616c0b79b782100da863741c0d1b'


def verify_terminal_documents(state, record, aggregate, report):
    checks = {
        'v2_terminal_ready': state.get('phase') == 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS',
        'v2_no_active_child': state.get('active_child_pid') is None,
        'same_experiment_finished': record.get('status') == 'COMPLETED',
        'complete_evaluation_accounting': record.get('accounting', {}).get('evaluation_hands') == 98304,
        'original_aggregate_complete': aggregate.get('status') == 'COMPLETED'
            and aggregate.get('schema') == 'cardpilot.static_current_kl_4m_aggregate.v1',
        'original_budgets_complete': aggregate.get('evaluation_hands') == 98304
            and aggregate.get('offline_drift_states') == 60000,
        'scoped_report_complete': report.get('status') == 'COMPLETED'
            and report.get('schema') == 'cardpilot.static4m.deviation_aware_descriptive_report.v1'
            and report.get('evaluation_hands') == 98304,
        'all_three_seeds_retained': set(report.get('aggregate', {}).get('by_seed', {})) == {'1', '2', '3'},
        'original_failures_preserved': report.get('original_training_audit_passed') is False,
        'no_automatic_scale': report.get('automatic_scaling_authorized') is False
            and report.get('promote') is False,
    }
    failures = [key for key, value in checks.items() if not value]
    if failures:
        raise ValueError(f'incomplete v2 handoff: {failures}')
    return checks


def combine_preflights(base, handoff):
    """Replace one obsolete phase objection only; never clear other blockers."""
    result = dict(base)
    blocks = list(base['blocked_by'])
    result['input_hashes'] = dict(base['input_hashes'])
    if base.get('phase') != 'STOPPED_FOR_RESEARCHER_ATTENTION':
        blocks.append('v2 adapter requires the preserved original stopped phase')
    elif handoff['qualified']:
        if blocks.count(OLD_PHASE_BLOCK) != 1:
            blocks.append('expected unique original phase blocker is absent or duplicated')
        else:
            blocks.remove(OLD_PHASE_BLOCK)
            result['previous_guarded_phase'] = base['phase']
            result['phase'] = handoff['phase']
    blocks.extend(handoff['blocked_by'])
    for path, digest in handoff['input_hashes'].items():
        if path in result['input_hashes'] and result['input_hashes'][path] != digest:
            blocks.append(f'conflicting preflight hash: {path}')
        else:
            result['input_hashes'][path] = digest
    result.update(blocked_by=blocks, eligible=not blocks, v2_handoff=handoff,
                  new_hands=0, workers_started=False)
    return result


def handoff_preflight():
    import psutil
    result = {'qualified': False, 'phase': None, 'blocked_by': [], 'input_hashes': {}}
    hashes = result['input_hashes']
    directory = original.FOUR_M / 'guarded_followthrough_v2_pool_qualified'

    def freeze(path):
        path = Path(path).resolve()
        digest = original.sha(path)
        value = original.read_json(path)
        if original.sha(path) != digest:
            raise ValueError(f'handoff document changed while reading: {path}')
        hashes[str(path)] = digest
        return value

    def verify_mapping(mapping):
        for value, expected in mapping.items():
            path = Path(value).resolve()
            if path == original.PRODUCTION.resolve():
                # Verify the retained old runtime; require the new runtime through
                # the original qualification's independent candidate-SHA check.
                retained = BASE / 'production_before_integration.py'
                if expected != OLD_PRODUCTION_SHA or original.sha(retained) != expected:
                    raise ValueError('historical production source not preserved')
                hashes[str(retained.resolve())] = expected
                hashes[str(path)] = original.sha(path)
            else:
                if original.sha(path) != expected:
                    raise ValueError(f'v2 frozen evidence changed: {path}')
                hashes[str(path)] = expected

    try:
        owner, state = freeze(directory / 'ownership.json'), freeze(directory / 'status.json')
        if owner['pid'] != state['pid']:
            raise ValueError('v2 status belongs to another owner')
        result['phase'] = state.get('phase')
        try:
            proc = psutil.Process(int(owner['pid']))
            if abs(proc.create_time() - float(owner['create_time'])) < .001 and proc.is_running():
                result['blocked_by'].append(f'v2 evaluation owner still live: {proc.pid}')
        except psutil.NoSuchProcess:
            pass
        if state.get('active_child_pid'):
            result['blocked_by'].append(f'v2 child not terminal in state: {state["active_child_pid"]}')
        if state.get('phase') != 'EVIDENCE_READY_FOR_RESEARCH_ANALYSIS':
            result['blocked_by'].append(f'v2 phase not terminal-ready: {state.get("phase")}')
        if result['blocked_by']:
            return result  # Do not inspect partial evaluation outcomes.
        record = freeze(original.FOUR_M / 'experiment.json')
        aggregate = freeze(original.FOUR_M / 'aggregate.json')
        report = freeze(original.FOUR_M / 'deviation_aware_report.json')
        result['checks'] = verify_terminal_documents(state, record, aggregate, report)
        verify_mapping(owner['frozen_sources'])
        verify_mapping(aggregate['input_sha256'])
        verify_mapping(report['input_sha256'])
        for path, expected in ((BASE / 'run_gpu_resume_qualification.py', ORIGINAL_RUNNER_SHA),
                               (BASE / 'gpu_qualification_protocol.md', ORIGINAL_PROTOCOL_SHA)):
            if original.sha(path) != expected:
                raise ValueError('the preregistered GPU runner or protocol changed')
            hashes[str(path.resolve())] = expected
        for path in (Path(__file__), BASE / 'gpu_v2_handoff_protocol.md'):
            hashes[str(path.resolve())] = original.sha(path)
        result['qualified'] = True
    except (OSError, KeyError, TypeError, ValueError) as error:
        result['blocked_by'].append(f'v2 handoff not qualified: {type(error).__name__}: {error}')
    return result


def preflight():
    return combine_preflights(original_preflight(), handoff_preflight())


def main():
    if sys.argv[1:] == ['--preflight-only']:
        result = preflight()
        if (BASE / 'gpu_current_recipe_v1').exists():
            result['blocked_by'].append('existing default output must not be rerun')
            result['eligible'] = False
        print(json.dumps({'eligible': result['eligible'], 'blocked_by': result['blocked_by'],
                          'phase': result['phase'], 'v2_phase': result['v2_handoff']['phase'],
                          'input_hash_count': len(result['input_hashes']), 'new_hands': 0,
                          'workers_started': False}, indent=2))
        return
    # Only the preflight gains a stronger, explicit successor-handoff proof.
    # Command construction, parent, ABBA order, targets, verification and scoring
    # execute directly from the unchanged, hash-bound original runner.
    original.preflight = preflight
    original.main()


if __name__ == '__main__':
    main()
