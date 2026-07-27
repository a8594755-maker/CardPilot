from __future__ import annotations

import sys
import stat
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import numpy as np
import torch
import torch.nn as nn

from v5_exp_w1_value_warmup import run_value_head_warmup, write_immutable_report


class TinyActorCritic(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = nn.Linear(814, 8)
        self.policy_head = nn.Linear(8, 9)
        self.value_head = nn.Linear(8, 1)

    def forward(self, cards, actions, extras, masks=None):
        flat = torch.cat((cards.flatten(1), actions.flatten(1), extras), dim=1)
        hidden = torch.tanh(self.encoder(flat))
        logits = self.policy_head(hidden)
        if masks is not None:
            logits = logits + (1.0 - masks) * -1e9
        return logits, self.value_head(hidden)


def fake_gae(rewards, values, dones, gamma):
    del values, dones, gamma
    returns = np.asarray(rewards, dtype=np.float32)
    return returns.copy(), returns.copy()


def transitions(count=40):
    rng = np.random.default_rng(7)
    rows = []
    for index in range(count):
        cards = rng.normal(size=(6, 4, 13)).astype(np.float32)
        actions = rng.normal(size=(25, 4, 5)).astype(np.float32)
        extras = rng.normal(size=(2,)).astype(np.float32)
        mask = np.ones(9, dtype=np.float32)
        reward = float(0.25 * extras[0] - 0.1 * extras[1] + cards.mean())
        rows.append((cards, actions, extras, mask, 1, 0.0, reward, 0.0, 1.0, 100.0, 100.0, 1.0))
    return rows


class ExpW1WarmupTest(unittest.TestCase):
    def test_value_only_pass_preserves_policy_and_nonvalue_state(self):
        torch.manual_seed(11)
        model = TinyActorCritic()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.03)
        fixture = transitions()
        cards = torch.as_tensor(np.stack([row[0] for row in fixture[:4]]))
        actions = torch.as_tensor(np.stack([row[1] for row in fixture[:4]]))
        extras = torch.as_tensor(np.stack([row[2] for row in fixture[:4]]))
        masks = torch.as_tensor(np.stack([row[3] for row in fixture[:4]]))
        logits, values = model(cards, actions, extras, masks)
        optimizer.zero_grad(set_to_none=True)
        (logits.mean() + values.mean()).backward()
        optimizer.step()
        result = run_value_head_warmup(
            model=model,
            optimizer=optimizer,
            transitions=fixture,
            device="cpu",
            compute_gae_fn=fake_gae,
            epochs=30,
            mini_batch_size=8,
            gamma=0.999,
            heldout_fraction=0.25,
            min_relative_mse_reduction=0.001,
            split_seed=99,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["policy_logits_max_abs_delta"], 0.0)
        self.assertTrue(result["checks"]["non_value_model_state_bitwise_unchanged"])
        self.assertTrue(result["checks"]["non_value_optimizer_state_unchanged"])
        self.assertGreater(result["value_head_max_abs_delta"], 0.0)

    def test_missing_actual_hand_marker_fails_closed(self):
        bad = [row[:11] for row in transitions()]
        with self.assertRaisesRegex(ValueError, "actual-hand markers"):
            run_value_head_warmup(
                model=TinyActorCritic(),
                optimizer=torch.optim.Adam(TinyActorCritic().parameters(), lr=0.01),
                transitions=bad,
                device="cpu",
                compute_gae_fn=fake_gae,
                epochs=1,
                mini_batch_size=8,
                gamma=0.999,
                heldout_fraction=0.2,
                min_relative_mse_reduction=0.01,
                split_seed=1,
            )

    def test_report_is_write_once(self):
        path = Path.cwd() / "reports" / "test_exp_w1_immutable_report.json"
        if path.exists():
            path.chmod(stat.S_IWRITE)
            path.unlink()
        try:
            digest = write_immutable_report(path, {"status": "PASS"})
            self.assertEqual(len(digest), 64)
            with self.assertRaises(FileExistsError):
                write_immutable_report(path, {"status": "FAIL"})
        finally:
            if path.exists():
                path.chmod(stat.S_IWRITE)
                path.unlink()

    def test_candidate_trainer_is_isolated_and_machine_gated(self):
        candidate = (SCRIPT_DIR / "train_v5_exp_w1.py").read_text(encoding="utf-8")
        live = (SCRIPT_DIR / "train_v5.py").read_text(encoding="utf-8")
        self.assertNotIn("--exp-w1-value-warmup-epochs", live)
        for marker in (
            "--exp-w1-value-warmup-epochs",
            "--exp-w1-design-lock",
            "EXP-W1 immutable design-lock identity/hash mismatch",
            "EXP-W1 treatment requires --resume, --allow-resume and --no-reset-optimizer",
            "EXP-W1 warmup missed exact iteration",
            "write_immutable_report",
            "'exp_w1_value_warmup': exp_w1_warmup_state",
        ):
            self.assertIn(marker, candidate)


if __name__ == "__main__":
    unittest.main()
