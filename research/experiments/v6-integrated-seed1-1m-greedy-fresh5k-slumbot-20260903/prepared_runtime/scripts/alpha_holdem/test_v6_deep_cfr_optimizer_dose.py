import torch

from scripts.alpha_holdem.v6_deep_cfr_neural_smoke import _passive_network


def test_trainable_passive_initializer_has_live_hidden_features():
    torch.manual_seed(7)
    network = _passive_network()
    assert torch.count_nonzero(network.trunk[0].weight) > 0
    assert torch.count_nonzero(network.adv_head[0].weight) > 0
    assert torch.count_nonzero(network.adv_head[2].weight) == 0
    assert network.adv_head[2].bias[1] == 1


def test_trainable_passive_initializer_is_seed_reproducible():
    torch.manual_seed(11)
    first = _passive_network()
    torch.manual_seed(11)
    second = _passive_network()
    assert all(
        torch.equal(first.state_dict()[key], second.state_dict()[key])
        for key in first.state_dict()
    )
