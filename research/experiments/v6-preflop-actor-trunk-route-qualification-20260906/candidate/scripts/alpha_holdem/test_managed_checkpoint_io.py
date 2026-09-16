from pathlib import Path

import pytest
import torch

from scripts.alpha_holdem.managed_checkpoint_io import atomic_torch_save


def test_atomic_checkpoint_roundtrip(tmp_path):
    target = tmp_path / 'latest.pt'
    atomic_torch_save({'step': 9, 'value': torch.tensor([1., 2.])}, target)
    loaded = torch.load(target, weights_only=False)
    assert loaded['step'] == 9
    assert torch.equal(loaded['value'], torch.tensor([1., 2.]))
    assert list(tmp_path.iterdir()) == [target]


def test_interrupted_serialization_preserves_previous_file(tmp_path, monkeypatch):
    target = tmp_path / 'latest.pt'
    atomic_torch_save({'step': 9}, target)
    prior = target.read_bytes()

    def interrupted(payload, handle):
        handle.write(b'incomplete checkpoint')
        raise KeyboardInterrupt()

    monkeypatch.setattr(torch, 'save', interrupted)
    with pytest.raises(KeyboardInterrupt):
        atomic_torch_save({'step': 10}, target)
    assert target.read_bytes() == prior
    assert list(tmp_path.iterdir()) == [target]


def test_failed_replace_preserves_previous_file(tmp_path, monkeypatch):
    import scripts.alpha_holdem.managed_checkpoint_io as module
    target = tmp_path / 'latest.pt'
    atomic_torch_save({'step': 9}, target)
    prior = target.read_bytes()

    def failed(*args):
        raise PermissionError('simulated reader/OS contention')

    monkeypatch.setattr(module.os, 'replace', failed)
    with pytest.raises(PermissionError):
        atomic_torch_save({'step': 10}, target)
    assert target.read_bytes() == prior
    assert list(tmp_path.iterdir()) == [target]
