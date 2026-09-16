"""Inspect retained state after missing process identities; never launch training."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import sys

import psutil

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
QUAL = ROOT / 'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(QUAL / 'candidate'))
sys.path.insert(0, str(BASE))
import run_actor_control as ctl

require, read, sha = ctl.require, ctl.read, ctl.sha
RUN = BASE / 'seed1_connected_stage1'


def require_dead():
    identities = [BASE / 'ownership.json', RUN / 'process.json',
                  BASE / 'seed1_detached_stage1/process.json']
    for path in identities:
        require(not ctl.execution.owner_live(read(path)), f'original process live: {path}')
    terminal = read(BASE / 'seed1_detached_stage1/termination.json')
    for pid, created in terminal['observed_children'].items():
        require(not ctl.execution.owner_live({'pid': int(pid), 'create_time': created}),
                'completed-cell descendant still live')
    # A missing controller has no reliable complete descendant receipt for the
    # interrupted job. Inspect all extant Python identities, not just stale PIDs.
    other_python = [p.info for p in psutil.process_iter(['pid', 'ppid', 'name', 'create_time'])
                    if p.pid != os.getpid() and (p.info['name'] or '').lower().startswith('python')]
    require(not other_python, f'Python process requires explicit ownership review: {other_python}')


def main():
    import torch
    torch.set_num_threads(1)
    out = HERE / 'interruption_audit.json'
    require(not out.exists(), 'preserve earlier audit')
    require_dead()
    require(read(BASE / 'experiment.json')['status'] == 'RUNNING', 'wrong record status')
    require(not (BASE / 'controller_error.json').exists() and not (RUN / 'termination.json').exists(),
            'new terminal evidence needs review')
    contract = read(BASE / 'input_contract.json')
    ctl.execution.check_hashes(contract['input_sha256'])
    files = [p for p in RUN.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [BASE / n for n in ('status.json', 'ownership.json', 'input_contract.json',
                                'controller_stdout.log', 'controller_stderr.log')]
    files += [p for p in (BASE / 'attempt_registry').glob('*.json')]
    files += [HERE / 'interruption_amendment.md', Path(__file__)]
    files += [BASE / 'seed1_detached_stage1' / n for n in
              ('verification.json', 'termination.json', 'process.json', 'latest.pt')]
    frozen = {str(p): sha(p) for p in files}
    require(not [p for p in RUN.rglob('*') if p.is_file() and 'pending' in p.name.lower()],
            'pending checkpoint candidate needs separate review')
    source = ctl.parent_path(1, 'connected', 1)
    require(sha(source) == ctl.CONNECTED_SHA[1], 'original parent changed')
    parent = torch.load(source, map_location='cpu', weights_only=False)
    initial = torch.load(RUN / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    saved = torch.load(RUN / 'latest.pt', map_location='cpu', weights_only=False)
    ctl.prior.initial_audit(parent, initial, True)
    ctl.route_audit(initial, True, parent)
    ctl.route_audit(saved, True, parent)
    iteration = saved['iteration']
    physical = saved['environment_hand_accounting']['completed_hands']
    require((iteration, physical, saved['total_hands']) == (2217, 10507221, 9140101),
            'saved boundary differs from last observed logs; review it without reset')
    raw = {}
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
        data = (RUN / name).read_bytes()
        require(data.endswith(b'\n'), f'partial JSONL suffix: {name}')
        raw[name] = [json.loads(line) for line in data.splitlines() if line.strip()]
    metrics = raw['h1_training_metrics.jsonl']
    assignments = raw['opponent_assignments.jsonl']
    require([r['iteration'] for r in metrics] == list(range(1, len(metrics) + 1)), 'metric gaps/duplicates')
    require([r['applies_to_iteration'] for r in assignments] == list(range(1, len(assignments) + 1)),
            'assignment gaps/duplicates')
    consumed = [r for r in metrics if r['iteration'] <= iteration]
    require(consumed[-1]['hands'] == saved['total_hands'] and
            consumed[-1]['environment_hand_accounting'] == saved['environment_hand_accounting'],
            'checkpoint and consumed metric differ')
    prefixes = read(RUN / 'prefixes.json')
    import hashlib
    for name, info in prefixes.items():
        require(hashlib.sha256((RUN / name).read_bytes()[:info['bytes']]).hexdigest() ==
                info['sha256'] == sha(info['path']), 'original raw prefix changed')
    optimizer = ctl.prior.optimizer_step_audit(parent, saved, True)
    require(all(torch.isfinite(v).all().item() for v in saved['model'].values()), 'nonfinite saved model')
    require(len(saved['ppo_replay_entries']) == 2 and saved['main_process_rng_state'], 'missing resume state')
    require(saved['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'], 'replay did not advance')
    new_rows = [r for r in consumed if r['iteration'] > parent['iteration']]
    require(ctl.HELPER.finite_update_evidence(new_rows, (RUN / 'latest_train.log').read_text(encoding='utf-8')),
            'retained update evidence invalid')
    attempt = saved['fixed_deal_attempt']
    receipt = ctl.HELPER.helpers.load_attempt(Path(attempt['path']), attempt['sha256'])
    require(receipt == attempt['receipt'] and receipt['parent_checkpoint_sha256'] == sha(source),
            'attempt provenance mismatch')
    require(receipt['namespace'] == saved['config']['fixed_training_deal_namespace'], 'namespace mismatch')
    trainer = ctl.evidence.module_at('actor_recovery_assignment', ctl.HELPER.PRODUCTION)
    replay = trainer.restore_group_assignment_rng_from_evidence(assignments, consumed, rng=random.Random(0),
        seed=20263001, worker_count=12, pool_size=len(saved['pool_snapshots']), group_count=8,
        self_play_fraction=.25, checkpoint_iteration=iteration, checkpoint_total_hands=saved['total_hands'],
        pool_snapshot_ids=[r['id'] for r in saved['pool_active_metadata']],
        replay_origin=saved.get('assignment_replay_origin'))
    pool = ctl.evidence.module_at('actor_recovery_pool', ctl.execution.POOL_HELPER)
    windows = [pool.load_window(source, sha(source)), pool.load_window(RUN / 'latest.pt', sha(RUN / 'latest.pt'))]
    pool_audit = ctl.prior.pool_audit(windows, consumed,
        [r for r in assignments if r['applies_to_iteration'] <= iteration])
    reference = ctl.evidence.verify_reference_windows('static', parent, initial, [saved], consumed, ctl.HELPER.equal)
    manifest = read(RUN / 'run_manifest.json')
    require_dead()
    ctl.execution.check_hashes(frozen)
    result = {'schema': 'cardpilot.actor_route.missing_process_audit.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.orig_argv[1:]],
        'cause': None, 'exit_code': None, 'missing_normal_termination_evidence': True,
        'original_process_identities_absent': True, 'other_python_processes_at_audit': [],
        'original_controller_last_status_at': read(BASE / 'status.json')['updated_at'],
        'checkpoint_sha256': sha(RUN / 'latest.pt'), 'iteration': iteration,
        'retained_physical_hands': physical, 'retained_transition_hands': saved['total_hands'],
        'new_retained_physical_hands': physical - parent['environment_hand_accounting']['completed_hands'],
        'new_retained_transition_hands': saved['total_hands'] - parent['total_hands'],
        'new_retained_replay_rows': saved['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
        'observed_completed_but_uncheckpointed_physical_hands': metrics[-1]['environment_hand_accounting']['completed_hands'] - physical,
        'observed_completed_but_uncheckpointed_transition_hands': metrics[-1]['hands'] - saved['total_hands'],
        'unknown_additional_worker_tail_hands': None,
        'remaining_stage1_retained_hands': ctl.INITIAL_PHYSICAL[1] + ctl.DOSES[1] - physical,
        'manifest_iteration': manifest.get('iteration'), 'manifest_status': manifest.get('status'),
        'metric_rows': len(metrics), 'assignment_rows': len(assignments), 'namespace': receipt['namespace'],
        'assignment_replay': replay, 'optimizer_audit': optimizer, 'pool_audit': pool_audit,
        'reference_audit': reference, 'effective_optimizer_lr': [g['lr'] for g in saved['optimizer']['param_groups']],
        'resume_semantics': 'Preserve original interrupted directory. A qualified new attempt must restore saved state and assignment evidence exactly with a fresh managed namespace; statistical, not bitwise worker continuation.',
        'frozen_interrupted_inputs': frozen, 'input_sha256': {**contract['input_sha256'], **frozen},
        'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0, 'training_started': False}
    ctl.write_new(out, result)
    print(json.dumps({k: v for k, v in result.items() if k not in
                     ('input_sha256', 'frozen_interrupted_inputs', 'optimizer_audit')}, indent=2))


if __name__ == '__main__':
    main()
