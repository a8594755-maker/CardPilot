"""Independent raw arithmetic and evidence review; never launches gameplay."""
from datetime import datetime,timezone
import json
import math
import statistics
import subprocess
import sys
from scipy.stats import t,ttest_ind
import run_transfer as run

BASE,ROOT=run.BASE,run.ROOT


def interval_arm(groups):
    if len(groups)!=8 or any(len(g)!=2500 for g in groups): raise ValueError('Wrong fixed arm')
    data=[v for g in groups for v in g]
    if any(type(v) is not int or abs(v)>20000 for v in data): raise ValueError('Invalid chip sample')
    mean=math.fsum(data)/20000
    se=math.sqrt(math.fsum((v-mean)**2 for v in data)/19999/20000)
    means=[math.fsum(g)/2500 for g in groups]
    group_se=math.sqrt(math.fsum((v-mean)**2 for v in means)/7/8)
    z=statistics.NormalDist().inv_cdf(1-.05/6)
    t7,t7a=float(t.ppf(.975,7)),float(t.ppf(1-.05/6,7))
    return dict(bb_per_100=mean,raw_hand_se=se,raw_hand_ci95=[mean-1.96*se,mean+1.96*se],
        raw_hand_ci_adjusted=[mean-z*se,mean+z*se],session_means_bb_per_100=means,session_se=group_se,
        session_t7_ci95=[mean-t7*group_se,mean+t7*group_se],session_t7_ci_adjusted=[mean-t7a*group_se,mean+t7a*group_se])


def contrast(a,b,confidence=.95):
    if len(a)<2 or len(b)<2 or any(not math.isfinite(v) for v in [*a,*b]): raise ValueError('Invalid cohorts')
    difference=math.fsum(a)/len(a)-math.fsum(b)/len(b)
    ma,mb=math.fsum(a)/len(a),math.fsum(b)/len(b)
    va=math.fsum((x-ma)**2 for x in a)/(len(a)-1)/len(a)
    vb=math.fsum((x-mb)**2 for x in b)/(len(b)-1)/len(b)
    se=math.sqrt(va+vb)
    if se:
        test=ttest_ind(a,b,equal_var=False)
        bounds=test.confidence_interval(confidence_level=confidence)
        df,ci=float(test.df),[float(bounds.low),float(bounds.high)]
    else: df,ci=None,[difference,difference]
    return dict(bb_per_100=difference,standard_error=se,degrees_of_freedom=df,ci=ci)


def close(a,b):
    if a is None or b is None: assert a is b
    elif isinstance(a,(list,tuple)):
        assert len(a)==len(b)
        for x,y in zip(a,b): close(x,y)
    else: assert math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7),(a,b)


def alive(row):
    import psutil
    try: return abs(psutil.Process(row['pid']).create_time()-row['create_time'])<.001
    except psutil.NoSuchProcess: return False


def main():
    if sys.argv[1:] or (BASE/'reviewed_analysis.json').exists(): raise ValueError('No repeated review')
    execution=run.read(BASE/'execution.json')
    assert execution['status']=='COMPLETED_PENDING_REVIEW' and not alive(execution)
    expected_roles=[r['session_id'] for r in run.PLAN]+[f'{arm}_audit' for arm in run.ARMS]
    assert [r['role'] for r in execution['children']]==expected_roles
    assert all(r['exit_code']==0 and not alive(r) for r in execution['children'])
    assert [w['wave'] for w in execution['waves']]==[0,1]
    end0=datetime.fromisoformat(execution['waves'][0]['finished_at']).timestamp()
    begin1=datetime.fromisoformat(execution['waves'][1]['started_at']).timestamp()
    assert begin1>=end0 and all(r['create_time']>=end0 for r in execution['children'][8:16])
    for item,child in zip(run.PLAN,execution['children'][:16]):
        assert child['arm']==item['arm'] and child['wave']==item['wave']
        assert child['command']==[sys.executable,*run.session_command(item)]
    inputs=run.verify()
    writer=run.read(BASE/'completed_analysis.json')
    record=run.read(BASE/'experiment.json')
    def recorded_hash(path):
        match=next(v for p,v in record['artifact_integrity'].items() if run.Path(p).resolve()==path.resolve())
        assert run.sha(path)==match['sha256']
    audits={arm:run.read(BASE/f'{arm}_combined_audit.json') for arm in run.ARMS}
    prior,seen=run.excluded_tokens(),set()
    groups={arm:[] for arm in run.ARMS}
    evidence=[]
    for arm in run.ARMS:
        audit=audits[arm]
        recorded_hash(BASE/f'{arm}_combined_audit.json')
        assert audit['status']=='PASS' and audit['sessions']==8 and audit['successful_hands']==20000 and audit['token_chains_disjoint']
        assert audit['model_sha256']==inputs['models'][arm]['sha256'] and len(audit['results'])==8
        registered=[item for item in run.PLAN if item['arm']==arm]
        for item,proof in zip(registered,audit['results']):
            directory=run.session_dir(item)
            summary=run.read(directory/'summary.json')
            assert proof['status']=='PASS' and proof['session_id']==item['session_id'] and proof['policy_seed']==item['policy_seed']
            assert proof['model_sha256']==inputs['models'][arm]['sha256']
            assert proof['successful_hands']==proof['attempted_hands']==proof['target_hands']==2500
            assert not any(proof[k] for k in ['pending_request_id','protocol_failures','committed_without_raw','partial_journal','partial_hands'])
            tokens=set(proof['token_sha256'])
            assert tokens and not tokens&seen and not tokens&prior
            seen.update(tokens)
            assert summary['status']=='COMPLETED' and summary['successful_hands']==2500 and summary['frozen_identity_verified']
            assert summary['model_sha256']==proof['model_sha256'] and summary['policy_mode']=='sample' and summary['policy_temperature']==1
            for path,expected in summary['runtime_sha256'].items(): assert run.sha(path)==expected
            for name,key in [('journal.jsonl','journal_sha256'),('hands.jsonl','hands_sha256')]:
                assert run.sha(directory/name)==summary[key]==proof[key]
                recorded_hash(directory/name)
            chips,draws,cumulative=[],0,0
            with (directory/'hands.jsonl').open() as handle:
                for index,line in enumerate(handle,1):
                    assert line.endswith('\n')
                    row=json.loads(line)
                    assert row['successful_hand']==row['attempted_hand']==index and row['session_id']==item['session_id']
                    assert row['model_sha256']==proof['model_sha256'] and row['policy_seed']==item['policy_seed']
                    assert row['strict_policy_execution'] and row['policy_mode']=='sample' and row['policy_temperature']==1
                    assert row['terminal_validation']['status']=='PASS' and row['winnings_chips']==row['terminal_response']['winnings']
                    assert row['terminal_response']['session_num_hands']==index and row['winnings_bb']==row['winnings_chips']/100
                    chips.append(row['winnings_chips'])
                    cumulative+=row['winnings_chips']
                    assert cumulative==row['cumulative_chips']==row['terminal_response']['session_total']
                    draws+=len(row['decisions'])
            assert len(chips)==2500 and draws==proof['decision_replays']==proof['policy_draws_verified']
            assert cumulative==proof['cumulative_chips']==summary['cumulative_chips']
            close(cumulative/2500,summary['bb_per_100'])
            groups[arm].append(chips)
            evidence.append(dict(arm=arm,session_id=item['session_id'],hands=2500,requests=proof['request_count'],
                decision_replays=draws,journal_sha256=proof['journal_sha256'],hands_sha256=proof['hands_sha256']))
    arms={arm:interval_arm(groups[arm]) for arm in run.ARMS}
    for arm,result in arms.items():
        for key,value in result.items(): close(value,writer['statistics']['arms'][arm][key])
    contrasts={}
    for name,values in [('raw_hand',{arm:[v for g in groups[arm] for v in g] for arm in run.ARMS}),
                        ('session',{arm:arms[arm]['session_means_bb_per_100'] for arm in run.ARMS})]:
        contrasts[name]={}
        for level,confidence in [('ordinary',.95),('adjusted',1-.05/3)]:
            result=contrast(values['selfplay75'],values['control25'],confidence)
            for key,value in result.items(): close(value,writer['statistics']['contrast_selfplay75_minus_control25'][name][level][key])
            contrasts[name][level]=result
    positive=[arm for arm in run.ARMS if arms[arm]['bb_per_100']>0]
    selected=max(positive,key=lambda arm:arms[arm]['bb_per_100']) if positive else None
    assert writer['statistics']['selected_for_separate_fresh100k']==selected
    assert writer['new_training_hands']==0 and writer['evaluation_hands']==writer['slumbot_hands']==40000
    assert writer['statistics']['qualification_hands']==0 and writer['statistics']['goal_achieved'] is False
    decision='ADMIT_SEPARATE_FRESH100K' if selected else 'NEITHER_PILOT_POINT_POSITIVE'
    assert writer['decision']==decision
    run.verify()
    report=dict(status='PASS',decision=decision,reviewed_at=datetime.now(timezone.utc).isoformat(),models=inputs['models'],
        new_training_hands=0,evaluation_hands=40000,slumbot_hands=40000,arms=arms,
        contrast_selfplay75_minus_control25=contrasts,selected_for_separate_fresh100k=selected,
        qualification_hands=0,goal_achieved=False,pilot_hands_pooled_into_qualification=0,
        server_rng_independence_proven=False,cross_arm_and_prior_token_chains_disjoint=True,
        clients_exited_normally=16,full_model_auditors_exited_normally=2,session_evidence=evidence)
    run.write(BASE/'reviewed_analysis.json',report)
    lines=['# Fixed two-arm fresh Slumbot transfer result','',f'Decision: {decision}; separately allocated endpoint: {selected}.',
        '', 'Each frozen arm completed20,000fresh hands,8sessions of2500. All16clients and2full-model auditors exited0.',
        '', '| Arm | bb/100 | Raw95%CI | Session95%CI |','|---|---:|---|---|']
    for arm,r in arms.items(): lines.append(f'| {arm} | {r["bb_per_100"]:+.5f} | {r["raw_hand_ci95"]} | {r["session_t7_ci95"]} |')
    lines+=['',f'Unpaired selfplay75-control25 raw95%CI: {contrasts["raw_hand"]["ordinary"]["ci"]}; session95%CI: {contrasts["session"]["ordinary"]["ci"]}.',
        '', 'Family3-adjusted intervals and all identities/hashes are in reviewed_analysis.json. No hand pairing or sample pooling.',
        '', 'Token disjointness does not prove server RNG independence. Session intervals assume independent clusters; balanced waves cannot eliminate shared temporal dependence.',
        '', 'Positive-point selection allocates a separate fresh100k test, not significance/superiority or Goal completion. Both nonpositive endpoints receive no100k qualification.']
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    run.log('--command',f'python research/experiments/{BASE.name}/review_finish.py','--artifact',BASE/'reviewed_analysis.json','--artifact',BASE/'result_summary.md')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
        '--summary',f'Fixed40k transfer completed: control25 {arms["control25"]["bb_per_100"]:+.4f}, selfplay75 {arms["selfplay75"]["bb_per_100"]:+.4f}bb/100; evidence PASS;{decision}.',
        '--conclusion','Both preregistered frozen endpoints tested regardless of internal score; independent raw/session CI and full terminal/model evidence reviewed. Not100k qualification.',
        '--decision',decision,'--next-step',f'Preregister entirely fresh100k qualification of exact {selected} hash without pooling.' if selected else
        'Analyze complete nonpositive transfer evidence and select next learned-weight experiment without extending or rescuing either endpoint.',
        '--count','new_training_hands=0','--count','evaluation_hands=40000','--count','slumbot_hands=40000'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__=='__main__': main()
