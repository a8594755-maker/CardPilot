import numpy as np
import torch

from scripts.alpha_holdem.v6_deep_cfr_neural_smoke import _passive_network
from scripts.alpha_holdem.v6_deep_cfr_paper_loss_control import train_paper_loss
from scripts.deep_cfr.reservoir import AdvantageSample, ReservoirBuffer


def test_paper_loss_updates_fresh_network_with_finite_loss():
    torch.manual_seed(3)
    network = _passive_network()
    buffer = ReservoirBuffer(4)
    for iteration in (1, 2):
        target = np.zeros(9, dtype=np.float32)
        target[1] = float(iteration)
        buffer.add(AdvantageSample(
            state=np.zeros(56, dtype=np.float32),
            advantages=target,
            legal_mask=np.ones(9, dtype=np.float32),
            iteration=iteration,
        ))
    loss = train_paper_loss(network, buffer, 2, steps=2, batch_size=2, lr=0.001)
    assert np.isfinite(loss)
    assert loss > 0
