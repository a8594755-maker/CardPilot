"""Reviewed controller continuation; never replay the completed seed1 work."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import time
import psutil
import torch
import run_probe as runner

BASE,old = runner.BASE,runner.old


def recover_result(probe, seed):
    folder = old.directory(seed,'control',1)
    contract = old.read(folder/'parent_contract.json')
    observation = old.read(folder/'mixture_observation.json')
    assert observation['clean_return'] and observation['opponent_forward_rows']>0
    assert 'Done!' in (folder/'stdout.log').read_text(encoding='utf-8')
    assert not psutil.pid_exists(old.read(folder/'process.json')['pid'])
    assert old.sha(Path(contract['path']))==contract['sha256']
    parent = torch.load(contract['path'],map_location='cpu',weights_only=False)
    final = torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
    rows = [r for r in old.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl') if r['iteration']>parent['iteration']]
    assert rows and all(r.get('gradient_diagnostics') for r in rows)
    assert [r['iteration'] for r in rows] == list(range(parent['iteration']+1,final['iteration']+1))
    physical = final['environment_hand_accounting']['completed_hands']-contract['physical_hands']
    assert physical>=16384
    current = [r for r in old.ctl.execution.complete_jsonl(folder/'opponent_assignments.jsonl') if r['applies_to_iteration']>parent['iteration']]
    assert [r['applies_to_iteration'] for r in current]==[r['iteration'] for r in rows]
    prior_ids = {s['id'] for s in parent['pool_snapshots']}
    sampled_new = {w['opponent']['snapshot_id'] for r in current for w in r['workers'] if w['opponent']['kind']=='pool_snapshot' and w['opponent']['snapshot_id'] not in prior_ids}
    result = dict(seed=seed,new_physical_hands=physical,new_transition_hands=final['total_hands']-parent['total_hands'],new_replay_rows=final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows'],checkpoint_sha256=old.sha(folder/'latest.pt'),namespace=final['fixed_deal_attempt']['receipt']['namespace'],sampled_new_snapshot_ids=sorted(sampled_new),optimizer=old.ctl.prior.optimizer_step_audit(parent,final,True),scope='Completed training recovered after inapplicable long-dose snapshot exposure gate; independent state review required.')
    if not (folder/'verification.json').exists():
        old.write_new(folder/'verification.json', result)
    old.write_new(folder/'gradient_probe.json',dict(seed=seed,rows=[dict(iteration=r['iteration'],gradient_diagnostics=r['gradient_diagnostics'],approx_kl=r['approx_kl'],entropy=r['entropy'],reference_policy_kl=r['reference_policy_kl']) for r in rows]))
    probe.results.append(result)
    probe.namespaces.add(result['namespace'])
    probe.inputs[str(folder/'latest.pt')] = result['checkpoint_sha256']


def main():
    for key in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key]='1'
    torch.set_num_threads(1)
    owner = old.read(BASE/'ownership.json')
    assert not psutil.pid_exists(owner['pid'])
    assert not old.directory(3,'control',1).exists()
    probe = runner.Probe.__new__(runner.Probe)
    contract = old.read(BASE/'input_contract.json')
    old.INITIAL = {int(k):v for k,v in contract['initial'].items()}
    probe.inputs = dict(contract['input_sha256'])
    old.ctl.execution.check_hashes(probe.inputs)
    probe.sources = {p:h for p,h in probe.inputs.items() if p.endswith('.py')}
    probe.namespaces = set(old.read(runner.PARENT/'post_terminal_review.json')['namespaces'])
    probe.namespaces.update(old.read(runner.PARENT/'qualification.json')['known_namespaces'])
    probe.started,probe.last_tick,probe.child = time.perf_counter(),0,None
    probe.results,probe.phase,probe.corpus = [],'RECOVER_COMPLETED_SEED1',{}
    probe.owner = dict(pid=os.getpid(),create_time=psutil.Process().create_time(),command=sys.orig_argv,started_at=datetime.now(timezone.utc).isoformat())
    old.write_new(BASE/'continuation_ownership.json',probe.owner)
    recover_result(probe,1)
    try:
        probe.train(3,'control',1)
    except ValueError as error:
        if str(error)!='new opponents not assigned':
            raise
        old.write_new(BASE/'seed3_long_dose_gate_deviation.json',dict(message=str(error),reason='Four-iteration gradient probe does not require two new opponent identities; record realized exposure without a diversity claim.'))
    # train may have appended its result; use one accounting entry per seed.
    probe.results = [r for r in probe.results if r['seed']!=3]
    recover_result(probe,3)
    old.ctl.execution.check_hashes(probe.inputs)
    old.write_new(BASE/'terminal.json',dict(status='COMPLETE_REVIEW_REQUIRED',runs=probe.results,wall_seconds=time.time()-owner['create_time'],controller_continuation=True))
    probe.tick(force=True)


if __name__=='__main__':
    main()
