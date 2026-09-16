"""Eight fixed fresh final-policy sessions; no retries or score-based stopping."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from pilot_stats import summarize

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
READY=ROOT/'research/experiments/v6-source-live-readiness-20260831'
MODEL_SHA='cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b'
READY_SHA='d2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file
CONFIRM=ROOT/'research/experiments/v6-historical-average-assessment-20260831'
PARITY=CONFIRM
REFERENCE=ROOT/'research/experiments/v6-source-fresh20k-slumbot-20260831'
CONFIRM_SHA='58aadf046cbda64689d06e46a9172da938bf3eb45f067fbd932d0757fca9330c'
PARITY_SHA='5427284bb91e77e2c42d32d2bf49d7dbb0791ea6fa3ed18e918963ccf8c8942f'
REFERENCE_SHA='fd94d113dddb6ce2f0d425980b93eba9234078283e34aedcf2b63c72b52a5147'


def sha(path): return sha256_file(Path(path))


def read(path): return json.loads(Path(path).read_text())


def write(path,value): atomic_json(Path(path),value)


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
        '--model',str(BASE/'frozen/final.pt'),'--hands','2500','--seed',str(2026101200+i),
        '--session-id',f'v6_historical_average_fresh20k_20260831_s{i:02d}','--out-dir',str(BASE/'sessions'/f's{i:02d}'),'--device','cpu']


def check_copies(path, originals=False):
    rows=read(path)
    for row in rows:
        assert sha(ROOT/row['copy'])==row['sha256']
        if originals: assert sha(ROOT/row['original'])==row['sha256']
    return len(rows)


def verify():
    assert isinstance(CONFIRM_SHA,str) and len(CONFIRM_SHA)==64 and isinstance(PARITY_SHA,str) and len(PARITY_SHA)==64, 'Assessment digests not frozen; no live launch'
    assert sha(CONFIRM/'reviewed_analysis.json')==CONFIRM_SHA
    confirmation=read(CONFIRM/'reviewed_analysis.json')
    assert confirmation['status']=='PASS' and confirmation['decision']=='ADMIT_SEPARATE_FRESH20K'
    assert confirmation['candidate_sha256']==MODEL_SHA
    assert read(CONFIRM/'experiment.json')['status']=='COMPLETED'
    assert sha(PARITY/'parity_analysis.json')==PARITY_SHA
    parity=read(PARITY/'parity_analysis.json')
    assert parity['status']=='PASS' and parity['model_sha256']==MODEL_SHA
    assert parity['states_checked']==4202 and parity['model_queries']==8404 and parity['network_connection_attempts']==0
    assert sha(PARITY/'parity.jsonl')==parity['parity_sha256']
    assert sha(CONFIRM/'frozen/student.pt')==MODEL_SHA
    assert sha(READY/'reviewed_analysis.json')==READY_SHA
    assert read(READY/'reviewed_analysis.json')['status']=='PASS'
    assert sha(REFERENCE/'reviewed_analysis.json')==REFERENCE_SHA
    assert read(REFERENCE/'reviewed_analysis.json')['status']=='PASS'
    for directory in [CONFIRM,PARITY,READY,REFERENCE]:
        check_copies(directory/'execution_code/copy_manifest.json')
    for path,expected in read(PARITY/'parity_analysis.json')['runtime_sha256'].items(): assert sha(path)==expected
    for directory,audit_path in prior_audits():
        prior_record=read(directory/'experiment.json')
        assert prior_record['status']=='COMPLETED'
        item=next(v for p,v in prior_record['artifact_integrity'].items() if Path(p).resolve()==audit_path.resolve())
        assert sha(audit_path)==item['sha256'] and read(audit_path)['status']=='PASS'
    if (BASE/'frozen/final.pt').exists(): assert sha(BASE/'frozen/final.pt')==MODEL_SHA
    if (BASE/'execution_code/copy_manifest.json').exists(): check_copies(BASE/'execution_code/copy_manifest.json',True)


def prior_audits():
    physical=ROOT/'research/experiments/v6-physical1m-fresh20k-slumbot-20260831'
    transfer=ROOT/'research/experiments/v6-selfplay-transfer-fresh40k-slumbot-20260831'
    return [(d,d/'combined_audit.json') for d in [READY,REFERENCE,physical]]+[
        (transfer,transfer/f'{arm}_combined_audit.json') for arm in ['control25','selfplay75']]


def excluded_tokens():
    return {h for _,path in prior_audits() for r in read(path)['results'] for h in r['token_sha256']}


def observe(directory):
    directory=Path(directory)
    def lines(name):
        path=directory/name
        return [json.loads(line) for line in path.read_bytes().split(b'\n')[:-1]] if path.exists() else []
    events,raw=lines('journal.jsonl'),lines('hands.jsonl')
    intents={r['request_id'] for r in events if r['event']=='request_intent'}
    responses={r['request_id'] for r in events if r['event']=='request_response'}
    return dict(durable_raw_hands=len(raw),attempted_hands=sum(r['event']=='hand_start' for r in events),
                request_intents=len(intents),responses=len(responses),ambiguous_request_ids=sorted(intents-responses),
                observed_server_terminal_hands=len({r['hand'] for r in events if r['event']=='request_response' and
                    isinstance(r.get('response'),dict) and r['response'].get('winnings') is not None}))


def raw_sessions():
    sessions=[]
    for i in range(1,9):
        chips=[]
        with (BASE/'sessions'/f's{i:02d}'/'hands.jsonl').open() as handle:
            for index,line in enumerate(handle,1):
                assert line.endswith('\n')
                row=json.loads(line)
                assert row['successful_hand']==row['attempted_hand']==index
                assert row['session_id']==f'v6_historical_average_fresh20k_20260831_s{i:02d}' and row['policy_seed']==2026101200+i
                assert row['model_sha256']==MODEL_SHA and row['strict_policy_execution']
                assert row['policy_mode']=='sample' and row['policy_temperature']==1
                assert row['terminal_validation']['status']=='PASS' and row['winnings_bb']==row['winnings_chips']/100
                chips.append(row['winnings_chips'])
        if len(chips)!=2500: raise ValueError('Incomplete fixed session')
        sessions.append(chips)
    return sessions


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json','execution_code','frozen','sessions']):
        raise ValueError('Preserve previous pilot; no retry/resume/overwrite')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid!=psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ['train_v5.py','play_slumbot.py','play_slumbot_v6.py','play_slumbot_v6_journaled.py','run_probe.py','run_pilot.py','run_baseline.py','v6_mirror_eval.py','run_confirmation.py','run_distillation.py','run_assessment.py','run_transfer.py']
            for a in p.info['cmdline'] or []): raise RuntimeError('Another training/external client is active')
    assert psutil.cpu_count()>=16 and psutil.virtual_memory().available>=16*2**30
    verify()
    execution=dict(status='PREPARING',pid=psutil.Process().pid,create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),children=[])
    write(BASE/'execution.json',execution)
    directory=BASE/'execution_code'
    directory.mkdir()
    paths=['research/experiment_log.py']
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
        readiness_review_sha256=READY_SHA,checkpoint_sha256=MODEL_SHA,confirmation_review_sha256=CONFIRM_SHA,parity_analysis_sha256=PARITY_SHA,
        prior_audits=[dict(path=str(p),sha256=sha(p)) for _,p in prior_audits()],
        runtime_manifests=[dict(path=str(READY/'execution_code'/n),sha256=sha(READY/'execution_code'/n)) for n in ['source_manifest.json','code.patch','copy_manifest.json']])
    write(BASE/'runtime_origin.json',origin)
    log(*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]],
        '--artifact',BASE/'runtime_origin.json','--artifact',READY/'reviewed_analysis.json',
        *[v for r in origin['runtime_manifests'] for v in ['--artifact',r['path']]])
    (BASE/'frozen').mkdir()
    shutil.copy2(CONFIRM/'frozen/student.pt',BASE/'frozen/final.pt')
    log('--artifact',BASE/'frozen/final.pt')
    children,handles=[],[]
    success=False
    try:
        cmd=['-m','pytest',str(BASE/'test_pilot.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'prerun_tests.xml')
        verify()
        execution['status']='RUNNING'
        commands=[session_command(i) for i in range(1,9)]
        for cmd in commands: record(cmd)
        write(BASE/'session_commands.json',[dict(session=i,command=[sys.executable,*cmd]) for i,cmd in enumerate(commands,1)])
        log('--artifact',BASE/'session_commands.json')
        for i,cmd in enumerate(commands,1):
            output=(BASE/f's{i:02d}_stdout.log').open('x')
            handles.append(output)
            child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            psutil.Process(child.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
            info=dict(role=f'session{i}',pid=child.pid,create_time=psutil.Process(child.pid).create_time(),command=[sys.executable,*cmd],exit_code=None)
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
        cmd=[str(READY/'execution_code/source_files/scripts/alpha_holdem/audit_slumbot_v6_session.py'),'--model',str(BASE/'frozen/final.pt')]
        for i in range(1,9): cmd+=['--session-dir',str(BASE/'sessions'/f's{i:02d}')]
        record(cmd)
        with (BASE/'combined_audit.json').open('x') as output:
            child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
            info=dict(role='combined_audit',pid=child.pid,create_time=psutil.Process(child.pid).create_time(),command=[sys.executable,*cmd],exit_code=None)
            execution['children'].append(info)
            write(BASE/'execution.json',execution)
            info['exit_code']=child.wait()
        if info['exit_code']!=0: raise RuntimeError('Independent combined audit failed')
        combined=read(BASE/'combined_audit.json')
        assert combined['status']=='PASS' and combined['sessions']==8 and combined['successful_hands']==20000
        assert combined['model_sha256']==MODEL_SHA and combined['token_chains_disjoint']
        assert not ({h for r in combined['results'] for h in r['token_sha256']} & excluded_tokens())
        sessions=raw_sessions()
        result=summarize(sessions)
        for i,(chips,audit) in enumerate(zip(sessions,combined['results']),1):
            assert audit['session_id']==f'v6_historical_average_fresh20k_20260831_s{i:02d}' and audit['policy_seed']==2026101200+i
            assert audit['successful_hands']==2500 and audit['cumulative_chips']==sum(chips)
        verify()
        report=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=0,evaluation_hands=20000,slumbot_hands=20000,
            model_sha256=MODEL_SHA,statistics=result,server_rng_independence_proven=False,
            qualification_admitted=False,decision='ADMIT_SEPARATE_FRESH100K_CONFIRMATION' if result['supports_separate_100k_confirmation'] else 'PILOT_POINT_NOT_POSITIVE')
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
            observed=[dict(session=i,**observe(BASE/'sessions'/f's{i:02d}')) for i in range(1,9) if (BASE/'sessions'/f's{i:02d}').exists()]
            write(BASE/'failed_accounting.json',dict(validity='UNPROVEN_OR_INCOMPLETE',durable_raw_hands=count,observed_sessions=observed,
                qualification_admitted=False,strength_statistics_computed=False))
            log('--artifact',BASE/'failed_accounting.json','--note','Fixed baseline invalid/incomplete; observed terminal claims and unresolved requests preserved separately from durable raw counts. No replacements or strength CI.')
        print(json.dumps(dict(status=execution['status'],durable_raw_hands=count)),flush=True)
    if not success: raise SystemExit(1)


if __name__=='__main__': main()
