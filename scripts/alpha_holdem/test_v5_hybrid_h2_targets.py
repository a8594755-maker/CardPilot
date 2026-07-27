import math
import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from deep_cfr.game_state import GameConfig, HUNLGameState
from deep_cfr.hand_eval import card_from_str
from v5_hybrid_h2_targets import (
    deterministic_runouts,
    evaluate_7card_batch,
    h2_showdown_critic_target_pair,
    h2_showdown_critic_target_pairs,
    h2_showdown_critic_target,
    showdown_target_from_runouts,
)
from alpha_holdem.train_mp3_hybrid_h1 import prepare_h2_critic_returns


class H2TargetTests(unittest.TestCase):
    def make_terminal(self, hole0, hole1, final_board, stacks=(150.0, 150.0), folded=-1):
        state = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(hole0, hole1, final_board[:3])
        state.board = list(final_board)
        state.stacks = list(stacks)
        state.is_done = True
        state.folded_player = folded
        return state

    def test_turn_is_exhaustive_and_deterministic(self):
        h0 = (card_from_str("As"), card_from_str("Ah"))
        h1 = (card_from_str("Ks"), card_from_str("Kh"))
        board = (card_from_str("2c"), card_from_str("7d"), card_from_str("9h"), card_from_str("Tc"))
        first = deterministic_runouts(h0, h1, board, deal_identity="d1", seat=0, row_index=2)
        second = deterministic_runouts(h0, h1, board, deal_identity="d1", seat=0, row_index=2)
        self.assertEqual(first, second)
        self.assertTrue(first[1])
        self.assertEqual(len(first[0]), 44)

    def test_preflop_is_unique_bounded_and_identity_keyed(self):
        h0 = (card_from_str("As"), card_from_str("Ah"))
        h1 = (card_from_str("Ks"), card_from_str("Kh"))
        a = deterministic_runouts(h0, h1, (), deal_identity="d1", seat=0, row_index=0)
        b = deterministic_runouts(h0, h1, (), deal_identity="d1", seat=0, row_index=0)
        c = deterministic_runouts(h0, h1, (), deal_identity="d2", seat=0, row_index=0)
        self.assertEqual(a, b)
        self.assertNotEqual(a[0], c[0])
        self.assertFalse(a[1])
        self.assertEqual(len(a[0]), 200)
        self.assertEqual(len(set(a[0])), 200)

    def test_seat_targets_are_zero_sum_at_equal_commitment(self):
        h0 = (card_from_str("As"), card_from_str("Ah"))
        h1 = (card_from_str("Ks"), card_from_str("Kh"))
        board = (card_from_str("2c"), card_from_str("7d"), card_from_str("9h"), card_from_str("Tc"))
        runouts, _, _ = deterministic_runouts(h0, h1, board, deal_identity="d1", seat=0, row_index=1)
        p0 = showdown_target_from_runouts(h0, h1, board, runouts, seat=0, hero_committed=50, villain_committed=50)[0]
        p1 = showdown_target_from_runouts(h0, h1, board, runouts, seat=1, hero_committed=50, villain_committed=50)[0]
        self.assertAlmostEqual(p0, -p1, places=12)

    def test_fold_and_river_rows_are_ineligible(self):
        h0 = (card_from_str("As"), card_from_str("Ah"))
        h1 = (card_from_str("Ks"), card_from_str("Kh"))
        board = [card_from_str(x) for x in ("2c", "7d", "9h", "Tc", "4s")]
        folded = self.make_terminal(h0, h1, board, folded=1)
        self.assertIsNone(h2_showdown_critic_target(folded, seat=0, row_board=board[:3], row_index=0, deal_identity="d", hero_committed=50, villain_committed=50))
        showdown = self.make_terminal(h0, h1, board)
        self.assertIsNone(h2_showdown_critic_target(showdown, seat=0, row_board=board, row_index=0, deal_identity="d", hero_committed=50, villain_committed=50))

    def test_common_runout_pair_is_zero_sum_for_equal_commitment(self):
        h0 = (card_from_str("As"), card_from_str("Ah"))
        h1 = (card_from_str("Ks"), card_from_str("Kh"))
        board = [card_from_str(x) for x in ("2c", "7d", "9h", "Tc", "4s")]
        state = self.make_terminal(h0, h1, board)
        result = h2_showdown_critic_target_pair(
            state, row_board=board[:3], deal_identity="d", committed=(50, 50)
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["target_bb"][0], -result["target_bb"][1], places=12)
        batch = h2_showdown_critic_target_pairs(
            state,
            row_boards=[(), board[:3], board[:3], board[:4], board],
            deal_identity="d",
            committed=(50, 50),
        )
        self.assertEqual(set(batch), {(), tuple(board[:3]), tuple(board[:4]), tuple(board)})
        self.assertIsNone(batch[tuple(board)])
        for key in ((), tuple(board[:3]), tuple(board[:4])):
            self.assertAlmostEqual(batch[key]["target_bb"][0], -batch[key]["target_bb"][1], places=12)

    def test_critic_override_does_not_change_actor_advantages(self):
        rewards = np.array([0.0, 10.0, 0.0, -4.0])
        values = np.array([1.0, 2.0, -1.0, -2.0])
        dones = np.array([0.0, 1.0, 0.0, 1.0])
        overrides = np.array([3.0, math.nan, math.nan, -2.0])
        advantages, baseline_returns, critic_returns, mask = prepare_h2_critic_returns(
            rewards, values, dones, overrides, gamma=0.999
        )
        from alpha_holdem.train_mp3_hybrid_h1 import compute_gae
        expected_advantages, expected_returns = compute_gae(rewards, values, dones, gamma=0.999)
        np.testing.assert_allclose(advantages, expected_advantages)
        np.testing.assert_allclose(baseline_returns, expected_returns)
        self.assertEqual(mask.tolist(), [True, False, False, True])
        self.assertEqual(critic_returns[0], 3.0)
        self.assertEqual(critic_returns[3], -2.0)
        np.testing.assert_allclose(critic_returns[~mask], expected_returns[~mask])

    def test_vectorized_evaluator_matches_treys(self):
        from deep_cfr.hand_eval import evaluate
        rng = np.random.default_rng(2026071401)
        cards = np.stack([rng.choice(52, size=7, replace=False) for _ in range(2000)])
        fast = evaluate_7card_batch(cards)
        slow = np.array([evaluate(tuple(map(int, row[:2])), list(map(int, row[2:]))) for row in cards])
        for i in range(len(cards)):
            for j in range(i + 1, min(i + 8, len(cards))):
                self.assertEqual(int(np.sign(fast[i] - fast[j])), int(np.sign(slow[j] - slow[i])))


if __name__ == "__main__":
    unittest.main()
