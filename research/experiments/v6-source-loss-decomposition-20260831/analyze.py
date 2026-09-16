"""Offline descriptive accounting only: no poker engine/model/network imports."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT/'research/experiments/v6-source-fresh20k-slumbot-20260831'
ACTIVE = ROOT/'research/experiments/v6-physical1m-learning-curve-20260831'
SOURCE_REVIEW_SHA = 'fd94d113dddb6ce2f0d425980b93eba9234078283e34aedcf2b63c72b52a5147'
MODEL_SHA = '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, data): Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def categories(row):
    response, terminal = row['terminal_response'], row['terminal_validation']
    seat, chips = response['client_pos'], row['winnings_chips']
    if type(seat) is not int or seat not in (0, 1): raise ValueError('Invalid seat')
    if type(chips) is not int or abs(chips) > 20000: raise ValueError('Invalid chips')
    if terminal['status'] != 'PASS': raise ValueError('Unvalidated terminal')
    if terminal['terminal_kind'] == 'fold':
        if terminal['folded_player'] not in (0, 1): raise ValueError('Invalid folded player')
        kind = 'hero_fold' if terminal['folded_player'] == seat else 'opponent_fold'
    elif terminal['terminal_kind'] == 'showdown': kind = 'showdown'
    else: raise ValueError('Invalid terminal kind')
    n = len(response['board'])
    if n not in (0, 3, 4, 5): raise ValueError('Invalid board length')
    band = next(label for maximum, label in [(0,'0'),(100,'1..100'),(500,'101..500'),(2000,'501..2000'),
                                             (5000,'2001..5000'),(10000,'5001..10000'),(20000,'10001..20000')]
                if abs(chips) <= maximum)
    name = 'BB' if seat == 0 else 'SB'
    return {'seat':name, 'terminal_kind':kind, 'final_board_cards':str(n),
            'seat_terminal':f'{name}/{kind}', 'absolute_payoff_chips':band}


def summarize(values, total_hands):
    if not values or total_hands < len(values): raise ValueError('Invalid aggregation')
    if any(type(x) is not int for x in values): raise ValueError('Non-integer chips')
    total = sum(values)
    return dict(hands=len(values), total_chips=total, conditional_bb_per_100=total/len(values),
                contribution_bb_per_100=total/total_hands,
                positive_hands=sum(x>0 for x in values), negative_hands=sum(x<0 for x in values), zero_hands=values.count(0))


def decision_bucket(d):
    response = d['response']
    seat, n = response['client_pos'], len(response['board'])
    if type(seat) is not int or seat not in (0, 1) or n not in (0, 3, 4, 5): raise ValueError('Invalid decision state')
    probabilities, table, mask, slot = d['behavior_probs'], d['action_table'], d['legal_mask'], d['selected_action_slot']
    if len(probabilities)!=9 or len(table)!=9 or len(mask)!=9 or type(slot) is not int or slot not in range(9): raise ValueError('Invalid slots')
    if not all(math.isfinite(p) and 0 <= p <= 1 for p in probabilities): raise ValueError('Invalid probabilities')
    if not math.isclose(math.fsum(probabilities),1,abs_tol=1e-8): raise ValueError('Not normalized')
    if not mask[slot] or table[slot] != d['direct_increment']: raise ValueError('Inconsistent selected action')
    if not math.isclose(probabilities[slot],d['behavior_action_probability'],abs_tol=1e-10): raise ValueError('Inconsistent selected probability')
    if any(p > 1e-12 and not m for p,m in zip(probabilities,mask)): raise ValueError('Illegal probability mass')
    if d['policy_mode']!='sample' or d['temperature']!=1: raise ValueError('Wrong policy mode')
    action = d['direct_increment']
    kind = {'f':'fold','c':'call','k':'check'}.get(action, 'raise' if action.startswith('b') else None)
    if kind is None: raise ValueError('Unknown action')
    return f'{"BB" if seat==0 else "SB"}/{dict(zip([0,3,4,5],["preflop","flop","turn","river"]))[n]}', kind


def verify_protected():
    copies = read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(copies)==76
    for item in copies:
        assert all(sha(ROOT/item[k])==item['sha256'] for k in ['original','copy'])
    assert sha(SOURCE/'reviewed_analysis.json')==SOURCE_REVIEW_SHA
    return len(copies)


def main():
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution_code','analysis.json']): raise ValueError('No repeated analysis or overwrite')
    verify_protected()
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
    test_cmd=['-m','pytest',str(BASE/'test_analysis.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,'--command',subprocess.list2cmdline(['python',*test_cmd])],cwd=ROOT,check=True)
    subprocess.run([sys.executable,*test_cmd],cwd=ROOT,check=True)
    review,audit=read(SOURCE/'reviewed_analysis.json'),read(SOURCE/'combined_audit.json')
    assert review['status']=='PASS' and review['slumbot_hands']==20000 and review['model_sha256']==MODEL_SHA
    assert audit['status']=='PASS' and audit['sessions']==8 and audit['successful_hands']==20000 and audit['token_chains_disjoint']
    groups=defaultdict(lambda:defaultdict(list))
    decisions={}
    all_chips, sessions, inputs = [], [], []
    for index,item in enumerate(audit['results'],1):
        path=SOURCE/'sessions'/f's{index:02d}'/'hands.jsonl'
        digest=sha(path)
        assert digest==item['hands_sha256']==review['sessions'][index-1]['hands_sha256']
        inputs.append(dict(path=str(path),sha256=digest))
        chips,draws=[],0
        with path.open() as handle:
            for number,line in enumerate(handle,1):
                assert line.endswith('\n')
                row=json.loads(line)
                assert row['successful_hand']==row['attempted_hand']==number
                assert row['session_id']==item['session_id'] and row['model_sha256']==MODEL_SHA
                assert row['winnings_chips']==row['terminal_response']['winnings']
                chips.append(row['winnings_chips'])
                assert row['cumulative_chips']==sum(chips)==row['terminal_response']['session_total']
                assert row['terminal_response']['session_num_hands']==number
                for partition,label in categories(row).items(): groups[partition][label].append(row['winnings_chips'])
                for decision in row['decisions']:
                    key,kind=decision_bucket(decision)
                    data=decisions.setdefault(key,dict(decisions=0,actual_slots=[0]*9,expected_slots=[0.0]*9,action_kinds=Counter(),entropy_sum=0.0))
                    data['decisions']+=1
                    data['actual_slots'][decision['selected_action_slot']]+=1
                    for slot,prob in enumerate(decision['behavior_probs']): data['expected_slots'][slot]+=prob
                    data['action_kinds'][kind]+=1
                    data['entropy_sum']-=sum(p*math.log(p) for p in decision['behavior_probs'] if p>0)
                    draws+=1
        assert len(chips)==2500 and sum(chips)==item['cumulative_chips'] and draws==item['decision_replays']
        all_chips.extend(chips)
        sessions.append(dict(session_id=item['session_id'],**summarize(chips,20000)))
    assert len(all_chips)==20000
    total=sum(all_chips)
    assert total/20000==review['statistics']['bb_per_100']
    partitions={}
    for name,values in groups.items():
        partitions[name]={label:summarize(v,20000) for label,v in sorted(values.items())}
        assert sum(r['hands'] for r in partitions[name].values())==20000
        assert sum(r['total_chips'] for r in partitions[name].values())==total
        assert math.isclose(math.fsum(r['contribution_bb_per_100'] for r in partitions[name].values()),total/20000,abs_tol=1e-10)
    for data in decisions.values():
        n=data['decisions']
        assert sum(data['actual_slots'])==sum(data['action_kinds'].values())==n
        assert math.isclose(math.fsum(data['expected_slots']),n,rel_tol=1e-10)
        data['mean_entropy_nats']=data.pop('entropy_sum')/n
    assert sum(d['decisions'] for d in decisions.values())==sum(s['decision_replays'] for s in review['sessions'])
    for row in inputs: assert sha(row['path'])==row['sha256']
    for row in copies: assert all(sha(ROOT/row[k])==row['sha256'] for k in ['original','copy'])
    verify_protected()
    report=dict(status='PASS',analyzed_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,evaluation_hands=0,slumbot_hands=0,
                reused_existing_hands=20000,new_model_queries=0,new_api_requests=0,model_sha256=MODEL_SHA,
                source_review_sha256=SOURCE_REVIEW_SHA,overall=summarize(all_chips,20000),partitions=partitions,
                sessions=sessions,decision_weighted_policy_summaries=decisions,protected_source_pairs=76,
                interpretation='Posthoc endogenous descriptive partitions; no causal, significance, optimal-action or qualification claim.')
    write(BASE/'input_manifest.json',inputs)
    write(BASE/'analysis.json',report)
    lines=['# Completed source20k descriptive loss accounting','',f'Overall {total/20000:+.4f}bb/100.0new hands;20000reused audited records.','',
           'Posthoc endogenous categories are descriptive,not causal skill estimates or evidence of optimal actions.','']
    for name in ['seat','terminal_kind','seat_terminal','absolute_payoff_chips']:
        lines += [f'## {name}','', '| Category | Hands | Contribution to total bb/100 | Conditional bb/100 |','|---|---:|---:|---:|']
        for label,row in partitions[name].items(): lines.append(f'| {label} | {row["hands"]} | {row["contribution_bb_per_100"]:+.4f} | {row["conditional_bb_per_100"]:+.4f} |')
        lines.append('')
    (BASE/'result_summary.md').write_text('\n'.join(lines)+'\n')
    artifacts=[BASE/'analysis.json',BASE/'input_manifest.json',BASE/'result_summary.md',BASE/'tests.xml']
    artifacts += [directory/n for n in ['source_manifest.json','code.patch','copy_manifest.json']]
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
                    *[v for p in artifacts for v in ['--artifact',str(p)]],'--metric','reused_existing_hands=20000',
                    '--note','All exhaustive partitions reconcile exactly to original chips and20000hands;76active source/copy pairs unchanged. No new policy query or hand.'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
                    '--summary','Reconciled fixed posthoc source20k loss/decision partitions with zero new hands or policy queries.',
                    '--conclusion','Descriptive endogenous outcome groups only; no causal skill or action-quality conclusion.',
                    '--decision','DESCRIPTIVE_ACCOUNTING_COMPLETE','--next-step','Use general loss/risk patterns to prioritize future diagnostics only after the unchanged physical1m gate.',
                    '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
    print(json.dumps(dict(status='PASS',overall=report['overall'],partitions=partitions,total_decisions=sum(d['decisions'] for d in decisions.values()))))


if __name__=='__main__': main()
