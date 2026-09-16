"""Read-only detailed review of a terminal job; never changes live training."""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import torch

BASE = Path(__file__).resolve().parent
QUAL = BASE.parent/'v6-independent-observable-critic-qualification-20260908'


def read(path): return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def require(condition, message):
    if not condition: raise ValueError(message)


def expected_steps(rows, batch_size):
    require(batch_size > 0, 'batch size')
    return sum(math.ceil(r['policy_rows']/batch_size)*r['ppo_epochs_completed'] for r in rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('job', type=Path)
    args = parser.parse_args()
    folder = args.job.resolve()
    require(folder.parent == BASE, 'job outside experiment')
    require(read(folder/'terminal_process.json')['returncode'] == 0, 'not clean terminal')
    contract = read(folder/'job_contract.json')
    declared = read(folder/'terminal_training.json')
    for name,digest in contract['sources'].items(): require(sha(Path(name)) == digest, 'source hash: '+name)
    parent_path = Path(contract['parent'])
    require(sha(parent_path) == contract['parent_sha256'], 'parent hash')
    require(sha(folder/'latest.pt') == declared['checkpoint_sha256'], 'endpoint hash')
    gate = read(folder/'initial_gate.json')
    require(gate['passed'] and sha(folder/'initial_resume.pt') == gate['sha256'], 'initial hash')
    sys.path.insert(0,str(QUAL))
    from check_parents import module
    helper = module('curve_initial_equality', BASE.parent/
        'v6-preflop-actor-trunk-route-qualification-20260906/route_transfer.py')
    from derive_capture_check_v2 import verify
    parent = torch.load(parent_path,map_location='cpu',weights_only=False)
    initial = torch.load(folder/'initial_resume.pt',map_location='cpu',weights_only=False)
    final = torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
    independent = contract['arm'] == 'independent'
    prior_independent = bool(parent['config'].get('independent_observable_critic',False))
    if independent and not prior_independent:
        verify(parent,initial,helper.equal_tree)
    else:
        for key in ('model','optimizer','total_hands','iteration','ppo_replay_entries','ppo_replay_rng_state',
                    'ppo_replay_cumulative_rows','pool_snapshots','pool_candidate_history','assignment_replay_origin'):
            require(helper.equal_tree(parent[key],initial[key]),'initial '+key)
    for key in ('adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations'):
        require(helper.equal_tree(parent.get(key),initial.get(key)),'initial '+key)
    for name,info in contract['prefixes'].items():
        with (folder/name).open('rb') as handle:
            require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'],'prefix '+name)
    rows = [json.loads(line) for line in (folder/'h1_training_metrics.jsonl').read_text().splitlines()]
    rows = [row for row in rows if row['iteration'] > parent['iteration']]
    require([r['iteration'] for r in rows] == list(range(parent['iteration']+1,final['iteration']+1)), 'metric suffix continuity')
    require(rows and all(r['critic_contract']=='critic_v2' for r in rows), 'critic metric contract')
    steps = expected_steps(rows,final['config']['mini_batch_size'])
    require(steps > 0, 'no updates')
    for key,state in initial['optimizer']['state'].items():
        require(int(final['optimizer']['state'][key]['step']-state['step']) == steps, 'old Adam step continuity')
    new_ids = set(final['optimizer']['state'])-set(initial['optimizer']['state'])
    require(len(new_ids) == (76 if independent and not prior_independent else 0), 'new Adam states')
    require(all(int(final['optimizer']['state'][key]['step']) == steps for key in new_ids), 'new Adam step')
    require(final['optimizer']['param_groups'] == initial['optimizer']['param_groups'],'Adam scope/LR drift')
    require(all(torch.isfinite(value).all() for value in final['model'].values()), 'nonfinite model')
    require(bool(final['config'].get('independent_observable_critic',False)) == independent,'wrong arm')
    require(any(not torch.equal(value,initial['model'][key]) for key,value in final['model'].items()
                if not key.startswith(('value_head.','observable_value_encoder.'))), 'actor unchanged')
    if independent:
        require(any(not torch.equal(value,initial['model'][key]) for key,value in final['model'].items()
                    if key.startswith('observable_value_encoder.')), 'encoder unchanged')
    new_physical = final['environment_hand_accounting']['completed_hands']-contract['initial_physical']
    require(new_physical == declared['new_physical_hands'],'terminal accounting mismatch')
    require(final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows'] == sum(r['ppo_replay_rows'] for r in rows),'replay count')
    require(len(final['ppo_replay_entries']) == 2,'replay window')
    require([e['iteration'] for e in final['ppo_replay_entries']] == [final['iteration']-1,final['iteration']],'replay tail')
    assignment = [json.loads(line) for line in (folder/'opponent_assignments.jsonl').read_text().splitlines()]
    current = [r for r in assignment if r['applies_to_iteration'] > parent['iteration']]
    require([r['applies_to_iteration'] for r in current] == list(range(parent['iteration']+1,final['iteration']+1)),'assignment suffix')
    namespace = final['fixed_deal_attempt']['receipt']['namespace']
    require(namespace == gate['namespace'] != parent['fixed_deal_attempt']['receipt']['namespace'],'namespace')
    from alpha_holdem.fixed_deal_attempt import load_attempt
    attempt = final['fixed_deal_attempt']
    require(load_attempt(Path(attempt['path']),attempt['sha256']) == attempt['receipt'],'attempt receipt')
    require(attempt['receipt']['parent_checkpoint_sha256'] == contract['parent_sha256'],'attempt parent')
    report = {'passed':True,'seed':contract['seed'],'arm':contract['arm'],'stage':contract['stage'],
        'new_physical_hands':new_physical,'new_transition_hands':final['total_hands']-parent['total_hands'],
        'new_replay_rows':sum(r['ppo_replay_rows'] for r in rows),'optimizer_step_delta':steps,
        'checkpoint_sha256':declared['checkpoint_sha256'],'namespace':namespace,
        'scope':'Training integrity only, not policy strength or bitwise worker equivalence.'}
    with (folder/'independent_review.json').open('x',encoding='utf-8') as handle: json.dump(report,handle,indent=2)
    print(json.dumps(report))


if __name__ == '__main__': main()
