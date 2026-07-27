#!/usr/bin/env python3
"""Immutable reporting-only H1-CAL-001 holdout generator, audit and endpoint comparator."""
from __future__ import annotations
import argparse, base64, hashlib, json, math, os, random, statistics, sys, time, zlib
from pathlib import Path
from typing import Any
import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
from v5_mirror_eval import (Policy, apply_policy_legal_emulation, checkpoint_summary, configure_runtime, init_model, make_fixed_state, observation_for, sha256_file, shuffled_deck, utc_now)
from alpha_holdem.environment_v55 import HUNLEnvironmentV55, NUM_ACTIONS
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2

DESIGN_ID='H1-CAL-001'
MANIFEST_SCHEMA='v5.hybrid.h1.calibration_manifest.v1'
ROW_SCHEMA='v5.hybrid.h1.calibration_decision.v1'
SUMMARY_SCHEMA='v5.hybrid.h1.calibration_summary.v1'
AUDIT_SCHEMA='v5.hybrid.h1.calibration_audit.v1'
COMPARE_SCHEMA='v5.hybrid.h1.endpoint_comparison.v1'
SOURCE_SHA='bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e'
PREREG_SHA='bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab'
PAIRS=10000
SEED=2026071111
BOOTSTRAP_SEED=2026071112
BOOTSTRAP_REPS=10000
STACK=200.0
GAMMA=0.999
ACTIVE_POOL_IDS=[109,115,120,129,103]
SOURCE_STATE_SHA='9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255'
POOL_STATE_SHAS={109:'aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953',115:'ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1',120:'86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e',129:'9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255',103:'cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1'}
OBS_FLOATS=6*4*13+25*4*5+2+9

def canonical_bytes(value: Any)->bytes: return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')
def payload_sha(value:dict[str,Any],field:str)->str:
    unsigned=dict(value); unsigned.pop(field,None); return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()

def state_dict_sha(state:dict[str,torch.Tensor])->str:
    d=hashlib.sha256()
    for name in sorted(state):
        t=state[name].detach().cpu().contiguous(); meta=canonical_bytes([name,str(t.dtype),list(t.shape)])
        d.update(len(meta).to_bytes(8,'big')); d.update(meta); d.update(t.numpy().tobytes())
    return d.hexdigest()

def pack_obs(obs:dict[str,Any])->tuple[str,str]:
    flat=np.concatenate([np.asarray(obs['card_info'],dtype=np.float32).reshape(-1),np.asarray(obs['action_info'],dtype=np.float32).reshape(-1),np.asarray(obs['extra_info'],dtype=np.float32).reshape(-1),np.asarray(obs['legal_mask'],dtype=np.float32).reshape(-1)])
    if flat.size!=OBS_FLOATS: raise ValueError('observation size mismatch')
    raw=flat.astype('<f4',copy=False).tobytes(); return base64.b64encode(zlib.compress(raw,9)).decode('ascii'),hashlib.sha256(raw).hexdigest()

def unpack_obs(text:str,expected_sha:str)->tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray]:
    raw=zlib.decompress(base64.b64decode(text.encode('ascii'),validate=True))
    if hashlib.sha256(raw).hexdigest()!=expected_sha: raise ValueError('observation hash mismatch')
    flat=np.frombuffer(raw,dtype='<f4')
    if flat.size!=OBS_FLOATS: raise ValueError('observation payload size mismatch')
    c=6*4*13; a=25*4*5
    return flat[:c].reshape(6,4,13),flat[c:c+a].reshape(25,4,5),flat[c+a:c+a+2],flat[c+a+2:]

def build_policy(label:str,state:dict[str,torch.Tensor],meta:dict[str,Any],identity_sha:str,device:str)->Policy:
    ckpt={**meta,'model':state}
    return Policy(label=label,path=Path(meta['container_path']),sha256=identity_sha,checkpoint=ckpt,model=init_model(ckpt,device),env_version='v55',obs_version='v55',emulate_raise_cap1_legality=False,device=device)

def load_source_and_pool(path:Path,device:str)->tuple[Policy,dict[int,Policy],dict[str,Any]]:
    if sha256_file(path)!=SOURCE_SHA: raise ValueError('source checkpoint SHA mismatch')
    ckpt=torch.load(path,map_location='cpu',weights_only=False)
    for key,value in {'iteration':31400,'total_hands':515989661,'env_version':'v55','obs_version':'v55','action_space_version':'9slot_v5'}.items():
        if ckpt.get(key)!=value: raise ValueError(f'source identity mismatch {key}')
    meta={'iteration':31400,'total_hands':515989661,'env_version':'v55','obs_version':'v55','action_space_version':'9slot_v5','starting_stack_bb':200.0,'container_path':str(path.resolve()),'version':ckpt.get('version'),'run_id':ckpt.get('run_id')}
    source=build_policy('gate31400_source',ckpt['model'],meta,SOURCE_SHA,device)
    rows={int(row['id']):row for row in ckpt.get('pool_snapshots',[])}
    if list(int(row['id']) for row in ckpt.get('pool_snapshots',[]))!=ACTIVE_POOL_IDS: raise ValueError('active pool IDs/order mismatch')
    pool={}; identities=[]
    for pool_id in ACTIVE_POOL_IDS:
        row=rows[pool_id]; state_sha=state_dict_sha(row['state_dict'])
        if state_sha!=POOL_STATE_SHAS[pool_id]: raise ValueError(f'pool snapshot state hash mismatch {pool_id}')
        smeta={**meta,'iteration':int(row['iteration']),'total_hands':int(row['hands'])}
        pool[pool_id]=build_policy(f'pool_{pool_id}',row['state_dict'],smeta,state_sha,device)
        identities.append({'id':pool_id,'iteration':int(row['iteration']),'hands':int(row['hands']),'selection_loss':float(row['selection_loss']),'state_sha256':state_sha})
    source_state_sha=state_dict_sha(ckpt['model'])
    if source_state_sha!=SOURCE_STATE_SHA: raise ValueError('source model state hash mismatch')
    identity={'source':checkpoint_summary(ckpt)|{'sha256':SOURCE_SHA,'state_sha256':source_state_sha},'pool':identities}
    return source,pool,identity

@torch.no_grad()
def choose(policy:Policy,state,player:int,want_obs:bool=False):
    obs,slot_to_action=observation_for(state,player,policy.obs_version)
    ood=apply_policy_legal_emulation(policy,state,obs['legal_mask'],slot_to_action)
    tensors=[torch.as_tensor(obs[k],dtype=torch.float32,device=policy.device).unsqueeze(0) for k in ('card_info','action_info','extra_info','legal_mask')]
    logits,value=policy.model(*tensors); slot=int(torch.argmax(logits,dim=-1).item())
    action=slot_to_action[slot] if 0<=slot<len(slot_to_action) else None
    if action is None:
        legal=[i for i,item in enumerate(slot_to_action) if item is not None]
        if not legal: raise RuntimeError('no legal action')
        slot=legal[int(torch.argmax(logits[0,legal]).item())]; action=slot_to_action[slot]
    return slot,action,ood,(obs if want_obs else None),float(value.item())

def play_trace(env,deck,source:Policy,opponent:Policy,source_seat:int)->dict[str,Any]:
    state=make_fixed_state(env,deck); trace=[]; source_ood=source_decisions=opponent_ood=opponent_decisions=0
    while not state.is_terminal():
        player=int(state.current_player); is_source=player==source_seat; policy=source if is_source else opponent
        slot,action,ood,obs,value=choose(policy,state,player,want_obs=is_source)
        if is_source:
            packed,obs_sha=pack_obs(obs); trace.append({'packed_obs_zlib_b64':packed,'obs_sha256':obs_sha,'source_value_prediction_bb':value,'action_slot':slot})
            source_decisions+=1; source_ood+=int(ood)
        else: opponent_decisions+=1; opponent_ood+=int(ood)
        state=state.apply(action)
    reward=float(state.payoff(source_seat))
    return {'reward_bb':reward,'trace':trace,'source_decisions':source_decisions,'source_ood':source_ood,'opponent_decisions':opponent_decisions,'opponent_ood':opponent_ood}

def make_manifest(source_path:Path,identity:dict[str,Any])->dict[str,Any]:
    rng=random.Random(SEED); deals=[]; stream=hashlib.sha256()
    for index in range(PAIRS):
        deck=shuffled_deck(rng); deck_sha=hashlib.sha256(bytes(deck)).hexdigest(); pool_id=ACTIVE_POOL_IDS[index%len(ACTIVE_POOL_IDS)]
        deal_id=f'h1cal-{SEED}-{index:05d}-{deck_sha[:16]}'
        deals.append({'index':index,'deal_id':deal_id,'deck_sha256':deck_sha,'opponent_pool_id':pool_id}); stream.update(bytes(deck))
    payload={'schema_version':MANIFEST_SCHEMA,'design_id':DESIGN_ID,'created_at':utc_now(),'preregistration_sha256':PREREG_SHA,'source_checkpoint_path':str(source_path.resolve()),'source_checkpoint_sha256':SOURCE_SHA,'pairs':PAIRS,'hands':PAIRS*2,'seed':SEED,'seat_order':[0,1],'starting_stack_bb':STACK,'env_version':'v55','obs_version':'v55','action_space_version':'9slot_v5','policy_mode':'greedy_argmax_both_sides','gamma':GAMMA,'target_units':'discounted_terminal_hero_return_div200','whole_deal_cluster':True,'training_use':'FORBIDDEN_HOLDOUT_ONLY','active_pool_ids':ACTIVE_POOL_IDS,'identities':identity,'deal_stream_sha256':stream.hexdigest(),'deals':deals,'tooling':{'generator_sha256':sha256_file(Path(__file__))}}
    payload['manifest_payload_sha256']=payload_sha(payload,'manifest_payload_sha256'); return payload

def generate(source_path:Path,out_dir:Path,device:str)->dict[str,Any]:
    if out_dir.exists() and any(out_dir.iterdir()): raise FileExistsError('H1-CAL output directory is not empty')
    out_dir.mkdir(parents=True,exist_ok=True); source,pool,identity=load_source_and_pool(source_path,device); manifest=make_manifest(source_path,identity)
    manifest_path=out_dir/'manifest.json'; hands_path=out_dir/'hands.jsonl'; decisions_path=out_dir/'decisions.jsonl'; summary_path=out_dir/'summary.json'
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    env=HUNLEnvironmentV55(starting_stack=STACK); rng=random.Random(SEED); total_rows=source_ood=source_decisions=opponent_ood=opponent_decisions=0; started=time.monotonic()
    with decisions_path.open('x',encoding='utf-8',newline='\n') as output, hands_path.open('x',encoding='utf-8',newline='\n') as hand_output:
        for expected in manifest['deals']:
            deck=shuffled_deck(rng); deck_sha=hashlib.sha256(bytes(deck)).hexdigest()
            if deck_sha!=expected['deck_sha256']: raise RuntimeError('deal replay mismatch')
            opponent=pool[int(expected['opponent_pool_id'])]
            for seat in (0,1):
                hand=play_trace(env,deck,source,opponent,seat); count=len(hand['trace'])
                hand_record={'schema_version':'v5.hybrid.h1.calibration_hand.v1','design_id':DESIGN_ID,'hand_id':f"{expected['deal_id']}-s{seat}",'deal_id':expected['deal_id'],'deal_index':expected['index'],'deck_sha256':deck_sha,'source_seat':seat,'opponent_pool_id':expected['opponent_pool_id'],'terminal_reward_bb':hand['reward_bb'],'source_decisions':count,'source_ood':hand['source_ood'],'opponent_decisions':hand['opponent_decisions'],'opponent_ood':hand['opponent_ood']}
                hand_output.write(json.dumps(hand_record,sort_keys=True,separators=(',',':'))+'\n')
                for index,row in enumerate(hand['trace']):
                    target=(GAMMA**(count-1-index))*hand['reward_bb']/STACK
                    record={'schema_version':ROW_SCHEMA,'design_id':DESIGN_ID,'decision_id':f"{expected['deal_id']}-s{seat}-d{index}",'deal_id':expected['deal_id'],'deal_index':expected['index'],'deck_sha256':deck_sha,'source_seat':seat,'opponent_pool_id':expected['opponent_pool_id'],'decision_index':index,'hero_decisions_in_hand':count,'terminal_reward_bb':hand['reward_bb'],'gamma':GAMMA,'target_normalized':target,'source_value_prediction_normalized':row['source_value_prediction_bb']/STACK,'action_slot':row['action_slot'],'packed_obs_zlib_b64':row['packed_obs_zlib_b64'],'obs_sha256':row['obs_sha256']}
                    output.write(json.dumps(record,sort_keys=True,separators=(',',':'))+'\n'); total_rows+=1
                source_ood+=hand['source_ood']; source_decisions+=hand['source_decisions']; opponent_ood+=hand['opponent_ood']; opponent_decisions+=hand['opponent_decisions']
    summary={'schema_version':SUMMARY_SCHEMA,'checked_at':utc_now(),'design_id':DESIGN_ID,'manifest_payload_sha256':manifest['manifest_payload_sha256'],'pairs':PAIRS,'hands':PAIRS*2,'decision_rows':total_rows,'source_ood_rate':source_ood/max(source_decisions,1),'opponent_ood_rate':opponent_ood/max(opponent_decisions,1),'elapsed_seconds':time.monotonic()-started,'manifest_sha256':sha256_file(manifest_path),'hands_sha256':sha256_file(hands_path),'decisions_sha256':sha256_file(decisions_path),'training_use':'FORBIDDEN_HOLDOUT_ONLY'}
    summary_path.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n',encoding='utf-8'); return summary

def read_rows(path:Path):
    with path.open('r',encoding='utf-8') as handle:
        for line in handle:
            if line.strip(): yield json.loads(line)

def audit_bundle(bundle_dir:Path)->dict[str,Any]:
    errors=[]; manifest_path=bundle_dir/'manifest.json'; hands_path=bundle_dir/'hands.jsonl'; decisions_path=bundle_dir/'decisions.jsonl'; summary_path=bundle_dir/'summary.json'
    try: manifest=json.loads(manifest_path.read_text(encoding='utf-8')); summary=json.loads(summary_path.read_text(encoding='utf-8'))
    except Exception as exc: return {'schema_version':AUDIT_SCHEMA,'status':'FAIL_CLOSED','errors':[f'missing/unreadable bundle: {exc}'],'launch_authority':'NONE'}
    if manifest.get('schema_version')!=MANIFEST_SCHEMA or manifest.get('manifest_payload_sha256')!=payload_sha(manifest,'manifest_payload_sha256'): errors.append('manifest integrity')
    exact={'design_id':DESIGN_ID,'preregistration_sha256':PREREG_SHA,'source_checkpoint_sha256':SOURCE_SHA,'pairs':PAIRS,'hands':PAIRS*2,'seed':SEED,'seat_order':[0,1],'starting_stack_bb':STACK,'env_version':'v55','obs_version':'v55','action_space_version':'9slot_v5','training_use':'FORBIDDEN_HOLDOUT_ONLY'}
    for key,value in exact.items():
        if manifest.get(key)!=value: errors.append(f'manifest exact field {key}')
    identities=manifest.get('identities') if isinstance(manifest.get('identities'),dict) else {}
    source_identity=identities.get('source') if isinstance(identities.get('source'),dict) else {}
    pool_identity=identities.get('pool') if isinstance(identities.get('pool'),list) else []
    if source_identity.get('state_sha256')!=SOURCE_STATE_SHA: errors.append('source model identity')
    if {int(row.get('id')):row.get('state_sha256') for row in pool_identity if isinstance(row,dict)}!=POOL_STATE_SHAS: errors.append('pool model identities')
    deal_rows=manifest.get('deals',[]) if isinstance(manifest.get('deals'),list) else []
    deal_ids=[row.get('deal_id') for row in deal_rows if isinstance(row,dict)]
    if len(deal_rows)!=PAIRS or len(set(deal_ids))!=PAIRS: errors.append('manifest duplicate/partial deals')
    for index,row in enumerate(deal_rows):
        if row.get('index')!=index or row.get('opponent_pool_id')!=ACTIVE_POOL_IDS[index%len(ACTIVE_POOL_IDS)]: errors.append('manifest deal order/opponent assignment'); break
    expected={row['deal_id']:row for row in deal_rows if isinstance(row,dict) and isinstance(row.get('deal_id'),str)}
    hand_records={}
    try:
        for hand in read_rows(hands_path):
            key=(hand.get('deal_id'),int(hand.get('source_seat',-1))); deal=expected.get(hand.get('deal_id'))
            if hand.get('schema_version')!='v5.hybrid.h1.calibration_hand.v1' or key in hand_records or not deal or hand.get('deal_index')!=deal['index'] or hand.get('deck_sha256')!=deal['deck_sha256'] or hand.get('opponent_pool_id')!=deal['opponent_pool_id'] or key[1] not in (0,1):
                errors.append('hand identity/duplicate'); break
            hand_records[key]=hand
    except Exception as exc: errors.append(f'hands unreadable: {exc}')
    expected_hand_keys={(deal_id,seat) for deal_id in expected for seat in (0,1)}
    if set(hand_records)!=expected_hand_keys: errors.append('partial seat-swap hand coverage')
    seen=set(); decision_counts={key:0 for key in expected_hand_keys}; rows=0
    try:
        for row in read_rows(decisions_path):
            rows+=1
            if row.get('schema_version')!=ROW_SCHEMA: errors.append('row schema'); break
            decision_id=row.get('decision_id')
            if decision_id in seen: errors.append('duplicate decision_id'); break
            seen.add(decision_id); deal=expected.get(row.get('deal_id'))
            if not deal or row.get('deal_index')!=deal['index'] or row.get('deck_sha256')!=deal['deck_sha256'] or row.get('opponent_pool_id')!=deal['opponent_pool_id']: errors.append('row deal identity'); break
            hand_key=(row['deal_id'],int(row.get('source_seat',-1)))
            if hand_key not in hand_records: errors.append('decision without hand record'); break
            decision_counts[hand_key]+=1
            try: unpack_obs(row['packed_obs_zlib_b64'],row['obs_sha256'])
            except Exception as exc: errors.append(f'observation payload: {exc}'); break
            recomputed=(GAMMA**(int(row['hero_decisions_in_hand'])-1-int(row['decision_index'])))*float(row['terminal_reward_bb'])/STACK
            if not math.isclose(float(row['target_normalized']),recomputed,rel_tol=0,abs_tol=1e-12): errors.append('target mismatch'); break
            if not -1.0<=float(row['target_normalized'])<=1.0: errors.append('target range'); break
    except Exception as exc: errors.append(f'decisions unreadable: {exc}')
    if any(decision_counts.get(key,0)!=int(hand_records[key].get('source_decisions',-1)) for key in hand_records): errors.append('hand/decision count mismatch')
    if rows!=int(summary.get('decision_rows') or -1): errors.append('decision row count mismatch')
    if summary.get('manifest_sha256')!=sha256_file(manifest_path) or summary.get('hands_sha256')!=sha256_file(hands_path) or summary.get('decisions_sha256')!=sha256_file(decisions_path): errors.append('bundle file hash mismatch')
    if float(summary.get('source_ood_rate',1))>0.15 or float(summary.get('opponent_ood_rate',1))>0.15: errors.append('OOD threshold')
    return {'schema_version':AUDIT_SCHEMA,'checked_at':utc_now(),'status':'PASS_IMMUTABLE_HOLDOUT' if not errors else 'FAIL_CLOSED','errors':errors,'pairs':len(expected),'hands':len(expected)*2,'decision_rows':rows,'manifest_sha256':sha256_file(manifest_path),'hands_sha256':sha256_file(hands_path),'decisions_sha256':sha256_file(decisions_path),'summary_sha256':sha256_file(summary_path),'training_use':'FORBIDDEN_HOLDOUT_ONLY','launch_authority':'NONE','official_hands_authorized':0}

def endpoint_predictions(checkpoint_path:Path,rows:list[dict[str,Any]],device:str,batch_size:int=2048)->dict[str,float]:
    ckpt=torch.load(checkpoint_path,map_location='cpu',weights_only=False); contract=str(ckpt.get('critic_contract') or (ckpt.get('config') or {}).get('critic_contract') or CRITIC_V1)
    model=AlphaHoldemNet(critic_contract=contract,critic_init_seed=int((ckpt.get('config') or {}).get('h1_critic_init_seed',2026071102))).to(device); model(torch.zeros(1,6,4,13,device=device),torch.zeros(1,25,4,5,device=device),torch.zeros(1,2,device=device)); model.load_state_dict(ckpt['model']); model.eval()
    errors={};
    with torch.no_grad():
        for start in range(0,len(rows),batch_size):
            chunk=rows[start:start+batch_size]; decoded=[unpack_obs(r['packed_obs_zlib_b64'],r['obs_sha256']) for r in chunk]
            cards=torch.tensor(np.stack([v[0] for v in decoded]),device=device); actions=torch.tensor(np.stack([v[1] for v in decoded]),device=device); extra=torch.tensor(np.stack([v[2] for v in decoded]),device=device); masks=torch.tensor(np.stack([v[3] for v in decoded]),device=device)
            _,values=model(cards,actions,extra,masks); pred=values.squeeze(-1).cpu().numpy();
            if contract==CRITIC_V1: pred=pred/STACK
            for row,value in zip(chunk,pred): errors.setdefault(row['deal_id'],[]).append((float(value)-float(row['target_normalized']))**2)
    return {deal:float(np.mean(vals)) for deal,vals in errors.items()}

def classify_reduction(control:dict[str,float],treatment:dict[str,float],reps:int=BOOTSTRAP_REPS,seed:int=BOOTSTRAP_SEED)->dict[str,Any]:
    deals=sorted(set(control)&set(treatment));
    if len(deals)!=PAIRS: raise ValueError('endpoint comparison deal coverage mismatch')
    c=np.array([control[d] for d in deals]); t=np.array([treatment[d] for d in deals]); point=1-float(t.mean()/c.mean()); rng=np.random.default_rng(seed); samples=np.empty(reps)
    for index in range(reps):
        chosen=rng.integers(0,len(deals),len(deals)); samples[index]=1-float(t[chosen].mean()/c[chosen].mean())
    lower,upper=np.quantile(samples,[0.025,0.975]);
    if point>=0.15 and lower>=0.10: status='PASS_VALUE_GATE'
    elif upper<0.10 or (float(t.mean()/c.mean())>1.10 and lower>0): status='FAIL_VALUE_GATE'
    else: status='INCONCLUSIVE_VALUE_GATE'
    return {'schema_version':COMPARE_SCHEMA,'status':status,'deal_clusters':len(deals),'control_normalized_mse':float(c.mean()),'treatment_normalized_mse':float(t.mean()),'relative_reduction':point,'bootstrap_repetitions':reps,'bootstrap_seed':seed,'ci95_lower':float(lower),'ci95_upper':float(upper),'launch_authority':'NONE','official_hands_authorized':0}

def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest='mode',required=True)
    g=sub.add_parser('generate'); g.add_argument('--source',required=True); g.add_argument('--out-dir',required=True); g.add_argument('--device',choices=['cpu','cuda'],default='cuda'); g.add_argument('--priority',choices=['below-normal','normal'],default='below-normal'); g.add_argument('--torch-threads',type=int,default=1); g.add_argument('--torch-interop-threads',type=int,default=1)
    a=sub.add_parser('audit'); a.add_argument('--bundle-dir',required=True); a.add_argument('--out-json',required=True)
    c=sub.add_parser('compare'); c.add_argument('--bundle-dir',required=True); c.add_argument('--control',required=True); c.add_argument('--treatment',required=True); c.add_argument('--device',choices=['cpu','cuda'],default='cuda'); c.add_argument('--out-json',required=True)
    args=parser.parse_args()
    if args.mode=='generate':
        execution=configure_runtime(args); device=args.device if args.device=='cpu' or torch.cuda.is_available() else 'cpu'; result=generate(Path(args.source),Path(args.out_dir),device); result['execution']={**execution,'status':'COMPLETED','finished_at':utc_now()}; (Path(args.out_dir)/'summary.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2)); return 0
    if args.mode=='audit':
        result=audit_bundle(Path(args.bundle_dir)); Path(args.out_json).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2)); return 0 if result['status'].startswith('PASS_') else 2
    rows=list(read_rows(Path(args.bundle_dir)/'decisions.jsonl')); device=args.device if args.device=='cpu' or torch.cuda.is_available() else 'cpu'; control=endpoint_predictions(Path(args.control),rows,device); treatment=endpoint_predictions(Path(args.treatment),rows,device); result=classify_reduction(control,treatment); Path(args.out_json).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2)); return 0

if __name__=='__main__': raise SystemExit(main())