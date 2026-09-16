"""Read-only startup identity check; never evaluates interim returns."""
from datetime import datetime,timezone
from pathlib import Path
import json
import shutil
import sys
import psutil
import run_pilot as run

def main():
    if sys.argv[1:] or (run.BASE/'startup_audit.json').exists():
        raise ValueError('Preserve original startup check')
    execution=run.read(run.BASE/'execution.json')
    assert execution['status']=='RUNNING'
    assert abs(psutil.Process(execution['pid']).create_time()-execution['create_time'])<.001
    assert len(execution['children'])==8
    commands=run.read(run.BASE/'session_commands.json')
    assert len(commands)==8
    run.verify()
    observations=[]
    for i,(child,command) in enumerate(zip(execution['children'],commands),1):
        expected=[sys.executable,*run.session_command(i)]
        assert child['role']==f'session{i}' and child['command']==command['command']==expected
        assert command['session']==i and child['exit_code'] in (None,0)
        if child['exit_code'] is None:
            assert abs(psutil.Process(child['pid']).create_time()-child['create_time'])<.001
        path=run.BASE/'sessions'/f's{i:02d}'/'hands.jsonl'
        with path.open() as handle:
            line=handle.readline()
        assert line.endswith('\n')
        first=json.loads(line)
        assert first['successful_hand']==first['attempted_hand']==1
        assert first['session_id']==f'v6_fictitious_average_phase2_fresh20k_20260831_s{i:02d}'
        assert first['policy_seed']==2026102200+i and first['model_sha256']==run.MODEL_SHA
        assert first['strict_policy_execution'] and first['policy_mode']=='sample' and first['policy_temperature']==1
        observations.append(dict(session_id=first['session_id'],seed=first['policy_seed'],
            pid=child['pid'],complete_raw_lines_at_observation=run.raw_count(path)))
    assert len({r['session_id'] for r in observations})==len({r['seed'] for r in observations})==8
    record=run.read(run.BASE/'experiment.json')
    assert record['status']=='RUNNING' and record['accounting']['new_training_hands']==0
    directory=run.BASE/'startup_code'
    directory.mkdir()
    relative=Path(__file__).resolve().relative_to(run.ROOT).as_posix()
    run.capture_code_provenance(run.ROOT,directory,[relative])
    target=directory/'source_files'/relative
    target.parent.mkdir(parents=True)
    shutil.copy2(run.ROOT/relative,target)
    run.write(directory/'copy_manifest.json',[dict(original=relative,copy=target.relative_to(run.ROOT).as_posix(),sha256=run.sha(target))])
    result=dict(status='PASS',checked_at=datetime.now(timezone.utc).isoformat(),frozen_model_sha256=run.MODEL_SHA,
        sessions=observations,first_raw_identity_checks=8,commands_registered=8,
        own_active_source_copy_pairs=run.check_copies(run.BASE/'execution_code/copy_manifest.json',True),
        qualified_client_source_pairs=run.check_copies(run.READY/'execution_code/copy_manifest.json'),
        excluded_prior_cohort_audits=len(run.prior_audits()),interim_returns_computed=False,
        model_queries=0,new_training_hands=0,new_unique_evaluation_hands=0,network_requests=0,
        scope='Startup identity only. Full journal/model/terminal/token audit remains required after all fixed sessions.')
    run.write(run.BASE/'startup_audit.json',result)
    run.log('--artifact',run.BASE/'startup_audit.json','--artifact',Path(__file__),
        *[v for n in ('source_manifest.json','code.patch','copy_manifest.json') for v in ('--artifact',directory/n)])
    print(json.dumps(result))

if __name__=='__main__': main()

