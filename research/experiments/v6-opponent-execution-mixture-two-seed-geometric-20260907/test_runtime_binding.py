import importlib.util
from pathlib import Path
import pytest
import torch

spec = importlib.util.spec_from_file_location('mixture_runtime', Path(__file__).with_name('train_candidate.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

@pytest.mark.parametrize('weight',[0.,.5])
def test_valid_binding(weight):
    assert m.validate_contract(weight, {'opponent_greedy_mixture':weight}, {'greedy_weight':weight})

@pytest.mark.parametrize('weight,contract,prior',[
    (.5,{},None), (0.,{'opponent_greedy_mixture':.5},None),
    (.5,{'opponent_greedy_mixture':.5},{'greedy_weight':0}),
    (.25,{'opponent_greedy_mixture':.25},None)])
def test_wrong_binding(weight,contract,prior):
    with pytest.raises(ValueError): m.validate_contract(weight,contract,prior)

def test_zero_proxy_preserves_logits_values_and_rng():
    spec = importlib.util.spec_from_file_location('qualified_proxy',m.QUALIFIED)
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    logits = torch.tensor([[0.,1.,-1e9],[2.,0.,-1e9]])
    value = torch.tensor([[.1],[.2]])
    class Model:
        def __call__(self): return logits,value
    torch.manual_seed(918)
    before = torch.get_rng_state().clone()
    out,v = q.OpponentView(Model(),0.)()
    assert out is logits and v is value
    assert torch.equal(before,torch.get_rng_state())
    expected = torch.distributions.Categorical(logits=logits).sample()
    torch.set_rng_state(before)
    actual = torch.distributions.Categorical(logits=out).sample()
    assert torch.equal(actual,expected)
