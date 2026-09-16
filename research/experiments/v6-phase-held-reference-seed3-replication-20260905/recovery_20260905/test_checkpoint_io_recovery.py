import ctypes
from ctypes import wintypes
import errno
import os
from pathlib import Path
import random
import threading
import time

import pytest
import torch

import checkpoint_io_candidate as candidate
import train_with_checkpoint_io as wrapper


def winerror(code=5):
    error = PermissionError('synthetic native file access denial')
    error.winerror = code
    return error


def test_roundtrip_and_no_training_rng_advance(tmp_path):
    rng = random.getstate()
    torch_rng = torch.get_rng_state().clone()
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 1, 'tensor': torch.ones(3)}, target)
    assert torch.equal(torch.load(target, weights_only=False)['tensor'], torch.ones(3))
    assert random.getstate() == rng
    assert torch.equal(torch.get_rng_state(), torch_rng)
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('code', [5, 32, 33])
def test_transient_retry_serializes_exactly_once(tmp_path, monkeypatch, code):
    replace, save = candidate.os.replace, torch.save
    calls = {'replace': 0, 'save': 0}
    def held(source, target):
        calls['replace'] += 1
        if calls['replace'] < 3:
            raise winerror(code)
        return replace(source, target)
    def once(payload, handle):
        calls['save'] += 1
        return save(payload, handle)
    monkeypatch.setattr(candidate, 'WINDOWS', True)
    monkeypatch.setattr(candidate.os, 'replace', held)
    monkeypatch.setattr(torch, 'save', once)
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 2}, target)
    assert calls == {'replace': 3, 'save': 1}
    assert torch.load(target, weights_only=False)['iteration'] == 2


def test_permanent_failure_preserves_old_and_durable_new(tmp_path, monkeypatch):
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 1}, target)
    before = target.read_bytes()
    calls = []
    def denied(*args):
        calls.append(args)
        raise winerror()
    monkeypatch.setattr(candidate.os, 'replace', denied)
    with pytest.raises(PermissionError) as caught:
        candidate.atomic_torch_save({'iteration': 2}, target, replace_timeout_seconds=0)
    assert len(calls) == 1 and target.read_bytes() == before
    pending, = tmp_path.glob('*.pending')
    assert torch.load(pending, weights_only=False)['iteration'] == 2
    assert str(pending) in caught.value.__notes__[0]


def test_attempt_cap_is_independent_of_deadline(tmp_path, monkeypatch):
    calls = []
    def denied(*args):
        calls.append(args)
        raise winerror()
    monkeypatch.setattr(candidate.os, 'replace', denied)
    with pytest.raises(PermissionError):
        candidate.atomic_torch_save({'iteration': 2}, tmp_path / 'latest.pt', max_replace_attempts=2)
    assert len(calls) == 2


@pytest.mark.parametrize('error', [OSError(errno.EIO, 'I/O error'), PermissionError('no native code')])
def test_nonretryable_error_is_not_hidden(tmp_path, monkeypatch, error):
    def denied(*args):
        raise error
    monkeypatch.setattr(candidate.os, 'replace', denied)
    monkeypatch.setattr(candidate.time, 'sleep', lambda _: pytest.fail('nonretryable error slept'))
    with pytest.raises(OSError):
        candidate.atomic_torch_save({'iteration': 2}, tmp_path / 'latest.pt')
    assert len(list(tmp_path.glob('*.pending'))) == 1


def test_partial_serialization_leaves_old_file_unchanged(tmp_path, monkeypatch):
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 1}, target)
    before = target.read_bytes()
    def interrupted(payload, handle):
        handle.write(b'partial')
        raise KeyboardInterrupt()
    monkeypatch.setattr(torch, 'save', interrupted)
    with pytest.raises(KeyboardInterrupt):
        candidate.atomic_torch_save({'iteration': 2}, target)
    assert target.read_bytes() == before
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('kwargs', [{'replace_timeout_seconds': -1}, {'replace_timeout_seconds': float('nan')},
                                    {'max_replace_attempts': 0}, {'max_replace_attempts': 1.5}])
def test_invalid_retry_bounds(tmp_path, kwargs):
    with pytest.raises(ValueError):
        candidate.atomic_torch_save({}, tmp_path / 'latest.pt', **kwargs)
    assert not list(tmp_path.iterdir())


def native_no_delete_handle(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return kernel, handle


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows sharing contract')
def test_actual_windows_sharing_conflict_recovers(tmp_path, monkeypatch):
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 1}, target)
    kernel, handle = native_no_delete_handle(target)
    errors, closed = [], []
    replace = candidate.os.replace
    def observed(*args):
        try:
            return replace(*args)
        except OSError as error:
            errors.append(error.winerror)
            raise
    def release():
        closed.append(bool(kernel.CloseHandle(handle)))
    timer = threading.Timer(.15, release)
    timer.start()
    monkeypatch.setattr(candidate.os, 'replace', observed)
    try:
        candidate.atomic_torch_save({'iteration': 2}, target, replace_timeout_seconds=2)
    finally:
        timer.join(timeout=3)
    assert errors and set(errors) <= candidate.RETRYABLE_WINERRORS
    assert closed == [True]
    assert torch.load(target, weights_only=False)['iteration'] == 2
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows sharing contract')
def test_actual_persistent_lock_keeps_recoverable_candidate(tmp_path):
    target = tmp_path / 'latest.pt'
    candidate.atomic_torch_save({'iteration': 1}, target)
    kernel, handle = native_no_delete_handle(target)
    try:
        with pytest.raises(PermissionError):
            candidate.atomic_torch_save({'iteration': 2}, target, replace_timeout_seconds=.06)
    finally:
        assert kernel.CloseHandle(handle)
    assert torch.load(target, weights_only=False)['iteration'] == 1
    pending, = tmp_path.glob('*.pending')
    assert torch.load(pending, weights_only=False)['iteration'] == 2


def test_wrapper_overrides_only_runtime_function(monkeypatch):
    import sys
    sys.path.insert(0, str(wrapper.ROOT / 'scripts'))
    import alpha_holdem.managed_checkpoint_io as original
    old = original.atomic_torch_save
    monkeypatch.setattr(original, 'atomic_torch_save', old)
    result = wrapper.install_io_override()
    assert original.atomic_torch_save is candidate.atomic_torch_save
    assert not result['learned_update_algorithm_modified']
    assert Path(original.__file__).resolve() == wrapper.ORIGINAL_IO
