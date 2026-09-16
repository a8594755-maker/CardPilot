"""Frozen public-state opponent-model execution contract for physical v6."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np
import torch

from alpha_holdem.physical_v6_cfr import PhysicalV6Encoder, legal_slot_actions
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_slumbot_opponent_model_feasibility import PublicOpponentModel


CONTRACT = "physical_v6_public_opponent_masked_private_sampled_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PublicOpponentPolicy:
    model: PublicOpponentModel
    path: Path
    sha256: str
    source_files: tuple[dict, ...]


def load_public_opponent(path: str | Path) -> PublicOpponentPolicy:
    path = Path(path).resolve()
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    required = {
        "schema_version": 1,
        "model": "PublicOpponentModel56x128x128x9",
        "private_card_contract": "masked_combo_feature_minus_one",
        "action_contract": "physical_v6_nearest_9slot_v1",
    }
    for key, value in required.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"public opponent requires {key}={value!r}")
    model = PublicOpponentModel()
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return PublicOpponentPolicy(
        model=model,
        path=path,
        sha256=sha256_file(path),
        source_files=tuple(checkpoint["source_files"]),
    )


@torch.no_grad()
def strategy(
    policy: PublicOpponentPolicy,
    state: ChipState,
    execution_legal_mask: np.ndarray | None = None,
) -> np.ndarray:
    if state.terminal:
        raise ValueError("public opponent cannot act in terminal state")
    encoded = PhysicalV6Encoder.encode(state)
    encoded[0] = -1.0
    mask = PhysicalV6Encoder.legal_mask(state)
    if execution_legal_mask is not None:
        execution_legal_mask = np.asarray(execution_legal_mask, dtype=np.float32)
        if execution_legal_mask.shape != mask.shape:
            raise ValueError("execution legal mask must have shape (9,)")
        # The environment may deduplicate abstract raise slots which map to the
        # same executable bet.  Preserve the physical contract while restricting
        # sampling to slots the live environment will actually accept.
        mask = ((mask > 0) & (execution_legal_mask > 0)).astype(np.float32)
        if not np.any(mask > 0):
            raise ValueError("physical and execution legal masks do not intersect")
    logits = policy.model(
        torch.from_numpy(encoded).unsqueeze(0),
        torch.from_numpy(mask).unsqueeze(0),
    ).squeeze(0).cpu().numpy().astype(np.float64)
    legal = mask > 0
    logits = logits[legal]
    logits -= logits.max()
    weights = np.exp(logits)
    weights /= weights.sum()
    result = np.zeros(9, dtype=np.float64)
    result[legal] = weights
    return result


def decide(
    policy: PublicOpponentPolicy,
    state: ChipState,
    rng: np.random.Generator,
    execution_legal_mask: np.ndarray | None = None,
) -> tuple[str, dict]:
    probabilities = strategy(policy, state, execution_legal_mask)
    slot_actions = dict(legal_slot_actions(state))
    slots = np.asarray(sorted(slot_actions), dtype=np.int64)
    selected = int(rng.choice(slots, p=probabilities[slots] / probabilities[slots].sum()))
    return slot_actions[selected], {
        "contract": CONTRACT,
        "checkpoint_sha256": policy.sha256,
        "selected_action_slot": selected,
        "behavior_probability": float(probabilities[selected]),
        "behavior_probs": probabilities.tolist(),
        "private_combo_feature": -1.0,
    }
