"""Read-only identities/liveness/counts check; never inspect interim returns."""
import json
import sys

import psutil
import run_assessment as run


def main():
    if sys.argv[1:] or (run.BASE/'startup_review.json').exists():
        raise ValueError('No repeated startup review')
    execution = run.read(run.BASE/'execution.json')
    assert execution['status'] == 'INTERNAL_EVALUATION'
    process = psutil.Process(execution['pid'])
    assert abs(process.create_time()-execution['create_time']) < .001
    copies = run.read(run.BASE/'execution_code/copy_manifest.json')
    inputs = run.read(run.BASE/'input_manifest.json')
    parent = run.validate_parent()
    run.verify(copies, inputs)
    assert parent['model_sha256'] == inputs['models']['student']['sha256'] == run.STUDENT_SHA
    commands = run.read(run.BASE/'evaluation_commands.json')
    expected = [(c,a,[sys.executable,*run.eval_command(c,a)]) for c in run.CANDIDATES for a in run.OPPONENTS]
    assert [(r['label'],r['anchor'],r['command']) for r in commands] == expected
    assert len(commands) == 21
    assert [(r['label'],r['anchor'],r['command']) for r in execution['children']] == expected[:len(execution['children'])]
    assert all(c['exit_code'] in (None,0) for c in execution['children'])
    parity = run.read(run.BASE/'parity_analysis.json')
    assert parity['status'] == 'PASS' and parity['model_sha256'] == run.STUDENT_SHA
    assert parity['states_checked'] == 4202 and parity['model_queries'] == 8404
    assert parity['new_unique_hands'] == parity['network_connection_attempts'] == 0
    assert parity['parity_sha256'] == run.sha(run.BASE/'parity.jsonl')
    assert sum(parity['strata'].values()) == 4202 and len(parity['strata']) == 8
    for path,digest in parity['runtime_sha256'].items():
        assert run.sha(path) == digest
    counts = {p.parent.name: p.read_bytes().count(b'\n')*2 for p in (run.BASE/'evaluation').glob('*/pairs.jsonl')}
    assert counts and sum(counts.values()) >= execution['evaluation_hands']
    report = dict(status='PASS', pid=execution['pid'], create_time=execution['create_time'],
        own_source_copy_pairs=len(copies), parent_source_copy_pairs=len(run.read(run.PARENT/'execution_code/copy_manifest.json')),
        frozen_models=len(inputs['models']), exact_fixed_commands=len(commands),
        children_launched=len(execution['children']), preserved_raw_hand_counts=counts,
        execution_observed_hands=execution['evaluation_hands'], new_training_hands=0,
        new_unique_hands=0, additional_model_queries=0, interim_returns_inspected=False,
        candidate_sha256=run.STUDENT_SHA, parity_states=4202, parity_model_queries=8404,
        interpretation='Read-only startup identity/count check; concurrently growing raw evidence is not a strength result.')
    run.write(run.BASE/'startup_review.json', report)
    run.log('--command', f'python research/experiments/{run.BASE.name}/check_startup.py',
        '--artifact', run.BASE/'check_startup.py', '--artifact', run.BASE/'startup_review.json',
        '--note', 'Read-only startup check PASS.21commands frozen, eightmodel hashes and parent/source snapshots intact; no interim returns inspected.')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
