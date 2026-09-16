"""Integration test: opt-in probes preserve the real PPO update on fixed data."""
import copy
import numpy as np
import torch

from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


class FixedDataModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


def test_real_ppo_updates_and_optimizer_are_bitwise_equal_with_probes():
    torch.set_num_threads(1)
    torch.manual_seed(41)
    model = FixedDataModel()
    reference = copy.deepcopy(model).eval()
    models = [copy.deepcopy(model), copy.deepcopy(model)]
    transitions = []
    for i in range(64):
        extras = np.array([i % 2, i % 3, (i % 7) / 7], dtype=np.float32)
        slot = i % 9
        with torch.no_grad():
            logits = model.policy_head(torch.tensor(extras))
            logp = float(logits.log_softmax(-1)[slot])
            value = float(model.value_head(torch.tensor(extras)).squeeze())
        transitions.append((np.zeros((6, 4, 13), np.float32),
                            np.zeros((25, 4, 5), np.float32), extras,
                            np.ones(9, np.float32), slot, logp,
                            float((i % 5) - 2), value, 1., 10., 10., 1.))
    optimizers = [torch.optim.Adam(m.parameters(), lr=0.001) for m in models]
    results = []
    rng = []
    for count, m, opt in zip([0, 2], models, optimizers):
        torch.manual_seed(52)
        np.random.seed(52)
        results.append(trinal_clip_ppo_update(
            m, opt, transitions, 'cpu', epochs=2, mini_batch_size=16,
            critic_contract='critic_v2', reference_policy=reference,
            reference_policy_kl_coef=1., gradient_diagnostic_minibatches=count))
        rng.append(torch.get_rng_state().clone())
    assert len(results[1]['gradient_diagnostics']) == 4
    assert results[0]['gradient_diagnostics'] == []
    assert torch.equal(rng[0], rng[1])
    for left, right in zip(models[0].parameters(), models[1].parameters()):
        assert torch.equal(left, right)
    for left, right in zip(optimizers[0].state.values(), optimizers[1].state.values()):
        for key in left:
            assert torch.equal(left[key], right[key])
    for key in ['policy_loss', 'value_loss', 'entropy', 'approx_kl', 'reference_policy_kl']:
        assert results[0][key] == results[1][key]
