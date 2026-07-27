from __future__ import annotations

import torch

from alpha_holdem.network import AlphaHoldemNet


def _inputs(board_cards: int):
    card = torch.zeros(2, 6, 4, 13)
    for index in range(board_cards):
        suit = index % 4
        rank = index // 4
        card[:, 4, suit, rank] = 1.0
    action = torch.zeros(2, 25, 4, 5)
    extra = torch.ones(2, 2)
    mask = torch.ones(2, 9)
    return card, action, extra, mask


def _init(model: AlphaHoldemNet) -> None:
    with torch.no_grad():
        model(*_inputs(0))


def test_zero_initialized_adapter_preserves_source_logits():
    torch.manual_seed(20260726)
    source = AlphaHoldemNet(separate_preflop_head=True)
    _init(source)

    torch.manual_seed(20260727)
    adapted = AlphaHoldemNet(
        separate_preflop_head=True,
        postflop_adapter_hidden=32,
    )
    _init(adapted)
    adapted.load_state_dict(source.state_dict(), strict=False)

    source.eval()
    adapted.eval()
    for board_cards in (0, 3, 4, 5):
        source_logits, _ = source(*_inputs(board_cards))
        adapted_logits, _ = adapted(*_inputs(board_cards))
        torch.testing.assert_close(adapted_logits, source_logits)


def test_adapter_changes_postflop_only_and_can_be_trained_in_isolation():
    torch.manual_seed(20260726)
    model = AlphaHoldemNet(
        separate_preflop_head=True,
        postflop_adapter_hidden=16,
    )
    _init(model)
    model.eval()

    preflop_before, _ = model(*_inputs(0))
    flop_before, _ = model(*_inputs(3))
    with torch.no_grad():
        model.postflop_policy_adapter[-1].bias[3] = 2.0
    preflop_after, _ = model(*_inputs(0))
    flop_after, _ = model(*_inputs(3))

    torch.testing.assert_close(preflop_after, preflop_before)
    assert torch.all(flop_after[:, 3] > flop_before[:, 3])

    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("postflop_policy_adapter."))
    loss = model(*_inputs(4))[0].square().mean()
    loss.backward()
    assert any(
        parameter.grad is not None
        for parameter in model.postflop_policy_adapter.parameters()
    )
    assert all(
        parameter.grad is None
        for name, parameter in model.named_parameters()
        if not name.startswith("postflop_policy_adapter.")
    )


def test_raw_preflop_adapter_is_zero_initialized_and_preflop_only():
    torch.manual_seed(20260728)
    source = AlphaHoldemNet(separate_preflop_head=True)
    _init(source)
    adapted = AlphaHoldemNet(
        separate_preflop_head=True,
        preflop_raw_adapter_hidden=32,
    )
    _init(adapted)
    adapted.load_state_dict(source.state_dict(), strict=False)
    source.eval()
    adapted.eval()

    for board_cards in (0, 3, 5):
        source_logits, _ = source(*_inputs(board_cards))
        adapted_logits, _ = adapted(*_inputs(board_cards))
        torch.testing.assert_close(adapted_logits, source_logits)

    with torch.no_grad():
        adapted.preflop_raw_policy_adapter[-1].bias[7] = 3.0
    preflop_source, _ = source(*_inputs(0))
    preflop_adapted, _ = adapted(*_inputs(0))
    river_source, _ = source(*_inputs(5))
    river_adapted, _ = adapted(*_inputs(5))
    assert torch.all(preflop_adapted[:, 7] > preflop_source[:, 7])
    torch.testing.assert_close(river_adapted, river_source)
