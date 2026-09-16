"""Reuse immutable parity predictions, not live poker data or new model calls."""
from collections import defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET
import behavior_stats as stats

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
ACTIVE=ROOT/'research/experiments/v6-selfplay-transfer-fresh40k-slumbot-20260831'
PARITY=ROOT/'research/experiments/v6-selfplay-transfer-deployment-parity-20260831'
ARMS=('control25','selfplay75')
ANALYSIS_SHA='8e584ec8268fdd31e5f639efccaf20804a27e5832ee3f0c1957ab4c5d7370df2'
RAW_SHA='bf5fca7060e852363747341ba207dffd17b7e96d65dba9f20dcd01ab2150b8f0'
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json,capture_code_provenance,sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): atomic_json(Path(path),value)
def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def protect():
    assert sha(PARITY/'analysis.json')==ANALYSIS_SHA and sha(PARITY/'parity.jsonl')==RAW_SHA
    report=read(PARITY/'analysis.json')
    assert report['status']=='PASS' and report['model_queries']==16808 and report['network_connection_attempts']==0
    copies=read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(copies)==5
    for row in copies: assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
    inputs=read(ACTIVE/'input_manifest.json')
    for path,expected in inputs['dependencies'].items(): assert sha(path)==expected
    for arm in ARMS:
        assert sha(ACTIVE/'frozen'/f'{arm}.pt')==inputs['models'][arm]['sha256']==report['arms'][arm]['model_sha256']
    return inputs['models']


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['analysis.json','execution_code','tests.xml']): raise ValueError('Preserve old attempt')
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform=='win32' else 5)
    models=protect()
    report=dict(status='RUNNING',pid=psutil.Process().pid,started_at=datetime.now(timezone.utc).isoformat(),
                new_training_hands=0,evaluation_hands=0,slumbot_hands=0,model_queries=0,network_connection_attempts=0)
    write(BASE/'analysis.json',report)
    try:
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
        log(*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]])
        cmd=['-m','pytest',str(BASE/'test_behavior.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        with (BASE/'test_stdout.log').open('x') as output:
            result=subprocess.run([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        log('--artifact',BASE/'tests.xml','--artifact',BASE/'test_stdout.log')
        if result.returncode: raise RuntimeError('Offline analytic tests failed')
        suites=ET.parse(BASE/'tests.xml').getroot().findall('testsuite')
        assert suites and all(int(s.get('errors','0'))==int(s.get('failures','0'))==0 for s in suites)
        write(BASE/'input_manifest.json',dict(models=models,parity_analysis_sha256=ANALYSIS_SHA,parity_raw_sha256=RAW_SHA,
            live_source_copy_manifest_sha256=sha(ACTIVE/'execution_code/copy_manifest.json'),live_input_manifest_sha256=sha(ACTIVE/'input_manifest.json')))
        raw=[json.loads(line) for line in (PARITY/'parity.jsonl').read_text().splitlines()]
        assert len(raw)==8404
        by_arm={arm:[r for r in raw if r['arm']==arm] for arm in ARMS}
        for arm,rows in by_arm.items():
            assert [r['state_index'] for r in rows]==list(range(4202))
            assert all(r['model_sha256']==models[arm]['sha256'] for r in rows)
        differences=[]
        for control,treatment in zip(by_arm['control25'],by_arm['selfplay75']):
            for key in ['state_index','hand_index','decision_index','street','seat','uniform']: assert control[key]==treatment[key]
            for row in [control,treatment]:
                assert row['observation_equal'] and row['action_table_equal'] and row['decision_equal']
                info=row['decision']
                stats.probability_vector(info['behavior_probs'])
                slot=info['selected_action_slot']
                assert type(slot) is int and 0<=slot<9 and info['behavior_probs'][slot]>0
                assert info['policy_mode']=='sample' and info['temperature']==1
            first,second=control['decision'],treatment['decision']
            differences.append(dict(state_index=control['state_index'],hand_index=control['hand_index'],street=control['street'],seat=control['seat'],
                selected_disagreement=float(first['selected_action_slot']!=second['selected_action_slot']),
                **stats.distances(first['behavior_probs'],second['behavior_probs'])))
        result=stats.aggregate(differences)
        strata=defaultdict(list)
        for row in differences: strata[f'street{row["street"]}_seat{row["seat"]}'].append(row)
        assert set(strata)=={f'street{s}_seat{p}' for s in range(4) for p in range(2)}
        stratum_summaries={name:dict(states=len(rows),tv=statistics.mean(r['tv'] for r in rows),
            js_bits=statistics.mean(r['js_bits'] for r in rows),selected_disagreement=statistics.mean(r['selected_disagreement'] for r in rows),
            fold_delta=statistics.mean(r['fold_delta'] for r in rows),raise_delta=statistics.mean(r['raise_delta'] for r in rows),
            allin_delta=statistics.mean(r['allin_delta'] for r in rows)) for name,rows in strata.items()}
        write(BASE/'state_differences.json',differences)
        write(BASE/'hand_blocks.json',result.pop('blocks'))
        assert protect()==models
        for row in copies: assert sha(ROOT/row['original'])==sha(ROOT/row['copy'])==row['sha256']
        report.update(status='PASS',decision='DESCRIPTIVE_POLICY_DISTANCE_RECORDED',finished_at=datetime.now(timezone.utc).isoformat(),
            tests_passed=sum(int(s.get('tests','0')) for s in suites),models=models,compared_states=4202,reused_policy_state_rows=8404,
            reused_exogenous_hand_blocks=512,statistics=result,strata=stratum_summaries,own_source_copy_pairs=len(copies),
            protected_active_source_copy_pairs=5,live_returns_read=False,qualification_admitted=False,goal_achieved=False,
            state_differences_sha256=sha(BASE/'state_differences.json'),hand_blocks_sha256=sha(BASE/'hand_blocks.json'))
        write(BASE/'analysis.json',report)
        primary=result['hand_weighted']['tv']
        lines=['# Fixed common-state mixture behavior diagnostic','',
            f'Hand-weighted TV: {primary["mean"]:.6f},95%CI {primary["ci95"]};512preserved exogenous hand blocks.',
            '',f'Hand-weighted JS bits: {result["hand_weighted"]["js_bits"]["mean"]:.6f}; common-uniform action disagreement: {result["hand_weighted"]["selected_disagreement"]["mean"]:.6f}.',
            '', 'These distances do not imply stronger poker. The corpus is not candidate occupancy or fresh Slumbot evidence. No live returns read, no models queried, no new hands/network.',
            '', '| Street/seat | States | TV | Fold probability change | Raise probability change | All-in probability change |',
            '|---|---:|---:|---:|---:|---:|']
        for name,row in sorted(stratum_summaries.items()): lines.append(f'| {name} | {row["states"]} | {row["tv"]:.6f} | {row["fold_delta"]:+.6f} | {row["raise_delta"]:+.6f} | {row["allin_delta"]:+.6f} |')
        (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
        log(*[v for name in ['analysis.json','input_manifest.json','state_differences.json','hand_blocks.json','result_summary.md'] for v in ['--artifact',BASE/name]],
            '--note','Completed outcome-blind reuse of preserved parity predictions; no live returns/model calls/new games. Active external cohort unchanged.')
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
            '--summary',f'Preserved512hand-block policy diagnostic: meanTV {primary["mean"]:.6f},CI95{primary["ci95"]};zero new hands/queries/network.',
            '--conclusion','Behavioral distance only, not strength or transfer evidence; both fixed endpoints continue the unchanged external cohort.',
            '--decision',report['decision'],'--next-step','Finish the same live fixed40k cohort and judge learned transfer only from its full audited outcomes.',
            '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
        print(json.dumps({k:report[k] for k in ['status','tests_passed','compared_states','model_queries','network_connection_attempts','statistics','strata']}))
    except BaseException:
        report.update(status='FAILED',error=traceback.format_exc(),finished_at=datetime.now(timezone.utc).isoformat())
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json')
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','FAILED',
            '--summary','Preserved-prediction diagnostic failed without new game hands or model queries.',
            '--conclusion','Inspect preserved error; ongoing fixed external experiment must remain unchanged.',
            '--decision','DIAGNOSTIC_FAILED','--next-step','Review failure while preserving active external cohort.'],cwd=ROOT,check=True)
        raise


if __name__=='__main__': main()
