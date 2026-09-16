"""Read only immutable first archive while the original PPO process continues.

Added after launch; not imported by the frozen trainer/wrapper. This diagnostic
writes only its own report and is separately registered and hashed.
"""
from datetime import datetime, timezone
import json
import sys

import psutil
import torch
import run_pilot as run


def main():
    torch.set_num_threads(1)
    if sys.argv[1:] or (run.BASE/'startup_analysis.json').exists():
        raise ValueError('No repeated startup diagnostic')
    execution = run.read(run.BASE/'execution.json')
    assert execution['status'] == 'TRAINING' and len(execution['children']) == 1
    trainer = execution['children'][0]
    for row in (execution, trainer):
        assert abs(psutil.Process(row['pid']).create_time()-row['create_time']) < .001
    assert trainer['role'] == 'trainer' and trainer['command'] == [sys.executable, *run.training_command()]
    copies, inputs = run.read(run.BASE/'execution_code/copy_manifest.json'), run.read(run.BASE/'input_manifest.json')
    run.verify(copies, inputs)
    archives = sorted((run.BASE/'production/checkpoints').glob('checkpoint_iter000004_hands*.pt'))
    assert len(archives) == 1
    path = archives[0]
    checkpoint = torch.load(path, map_location='cpu', weights_only=False)
    source = torch.load(run.BASE/'frozen/average.pt', map_location='cpu', weights_only=False)
    assert checkpoint['iteration'] == 4 and checkpoint['run_id'] == 'v6_fictitious_response_phase2_20260831'
    account, config = checkpoint['environment_hand_accounting'], checkpoint['config']
    assert account['prefix_complete'] and account['completed_hands'] > 0 and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == checkpoint['run_id']
    assert sum(r['completed_hands'] for r in account['session_worker_counts']) == account['completed_hands']
    assert config['reset_hand_counter'] and config['reset_optimizer'] and not config['v6_rebind_legacy_weights']
    assert config['self_play_fraction'] == config['source_policy_kl_coef'] == 0
    assert config['seed'] == run.SEED and config['worker_seed_base'] == 2026101800
    assert config['fixed_opponent_checkpoints'] == [str(run.BASE/'frozen/average.pt')]
    assert config['validate_stream'] and config['total_environment_hands'] == run.TARGET
    assert len(checkpoint['optimizer']['state']) == 86 and len(source['optimizer']['state']) == 80
    assert source['optimizer_steps'] == 1024 and all(float(r['step']) == 1024 for r in source['optimizer']['state'].values())
    assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    changed = sum(not torch.equal(v, source['model'][k]) for k,v in checkpoint['model'].items())
    assert changed == 86
    pool = checkpoint['pool_snapshots']
    assert len(pool) == 1 and len(pool[0]['state_dict']) == 86
    assert all(torch.equal(v, source['model'][k]) for k,v in pool[0]['state_dict'].items())
    assert pool[0]['score_components']['checkpoint_sha256'] == run.MODEL_SHA
    steps = []
    for state in checkpoint['optimizer']['state'].values():
        assert all(torch.isfinite(v).all() for v in state.values() if torch.is_tensor(v))
        steps.append(float(state['step']))
    assert min(steps) > 0 and max(steps) < source['optimizer_steps']
    assert run.sha(run.PARENT/'frozen/student.pt') == run.MODEL_SHA
    report = dict(status='PASS', checked_at=datetime.now(timezone.utc).isoformat(),
        archived_iteration=4, archived_actual_hands=account['completed_hands'],
        archive_path=str(path), archive_sha256=run.sha(path), frozen_source_sha256=run.MODEL_SHA,
        changed_finite_model_tensors=changed, new_ppo_optimizer_states=86, preserved_source_sl_optimizer_states=80, preserved_source_sl_optimizer_steps=1024,
        ppo_adam_step_range=[min(steps), max(steps)], opponent_tensors_exactly_equal_source=86,
        original_wrapper_pid=execution['pid'], original_trainer_pid=trainer['pid'],
        original_processes_alive=True, verified_source_copy_pairs=len(copies),
        new_diagnostic_environment_hands=0, no_external_requests=True)
    run.write(run.BASE/'startup_analysis.json', report)
    run.log('--command', f'python research/experiments/{run.BASE.name}/check_startup.py',
        '--artifact', run.BASE/'check_startup.py', '--artifact', run.BASE/'startup_analysis.json',
        '--artifact', path, '--note', 'Read-only first-archive startup audit PASS: original PIDs, all86learner tensors changed, fresh86-state Adam distinct from preserved80-state SL optimizer, all86fixed-opponent tensors exactly unchanged, source/copy hashes intact. Diagnostic added after capture; no active captured source modified.')
    print(json.dumps(report))


if __name__ == '__main__': main()
