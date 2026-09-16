"""Read-only failed-save boundary audit; no resume, trimming, or model inference."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
import run_control as ctl
import control_evidence as ev


def main():
    import torch
    torch.set_num_threads(1)
    out = HERE / 'interruption_audit.json'
    ev.require(not out.exists(), 'preserve earlier audit')
    run = BASE / 'static_stage1'
    for path in (BASE / 'ownership.json', run / 'process.json'):
        ev.require(not ctl.owner_live(ev.read_json(path)), 'original owner still live')
    terminal = ev.read_json(run / 'termination.json')
    ev.require(terminal['exit_code'] == 1 and not terminal['observer_errors'] and
               not terminal['remaining_observed_child_pids'], 'unexpected terminal receipt')
    for pid, created in terminal['observed_children'].items():
        ev.require(not ctl.owner_live({'pid': int(pid), 'create_time': created}), 'surviving descendant')
    contract = ev.read_json(BASE / 'input_contract.json')
    ctl.check_hashes(contract['input_sha256'])
    files = [p for p in run.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [BASE / n for n in ('status.json', 'controller_error.json', 'ownership.json',
                                 'controller.stderr.log', 'controller.stdout.log', 'input_contract.json')]
    frozen = {str(p): ev.sha(p) for p in files}
    saved = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
    parent = torch.load(ctl.PARENT, map_location='cpu', weights_only=False)
    initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
    helper = ctl.qualified_command_helper()
    metrics = ctl.complete_jsonl(run / 'h1_training_metrics.jsonl')
    assignments = ctl.complete_jsonl(run / 'opponent_assignments.jsonl')
    for name, rows in (('h1_training_metrics.jsonl', metrics), ('opponent_assignments.jsonl', assignments)):
        data = (run / name).read_bytes()
        ev.require(data.endswith(b'\n') and len(rows) == sum(bool(x.strip()) for x in data.splitlines()), 'partial raw JSONL')
    iteration, physical = saved['iteration'], saved['environment_hand_accounting']['completed_hands']
    ev.require(iteration == 1117 and physical == 5314037 and saved['total_hands'] == 4602125, 'unexpected saved boundary')
    ev.require([r['iteration'] for r in metrics] == list(range(1, 1119)), 'unexpected completed metric chain')
    ev.require([r['applies_to_iteration'] for r in assignments] == list(range(1, 1119)), 'unexpected assignment chain')
    retained_metrics = [r for r in metrics if r['iteration'] <= iteration]
    ev.require(retained_metrics[-1]['hands'] == saved['total_hands'] and
               retained_metrics[-1]['environment_hand_accounting'] == saved['environment_hand_accounting'], 'saved metric mismatch')
    manifest = ev.read_json(run / 'run_manifest.json')
    retained_keys = ('model', 'optimizer', 'ppo_replay_entries', 'ppo_replay_rng_state',
                     'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_candidate_history')
    ev.require(all(helper.equal(parent[k], initial[k]) for k in retained_keys), 'initial state changed')
    ev.require(min(helper.steps(saved)) > max(helper.steps(parent)), 'optimizer did not advance')
    ev.require(all(torch.isfinite(v).all().item() for v in saved['model'].values()), 'nonfinite saved model')
    ev.require(len(saved['ppo_replay_entries']) == 2 and saved['main_process_rng_state'], 'missing resume state')
    trainer = ev.module_at('failed_save_assignment_replay', ctl.PRODUCTION)
    replay = trainer.restore_group_assignment_rng_from_evidence(assignments, retained_metrics, rng=random.Random(0),
        seed=ctl.TRAINING_SEED, worker_count=12, pool_size=len(saved['pool_snapshots']), group_count=8,
        self_play_fraction=.25, checkpoint_iteration=iteration, checkpoint_total_hands=saved['total_hands'],
        pool_snapshot_ids=[r['id'] for r in saved['pool_active_metadata']], replay_origin=saved.get('assignment_replay_origin'))
    ev.require(replay['pending_assignments'] is not None, 'pending assignment lost')
    ev.require(metrics[-1]['environment_hand_accounting']['completed_hands'] == 5318329, 'unexpected observed suffix')
    ev.require(not list(run.glob('*.pending')), 'a recoverable candidate exists; review it before selecting earlier state')
    inputs = {**contract['input_sha256'], **frozen}
    ctl.check_hashes(inputs)
    result = {'schema': 'cardpilot.seed3.failed_save_boundary.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
        'cause': 'os.replace of a fully serialized pending checkpoint failed with Windows error5; original finally removed pending file',
        'file_lock_owner_or_other_access_denial_cause': None, 'original_exit_code': 1,
        'original_processes_and_observed_descendants_terminal': True,
        'checkpoint_sha256': ev.sha(run / 'latest.pt'), 'iteration': iteration,
        'retained_physical_hands': physical, 'retained_transition_hands': saved['total_hands'],
        'new_retained_physical_hands': physical - ctl.INITIAL_PHYSICAL,
        'new_retained_transition_hands': saved['total_hands'] - parent['total_hands'],
        'new_retained_replay_rows': saved['ppo_replay_cumulative_rows'] - parent['ppo_replay_cumulative_rows'],
        'observed_completed_but_uncheckpointed_physical_hands': 5318329 - physical,
        'observed_completed_but_uncheckpointed_transition_hands': metrics[-1]['hands'] - saved['total_hands'],
        'unknown_additional_worker_tail_hands': None, 'remaining_stage1_retained_hands': ctl.TARGETS[1] - physical,
        'manifest_iteration': manifest.get('iteration'), 'manifest_status': manifest.get('status'),
        'namespace': saved['fixed_deal_attempt']['receipt']['namespace'],
        'assignment_replay': replay, 'effective_optimizer_lr': [g['lr'] for g in saved['optimizer']['param_groups']],
        'resume_semantics': 'Restore iteration1117 state exactly; retain full1118-row assignment chain including pending1118. Derive an explicitly documented consumed-metric view through1117 in a new attempt only; original unsaved1118 metric remains immutable. New namespace gives statistical, not bitwise worker continuation.',
        'frozen_interrupted_inputs': frozen, 'input_sha256': inputs,
        'analysis_added_training_hands': 0, 'analysis_added_evaluation_hands': 0}
    ctl.write_new(out, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('input_sha256', 'frozen_interrupted_inputs')}, indent=2))


if __name__ == '__main__':
    main()
