"""Isolated candidate validation; no active source/record rewrite."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import candidate

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ACTIVE=ROOT/'research/experiments/v6-physical1m-learning-curve-20260831'
sys.path.insert(0,str(ROOT))
from research.experiment_log import capture_code_provenance, command_audit as legacy, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def protect():
    copies=read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(copies)==76
    for row in copies: assert all(sha(ROOT/row[k])==row['sha256'] for k in ['original','copy'])
    selected=read(ACTIVE/'checkpoint_selection.json')
    assert len(selected)==4
    for row in selected.values(): assert sha(row['path'])==row['sha256']
    return len(copies)


def main():
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution_code','analysis.json']): raise ValueError('No rerun or alternate corpus')
    protect()
    original=read(ACTIVE/'experiment.json')
    corpus=[r['command'] if isinstance(r,dict) else r for r in original['commands']]
    write(BASE/'command_corpus.json',dict(source=str(ACTIVE/'experiment.json'),snapshot_at=datetime.now(timezone.utc).isoformat(),commands=corpus))
    directory=BASE/'execution_code'
    directory.mkdir()
    paths=[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]+['research/experiment_log.py']
    capture_code_provenance(ROOT,directory,paths)
    copies=[]
    for relative in paths:
        target=directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        copies.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write(directory/'copy_manifest.json',copies)
    cmd=['-m','pytest',str(BASE/'test_candidate.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,'--command',subprocess.list2cmdline(['python',*cmd])],cwd=ROOT,check=True)
    subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
    changed=[]
    for index,command in enumerate(corpus):
        old,new=legacy(command),candidate.command_audit(command,legacy)
        if old['exact']!=new['exact']:
            assert not old['exact'] and new['exact'] and old['reasons']==['contains_placeholder']
            assert "assert first['environment_hand_accounting']['completed_hands']<account['completed_hands']" in command
            assert 'assert min(steps)>max(' in command
            changed.append(dict(index=index,command_sha256=__import__('hashlib').sha256(command.encode()).hexdigest(),old=old,new=new))
        else: assert old['exact']==new['exact']
    assert len(changed)==2
    assert all(candidate.command_audit(c,legacy)['exact'] for c in corpus)
    protect()
    for row in copies: assert all(sha(ROOT/row[k])==row['sha256'] for k in ['original','copy'])
    report=dict(status='PASS',completed_at=datetime.now(timezone.utc).isoformat(),corpus_commands=len(corpus),changed_commands=changed,
                production_logger_changed=False,active_record_commands_rewritten=False,protected_source_pairs=76,frozen_checkpoints_verified=4,
                code_payloads_executed=0,new_training_hands=0,evaluation_hands=0,slumbot_hands=0,
                decision='ISOLATED_LITERAL_PYTHON_CLASSIFIER_QUALIFIED',legacy_warning_still_present=True,
                limitation='Narrow literal quoting only; syntactic triage does not establish execution success or safety.')
    write(BASE/'analysis.json',report)
    (BASE/'result_summary.md').write_text('# Isolated command classifier regression\n\n'
        f'Qualified candidate on{len(corpus)}snapshotted actual commands: exactly2known false positives corrected, all others unchanged.\n\n'
        'Production logger and active raw commands were NOT modified. AST payloads were parsed,never executed. '
        'All76active source/copy pairs and4frozen model hashes remain intact. Zero new hands. '
        'Integration must wait for active final review; the legacy audit warning still exists.\n')
    artifacts=[BASE/'command_corpus.json',BASE/'analysis.json',BASE/'result_summary.md',BASE/'tests.xml']
    artifacts += [directory/n for n in ['source_manifest.json','code.patch','copy_manifest.json']]
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
                    *[v for p in artifacts for v in ['--artifact',str(p)]]],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
                    '--summary',f'Isolated AST classifier corrected2known false positives across{len(corpus)}actual commands without modifying active sources.',
                    '--conclusion','Narrow literal Python syntax triage qualified; production logger unchanged and legacy warning retained.',
                    '--decision',report['decision'],'--next-step','After the current matrix final review, consider separately recorded integration preserving original command evidence.',
                    '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
    print(json.dumps({k:v for k,v in report.items() if k!='changed_commands'}))


if __name__=='__main__': main()
