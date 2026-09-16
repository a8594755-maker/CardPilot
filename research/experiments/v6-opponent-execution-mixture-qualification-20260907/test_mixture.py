import importlib.util
from pathlib import Path
import numpy as np
import pytest
import torch

spec = importlib.util.spec_from_file_location('mixture_candidate', Path(__file__).with_name('train_candidate.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

@pytest.mark.parametrize('weight', [0, 0.5, 1])
def test_distribution(weight):
    logits = torch.tensor([[1., 3., -float('inf')], [2., 2., -1e9]])
    result = m.mixture_logits(logits, weight)
    expected = (1-weight)*logits.softmax(-1)
    expected[0,1] += weight
    expected[1,0] += weight
    torch.testing.assert_close(result.softmax(-1), expected)
    assert torch.equal(result.softmax(-1)[:,2], torch.zeros(2))
    if weight == 0:
        assert result is logits

@pytest.mark.parametrize('weight', [-0.1, 1.1, float('nan'), float('inf')])
def test_invalid_weight(weight):
    with pytest.raises(ValueError):
        m.mixture_logits(torch.zeros(1,3), weight)

def test_values_untouched():
    values = torch.tensor([[0.75]])
    logits = torch.tensor([[0.,1.,2.]])
    class Model:
        def __call__(self, *args): return logits, values
    result, result_values = m.OpponentView(Model(), .5)()
    assert result_values is values
    assert torch.equal(logits, torch.tensor([[0.,1.,2.]]))

def test_real_inference_routes():
    trainer, binding, original = m.install(.5)
    count = 128
    class Model:
        def __call__(self, cards, actions, extras, masks):
            logits = torch.zeros_like(masks)
            logits[:,1] = 1
            logits[:,2:] = -float('inf')
            return logits, torch.ones((len(cards),1))
    hero, opponent = Model(), Model()
    observation = np.zeros(count*trainer.OBS_SIZE, dtype=np.float32)
    requests = np.zeros(count, dtype=np.int32)
    requests[:64] = trainer.HERO_MODEL_ID
    def run(fn):
        status = np.full(count, trainer.WAITING, dtype=np.int32)
        result = np.zeros(count*trainer.RESULT_SIZE, dtype=np.float32)
        torch.manual_seed(123)
        n = fn(hero, [opponent], observation, result, status, requests, count, 'cpu', [])
        assert n == count
        assert np.all(status == trainer.READY)
        return result.reshape(count,trainer.RESULT_SIZE)
    baseline, treated = run(original), run(trainer.run_inference_v5)
    np.testing.assert_array_equal(baseline[:64], treated[:64])
    np.testing.assert_array_equal(baseline[:,2], treated[:,2])
    assert set(treated[:,0]) <= {0,1}
    # Actual emitted opponent log-probability must match the changed distribution.
    p1 = .5 + .5 * torch.softmax(torch.tensor([0.,1.]),0)[1].item()
    for action, logprob, *_ in treated[64:]:
        assert logprob == pytest.approx(np.log(p1 if action == 1 else 1-p1), abs=1e-6)
    assert binding['opponent_execution_mixture']['hero_and_selfplay_unchanged']
