import copy
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_forward_optimizer import make_model
from resume_contract import FLAG, VERSION, before_load, after_load, attach_snapshot, strip_reference_encoder


def config():
    return {FLAG: True, 'resume': 'bound-parent.pt', 'critic_contract': 'critic_v2', 'norm_layer': 'gn'}


def parent():
    model = make_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    return {'model': copy.deepcopy(model.state_dict()), 'optimizer': optimizer.state_dict(),
            'config': {}, 'total_hands': 12345, 'ppo_replay_entries': ['untouched-fixture']}


def restore(checkpoint):
    model = make_model()
    optimizer = torch.optim.Adam(model.parameters(), lr=.003)
    before_load(model, optimizer, checkpoint, config())
    model.load_state_dict(checkpoint['model'], strict=True)
    optimizer.load_state_dict(checkpoint['optimizer'])
    after_load(model, optimizer, checkpoint, config())
    return model, optimizer


def test_first_derivation_then_extended_resume():
    original = parent()
    model, optimizer = restore(original)
    assert optimizer.param_groups[0]['lr'] == 1e-4
    extended = dict(original, model=copy.deepcopy(model.state_dict()), optimizer=optimizer.state_dict(),
                    config=config(), observable_critic_contract=VERSION)
    again, again_optimizer = restore(extended)
    assert all(torch.equal(a, b) for a, b in zip(model.state_dict().values(), again.state_dict().values()))
    assert len(again_optimizer.param_groups[0]['params']) == len(list(again.parameters()))
    assert original['total_hands'] == extended['total_hands'] == 12345
    assert original['ppo_replay_entries'] == ['untouched-fixture']


@pytest.mark.parametrize('bad', ['missing_flag', 'missing_state', 'wrong_version', 'disabled'])
def test_inconsistent_resume_rejected(bad):
    original = parent()
    model, opt = restore(original)
    extended = dict(original, model=model.state_dict(), optimizer=opt.state_dict(),
                    config=config(), observable_critic_contract=VERSION)
    current = config()
    if bad == 'missing_flag': extended['config'] = {}
    if bad == 'missing_state': extended['model'] = original['model']
    if bad == 'wrong_version': extended['observable_critic_contract'] = 'unknown'
    if bad == 'disabled': current[FLAG] = False
    clean = make_model()
    with pytest.raises(ValueError):
        before_load(clean, torch.optim.Adam(clean.parameters()), extended, current)


def test_pool_snapshot_and_reference():
    model, _ = restore(parent())
    state = copy.deepcopy(model.state_dict())
    other = make_model()
    attach_snapshot(other, state)
    other.load_state_dict(state, strict=True)
    reference = strip_reference_encoder(copy.deepcopy(other))
    assert not hasattr(reference, 'observable_value_encoder')
    assert hasattr(other, 'observable_value_encoder')
    for key, value in reference.state_dict().items():
        assert torch.equal(value, state[key])
