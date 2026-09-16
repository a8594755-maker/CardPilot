"""Atomic replacement for a completed managed-training checkpoint."""
import os
from pathlib import Path
import uuid


def atomic_torch_save(payload, target):
    import torch
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.pending")
    try:
        with temporary.open("xb") as handle:
            torch.save(payload, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        # Only the exact temporary file created for this attempted save is removed.
        if temporary.exists():
            temporary.unlink()
