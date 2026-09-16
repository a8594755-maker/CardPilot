"""Eight fixed fresh source sessions; immutable journaled runtime, no extension."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from baseline_stats import summarize

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
READY=ROOT/'research/experiments/v6-source-live-readiness-20260831'
SOURCE_SHA='944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
READY_SHA='d2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
sys.path.insert(0,str(ROOT))
from research.experiment_log import capture_code_provenance,sha256_file
spec=importlib.util.spec_from_file_location('preserved_live_probe',READY/'run_probe.py')
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def sha(path): return sha256_file(Path(path))


def read(path): return json.loads(Path(path).read_text())


def write(path,value): Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def record(cmd): log('--command',subprocess.list2cmdline(['python',*map(str,cmd)]))


def raw_count(path):
    path=Path(path)
    return path.read_bytes().count(b'\n') if path.exists() else 0


def total_raw(): return sum(raw_count(BASE/'sessions'/f's{i:02d}'/'hands.jsonl') for i in range(1,9))


def session_command(i):
    assert type(i) is int and 1<=i<=8
    return [str(READY/'execution_code/source_files/scripts/alpha_holdem/play_slumbot_v6_journaled.py'),
        '--model',str(BASE/'frozen/source.pt'),'--hands','2500','--seed',str(2026092900+i),
        '--session-id',f'v6_source_fresh20k_20260831_s{i:02d}','--out-dir',str(BASE/'sessions'/f's{i:02d}'),'--device','cpu']


def verify():
    probe.verify()
    assert sha(READY/'reviewed_analysis.json')==READY_SHA
    ready=read(READY/'reviewed_analysis.json')
    assert ready['status']=='PASS' and ready['slumbot_hands']==16 and ready['checkpoint_sha256']==SOURCE_SHA
    assert read(READY/'loader_check.json')['status']=='PASS'
    for path,expected in read(READY/'loader_check.json')['runtime_sha256'].items(): assert sha(path)==expected
    if (BASE/'frozen/source.pt').exists(): assert sha(BASE/'frozen/source.pt')==SOURCE_SHA
    if (BASE/'execution_code/copy_manifest.json').exists(): probe.check_pairs(BASE/'execution_code/copy_manifest.json')


def raw_sessions():
    sessions=[]
    for i in range(1,9):
        chips=[]
        with (BASE/'sessions'/f's{i:02d}'/'hands.jsonl').open() as handle:
            for index,line in enumerate(handle,1):
                assert line.endswith('\n')
                row=json.loads(line)
                assert row['successful_hand']==row['attempted_hand']==index
                assert row['session_id']==f'v6_source_fresh20k_20260831_s{i:02d}' and row['policy_seed']==2026092900+i
                assert row['model_sha256']==SOURCE_SHA and row['strict_policy_execution']
                assert row['policy_mode']=='sample' and row['policy_temperature']==1
                assert row['terminal_validation']['status']=='PASS' and row['winnings_bb']==row['winnings_chips']/100
                chips.append(row['winnings_chips'])
        if len(chips)!=2500: raise ValueError('Incomplete fixed session')
        sessions.append(chips)
    return sessions


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json','execution_code','frozen','sessions']):
        raise ValueError('Preserve previous baseline; no retry/resume/overwrite')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid!=psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ['train_v5.py','play_slumbot.py','play_slumbot_v6.py','play_slumbot_v6_journaled.py','run_probe.py','run_baseline.py']
            for a in p.info['cmdline'] or []): raise RuntimeError('Another training/external client is active')
    assert psutil.cpu_count()>=16 and psutil.virtual_memory().available>=16*2**30
    verify()
    execution=dict(status='PREPARING',pid=psutil.Process().pid,started_at=datetime.now(timezone.utc).isoformat(),children=[])
    write(BASE/'execution.json',execution)
    directory=BASE/'execution_code'
    directory.mkdir()
    paths=['research/experiment_log.py',(READY/'run_probe.py').relative_to(ROOT).as_posix()]
    paths+=[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write(directory/'copy_manifest.json',copies)
    origin=dict(client=str(READY/'execution_code/source_files/scripts/alpha_holdem/play_slumbot_v6_journaled.py'),
        readiness_review_sha256=READY_SHA,checkpoint_sha256=SOURCE_SHA,
        runtime_manifests=[dict(path=str(READY/'execution_code'/n),sha256=sha(READY/'execution_code'/n)) for n in ['source_manifest.json','code.patch','copy_manifest.json']])
    write(BASE/'runtime_origin.json',origin)
    log(*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]],
        '--artifact',BASE/'runtime_origin.json','--artifact',READY/'reviewed_analysis.json',
        *[v for r in origin['runtime_manifests'] for v in ['--artifact',r['path']]])
    (BASE/'frozen').mkdir()
    shutil.copy2(READY/'frozen/source.pt',BASE/'frozen/source.pt')
    log('--artifact',BASE/'frozen/source.pt')
    children,handles=[],[]
    success=False
    try:
        cmd=['-m','pytest',str(BASE/'test_baseline.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'prerun_tests.xml')
        verify()
        execution['status']='RUNNING'
        for i in range(1,9):
            cmd=session_command(i)
            record(cmd)
            output=(BASE/f's{i:02d}_stdout.log').open('x')
            handles.append(output)
            child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            psutil.Process(child.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
            info=dict(role=f'session{i}',pid=child.pid,command=[sys.executable,*cmd],exit_code=None)
            execution['children'].append(info)
            children.append((child,info))
            write(BASE/'execution.json',execution)
        previous=-1
        while any(child.poll() is None for child,_ in children):
            for child,info in children: info['exit_code']=child.poll()
            count=total_raw()
            if count!=previous:
                log('--count',f'evaluation_hands={count}','--count',f'slumbot_hands={count}')
                previous=count
            write(BASE/'execution.json',execution)
            time.sleep(5)
        for child,info in children: info['exit_code']=child.wait()
        for handle in handles: handle.close()
        write(BASE/'execution.json',execution)
        count=total_raw()
        log('--count',f'evaluation_hands={count}','--count',f'slumbot_hands={count}')
        if count!=20000 or any(info['exit_code']!=0 for _,info in children):
            raise RuntimeError('Incomplete/failed fixed baseline; retain all evidence without replacements')
        verify()
        execution['status']='AUDITING'
        cmd=['scripts/alpha_holdem/audit_slumbot_v6_session.py','--model',str(BASE/'frozen/source.pt')]
        for i in range(1,9): cmd+=['--session-dir',str(BASE/'sessions'/f's{i:02d}')]
        record(cmd)
        with (BASE/'combined_audit.json').open('x') as output:
            child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            info=dict(role='combined_audit',pid=child.pid,command=[sys.executable,*cmd],exit_code=None)
            execution['children'].append(info)
            write(BASE/'execution.json',execution)
            info['exit_code']=child.wait()
        if info['exit_code']!=0: raise RuntimeError('Independent combined audit failed')
        combined=read(BASE/'combined_audit.json')
        assert combined['status']=='PASS' and combined['sessions']==8 and combined['successful_hands']==20000
        assert combined['model_sha256']==SOURCE_SHA and combined['token_chains_disjoint']
        sessions=raw_sessions()
        result=summarize(sessions)
        for i,(chips,audit) in enumerate(zip(sessions,combined['results']),1):
            assert audit['session_id']==f'v6_source_fresh20k_20260831_s{i:02d}' and audit['policy_seed']==2026092900+i
            assert audit['successful_hands']==2500 and audit['cumulative_chips']==sum(chips)
        verify()
        report=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=0,evaluation_hands=20000,slumbot_hands=20000,
            model_sha256=SOURCE_SHA,statistics=result,server_rng_independence_proven=False,
            qualification_admitted=False,decision='SUPPORTS_SEPARATE_100K_CONFIRMATION' if result['supports_separate_100k_confirmation'] else 'SOURCE_BASELINE_NOT_POSITIVE_CONFIDENTLY')
        write(BASE/'completed_analysis.json',report)
        log('--artifact',BASE/'combined_audit.json','--artifact',BASE/'completed_analysis.json',
            '--note','All eight fixed sessions complete; combined full model/terminal/session evidence audit passed. Raw20k statistics computed; independent final review required. No automatic extension or policy change.')
        success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        log('--artifact',BASE/'failure.txt')
    finally:
        # Already launched sessions retain their original fixed budget after an
        # orchestration failure. Never substitute, retry or silently abandon them.
        for child,info in children:
            if child.poll() is None: info['exit_code']=child.wait()
        for handle in handles:
            if not handle.closed: handle.close()
        count=total_raw()
        execution['status']='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED'
        execution['finished_at']=datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json',execution)
        artifacts=[]
        for i in range(1,9):
            directory=BASE/'sessions'/f's{i:02d}'
            for path in [BASE/f's{i:02d}_stdout.log',*[directory/n for n in ['journal.jsonl','hands.jsonl','summary.json']]]:
                if path.exists(): artifacts+=['--artifact',str(path)]
        log('--count','new_training_hands=0','--count',f'evaluation_hands={count}','--count',f'slumbot_hands={count}',
            '--artifact',BASE/'execution.json',*artifacts)
        if not success:
            observed=[dict(session=i,**probe.observe(BASE/'sessions'/f's{i:02d}')) for i in range(1,9) if (BASE/'sessions'/f's{i:02d}').exists()]
            write(BASE/'failed_accounting.json',dict(validity='UNPROVEN_OR_INCOMPLETE',durable_raw_hands=count,observed_sessions=observed,
                qualification_admitted=False,strength_statistics_computed=False))
            log('--artifact',BASE/'failed_accounting.json','--note','Fixed baseline invalid/incomplete; observed terminal claims and unresolved requests preserved separately from durable raw counts. No replacements or strength CI.')
        print(json.dumps(dict(status=execution['status'],durable_raw_hands=count)),flush=True)
    if not success: raise SystemExit(1)


if __name__=='__main__': main()
