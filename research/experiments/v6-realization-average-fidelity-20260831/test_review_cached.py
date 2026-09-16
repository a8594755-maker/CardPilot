import numpy as np
from review_cached import cached_load,ORIGINAL_LOAD

def test_eager_cache_exact_values_and_repeated_access_identity(tmp_path):
    path=tmp_path/'mixture_metrics.npz'
    values=dict(posterior=np.arange(30,dtype=np.float64).reshape(10,3),
                mixture=np.arange(90,dtype=np.float64).reshape(10,9),
                tv=np.linspace(0,1,10),js=np.linspace(1,0,10),naive_tv=np.zeros(10))
    np.savez_compressed(path,**values)
    loaded=cached_load(path)
    assert isinstance(loaded,dict)
    with ORIGINAL_LOAD(path) as baseline:
        for name in values:
            assert np.array_equal(loaded[name],baseline[name])
            assert loaded[name] is loaded[name]
    # Repeated row access uses the same cached array, not another archive decode.
    assert loaded['posterior'] is loaded['posterior']

def test_other_archive_and_npy_loading_unchanged(tmp_path):
    path=tmp_path/'observations.npz'
    np.savez_compressed(path,legal_mask=np.ones((3,9)))
    with cached_load(path) as loaded:
        assert loaded.files==['legal_mask']
        assert np.array_equal(loaded['legal_mask'],np.ones((3,9)))
    path=tmp_path/'probabilities_model0.npy'
    np.save(path,np.arange(9))
    assert np.array_equal(cached_load(path),np.arange(9))

