"""Close the same retained-state qualification with hashes and exact commands."""
import json
from pathlib import Path
import subprocess
import sys
from prepare_candidate import BASE, ROOT, sha


def call(args):
    process = subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if process.returncode:
        raise RuntimeError(process.stdout+process.stderr)


def main():
    record = json.loads((BASE/'experiment.json').read_text())
    assert record['status']=='RUNNING'
    report = json.loads((BASE/'qualification_v2.json').read_text())
    assert sha(BASE/'qualification_v2.json')=='a5f6cfce6bc32535cc4f43231b69f30cd1d7e2ab748da175af4f65f7d88a705c'
    assert report['passed'] and report['new_training_hands']==0 and report['goal_achieved'] is False
    assert all(sha(path)==digest for path,digest in report['input_sha256'].items())
    assert sha(BASE/'protocol_initial.md')=='602235fa41b84f9ba7e2afec396223c35b6c09ce49ad63dacbe9e703d938fbf3'
    for row in report['parents'].values():
        assert sha(row['derived'])==row['derived_sha256'] and row['unstepped_serialization_exact']
    args = ['update',BASE.name]
    for command in [v['argv'] for v in report['actual_cli_checks']] + [[sys.executable,*sys.orig_argv[1:]]]:
        args += ['--command',subprocess.list2cmdline(command)]
    call(args)
    artifacts = [p for p in BASE.iterdir() if p.is_file() and p.name not in {'experiment.json','source_manifest.json','code.patch'}]
    artifacts += [BASE/'candidate/scripts/alpha_holdem'/name for name in ('train_v5.py','network_hybrid_h1.py','preflop_gradient_contract.py')]
    batch,chars = [],0
    for path in artifacts:
        if chars+len(str(path))+16>24000:
            call(['update',BASE.name,*batch]); batch,chars=[],0
        batch += ['--artifact',str(path)]; chars += len(str(path))+16
    if batch:
        call(['update',BASE.name,*batch])
    call(['finish',BASE.name,'--status','COMPLETED',
          '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0','--count','final_qualification_hands=0',
          '--metric','qualified_parents=2','--metric','focused_tests_passed=43','--metric','candidate_regressions_passed=375','--metric','goal_achieved=false',
          '--summary','Both retained original-LR parents passed metadata-only actor-route derivation,64-state per-seed forward parity, street-specific gradients and exact86-state Adam/replay/counter restoration;43 focused plus375 runtime tests passed.',
          '--conclusion','The opt-in route changes preflop actor backward connectivity without changing initial inference, critic routing or retained training state. This qualifies a matched learned-weight experiment, not stronger poker or actual worker resume equivalence.',
          '--decision','Retain production and all failed qualification artifacts; complete this record with zero new environment hands and use both original-LR lineages in one connected-versus-detached training control.',
          '--next-step','Preregister the two-seed geometric pilot, reuse established execution helpers, and verify actual initial GPU optimizer/replay/pool/RNG/counters plus route provenance before admitting further training cells.'])
    audit = BASE/'post_finish_audit.json'
    call(['audit','--since',record['created_at'],'--out-json',str(audit),'--fail-on-warning'])
    call(['update',BASE.name,'--artifact',str(audit)])
    print(json.dumps({'status':'COMPLETED','audit_warnings':json.loads(audit.read_text())['warning_count'],'goal_achieved':False}))


if __name__=='__main__':
    main()
