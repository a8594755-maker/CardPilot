"""Bounded CPU-only protocol qualification, protecting the live training capture."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ACTIVE=ROOT/'research/experiments/v6-selfplay75-transfer-pilot-r4-20260831'
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): atomic_json(Path(path),value)
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def protect():
    rows=read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(rows)==76
    for row in rows:
        assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
    for row in read(ACTIVE/'anchor_manifest.json'):
        assert sha(row['path'])==row['sha256']==sha(row['source'])
    return len(rows)


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution_code','analysis.json','tests.xml']):
        raise ValueError('Preserve prior attempt')
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
    protected=protect()
    report=dict(status='RUNNING',started_at=datetime.now(timezone.utc).isoformat(),pid=psutil.Process().pid,
                new_training_hands=0,evaluation_hands=0,slumbot_hands=0,model_queries=0)
    write(BASE/'analysis.json',report)
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
        cmd=['-m','pytest',str(BASE/'test_protocol.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
        with (BASE/'test_stdout.log').open('x') as output:
            result=subprocess.run([sys.executable,*cmd],cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        log('--artifact',BASE/'tests.xml','--artifact',BASE/'test_stdout.log')
        if result.returncode: raise RuntimeError('Offline tests failed; preserve result')
        suites=ET.parse(BASE/'tests.xml').getroot().findall('testsuite')
        assert suites and all(int(s.get('failures','0'))==int(s.get('errors','0'))==0 for s in suites)
        import scipy
        from pair_protocol import schedule
        write(BASE/'reserved_schedule.json',dict(status='NOT_LAUNCHED',model_identities='PENDING_TRAINING_REVIEW_AND_PARITY',sessions=schedule()))
        assert protect()==protected
        for row in copies: assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
        report.update(status='PASS',tests_passed=sum(int(s.get('tests','0')) for s in suites),
            protected_source_copy_pairs=protected,own_source_copy_pairs=len(copies),scipy_version=scipy.__version__,
            network_connection_attempts=0,external_sessions_launched=0,qualification_admitted=False,goal_achieved=False,
            decision='PAIRED_EXTERNAL_PROTOCOL_OFFLINE_READY',finished_at=datetime.now(timezone.utc).isoformat())
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json','--artifact',BASE/'reserved_schedule.json',
            '--note','Synthetic arithmetic/schedule/audit fixtures only; no model calls, poker hands or network. Active76original/copy pairs and anchors preserved.')
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
            '--summary',f'Offline paired transfer protocol passed{report["tests_passed"]}tests with zero hands/network/model queries; active76pairs preserved.',
            '--conclusion','Balanced16-session scheduling and unpaired raw/session arithmetic qualified offline; not live evidence or a strength result.',
            '--decision',report['decision'],'--next-step','After both training finals and full review, qualify actual-weight deployment parity and freeze a separate external20k-per-arm record.',
            '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
        print(json.dumps(report))
    except BaseException:
        report.update(status='FAILED',error=traceback.format_exc(),finished_at=datetime.now(timezone.utc).isoformat())
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json','--note','Failed offline qualification preserved; no active-training changes or live requests.')
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','FAILED',
            '--summary','Offline paired protocol qualification failed; zero hands and original evidence preserved.',
            '--conclusion','Read analysis before further action; no live qualification.','--decision','OFFLINE_READINESS_FAILED',
            '--next-step','Inspect preserved offline failure without modifying active training.'],cwd=ROOT,check=True)
        raise


if __name__=='__main__': main()
