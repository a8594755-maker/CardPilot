from __future__ import annotations

import unittest
import sys
from pathlib import Path

import torch
from torch.utils.data import DataLoader, TensorDataset

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(THIS_DIR))

from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet as HybridAlphaHoldemNet
from distill_position_teachers import clone_with_position_adapter
from offline_slumbot_awr import evaluate, model_extras
from train_v5 import pack_position_extra


class PositionPolicyAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(7)
        self.base = AlphaHoldemNet(
            num_actions=9,
            norm_layer="gn",
            separate_preflop_head=True,
        )
        self.cards = torch.randn(4, 6, 4, 13)
        self.actions = torch.randn(4, 25, 4, 5)
        self.extras = torch.rand(4, 2)
        self.legal = torch.ones(4, 9)
        with torch.no_grad():
            self.base(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )
        self.expert = clone_with_position_adapter(self.base, 16)

    def test_zero_init_is_exactly_behavior_preserving(self) -> None:
        with torch.no_grad():
            expected, _ = self.base(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )
            for seat in (0.0, 1.0):
                observed, _ = self.expert(
                    self.cards,
                    self.actions,
                    torch.cat(
                        [
                            self.extras,
                            torch.full((4, 1), seat),
                        ],
                        dim=1,
                    ),
                    self.legal,
                )
                self.assertTrue(torch.equal(expected, observed))

    def test_legacy_network_ignores_appended_position_feature(self) -> None:
        with torch.no_grad():
            expected_logits, expected_value = self.base(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )
            observed_logits, observed_value = self.base(
                self.cards,
                self.actions,
                torch.cat(
                    [self.extras, torch.tensor([[0.0], [1.0], [0.0], [1.0]])],
                    dim=1,
                ),
                self.legal,
            )
        self.assertTrue(torch.equal(expected_logits, observed_logits))
        self.assertTrue(torch.equal(expected_value, observed_value))

    def test_training_extra_maps_engine_player_to_seat_feature(self) -> None:
        legacy = self.extras[0].numpy()
        bb = pack_position_extra(legacy, player=0)
        sb = pack_position_extra(legacy, player=1)
        self.assertEqual(bb.shape, (3,))
        self.assertTrue(torch.equal(torch.from_numpy(bb[:2]), self.extras[0]))
        self.assertEqual(float(bb[2]), 0.0)
        self.assertEqual(float(sb[2]), 1.0)

    def test_hybrid_trainer_network_position_adapter_is_zero_residual(self) -> None:
        torch.manual_seed(11)
        base = HybridAlphaHoldemNet(
            num_actions=9,
            norm_layer="gn",
            critic_contract="critic_v2",
            separate_preflop_head=True,
        )
        expert = HybridAlphaHoldemNet(
            num_actions=9,
            norm_layer="gn",
            critic_contract="critic_v2",
            separate_preflop_head=True,
            position_adapter_hidden=16,
        )
        with torch.no_grad():
            base(self.cards, self.actions, self.extras, self.legal)
            expert(
                self.cards,
                self.actions,
                torch.cat([self.extras, torch.zeros(4, 1)], dim=1),
                self.legal,
            )
            loaded = expert.load_state_dict(base.state_dict(), strict=False)
            expected, _ = base(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )
            observed, _ = expert(
                self.cards,
                self.actions,
                torch.cat([self.extras, torch.ones(4, 1)], dim=1),
                self.legal,
            )
        self.assertEqual(len(loaded.unexpected_keys), 0)
        self.assertEqual(len(loaded.missing_keys), 8)
        self.assertTrue(torch.equal(expected, observed))

    def test_bb_expert_cannot_change_sb_output(self) -> None:
        with torch.no_grad():
            baseline, _ = self.expert(
                self.cards,
                self.actions,
                torch.cat(
                    [self.extras, torch.ones(4, 1)],
                    dim=1,
                ),
                self.legal,
            )
            self.expert.position_policy_adapters[0][-1].bias[3] = 2.0
            bb_logits, _ = self.expert(
                self.cards,
                self.actions,
                torch.cat(
                    [self.extras, torch.zeros(4, 1)],
                    dim=1,
                ),
                self.legal,
            )
            sb_logits, _ = self.expert(
                self.cards,
                self.actions,
                torch.cat(
                    [self.extras, torch.ones(4, 1)],
                    dim=1,
                ),
                self.legal,
            )
        self.assertTrue(torch.equal(baseline, sb_logits))
        self.assertTrue(torch.allclose(bb_logits[:, 3], baseline[:, 3] + 2.0))

    def test_position_feature_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "seat feature"):
            self.expert(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )

    def test_offline_awr_appends_the_logged_seat(self) -> None:
        position = torch.tensor([0, 1, 0, 1], dtype=torch.long)
        observed = model_extras(self.expert, self.extras, position)
        self.assertTrue(torch.equal(observed[:, :2], self.extras))
        self.assertTrue(
            torch.equal(observed[:, 2], position.to(self.extras.dtype))
        )
        self.assertIs(model_extras(self.base, self.extras, position), self.extras)

    def test_offline_awr_validation_objective_supports_position_adapter(
        self,
    ) -> None:
        position = torch.tensor([0, 1, 0, 1], dtype=torch.long)
        with torch.no_grad():
            source_logits, _ = self.base(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
            )
            selected = source_logits.argmax(dim=-1)
            self.expert.position_policy_adapters[0][-1].bias[3] = 1.0
        loader = DataLoader(
            TensorDataset(
                self.cards,
                self.actions,
                self.extras,
                self.legal,
                selected,
                torch.ones(4),
                position,
                torch.zeros(4, dtype=torch.long),
            ),
            batch_size=4,
        )
        metrics = evaluate(
            self.expert,
            loader,
            "cpu",
            source=self.base,
        )
        self.assertGreater(metrics["source_kl"], 0.0)
        self.assertGreater(metrics["weighted_nll"], 0.0)


if __name__ == "__main__":
    unittest.main()
