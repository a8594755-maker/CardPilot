import copy
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.ppo_hand_gradient_noise import hand_group_indices, hand_gradient_noise, summarize_gram
from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update
from scripts.alpha_holdem.train_v5 import split_complete_hand_blocks


class TinyHeads(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.preflop_policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = torch.where(extras[:, :1] < 0.5, self.preflop_policy_head(extras), self.policy_head(extras))
        return logits.masked_fill(masks <= 0, -1e9), self.value_head(extras)


def transitions(model):
    result = []
    for hand in range(24):
        for seat in range(2 if hand % 2 == 0 else 1):
            length = 1+hand % 3 if seat == 0 else 1
            for step in range(length):
                extra = np.array([step % 2, hand/24, seat+0.1], dtype=np.float32)
                mask = np.ones(9, np.float32)
                mask[0] = 0
                slot = 1+hand % 8
                with torch.no_grad():
                    logits, value = model(None, None, torch.tensor(extra).unsqueeze(0), torch.tensor(mask).unsqueeze(0))
                    logp = float(torch.distributions.Categorical(logits=logits).log_prob(torch.tensor([slot]))[0])
                done = float(step == length-1)
                result.append((np.zeros((6, 4, 13), np.float32), np.zeros((25, 4, 5), np.float32),
                               extra, mask, slot, logp, (hand % 7-3)*(1-2*seat)*done,
                               float(value.squeeze()), done, 10., 10., done if seat == 0 else 0.))
    return result


def test_grouping_keeps_both_seat_trajectories_in_one_hand():
    data = transitions(TinyHeads())
    lengths = [len(block) for block in split_complete_hand_blocks(data)]
    assert len(lengths) == 24
    groups, info = hand_group_indices(lengths, 5, len(data))
    assert info['hands_per_group'] == 4
    assert info['used_hands'] == 20
    assert len(info['excluded_remainder_hand_indices']) == 4
    starts = np.cumsum([0, *lengths]).tolist()
    owner = {row: group for group, rows in enumerate(groups) for row in rows}
    for hand in range(24):
        memberships = {owner.get(row) for row in range(starts[hand], starts[hand+1])}
        assert len(memberships) == 1
    assert len(owner) == info['used_transition_rows']


@pytest.mark.parametrize('lengths,k,n', [([1, 1], 1, 2), ([1], 2, 1), ([1, 0], 2, 1),
                                        ([1, 1], 2, 3), ([1.2, 2.8], 2, 3)])
def test_bad_group_lengths_fail(lengths, k, n):
    with pytest.raises(ValueError): hand_group_indices(lengths, k, n)


def test_grouping_deterministic_without_process_rng_draws():
    np.random.seed(13)
    random.seed(13)
    torch.manual_seed(13)
    states = (np.random.get_state(), random.getstate(), torch.get_rng_state())
    first = hand_group_indices([1, 2, 3, 4], 2, 10)
    second = hand_group_indices([1, 2, 3, 4], 2, 10)
    assert first == second
    assert all(np.array_equal(a, b) for a, b in zip(states[0], np.random.get_state()))
    assert states[1] == random.getstate()
    assert torch.equal(states[2], torch.get_rng_state())


def test_gram_known_scalar_variance_and_signal():
    vectors = torch.tensor([[1.], [2.], [3.]], dtype=torch.float64)
    result = summarize_gram(vectors@vectors.T, 16)
    assert result['group_covariance_trace'] == pytest.approx(1.)
    assert result['mean_gradient_squared_norm'] == pytest.approx(4.)
    assert result['estimated_signal_squared_norm'] == pytest.approx(4-1/3)
    assert result['noise_to_signal_at_group_size'] == pytest.approx(3/11)
    assert result['simple_noise_scale_hands'] == pytest.approx(48/11)
    assert result['pairwise_cosine_mean'] == pytest.approx(1.)


def test_unresolved_noise_is_distinct_from_zero_gradient():
    noisy = summarize_gram([[1., -1.], [-1., 1.]], 4)
    assert noisy['noise_to_signal_at_group_size'] is None
    assert noisy['noisy_or_unresolved']
    zero = summarize_gram([[0., 0.], [0., 0.]], 4)
    assert not zero['signal_resolved']
    assert not zero['noisy_or_unresolved']


def test_real_ppo_model_adam_and_rng_bitwise_unchanged_by_noise_probe():
    torch.set_num_threads(1)
    torch.manual_seed(59)
    base = TinyHeads()
    data = transitions(base)
    lengths = [len(block) for block in split_complete_hand_blocks(data)]
    models = [copy.deepcopy(base), copy.deepcopy(base)]
    optimizers = [torch.optim.Adam(model.parameters(), lr=.001) for model in models]
    outputs, states = [], []
    for k, model, optimizer in zip([0, 4], models, optimizers):
        torch.manual_seed(99)
        np.random.seed(99)
        random.seed(99)
        outputs.append(trinal_clip_ppo_update(model, optimizer, data, 'cpu', epochs=2, mini_batch_size=16,
            critic_contract='critic_v2', reference_policy=copy.deepcopy(base).eval(), reference_policy_kl_coef=1.,
            policy_advantage_clip=3., gradient_noise_hand_groups=k, gradient_noise_hand_lengths=lengths))
        states.append((torch.get_rng_state().clone(), np.random.get_state(), random.getstate()))
    for left, right in zip(models[0].state_dict().values(), models[1].state_dict().values()):
        assert torch.equal(left, right)
    for left, right in zip(optimizers[0].state.values(), optimizers[1].state.values()):
        for key in left: assert torch.equal(left[key], right[key])
    assert torch.equal(states[0][0], states[1][0])
    assert all(np.array_equal(a, b) for a, b in zip(states[0][1], states[1][1]))
    assert states[0][2] == states[1][2]
    assert outputs[0]['hand_gradient_noise'] is None
    assert outputs[1]['hand_gradient_noise']['grouping']['used_hands'] == 24
    for key in ['policy_loss', 'value_loss', 'entropy', 'approx_kl', 'reference_policy_kl']:
        assert outputs[0][key] == outputs[1][key]


def test_probe_does_not_touch_existing_gradients_or_model_buffers():
    torch.manual_seed(5)
    model = TinyHeads()
    for p in model.parameters(): p.grad = torch.ones_like(p)*3
    saved = [p.grad.clone() for p in model.parameters()]
    extras = torch.tensor([[0., 1., 0.], [1., 0., 1.], [0., 0., 1.], [1., 1., 0.]])
    mask = torch.ones(4, 9)
    with torch.no_grad(): logits, _ = model(None, None, extras, mask)
    acts = torch.tensor([1, 2, 3, 4])
    lp = torch.distributions.Categorical(logits=logits).log_prob(acts).detach()
    result = hand_gradient_noise(model, copy.deepcopy(model).eval(), cards=torch.zeros(4, 1), actions=torch.zeros(4, 1),
        extras=extras, masks=mask, selected_actions=acts, old_log_probs=lp, advantages=torch.tensor([1., -1., 2., -2.]),
        hand_lengths=[1]*4, num_groups=2, eps=.2, delta1=3., reference_kl_coef=1., entropy_coef=.005, entropy_floor=.05)
    assert set(result['groups']) == {'all_actor', 'policy_head', 'preflop_policy_head'}
    for p, before in zip(model.parameters(), saved): assert torch.equal(p.grad, before)
    assert math.isfinite(result['groups']['all_actor']['ppo']['group_covariance_trace'])


def test_group_mean_matches_full_selected_transition_weighted_gradient():
    torch.manual_seed(83)
    model = TinyHeads()
    reference = copy.deepcopy(model)
    with torch.no_grad():
        reference.policy_head.bias[1] += .4
        reference.preflop_policy_head.bias[3] -= .3
    extras = torch.tensor([[i % 2, i/8, (i % 3)/3] for i in range(8)], dtype=torch.float32)
    mask = torch.ones(8, 9)
    acts = torch.arange(1, 9)
    adv = torch.tensor([1., -1., 2., -2., .5, .8, -.3, 1.3])
    logits, _ = model(None, None, extras, mask)
    old = torch.distributions.Categorical(probs=logits.softmax(-1)).log_prob(acts).detach()
    result = hand_gradient_noise(model, reference, cards=torch.zeros(8, 1), actions=torch.zeros(8, 1),
        extras=extras, masks=mask, selected_actions=acts, old_log_probs=old, advantages=adv,
        hand_lengths=[1, 2, 1, 3, 1], num_groups=2, eps=.2, delta1=3., reference_kl_coef=.7,
        entropy_coef=.005, entropy_floor=.05)
    row_groups, _ = hand_group_indices([1, 2, 1, 3, 1], 2, 8)
    idx = torch.tensor([row for group in row_groups for row in group])
    logits, _ = model(None, None, extras[idx], mask[idx])
    probs = logits.softmax(-1)
    distribution = torch.distributions.Categorical(probs=probs)
    ratio = (distribution.log_prob(acts[idx])-old[idx]).exp()
    capped = torch.where(adv[idx] < 0, ratio.clamp(max=3), ratio)
    ppo = -torch.minimum(capped*adv[idx], ratio.clamp(.8, 1.2)*adv[idx]).mean()
    with torch.no_grad():
        ref_logits, _ = reference(None, None, extras[idx], mask[idx])
        q = ref_logits.softmax(-1)
    kl = .7*(q*(q.clamp_min(1e-8).log()-probs.clamp_min(1e-8).log())).sum(-1).mean()
    actor_loss = ppo+kl-.005*distribution.entropy().mean()
    parameters = [p for name, p in model.named_parameters() if not name.startswith('value_head.')]
    for component, loss in [('ppo', ppo), ('source_kl', kl), ('actor', actor_loss)]:
        gradient = torch.cat([g.flatten().double() for g in torch.autograd.grad(loss, parameters, retain_graph=True)])
        measured = result['groups']['all_actor'][component]['mean_gradient_squared_norm']
        assert measured == pytest.approx(float(gradient.square().sum()), rel=1e-5, abs=1e-8)


def test_probe_refuses_random_forward_layers():
    model = TinyHeads()
    model.dropout = torch.nn.Dropout(.2)
    with pytest.raises(ValueError, match='dropout'):
        hand_gradient_noise(model, None, cards=None, actions=None, extras=None, masks=None,
            selected_actions=None, old_log_probs=None, advantages=None, hand_lengths=[1, 1],
            num_groups=2, eps=.2, delta1=3., reference_kl_coef=0, entropy_coef=.005, entropy_floor=.05)
