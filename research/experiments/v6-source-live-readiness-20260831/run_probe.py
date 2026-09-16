"""Fixed two-session live protocol probe; not a strength/qualification test."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
LIVE = ROOT/'research/experiments/v6-diverse-learned-league-pilot-20260831'
OFFLINE = ROOT/'research/experiments/v6-journaled-client-readiness-20260831'
SOURCE_SHA = '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
OFFLINE_SHA = '8d905b413e6417543e727df7edd24846839127caad2ed296a9bbe24791eb29b6'
sys.path.insert(0,str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))


def read(path): return json.loads(Path(path).read_text())


def write(path,value): Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def record(cmd): log('--command',subprocess.list2cmdline(['python',*map(str,cmd)]))


def lines(path):
    path = Path(path)
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_bytes().split(b'\n')[:-1]]


def observe(directory):
    directory = Path(directory)
    events = lines(directory/'journal.jsonl')
    raw = lines(directory/'hands.jsonl')
    intents = {r['request_id'] for r in events if r['event'] == 'request_intent'}
    responses = {r['request_id'] for r in events if r['event'] == 'request_response'}
    return dict(durable_raw_hands=len(raw),attempted_hands=sum(r['event']=='hand_start' for r in events),
                request_intents=len(intents),responses=len(responses),ambiguous_request_ids=sorted(intents-responses),
                observed_server_terminal_hands=len({r['hand'] for r in events if r['event']=='request_response' and
                    isinstance(r.get('response'),dict) and r['response'].get('winnings') is not None}))


def session_command(index):
    assert index in [1,2]
    return [str(BASE/'execution_code/source_files/scripts/alpha_holdem/play_slumbot_v6_journaled.py'),
            '--model',str(BASE/'frozen/source.pt'),'--hands','8','--seed',str(2026092800+index),
            '--session-id',f'v6_source_live_20260831_s{index:02d}','--out-dir',str(BASE/'sessions'/f's{index:02d}'),'--device','cpu']


def check_pairs(path, expected=None):
    rows = read(path)
    if expected is not None: assert len(rows) == expected
    for row in rows: assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original','copy'])
    return len(rows)


def verify():
    assert sha(LIVE/'frozen/anchor0.pt') == SOURCE_SHA
    assert sha(OFFLINE/'attempt01/analysis.json') == OFFLINE_SHA
    check_pairs(LIVE/'execution_code/copy_manifest.json',77)
    check_pairs(OFFLINE/'attempt01/execution_code/copy_manifest.json',76)
    for row in read(LIVE/'candidate_manifest.json').values(): assert sha(row['path']) == row['sha256']
    if (BASE/'frozen/source.pt').exists(): assert sha(BASE/'frozen/source.pt') == SOURCE_SHA
    if (BASE/'execution_code/copy_manifest.json').exists(): check_pairs(BASE/'execution_code/copy_manifest.json')


def offline_load_check():
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    snapshot = BASE/'execution_code/source_files/scripts'
    sys.path.insert(0,str(snapshot))
    from alpha_holdem.play_slumbot_v6_journaled import runtime_hashes
    from alpha_holdem.execution_v6 import load_policy
    model,_,identity = load_policy(BASE/'frozen/source.pt','cpu')
    assert identity == SOURCE_SHA and not model.training
    runtime = runtime_hashes()
    assert runtime and all(Path(p).is_relative_to(snapshot) and sha(p)==h for p,h in runtime.items())
    output = BASE/'loader_check.json'
    if output.exists(): raise ValueError('Preserve existing loader check')
    write(output,dict(status='PASS',model_sha256=identity,runtime_sha256=runtime,network_requests=0,executed_hands=0))
    print(json.dumps(dict(status='PASS',runtime_files=len(runtime),network_requests=0,executed_hands=0)))


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json','execution_code','frozen','sessions']):
        raise ValueError('Preserve existing probe; no automatic retry')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
                Path(a).name in ['train_v5.py','play_slumbot.py','play_slumbot_v6.py','play_slumbot_v6_journaled.py','run_probe.py']
                for a in p.info['cmdline'] or []): raise RuntimeError('Active training/external client or duplicate probe')
    assert read(OFFLINE/'attempt01/analysis.json')['status']=='PASS'
    verify()
    execution = dict(status='RUNNING',pid=psutil.Process().pid,started_at=datetime.now(timezone.utc).isoformat(),children=[])
    write(BASE/'execution.json',execution)
    directory = BASE/'execution_code'
    directory.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__','game_state','hand_eval']]
    paths += ['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write(directory/'copy_manifest.json',copies)
    log(*[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/name]])
    (BASE/'frozen').mkdir()
    shutil.copy2(LIVE/'frozen/anchor0.pt',BASE/'frozen/source.pt')
    log('--artifact',BASE/'frozen/source.pt')
    valid, observed = 0, []
    passed=False
    try:
        cmd=['-m','pytest',str(BASE/'test_probe.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'prerun_tests.xml')
        cmd=[str(BASE/'run_probe.py'),'--offline-load-check']
        record(cmd)
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        assert read(BASE/'loader_check.json')['status']=='PASS'
        log('--artifact',BASE/'loader_check.json')
        for index in [1,2]:
            verify()
            cmd=session_command(index)
            record(cmd)
            out=BASE/'sessions'/f's{index:02d}'
            with (BASE/f's{index:02d}_stdout.log').open('x') as output:
                child=subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
                info=dict(role=f'session{index}',pid=child.pid,command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(info)
                write(BASE/'execution.json',execution)
                previous=-1
                while child.poll() is None:
                    current=sum(observe(BASE/'sessions'/f's{i:02d}')['durable_raw_hands'] for i in range(1,index+1))
                    if current != previous:
                        valid,previous=current,current
                        log('--count',f'evaluation_hands={valid}','--count',f'slumbot_hands={valid}')
                    time.sleep(2)
                info['exit_code']=child.wait()
            write(BASE/'execution.json',execution)
            obs=observe(out)
            observed.append(dict(session=index,**obs))
            valid=sum(r['durable_raw_hands'] for r in observed)
            log('--count',f'evaluation_hands={valid}','--count',f'slumbot_hands={valid}',
                '--artifact',BASE/f's{index:02d}_stdout.log',*[v for n in ['journal.jsonl','hands.jsonl','summary.json'] if (out/n).exists() for v in ['--artifact',out/n]])
            cmd=['scripts/alpha_holdem/audit_slumbot_v6_session.py','--session-dir',str(out),'--model',str(BASE/'frozen/source.pt')]
            record(cmd)
            with (BASE/f's{index:02d}_audit_stdout.log').open('x') as output:
                audit_result=subprocess.run([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
            log('--artifact',BASE/f's{index:02d}_audit_stdout.log')
            if info['exit_code'] != 0 or audit_result.returncode != 0:
                raise RuntimeError('Live protocol/session evidence failed; no further session')
            audit=read(BASE/f's{index:02d}_audit_stdout.log')
            assert audit['status']=='PASS' and audit['successful_hands']==8 and obs['durable_raw_hands']==8
            assert not obs['ambiguous_request_ids']
            verify()
            print(json.dumps(dict(session=index,status='PASS',hands=8,requests=audit['request_count'],decision_replays=audit['decision_replays'])),flush=True)
        cmd=['scripts/alpha_holdem/audit_slumbot_v6_session.py','--model',str(BASE/'frozen/source.pt')]
        for i in [1,2]: cmd+=['--session-dir',str(BASE/'sessions'/f's{i:02d}')]
        record(cmd)
        with (BASE/'combined_audit.json').open('x') as output:
            subprocess.run([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,check=True)
        combined=read(BASE/'combined_audit.json')
        assert combined['status']=='PASS' and combined['successful_hands']==16 and combined['token_chains_disjoint']
        verify()
        log('--artifact',BASE/'combined_audit.json')
        passed=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        log('--artifact',BASE/'failure.txt')
    finally:
        observed=[dict(session=i,**observe(BASE/'sessions'/f's{i:02d}')) for i in [1,2] if (BASE/'sessions'/f's{i:02d}').exists()]
        valid=sum(r['durable_raw_hands'] for r in observed)
        execution['status']='COMPLETED' if passed else 'FAILED_PRESERVED'
        execution['finished_at']=datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json',execution)
        report=dict(status='PASS' if passed else 'FAILED',decision='OBSERVED_LIVE_PROTOCOL_READY' if passed else 'LIVE_PROTOCOL_READINESS_FAILED',
            new_training_hands=0,evaluation_hands=valid,slumbot_hands=valid,observed_sessions=observed,
            strength_qualified=False,qualification_admitted=False,server_rng_independence_proven=False,
            source_pairs_verified=len(copies),scope='Only the observed fixed16hand source protocol probe; no universal compatibility or strength inference.')
        write(BASE/'analysis.json',report)
        log('--count','new_training_hands=0','--count',f'evaluation_hands={valid}','--count',f'slumbot_hands={valid}',
            '--artifact',BASE/'execution.json','--artifact',BASE/'analysis.json',
            '--note','Fixed live probe terminal; valid durable raw hands counted separately from observed terminal claims/ambiguous requests. No retries, replacements, pooling or strength admission.')
        print(json.dumps(report),flush=True)
    if not passed: raise SystemExit(1)


if __name__=='__main__':
    if sys.argv[1:]==['--offline-load-check']: offline_load_check()
    else: main()
