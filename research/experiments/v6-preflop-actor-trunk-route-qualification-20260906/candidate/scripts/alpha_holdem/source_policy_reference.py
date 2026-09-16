"""Explicit source-policy KL and checkpoint-safe moving-reference helpers."""

from __future__ import annotations

import random
from typing import Mapping

import numpy as np
import torch
import torch.nn.functional as F


MOVING_REFERENCE_SCHEMA = "alpha_holdem.moving_source_policy_reference.v1"
KL_DIRECTIONS = ("reference_to_current", "current_to_reference")


def categorical_policy_kl(
    current_logits: torch.Tensor,
    reference_logits: torch.Tensor,
    legal_masks: torch.Tensor,
    *,
    temperature: float = 1.0,
    direction: str = "reference_to_current",
) -> torch.Tensor:
    """Return per-row legal-action KL in the explicitly requested direction."""
    if direction not in KL_DIRECTIONS:
        raise ValueError(f"unsupported source-policy KL direction: {direction}")
    if current_logits.ndim != 2 or reference_logits.shape != current_logits.shape:
        raise ValueError("current and reference logits must be aligned rank-two tensors")
    if legal_masks.shape != current_logits.shape:
        raise ValueError("legal masks must align with policy logits")
    if float(temperature) <= 0.0:
        raise ValueError("source-policy KL temperature must be positive")

    legal = legal_masks > 0
    if not bool(legal.any(dim=-1).all().item()):
        raise ValueError("every source-policy KL row must contain a legal action")
    masked_current = current_logits.masked_fill(~legal, -torch.inf)
    masked_reference = reference_logits.masked_fill(~legal, -torch.inf)
    if direction == "reference_to_current":
        # Preserve the original trainer's softmax/clamp/log arithmetic for
        # legacy fixed-reference runs; model logits are already legal-masked.
        reference_probs = F.softmax(
            masked_reference / float(temperature), dim=-1
        )
        current_probs = F.softmax(
            masked_current / float(temperature), dim=-1
        )
        terms = reference_probs * (
            reference_probs.clamp_min(1e-8).log()
            - current_probs.clamp_min(1e-8).log()
        )
        return torch.where(legal, terms, torch.zeros_like(terms)).sum(dim=-1)

    current_log_probs = F.log_softmax(
        masked_current / float(temperature), dim=-1
    )
    reference_log_probs = F.log_softmax(
        masked_reference / float(temperature), dim=-1
    )
    log_ratio = torch.where(
        legal,
        current_log_probs - reference_log_probs,
        torch.zeros_like(current_log_probs),
    )
    return (current_log_probs.exp() * log_ratio).sum(dim=-1)


def capture_training_rng_state() -> dict:
    """Capture main-process RNGs needed to resume a PPO update boundary."""
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state().detach().cpu().clone(),
        "torch_cuda": (
            [state.detach().cpu().clone() for state in torch.cuda.get_rng_state_all()]
            if torch.cuda.is_available()
            else []
        ),
    }


def restore_training_rng_state(state: Mapping) -> None:
    required = {"python", "numpy", "torch_cpu", "torch_cuda"}
    missing = required - set(state)
    if missing:
        raise RuntimeError(f"moving-reference RNG state is incomplete: {sorted(missing)}")
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch_cpu"].detach().cpu())
    cuda_states = list(state["torch_cuda"])
    if cuda_states:
        if not torch.cuda.is_available():
            raise RuntimeError("checkpoint has CUDA RNG state but CUDA is unavailable")
        if len(cuda_states) != torch.cuda.device_count():
            raise RuntimeError(
                "moving-reference CUDA RNG device-count mismatch: "
                f"checkpoint={len(cuda_states)} runtime={torch.cuda.device_count()}"
            )
        torch.cuda.set_rng_state_all([value.detach().cpu() for value in cuda_states])


def moving_reference_checkpoint_state(
    reference_policy,
    *,
    direction: str,
    refresh_interval_updates: int,
    completed_updates: int,
    last_refresh_update: int,
    reference_round: int,
    activation_iteration: int,
    trainer_iteration: int,
) -> dict:
    validate_moving_reference_counters(
        direction=direction,
        refresh_interval_updates=refresh_interval_updates,
        completed_updates=completed_updates,
        last_refresh_update=last_refresh_update,
        reference_round=reference_round,
    )
    if int(activation_iteration) < 0 or int(trainer_iteration) < 0:
        raise ValueError("moving-reference trainer iterations must be nonnegative")
    if int(trainer_iteration) - int(activation_iteration) != int(completed_updates):
        raise ValueError(
            "moving-reference completed updates do not match trainer iteration"
        )
    return {
        "schema_version": MOVING_REFERENCE_SCHEMA,
        "direction": direction,
        "refresh_interval_updates": int(refresh_interval_updates),
        "completed_updates": int(completed_updates),
        "last_refresh_update": int(last_refresh_update),
        "reference_round": int(reference_round),
        "activation_iteration": int(activation_iteration),
        "trainer_iteration": int(trainer_iteration),
        "reference_model": {
            name: value.detach().cpu().clone()
            for name, value in reference_policy.state_dict().items()
        },
        "rng_state": capture_training_rng_state(),
    }


def validate_moving_reference_counters(
    *,
    direction: str,
    refresh_interval_updates: int,
    completed_updates: int,
    last_refresh_update: int,
    reference_round: int,
) -> None:
    if direction != "current_to_reference":
        raise ValueError("moving source-policy reference requires KL(current || reference)")
    interval = int(refresh_interval_updates)
    completed = int(completed_updates)
    last = int(last_refresh_update)
    round_index = int(reference_round)
    if interval <= 0 or completed < 0 or last < 0 or round_index < 0:
        raise ValueError("moving-reference interval/counters are invalid")
    if round_index != completed // interval or last != round_index * interval:
        raise ValueError(
            "moving-reference counters violate completed-update refresh cadence"
        )


def restore_moving_reference_checkpoint(
    reference_policy,
    state: Mapping,
    *,
    direction: str,
    refresh_interval_updates: int,
) -> dict:
    if state.get("schema_version") != MOVING_REFERENCE_SCHEMA:
        raise RuntimeError("unsupported moving source-policy reference checkpoint schema")
    if state.get("direction") != direction:
        raise RuntimeError(
            "moving-reference KL direction mismatch: "
            f"checkpoint={state.get('direction')} requested={direction}"
        )
    if int(state.get("refresh_interval_updates", -1)) != int(refresh_interval_updates):
        raise RuntimeError(
            "moving-reference refresh interval mismatch: "
            f"checkpoint={state.get('refresh_interval_updates')} "
            f"requested={refresh_interval_updates}"
        )
    counters = {
        "completed_updates": int(state.get("completed_updates", -1)),
        "last_refresh_update": int(state.get("last_refresh_update", -1)),
        "reference_round": int(state.get("reference_round", -1)),
    }
    try:
        validate_moving_reference_counters(
            direction=direction,
            refresh_interval_updates=refresh_interval_updates,
            **counters,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    serialized_model = state.get("reference_model")
    if not isinstance(serialized_model, Mapping):
        raise RuntimeError("moving-reference checkpoint has no reference model")
    try:
        reference_policy.load_state_dict(serialized_model, strict=True)
    except (KeyError, RuntimeError) as exc:
        raise RuntimeError("moving-reference model state is incompatible") from exc
    if not isinstance(state.get("rng_state"), Mapping):
        raise RuntimeError("moving-reference checkpoint has no main-process RNG state")
    activation_iteration = int(state.get("activation_iteration", -1))
    trainer_iteration = int(state.get("trainer_iteration", -1))
    if (
        activation_iteration < 0
        or trainer_iteration < 0
        or trainer_iteration - activation_iteration
        != counters["completed_updates"]
    ):
        raise RuntimeError(
            "moving-reference checkpoint trainer iteration is inconsistent"
        )
    return {
        **counters,
        "activation_iteration": activation_iteration,
        "trainer_iteration": trainer_iteration,
        "rng_state": state["rng_state"],
    }


@torch.no_grad()
def advance_moving_reference(
    current_policy,
    reference_policy,
    *,
    refresh_interval_updates: int,
    completed_updates: int,
    last_refresh_update: int,
    reference_round: int,
) -> dict:
    completed = int(completed_updates) + 1
    interval = int(refresh_interval_updates)
    if interval <= 0:
        raise ValueError("moving-reference refresh interval must be positive")
    refreshed = completed % interval == 0
    last = int(last_refresh_update)
    round_index = int(reference_round)
    if refreshed:
        reference_policy.load_state_dict(current_policy.state_dict(), strict=True)
        reference_policy.eval()
        last = completed
        round_index += 1
    validate_moving_reference_counters(
        direction="current_to_reference",
        refresh_interval_updates=interval,
        completed_updates=completed,
        last_refresh_update=last,
        reference_round=round_index,
    )
    return {
        "completed_updates": completed,
        "last_refresh_update": last,
        "reference_round": round_index,
        "refreshed": refreshed,
    }
