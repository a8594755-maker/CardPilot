from __future__ import annotations

import unittest

import torch
import torch.nn as nn

from alpha_holdem.network_dual_seat import DualSeatAlphaHoldemNet


class _ConstantActor(nn.Module):
    num_actions = 3

    def __init__(self, value: float) -> None:
        super().__init__()
        self.register_buffer("output", torch.full((3,), value))

    def forward(self, cards, actions, extra, legal_mask=None):
        logits = self.output.expand(cards.shape[0], -1)
        value = torch.full(
            (cards.shape[0], 1),
            float(self.output[0]),
            device=cards.device,
        )
        if legal_mask is not None:
            logits = logits + (1 - legal_mask) * -1e9
        return logits, value


class DualSeatPolicyTest(unittest.TestCase):
    def test_routes_each_batch_row_inside_forward(self) -> None:
        model = DualSeatAlphaHoldemNet(
            sb_model=_ConstantActor(7.0),
            bb_model=_ConstantActor(3.0),
        )
        cards = torch.zeros(4, 6, 4, 13)
        actions = torch.zeros(4, 25, 4, 5)
        extra = torch.tensor(
            [[1.0, 1.0, 0.0], [1.0, 1.0, 1.0]] * 2
        )
        logits, value = model(cards, actions, extra)
        self.assertTrue(torch.equal(logits[:, 0], torch.tensor([3., 7., 3., 7.])))
        self.assertTrue(torch.equal(value[:, 0], torch.tensor([3., 7., 3., 7.])))

    def test_requires_public_seat_feature(self) -> None:
        model = DualSeatAlphaHoldemNet(
            sb_model=_ConstantActor(7.0),
            bb_model=_ConstantActor(3.0),
        )
        with self.assertRaisesRegex(ValueError, "public seat"):
            model(
                torch.zeros(1, 6, 4, 13),
                torch.zeros(1, 25, 4, 5),
                torch.zeros(1, 2),
            )


if __name__ == "__main__":
    unittest.main()
