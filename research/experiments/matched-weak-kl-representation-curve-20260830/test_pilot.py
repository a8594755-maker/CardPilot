import copy
import json
from pathlib import Path
import sys

import pytest

BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import run_pilot as run
import evaluate as evaluation


def options(command):
    result={}
    current=None
    for item in command:
        if item.startswith('--'):
            current=item
            result[current]=[]
        elif current:
            result[current].append(item)
    return result


def test_scope_is_only_training_intervention():
    heads,full=[options(run.make_command(arm)) for arm in ['heads','full']]
    assert heads.pop('--all-policy-heads-only-training')==[]
    assert '--all-policy-heads-only-training' not in full
    outputs={'--run-dir','--run-id','--out','--opponent-assignment-provenance-file'}
    assert {key for key in heads if heads[key]!=full[key]}==outputs
    for command in [heads,full]:
        expected={'--source-policy-kl-coef':['0.01'],'--total-environment-hands':['524288'],
                  '--mini-batch-size':['1024'],'--lr':['0.00003'],'--seed':['20260911'],
                  '--worker-seed-base':['2026091100'],'--archive-checkpoint-every':['4']}
        assert all(command[key]==value for key,value in expected.items())
        assert command['--fixed-opponent-checkpoints']==list(map(str,run.ANCHORS[:3]))
        assert str(run.ANCHORS[3]) not in command['--fixed-opponent-checkpoints']
        assert command['--source-policy-reference-checkpoint']==[str(run.SOURCE)]
        assert '--reset-optimizer' in command and '--reset-hand-counter' in command


def test_audit_matches_physical_endpoint_and_three_training_anchors():
    command=options(run.make_audit_command(Path('run'),{'iteration':100},Path('out')))
    assert command['--expected-target-environment-hands']==['524288']
    assert command['--expected-pool-size']==['3']
    assert command['--expected-archive-every']==['4']


def midpoint_rows():
    return [dict(iteration=i,environment_hand_accounting=dict(completed_hands=i*5000,prefix_complete=True))
            for i in range(1,109)]


def test_midpoint_is_first_scheduled_archive_by_physical_not_legacy_counts():
    assert run.choose_midpoint_row(midpoint_rows(),range(4,109,4))['iteration']==56


@pytest.mark.parametrize('kind',['missing','extra','nonmonotonic','iteration','no_crossing'])
def test_midpoint_rejects_incomplete_evidence(kind):
    rows=midpoint_rows()
    archives=list(range(4,109,4))
    if kind=='missing': archives.remove(56)
    if kind=='extra': archives.append(55)
    if kind=='nonmonotonic': rows[25]['environment_hand_accounting']['completed_hands']=1
    if kind=='iteration': rows[25]['iteration']=1
    if kind=='no_crossing': rows=rows[:40]; archives=list(range(4,41,4))
    with pytest.raises(ValueError): run.choose_midpoint_row(rows,archives)


def test_real_archive_filename_and_checkpoint_counter_contract(tmp_path):
    import torch
    rows=midpoint_rows()
    (tmp_path/'h1_training_metrics.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
    (tmp_path/'checkpoints').mkdir()
    for i in range(4,109,4):
        path=tmp_path/'checkpoints'/f'checkpoint_iter{i:06d}_hands{i*4000:012d}.pt'
        torch.save(rows[i-1],path)
    path=run.select_midpoint(tmp_path)
    assert 'iter000056' in path.name
    bad=copy.deepcopy(rows[55]); bad['environment_hand_accounting']['completed_hands']+=1
    torch.save(bad,path)
    with pytest.raises(ValueError): run.select_midpoint(tmp_path)


def test_persisted_historical_archive_and_metric_counter_semantics_agree():
    """Read-only integration; no new poker hands and no historical mutations."""
    import torch
    checked=0
    for arm in ['control','weak']:
        old=run.ROOT/'research/experiments/weak-source-kl-pilot-20260830'/arm
        rows=[json.loads(line) for line in (old/'h1_training_metrics.jsonl').read_text().splitlines()]
        for iteration in [4,8,12]:
            paths=list((old/'checkpoints').glob(f'checkpoint_iter{iteration:06d}_hands*.pt'))
            assert len(paths)==1
            payload=torch.load(paths[0],map_location='cpu',weights_only=False)
            assert payload['iteration']==iteration
            assert payload['environment_hand_accounting']['completed_hands']==rows[iteration-1]['environment_hand_accounting']['completed_hands']
            checked+=1
    assert checked==6


def fixture():
    return dict(seed=evaluation.SEED,pairs=2,policy_mode=evaluation.MODE,action_rng_schema=evaluation.RNG,
        starting_stack=200.,candidate={'sha256':'candidate'},execution={'status':'COMPLETED'},
        anchors=[dict(anchor=name,anchor_sha256=run.DIGESTS[i],action_rng=dict(seed=evaluation.SEED+i*1000003,schema=evaluation.RNG),
                      pairs=2,hands=4,candidate_bb100=0.,anchor_ood_valid=True,
                      paired_outcomes=dict(overall_bb_per_hand=[0.,0.],bb_bb_per_hand=[1.,2.],sb_bb_per_hand=[-1.,-2.]))
                 for i,name in enumerate(evaluation.NAMES)])


def test_raw_cell_four_opponents_zero_self_difference():
    doc=fixture()
    assert evaluation.validate(doc,{'status':'COMPLETED'},'candidate',pairs=2)==16
    assert len(evaluation.CANDIDATES)*len(evaluation.NAMES)*evaluation.PAIRS*2==163840
    assert all(r['delta_bb100']==r['ci95_half_width']==0 for r in evaluation.compare(doc,doc))


@pytest.mark.parametrize('kind',['seed','rng','raw','count','identity','heldout_identity','missing_anchor'])
def test_rejects_misaligned_raw_evidence(kind):
    doc=fixture()
    if kind=='seed': doc['seed']+=1
    if kind=='rng': doc['anchors'][0]['action_rng']['seed']+=1
    if kind=='raw': doc['anchors'][0]['paired_outcomes']['overall_bb_per_hand'][0]=float('inf')
    if kind=='count': doc['anchors'][0]['hands']=3
    if kind=='identity': doc['candidate']['sha256']='other'
    if kind=='heldout_identity': doc['anchors'][-1]['anchor_sha256']='other'
    if kind=='missing_anchor': doc['anchors'].pop()
    with pytest.raises(ValueError): evaluation.validate(doc,{'status':'COMPLETED'},'candidate',pairs=2)


def gate_rows():
    return [dict(anchor=name,delta_bb100=1.,bonferroni_lower=.1,ood_valid=True) for name in evaluation.NAMES]


def test_gate_needs_breadth_not_only_cfr96_or_free():
    primary,source=gate_rows(),gate_rows()
    assert evaluation.admission(primary,source)
    primary[0]['bonferroni_lower']=-1
    primary[3]['bonferroni_lower']=-1
    assert not evaluation.admission(primary,source)
    primary[3]['bonferroni_lower']=.1
    assert evaluation.admission(primary,source)
    primary[1]['bonferroni_lower']=primary[2]['bonferroni_lower']=-1
    assert not evaluation.admission(primary,source)


@pytest.mark.parametrize('kind',['negative_primary','zero_primary','negative_source','ood','missing'])
def test_gate_rejects_invalid_admission(kind):
    primary,source=gate_rows(),gate_rows()
    if kind=='negative_primary': primary[0]['delta_bb100']=-.1
    if kind=='zero_primary': primary[0]['delta_bb100']=0
    if kind=='negative_source': source[-1]['delta_bb100']=-.1
    if kind=='ood': source[-1]['ood_valid']=False
    if kind=='missing': primary.pop()
    assert not evaluation.admission(primary,source)
