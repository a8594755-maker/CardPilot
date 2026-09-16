import copy
import io
import math
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from temporal_average import Reservoir, KEYS, SHAPES, hand_spec, uniform_for, softmax_legal, select, soft_ce, observation_digest


def obs():
    result = {k: np.zeros(s, dtype=np.float32) for k, s in zip(KEYS, SHAPES)}
    result['legal_mask'][:] = 1
    return result


def test_reservoir_algorithm_r_independent_reference_and_roundtrip():
    import random
    r, rng, ids = Reservoir(7, 311), random.Random(311), []
    for i in range(100):
        o = obs()
        o['extra_info'][0] = i
        r.add(o, np.ones(9)/9, (i, 0))
        if i < 7:
            ids.append(i)
        else:
            j = rng.randrange(i+1)
            if j < 7:
                ids[j] = i
    assert list(r.ids[:, 0]) == ids and r.seen == 100
    buffer = io.BytesIO()
    torch.save(r.state_dict(), buffer)
    buffer.seek(0)
    restored = Reservoir.restore(torch.load(buffer, weights_only=False))
    for i in range(100, 130):
        for reservoir in (r, restored):
            reservoir.add(obs(), np.ones(9)/9, (i, 0))
    assert r.rng.getstate() == restored.rng.getstate()
    assert np.array_equal(r.ids, restored.ids)
    assert np.array_equal(r.targets, restored.targets)
    for k in KEYS:
        assert np.array_equal(r.arrays[k], restored.arrays[k])


def test_reservoir_is_not_recent_window_or_prefix_only():
    r = Reservoir(20, 37)
    for i in range(200):
        r.add(obs(), np.ones(9)/9, (i, 0))
    assert r.ids[:, 0].min() < 100 and r.ids[:, 0].max() >= 100
    assert len(set(map(tuple, r.ids))) == 20


def test_reservoir_snapshot_does_not_alias_live_data():
    r = Reservoir(1, 1)
    r.add(obs(), np.ones(9)/9, (0, 0))
    saved = r.state_dict()
    r.targets[:] = 0
    assert np.all(saved['targets'] > 0)


@pytest.mark.parametrize('bad', [0, -1, 1.5])
def test_bad_capacity(bad):
    with pytest.raises(ValueError):
        Reservoir(bad, 1)


def test_separate_deck_teacher_action_streams_and_order_independence():
    specs = [hand_spec(553, i, 17) for i in range(2000)]
    assert all(sorted(d) == list(range(52)) for d, _ in specs)
    assert len({tuple(d) for d, _ in specs}) == 2000
    assert all(hand_spec(553, i, 17) == specs[i] for i in reversed(range(2000)))
    assert all(hand_spec(553, i, 2)[0] == specs[i][0] for i in range(2000))
    assert all(hand_spec(554, i, 17)[0] != specs[i][0] for i in range(2000))
    pairs = {tuple(t) for _, t in specs}
    assert len(pairs) > 280 and sum(t[0] == t[1] for _, t in specs) < 200
    assert uniform_for(553, 0, 0, 0) != uniform_for(553, 0, 1, 0)
    assert uniform_for(553, 0, 0, 0) != uniform_for(553, 0, 0, 1)


def test_whole_episode_mixture_requires_reach_weighting():
    # Two equiprobable policies reach a later infoset with .9 and .1.
    # Their later probabilities of action A are .8 and .2.
    reaches, actions = [.9, .1], [.8, .2]
    conditional = sum(.5*r*a for r, a in zip(reaches, actions))/sum(.5*r for r in reaches)
    assert math.isclose(conditional, .74)
    assert not math.isclose(conditional, np.mean(actions))
    # Integer population of whole episodes reproduces the conditional mixture.
    population = [actions[0]]*900 + [actions[1]]*100
    assert math.isclose(np.mean(population), conditional)


def test_masked_probabilities_and_endpoint_draws():
    mask = np.array([[1, 0, 1, 0, 0, 0, 0, 0, 0]])
    p = softmax_legal(np.zeros((1, 9)), mask)[0]
    assert list(p[[0, 2]]) == [.5, .5] and np.all(p[mask[0] == 0] == 0)
    assert select(p, 0) == 0 and select(p, .5) == 2 and select(p, np.nextafter(1., 0.)) == 2
    with pytest.raises(ValueError):
        select(p, 1.)


@pytest.mark.parametrize('kind', ['no_legal', 'nan', 'bad_mask'])
def test_invalid_batch(kind):
    logits, mask = np.zeros((1, 9)), np.ones((1, 9))
    if kind == 'no_legal':
        mask[:] = 0
    elif kind == 'nan':
        logits[0, 0] = np.nan
    else:
        mask[0, 0] = .5
    with pytest.raises(ValueError):
        softmax_legal(logits, mask)


def test_soft_target_ce_gradient_and_illegal_target_rejection():
    logits = torch.zeros(1, 9, requires_grad=True)
    masks = torch.tensor([[1, 1, 0, 0, 0, 0, 0, 0, 0]])
    target = torch.tensor([[.9, .1, 0, 0, 0, 0, 0, 0, 0]])
    loss = soft_ce(logits, target, masks).mean()
    assert math.isclose(float(loss.detach()), math.log(2), rel_tol=1e-6)
    loss.backward()
    assert torch.allclose(logits.grad, torch.tensor([[-.4, .4, 0, 0, 0, 0, 0, 0, 0]]))
    bad = target.clone()
    bad[0, 1], bad[0, 2] = 0, .1
    with pytest.raises(ValueError):
        soft_ce(logits, bad, masks)


def test_observation_digest_detects_changed_amount_without_hidden_teacher_input():
    original = obs()
    changed = copy.deepcopy(original)
    changed['action_info'][0, 2, 0] = .25
    assert observation_digest(original) != observation_digest(changed)
    original['teacher_id'] = 7
    assert observation_digest(original) == observation_digest(obs())


def test_reservoir_rejects_illegal_target_before_changing_count():
    r, o = Reservoir(4, 1), obs()
    o['legal_mask'][0] = 0
    with pytest.raises(ValueError):
        r.add(o, np.ones(9)/9, (0, 0))
    assert r.seen == 0
