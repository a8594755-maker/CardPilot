"""Read-only independent raw/identity review before finishing the two-arm record."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import statistics
import subprocess
import sys
import run_pilot as pilot

BASE, ROOT = pilot.BASE, pilot.ROOT
def interval(values):
    if len(values)<2 or not all(math.isfinite(x) for x in values): raise ValueError('Invalid pairs')
    mean=math.fsum(values)/len(values)
    se=math.sqrt(math.fsum((x-mean)**2 for x in values)/(len(values)-1)/len(values))
    z=statistics.NormalDist().inv_cdf((1+(1-.05/6))/2)
    return dict(bb_per_100=mean,standard_error=se,ci95=[mean-1.96*se,mean+1.96*se],
                ci_adjusted=[mean-z*se,mean+z*se])


def raw_values(rows):
    if len(rows)!=4096 or [r['pair_index'] for r in rows]!=list(range(4096)):
        raise ValueError('Wrong raw pair prefix')
    for row in rows:
        assert len(row['deck'])==52 and set(row['deck'])==set(range(52))
        assert len(row['rewards_bb'])==2 and all(math.isfinite(v) and abs(v)<=200 for v in row['rewards_bb'])
        assert len(row['decisions'])==2 and all(type(v) is int and v>0 for v in row['decisions'])
    return [math.fsum(row['rewards_bb'])/2*100 for row in rows]


def same_process_alive(row):
    import psutil
    try: return abs(psutil.Process(row['pid']).create_time()-row['create_time'])<.01
    except psutil.NoSuchProcess: return False


def close(a,b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8), (a,b)


def main():
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No repeated or alternate review')
    execution = pilot.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not same_process_alive(execution)
    children = execution['children']
    roles = {'train_control25','train_selfplay75'} | {f'{label}_anchor{a}' for label in ['source','control25','selfplay75'] for a in range(5)}
    assert len(children) == 17 and {r['role'] for r in children} == roles
    assert all(r['exit_code'] == 0 and not same_process_alive(r) for r in children)
    copies = pilot.read(BASE/'execution_code/copy_manifest.json')
    inputs = pilot.read(BASE/'frozen_inputs.json')
    pilot.verify(copies,inputs)
    anchors = pilot.read(BASE/'anchor_manifest.json')
    assert [r['index'] for r in anchors] == list(range(5))
    candidates = pilot.read(BASE/'candidate_manifest.json')
    assert list(candidates) == ['source','control25','selfplay75']
    for row in candidates.values():
        assert pilot.sha(row['path']) == row['sha256']
        validate_metadata(torch.load(row['path'],map_location='cpu',weights_only=False))
    source = torch.load(ROOT/'models/baseline/standard10/latest.pt',map_location='cpu',weights_only=False)
    counts, training = {}, []
    for label in ['control25','selfplay75']:
        run = BASE/'production'/label
        checkpoint = torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        validate_metadata(checkpoint)
        config = checkpoint['config']
        for k,v in dict(rollout_mode='multi',rollout_envs_per_worker=8,workers=12,seed=20261005,worker_seed_base=2026100500,
                        validate_stream=True,reset_hand_counter=True,reset_optimizer=True,source_policy_kl_coef=.01,
                        total_environment_hands=1048576,fixed_training_deal_start_index=0,
                        self_play_fraction=.25 if label=='control25' else .75).items(): assert config[k] == v
        account = checkpoint['environment_hand_accounting']
        count = account['completed_hands']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert account['origin_run_id'] == checkpoint['run_id'] == f'v6_selfplay_share_r3_{label}_20260831'
        assert sum(r['completed_hands'] for r in account['session_worker_counts']) == count
        manifest, audit = pilot.read(run/'run_manifest.json'), pilot.read(run/'session_audit.json')
        assert manifest['status'] == 'finished' and audit['status'] == 'PASS'
        assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands']
        metrics = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
        assert [r['iteration'] for r in metrics] == list(range(1,checkpoint['iteration']+1))
        physical = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
        assert all(a < b for a,b in zip([0]+physical[:-1],physical))
        assert all(v < 1048576 for v in physical[:-1]) and 1048576 <= physical[-1] <= count
        for r in metrics:
            assert r['run_id'] == checkpoint['run_id'] and r['ppo_replay_rows'] == 0
            assert all(math.isfinite(r[k]) for k in ['approx_kl','reference_policy_kl'])
        assert checkpoint['total_hands'] == manifest['total_hands'] == metrics[-1]['hands']
        expected_pool = [r['sha256'] for r in anchors[:3]]
        assert [r['score_components']['checkpoint_sha256'] for r in checkpoint['pool_snapshots']] == expected_pool
        assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
        assert sum(not torch.equal(v,source['model'][k]) for k,v in checkpoint['model'].items()) == 86
        assert len(checkpoint['optimizer']['state']) == 86
        for state in checkpoint['optimizer']['state'].values():
            assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v,torch.Tensor))
        assert candidates[label]['sha256'] == pilot.sha(run/'latest.pt') == pilot.sha(BASE/'frozen'/f'{label}.pt')
        for key,name in dict(checkpoint='latest.pt',manifest='run_manifest.json',metrics='h1_training_metrics.jsonl',
                             assignments='opponent_assignments.jsonl',train_log='latest_train.log').items():
            assert pilot.sha(run/name) == audit['artifact_integrity'][key]['sha256']
        health=pilot.read(run/'training_health.json')
        assert health['status']=='PASS' and health['new_training_hands']==count
        assignments=[json.loads(line) for line in (run/'opponent_assignments.jsonl').read_text().splitlines()]
        used=[r for r in assignments if r['applies_to_iteration']<=checkpoint['iteration']]
        assert [r['applies_to_iteration'] for r in used]==list(range(1,checkpoint['iteration']+1))
        worker_counts=[]
        for record in used:
            groups=record['group_metadata']
            assert len(groups)==8 and sum(g['opponent_id']==-1 for g in groups)==(2 if label=='control25' else 6)
            assert sorted(w for g in groups for w in g['workers'])==list(range(12))
            worker_counts.append(sum(len(g['workers']) for g in groups if g['opponent_id']==-1))
        exposure=health['assignment_exposure']
        assert exposure['selfplay_workers_per_update']==worker_counts
        assert exposure['selfplay_worker_slots']==sum(worker_counts) and exposure['all_worker_slots']==12*checkpoint['iteration']
        close(exposure['selfplay_worker_fraction'],sum(worker_counts)/(12*checkpoint['iteration']))
        assert exposure['terminal_hand_fraction'] is None
        assert health['fresh_policy_rows']==sum(r['fresh_policy_rows'] for r in metrics)
        assert health['terminal_trajectories']==sum(r['terminal_trajectories'] for r in metrics)
        steps=[float(s['step']) for s in checkpoint['optimizer']['state'].values()]
        assert health['adam_step_range']==[min(steps),max(steps)]
        counts[label] = count
        training.append(dict(arm=label,new_training_hands=count,iteration=checkpoint['iteration'],overshoot=count-1048576,
                             shutdown_counter_tail=count-physical[-1],checkpoint_sha256=pilot.sha(run/'latest.pt'),
                             fresh_policy_rows=health['fresh_policy_rows'],terminal_trajectories=health['terminal_trajectories'],
                             adam_step_range=health['adam_step_range'],assignment_exposure=exposure))
    expected_decks, rng = [], random.Random(20261006)
    for _ in range(4096):
        deck = list(range(52))
        rng.shuffle(deck)
        expected_decks.append(deck)
    assert len({tuple(d) for d in expected_decks}) == 4096
    values, cells = {}, []
    for label,candidate in candidates.items():
        for a in range(5):
            directory = BASE/'matrix'/f'{label}_anchor{a}'
            summary = pilot.read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['seed'] == 20261006 and summary['evaluation_hands'] == 8192
            assert summary['candidate_sha256'] == candidate['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
            assert summary['pairs_sha256'] == pilot.sha(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert [r['deck'] for r in rows] == expected_decks
            values[label,a] = raw_values(rows)
            result = interval(values[label,a])
            close(result['bb_per_100'],summary['bb_per_100'])
            for x,y in zip(result['ci95'],summary['ci95']): close(x,y)
            cells.append(dict(candidate=label,anchor=a,**result))
    assert all(x == 0 for x in values['source',0])
    contrasts = [dict(anchor=a,**interval([v-s for s,v in zip(values['source',a],values['selfplay75',a])])) for a in range(5)]
    heldout = interval([math.fsum(values['selfplay75',a][i]-values['control25',a][i] for a in [3,4])/2 for i in range(4096)])
    passed=all(count>=1048576 for count in counts.values()) and set(counts)=={'control25','selfplay75'}
    assert passed
    writer = pilot.read(BASE/'completed_analysis.json')
    assert writer['arm_counts'] == counts and writer['new_training_hands'] == sum(counts.values())
    assert writer['evaluation_hands'] == 122880 and writer['slumbot_hands'] == 0 and writer['external_pair_admitted'] == passed and writer['internal_strength_selection'] is False
    for r,w in zip([*contrasts,heldout],[*writer['primary_contrasts'],writer['heldout_league_contrast']]):
        close(r['bb_per_100'],w['bb_per_100'])
        for x,y in zip(r['ci_adjusted'],w['ci_adjusted']): close(x,y)
    decision = 'ADMIT_FIXED_EXTERNAL_TRANSFER_PAIR'
    assert writer['decision'] == decision
    report = dict(status='PASS',decision=decision,reviewed_at=datetime.now(timezone.utc).isoformat(),
                  external_pair_admitted=passed,internal_strength_selection=False,qualification_admitted=False,
                  new_training_hands=sum(counts.values()),evaluation_hands=122880,slumbot_hands=0,
                  source_pairs_verified=len(copies),clean_child_exits=17,training=training,primary_contrasts=contrasts,
                  heldout_league_contrast=heldout,cells=cells)
    pilot.write(BASE/'reviewed_analysis.json',report)
    lines = ['# v6 self-play share training and internal diagnostics','',f'Decision: {decision}.',
             '',f'{sum(counts.values())} actual new training hands;122880 internal hands;17 normal child exits. Full evidence review passed.',
             '', '| Contrast | bb/100 | 95%CI | Six-contrast adjusted CI |','|---|---:|---|---|']
    for name,row in [(f'selfplay75-source anchor{r["anchor"]}',r) for r in contrasts]+[('heldout selfplay75-control25 mean',heldout)]:
        lines.append(f'| {name} | {row["bb_per_100"]:+.4f} | {row["ci95"]} | {row["ci_adjusted"]} |')
    lines += ['', 'Both healthy endpoints are admitted to the prespecified external transfer pair regardless of these internal scores. No100k qualification. Matched seeds are not identical asynchronous trajectories. '
              'These anchors are held out of training, not unseen policy families or independent training seeds.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    pilot.log('--command','python research/experiments/v6-selfplay75-transfer-pilot-r3-20260831/review_finish.py',
              '--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md',
              '--note','Independent raw arithmetic, regenerated deal sequence and full source/session review passed; no internal strength selection.')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
                    '--summary',f'Matched self-play share completed{sum(counts.values())}physical training and122880internal hands;{decision}.',
                    '--conclusion','Internal diagnostics cannot select external arms; both fixed healthy endpoints admitted, no external or Nash-strength conclusion.',
                    '--decision',decision,'--next-step',
                    'Verify candidate-specific deployment parity then preregister20k fresh external hands per frozen arm, balanced/interleaved total concurrency8; no checkpoint rescue.',
                    '--count',f'new_training_hands={sum(counts.values())}','--count','evaluation_hands=122880','--count','slumbot_hands=0'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
