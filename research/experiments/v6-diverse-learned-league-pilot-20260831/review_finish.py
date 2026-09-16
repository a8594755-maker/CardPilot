"""Read-only independent raw/identity review before finishing the two-arm record."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import run_pilot as pilot

BASE, ROOT = pilot.BASE, pilot.ROOT
independent = pilot.load_module('independent_raw_arithmetic', pilot.RETENTION/'review_finish.py')


def close(a,b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-11,abs_tol=1e-8), (a,b)


def main():
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    torch.set_num_threads(1)
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No repeated or alternate review')
    execution = pilot.read(BASE/'execution.json')
    assert execution['status'] == 'COMPLETED_PENDING_REVIEW' and not psutil.pid_exists(execution['pid'])
    children = execution['children']
    roles = {'train_control3','train_diverse5'} | {f'{label}_anchor{a}' for label in ['source','control3','diverse5'] for a in range(5)}
    assert len(children) == 17 and {r['role'] for r in children} == roles
    assert all(r['exit_code'] == 0 and not psutil.pid_exists(r['pid']) for r in children)
    copies = pilot.read(BASE/'execution_code/copy_manifest.json')
    inputs = pilot.read(BASE/'frozen_inputs.json')
    pilot.verify(copies,inputs)
    anchors = pilot.read(BASE/'anchor_manifest.json')
    assert [r['index'] for r in anchors] == list(range(5))
    candidates = pilot.read(BASE/'candidate_manifest.json')
    assert list(candidates) == ['source','control3','diverse5']
    for row in candidates.values():
        assert pilot.sha(row['path']) == row['sha256']
        validate_metadata(torch.load(row['path'],map_location='cpu',weights_only=False))
    source = torch.load(ROOT/'models/baseline/standard10/latest.pt',map_location='cpu',weights_only=False)
    counts, training = {}, []
    for label in ['control3','diverse5']:
        run = BASE/'production'/label
        checkpoint = torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        validate_metadata(checkpoint)
        config = checkpoint['config']
        for k,v in dict(rollout_mode='multi',rollout_envs_per_worker=8,workers=12,seed=20260926,worker_seed_base=2026092600,
                        validate_stream=True,reset_hand_counter=True,reset_optimizer=True,source_policy_kl_coef=.01,
                        total_environment_hands=262144,fixed_training_deal_start_index=0).items(): assert config[k] == v
        account = checkpoint['environment_hand_accounting']
        count = account['completed_hands']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert account['origin_run_id'] == checkpoint['run_id'] == f'v6_diverse_{label}_20260831'
        assert sum(r['completed_hands'] for r in account['session_worker_counts']) == count
        manifest, audit = pilot.read(run/'run_manifest.json'), pilot.read(run/'session_audit.json')
        assert manifest['status'] == 'finished' and audit['status'] == 'PASS'
        assert count == manifest['environment_hand_accounting']['completed_hands'] == audit['actual_environment_hands']
        metrics = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
        assert [r['iteration'] for r in metrics] == list(range(1,checkpoint['iteration']+1))
        physical = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
        assert all(a < b for a,b in zip([0]+physical[:-1],physical))
        assert all(v < 262144 for v in physical[:-1]) and 262144 <= physical[-1] <= count
        for r in metrics:
            assert r['run_id'] == checkpoint['run_id'] and r['ppo_replay_rows'] == 0
            assert all(math.isfinite(r[k]) for k in ['approx_kl','reference_policy_kl'])
        assert checkpoint['total_hands'] == manifest['total_hands'] == metrics[-1]['hands']
        expected_pool = [r['sha256'] for r in anchors[:3]] + ([r[2] for r in pilot.LEAGUE] if label == 'diverse5' else [])
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
        counts[label] = count
        training.append(dict(arm=label,new_training_hands=count,iteration=checkpoint['iteration'],overshoot=count-262144,
                             shutdown_counter_tail=count-physical[-1],checkpoint_sha256=pilot.sha(run/'latest.pt')))
    expected_decks, rng = [], random.Random(20260927)
    for _ in range(8192):
        deck = list(range(52))
        rng.shuffle(deck)
        expected_decks.append(deck)
    assert len({tuple(d) for d in expected_decks}) == 8192
    values, cells = {}, []
    for label,candidate in candidates.items():
        for a in range(5):
            directory = BASE/'matrix'/f'{label}_anchor{a}'
            summary = pilot.read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['seed'] == 20260927 and summary['evaluation_hands'] == 16384
            assert summary['candidate_sha256'] == candidate['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
            assert summary['pairs_sha256'] == pilot.sha(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert [r['deck'] for r in rows] == expected_decks
            values[label,a] = independent.raw_values(rows)
            result = independent.interval(values[label,a])
            close(result['bb_per_100'],summary['bb_per_100'])
            for x,y in zip(result['ci95'],summary['ci95']): close(x,y)
            cells.append(dict(candidate=label,anchor=a,**result))
    assert all(x == 0 for x in values['source',0])
    contrasts = [dict(anchor=a,**independent.interval([v-s for s,v in zip(values['source',a],values['diverse5',a])])) for a in range(5)]
    heldout = independent.interval([math.fsum(values['diverse5',a][i]-values['control3',a][i] for a in [3,4])/2 for i in range(8192)])
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    passed = all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3 and 0 in significant and bool(significant & {3,4}) and heldout['ci_adjusted'][0] > 0
    writer = pilot.read(BASE/'completed_analysis.json')
    assert writer['arm_counts'] == counts and writer['new_training_hands'] == sum(counts.values())
    assert writer['evaluation_hands'] == 245760 and writer['slumbot_hands'] == 0 and writer['confirmation_gate_pass'] == passed
    for r,w in zip([*contrasts,heldout],[*writer['primary_contrasts'],writer['heldout_league_contrast']]):
        close(r['bb_per_100'],w['bb_per_100'])
        for x,y in zip(r['ci_adjusted'],w['ci_adjusted']): close(x,y)
    decision = 'ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'LEAGUE_DIVERSITY_GATE_NOT_PASSED'
    assert writer['decision'] == decision
    report = dict(status='PASS',decision=decision,reviewed_at=datetime.now(timezone.utc).isoformat(),
                  confirmation_gate_pass=passed,qualification_admitted=False,control_eligible=False,
                  new_training_hands=sum(counts.values()),evaluation_hands=245760,slumbot_hands=0,
                  source_pairs_verified=len(copies),clean_child_exits=17,training=training,primary_contrasts=contrasts,
                  heldout_league_contrast=heldout,cells=cells)
    pilot.write(BASE/'reviewed_analysis.json',report)
    lines = ['# v6 learned-opponent diversity result','',f'Decision: {decision}.',
             '',f'{sum(counts.values())} actual new training hands;245760 internal hands;17 normal child exits. Full evidence review passed.',
             '', '| Contrast | bb/100 | 95%CI | Six-contrast adjusted CI |','|---|---:|---|---|']
    for name,row in [(f'diverse5-source anchor{r["anchor"]}',r) for r in contrasts]+[('heldout diverse5-control3 mean',heldout)]:
        lines.append(f'| {name} | {row["bb_per_100"]:+.4f} | {row["ci95"]} | {row["ci_adjusted"]} |')
    lines += ['', 'No Slumbot qualification or control/checkpoint rescue. Matched seeds are not identical asynchronous trajectories. '
              'These anchors are held out of training, not unseen policy families or independent training seeds.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    pilot.log('--command','python research/experiments/v6-diverse-learned-league-pilot-20260831/review_finish.py',
              '--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md',
              '--note','Independent raw arithmetic, regenerated deal sequence, fixed joint gate and full source/session review passed.')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
                    '--summary',f'Matched learned-opponent diversity completed{sum(counts.values())}physical training and245760internal hands;{decision}.',
                    '--conclusion','Fixed held-out/source joint gate completed; no external or Nash-strength conclusion.',
                    '--decision',decision,'--next-step',
                    'Preregister independent confirmation of the new diverse5 final.' if passed else
                    'Choose the next mechanism from complete training/held-out evidence; no control or earlier checkpoint rescue.',
                    '--count',f'new_training_hands={sum(counts.values())}','--count','evaluation_hands=245760','--count','slumbot_hands=0'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
