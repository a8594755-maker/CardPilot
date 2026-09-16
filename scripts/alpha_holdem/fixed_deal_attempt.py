"""Durable, single-use deal namespaces for statistical training continuation.

An attempt is consumed even if it crashes before its first hand. Its UUID changes
the deterministic deck stream, not the optimizer or any hand counter. Reading a
receipt for offline replay is allowed; allocating it for another live attempt is
not. Trainer integration must allocate before workers and record the receipt SHA.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import uuid


SCHEMA = "cardpilot.fixed_deal_attempt.v1"


def check_namespace(namespace: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", namespace):
        raise ValueError("attempt namespace must be 32 lowercase hexadecimal characters")
    return namespace


def allocate_attempt(registry: Path, *, run_id: str, training_seed: int,
                     worker_seed_base: int, workers: int, envs_per_worker: int,
                     parent_checkpoint_sha256: str | None,
                     namespace: str | None = None) -> dict:
    """Exclusive durable reservation. Existing or torn receipts always fail closed."""
    namespace = check_namespace(namespace if namespace is not None else uuid.uuid4().hex)
    if not run_id or workers < 1 or envs_per_worker < 1:
        raise ValueError("run identity and positive worker/env counts required")
    if parent_checkpoint_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", parent_checkpoint_sha256):
        raise ValueError("invalid parent checkpoint SHA256")
    receipt = {
        "schema": SCHEMA, "namespace": namespace, "run_id": run_id,
        "training_seed": int(training_seed), "worker_seed_base": int(worker_seed_base),
        "workers": int(workers), "envs_per_worker": int(envs_per_worker),
        "parent_checkpoint_sha256": parent_checkpoint_sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(), "hand_count_increment": 0,
        "semantics": "fresh-attempt statistical continuation",
        "bitwise_uninterrupted_equivalence": False,
    }
    registry = Path(registry)
    registry.mkdir(parents=True, exist_ok=True)
    path = registry / f"attempt-{namespace}.json"
    raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")
    # O_EXCL is the cross-process claim. Do not unlink even on write/fsync failure.
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        fd = os.open(registry, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
            "receipt": receipt}


def load_attempt(path: Path, expected_sha256: str) -> dict:
    """Verify an existing receipt for evidence replay, not live reallocation."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("attempt receipt SHA256 mismatch")
    receipt = json.loads(raw)
    if receipt.get("schema") != SCHEMA:
        raise ValueError("unknown attempt receipt schema")
    check_namespace(receipt["namespace"])
    return receipt


def attempt_deck(worker_seed: int, env_index: int, deal_index: int,
                 *, namespace: str = "") -> list[int]:
    """Empty namespace preserves v1 exactly; nonempty is the v2 stream contract."""
    if worker_seed is None or env_index < 0 or deal_index < 0:
        raise ValueError("seed and nonnegative env/deal indices required")
    if namespace:
        check_namespace(namespace)
        material = f"v5.fixed.training.deal.v2:{namespace}:{int(worker_seed)}:{int(env_index)}:{int(deal_index)}"
    else:
        material = f"v5.fixed.training.deal.v1:{int(worker_seed)}:{int(env_index)}:{int(deal_index)}"
    seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "big")
    deck = list(range(52))
    random.Random(seed).shuffle(deck)
    return deck


def attempt_deal_identity(namespace: str, worker_seed: int, env_index: int,
                          deal_index: int) -> str:
    check_namespace(namespace)
    return f"{namespace}:s{int(worker_seed)}:e{int(env_index)}:d{int(deal_index)}"
