import copy

import numpy as np
import pytest
import torch

from scripts.alpha_holdem.train_mp3_hybrid_h1 import (
    minimum_norm_actor_gradient,
    multi_objective_gradient_diagnostics,
    trinal_clip_ppo_update,
)


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


def make_transitions(model, count=48, legacy_prefix=0):
    transitions = []
    for i in range(count):
        extras = np.array([i % 2, i % 3, (i % 7) / 7], dtype=np.float32)
        action = i % 9
        with torch.no_grad():
            logits, value = model(
                torch.zeros((1, 6, 4, 13)),
                torch.zeros((1, 25, 4, 5)),
                torch.tensor(extras).unsqueeze(0),
                torch.ones((1, 9)),
            )
            log_prob = float(logits.log_softmax(-1)[0, action])
            old_value = float(value[0, 0])
        base = (
            np.zeros((6, 4, 13), np.float32),
            np.zeros((25, 4, 5), np.float32),
            extras,
            np.ones(9, np.float32),
            action,
            log_prob,
            float((i % 5) - 2),
            old_value,
            1.0,
            10.0,
            10.0,
            1.0,
        )
        if i < legacy_prefix:
            transitions.append(base)
        else:
            transitions.append(
                base + (np.nan, i % 2, np.nan, np.nan, (i // 2) % 4 - 1)
            )
    return transitions


def test_multi_objective_geometry_drops_zero_without_mutating_grads():
    model = TinyModel()
    before = [parameter.grad for parameter in model.parameters()]
    positive = model.policy_head.weight.sum()
    negative = -model.policy_head.weight[:, :1].sum()
    result = multi_objective_gradient_diagnostics(
        model,
        {'positive': positive, 'negative': negative, 'zero': positive * 0.0},
        positive + negative,
    )
    assert result['objective_names'] == ['positive', 'negative']
    assert result['zero_gradient_objectives'] == ['zero']
    assert result['pairwise_negative_count'] == 1
    assert len(result['aggregate_alignments']) == 2
    assert all(parameter.grad is old for parameter, old in zip(model.parameters(), before))


def test_minimum_norm_actor_gradient_is_common_descent_and_norm_matched():
    model = TinyModel()
    weight = model.policy_head.weight
    objective_a = weight[0, 0]
    objective_b = weight[0, 1]
    aggregate = 2.0 * objective_a + objective_b
    parameters, gradients, report = minimum_norm_actor_gradient(
        model,
        {'a': objective_a, 'b': objective_b},
        aggregate,
    )
    assert len(parameters) == len(gradients)
    assert report['simplex_weights'] == pytest.approx([0.5, 0.5])
    assert report['worst_intervention_alignment'] == pytest.approx(2**-0.5)
    assert report['intervention_actor_gradient_l2'] == pytest.approx(
        report['ordinary_actor_gradient_l2']
    )
    assert all(parameter.grad is None for parameter in model.parameters())


def test_opponent_seat_probe_accepts_legacy_replay_and_records_coverage():
    torch.manual_seed(23)
    source = TinyModel()
    model = copy.deepcopy(source)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    transitions = make_transitions(source, legacy_prefix=12)
    result = trinal_clip_ppo_update(
        model,
        optimizer,
        transitions,
        'cpu',
        epochs=1,
        mini_batch_size=len(transitions),
        critic_contract='critic_v2',
        reference_policy=source,
        reference_policy_kl_coef=1.0,
        opponent_seat_gradient_diagnostic_minibatches=1,
    )
    diagnostics = result['opponent_seat_gradient_diagnostics']
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic['known_identity_policy_rows'] == 36
    assert diagnostic['unknown_identity_policy_rows'] == 12
    assert diagnostic['known_identity_fraction'] == pytest.approx(0.75)
    assert 'source_kl' in (
        diagnostic['objective_names'] + diagnostic['zero_gradient_objectives']
    )
    assert any(name.startswith('pool0_seat') for name in diagnostic['objective_names'])


def test_opponent_seat_probe_rejects_all_legacy_transitions():
    model = TinyModel()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    with pytest.raises(ValueError, match='at least one transition'):
        trinal_clip_ppo_update(
            model,
            optimizer,
            make_transitions(model, count=8, legacy_prefix=8),
            'cpu',
            epochs=1,
            mini_batch_size=8,
            critic_contract='critic_v2',
            opponent_seat_gradient_diagnostic_minibatches=1,
        )


def test_online_mgda_reports_strict_common_descent_update():
    torch.manual_seed(29)
    source = TinyModel()
    model = copy.deepcopy(source)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    result = trinal_clip_ppo_update(
        model,
        optimizer,
        make_transitions(source),
        'cpu',
        epochs=1,
        mini_batch_size=48,
        critic_contract='critic_v2',
        reference_policy=source,
        reference_policy_kl_coef=1.0,
        opponent_seat_mgda=True,
    )
    reports = result['opponent_seat_mgda_updates']
    assert len(reports) == 1
    report = reports[0]
    assert report['worst_intervention_alignment'] > 0.0
    assert report['kkt_min_product_minus_objective'] >= -1e-7
    assert report['intervention_actor_gradient_l2'] == pytest.approx(
        report['ordinary_actor_gradient_l2'], rel=1e-5
    )


def test_online_mgda_rejects_legacy_replay_identity():
    model = TinyModel()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    with pytest.raises(ValueError, match='identity-complete replay'):
        trinal_clip_ppo_update(
            model,
            optimizer,
            make_transitions(model, count=8, legacy_prefix=1),
            'cpu',
            epochs=1,
            mini_batch_size=8,
            critic_contract='critic_v2',
            reference_policy=model,
            reference_policy_kl_coef=1.0,
            opponent_seat_mgda=True,
        )
