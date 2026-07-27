from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
RUNNER = ROOT / "scripts" / "alpha_holdem" / "v5_ct002_runner_7fa29a5e2f003b9fe4236c23fdad2093.py"
SPEC = importlib.util.spec_from_file_location("v5_ct002_corrected_runner", RUNNER)
ct = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ct)


class DeterministicContractTests(unittest.TestCase):
    def test_golden_decks_and_permutation(self):
        deck0 = ct.deterministic_deck(0)
        deck_last = ct.deterministic_deck(29999)
        self.assertEqual(sorted(deck0), list(range(52)))
        self.assertEqual(hashlib.sha256(bytes(deck0)).hexdigest(),
                         "03e04e8aa4c0b80a5d9ef4b4a49efe00bd96b5c9c9f74299f982bb45c0894f6a")
        self.assertEqual(hashlib.sha256(bytes(deck_last)).hexdigest(),
                         "efd225627bcee21210ddc35586fde5324354eb85750208cb729cf867857e53dc")

    def test_action_row_and_pool_goldens(self):
        self.assertEqual(ct.action_u64("shared_hero", 17, 1, 3), 4949836912097489231)
        self.assertEqual(ct.treatment_opponent_id(17, 1), 103)
        self.assertEqual(
            ct.row_key(ct.ARMS[0], "heldout", 29999, 1, 7),
            "bb0e12fac2df976eb24536f34a56f62e3a9c6324f8213d6194ec74cb65cc325f",
        )
        self.assertEqual(
            ct.shuffle_key(0, "0" * 64),
            "ec3a907894b24f6f120b54a11ffbab8b52d4c3be9f8cb1cefe1e2ab07dd045cf",
        )

    def test_inverse_cdf_is_legal_only(self):
        probabilities = np.array([0.1, 0.2, 0.3, 0.4, 0, 0, 0, 0, 0], dtype=np.float64)
        mask = np.array([0, 1, 0, 1, 0, 0, 0, 0, 0], dtype=np.float32)
        self.assertEqual(ct.inverse_cdf_legal(probabilities, mask, 0), 1)
        self.assertEqual(ct.inverse_cdf_legal(probabilities, mask, (1 << 64) - 1), 3)

    def test_observation_round_trip(self):
        rng = np.random.default_rng(2026072214)
        obs = {
            "card_info": rng.normal(size=(6, 4, 13)).astype(np.float32),
            "action_info": rng.normal(size=(25, 4, 5)).astype(np.float32),
            "extra_info": rng.normal(size=2).astype(np.float32),
            "legal_mask": np.array([1, 1, 0, 1, 0, 0, 0, 0, 1], dtype=np.float32),
        }
        restored = ct.unpack_observation(ct.pack_observation(obs))
        for key, array in zip(("card_info", "action_info", "extra_info", "legal_mask"), restored):
            self.assertTrue(np.array_equal(obs[key], array))

    def test_assignment_goldens_and_proxy(self):
        expected_members = [115, 109, 120, 129, 115]
        self.assertEqual([ct.ppo_assignment(i)["member_id"] for i in range(35052, 35057)], expected_members)
        import random
        proxy = ct._AssignmentRandomProxy(random, 35052, {103: 4, 109: 0, 115: 1, 120: 2, 129: 3})
        observed = []
        for _ in range(5):
            draw = proxy.random()
            observed.append(-1 if draw < 0.2 else proxy.randint(0, 4))
        self.assertEqual(observed, [1, 0, 2, 3, 1])


class FrozenModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet
        cls.torch = torch
        cls.AlphaHoldemNet = AlphaHoldemNet
        cls.checkpoint = torch.load(ct.SOURCE_CHECKPOINT, map_location="cpu", weights_only=False)

    def test_source_and_pool_identities(self):
        self.assertEqual(ct.sha256_file(ct.SOURCE_CHECKPOINT), ct.SOURCE_SHA256)
        self.assertEqual(ct.state_dict_sha256(self.checkpoint["model"]), ct.SOURCE_MODEL_SHA256)
        pool = {int(item["id"]): item for item in self.checkpoint["pool_snapshots"]}
        self.assertEqual(set(pool), set(ct.POOL_IDS))
        for member_id in ct.POOL_IDS:
            self.assertEqual(ct.state_dict_sha256(pool[member_id]["state_dict"]), ct.POOL_HASHES[member_id])

    def test_value_only_step_preserves_actor_and_buffers(self):
        torch = self.torch
        model = ct._new_model(torch, self.AlphaHoldemNet, "cpu")
        model.load_state_dict(self.checkpoint["model"])
        model.eval()
        before = copy.deepcopy(model.state_dict())
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(name in ct.VALUE_NAMES)
        optimizer = torch.optim.Adam([parameter for parameter in model.parameters() if parameter.requires_grad], lr=1e-4)
        card = torch.zeros((4, 6, 4, 13))
        action = torch.zeros((4, 25, 4, 5))
        extra = torch.zeros((4, 2))
        mask = torch.ones((4, 9))
        baseline_logits, _ = model(card, action, extra, mask)
        _, values = model(card, action, extra, mask)
        loss = torch.mean((values.squeeze(-1) - torch.tensor([1.0, -1.0, 2.0, -2.0])) ** 2)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        after = model.state_dict()
        for name in before:
            if name not in ct.VALUE_NAMES:
                self.assertTrue(torch.equal(before[name], after[name]), name)
        after_logits, _ = model(card, action, extra, mask)
        self.assertTrue(torch.equal(baseline_logits, after_logits))

    def test_optimizer_transform_changes_only_value_moments(self):
        torch = self.torch
        model = ct._new_model(torch, self.AlphaHoldemNet, "cpu")
        model.load_state_dict(self.checkpoint["model"])
        original = self.checkpoint["optimizer"]
        transformed, value_ids = ct._zero_value_optimizer_moments(torch, original, model)
        self.assertEqual(len(value_ids), 2)
        for state_id, original_state in original["state"].items():
            new_state = transformed["state"][state_id]
            for key, value in original_state.items():
                if state_id in value_ids and key in ("exp_avg", "exp_avg_sq", "max_exp_avg_sq"):
                    self.assertEqual(int(torch.count_nonzero(new_state[key]).item()), 0)
                else:
                    self.assertTrue(torch.equal(value, new_state[key]) if torch.is_tensor(value) else value == new_state[key])


class StaticOrchestrationTests(unittest.TestCase):
    def test_ppo_argument_contract(self):
        args = ct.ppo_arguments(
            ct.ARMS[0], Path("resume.pt"), Path("run"), Path("out.pt"), Path("provenance.jsonl")
        )
        joined = " ".join(args)
        for required in (
            "--workers 22", "--hands-per-iter 16384", "--total-hands 581021901",
            "--env-version v55", "--ppo-epochs 4", "--mini-batch-size 1024",
            "--gamma 0.999", "--epsilon 0", "--entropy-coef 0.05", "--entropy-floor 0.3",
            "--self-play-fraction 0.2", "--opponent-assignment per-iteration",
            "--rollout-mode multi", "--rollout-envs-per-worker 16",
            "--worker-seed-base 84000", "--fixed-training-deal-stream",
            "--mirror-self-play-deals", "--allin-runout-ev-max-runouts 200",
            "--critic-contract critic_v1", "--value-coef 0.5", "--snapshot-every 1000000000",
            "--save-interval 1",
            "--seed 2026072217", "--max-runtime-seconds 10800", "--allow-resume", "--no-reset-optimizer",
        ):
            self.assertIn(required, joined)
        self.assertNotIn("--reset-hand-counter", args)
        self.assertFalse(any(arg.startswith("--lg") for arg in args))

    def test_clean_room_source_has_no_forbidden_derivation(self):
        source = RUNNER.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn("train_v5.py", source)
        self.assertNotIn("ae78e683c41a2abcff33eeae9fdad8ad", source)
        self.assertNotIn("lg001", source.lower())
        self.assertNotIn("lg002", source.lower())

    def test_probe_paths_are_write_free(self):
        source = RUNNER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        probe = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "contract_probe")
        calls = [node for node in ast.walk(probe) if isinstance(node, ast.Call)]
        forbidden_attributes = {"open", "mkdir", "write_text", "write_bytes", "touch", "unlink", "rename", "replace"}
        for call in calls:
            if isinstance(call.func, ast.Attribute):
                self.assertNotIn(call.func.attr, forbidden_attributes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
