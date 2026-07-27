from __future__ import annotations
import copy
import io
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from alpha_holdem.network import AlphaHoldemNet as BaselineNet
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2
from alpha_holdem.train_mp3_hybrid_h1 import compute_gae, prepare_h1_critic_arrays
from v5_hybrid_h1_critic import actor_key, initialize_model, migrate_v1_checkpoint_to_v2

def inputs(batch=4):
    generator = torch.Generator().manual_seed(123)
    return (torch.randn(batch, 6, 4, 13, generator=generator), torch.randn(batch, 25, 4, 5, generator=generator), torch.randn(batch, 2, generator=generator), torch.ones(batch, 9))

def initialized(contract):
    model = AlphaHoldemNet(critic_contract=contract)
    initialize_model(model)
    return model

class HybridH1CriticTest(unittest.TestCase):
    def test_control_network_is_bitwise_equivalent(self):
        torch.manual_seed(9)
        baseline = BaselineNet()
        with torch.no_grad(): baseline(*inputs()[:3])
        candidate = initialized(CRITIC_V1)
        candidate.load_state_dict(baseline.state_dict())
        with torch.no_grad():
            b_logits, b_value = baseline(*inputs())
            c_logits, c_value = candidate(*inputs())
        self.assertTrue(torch.equal(b_logits, c_logits))
        self.assertTrue(torch.equal(b_value, c_value))

    def test_critic_v2_initialization_is_deterministic(self):
        a = initialized(CRITIC_V2)
        b = initialized(CRITIC_V2)
        for (na, pa), (nb, pb) in zip(a.value_head.named_parameters(), b.value_head.named_parameters()):
            self.assertEqual(na, nb)
            self.assertTrue(torch.equal(pa, pb))

    def test_critic_v2_value_gradient_is_isolated(self):
        model = initialized(CRITIC_V2)
        _, value = model(*inputs())
        value.square().mean().backward()
        self.assertTrue(any(p.grad is not None for p in model.value_head.parameters()))
        upstream = [(n, p.grad) for n, p in model.named_parameters() if actor_key(n)]
        self.assertTrue(all(grad is None for _, grad in upstream))

    def test_critic_v1_value_gradient_reaches_trunk(self):
        model = initialized(CRITIC_V1)
        _, value = model(*inputs())
        value.square().mean().backward()
        self.assertTrue(any(p.grad is not None for p in model.trunk.parameters()))

    def test_scaling_and_gae_are_linear(self):
        rewards = np.array([0.0, 0.0, 80.0, 0.0, -25.0])
        values = np.array([2.0, 3.0, 4.0, -1.0, -2.0])
        dones = np.array([0.0, 0.0, 1.0, 0.0, 1.0])
        chips = np.full(5, 200.0)
        raw_adv, raw_ret = compute_gae(rewards, values, dones)
        rew, val, d2, d3, scale = prepare_h1_critic_arrays(rewards, values, chips, chips, critic_contract=CRITIC_V2, effective_stack_divisor=200.0)
        norm_adv, norm_ret = compute_gae(rew, val, dones)
        np.testing.assert_allclose(norm_adv, raw_adv / 200.0, rtol=1e-6, atol=1e-9)
        np.testing.assert_allclose(norm_ret, raw_ret / 200.0, rtol=1e-6, atol=1e-9)
        np.testing.assert_allclose(d2, 1.0)
        np.testing.assert_allclose(d3, 1.0)
        self.assertEqual(scale, 200.0)

    def test_wrong_scaling_fails_closed(self):
        with self.assertRaises(ValueError):
            prepare_h1_critic_arrays([1], [0], [1], [1], critic_contract=CRITIC_V2, effective_stack_divisor=100.0)

    def test_actor_and_optimizer_migration_is_exact(self):
        source = initialized(CRITIC_V1)
        optimizer = torch.optim.Adam(source.parameters(), lr=3e-4)
        logits, value = source(*inputs())
        (logits.square().mean() + value.square().mean()).backward()
        optimizer.step()
        checkpoint = {'model': copy.deepcopy(source.state_dict()), 'optimizer': copy.deepcopy(optimizer.state_dict())}
        target = initialized(CRITIC_V2)
        target_optimizer = torch.optim.Adam(target.parameters(), lr=3e-4)
        report = migrate_v1_checkpoint_to_v2(model=target, optimizer=target_optimizer, checkpoint=checkpoint, device='cpu')
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['new_critic_optimizer_state_count'], 0)
        source.eval()
        target.eval()
        with torch.no_grad():
            source_logits, _ = source(*inputs())
            target_logits, _ = target(*inputs())
        self.assertTrue(torch.equal(source_logits, target_logits))
        for name, tensor in target.state_dict().items():
            if actor_key(name): self.assertTrue(torch.equal(tensor, checkpoint['model'][name]))
        critic_params = {p for n, p in target.named_parameters() if not actor_key(n)}
        self.assertTrue(all(p not in target_optimizer.state for p in critic_params))

    def test_checkpoint_roundtrip(self):
        buffer = io.BytesIO()
        model = initialized(CRITIC_V2)
        torch.save({'model': model.state_dict(), 'critic_contract': CRITIC_V2}, buffer)
        buffer.seek(0)
        loaded = torch.load(buffer, map_location='cpu', weights_only=False)
        restored = initialized(CRITIC_V2)
        restored.load_state_dict(loaded['model'])
        for left, right in zip(model.state_dict().values(), restored.state_dict().values()):
            self.assertTrue(torch.equal(left, right))

if __name__ == '__main__': unittest.main()