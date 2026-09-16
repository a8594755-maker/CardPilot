"""Independent terminal evidence and raw hand/session arithmetic, no gameplay."""
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import run_pilot as run

BASE,ROOT=run.BASE,run.ROOT


def independent_estimate(groups):
    if len(groups)!=8 or any(len(g)!=2500 for g in groups): raise ValueError('Wrong fixed cohort')
    data=[x for g in groups for x in g]
    if any(type(x) is not int or abs(x)>20000 for x in data): raise ValueError('Invalid chip value')
    mean=math.fsum(data)/20000
    se=math.sqrt(math.fsum((x-mean)**2 for x in data)/19999/20000)
    means=[math.fsum(g)/2500 for g in groups]
    group_mean=math.fsum(means)/8
    group_se=math.sqrt(math.fsum((m-group_mean)**2 for m in means)/7/8)
    return dict(bb_per_100=mean,raw_hand_ci95=[mean-1.96*se,mean+1.96*se],raw_hand_se=se,
        session_means_bb_per_100=means,session_se=group_se,
        session_t7_ci95=[group_mean-2.3646242515927853*group_se,group_mean+2.3646242515927853*group_se],
        both_pilot_lower_bounds_positive=mean-1.96*se>0 and group_mean-2.3646242515927853*group_se>0)


def close(a,b):
    assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7),(a,b)


def main():
    import psutil
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('Preserve prior review')
    execution=run.read(BASE/'execution.json')
    def original_process_alive(row):
        try: return abs(psutil.Process(row['pid']).create_time()-row['create_time'])<.001
        except psutil.NoSuchProcess: return False
    assert execution['status']=='COMPLETED_PENDING_REVIEW' and not original_process_alive(execution)
    assert len(execution['children'])==9 and {r['role'] for r in execution['children']}=={f'session{i}' for i in range(1,9)}|{'combined_audit'}
    assert all(r['exit_code']==0 and not original_process_alive(r) for r in execution['children'])
    run.verify()
    writer=run.read(BASE/'completed_analysis.json')
    audit=run.read(BASE/'combined_audit.json')
    assert audit['status']=='PASS' and audit['sessions']==8 and audit['successful_hands']==20000
    assert audit['model_sha256']==run.MODEL_SHA and audit['token_chains_disjoint']
    excluded_tokens=run.excluded_tokens()
    seen=set()
    groups=[]
    observed=[]
    for i,item in enumerate(audit['results'],1):
        directory=BASE/'sessions'/f's{i:02d}'
        summary=run.read(directory/'summary.json')
        assert item['status']=='PASS' and item['successful_hands']==item['target_hands']==item['attempted_hands']==2500
        assert item['session_id']==f'v6_physical1m_fresh20k_20260831_s{i:02d}' and item['policy_seed']==2026100400+i
        assert not item['pending_request_id'] and not item['protocol_failures'] and not item['committed_without_raw']
        assert not item['partial_journal'] and not item['partial_hands']
        tokens=set(item['token_sha256'])
        assert tokens and not (tokens&seen) and not (tokens&excluded_tokens)
        seen.update(tokens)
        assert summary['status']=='COMPLETED' and summary['successful_hands']==2500 and summary['frozen_identity_verified']
        assert summary['model_sha256']==run.MODEL_SHA and summary['policy_mode']=='sample' and summary['policy_temperature']==1
        for path,expected in summary['runtime_sha256'].items(): assert run.sha(path)==expected
        assert run.sha(directory/'journal.jsonl')==summary['journal_sha256']==item['journal_sha256']
        assert run.sha(directory/'hands.jsonl')==summary['hands_sha256']==item['hands_sha256']
        chips=[]
        draws=0
        with (directory/'hands.jsonl').open() as handle:
            for index,line in enumerate(handle,1):
                assert line.endswith('\n')
                row=json.loads(line)
                assert row['successful_hand']==row['attempted_hand']==index and row['session_id']==item['session_id']
                assert row['model_sha256']==run.MODEL_SHA and row['policy_seed']==item['policy_seed']
                assert row['policy_mode']=='sample' and row['policy_temperature']==1 and row['strict_policy_execution']
                assert row['terminal_validation']['status']=='PASS' and row['winnings_chips']==row['terminal_response']['winnings']
                assert row['terminal_response']['session_num_hands']==index
                chips.append(row['winnings_chips'])
                assert row['cumulative_chips']==sum(chips)==row['terminal_response']['session_total']
                draws+=len(row['decisions'])
        assert len(chips)==2500 and draws==item['decision_replays']==item['policy_draws_verified']
        assert sum(chips)==item['cumulative_chips']==summary['cumulative_chips']
        close(sum(chips)/2500,summary['bb_per_100'])
        groups.append(chips)
        observed.append(dict(session_id=item['session_id'],hands=2500,requests=item['request_count'],decision_replays=draws,
                             journal_sha256=item['journal_sha256'],hands_sha256=item['hands_sha256']))
    result=independent_estimate(groups)
    for key in ['bb_per_100','raw_hand_se','session_se']: close(result[key],writer['statistics'][key])
    for key in ['raw_hand_ci95','session_t7_ci95','session_means_bb_per_100']:
        for a,b in zip(result[key],writer['statistics'][key]): close(a,b)
    supports=result['bb_per_100']>0
    both_positive=result['raw_hand_ci95'][0]>0 and result['session_t7_ci95'][0]>0
    assert both_positive==writer['statistics']['both_pilot_lower_bounds_positive']
    assert supports==writer['statistics']['supports_separate_100k_confirmation']
    assert writer['evaluation_hands']==writer['slumbot_hands']==20000 and writer['new_training_hands']==0
    decision='ADMIT_SEPARATE_FRESH100K_CONFIRMATION' if supports else 'PILOT_POINT_NOT_POSITIVE'
    assert writer['decision']==decision
    report=dict(status='PASS',reviewed_at=datetime.now(timezone.utc).isoformat(),decision=decision,
        model_sha256=run.MODEL_SHA,new_training_hands=0,evaluation_hands=20000,slumbot_hands=20000,
        statistics=result,supports_separate_100k_confirmation=supports,qualification_admitted=False,goal_achieved=False,
        probe_hands_pooled=0,old_baseline_hands_pooled=0,excluded_source_and_probe_token_chains_disjoint=True,server_rng_independence_proven=False,
        clients_exited_normally=8,full_model_session_audit_exit=0,sessions=observed,
        confirmation_source_copy_pairs_verified=len(run.read(run.CONFIRM/'execution_code/copy_manifest.json')),client_runtime_source_pairs_verified=len(run.read(run.READY/'execution_code/copy_manifest.json')))
    directory=BASE/'review_code'
    directory.mkdir(exist_ok=False)
    relative=Path(__file__).resolve().relative_to(ROOT).as_posix()
    run.capture_code_provenance(ROOT,directory,[relative])
    target=directory/'source_files'/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/relative,target)
    run.write(directory/'copy_manifest.json',[dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=run.sha(target))])
    run.write(BASE/'reviewed_analysis.json',report)
    text='# Frozen physical1m final fresh20k Slumbot pilot\n\n'
    text+=f'Decision: {decision}. Exactly20,000fresh hands in8complete2500hand sessions.\n\n'
    text+=f'Frozen final: {run.MODEL_SHA}.\n\nbb/100: {result["bb_per_100"]:+.4f}; raw-hand95%CI: {result["raw_hand_ci95"]}; session-t7 95%CI: {result["session_t7_ci95"]}.\n\n'
    text+='All clients exited0. Complete journal/terminal/server-counter/frozen-model replay audit and independent raw arithmetic passed. Token chains are disjoint across all8sessions and the excluded source16hand probe and source20k baseline. No proof of server RNG independence is claimed. No probe,internal,or old-contract hands are pooled.\n\n'
    text+='This20k pilot is not the100k Goal. A positive point only admits a separate fresh100k allocation; either pilot CI may cross zero. No pilot/internal/old samples are pooled into qualification and no policy substitution is allowed.\n'
    (BASE/'result_summary.md').write_text(text)
    run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py',
        *[v for path in [BASE/'reviewed_analysis.json',BASE/'result_summary.md',directory/'source_manifest.json',directory/'code.patch',directory/'copy_manifest.json'] for v in ['--artifact',path]])
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
        '--summary',f'Exactly20k fresh frozen physical1m final hands: {result["bb_per_100"]:+.4f}bb/100; raw95%CI{result["raw_hand_ci95"]}; complete evidence PASS.',
        '--conclusion','Independent raw and session-cluster analysis of one immutable v6 final; positive-point allocation is not significance, and no pilot/probe/old-contract pooling or100k completion.',
        '--decision',decision,'--next-step',
        'Preregister independent fresh100k qualification of this exact final; no pilot, baseline, probe or internal hands pooled.' if supports else
        'Analyze the complete nonpositive external pilot and select the next learned-weight experiment; no extension or checkpoint rescue.',
        '--count','new_training_hands=0','--count','evaluation_hands=20000','--count','slumbot_hands=20000'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__=='__main__': main()
