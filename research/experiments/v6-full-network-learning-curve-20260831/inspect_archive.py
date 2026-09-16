"""Read-only health review of one immutable scheduled checkpoint, no hands."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from research.experiment_log import sha256_file
from alpha_holdem.policy_contract_v6 import validate_metadata


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--iteration',type=int,required=True)
    args=p.parse_args()
    if args.iteration<=0 or args.iteration%4:
        raise ValueError('Only scheduled positive4-update archives')
    output=BASE/f'archive_iter{args.iteration:06d}_review.json'
    if output.exists(): raise ValueError('Preserve earlier archive review')
    paths=list((BASE/'production/checkpoints').glob(f'checkpoint_iter{args.iteration:06d}_hands*.pt'))
    if len(paths)!=1: raise ValueError('Need exactly one completed scheduled archive')
    path=paths[0]
    digest=sha256_file(path)
    checkpoint=torch.load(path,map_location='cpu',weights_only=False)
    validate_metadata(checkpoint)
    rows=[json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    row=next(r for r in rows if r['iteration']==args.iteration)
    assert checkpoint['iteration']==args.iteration
    account=checkpoint['environment_hand_accounting']
    assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands']==0
    assert account['completed_hands']==row['environment_hand_accounting']['completed_hands']
    assert sum(r['completed_hands'] for r in account['session_worker_counts'])==account['completed_hands']
    assert checkpoint['config']['env_version']=='v6' and checkpoint['config']['v6_rebind_legacy_weights']
    assert checkpoint['config']['reset_optimizer'] and checkpoint['config']['reset_hand_counter']
    assert not checkpoint.get('ppo_replay_entries')
    source_path=ROOT/'models/baseline/standard10/latest.pt'
    source_sha=sha256_file(source_path)
    assert source_sha=='91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    source=torch.load(source_path,map_location='cpu',weights_only=False)
    changed=[k for k,v in checkpoint['model'].items() if not torch.equal(v,source['model'][k])]
    assert len(changed)==86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    optimizer=checkpoint['optimizer']['state']
    assert len(optimizer)==86
    for state in optimizer.values():
        assert all(torch.isfinite(v).all() for v in state.values() if isinstance(v,torch.Tensor))
    anchors=json.loads((BASE/'anchor_manifest.json').read_text())
    pool=checkpoint['pool_snapshots']
    assert len(pool)==3
    assert [r['score_components']['checkpoint_sha256'] for r in pool]==[r['sha256'] for r in anchors[:3]]
    assert digest==sha256_file(path)
    summary=dict(status='PASS',iteration=args.iteration,physical_hands=account['completed_hands'],
        legacy_training_markers=checkpoint['total_hands'],checkpoint_sha256=digest,source_sha256=source_sha,
        changed_finite_tensors=len(changed),optimizer_states=len(optimizer),
        optimizer_steps=sorted(set(float(s['step']) for s in optimizer.values())),
        reference_policy_kl=row['reference_policy_kl'],approx_kl=row['approx_kl'],
        ppo_epochs_completed=row['ppo_epochs_completed'],additional_training_hands=0,
        additional_evaluation_hands=0,reviewed_at=datetime.now(timezone.utc).isoformat())
    output.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__': main()
