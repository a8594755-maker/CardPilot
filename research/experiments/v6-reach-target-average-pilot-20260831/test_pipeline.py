import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
import run_pilot as run
from native_relabel import stream_relabel,reconstruct,targets_for_block
from fit_metrics import hero_tv,paired_gate,interval,cross_entropy

def test_real_native_only_inputs_and_frozen_scope():
    data=run.input_manifest()
    assert len(data['teachers'])==3
    assert len({r['sha256'] for r in data['teachers']+[data['initializer'],data['control']]})==5
    assert data['new_training_hands']==0 and data['new_native_validation_target']==8192
    assert data['validation_seed']==2026102401 and data['fit_seed']==2026102004
    assert not data['external_data_used_for_training']
    assert not any('slumbot' in r['path'].lower() for r in data['dependencies'])

def test_queries_not_allowed_outside_recorded_execution(monkeypatch):
    monkeypatch.setattr(run,'EXECUTION',None)
    with pytest.raises(RuntimeError):run.query('fixture',lambda:1,1)

def test_query_exception_separates_attempted_from_completed(monkeypatch):
    monkeypatch.setattr(run,'EXECUTION',{})
    monkeypatch.setattr(run,'QUERIES',{})
    def fail():raise ValueError('fixture')
    with pytest.raises(ValueError):run.query('fixture',fail,64)
    assert run.QUERIES['fixture']==dict(attempted=64,completed=0)

def test_interrupted_collection_preserves_unknown_tail(monkeypatch,tmp_path):
    monkeypatch.setattr(run,'BASE',tmp_path)
    (tmp_path/'validation_hands.jsonl').write_bytes(b'{}\n{}\n{')
    report=run.failure_accounting('NATIVE_VALIDATION_COLLECTION')
    assert report['preserved_complete_native_validation_lines']==2
    assert report['additional_unserialized_terminal_hands_upper_bound']==1024
    assert report['additional_unserialized_terminal_hands_unknown']
    assert report['new_training_hands']==0 and not report['automatic_resume_qualified']
    assert run.failure_accounting('NATIVE_TRAINING_RELABEL')['additional_unserialized_terminal_hands_upper_bound']==0

def native_fixture():
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation,apply_incr
    from temporal_average import observation_digest
    deck=list(range(52));state=ChipState.new(deck);obs,table=observation(state)
    assert state.actor==1 and table[0]=='f'
    probabilities=np.zeros((3,1,9))
    probabilities[:,0,0]=[.2,.7,.4];probabilities[:,0,1]=[.8,.3,.6]
    event=dict(seat=state.actor,teacher=1,action=0,increment='f',probabilities=probabilities[1,0].tolist(),
        observation_sha256=observation_digest(obs),uniform=.5)
    terminal=apply_incr(state,'f')
    raw=dict(index=0,deck=deck,teachers=[0,1],events=[event],payoffs=list(terminal.payoffs()))
    reservoir=dict(ids=np.array([[0,0]]),arrays={k:np.expand_dims(obs[k],0) for k in run.KEYS},
        targets=probabilities[1].copy(),seen=1,capacity=1)
    return raw,reservoir,probabilities

def test_streamed_three_teacher_labels_and_exact_row_identity(tmp_path):
    raw,reservoir,p=native_fixture()
    source=tmp_path/'native.jsonl';source.write_text(json.dumps(raw)+'\n')
    calls=[];progress=[]
    def infer(arrays):
        calls.append(len(arrays['legal_mask']))
        return p.copy()
    def save(path,value):Path(path).write_text(json.dumps(value))
    result,targets,_,_=stream_relabel(source,tmp_path/'labels',1,1,infer,save,run.sha,
        lambda *args:progress.append(args),reservoir=reservoir)
    assert result['status']=='PASS' and result['retained_rows']==1 and calls==[1]
    assert np.allclose(targets[0],p[:,0].mean(0))
    assert not np.allclose(targets[0],reservoir['targets'][0])
    assert progress==[(1,1,1)]
    assert np.array_equal(np.load(tmp_path/'labels/retained_ids.npy'),reservoir['ids'])
    with np.load(tmp_path/'labels/block0000.npz') as data:
        assert np.array_equal(data['teacher_probabilities'],p)
        assert np.array_equal(data['targets'],targets)
    with pytest.raises(ValueError,match='restart'):
        stream_relabel(source,tmp_path/'labels',1,1,infer,save,run.sha,lambda *args:None,reservoir=reservoir)

def test_retained_observation_tamper_rejected():
    raw,reservoir,_=native_fixture()
    reservoir['arrays']['card_info'][0,0,0,0]+=1
    with pytest.raises(AssertionError):
        reconstruct([(raw,json.dumps(raw)+'\n')],0,{(0,0):0},reservoir)

def test_missing_retained_identity_does_not_silently_train_nan(tmp_path):
    raw,reservoir,p=native_fixture()
    reservoir['ids']=np.array([[0,1]])
    source=tmp_path/'native.jsonl';source.write_text(json.dumps(raw)+'\n')
    with pytest.raises(AssertionError):
        stream_relabel(source,tmp_path/'labels',1,1,lambda arrays:p,
            lambda path,value:Path(path).write_text(json.dumps(value)),run.sha,lambda *args:None,reservoir=reservoir)
    assert (tmp_path/'labels/block0000.npz').exists()

def test_partial_native_line_rejected(tmp_path):
    source=tmp_path/'partial.jsonl';source.write_bytes(b'{')
    from native_relabel import chunks
    with pytest.raises(ValueError,match='Partial'):list(chunks(source))

def test_hand_offsets_must_cover_all_teacher_predictions():
    p=np.zeros((3,2,9));p[:,:,0]=1
    with pytest.raises(ValueError):targets_for_block(p,[1],np.array([0,1]),np.array([0,0]))

def test_hero_only_metrics_do_not_use_opponent_decision_or_impute_zero():
    q=np.zeros((3,9));q[:,0]=1
    p=q.copy();p[1]=[0,1]+[0]*7
    values,counts=hero_tv(p,q,np.array([0,0,1]),np.array([0,1,1]),physical_hands=3)
    assert np.array_equal(counts,[1,1,0]) and np.allclose(values[:2],0) and np.isnan(values[2])

@pytest.mark.parametrize('candidate,admitted',[([.1,.1],True),([.15,.15],True),([.151,.151],False),([.2,.2],False)])
def test_fixed_paired_gate_boundaries(candidate,admitted):
    result=paired_gate(np.array([.2,.2]),np.asarray(candidate))
    assert (result['decision']=='ADMIT_SEPARATE_STRATEGIC_ASSESSMENT')==admitted
    assert not result['goal_achieved'] and result['strength_evaluation_hands']==0

def test_paired_coverage_mismatch_rejected():
    with pytest.raises(ValueError):paired_gate(np.array([.2,np.nan]),np.array([.1,.1]))

def test_ci_and_ce_units():
    value=interval([1.,2.,3.])
    assert value['mean']==2 and value['standard_error']==pytest.approx(1/np.sqrt(3))
    q=np.array([[1.]+[0.]*8]);p=np.array([[.5,.5]+[0.]*7])
    assert cross_entropy(p,q)[0]==pytest.approx(np.log(2))
    with pytest.raises(ValueError):cross_entropy(np.array([[0,1]+[0]*7]),q)

