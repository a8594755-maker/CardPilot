import copy
import importlib.util
from pathlib import Path
import sys

import pytest
import torch

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from observable_critic import attach_encoder, extend_optimizer
from prepare_network import prepare
from test_encoder import inputs

spec = importlib.util.spec_from_file_location('qualified_value_network', prepare())
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def make_model():
    torch.set_num_threads(1)
    torch.manual_seed(202609082)
    model = candidate.AlphaHoldemNet(norm_layer='gn', critic_contract='critic_v2',
        separate_preflop_head=True, preflop_trunk_gradient=True)
    model(*inputs(0))
    return model.eval()


@pytest.mark.parametrize('street', range(4))
def test_actual_forward_routes(street):
    model = make_model()
    args = inputs(street)
    mask = torch.ones(2, 9)
    mask[:, 4] = 0
    before = [x.detach().clone() for x in model(*args, legal_mask=mask)]
    attach_encoder(model)
    after = model(*args, legal_mask=mask)
    assert all(torch.equal(a, b) for a, b in zip(before, after))
    after[1].square().sum().backward()
    assert any(p.grad is not None and p.grad.abs().sum() > 0
               for p in model.observable_value_encoder.parameters())
    assert all(p.grad is None for n, p in model.named_parameters()
               if not n.startswith(('value_head.', 'observable_value_encoder.')))


def test_optimizer_disk_roundtrip_and_next_step(tmp_path):
    model = make_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    logits, value = model(*inputs(1))
    (logits.square().mean() + value.square().mean()).backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    old_parameters = list(model.parameters())
    old_states = {p: copy.deepcopy(optimizer.state[p]) for p in old_parameters}
    attach_encoder(model)
    receipt = extend_optimizer(model, optimizer)
    assert receipt['lr'] == 1e-4
    for p in old_parameters:
        for key, value in old_states[p].items():
            assert torch.equal(value, optimizer.state[p][key])
    assert all(p not in optimizer.state for p in model.observable_value_encoder.parameters())
    with pytest.raises(ValueError, match='order/scope'):
        extend_optimizer(model, optimizer)
    path = tmp_path / 'roundtrip.pt'
    torch.save({'model': model.state_dict(), 'optimizer': optimizer.state_dict()}, path)
    restored = make_model()
    attach_encoder(restored)
    restored_optimizer = torch.optim.Adam(restored.parameters(), lr=9e-3)
    state = torch.load(path, weights_only=True)
    restored.load_state_dict(state['model'], strict=True)
    restored_optimizer.load_state_dict(state['optimizer'])
    assert restored_optimizer.param_groups[0]['lr'] == 1e-4
    for net, opt in [(model, optimizer), (restored, restored_optimizer)]:
        opt.zero_grad(set_to_none=True)
        logits, value = net(*inputs(2))
        (logits.square().mean() + (value - .3).square().mean()).backward()
        opt.step()
    assert all(torch.equal(a, b) for a, b in zip(model.state_dict().values(), restored.state_dict().values()))
    for a, b in zip(optimizer.state_dict()['state'].values(), restored_optimizer.state_dict()['state'].values()):
        assert a.keys() == b.keys()
        assert all(torch.equal(a[k], b[k]) for k in a)


def test_unsupported_routes_fail_closed():
    model = make_model()
    attach_encoder(model)
    with pytest.raises(ValueError, match='forbids'):
        model(*inputs(1), critic_private_info=torch.zeros(2, 52))
    with pytest.raises(ValueError, match='forbids'):
        model(*inputs(1), return_action_q=True)
