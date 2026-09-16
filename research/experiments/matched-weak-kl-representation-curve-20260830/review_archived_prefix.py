"""Read immutable training archive on CPU; no games, restarts or policy selection."""
import argparse
import json
from pathlib import Path
import sys

import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
from run_pilot import SOURCE, DIGESTS, sha, verify_sources
from report_completed_pilot import batch_accounting, validate_steps, validate_training


def inspect_prefix(source, checkpoint, rows, config, arm, iteration):
    if iteration <= 0 or iteration % 4 or checkpoint['iteration'] != iteration or len(rows) != iteration:
        raise ValueError('Not the requested complete archival PPO prefix')
    validate_training(config,rows,arm)
    accounting = checkpoint['environment_hand_accounting']
    counts = [row['environment_hand_accounting']['completed_hands'] for row in rows]
    if (not accounting['prefix_complete'] or accounting['completed_hands'] != counts[-1]
            or any(b <= a for a,b in zip(counts,counts[1:]))
            or checkpoint['total_hands'] != accounting['legacy_training_marker_hands']):
        raise ValueError('Invalid physical counter prefix or legacy marker continuity')
    if accounting['session_completed_hands'] != accounting['completed_hands']:
        raise ValueError('Unexpected resumed session in this uninterrupted new run')
    if sum(row['completed_hands'] for row in accounting['session_worker_counts']) != accounting['completed_hands']:
        raise ValueError('Worker physical counters disagree')
    if list(source['model']) != list(checkpoint['model']):
        raise ValueError('Unexpected model architecture')
    heads,representation = {},{}
    for name,value in checkpoint['model'].items():
        if not torch.isfinite(value).all():
            raise ValueError('Nonfinite learned weights')
        difference = float(torch.linalg.vector_norm(value-source['model'][name]))
        target = heads if name.startswith(('policy_head.','preflop_policy_head.','value_head.')) else representation
        target[name]=difference
    if len(heads)!=10 or len(representation)!=76 or any(value<=0 for value in heads.values()):
        raise ValueError('Native head scope or movement missing')
    expected_changed = 0 if arm=='heads' else 76
    if sum(value>0 for value in representation.values()) != expected_changed:
        raise ValueError('Actual representation update scope differs')
    for state in checkpoint['optimizer']['state'].values():
        if any(isinstance(value,torch.Tensor) and not torch.isfinite(value).all() for value in state.values()):
            raise ValueError('Nonfinite persisted Adam state')
    steps = [float(state['step']) for state in checkpoint['optimizer']['state'].values()]
    batches = batch_accounting(rows,1024)
    validate_steps(batches,steps,10 if arm=='heads' else 86)
    return dict(status='PASS',arm=arm,iteration=iteration,
        observed_physical_prefix_hands=accounting['completed_hands'],
        observed_marker_prefix_hands=checkpoint['total_hands'],
        optimizer_state_tensors=len(steps),adam_steps_per_tensor=batches['total_steps'],
        partial_batch_steps=batches['partial_batch_steps'],
        changed_head_tensors=len(heads),changed_representation_tensors=expected_changed,
        head_change_l2=heads,representation_change_l2=representation,
        max_reference_kl=max(row['reference_policy_kl'] for row in rows),
        max_approx_kl=max(row['approx_kl'] for row in rows),
        max_clip_fraction=max(row['clip_frac'] for row in rows),
        kl_early_stops=sum(bool(row['kl_early_stop_triggered']) for row in rows),
        new_training_hands=0,evaluation_hands=0,
        claim_scope='Read-only archival health; no strength estimate or change to the registered experiment.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--arm',choices=['heads','full'],required=True)
    parser.add_argument('--iteration',type=int,required=True)
    args=parser.parse_args()
    run=BASE/args.arm
    output=BASE/f'{args.arm}_iter{args.iteration:06d}_prefix_review.json'
    if output.exists():
        raise RuntimeError('Refuse to overwrite archived-prefix review')
    paths=list((run/'checkpoints').glob(f'checkpoint_iter{args.iteration:06d}_hands*.pt'))
    if len(paths)!=1:
        raise ValueError('Wait for the exact immutable archive; no substitution')
    path=paths[0]
    before=sha(path)
    torch.set_num_threads(1)
    copied=json.loads((BASE/'execution_code/copy_manifest.json').read_text())
    verify_sources(copied)
    source=torch.load(SOURCE,map_location='cpu',weights_only=False)
    checkpoint=torch.load(path,map_location='cpu',weights_only=False)
    # A live tail is not evidence for this completed prefix. Select only complete
    # newline-terminated rows and require all1..N; never modify the metrics file.
    raw=(run/'h1_training_metrics.jsonl').read_bytes()
    complete=raw[:raw.rfind(b'\n')+1]
    all_rows=[json.loads(line) for line in complete.splitlines() if line.strip()]
    rows=[row for row in all_rows if row['iteration']<=args.iteration]
    config=json.loads((run/'run_manifest.json').read_text())['config']
    result=inspect_prefix(source,checkpoint,rows,config,args.arm,args.iteration)
    if sha(path)!=before or sha(SOURCE)!=DIGESTS[0]:
        raise ValueError('Immutable archive/source changed while reading')
    verify_sources(copied)
    result.update(archive_path=str(path),archive_sha256=before,source_sha256=DIGESTS[0],
        review_script_sha256=sha(Path(__file__)),prefix_metric_rows=rows)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({key:value for key,value in result.items()
                     if key not in ['head_change_l2','representation_change_l2','prefix_metric_rows']}))


if __name__=='__main__':
    main()
