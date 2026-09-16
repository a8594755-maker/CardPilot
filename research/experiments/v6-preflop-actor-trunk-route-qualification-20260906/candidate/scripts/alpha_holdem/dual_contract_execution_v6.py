"""Frozen execution adapter for a legacy-v4 base plus native-v6 residual.

The deployment bundle is self-contained for residual architecture and weights,
but intentionally does not duplicate the legacy base.  Runtime identity is the
pair (deployment bundle SHA256, base checkpoint SHA256).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import numpy as np
import torch

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.execution_v6 import sha256_file
from alpha_holdem.legacy_observation_bridge_v6 import (
    LegacyObservationBridgePolicy,
    legacy_observation,
    load_policy as load_base_policy,
)
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, action_table, from_external
from alpha_holdem.v6_dual_contract_residual_training_smoke import state_inputs


DEPLOYMENT_SCHEMA = "cardpilot.dual_contract_deployment.v1"
DUAL_CONTRACT = "legacy-v4-base+native-v6-bounded-residual.v1"


@dataclass(frozen=True)
class DualContractExecutionPolicy:
    model: DualContractResidualPolicy
    base_policy: LegacyObservationBridgePolicy
    checkpoint: dict
    path: Path
    sha256: str
    base_path: Path
    base_sha256: str
    source_residual_sha256: str
    device: str


def _load_checkpoint(path: Path) -> dict:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(checkpoint, dict):
        raise ValueError("Dual-contract checkpoint must be a mapping")
    return checkpoint


def _architecture(source: dict, source_path: Path) -> tuple[int, float, Path, str]:
    hidden = source.get("hidden")
    cap = source.get("policy_delta_cap")
    architecture_path = source_path
    architecture_sha = sha256_file(source_path)
    if hidden is None or cap is None:
        parent_value = source.get("start_checkpoint")
        parent_sha = source.get("start_checkpoint_sha256")
        if not isinstance(parent_value, str) or not isinstance(parent_sha, str):
            raise ValueError("Residual checkpoint omits architecture and a hash-bound parent")
        architecture_path = Path(parent_value).resolve()
        if not architecture_path.is_file() or sha256_file(architecture_path) != parent_sha:
            raise ValueError("Architecture parent checkpoint identity mismatch")
        parent = _load_checkpoint(architecture_path)
        hidden, cap = parent.get("hidden"), parent.get("policy_delta_cap")
        architecture_sha = parent_sha
    if type(hidden) is not int or hidden <= 0:
        raise ValueError("Invalid residual hidden width")
    if type(cap) not in (int, float) or not math.isfinite(float(cap)) or float(cap) < 0:
        raise ValueError("Invalid residual policy-delta cap")
    return hidden, float(cap), architecture_path, architecture_sha


def build_deployment_bundle(
    source_residual: str | Path,
    base_checkpoint: str | Path,
    output: str | Path,
) -> dict:
    """Create a weight-identical, architecture-complete frozen deployment file."""
    source_path = Path(source_residual).resolve()
    base_path = Path(base_checkpoint).resolve()
    output_path = Path(output).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    source = _load_checkpoint(source_path)
    if source.get("schema") != "cardpilot.dual_contract_residual.v1":
        raise ValueError("Unsupported residual checkpoint schema")
    base_sha = sha256_file(base_path)
    if source.get("base_sha256") != base_sha:
        raise ValueError("Residual checkpoint is bound to a different base checkpoint")
    state = source.get("residual_state_dict")
    if not isinstance(state, dict) or not state:
        raise ValueError("Residual checkpoint has no state dict")
    hidden, cap, architecture_path, architecture_sha = _architecture(source, source_path)
    source_sha = sha256_file(source_path)
    bundle = {
        "schema": DEPLOYMENT_SCHEMA,
        "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": DUAL_CONTRACT,
        "model_obs_version": "legacy-v4+native-v6",
        "base_checkpoint": str(base_path),
        "base_sha256": base_sha,
        "source_residual_checkpoint": str(source_path),
        "source_residual_sha256": source_sha,
        "source_residual_schema": source["schema"],
        "architecture_source_checkpoint": str(architecture_path),
        "architecture_source_sha256": architecture_sha,
        "hidden": hidden,
        "policy_delta_cap": cap,
        "dose_hands": source.get("dose_hands"),
        "residual_state_dict": {
            key: value.detach().cpu().clone() if torch.is_tensor(value) else value
            for key, value in state.items()
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(bundle, output_path)
    return {
        "path": str(output_path),
        "sha256": sha256_file(output_path),
        "base_path": str(base_path),
        "base_sha256": base_sha,
        "source_residual_path": str(source_path),
        "source_residual_sha256": source_sha,
        "architecture_source_path": str(architecture_path),
        "architecture_source_sha256": architecture_sha,
        "hidden": hidden,
        "policy_delta_cap": cap,
    }


def load_policy(
    path: str | Path,
    base_checkpoint: str | Path | None = None,
    device: str = "cpu",
) -> DualContractExecutionPolicy:
    path = Path(path).resolve()
    checkpoint = _load_checkpoint(path)
    required = {
        "schema": DEPLOYMENT_SCHEMA,
        "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": DUAL_CONTRACT,
        "model_obs_version": "legacy-v4+native-v6",
    }
    for key, value in required.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"Deployment checkpoint requires {key}={value!r}")
    recorded_base = checkpoint.get("base_checkpoint")
    base_path = Path(base_checkpoint if base_checkpoint is not None else recorded_base).resolve()
    base_sha = sha256_file(base_path)
    if checkpoint.get("base_sha256") != base_sha:
        raise ValueError("Deployment base checkpoint identity mismatch")
    hidden = checkpoint.get("hidden")
    cap = checkpoint.get("policy_delta_cap")
    if type(hidden) is not int or hidden <= 0 or type(cap) not in (int, float):
        raise ValueError("Invalid deployment architecture")
    base_policy = load_base_policy(base_path, device)
    model = DualContractResidualPolicy(
        base_policy.model, hidden=hidden, policy_delta_cap=float(cap)
    ).to(device)
    state = checkpoint.get("residual_state_dict")
    if not isinstance(state, dict):
        raise ValueError("Deployment checkpoint has no residual state")
    expected = {name for name in model.state_dict() if not name.startswith("base.")}
    if set(state) != expected:
        raise ValueError("Deployment residual state keys do not match the architecture")
    incompatible = model.load_state_dict(state, strict=False)
    if incompatible.unexpected_keys or set(incompatible.missing_keys) != {
        name for name in model.state_dict() if name.startswith("base.")
    }:
        raise ValueError("Deployment residual state load was not exact")
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    source_sha = checkpoint.get("source_residual_sha256")
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise ValueError("Missing source residual identity")
    return DualContractExecutionPolicy(
        model=model,
        base_policy=base_policy,
        checkpoint=checkpoint,
        path=path,
        sha256=sha256_file(path),
        base_path=base_path,
        base_sha256=base_sha,
        source_residual_sha256=source_sha,
        device=device,
    )


@torch.no_grad()
def decide(
    policy: DualContractExecutionPolicy,
    state,
    *,
    uniform: float,
    policy_mode: str = "greedy",
) -> tuple[str, dict]:
    if not 0 <= uniform < 1:
        raise ValueError("Uniform variate must be in [0,1)")
    if policy_mode not in {"greedy", "sample"}:
        raise ValueError("policy_mode must be greedy or sample")
    values, legacy_obs, legacy_table = state_inputs(
        policy.base_policy, state, policy.device
    )
    logits, _ = policy.model(*values)
    legal = np.flatnonzero(legacy_obs["legal_mask"] > 0)
    legal_logits = logits[0, legal].detach().cpu().numpy().astype(np.float64)
    weights = np.exp(legal_logits - legal_logits.max())
    probabilities = weights / weights.sum()
    greedy_local = int(np.argmax(legal_logits))
    if policy_mode == "greedy":
        selected_local = greedy_local
        temperature = 0.0
    else:
        selected_local = min(
            int(np.searchsorted(np.cumsum(probabilities), uniform, side="right")),
            len(legal) - 1,
        )
        temperature = 1.0
    selected_legacy_slot = int(legal[selected_local])
    greedy_legacy_slot = int(legal[greedy_local])
    selected_action = legacy_table[selected_legacy_slot]
    current_mask, current_table = action_table(state)

    def physical_slot(action: str) -> int:
        matches = [index for index, current in enumerate(current_table) if current == action]
        if len(matches) != 1:
            raise ValueError(f"Dual-contract action {action!r} has no unique native-v6 slot")
        return matches[0]

    selected_slot = physical_slot(selected_action)
    greedy_slot = physical_slot(legacy_table[greedy_legacy_slot])
    model_probs = np.zeros(9, dtype=np.float64)
    for probability, legacy_slot in zip(probabilities, legal):
        model_probs[physical_slot(legacy_table[int(legacy_slot)])] += float(probability)
    if policy_mode == "greedy":
        behavior_probs = np.zeros(9, dtype=np.float64)
        behavior_probs[selected_slot] = 1.0
        behavior_probability = 1.0
    else:
        behavior_probs = model_probs.copy()
        behavior_probability = float(model_probs[selected_slot])
    return selected_action, {
        "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": DUAL_CONTRACT,
        "deployment_checkpoint_sha256": policy.sha256,
        "base_checkpoint_sha256": policy.base_sha256,
        "source_residual_sha256": policy.source_residual_sha256,
        "policy_mode": policy_mode,
        "temperature": temperature,
        "legacy_selected_action_slot": selected_legacy_slot,
        "selected_action_slot": selected_slot,
        "direct_increment": selected_action,
        "greedy_action_slot": greedy_slot,
        "legacy_greedy_action_slot": greedy_legacy_slot,
        "behavior_action_probability": behavior_probability,
        "behavior_probs": behavior_probs.tolist(),
        "model_probs": model_probs.tolist(),
        "legal_mask": current_mask.tolist(),
        "action_table": current_table,
        "legacy_legal_mask": legacy_obs["legal_mask"].tolist(),
        "legacy_action_table": legacy_table,
        "v6_action_table": current_table,
        "uniform": float(uniform),
    }


def external_decision(
    policy: DualContractExecutionPolicy,
    response: dict,
    *,
    uniform: float,
    device: str = "cpu",
    policy_mode: str = "greedy",
) -> tuple[str, dict]:
    if device != policy.device:
        raise ValueError(f"Dual-contract policy is on {policy.device}, requested {device}")
    state = from_external(
        response["action"], response["hole_cards"], response.get("board", []),
        response["client_pos"],
    )
    return decide(policy, state, uniform=uniform, policy_mode=policy_mode)
