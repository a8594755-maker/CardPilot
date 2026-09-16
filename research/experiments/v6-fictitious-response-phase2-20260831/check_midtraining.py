"""Outcome-blind, read-only training-prefix and immutable iteration128 audit.

Not imported by the active trainer or wrapper; no environment or optimizer steps.
"""
from datetime import datetime, timezone
import json
import sys

import psutil
import torch
import run_pilot as run


def complete_rows(path):
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    return [json.loads(line) for line in lines if line.endswith(b'\n')], sum(len(line) for line in lines if not line.endswith(b'\n'))


def main():
    if sys.argv[1:] or (run.BASE/'midtraining_analysis.json').exists():
        raise ValueError('No repeated prefix audit')
    torch.set_num_threads(1)
    execution = run.read(run.BASE/'execution.json')
    assert execution['status'] == 'TRAINING' and len(execution['children']) == 1
    trainer = execution['children'][0]
    for row in (execution, trainer):
        assert abs(psutil.Process(row['pid']).create_time()-row['create_time']) < .001
    assert trainer['role'] == 'trainer' and trainer['command'] == [sys.executable,*run.training_command()]
    copies, inputs = run.read(run.BASE/'execution_code/copy_manifest.json'), run.read(run.BASE/'input_manifest.json')
    run.verify(copies,inputs)
    metrics, metric_tail = complete_rows(run.BASE/'production/h1_training_metrics.jsonl')
    assert len(metrics) >= 128 and [m['iteration'] for m in metrics] == list(range(1,len(metrics)+1))
    counts = []
    for metric in metrics:
        a = metric['environment_hand_accounting']
        assert a['prefix_complete'] and a['unknown_prefix_training_marker_hands'] == 0
        assert a['origin_run_id'] == 'v6_fictitious_response_phase2_20260831'
        assert sum(w['completed_hands'] for w in a['session_worker_counts']) == a['completed_hands']
        counts.append(a['completed_hands'])
    assert all(x < y for x,y in zip([0]+counts[:-1],counts))
    assignments, assignment_tail = complete_rows(run.BASE/'production/opponent_assignments.jsonl')
    exposure = run.stats.exposure(assignments,len(assignments))
    paths = list((run.BASE/'production/checkpoints').glob('checkpoint_iter000128_hands*.pt'))
    assert len(paths) == 1
    path = paths[0]
    archive = torch.load(path,map_location='cpu',weights_only=False)
    source = torch.load(run.BASE/'frozen/average.pt',map_location='cpu',weights_only=False)
    assert archive['iteration'] == 128 and archive['run_id'] == 'v6_fictitious_response_phase2_20260831'
    actual = archive['environment_hand_accounting']['completed_hands']
    assert counts[127] <= actual < counts[128] if len(counts) > 128 else counts[127] <= actual
    assert len(archive['model']) == len(archive['optimizer']['state']) == 86
    assert all(torch.isfinite(v).all() and not torch.equal(v,source['model'][k]) for k,v in archive['model'].items())
    assert len(source['optimizer']['state']) == 80 and source['optimizer_steps'] == 1024
    assert all(float(s['step']) == 1024 for s in source['optimizer']['state'].values())
    steps = []
    for state in archive['optimizer']['state'].values():
        assert all(torch.isfinite(v).all() for v in state.values() if torch.is_tensor(v))
        steps.append(float(state['step']))
    assert min(steps) > 0 and min(steps) == max(steps)
    pool = archive['pool_snapshots']
    assert len(pool) == 1 and len(pool[0]['state_dict']) == 86
    assert pool[0]['score_components']['checkpoint_sha256'] == run.MODEL_SHA
    assert all(torch.equal(v,source['model'][k]) for k,v in pool[0]['state_dict'].items())
    run.verify(copies,inputs)
    report = dict(status='PASS',checked_at=datetime.now(timezone.utc).isoformat(),
        original_wrapper_pid=execution['pid'],original_trainer_pid=trainer['pid'],original_processes_alive=True,
        complete_metric_iterations=len(metrics),last_prefix_actual_hands=counts[-1],counter_prefix_monotonic=True,
        complete_assignment_rows=len(assignments),ignored_incomplete_tail_bytes=dict(metrics=metric_tail,assignments=assignment_tail),
        archived_iteration=128,archived_actual_hands=actual,archive_path=str(path),archive_sha256=run.sha(path),
        changed_finite_tensors=86,ppo_adam_step_range=[min(steps),max(steps)],fixed_opponent_tensors_exact=86,
        preserved_source_sl_states=80,preserved_source_sl_steps=1024,source_copy_pairs=len(copies),frozen_inputs=len(inputs),
        exposure=exposure,new_diagnostic_environment_hands=0,additional_model_queries=0,
        interpretation='Read-only prefix audit, not a learning-curve outcome or terminal training completion.')
    run.write(run.BASE/'midtraining_analysis.json',report)
    run.log('--command',f'python research/experiments/{run.BASE.name}/check_midtraining.py',
        '--artifact',run.BASE/'check_midtraining.py','--artifact',run.BASE/'midtraining_analysis.json','--artifact',path,
        '--note','Read-only immutable iteration128 and complete-prefix audit PASS; counters and fixed opponent preserved. No learning-curve return selection, model queries or new hands.')
    print(json.dumps(report))


if __name__ == '__main__': main()
