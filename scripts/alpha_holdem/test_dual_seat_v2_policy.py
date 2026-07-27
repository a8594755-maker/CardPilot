from __future__ import annotations

import unittest

import torch
import torch.nn as nn

from alpha_holdem.network_dual_seat_v2 import DualSeatAlphaHoldemNetV2


class _ContractActor(nn.Module):
    num_actions = 3

    def __init__(
        self,
        *,
        offset: float,
        position_aware: bool,
    ) -> None:
        super().__init__()
        self.offset = float(offset)
        self.position_adapter_hidden = 4 if position_aware else 0

    def forward(self, cards, actions, extra, legal_mask=None):
        expected_width = 3 if self.position_adapter_hidden > 0 else 2
        if extra.shape[1] != expected_width:
            raise ValueError(
                f"expected {expected_width} extra features, got {extra.shape[1]}"
            )
        row = extra.sum(dim=1, keepdim=True) + self.offset
        logits = row.expand(-1, self.num_actions).clone()
        value = row.clone()
        if legal_mask is not None:
            logits = logits + (1 - legal_mask) * -1e9
        return logits, value


class DualSeatV2PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cards = torch.zeros(4, 6, 4, 13)
        self.actions = torch.zeros(4, 25, 4, 5)
        self.extra = torch.tensor(
            [
                [0.10, 0.20, 0.0],
                [0.30, 0.40, 1.0],
                [0.50, 0.60, 0.0],
                [0.70, 0.80, 1.0],
            ]
        )
        self.legal = torch.ones(4, 3)

    def test_mixed_batch_preserves_legacy_and_position_contracts(self) -> None:
        sb = _ContractActor(offset=10.0, position_aware=True)
        bb = _ContractActor(offset=20.0, position_aware=False)
        model = DualSeatAlphaHoldemNetV2(sb_model=sb, bb_model=bb)

        logits, value = model(
            self.cards,
            self.actions,
            self.extra,
            self.legal,
        )
        sb_logits, sb_value = sb(
            self.cards,
            self.actions,
            self.extra,
            self.legal,
        )
        bb_logits, bb_value = bb(
            self.cards,
            self.actions,
            self.extra[:, :2],
            self.legal,
        )
        is_sb = self.extra[:, 2].bool()
        self.assertTrue(
            torch.equal(
                logits,
                torch.where(is_sb.unsqueeze(-1), sb_logits, bb_logits),
            )
        )
        self.assertTrue(
            torch.equal(
                value,
                torch.where(is_sb.unsqueeze(-1), sb_value, bb_value),
            )
        )

    def test_homogeneous_fast_paths_are_bitwise_direct(self) -> None:
        sb = _ContractActor(offset=10.0, position_aware=True)
        bb = _ContractActor(offset=20.0, position_aware=False)
        model = DualSeatAlphaHoldemNetV2(sb_model=sb, bb_model=bb)

        sb_extra = self.extra.clone()
        sb_extra[:, 2] = 1.0
        observed = model(self.cards, self.actions, sb_extra, self.legal)
        expected = sb(self.cards, self.actions, sb_extra, self.legal)
        self.assertTrue(torch.equal(observed[0], expected[0]))
        self.assertTrue(torch.equal(observed[1], expected[1]))

        bb_extra = self.extra.clone()
        bb_extra[:, 2] = 0.0
        observed = model(self.cards, self.actions, bb_extra, self.legal)
        expected = bb(self.cards, self.actions, bb_extra[:, :2], self.legal)
        self.assertTrue(torch.equal(observed[0], expected[0]))
        self.assertTrue(torch.equal(observed[1], expected[1]))

    def test_supports_two_position_aware_actors(self) -> None:
        model = DualSeatAlphaHoldemNetV2(
            sb_model=_ContractActor(offset=10.0, position_aware=True),
            bb_model=_ContractActor(offset=20.0, position_aware=True),
        )
        logits, _ = model(self.cards, self.actions, self.extra)
        self.assertTrue(torch.equal(logits[:, 0], torch.tensor([20.3, 11.7, 21.1, 12.5])))

    def test_requires_public_seat_feature(self) -> None:
        model = DualSeatAlphaHoldemNetV2(
            sb_model=_ContractActor(offset=10.0, position_aware=True),
            bb_model=_ContractActor(offset=20.0, position_aware=False),
        )
        with self.assertRaisesRegex(ValueError, "public seat"):
            model(
                self.cards[:1],
                self.actions[:1],
                self.extra[:1, :2],
            )


if __name__ == "__main__":
    unittest.main()
