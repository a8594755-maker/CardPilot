import copy
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha_holdem.train_mp3_hybrid_h1 import (
    preflop_context_masks,
    trinal_clip_ppo_update,
)
from scripts.alpha_holdem.train_v5 import configure_preflop_head_only_training


class FixedDataModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


class RoutedDataModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.preflop_policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        postflop = cards[:, 4].sum(dim=(1, 2)) >= 2.5
        postflop_logits = self.policy_head(extras)
        preflop_logits = self.preflop_policy_head(extras)
        logits = torch.where(postflop[:, None], postflop_logits, preflop_logits)
        return logits.masked_fill(masks <= 0, -1e9), self.value_head(extras)


def _state_arrays():
    cards = np.zeros((5, 6, 4, 13), dtype=np.float32)
    actions = np.zeros((5, 25, 4, 5), dtype=np.float32)

    # Row 0 has no history: SB first action.
    # Row 1 has one opponent raise: BB facing an open.
    actions[1, 0, 3, 0] = 1.0
    actions[1, 0, 1, 3] = 1.0
    # Row 2 has one opponent call, not an aggressive open.
    actions[2, 0, 3, 0] = 1.0
    actions[2, 0, 1, 2] = 1.0
    # Row 3 has two actions, so it is neither contextual first decision.
    actions[3, :2, 3, 0] = 1.0
    actions[3, 0, 1, 3] = 1.0
    # Row 4 is postflop even though its action history is empty.
    cards[4, 4, 0, :3] = 1.0
    return cards, actions


def test_preflop_context_masks_are_disjoint_and_public_state_exact():
    cards, actions = _state_arrays()
    postflop, sb_open, bb_vs_open = preflop_context_masks(cards, actions)
    assert postflop.tolist() == [False, False, False, False, True]
    assert sb_open.tolist() == [True, False, False, False, False]
    assert bb_vs_open.tolist() == [False, True, False, False, False]
    assert not np.any(sb_open & bb_vs_open)


def _transitions(source):
    cards, action_histories = _state_arrays()
    rows = []
    for index in range(80):
        context = index % 5
        extras = np.asarray(
            [context / 5.0, (index % 3) / 3.0, (index % 7) / 7.0],
            dtype=np.float32,
        )
        action = index % 9
        with torch.no_grad():
            logits, value_output = source(
                torch.tensor(cards[context]).unsqueeze(0),
                torch.tensor(action_histories[context]).unsqueeze(0),
                torch.tensor(extras).unsqueeze(0),
                torch.ones((1, 9)),
            )
            old_log_prob = float(logits[0].log_softmax(-1)[action])
            value = float(value_output.squeeze())
        rows.append(
            (
                cards[context],
                action_histories[context],
                extras,
                np.ones(9, np.float32),
                action,
                old_log_prob,
                float((index % 3) - 1),
                value,
                1.0,
                10.0,
                10.0,
                1.0,
            )
        )
    return rows


def test_context_priors_change_real_ppo_actor_and_report_both_losses():
    torch.set_num_threads(1)
    torch.manual_seed(811)
    source = FixedDataModel()
    models = [copy.deepcopy(source), copy.deepcopy(source)]
    transitions = _transitions(source)
    optimizers = [torch.optim.Adam(model.parameters(), lr=0.001) for model in models]
    results = []
    for coefficient, model, optimizer in zip((0.0, 0.01), models, optimizers):
        torch.manual_seed(812)
        np.random.seed(812)
        results.append(
            trinal_clip_ppo_update(
                model,
                optimizer,
                transitions,
                'cpu',
                epochs=1,
                mini_batch_size=16,
                critic_contract='critic_v2',
                preflop_sb_open_action_prior_coef=coefficient,
                preflop_bb_vs_open_action_prior_coef=coefficient,
            )
        )
    assert results[0]['preflop_sb_open_action_prior_loss'] == 0.0
    assert results[0]['preflop_bb_vs_open_action_prior_loss'] == 0.0
    assert results[1]['preflop_sb_open_action_prior_loss'] > 0.0
    assert results[1]['preflop_bb_vs_open_action_prior_loss'] > 0.0
    assert not torch.equal(models[0].policy_head.weight, models[1].policy_head.weight)


def test_preflop_head_only_real_update_preserves_postflop_logits_bitwise():
    torch.set_num_threads(1)
    torch.manual_seed(813)
    model = RoutedDataModel()
    transitions = _transitions(model)
    named = dict(model.named_parameters())
    postflop_weight_before = named['policy_head.weight'].detach().clone()
    preflop_weight_before = named['preflop_policy_head.weight'].detach().clone()
    cards, actions = _state_arrays()
    extras = torch.tensor([[0.0, 0.0, 0.0], [0.8, 0.0, 0.0]])
    masks = torch.ones((2, 9))
    with torch.no_grad():
        logits_before, _ = model(
            torch.tensor(cards[[0, 4]]),
            torch.tensor(actions[[0, 4]]),
            extras,
            masks,
        )
    trainable = configure_preflop_head_only_training(model)
    assert {name for name, parameter in model.named_parameters() if parameter.requires_grad} == {
        'preflop_policy_head.weight',
        'preflop_policy_head.bias',
        'value_head.weight',
        'value_head.bias',
    }
    optimizer = torch.optim.Adam(trainable, lr=0.001)
    torch.manual_seed(814)
    np.random.seed(814)
    result = trinal_clip_ppo_update(
        model,
        optimizer,
        transitions,
        'cpu',
        epochs=1,
        mini_batch_size=16,
        critic_contract='critic_v2',
        preflop_sb_open_action_prior_coef=0.01,
        preflop_bb_vs_open_action_prior_coef=0.01,
    )
    with torch.no_grad():
        logits_after, _ = model(
            torch.tensor(cards[[0, 4]]),
            torch.tensor(actions[[0, 4]]),
            extras,
            masks,
        )
    assert result['preflop_sb_open_action_prior_loss'] > 0.0
    assert result['preflop_bb_vs_open_action_prior_loss'] > 0.0
    assert torch.equal(named['policy_head.weight'], postflop_weight_before)
    assert not torch.equal(named['preflop_policy_head.weight'], preflop_weight_before)
    assert not torch.equal(logits_after[0], logits_before[0])
    assert torch.equal(logits_after[1], logits_before[1])
