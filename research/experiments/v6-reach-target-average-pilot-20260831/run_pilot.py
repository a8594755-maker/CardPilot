"""One fixed native-only relabel/validation/SL experiment; no restart or external data."""
from datetime import datetime,timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback
from unittest.mock import patch
import numpy as np
import psutil
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
PARENT=ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
FIDELITY=ROOT/'research/experiments/v6-realization-average-fidelity-20260831'
RUNTIME=PARENT/'execution_code/source_files/scripts'
CORPUS=ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01/states.jsonl'
PARENT_REVIEW='9f76cf2c0ae6109ee366f05839d98d0e578e5a7dce994aae9d58fe8a62674293'
FIDELITY_REVIEW='6c3db8a85270afd70a4c03924a7a4d9b9ca11d704e2b8978ebbefd76dfcd4e12'
RESERVOIR_SHA='5f6be731f0a14a5d6a64f4847bb519fab31ee68ad5183c4476b8db26a07717c6'
INITIALIZER_SHA='a73dd73af04e990bdff9892ba2b3eeebf96ded26ba6d4f099597feb262329d38'
CONTROL_SHA='c60dfc881ff1b97245219b226eabb5f4c00c1a3d421f71681b63097f45bfa3ea'
TEACHER_SHAS=['cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b',
 '58ef62e875ce8ad1ecf518a1a65c8f54ba711b3bc1ea1a3ab3a00ed1e1a3540d',
 '393fb9e119ba73864ee76f6732c468d3e09c1329da3625f167f53de8321eea17']
KEYS=('card_info','action_info','extra_info','legal_mask')
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(RUNTIME))
sys.path.insert(0,str(PARENT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
from alpha_holdem.execution_v6 import load_policy,decide
from alpha_holdem.policy_contract_v6 import observation,from_external
from temporal_average import collect,audit_trace,softmax_legal
from native_relabel import stream_relabel
import fit_average

EXECUTION=None
QUERIES={}

def read(path):return json.loads(Path(path).read_text())
def sha(path):return sha256_file(Path(path))
def write(name,value):atomic_json(BASE/name,value)
def array_digest(array):return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)

def require_parents():
    assert read(PARENT/'experiment.json')['status']==read(FIDELITY/'experiment.json')['status']=='COMPLETED'
    assert sha(PARENT/'reviewed_analysis.json')==PARENT_REVIEW and sha(FIDELITY/'reviewed_analysis.json')==FIDELITY_REVIEW
    assert read(FIDELITY/'reviewed_analysis.json')['decision']=='LARGE_AVERAGING_FIDELITY_GAP'
    assert read(PARENT/'reviewed_analysis.json')['model_sha256']==CONTROL_SHA
    assert sha(PARENT/'reservoir.pt')==RESERVOIR_SHA
    assert sha(PARENT/'temporal_average.py')=='836ad2770bd1ec725c57cf53757c26bb81ea813f72bb506e0ca71759e3c2b0db'
    assert sha(CORPUS)=='da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d'
    for row in read(PARENT/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy'])==sha(ROOT/row['original'])==row['sha256']

def input_manifest():
    require_parents()
    def identity(path,digest):
        assert sha(path)==digest
        return dict(path=str(path),sha256=digest)
    teachers=[identity(PARENT/'teachers'/f'teacher{i:02d}.pt',digest) for i,digest in enumerate(TEACHER_SHAS)]
    dependencies=[PARENT/'training_hands.jsonl',PARENT/'validation_hands.jsonl',PARENT/'reservoir.pt',
        PARENT/'reviewed_analysis.json',FIDELITY/'reviewed_analysis.json',FIDELITY/'mixture.py',
        PARENT/'temporal_average.py',PARENT/'execution_code/copy_manifest.json',CORPUS]
    parent_record=read(PARENT/'experiment.json')
    for path in dependencies[:3]:
        entry=next(v for p,v in parent_record['artifact_integrity'].items() if Path(p).resolve()==path.resolve())
        assert sha(path)==entry['sha256']
    return dict(teachers=teachers,control=identity(PARENT/'latest.pt',CONTROL_SHA),
        initializer=identity(PARENT/'initializer.pt',INITIALIZER_SHA),
        dependencies=[dict(path=str(p),sha256=sha(p)) for p in dependencies],
        training_data_domain='preserved native only',new_training_hands=0,new_native_validation_target=8192,
        validation_seed=2026102401,fit_seed=2026102004,external_data_used_for_training=False)

def capture():
    directory=BASE/'execution_code';directory.mkdir()
    paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write('execution_code/copy_manifest.json',copies)
    log(*[v for name in ('source_manifest.json','code.patch','copy_manifest.json') for v in ('--artifact',directory/name)])
    return copies

def verify(copies,manifest):
    require_parents()
    for row in copies:
        assert sha(ROOT/row['copy'])==sha(ROOT/row['original'])==row['sha256']
    for row in manifest['teachers']+[manifest['initializer'],manifest['control']]+manifest['dependencies']:
        assert sha(row['path'])==row['sha256']

def query(category,fn,n):
    if EXECUTION is None:raise RuntimeError('Queries require an active recorded execution')
    item=QUERIES.setdefault(category,dict(attempted=0,completed=0))
    item['attempted']+=int(n)
    result=fn()
    item['completed']+=int(n)
    return result

@torch.no_grad()
def infer(model,arrays,device,category,batch=512):
    pieces=[]
    model.eval()
    for begin in range(0,len(arrays['legal_mask']),batch):
        stop=min(begin+batch,len(arrays['legal_mask']))
        tensors=[torch.as_tensor(arrays[k][begin:stop],dtype=torch.float32,device=device) for k in KEYS]
        logits=query(category,lambda:model(*tensors)[0],stop-begin)
        pieces.append(softmax_legal(logits.detach().cpu().numpy(),arrays['legal_mask'][begin:stop]))
    return np.concatenate(pieces)

def qualify_one(model,identity,states,label,category):
    assert len(states)==64
    cpu,_,digest=load_policy(identity['path'],'cpu');assert digest==identity['sha256']
    obs=[observation(s)[0] for s in states]
    arrays={k:np.stack([o[k] for o in obs]) for k in KEYS}
    direct=np.asarray([query(category,lambda:decide(cpu,s,uniform=.371)[1]['behavior_probs'],1) for s in states])
    cb=infer(cpu,arrays,'cpu',category,64);gb=infer(model,arrays,'cuda',category,64)
    ce,ge=float(np.abs(cb-direct).max()),float(np.abs(gb-direct).max())
    assert max(ce,ge)<=2e-5
    return dict(label=label,states=64,model_queries=192,cpu_delta=ce,gpu_delta=ge,model_sha256=digest)

def fresh_decks():
    seen=set()
    for path,count in [(PARENT/'training_hands.jsonl',262144),(PARENT/'validation_hands.jsonl',8192),(BASE/'validation_hands.jsonl',8192)]:
        hands=0
        with path.open() as handle:
            for line in handle:
                deck=json.loads(line)['deck'];assert sorted(deck)==list(range(52))
                digest=hashlib.sha256(bytes(deck)).digest()
                assert digest not in seen
                seen.add(digest);hands+=1
        assert hands==count
    result=dict(status='PASS',prior_training_hands=262144,prior_validation_hands=8192,new_validation_hands=8192,
        unique_decks_checked=len(seen),collisions=0,new_training_hands=0)
    write('fresh_deck_audit.json',result)
    return result

def record_progress():
    EXECUTION['query_categories']=copy.deepcopy(QUERIES)
    EXECUTION['completed_model_queries']=sum(v['completed'] for v in QUERIES.values())
    write('execution.json',EXECUTION)

def register_files(paths):
    paths=list(paths)
    for begin in range(0,len(paths),12):
        log(*[v for p in paths[begin:begin+12] for v in ('--artifact',p)])

def failure_accounting(phase):
    path=BASE/'validation_hands.jsonl'
    preserved=path.read_bytes().count(b'\n') if path.exists() else 0
    upper=min(1024,8192-preserved) if phase=='NATIVE_VALIDATION_COLLECTION' else 0
    return dict(preserved_complete_native_validation_lines=preserved,additional_unserialized_terminal_hands_unknown=bool(upper),
        additional_unserialized_terminal_hands_upper_bound=upper,new_training_hands=0,
        exact_actual_totals_claimed=False,automatic_resume_qualified=False,
        model_query_categories=QUERIES)

def main():
    global EXECUTION
    require_parents()
    if sys.argv[1:] or any((BASE/n).exists() for n in ('execution.json','execution_code','training_relabel','validation_hands.jsonl')):
        raise ValueError('No relabel/collection/fit restart or overwrite')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid!=os.getpid() and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ('train_v5.py','run_pilot.py','run_distillation.py','run_diagnostic.py','v6_mirror_eval.py','play_slumbot_v6_journaled.py','review_cached.py','review_finish.py')
            for a in p.info['cmdline'] or []):raise ValueError('Another poker workload active')
    assert torch.cuda.is_available() and psutil.virtual_memory().available>16*2**30
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
    started=time.monotonic()
    EXECUTION=dict(status='PREPARING',pid=os.getpid(),create_time=psutil.Process().create_time(),
        started_at=datetime.now(timezone.utc).isoformat(),command=[sys.executable,*sys.argv],
        new_training_hands=0,new_native_validation_hands=0,network_connection_attempts=0)
    record_progress()
    success=False
    def deny(*args,**kwargs):
        EXECUTION['network_connection_attempts']+=1
        raise RuntimeError('Native-only experiment prohibits network')
    try:
        copies=capture();manifest=input_manifest();write('input_manifest.json',manifest)
        cmd=['-m','pytest',str(BASE/'test_reach_targets.py'),str(BASE/'test_pipeline.py'),str(BASE/'test_review.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        verify(copies,manifest)
        with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny):
            teachers=[load_policy(row['path'],'cuda')[0] for row in manifest['teachers']]
            control=load_policy(manifest['control']['path'],'cuda')[0]
            states=[]
            with CORPUS.open() as handle:
                for _,line in zip(range(64),handle):
                    r=json.loads(line);states.append(from_external(r['action'],r['hole_cards'],r['board'],r['seat']))
            qualification=[qualify_one(model,identity,states,f'teacher{i}','initial_qualification')
                for i,(model,identity) in enumerate(zip(teachers,manifest['teachers']))]
            qualification.append(qualify_one(control,manifest['control'],states,'control','initial_qualification'))
            write('initial_qualification.json',dict(status='PASS',evidence=qualification,model_queries=768))
            reservoir=torch.load(PARENT/'reservoir.pt',map_location='cpu',weights_only=False)
            assert reservoir['seen']==2242056 and len(reservoir['ids'])==262144
            EXECUTION['status']='NATIVE_TRAINING_RELABEL';record_progress()
            def progress_relabel(hands,decisions,retained):
                EXECUTION.update(replayed_old_training_hands=hands,replayed_old_decisions=decisions,retained_targets=retained)
                record_progress()
                log('--count','new_training_hands=0','--count',f'offline_samples={retained}',
                    '--count',f'replayed_training_hands={hands}','--count',f'model_state_queries={EXECUTION["completed_model_queries"]}')
                print(json.dumps(dict(phase='NATIVE_TRAINING_RELABEL',old_hands=hands,retained_targets=retained)),flush=True)
            training,targets,_,_=stream_relabel(PARENT/'training_hands.jsonl',BASE/'training_relabel',262144,2242056,
                lambda arrays:np.asarray([infer(model,arrays,'cuda','training_relabel') for model in teachers]),
                lambda path,value:atomic_json(path,value),sha,progress_relabel,reservoir=reservoir)
            register_files(sorted((BASE/'training_relabel').iterdir()))
            assert QUERIES['training_relabel']['completed']==6726168
            EXECUTION['status']='NATIVE_VALIDATION_COLLECTION';record_progress()
            def progress_validation(hands,decisions):
                EXECUTION['new_native_validation_hands']=hands
                QUERIES['validation_collection']=dict(attempted=decisions,completed=decisions)
                record_progress()
                log('--count','new_training_hands=0','--count',f'evaluation_hands={hands}','--count',f'supervised_validation_hands={hands}')
                print(json.dumps(dict(phase='NATIVE_VALIDATION_COLLECTION',hands=hands)),flush=True)
            collected=collect(teachers,seed=2026102401,hands=8192,out=BASE/'validation_hands.jsonl',progress=progress_validation)
            register_files([BASE/'validation_hands.jsonl'])
            EXECUTION['status']='VALIDATION_AUDIT';record_progress()
            audit=audit_trace(BASE/'validation_hands.jsonl',seed=2026102401,hands=8192,teacher_count=3)
            assert audit['decisions']==collected['decisions']
            write('validation_collection_audit.json',audit)
            fresh_decks()
            EXECUTION['status']='NATIVE_VALIDATION_RELABEL';record_progress()
            def progress_reference(hands,decisions,retained):
                EXECUTION['validation_reference_hands']=hands;record_progress()
            val_summary,_,validation,val_states=stream_relabel(BASE/'validation_hands.jsonl',BASE/'validation_relabel',8192,collected['decisions'],
                lambda arrays:np.asarray([infer(model,arrays,'cuda','validation_relabel') for model in teachers]),
                lambda path,value:atomic_json(path,value),sha,progress_reference,validation=True)
            register_files(sorted((BASE/'validation_relabel').iterdir()))
            control_probabilities=infer(control,validation['arrays'],'cuda','control_validation')
            np.save(BASE/'control_validation_probabilities.npy',control_probabilities)
            verify(copies,manifest)
            del teachers,control;torch.cuda.empty_cache()
            EXECUTION['status']='FIXED_SUPERVISED_FIT';record_progress()
            result=fit_average.fit(sys.modules[__name__],manifest,reservoir,targets,validation,control_probabilities)
            final,_,digest=load_policy(BASE/'latest.pt','cuda')
            assert digest==result['model_sha256']
            qualification=qualify_one(final,dict(path=str(BASE/'latest.pt'),sha256=digest),val_states,'final','final_qualification')
            write('final_qualification.json',dict(status='PASS',**qualification))
            n=collected['decisions']
            expected=dict(initial_qualification=768,training_relabel=6726168,validation_collection=n,
                validation_relabel=3*n,control_validation=n,student_validation=4*n,final_qualification=192)
            assert {k:v['completed'] for k,v in QUERIES.items()}==expected
            assert all(v['attempted']==v['completed'] for v in QUERIES.values())
            assert EXECUTION['new_native_validation_hands']==8192 and EXECUTION['network_connection_attempts']==0
            verify(copies,manifest)
            write('completed_analysis.json',dict(status='COMPLETED_PENDING_REVIEW',fit=result,training_relabel=training,
                validation_relabel=val_summary,query_categories=QUERIES,model_state_queries=sum(expected.values()),
                optimizer_rows_processed=2097152,new_training_hands=0,evaluation_hands=8192,supervised_validation_hands=8192,
                strength_evaluation_hands=0,slumbot_hands=0,qualification_hands=0,goal_achieved=False,external_data_used_for_training=False))
            success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        failed=failure_accounting(EXECUTION['status']);write('failed_accounting.json',failed)
        EXECUTION['new_native_validation_hands']=failed['preserved_complete_native_validation_lines']
        print(traceback.format_exc(),flush=True)
    finally:
        EXECUTION.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-started)
        record_progress()
        for name in ('training_relabel','validation_relabel','checkpoints'):
            if (BASE/name).exists():register_files(sorted((BASE/name).iterdir()))
        register_files(p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','source_manifest.json','code.patch'))
        log('--count','new_training_hands=0','--count',f'evaluation_hands={EXECUTION["new_native_validation_hands"]}',
            '--count',f'supervised_validation_hands={EXECUTION["new_native_validation_hands"]}','--count','slumbot_hands=0',
            '--count',f'model_state_queries={EXECUTION["completed_model_queries"]}')
        print(json.dumps(EXECUTION),flush=True)
    if not success:raise SystemExit(1)

if __name__=='__main__':main()
