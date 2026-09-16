"""Terminal-only raw evidence reconciliation; no training or network requests."""
import hashlib
import json
from pathlib import Path
import time
import psutil
import torch
import run_smoke as s

BASE = Path(__file__).resolve().parent


def terminal(identity):
    try:
        return abs(psutil.Process(int(identity['pid'])).create_time()-identity['create_time']) > .001
    except psutil.NoSuchProcess:
        return True


def rows(path):
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main():
    torch.set_num_threads(1)
    s.require(terminal(s.read(BASE/'smoke_ownership.json')), 'controller live')
    contract = s.read(BASE/'smoke_input_contract.json')
    s.ctl.execution.check_hashes(contract['input_sha256'])
    results, namespaces = [], set()
    for seed in (1,3):
        run = BASE/f'seed{seed}_smoke'
        end = s.read(run/'termination.json')
        s.require(terminal(s.read(run/'process.json')) and end['exit_code'] == 0
            and not end['observer_errors'] and not end['remaining_observed_child_pids'], 'job not cleanly terminal')
        s.require(all(terminal({'pid':pid, 'create_time':created})
            for pid,created in end['observed_children'].items()), 'worker live')
        parent_path = Path(s.read(run/'parent_contract.json')['path'])
        parent = torch.load(parent_path, map_location='cpu', weights_only=False)
        initial = torch.load(run/'initial_resumed_state.pt', map_location='cpu', weights_only=False)
        final = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        gate, verification = s.read(run/'initial_resume_gate.json'), s.read(run/'verification.json')
        for key in gate['exact_keys']:
            s.require(s.ctl.HELPER.equal(parent[key], initial[key]), 'initial changed: '+key)
        s.require(s.sha(parent_path) == gate['parent_sha256'] == s.EXPECTED[seed], 'parent changed')
        s.require(s.sha(run/'latest.pt') == verification['checkpoint_sha256'], 'endpoint changed')
        receipt = final['fixed_deal_attempt']
        namespace = receipt['receipt']['namespace']
        s.require(namespace == gate['namespace'] and namespace not in namespaces
            and namespace != parent['fixed_deal_attempt']['receipt']['namespace'], 'namespace reused')
        s.require(s.ctl.HELPER.helpers.load_attempt(Path(receipt['path']), receipt['sha256']) == receipt['receipt'], 'attempt receipt changed')
        s.require(receipt['receipt']['parent_checkpoint_sha256'] == s.EXPECTED[seed], 'attempt wrong parent')
        namespaces.add(namespace)
        metric_rows = rows(run/'h1_training_metrics.jsonl')
        metrics = [r for r in metric_rows if r['iteration'] > parent['iteration']]
        s.require([r['iteration'] for r in metrics] == list(range(parent['iteration']+1, final['iteration']+1)), 'metric iteration gaps')
        assignments = rows(run/'opponent_assignments.jsonl')
        previous = None
        for row in assignments:
            payload = {k:v for k,v in row.items() if k != 'record_sha256'}
            canonical = json.dumps(payload, sort_keys=True, separators=(',',':'), ensure_ascii=False)
            s.require(hashlib.sha256(canonical.encode()).hexdigest() == row['record_sha256'], 'assignment hash')
            s.require(row['previous_record_sha256'] == previous, 'assignment chain')
            previous = row['record_sha256']
        current = [r for r in assignments if r['applies_to_iteration'] > parent['iteration']]
        s.require([r['applies_to_iteration'] for r in current] == [r['iteration'] for r in metrics], 'assignment iteration gaps')
        parent_ids = {r['id'] for r in parent['pool_snapshots']}
        sampled_new = {w['opponent']['snapshot_id'] for row in current for w in row['workers']
            if w['opponent']['kind'] == 'pool_snapshot' and w['opponent']['snapshot_id'] not in parent_ids}
        s.require(len(sampled_new) >= 2, 'new snapshots not actually assigned')
        for name,prefix in s.read(run/'prefixes.json').items():
            with (run/name).open('rb') as handle:
                s.require(hashlib.sha256(handle.read(prefix['bytes'])).hexdigest() == prefix['sha256']
                    == s.sha(parent_path.parent/name), 'inherited raw prefix changed')
        accounting = final['environment_hand_accounting']
        physical = accounting['completed_hands']-parent['environment_hand_accounting']['completed_hands']
        transition = final['total_hands']-parent['total_hands']
        no_decision = accounting['no_trainable_decision_hands']-parent['environment_hand_accounting']['no_trainable_decision_hands']
        replay = final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows']
        s.require(physical == verification['new_physical_hands'] == accounting['session_completed_hands'], 'physical mismatch')
        s.require(sum(r['completed_hands'] for r in accounting['session_worker_counts']) == physical, 'worker sum')
        s.require(metrics[-1]['environment_hand_accounting']['completed_hands'] == accounting['completed_hands'], 'metrics final physical mismatch')
        s.require(sum(r['ppo_replay_rows'] for r in metrics) == replay, 'replay mismatch')
        s.require(physical-transition-no_decision >= 0, 'negative worker tail')
        results.append({'seed':seed, 'physical_hands':physical, 'transition_hands':transition,
            'no_decision_hands':no_decision, 'residual_worker_tail_hands':physical-transition-no_decision,
            'replay_rows':replay, 'iterations':len(metrics), 'sampled_new_snapshot_ids':sorted(sampled_new),
            'namespace':namespace, 'wall_seconds':end['wall_seconds'], 'terminated_descendants':len(end['observed_children'])})
        del parent,initial,final
    hashes = {str(p):s.sha(p) for p in BASE.rglob('*') if p.is_file()
        and p.name not in {'experiment.json','source_manifest.json','code.patch'} and '__pycache__' not in p.parts}
    s.write_new(BASE/'terminal_review.json', {'passed':True, 'runs':results,
        'input_sha256':hashes, 'new_training_hands':sum(r['physical_hands'] for r in results),
        'execution_wall_seconds':sum(r['wall_seconds'] for r in results),
        'evaluation_hands':0, 'final_qualification_hands':0,
        'limitations':['Statistical continuation, not bitwise worker RNG restoration.',
            'Unique managed namespaces and receipts checked; no full per-hand deck corpus was logged in this smoke.',
            'Mechanism qualification only; no evidence of improved poker strength.',
            'Live logger accounting used completed jobs, so current-job hands lagged until termination; final counts reconciled.']})


if __name__ == '__main__':
    main()
