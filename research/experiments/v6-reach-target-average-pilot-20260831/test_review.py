import json
import numpy as np
import pytest
import run_pilot as run
from native_relabel import stream_relabel,targets_for_block
from test_pipeline import native_fixture
from review_finish import independent_targets,independently_grouped_tv,independent_interval,review_blocks
from fit_metrics import hero_tv,interval

def test_independent_probability_products_match_log_reference_and_reset():
    rng=np.random.default_rng(104)
    p=rng.dirichlet(np.ones(9),size=(3,37))
    actors=rng.integers(0,2,size=37);slots=rng.integers(0,9,size=37)
    lengths=[12,1,24]
    q=independent_targets(p,lengths,actors,slots)
    assert np.allclose(q,targets_for_block(p,lengths,actors,slots),rtol=0,atol=2e-12)
    for i in (0,12,13):assert np.allclose(q[i],p[:,i].mean(0))
    changed=slots.copy();changed[0]=(changed[0]+1)%9
    altered=independent_targets(p,lengths,actors,changed)
    assert np.array_equal(q[0],altered[0])
    assert np.array_equal(q[1:12][actors[1:12]!=actors[0]],altered[1:12][actors[1:12]!=actors[0]])
    assert np.array_equal(q[12:],altered[12:])

def test_independent_reference_rejects_impossible_path():
    p=np.zeros((3,1,9));p[:,:,1]=1
    with pytest.raises(ValueError,match='Impossible'):independent_targets(p,[1],[1],[0])
    with pytest.raises(ValueError,match='coverage'):independent_targets(p,[],[1],[1])

@pytest.mark.parametrize('validation',[False,True])
def test_stream_artifacts_can_be_fully_independently_reviewed(tmp_path,validation):
    raw,reservoir,p=native_fixture()
    source=tmp_path/'native.jsonl';source.write_text(json.dumps(raw)+'\n')
    output=tmp_path/'out'
    stream_relabel(source,output,1,1,lambda arrays:p,run.atomic_json,run.sha,lambda *args:None,
        reservoir=None if validation else reservoir,validation=validation)
    result=review_blocks(output,source,1,1,None if validation else reservoir)
    assert result['status']=='PASS' and result['hands']==1
    assert result['retained_rows_verified']==(0 if validation else 1)
    path=output/'block0000.npz'
    with np.load(path) as loaded:cache={k:loaded[k] for k in loaded.files}
    cache['targets'][0,0]+=.001
    np.savez_compressed(path,**cache)
    with pytest.raises(AssertionError):review_blocks(output,source,1,1,None if validation else reservoir)

def test_independent_grouping_and_ci_match_primary():
    rng=np.random.default_rng(921)
    p=rng.dirichlet(np.ones(9),size=37);q=rng.dirichlet(np.ones(9),size=37)
    hands=np.repeat(np.arange(4),[8,11,6,12]);actors=rng.integers(0,2,size=37)
    a,c=independently_grouped_tv(p,q,hands,actors,5)
    b,d=hero_tv(p,q,hands,actors,5)
    assert np.array_equal(c,d) and c[-1]==0 and np.isnan(a[-1])
    assert np.allclose(a,b,atol=1e-12,rtol=0,equal_nan=True)
    old,new=independent_interval(a[:4]),interval(b[:4])
    assert np.allclose(old['ci95'],new['ci95'],atol=1e-12,rtol=0)

