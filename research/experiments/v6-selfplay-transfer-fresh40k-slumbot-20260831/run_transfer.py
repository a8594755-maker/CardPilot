"""Fixed two-wave external cohort; no retries, substitutions or score peeking."""
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
TRAIN=ROOT/'research/experiments/v6-selfplay75-transfer-pilot-r4-20260831'
PARITY=ROOT/'research/experiments/v6-selfplay-transfer-deployment-parity-20260831'
READY=ROOT/'research/experiments/v6-source-live-readiness-20260831'
PROTOCOL=ROOT/'research/experiments/v6-paired-transfer-protocol-readiness-20260831'
PRIOR=[READY,ROOT/'research/experiments/v6-source-fresh20k-slumbot-20260831',ROOT/'research/experiments/v6-physical1m-fresh20k-slumbot-20260831']
PROTOCOL_SHA='529903cfd246c1ee9e0f9374e083dc62a91b2d135e083aae88a264cad5047cdd'
PROTOCOL_REVIEW_SHA='8aed7a92db157a43102b400514f07c6d0365ef0fe96c87b5b1c2d1ac005860f9'
READY_SHA='d2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): atomic_json(Path(path),value)
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
def record(cmd): log('--command',subprocess.list2cmdline(['python',*map(str,cmd)]))


helper=PROTOCOL/'execution_code/source_files/research/experiments'/PROTOCOL.name/'pair_protocol.py'
assert sha(helper)==PROTOCOL_SHA
spec=importlib.util.spec_from_file_location('qualified_transfer_protocol',helper)
protocol=importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
ARMS=protocol.ARMS
PLAN=protocol.schedule()


def check_copies(directory,originals=False):
    rows=read(directory/'execution_code/copy_manifest.json')
    for row in rows:
        assert sha(ROOT/row['copy'])==row['sha256']
        if originals: assert sha(ROOT/row['original'])==row['sha256']
    return len(rows)


def prerequisites():
    assert read(TRAIN/'experiment.json')['status']=='COMPLETED'
    reviewed=read(TRAIN/'reviewed_analysis.json')
    assert reviewed['status']=='PASS' and reviewed['decision']=='ADMIT_FIXED_EXTERNAL_TRANSFER_PAIR'
    assert reviewed['internal_strength_selection'] is False and reviewed['evaluation_hands']==122880
    candidates=read(TRAIN/'candidate_manifest.json')
    assert set(candidates)=={'source',*ARMS}
    assert read(PARITY/'experiment.json')['status']=='COMPLETED'
    parity=read(PARITY/'analysis.json')
    assert parity['status']=='PASS' and parity['states_checked']==8404 and parity['model_queries']==16808
    assert parity['network_connection_attempts']==0 and sha(PARITY/'parity.jsonl')==parity['parity_sha256']
    for arm in ARMS:
        model=candidates[arm]
        assert sha(model['path'])==model['sha256']==parity['arms'][arm]['model_sha256']
        assert parity['arms'][arm]['status']=='PASS' and parity['arms'][arm]['states_checked']==4202
        assert sha(PARITY/'frozen'/f'{arm}.pt')==model['sha256']
    assert sha(PROTOCOL/'analysis.json')==PROTOCOL_REVIEW_SHA and sha(helper)==PROTOCOL_SHA
    assert read(PROTOCOL/'analysis.json')['status']=='PASS' and read(PROTOCOL/'analysis.json')['tests_passed']==34
    assert sha(READY/'reviewed_analysis.json')==READY_SHA
    for directory in [TRAIN,PARITY,READY,PROTOCOL]: check_copies(directory)
    for path,expected in read(PARITY/'input_manifest.json')['runtime_sha256'].items(): assert sha(path)==expected
    deps=[TRAIN/'reviewed_analysis.json',TRAIN/'candidate_manifest.json',PARITY/'analysis.json',PARITY/'input_manifest.json',
          PARITY/'parity.jsonl',PROTOCOL/'analysis.json',helper,READY/'reviewed_analysis.json',READY/'loader_check.json']
    for directory in PRIOR:
        assert read(directory/'experiment.json')['status']=='COMPLETED'
        audit_path=directory/'combined_audit.json'
        audit=read(audit_path)
        assert audit['status']=='PASS' and audit['token_chains_disjoint']
        saved=next(v for p,v in read(directory/'experiment.json')['artifact_integrity'].items() if Path(p).resolve()==audit_path.resolve())
        assert sha(audit_path)==saved['sha256']
        deps.extend([audit_path,directory/'reviewed_analysis.json'])
    return dict(models={arm:candidates[arm] for arm in ARMS},dependencies={str(p):sha(p) for p in deps},schedule=PLAN)


def verify():
    current=prerequisites()
    if (BASE/'input_manifest.json').exists(): assert current==read(BASE/'input_manifest.json')
    if (BASE/'execution_code/copy_manifest.json').exists(): check_copies(BASE,True)
    for arm,model in current['models'].items():
        target=BASE/'frozen'/f'{arm}.pt'
        if target.exists(): assert sha(target)==model['sha256']
    return current


def excluded_tokens():
    return {token for directory in PRIOR for row in read(directory/'combined_audit.json')['results'] for token in row['token_sha256']}


def session_dir(item): return BASE/'sessions'/item['arm']/f's{item["index"]:02d}'


def session_command(item):
    assert item in PLAN
    return [str(READY/'execution_code/source_files/scripts/alpha_holdem/play_slumbot_v6_journaled.py'),
        '--model',str(BASE/'frozen'/f'{item["arm"]}.pt'),'--hands','2500','--seed',str(item['policy_seed']),
        '--session-id',item['session_id'],'--out-dir',str(session_dir(item)),'--device','cpu']


def raw_count(path): return Path(path).read_bytes().count(b'\n') if Path(path).exists() else 0
def total_raw(): return sum(raw_count(session_dir(item)/'hands.jsonl') for item in PLAN)


def observe(directory):
    def lines(name):
        path=Path(directory)/name
        return [json.loads(line) for line in path.read_bytes().split(b'\n')[:-1]] if path.exists() else []
    events=lines('journal.jsonl')
    intents={r['request_id'] for r in events if r['event']=='request_intent'}
    responses={r['request_id'] for r in events if r['event']=='request_response'}
    return dict(durable_raw_hands=len(lines('hands.jsonl')),attempted_hands=sum(r['event']=='hand_start' for r in events),
        request_intents=len(intents),responses=len(responses),ambiguous_request_ids=sorted(intents-responses),
        observed_server_terminal_hands=len({r['hand'] for r in events if r['event']=='request_response' and
            isinstance(r.get('response'),dict) and r['response'].get('winnings') is not None}))


def raw_sessions(models):
    groups={arm:[] for arm in ARMS}
    for arm in ARMS:
        for item in [r for r in PLAN if r['arm']==arm]:
            chips=[]
            for index,line in enumerate((session_dir(item)/'hands.jsonl').open(),1):
                assert line.endswith('\n')
                row=json.loads(line)
                assert row['successful_hand']==row['attempted_hand']==index and row['session_id']==item['session_id']
                assert row['policy_seed']==item['policy_seed'] and row['model_sha256']==models[arm]['sha256']
                assert row['strict_policy_execution'] and row['policy_mode']=='sample' and row['policy_temperature']==1
                assert row['terminal_validation']['status']=='PASS' and row['winnings_bb']==row['winnings_chips']/100
                chips.append(row['winnings_chips'])
            if len(chips)!=2500: raise ValueError('Incomplete fixed cohort')
            groups[arm].append(chips)
    return groups


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json','execution_code','frozen','sessions']):
        raise ValueError('No restart/resume/overwrite')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid!=psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ['train_v5.py','play_slumbot.py','play_slumbot_v6.py','play_slumbot_v6_journaled.py','run_probe.py','run_pilot.py','run_baseline.py','v6_mirror_eval.py','run_confirmation.py','run_transfer.py'] for a in p.info['cmdline'] or []):
            raise RuntimeError('Another poker training/evaluation is live')
    assert psutil.cpu_count()>=16 and psutil.virtual_memory().available>=16*2**30
    inputs=verify()
    execution=dict(status='PREPARING',pid=psutil.Process().pid,create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),children=[],waves=[])
    write(BASE/'execution.json',execution)
    write(BASE/'input_manifest.json',inputs)
    paths=['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
    directory=BASE/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write(directory/'copy_manifest.json',copies)
    log('--artifact',BASE/'input_manifest.json',*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]])
    (BASE/'frozen').mkdir()
    for arm,model in inputs['models'].items():
        target=BASE/'frozen'/f'{arm}.pt'
        shutil.copy2(model['path'],target)
        log('--artifact',target)
    children,handles=[],[]
    success=False
    try:
        cmd=['-m','pytest',str(BASE/'test_transfer.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'prerun_tests.xml')
        commands=[session_command(item) for item in PLAN]
        for cmd in commands: record(cmd)
        write(BASE/'session_commands.json',[dict(**item,command=[sys.executable,*cmd]) for item,cmd in zip(PLAN,commands)])
        log('--artifact',BASE/'session_commands.json')
        for wave in range(2):
            verify()
            execution['status']='RUNNING'
            wave_info=dict(wave=wave,started_at=datetime.now(timezone.utc).isoformat(),finished_at=None)
            execution['waves'].append(wave_info)
            current=[]
            for item,cmd in zip(PLAN,commands):
                if item['wave']!=wave: continue
                output=(BASE/f'{item["arm"]}_s{item["index"]:02d}_stdout.log').open('x')
                handles.append(output)
                child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                psutil.Process(child.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
                info=dict(role=item['session_id'],arm=item['arm'],wave=wave,pid=child.pid,create_time=psutil.Process(child.pid).create_time(),command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(info)
                children.append((child,info))
                current.append((child,info))
                write(BASE/'execution.json',execution)
            previous=-1
            while any(child.poll() is None for child,_ in current):
                for child,info in current: info['exit_code']=child.poll()
                count=total_raw()
                if count!=previous:
                    log('--count',f'evaluation_hands={count}','--count',f'slumbot_hands={count}')
                    previous=count
                write(BASE/'execution.json',execution)
                time.sleep(5)
            for child,info in current: info['exit_code']=child.wait()
            wave_info['finished_at']=datetime.now(timezone.utc).isoformat()
            write(BASE/'execution.json',execution)
            if any(info['exit_code']!=0 for _,info in current) or any(raw_count(session_dir(r)/'hands.jsonl')!=2500 for r in PLAN if r['wave']==wave):
                raise RuntimeError('Fixed wave incomplete; no replacements or later wave')
        assert total_raw()==40000
        log('--count','evaluation_hands=40000','--count','slumbot_hands=40000')
        verify()
        execution['status']='AUDITING'
        audits={}
        for arm in ARMS:
            cmd=[str(READY/'execution_code/source_files/scripts/alpha_holdem/audit_slumbot_v6_session.py'),'--model',str(BASE/'frozen'/f'{arm}.pt')]
            for item in PLAN:
                if item['arm']==arm: cmd+=['--session-dir',str(session_dir(item))]
            record(cmd)
            with (BASE/f'{arm}_combined_audit.json').open('x') as output:
                child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                info=dict(role=f'{arm}_audit',pid=child.pid,create_time=psutil.Process(child.pid).create_time(),command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(info)
                write(BASE/'execution.json',execution)
                info['exit_code']=child.wait()
            if info['exit_code']!=0: raise RuntimeError('Full-model session audit failed')
            audits[arm]=read(BASE/f'{arm}_combined_audit.json')
            log('--artifact',BASE/f'{arm}_combined_audit.json')
        cross=protocol.validate_combined_audits(audits,{arm:r['sha256'] for arm,r in inputs['models'].items()},excluded_tokens())
        groups=raw_sessions(inputs['models'])
        for arm in ARMS:
            for chips,audit in zip(groups[arm],audits[arm]['results']): assert sum(chips)==audit['cumulative_chips']
        result=protocol.summarize_pair(groups,evidence_valid=True)
        verify()
        report=dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=0,evaluation_hands=40000,slumbot_hands=40000,
            models=inputs['models'],statistics=result,cross_arm_audit=cross,qualification_admitted=False,
            decision='ADMIT_SEPARATE_FRESH100K' if result['selected_for_separate_fresh100k'] else 'NEITHER_PILOT_POINT_POSITIVE')
        write(BASE/'completed_analysis.json',report)
        log('--artifact',BASE/'completed_analysis.json','--note','Both fixed20k cohorts and frozen-model/journal audits complete; independent final review required. No automatic100k launch.')
        success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        log('--artifact',BASE/'failure.txt')
    finally:
        for child,info in children:
            if child.poll() is None: info['exit_code']=child.wait()
        for handle in handles: handle.close()
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',finished_at=datetime.now(timezone.utc).isoformat())
        write(BASE/'execution.json',execution)
        count=total_raw()
        artifacts=[]
        for item in PLAN:
            for path in [BASE/f'{item["arm"]}_s{item["index"]:02d}_stdout.log',*[session_dir(item)/n for n in ['journal.jsonl','hands.jsonl','summary.json']]]:
                if path.exists(): artifacts+=['--artifact',str(path)]
        log('--artifact',BASE/'execution.json','--count','new_training_hands=0','--count',f'evaluation_hands={count}','--count',f'slumbot_hands={count}',*artifacts)
        if not success:
            observed=[dict(session_id=item['session_id'],**observe(session_dir(item))) for item in PLAN if session_dir(item).exists()]
            write(BASE/'failed_accounting.json',dict(validity='UNPROVEN_OR_INCOMPLETE',durable_raw_hands=count,sessions=observed,strength_statistics_computed=False,qualification_admitted=False))
            log('--artifact',BASE/'failed_accounting.json','--note','Invalid/incomplete cohort preserved. No survivor rescue, retries, sample replacement or strength CI.')
        print(json.dumps(dict(status=execution['status'],durable_raw_hands=count)),flush=True)
    if not success: raise SystemExit(1)


if __name__=='__main__': main()
