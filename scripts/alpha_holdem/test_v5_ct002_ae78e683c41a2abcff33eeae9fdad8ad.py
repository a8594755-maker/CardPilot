#!/usr/bin/env python3
"""Deterministic no-output contract tests for canonical CT002 ae78."""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import v5_ct002_runner_ae78e683c41a2abcff33eeae9fdad8ad as runner


class CT002ContractTests(unittest.TestCase):
    def test_registration_and_clean_sources(self) -> None:
        prereg = runner.validate_registration_files()
        self.assertEqual(prereg["identity"]["token"], runner.TOKEN)
        self.assertEqual(len(prereg["frozen_inputs"]), 20)
        self.assertEqual(len(prereg["evaluation_tools"]), 8)

    def test_registered_arithmetic(self) -> None:
        self.assertEqual(len(runner.TRAIN_DEAL_RANGE) * 2, runner.TRAIN_HANDS_PER_ARM)
        self.assertEqual(len(runner.HELDOUT_DEAL_RANGE) * 2, runner.HELDOUT_HANDS_PER_ARM)
        self.assertEqual(runner.TRAIN_ROWS // runner.CALIBRATION_BATCH_SIZE * runner.CALIBRATION_EPOCHS, runner.CALIBRATION_UPDATES)
        self.assertEqual(runner.STAGE_A_TARGET_HANDS - runner.SOURCE_HANDS, 5_000_000)
        self.assertEqual(runner.POOL_ASCENDING_ORDER, sorted(runner.POOL_CHECKPOINT_ORDER))

    def test_deck_replay_golden(self) -> None:
        deck = runner.deterministic_deck(0)
        self.assertEqual(len(deck), 52)
        self.assertEqual(sorted(deck), list(range(52)))
        self.assertEqual(deck[:10], [11, 12, 21, 14, 18, 37, 36, 0, 31, 9])
        self.assertEqual(hashlib.sha256(bytes(deck)).hexdigest(), "48333c3db1358772ebb1970a713f80a554509be7689aede4cc638ff32516588f")
        self.assertNotEqual(runner.deterministic_deck(0), runner.deterministic_deck(1))

    def test_action_and_row_replay_golden(self) -> None:
        self.assertEqual(runner.action_u64("hero", 0, 0, 0), 4644989437213838645)
        self.assertEqual(runner.action_u64("control_opponent", 0, 0, 1), 2273333639682846079)
        self.assertEqual(
            runner.row_key("control", "train", 0, 0, 0),
            "c16e3fd16ab06e7593e0c172116f4752637e5d9acb59fc7d975fbab14a72480f",
        )
        self.assertNotEqual(
            runner.row_key("control", "train", 0, 0, 0),
            runner.row_key("treatment", "train", 0, 0, 0),
        )

    def test_inverse_cdf_legal_only(self) -> None:
        probabilities = [0.1, 0.2, 0.3, 0.4]
        mask = [0.0, 1.0, 0.0, 1.0]
        observed = {runner.inverse_cdf_index(probabilities, mask, value) for value in (0, 1 << 62, 1 << 63, (1 << 64) - 1)}
        self.assertTrue(observed <= {1, 3})
        self.assertIn(1, observed)
        self.assertIn(3, observed)

    def test_assignment_replay_and_facade(self) -> None:
        first = runner.ppo_assignment(35052)
        self.assertEqual(first, {"kind": "self", "member_id": -1, "local_index": -1, "u64": 264258065428502673})
        facade = runner.AssignmentRandomFacade(35052)
        for iteration in range(35052, 35152):
            expected = runner.ppo_assignment(iteration)
            fraction = facade.random()
            self.assertEqual(fraction < 0.2, expected["kind"] == "self")
            if expected["kind"] == "pool":
                self.assertEqual(facade.randint(0, 4), expected["local_index"])
                self.assertIn(expected["member_id"], runner.POOL_ASCENDING_ORDER)

    def test_calibration_order_is_epoch_specific_and_total(self) -> None:
        keys = [runner.row_key("control", "train", i, i % 2, 0) for i in range(100)]
        order0 = sorted(keys, key=lambda key: runner.calibration_order_key(0, key))
        order1 = sorted(keys, key=lambda key: runner.calibration_order_key(1, key))
        self.assertEqual(set(order0), set(keys))
        self.assertEqual(set(order1), set(keys))
        self.assertNotEqual(order0, order1)

    def test_runner_ast_has_no_forbidden_import(self) -> None:
        tree = ast.parse(Path(runner.__file__).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertNotIn("train_v5", imported)
        self.assertFalse(any(name.startswith("v5_lg001") or name.startswith("v5_lg002") for name in imported))

    def test_probe_contract_constants(self) -> None:
        self.assertEqual(runner.PROBE_NONCES, {"control": "2026072213", "treatment": "2026072214"})
        self.assertEqual(runner.DEVICE_MODE_PROBE, "CPU_ONLY_NO_GPU_NO_OUTPUT")
        self.assertEqual(runner.PYTHON_SHA256, "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a")

    def test_cpu_source_policy_and_value_head_isolation(self) -> None:
        import numpy as np
        import torch
        from alpha_holdem.environment_v55 import HUNLEnvironmentV55

        checkpoint, summary = runner.inspect_source_checkpoint()
        self.assertEqual(summary["model_state_sha256"], runner.SOURCE_MODEL_SHA256)
        model = runner.build_model(checkpoint["model"], "cpu")
        environment = HUNLEnvironmentV55(starting_stack=200.0)
        observation = runner.reset_with_deck(environment, runner.deterministic_deck(0))
        probabilities = runner.policy_probabilities(model, [observation], "cpu")[0]
        action = runner.inverse_cdf_index(
            probabilities, observation["legal_mask"], runner.action_u64("hero", 0, 0, 0),
        )
        self.assertGreater(float(observation["legal_mask"][action]), 0.0)

        non_value_before = runner.non_value_state_sha256(model)
        value_before = runner.state_dict_sha256({
            name: tensor for name, tensor in model.state_dict().items() if name.startswith("value_head.")
        })
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(name in {"value_head.weight", "value_head.bias"})
        optimizer = torch.optim.Adam(model.value_head.parameters(), lr=runner.CALIBRATION_LR)
        card = torch.as_tensor(np.stack([observation["card_info"]]), dtype=torch.float32)
        action_info = torch.as_tensor(np.stack([observation["action_info"]]), dtype=torch.float32)
        extra = torch.as_tensor(np.stack([observation["extra_info"]]), dtype=torch.float32)
        features = runner.trunk_features(model, card, action_info, extra)
        loss = torch.mean(model.value_head(features).squeeze(-1) ** 2)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        self.assertEqual(non_value_before, runner.non_value_state_sha256(model))
        value_after = runner.state_dict_sha256({
            name: tensor for name, tensor in model.state_dict().items() if name.startswith("value_head.")
        })
        self.assertNotEqual(value_before, value_after)
        transformed = runner.zero_value_optimizer_moments(checkpoint["optimizer"], model)
        self.assertEqual(len(transformed["param_groups"]), len(checkpoint["optimizer"]["param_groups"]))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CT002ContractTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"schema_version": "v5.ct002.unit_test.v1", "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "passed": result.wasSuccessful()}, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
