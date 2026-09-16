"""Bounded Windows replace retry; keep durable candidates when replacement fails."""
import math
import os
from pathlib import Path
import sys
import time
import uuid

WINDOWS = os.name == 'nt'
RETRYABLE_WINERRORS = frozenset({5, 32, 33})


def atomic_torch_save(payload, target, *, replace_timeout_seconds=5.0, max_replace_attempts=64):
    import torch
    if not math.isfinite(replace_timeout_seconds) or replace_timeout_seconds < 0:
        raise ValueError('finite nonnegative replace deadline required')
    if not isinstance(max_replace_attempts, int) or max_replace_attempts < 1:
        raise ValueError('positive integer attempt limit required')
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.{uuid.uuid4().hex}.pending')
    durable = False
    created = False
    try:
        with temporary.open('xb') as handle:
            created = True
            torch.save(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        durable = True
        started = time.monotonic()
        deadline = started + replace_timeout_seconds
        for attempt in range(1, max_replace_attempts + 1):
            try:
                os.replace(temporary, target)
                if attempt > 1:
                    print(f'[CheckpointIO] replacement recovered after {attempt} attempts; same serialized payload; elapsed={time.monotonic()-started:.3f}s', file=sys.stderr, flush=True)
                return
            except OSError as error:
                remaining = deadline - time.monotonic()
                retryable = WINDOWS and getattr(error, 'winerror', None) in RETRYABLE_WINERRORS
                if not retryable or remaining <= 0 or attempt == max_replace_attempts:
                    error.add_note(f'Old destination was not deleted. Durable candidate retained for explicit review: {temporary}')
                    raise
                if attempt == 1:
                    print(f'[CheckpointIO] replace WinError={error.winerror}; bounded retry of same serialized payload', file=sys.stderr, flush=True)
                time.sleep(min(.025 * 2 ** min(attempt - 1, 4), .25, remaining))
    finally:
        if created and not durable:
            # Never touch the destination or any temporary created by another call.
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                print(f'[CheckpointIO] incomplete temporary cleanup failed; preserved {temporary}: {cleanup_error!r}', file=sys.stderr, flush=True)
