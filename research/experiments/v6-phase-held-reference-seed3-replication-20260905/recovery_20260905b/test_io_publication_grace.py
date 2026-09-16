"""Actual Windows lock longer than the original grace; bounded permanent failure."""
import ctypes
from ctypes import wintypes
import os
import random
import sys
import threading
import time

import pytest
import torch

import train_with_checkpoint_io_45s as wrapper
sys.path.insert(0, str(wrapper.PREVIOUS))
import checkpoint_io_candidate as candidate


def install(monkeypatch):
    sys.path.insert(0, str(wrapper.ROOT / 'scripts'))
    import alpha_holdem.managed_checkpoint_io as original
    monkeypatch.setattr(original, 'atomic_torch_save', original.atomic_torch_save)
    description = wrapper.install_io_override()
    assert description['bounds'] == {'replace_timeout_seconds': 45.0, 'max_replace_attempts': 256}
    assert original.atomic_torch_save.func is candidate.atomic_torch_save
    assert not description['learned_update_algorithm_modified']
    return original.atomic_torch_save


@pytest.mark.skipif(os.name != 'nt', reason='actual Windows sharing semantics required')
def test_actual_windows_lock_beyond_old_5s_grace_recovers_same_payload(tmp_path, monkeypatch):
    save = install(monkeypatch)
    target = tmp_path / 'latest.pt'
    save({'iteration': 1}, target)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(target), 0x80000000, 3, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    original_save, original_replace = torch.save, candidate.os.replace
    calls, errors, closed = [], [], []
    def once(*args, **kwargs):
        calls.append(1)
        return original_save(*args, **kwargs)
    def observe(*args):
        try:
            return original_replace(*args)
        except OSError as error:
            errors.append(error.winerror)
            raise
    def release():
        closed.append(bool(kernel.CloseHandle(handle)))
    monkeypatch.setattr(torch, 'save', once)
    monkeypatch.setattr(candidate.os, 'replace', observe)
    before_random, before_torch = random.getstate(), torch.get_rng_state().clone()
    timer = threading.Timer(5.5, release)
    timer.start()
    begin = time.perf_counter()
    try:
        save({'iteration': 2, 'tensor': torch.ones(3)}, target)
    finally:
        timer.join(timeout=10)
    elapsed = time.perf_counter() - begin
    assert 5.25 <= elapsed < 15
    assert closed == [True] and calls == [1] and errors
    assert set(errors) <= candidate.RETRYABLE_WINERRORS
    assert torch.load(target, weights_only=False)['iteration'] == 2
    assert not list(tmp_path.glob('*.pending'))
    assert before_random == random.getstate() and torch.equal(before_torch, torch.get_rng_state())


def test_full_45s_deadline_is_bounded_and_retains_candidate(tmp_path, monkeypatch):
    save = install(monkeypatch)
    target = tmp_path / 'latest.pt'
    save({'iteration': 1}, target)
    before = target.read_bytes()
    class Clock:
        now = 0.0
        @classmethod
        def monotonic(cls):
            return cls.now
        @classmethod
        def sleep(cls, seconds):
            cls.now += seconds
    attempts = []
    def locked(*args):
        attempts.append(args)
        error = PermissionError('synthetic persistent native access denial')
        error.winerror = 5
        raise error
    monkeypatch.setattr(candidate, 'time', Clock)
    monkeypatch.setattr(candidate.os, 'replace', locked)
    with pytest.raises(PermissionError):
        save({'iteration': 2}, target)
    assert Clock.now == pytest.approx(45.0)
    assert 64 < len(attempts) <= 256
    assert target.read_bytes() == before
    pending, = tmp_path.glob('*.pending')
    assert torch.load(pending, weights_only=False)['iteration'] == 2


def test_source_hash_change_is_rejected_before_override(monkeypatch):
    monkeypatch.setattr(wrapper, 'EXPECTED', {wrapper.CANDIDATE: '0' * 64})
    with pytest.raises(ValueError, match='Frozen recovery source changed'):
        wrapper.install_io_override()
