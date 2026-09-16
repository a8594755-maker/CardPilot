"""Both new frozen endpoints, fixed old corpus, zero network and zero new hands."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
from parity_contract import assert_parity,assert_coverage

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ACTIVE=ROOT/'research/experiments/v6-selfplay75-transfer-pilot-r4-20260831'
READY=ROOT/'research/experiments/v6-source-live-readiness-20260831'
CORPUS=ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01'
ARMS=('control25','selfplay75')
INPUT_SHAS={'analysis.json':'23564045b6876f848a6fb3e92b5d32a231dbec556803bdf1cb3cbc180b70557f',
    'states.jsonl':'da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d',
    'trajectories.jsonl':'9f130066b723a42a2745acdf277d1c4a6bae43e0f4a66ccf33ad78c92f46a6d9'}
READY_SHA='d2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
LOADER_SHA='080e33f000c59d1af5cdd6a55511d9f3887e0475895449f1e3b7eb536af9d352'
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): atomic_json(Path(path),value)
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def protect():
    copies=read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(copies)==76
    for row in copies: assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
    candidates=read(ACTIVE/'candidate_manifest.json')
    assert set(candidates)=={'source',*ARMS}
    for arm in ARMS:
        health=read(ACTIVE/'production'/arm/'training_health.json')
        assert health['status']=='PASS' and health['new_training_hands']>=1048576
        assert read(ACTIVE/'production'/arm/'run_manifest.json')['status']=='finished'
        assert read(ACTIVE/'production'/arm/'session_audit.json')['status']=='PASS'
        assert sha(candidates[arm]['path'])==candidates[arm]['sha256']==health['checkpoint_sha256']
        assert sha(ACTIVE/'production'/arm/'latest.pt')==candidates[arm]['sha256']
    assert sha(READY/'reviewed_analysis.json')==READY_SHA and sha(READY/'loader_check.json')==LOADER_SHA
    for path,expected in read(READY/'loader_check.json')['runtime_sha256'].items(): assert sha(path)==expected
    for name,expected in INPUT_SHAS.items(): assert sha(CORPUS/name)==expected
    for row in read(ACTIVE/'anchor_manifest.json'): assert sha(row['path'])==sha(row['source'])==row['sha256']
    return copies,{arm:candidates[arm] for arm in ARMS}


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['analysis.json','execution_code','frozen','parity.jsonl']):
        raise ValueError('No overwrite/restart')
    active_copies,models=protect()
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
    started=time.time()
    report=dict(status='RUNNING',pid=psutil.Process().pid,create_time=psutil.Process().create_time(),
        started_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,evaluation_hands=0,slumbot_hands=0,
        states_checked=0,model_queries=0,replayed_validation_trajectories=0,new_unique_decks=0,arms={})
    write(BASE/'analysis.json',report)
    connections=[]
    try:
        directory=BASE/'execution_code'
        directory.mkdir()
        paths=[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
        paths+=['research/experiment_log.py']
        capture_code_provenance(ROOT,directory,paths)
        copies=[]
        for relative in paths:
            target=directory/'source_files'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/relative,target)
            copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
        write(directory/'copy_manifest.json',copies)
        log(*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]])
        cmd=['-m','pytest',str(BASE/'test_parity.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'tests.xml')
        (BASE/'frozen').mkdir()
        for arm,row in models.items():
            target=BASE/'frozen'/f'{arm}.pt'
            shutil.copy2(row['path'],target)
            assert sha(target)==row['sha256']
            log('--artifact',target)
        snapshot=READY/'execution_code/source_files/scripts'
        sys.path.insert(0,str(snapshot))
        def deny(*args,**kwargs):
            connections.append('blocked_connection_attempt')
            raise AssertionError('Offline parity prohibits network')
        with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny), (BASE/'parity.jsonl').open('x') as output:
            import torch
            from alpha_holdem import play_slumbot_v6_journaled as client
            from alpha_holdem import v6_mirror_eval as mirror
            from alpha_holdem.execution_v6 import load_policy
            from alpha_holdem.policy_contract_v6 import observation,from_external,apply_incr
            from alpha_holdem.rules_v6 import ChipState
            from deep_cfr.hand_eval import card_to_str
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
            runtime=client.runtime_hashes()
            expected_runtime={row['original']:row['sha256'] for row in active_copies}
            for path,expected in runtime.items():
                relative='scripts/'+Path(path).relative_to(snapshot).as_posix()
                assert sha(path)==expected==expected_runtime[relative]
            for path,expected in read(READY/'loader_check.json')['runtime_sha256'].items(): assert runtime[path]==expected
            write(BASE/'input_manifest.json',dict(models=models,corpus={str(CORPUS/n):h for n,h in INPUT_SHAS.items()},
                runtime_sha256=runtime,active_copy_manifest_sha256=sha(ACTIVE/'execution_code/copy_manifest.json'),
                ready_review_sha256=READY_SHA,ready_loader_sha256=LOADER_SHA,uniform_seed=20261009))
            log('--artifact',BASE/'input_manifest.json')
            traces=[json.loads(line) for line in (CORPUS/'trajectories.jsonl').read_text().splitlines()]
            states=[json.loads(line) for line in (CORPUS/'states.jsonl').read_text().splitlines()]
            assert len(traces)==512 and len(states)==4202 and len({tuple(r['deck']) for r in traces})==512
            assert [r['hand_index'] for r in traces]==list(range(512)) and [r['state_index'] for r in states]==list(range(4202))
            for arm,row in models.items():
                model,payload,identity=load_policy(BASE/'frozen'/f'{arm}.pt','cpu')
                assert identity==row['sha256'] and not model.training and len(payload['model'])==86
                assert all(torch.isfinite(v).all() for v in payload['model'].values())
                include_position=bool(getattr(model,'requires_position_feature',False)) or any(int(getattr(model,k,0))>0 for k in ['position_adapter_hidden','position_value_adapter_hidden'])
                rng,strata,index=random.Random(20261009),Counter(),0
                for trace in traces:
                    state,prefix=ChipState.new(trace['deck']),''
                    assert trace['states']==len(trace['actions'])
                    for decision_index,action in enumerate(trace['actions']):
                        saved=states[index]
                        assert saved['hand_index']==trace['hand_index'] and saved['decision_index']==decision_index
                        assert saved['behavior_increment']==action and saved['action']==prefix
                        assert saved['seat']==state.actor and saved['street']==state.street
                        assert saved['hole_cards']==[card_to_str(c) for c in state.holes[state.actor]]
                        assert saved['board']==[card_to_str(c) for c in state.board]
                        response=dict(action=prefix,hole_cards=saved['hole_cards'],board=saved['board'],client_pos=state.actor)
                        rebuilt=from_external(prefix,saved['hole_cards'],saved['board'],state.actor)
                        left,left_table=observation(state,include_position=include_position)
                        right,right_table=observation(rebuilt,include_position=include_position)
                        uniform=rng.random()
                        native=mirror.decide(model,state,uniform=uniform,device='cpu')
                        public=client.external_decision(model,response,uniform=uniform,device='cpu')
                        report['model_queries']+=2
                        assert_parity(left,left_table,right,right_table,native,public)
                        strata[f'street{state.street}_seat{state.actor}']+=1
                        output.write(json.dumps(dict(arm=arm,model_sha256=identity,state_index=index,hand_index=trace['hand_index'],
                            decision_index=decision_index,street=state.street,seat=state.actor,uniform=uniform,
                            observation_equal=True,action_table_equal=True,decision_equal=True,decision=public[1]),allow_nan=False)+'\n')
                        old=state.street
                        state=apply_incr(state,action)
                        prefix+=action
                        if state.street>old and not state.terminal: prefix+='/'
                        index+=1
                        report['states_checked']+=1
                    assert state.terminal and state.folded==trace['folded'] and list(state.board)==trace['terminal_board']
                    report['replayed_validation_trajectories']+=1
                    if (trace['hand_index']+1)%64==0:
                        output.flush()
                        write(BASE/'analysis.json',report)
                        print(json.dumps(dict(arm=arm,states_checked=index,total_model_queries=report['model_queries'])),flush=True)
                assert index==4202
                assert_coverage(strata)
                report['arms'][arm]=dict(status='PASS',model_sha256=identity,states_checked=index,model_queries=8404,strata=dict(strata))
                del model,payload
            assert report['states_checked']==8404 and report['model_queries']==16808 and not connections
        assert protect()==(active_copies,models)
        for row in copies: assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
        for path,expected in runtime.items(): assert sha(path)==expected
        for arm,row in models.items(): assert sha(BASE/'frozen'/f'{arm}.pt')==row['sha256']
        report.update(status='PASS',decision='BOTH_FROZEN_ENDPOINTS_DEPLOYMENT_PARITY_PASS',network_connection_attempts=0,
            protected_source_copy_pairs=76,own_source_copy_pairs=len(copies),runtime_files=len(runtime),
            parity_sha256=sha(BASE/'parity.jsonl'),strength_assessed=False,corpus_outcomes_used=False,qualification_admitted=False,
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.time()-started)
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json','--artifact',BASE/'parity.jsonl',
            '--metric','model_queries=16808','--metric','states_checked=8404','--metric','replayed_validation_trajectories=1024')
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
            '--summary','Both frozen self-play-share endpoints passed4202native/public state comparisons each;16808model calls, zero new hands/network.',
            '--conclusion','Exact observation/legal/probability/action parity on fixed old exogenous corpus; not live strength or100k qualification.',
            '--decision',report['decision'],'--next-step','Require completed independent r4 training/evidence review before a separately preregistered balanced20k-per-arm Slumbot cohort.',
            '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
        print(json.dumps(report))
    except BaseException:
        report.update(status='FAILED',error=traceback.format_exc(),network_connection_attempts=len(connections),finished_at=datetime.now(timezone.utc).isoformat())
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json',*[v for name in ['parity.jsonl','input_manifest.json'] if (BASE/name).exists() for v in ['--artifact',BASE/name]])
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','FAILED',
            '--summary','New frozen-endpoint offline parity failed; partial evidence preserved, zero game hands.',
            '--conclusion','Inspect preserved parity error; do not change frozen models or proceed to live testing.',
            '--decision','PARITY_FAILED','--next-step','Diagnose without retrying or modifying active training/evaluation.'],cwd=ROOT,check=True)
        raise


if __name__=='__main__': main()
