"""One fixed iteration16 health review per arm, using immutable archives only."""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import shutil
import sys
import run_pilot as pilot

BASE, ROOT = pilot.BASE, pilot.ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--arm',required=True,choices=['control3','diverse5'])
    args = p.parse_args()
    out = BASE/f'archive_{args.arm}_iter16_review.json'
    if out.exists(): raise ValueError('Preserve prior fixed archive review')
    run = BASE/'production'/args.arm
    if pilot.read(run/'run_manifest.json')['iteration'] <= 16:
        raise ValueError('Wait until archive16 is followed by a completed update')
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    sys.path.insert(0,str(ROOT/'scripts/alpha_holdem'))
    from train_v5 import restore_group_assignment_rng_from_evidence
    torch.set_num_threads(1)
    code = BASE/'archive_review_code'
    relative = Path(__file__).resolve().relative_to(ROOT).as_posix()
    if not code.exists():
        code.mkdir()
        pilot.capture_code_provenance(ROOT,code,[relative])
        target = code/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        pilot.write(code/'copy_manifest.json',[dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=pilot.sha(target))])
    for row in pilot.read(code/'copy_manifest.json'):
        assert all(pilot.sha(ROOT/row[k]) == row['sha256'] for k in ['original','copy'])
    copies = pilot.read(BASE/'execution_code/copy_manifest.json')
    pilot.verify(copies,pilot.read(BASE/'frozen_inputs.json'))
    archives = []
    for iteration in [4,16]:
        paths = list((run/'checkpoints').glob(f'checkpoint_iter{iteration:06d}_hands*.pt'))
        assert len(paths) == 1
        path = paths[0]
        before = pilot.sha(path)
        checkpoint = torch.load(path,map_location='cpu',weights_only=False)
        assert before == pilot.sha(path)
        validate_metadata(checkpoint)
        assert checkpoint['iteration'] == iteration and checkpoint['run_id'] == f'v6_diverse_{args.arm}_20260831'
        config = checkpoint['config']
        assert config['reset_optimizer'] and config['reset_hand_counter'] and config['validate_stream']
        assert config['rollout_envs_per_worker'] == 8 and config['source_policy_kl_coef'] == .01
        account = checkpoint['environment_hand_accounting']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
        assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
        optimizer = checkpoint['optimizer']['state']
        assert len(optimizer) == 86
        steps = {float(s['step']) for s in optimizer.values()}
        assert len(steps) == 1 and min(steps) > 0
        for state in optimizer.values(): assert all(torch.isfinite(v).all() for v in state.values() if isinstance(v,torch.Tensor))
        anchors = pilot.read(BASE/'anchor_manifest.json')
        expected = [r['sha256'] for r in anchors[:3]] + ([r[2] for r in pilot.LEAGUE] if args.arm == 'diverse5' else [])
        assert [r['score_components']['checkpoint_sha256'] for r in checkpoint['pool_snapshots']] == expected
        archives.append(dict(iteration=iteration,physical_hands=account['completed_hands'],legacy_markers=checkpoint['total_hands'],
                             optimizer_states=86,optimizer_step=min(steps),checkpoint_sha256=before,path=str(path)))
    assert archives[1]['optimizer_step'] > archives[0]['optimizer_step']
    assert archives[1]['physical_hands'] > archives[0]['physical_hands']
    prefix_files = []
    parsed = []
    for name in ['h1_training_metrics.jsonl','opponent_assignments.jsonl']:
        lines = (run/name).read_text().splitlines(keepends=True)[:16]
        assert len(lines) == 16 and all(line.endswith('\n') for line in lines)
        path = BASE/f'archive_{args.arm}_iter16_{name}'
        if path.exists(): raise ValueError('Preserve previous evidence prefix')
        path.write_text(''.join(lines))
        prefix_files.append(path)
        parsed.append([json.loads(line) for line in lines])
    metrics, assignments = parsed
    assert [r['iteration'] for r in metrics] == list(range(1,17))
    assert metrics[-1]['hands'] == checkpoint['total_hands']
    physical = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
    assert all(a < b for a,b in zip([0]+physical[:-1],physical))
    assert physical[-1] <= archives[1]['physical_hands'] < 262144
    assert all(math.isfinite(r[k]) for r in metrics for k in ['approx_kl','reference_policy_kl'])
    assert all(r['ppo_replay_rows'] == 0 for r in metrics)
    for r in assignments:
        assert r['run_id'] == checkpoint['run_id'] and r['pool_size'] == len(expected)
        assert [s['snapshot_id'] for s in r['pool_snapshot_refs']] == list(range(len(expected)))
    assignment_audit = restore_group_assignment_rng_from_evidence(assignments,metrics,rng=random.Random(0),seed=20260926,
        worker_count=12,pool_size=len(expected),group_count=8,self_play_fraction=.25,checkpoint_iteration=16,
        checkpoint_total_hands=checkpoint['total_hands'],pool_snapshot_ids=list(range(len(expected))))
    assert assignment_audit['records_verified'] == 16 and assignment_audit['pending_assignments'] is None
    report = dict(status='PASS',arm=args.arm,reviewed_at=datetime.now(timezone.utc).isoformat(),archives=archives,
                  final_prefix_reference_kl=metrics[-1]['reference_policy_kl'],final_prefix_approx_kl=metrics[-1]['approx_kl'],
                  assignment_prefix_audit=assignment_audit,source_pairs_verified=len(copies),
                  prefix_files=[dict(path=str(path),sha256=pilot.sha(path)) for path in prefix_files],
                  additional_training_hands=0,additional_evaluation_hands=0,qualification_admitted=False,resume_qualified=False)
    pilot.write(out,report)
    pilot.log('--command',f'python research/experiments/{BASE.name}/inspect_archive.py --arm {args.arm}',
              '--artifact',out,*[v for path in prefix_files for v in ['--artifact',path]],
              *[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',code/name]],
              '--note',f'{args.arm} fixed iteration16 archive health PASS; iteration4->16 optimizer/counters advance;16assignment records replayed. No strength selection or resume qualification.')
    print(json.dumps(report))


if __name__ == '__main__': main()
