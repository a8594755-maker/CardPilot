"""Read-only current four-branch pool turnover and retained-metric allocation audit."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
TRAIN=ROOT/'research/experiments/v6-preflop-actor-route-2m-continuation-20260906'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,message):
    if not ok: raise ValueError(message)
def main():
    out=BASE/'report.json'
    require(not out.exists(),'preserve report')
    report=read(TRAIN/'post_terminal_review.json')
    require(read(TRAIN/'experiment.json')['status']=='COMPLETED' and report['passed'],'training not closed')
    inputs={str(TRAIN/'post_terminal_review.json'):sha(TRAIN/'post_terminal_review.json'),str(Path(__file__)):sha(Path(__file__))}
    results={}
    for seed in (1,3):
        for arm in ('detached','connected'):
            name=f'seed{seed}_{arm}_stage3'
            folder=TRAIN/name
            paths=[folder/'verification.json',folder/'latest.pt',folder/'h1_training_metrics.jsonl']
            for p in paths:
                digest=sha(p)
                require(report['input_sha256'].get(str(p))==digest,'unbound input '+str(p))
                inputs[str(p)]=digest
            verified=read(paths[0]); start=verified['pool_audit']['parent_iteration']
            checkpoint=torch.load(paths[1],map_location='cpu',weights_only=False)
            history=[x for x in checkpoint['pool_candidate_history'] if x.get('iteration',-1)>start]
            require(len(history)==verified['pool_audit']['new_candidates_reconstructed'],'incomplete current candidate coverage')
            with paths[2].open(encoding='utf-8') as f:
                rows=[json.loads(line) for line in f if line.strip()]
            rows=[row for row in rows if row['iteration']>start]
            require([x['iteration'] for x in rows]==list(range(start+1,verified['pool_audit']['final_iteration']+1)),'incomplete metric suffix')
            slots=Counter(); exposure=Counter(); epochs=Counter()
            for row in rows:
                for group in row['adaptive_opponent_league']:
                    slots[str(group['opponent_id'])]+=group['iteration_hands']
                for group, actions in row['advantage_by_position_street_action_slot'].items():
                    exposure[group]+=sum(v['rows'] for v in actions.values())
                epochs[str(row['ppo_epochs_completed'])]+=1
            active=[{k:x.get(k) for k in ('id','iteration','selection_loss','selection_score')}
                    |{'kind':x.get('score_components',{}).get('kind','learned_snapshot')}
                    for x in checkpoint['pool_active_metadata']]
            results[name]={'new_physical_hands':verified['new_physical_hands'],
                'new_candidate_count':len(history),'new_candidates_selected_at_insertion':sum(bool(x['selected']) for x in history),
                'distinct_active_sets_after_insertions':len({tuple(x['active_ids_after']) for x in history}),
                'active_metadata':active,'parent_iteration':start,'final_iteration':rows[-1]['iteration'],
                'pool_slot_transition_hand_observations':dict(slots),
                'policy_advantage_row_exposure_by_seat_street':dict(exposure),
                'ppo_epochs_histogram':dict(epochs),
                'kl_early_stop_iterations':sum(bool(x['kl_early_stop_triggered']) for x in rows),
                'procedural_hands_in_suffix_metrics':sum(x['procedural_opponent_metrics']['hands'] for x in rows),
                'public_session_hands_at_endpoint':rows[-1]['public_opponent_accounting']['session_hands'],
                'replay_rows_in_suffix':sum(x['ppo_replay_rows'] for x in rows)}
            del checkpoint
    for p,h in inputs.items(): require(sha(Path(p))==h,'source changed')
    value={'passed':True,'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
        'input_sha256':inputs,'branches':results,'new_training_hands':0,'evaluation_hands':0,
        'limitations':['Pool slots are local positions, not global snapshot identities across pool changes.',
            'Advantage row exposures include replay and are not unique hands or optimizer gradient mass.',
            'Candidate loss scores measured on different data are not calibrated opponent strengths.',
            'Descriptive coverage cannot establish causal external-performance effects.']}
    with out.open('x',encoding='utf-8') as f: json.dump(value,f,indent=2,allow_nan=False)
    print(json.dumps(results,indent=2))
if __name__=='__main__': main()
