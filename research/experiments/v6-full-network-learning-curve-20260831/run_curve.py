"""Fixed v6 learned-weight curve and untouched matrix; no auto retries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback
import psutil
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SMOKE=ROOT/'research/experiments/v6-physical-training-smoke-20260831'
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file
from alpha_holdem.policy_contract_v6 import METADATA, validate_metadata

SOURCE=ROOT/'models/baseline/standard10/latest.pt'
SOURCE_SHA='91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
ANCHOR_SHAS=['944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2',
             'd942236f1272664576daed3eb624cc2ee3647ad952a47eeb0f4a5185b5679e90',
             'c2c8171a3c06e6b2fca2012b4e693246881586c1e2a1831c0d66935713bca577']
HELDOUT=[(ROOT/'research/experiments/weak-source-kl-pilot-20260830/frozen/weak.pt',
          'a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b'),
         (ROOT/'research/experiments/matched-weak-kl-representation-curve-20260830/frozen/full.pt',
          'ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e')]
HELPER_SHA='f85c17f218e7ed188743432393e42ac3ea89b3871d4faa8c9dd48ad073447580'
TARGET=262144
PAIR_COUNT=2048
BONF_Z=2.5758293035489004


def sha(path): return sha256_file(Path(path))


def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True)


def record(command): log('--command',subprocess.list2cmdline(['python',*map(str,command)]))


def training_command():
    path=SMOKE/'run_smoke.py'
    assert sha(path)==HELPER_SHA
    spec=importlib.util.spec_from_file_location('fixed_smoke_command_reference',path)
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.BASE=BASE
    cmd=helper.command()
    for key,value in {'--total-environment-hands':str(TARGET),'--max-runtime-seconds':'6000',
        '--archive-checkpoint-every':'4','--run-id':'v6_full_curve_20260831',
        '--seed':'20260918','--worker-seed-base':'2026091800'}.items():
        cmd[cmd.index(key)+1]=value
    return cmd


def stats(values,z=1.96):
    if len(values)<2: raise ValueError('At least two independent pairs required')
    mean=statistics.mean(values)
    half=z*statistics.stdev(values)/(len(values)**.5)
    return dict(bb_per_100=mean,ci=[mean-half,mean+half])


def admit(contrasts):
    if len(contrasts)!=5: raise ValueError('Exactly five primary contrasts required')
    positive=[x['ci99'][0]>0 for x in contrasts]
    return (all(x['bb_per_100']>0 for x in contrasts) and sum(positive)>=3
            and positive[0] and any(positive[3:5]))


def choose_curve(rows,archives):
    if [r['iteration'] for r in rows]!=list(range(1,len(rows)+1)):
        raise ValueError('Missing metric iteration')
    counts=[r['environment_hand_accounting']['completed_hands'] for r in rows]
    if any(a>=b for a,b in zip([0]+counts,counts+[counts[-1]+1])):
        raise ValueError('Nonmonotonic physical counts')
    scheduled=[r for r in rows if r['iteration']%4==0]
    if {r['iteration'] for r in scheduled}!=set(archives):
        raise ValueError('Scheduled archives incomplete or unexpected')
    return {label:next(r for r in scheduled if r['environment_hand_accounting']['completed_hands']>=threshold)
            for label,threshold in [('mid65',65536),('mid131',131072)]}


def raw_pair_count(path):
    if not path.exists(): return 0
    # A writer may have an unflushed/partial final line: only complete JSON rows
    # ending with newline are evidence. No hand is retried or modified here.
    data=path.read_bytes()
    complete=data[:data.rfind(b'\n')+1] if b'\n' in data else b''
    return len(complete.splitlines())


def verify(copies,anchors=None):
    for item in copies:
        assert all(sha(ROOT/item[key])==item['sha256'] for key in ['original','copy'])
    assert sha(SOURCE)==SOURCE_SHA
    for path,digest in HELDOUT: assert sha(path)==digest
    for item in anchors or []: assert sha(item['path'])==item['sha256']


def main():
    if sys.argv[1:]: raise ValueError('Fixed experiment, no alternate budgets/restarts')
    for p in psutil.process_iter(['pid','name','cmdline']):
        if p.pid!=psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(arg).name in ['train_v5.py','v6_mirror_eval.py','play_slumbot.py','play_slumbot_v6.py','run_curve.py']
            for arg in p.info['cmdline'] or []): raise RuntimeError('Another poker job is active')
    if any((BASE/name).exists() for name in ['production','frozen','execution_code','execution.json']):
        raise ValueError('Existing output: inspect, never overwrite')
    assert json.loads((SMOKE/'reviewed_analysis.json').read_text())['decision']=='V6_TRAINING_PIPELINE_SMOKE_PASSED'
    started=time.time()
    execution=dict(status='RUNNING',pid=psutil.Process().pid,started_at=datetime.now(timezone.utc).isoformat(),children=[])
    def save_execution():
        (BASE/'execution.json').write_text(json.dumps(execution,indent=2)+'\n')
    save_execution()
    paths=[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__','game_state','hand_eval']]
    paths += ['research/experiment_log.py',(SMOKE/'run_smoke.py').relative_to(ROOT).as_posix()]
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.glob('*.py'))]
    paths += [(BASE/'preregistration.md').relative_to(ROOT).as_posix()]
    directory=BASE/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies,indent=2)+'\n')
    verify(copies)
    log(*[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',str(directory/name)]])
    test_cmd=['-m','pytest',str(BASE/'test_curve.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
    record(test_cmd)
    subprocess.run([sys.executable,*test_cmd],cwd=ROOT,check=True)
    log('--artifact',str(BASE/'prerun_tests.xml'))
    frozen=BASE/'frozen'
    frozen.mkdir()
    anchors=[]
    for index,digest in enumerate(ANCHOR_SHAS):
        origin=SMOKE/f'frozen/anchor{index}.pt'
        assert sha(origin)==digest
        target=frozen/f'anchor{index}.pt'
        shutil.copy2(origin,target)
        anchors.append(dict(index=index,path=str(target),sha256=sha(target),source=str(origin),source_sha256=digest,role='training'))
    for index,(origin,digest) in enumerate(HELDOUT,3):
        old=torch.load(origin,map_location='cpu',weights_only=False)
        payload={k:v for k,v in old.items() if k!='optimizer' and not k.startswith(('pool_','ppo_replay_','adaptive_opponent_'))}
        payload.update(METADATA)
        payload.update(artifact_kind='explicit_weight_rebinding_no_training',source_path=str(origin),source_sha256=digest,
            source_total_hands=old.get('total_hands'),source_iteration=old.get('iteration'),total_hands=0,iteration=0,
            environment_hand_accounting=None,run_id=f'v6_curve_heldout{index}_20260831')
        assert all(torch.equal(old['model'][k],payload['model'][k]) for k in old['model'])
        validate_metadata(payload)
        target=frozen/f'anchor{index}.pt'
        torch.save(payload,target)
        anchors.append(dict(index=index,path=str(target),sha256=sha(target),source=str(origin),source_sha256=digest,role='heldout_this_run'))
    (BASE/'anchor_manifest.json').write_text(json.dumps(anchors,indent=2)+'\n')
    log('--artifact',str(BASE/'anchor_manifest.json'),*[v for item in anchors for v in ['--artifact',item['path']]])
    count=0
    try:
        cmd=training_command()
        record(cmd)
        with (BASE/'trainer_stdout.log').open('x') as output:
            child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            info=dict(role='trainer',pid=child.pid,command=[sys.executable,*cmd],exit_code=None)
            execution['children'].append(info)
            save_execution()
            log('--metric',f'trainer_pid={child.pid}')
            seen=-1
            while child.poll() is None:
                path=BASE/'production/run_manifest.json'
                try: manifest=json.loads(path.read_text()) if path.exists() else {}
                except (OSError,json.JSONDecodeError): manifest={}
                fresh=int((manifest.get('environment_hand_accounting') or {}).get('completed_hands',0))
                if fresh>seen:
                    count=fresh
                    log('--count',f'new_training_hands={count}','--metric',f'latest_iteration={manifest.get("iteration",0)}')
                    seen=fresh
                time.sleep(5)
            info['exit_code']=child.wait()
        save_execution()
        log('--artifact',str(BASE/'trainer_stdout.log'),'--metric',f'trainer_exit_code={info["exit_code"]}')
        if info['exit_code']: raise RuntimeError('Trainer terminated nonzero; inspect preserved state')
        run=BASE/'production'
        manifest=json.loads((run/'run_manifest.json').read_text())
        checkpoint=torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        validate_metadata(checkpoint)
        count=checkpoint['environment_hand_accounting']['completed_hands']
        assert count>=TARGET and checkpoint['environment_hand_accounting']['prefix_complete']
        audit_cmd=['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py','--run-dir',str(run),
            '--expected-target-hands','99999999','--expected-target-environment-hands',str(TARGET),
            '--expected-final-iteration',str(checkpoint['iteration']),'--expected-pool-size','3',
            '--expected-archive-every','4','--expected-normalization','global','--out',str(BASE/'session_audit.json')]
        record(audit_cmd)
        subprocess.run([sys.executable,*audit_cmd],cwd=ROOT,check=True)
        metrics=[json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
        import re
        archives={}
        for path in (run/'checkpoints').glob('checkpoint_iter*_hands*.pt'):
            match=re.fullmatch(r'checkpoint_iter(\d+)_hands(\d+)\.pt',path.name)
            assert match and int(match[1]) not in archives
            archives[int(match[1])]=path
        chosen=choose_curve(metrics,archives)
        selection={'source':dict(path=str(frozen/'anchor0.pt'),sha256=sha(frozen/'anchor0.pt'),physical_hands=0)}
        for label,row in chosen.items():
            payload=torch.load(archives[row['iteration']],map_location='cpu',weights_only=False)
            assert payload['environment_hand_accounting']['completed_hands']==row['environment_hand_accounting']['completed_hands']
            target=frozen/f'{label}.pt'
            shutil.copy2(archives[row['iteration']],target)
            selection[label]=dict(path=str(target),sha256=sha(target),iteration=row['iteration'],
                                 physical_hands=payload['environment_hand_accounting']['completed_hands'])
        shutil.copy2(run/'latest.pt',frozen/'final.pt')
        selection['final']=dict(path=str(frozen/'final.pt'),sha256=sha(frozen/'final.pt'),physical_hands=count,iteration=checkpoint['iteration'])
        (BASE/'checkpoint_selection.json').write_text(json.dumps(selection,indent=2)+'\n')
        verify(copies,anchors)
        log('--count',f'new_training_hands={count}','--artifact',str(BASE/'checkpoint_selection.json'),
            '--artifact',str(BASE/'session_audit.json'),*[v for item in selection.values() for v in ['--artifact',item['path']]],
            *[v for name in ['latest.pt','run_manifest.json','h1_training_metrics.jsonl','opponent_assignments.jsonl'] for v in ['--artifact',str(run/name)]],
            '--note','All curve checkpoints frozen by counters before any performance cell. Beginning fixed81920hand matrix; no selection or budget changes permitted.')
        jobs=[]
        for label,item in selection.items():
            for anchor in anchors:
                out=BASE/'matrix'/f'{label}_anchor{anchor["index"]}'
                cmd=['scripts/alpha_holdem/v6_mirror_eval.py','--candidate',item['path'],'--anchor',anchor['path'],
                     '--pairs',str(PAIR_COUNT),'--seed','20260919','--device','cpu','--out-dir',str(out)]
                record(cmd)
                jobs.append((label,anchor['index'],out,cmd))
        def evaluate(job):
            label,index,out,cmd=job
            output_path=BASE/f'{label}_anchor{index}_stdout.log'
            with output_path.open('x') as output:
                process=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                psutil.Process(process.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
                item=dict(role=f'{label}_anchor{index}',pid=process.pid,command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(item)
                item['exit_code']=process.wait()
            return item
        # No worker touches logger/index files; the wrapper alone updates records.
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(evaluate,job) for job in jobs]
            previous=-1
            while not all(f.done() for f in futures):
                total=sum(raw_pair_count(out/'pairs.jsonl')*2 for _,_,out,_ in jobs)
                if total!=previous:
                    log('--count',f'evaluation_hands={total}')
                    previous=total
                save_execution()
                time.sleep(10)
            results=[f.result() for f in futures]
        save_execution()
        assert all(item['exit_code']==0 for item in results),results
        total=sum(raw_pair_count(out/'pairs.jsonl')*2 for _,_,out,_ in jobs)
        assert total==81920
        cells={}
        for label,index,out,_ in jobs:
            result=json.loads((out/'summary.json').read_text())
            assert result['status']=='COMPLETED' and result['evaluation_hands']==4096
            assert result['candidate_sha256']==selection[label]['sha256'] and result['anchor_sha256']==anchors[index]['sha256']
            assert result['pairs_sha256']==sha(out/'pairs.jsonl')
            rows=[json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
            assert [row['pair_index'] for row in rows]==list(range(PAIR_COUNT))
            cells[label,index]=rows
            log('--artifact',str(out/'summary.json'),'--artifact',str(out/'pairs.jsonl'),
                '--artifact',str(BASE/f'{label}_anchor{index}_stdout.log'))
        contrasts=[]
        for index in range(5):
            source_rows=cells['source',index]
            final_rows=cells['final',index]
            assert [r['deck'] for r in source_rows]==[r['deck'] for r in final_rows]
            values=[(sum(b['rewards_bb'])-sum(a['rewards_bb']))*50 for a,b in zip(source_rows,final_rows)]
            s=stats(values)
            contrasts.append(dict(anchor=index,bb_per_100=s['bb_per_100'],ci95=s['ci'],ci99=stats(values,BONF_Z)['ci']))
        assert all(sum(row['rewards_bb'])==0 for row in cells['source',0])
        verify(copies,anchors)
        for item in selection.values(): assert sha(item['path'])==item['sha256']
        summary=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=count,evaluation_hands=81920,slumbot_hands=0,
            primary_contrasts=contrasts,confirmation_gate_pass=admit(contrasts),selection=selection,
            wall_time_seconds=time.time()-started,decision='ADMIT_INDEPENDENT_CONFIRMATION' if admit(contrasts) else 'FINAL_BREADTH_GATE_NOT_PASSED')
        (BASE/'completed_analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
        log('--count',f'new_training_hands={count}','--count','evaluation_hands=81920',
            '--artifact',str(BASE/'completed_analysis.json'),'--note','Fixed training and matrix completed; primary final gate calculated. Independent review required before finish or confirmation.')
        execution['status']='COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status']='NEEDS_REVIEW'
        execution['error']=traceback.format_exc()
        log('--count',f'new_training_hands={count}','--note','Wrapper reached a terminal exception; preserve all output and inspect. No automatic retraining/reevaluation.')
        raise
    finally:
        execution['finished_at']=datetime.now(timezone.utc).isoformat()
        execution['wall_time_seconds']=time.time()-started
        save_execution()
        log('--artifact',str(BASE/'execution.json'))


if __name__=='__main__': main()
