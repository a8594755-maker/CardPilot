"""Deploy-only exports and external public-state sampled parity, zero requests."""
import hashlib
import json
from pathlib import Path
import sys
import time
import torch
import numpy as np

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PILOT=BASE.parent/'v6-regularized-return-two-seed-pilot-20260908'
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908'))
import sampled_eval as ev
from alpha_holdem import legacy_observation_bridge_v6 as bridge
from alpha_holdem.v5_mirror_eval import init_model,read_checkpoint


def sha(path):
    with Path(path).open('rb') as h: return hashlib.file_digest(h,'sha256').hexdigest()
def write(path,x):
    with path.open('x') as h: json.dump(x,h,indent=2)


def states(seed):
    selected={i:[] for i in range(4)}; completed=0
    # Reconstruct retained training traces only, no fresh deals or new outcomes.
    for path in sorted((PILOT/f'seed{seed}_regularized').glob('update-*/hands.jsonl')):
        for line in path.read_text().splitlines():
            trace=json.loads(line); state=ev.ChipState.new(trace['deck'])
            for row in trace['rows']:
                assert state.actor==row['actor']
                if len(selected[state.street])<8: selected[state.street].append(state)
                _,table=bridge.legacy_observation_from_state(state)
                state=ev.apply_incr(state,table[row['slot']])
            assert state.terminal and [x/100 for x in state.payoffs()]==trace['terminal_bb']
            completed+=1
            if all(len(v)==8 for v in selected.values()): return selected,completed
    raise AssertionError('insufficient four-street coverage')


def main():
    started=time.perf_counter(); torch.set_num_threads(1)
    contract=json.loads((PILOT/'stage2_evaluation_contract.json').read_text())
    hashes={str(p):sha(p) for p in (ROOT/'scripts/alpha_holdem').glob('*.py')}
    hashes[str(Path(__file__))]=sha(__file__)
    reports=[]; reconstructions=0
    for seed in ('1','3'):
        parent_info=contract['policies'][seed]['parent']; parent_path=Path(parent_info['path'])
        assert sha(parent_path)==parent_info['sha256']; hashes[str(parent_path)]=sha(parent_path)
        parent=read_checkpoint(parent_path)
        selected,count=states(seed); reconstructions+=count
        for label,item in contract['policies'][seed].items():
            path=Path(item['path']); assert sha(path)==item['sha256']; hashes[str(path)]=sha(path)
            source=read_checkpoint(path)
            weights=source['model']
            internal=init_model(parent,'cpu').eval(); internal.load_state_dict(weights,strict=True)
            # Only execution/model metadata: no stale optimizer/replay or inherited
            # training accounting masquerading as a new-regimen resume artifact.
            keys=('norm_layer','critic_contract','separate_preflop_head','preflop_trunk_gradient',
                  'env_version','obs_version','model_obs_version','observation_bridge_contract',
                  'policy_contract','rules_version','chips_per_bb','starting_stack_bb',
                  'raise_action_mapping','action_space_version')
            export={k:parent[k] for k in keys if k in parent}
            export.update(model=weights,deployment_only=True,not_training_resume=True,
                source_checkpoint_path=str(path),source_checkpoint_sha256=item['sha256'],
                architecture_parent_sha256=parent_info['sha256'],
                execution_contract=dict(policy_mode='sample',temperature=1,device='cpu',observation_bridge='legacy-v4'))
            out=BASE/f'seed{seed}_{label}.pt'
            with out.open('xb') as h: torch.save(export,h)
            deployed=bridge.load_policy(out,'cpu')
            assert all(torch.equal(v,deployed.model.state_dict()[k]) for k,v in weights.items())
            checked=0
            for street,fixtures in selected.items():
                for state in fixtures:
                    obs,table=ev._observation(internal,state,'legacy_v4')
                    external=dict(action=bridge.action_prefix(state),client_pos=state.actor,
                        hole_cards=[bridge.card_string(x) for x in state.holes[state.actor]],
                        board=[bridge.card_string(x) for x in state.board])
                    args=[torch.as_tensor(obs[k]).unsqueeze(0) for k in ('card_info','action_info','extra_info','legal_mask')]
                    with torch.no_grad():
                        left=internal(*args); right=deployed.model(*args)
                    assert all(torch.equal(a,b) for a,b in zip(left,right))
                    for u in (0.0,.123456,.5,.876543,1-2**-53):
                        slot=ev.legal_slot(left[0][0].numpy(),obs['legal_mask'],u)
                        action,info=bridge.external_decision(deployed,external,uniform=u,policy_mode='sample')
                        assert action==table[slot] and info['legacy_selected_action_slot']==slot
                        assert info['temperature']==1 and info['policy_mode']=='sample'
                        assert info['source_checkpoint_sha256']==sha(out)
                        assert abs(sum(info['behavior_probs'])-1)<1e-10
                        checked+=1
            reports.append(dict(seed=seed,policy=label,path=str(out),sha256=sha(out),
                source_sha256=item['sha256'],retained_states=32,uniform_decisions=checked,
                tensor_count=len(weights),exact_forward=True,external_action_parity=True))
    for path,digest in hashes.items(): assert sha(path)==digest
    write(BASE/'result.json',dict(passed=True,reports=reports,source_hashes=hashes,
        reconstruction_hands=reconstructions,new_training_hands=0,slumbot_hands=0,network_requests=0,
        wall_seconds=time.perf_counter()-started,
        limitations='192 retained public states and960 uniform decisions; no universal state proof or live transport qualification. Exports are deployment-only, original training states unchanged.'))
    print(json.dumps(dict(passed=True,exports=len(reports),reconstruction_hands=reconstructions)))


if __name__=='__main__': main()
