"""Independent terminal evidence and family-assignment reconstruction."""
from pathlib import Path
import hashlib
import importlib.util
import json
import random
import sys
import time
import psutil
import torch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import run_family_smoke as run
run.configure()
s = run.s

def live(pid, ct):
    try:
        return abs(psutil.Process(int(pid)).create_time() - ct) < .001
    except psutil.NoSuchProcess:
        return False

def mass(weights, ids, old, added):
    s.require(len(weights) == len(ids) == 9, 'capacity')
    for family, target in ((old, .5), (added, .25), (set(ids) - old - added, .25)):
        s.require(abs(sum(w for w, i in zip(weights, ids) if i in family) - target) < 1e-8, 'family mass')

def main():
    torch.set_num_threads(1)
    start = time.perf_counter()
    owner = s.read(BASE / 'smoke_ownership_v3.json')
    s.require(not live(owner['pid'], owner['create_time']), 'controller live')
    result = s.read(BASE / 'smoke_result_v3.json')
    s.require(result['passed'], 'incomplete')
    hashes = dict(s.read(BASE / 'smoke_input_contract_v3.json')['input_sha256'])
    s.ctl.execution.check_hashes(hashes)
    wrapper = BASE.parent / 'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
    spec = importlib.util.spec_from_file_location('review_trainer', wrapper)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    trainer, _ = m.install()
    counts = [0, 0, 0]
    namespaces = set()
    reports = {}
    for seed in (1, 3):
        folder = BASE / f'seed{seed}_smoke_v3'
        term, proc = s.read(folder / 'termination.json'), s.read(folder / 'process.json')
        s.require(term['exit_code'] == 0 and not term['observer_errors'] and not term['remaining_observed_child_pids'], 'unclean termination')
        s.require(not live(proc['pid'], proc['create_time']) and all(not live(p,c) for p,c in term['observed_children'].items()), 'live workers')
        s.require(len(term['observed_children']) >= 12, 'worker identities missing')
        binding = s.read(folder / 'parent_contract.json')
        p = torch.load(binding['path'], map_location='cpu', weights_only=False)
        initial = torch.load(folder / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
        final = torch.load(folder / 'latest.pt', map_location='cpu', weights_only=False)
        gate = s.read(folder / 'initial_resume_gate.json')
        norm = s.normalized_pool(p, 200)
        s.require(gate['passed'] and all(s.state_equal(norm[k], initial[k]) for k in gate['exact_keys']), 'initial state')
        s.require(s.sha(binding['path']) == binding['sha256'] and s.sha(folder / 'initial_resumed_state.pt') == gate['initial_sha256'], 'initial hashes')
        for name, prefix in s.read(folder / 'prefixes.json').items():
            with (folder / name).open('rb') as f:
                s.require(hashlib.sha256(f.read(prefix['bytes'])).hexdigest() == prefix['sha256'], 'prefix changed')
        rows = s.ctl.execution.complete_jsonl(folder / 'opponent_assignments.jsonl')
        metrics = s.ctl.execution.complete_jsonl(folder / 'h1_training_metrics.jsonl')
        new = [r for r in rows if p['iteration'] < r['applies_to_iteration'] <= final['iteration']]
        s.require(len(new) == final['iteration'] - p['iteration'], 'missing completed assignments')
        args = s.read(folder / 'command.json')
        option = lambda k: args[args.index(k) + 1]
        rng = random.Random()
        restored = trainer.restore_group_assignment_rng_from_evidence(
            [r for r in rows if r['applies_to_iteration'] <= p['iteration']],
            [r for r in metrics if r['iteration'] <= p['iteration']],
            rng=rng, seed=int(option('--seed')), worker_count=int(option('--workers')),
            group_count=int(option('--opponent-groups')), self_play_fraction=float(option('--self-play-fraction')),
            checkpoint_iteration=p['iteration'], checkpoint_total_hands=p['total_hands'],
            replay_origin=p['assignment_replay_origin'], pool_size=9, pool_snapshot_ids=[x['id'] for x in p['pool_snapshots']])
        s.require(restored['pending_assignments'] is None, 'pending prior work')
        first, _ = trainer.build_group_opponent_assignments(worker_count=int(option('--workers')), pool_size=9,
            group_count=int(option('--opponent-groups')), self_play_fraction=float(option('--self-play-fraction')),
            rng=rng, pool_weights=p['adaptive_opponent_weights'])
        s.require(first.tolist() == [w['opponent']['local_index'] for w in new[0]['workers']], 'first allocation replay mismatch')
        fc = s.read(folder / 'family_contract.json')
        old, added = set(fc['original_ids']), set(fc['added_ids'])
        runtime = s.read(folder / 'family_runtime.json')
        s.require(runtime['contract_sha256'] == s.sha(folder / 'family_contract.json') and runtime['parent_sha256'] == binding['sha256'], 'runtime binding')
        for r in new:
            mass(r['pool_sampling_weights'], [x['snapshot_id'] for x in r['pool_snapshot_refs']], old, added)
        mass(final['adaptive_opponent_weights'], [x['id'] for x in final['pool_snapshots']], old, added)
        verify = s.read(folder / 'verification.json')
        s.require(s.sha(folder / 'latest.pt') == verify['checkpoint_sha256'], 'final hash')
        s.require(s.ctl.prior.optimizer_step_audit(p, final, True) == verify['optimizer'], 'Adam')
        ns = final['fixed_deal_attempt']['receipt']['namespace']
        s.require(ns not in namespaces and ns != p['fixed_deal_attempt']['receipt']['namespace'], 'namespace reuse')
        namespaces.add(ns)
        delta = [final['environment_hand_accounting']['completed_hands'] - p['environment_hand_accounting']['completed_hands'], final['total_hands'] - p['total_hands'], final['ppo_replay_cumulative_rows'] - p['ppo_replay_cumulative_rows']]
        s.require(delta == [verify[k] for k in ('new_physical_hands', 'new_transition_hands', 'new_replay_rows')], 'accounting')
        counts = [a + b for a, b in zip(counts, delta)]
        reports[str(seed)] = {'passed': True, 'first_assignment_replayed': first.tolist(), 'completed_assignments_checked': len(new), 'namespace': ns}
        for file in folder.iterdir():
            if file.is_file(): hashes[str(file)] = s.sha(file)
    s.require(counts[0] == result['new_physical_hands'], 'total accounting')
    hashes[str(Path(__file__))] = s.sha(Path(__file__))
    s.ctl.execution.check_hashes(hashes)
    s.write_new(BASE / 'terminal_family_review.json', {'passed': True, 'input_sha256': hashes, 'seeds': reports,
        'training_hands': counts[0], 'transition_hands': counts[1], 'replay_rows': counts[2], 'evaluation_hands': 0,
        'review_wall_seconds': time.perf_counter() - start,
        'scope': 'Real statistical continuation and family allocation mechanism; not strength or unique training-deck coverage.'})
    print(json.dumps({'passed': True, 'counts': counts, 'seeds': reports}))

if __name__ == '__main__':
    main()
