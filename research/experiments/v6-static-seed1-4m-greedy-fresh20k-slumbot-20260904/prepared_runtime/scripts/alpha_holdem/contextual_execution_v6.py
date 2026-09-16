"""Self-contained frozen execution for posterior-context Standard10 residuals."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.execution_v6 import sha256_file
from alpha_holdem.legacy_observation_bridge_v6 import decide as base_decide, load_policy as load_base_policy
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, action_table, from_external
from alpha_holdem.slumbot_terminal_v6 import _observed, _terminal_state
from alpha_holdem.v6_dual_contract_residual_training_smoke import state_inputs
from alpha_holdem.v6_opponent_context_feasibility import action_bucket, context_features
from deep_cfr.hand_eval import card_from_str


DEPLOYMENT_SCHEMA = "cardpilot.posterior_context_deployment.v1"
CONTEXT_CONTRACT = "legacy-v4-base+native-v6-posterior-context-residual.v1"


@dataclass(frozen=True)
class ContextualExecutionPolicy:
    model: PosteriorCenteredResidualPolicy
    base_policy: object
    checkpoint: dict
    path: Path
    sha256: str
    base_path: Path
    base_sha256: str
    source_checkpoint_sha256: str
    classifier_sha256: str
    cold_start_hands: int
    device: str


class SessionContextTracker:
    def __init__(self, cold_start_hands: int = 64):
        if cold_start_hands <= 0:
            raise ValueError("cold_start_hands must be positive")
        self.cold_start_hands = int(cold_start_hands)
        self.counts = np.zeros((4, 4), dtype=np.int64)
        self.current_hand = 0
        self.completed_hands = 0
        self.context = np.zeros(20, dtype=np.float32)
        self.cold_start = True

    def start_hand(self, hand: int) -> dict:
        if hand != self.current_hand + 1:
            raise ValueError("session context requires contiguous hand indices")
        self.current_hand = hand
        self.context = context_features(self.counts)
        self.cold_start = hand <= self.cold_start_hands
        return self.metadata()

    def finish_hand(self, hand: int, terminal_response: dict) -> dict:
        if hand != self.current_hand:
            raise ValueError("session context hand completion mismatch")
        if self.completed_hands != hand - 1:
            raise ValueError("session context hand was already completed")
        hero_seat, holes, board = _observed(terminal_response)
        other_value = terminal_response.get("bot_hole_cards")
        other = tuple(card_from_str(card) for card in other_value) if other_value not in (None, []) else ()
        known = holes + board + other
        if len(set(known)) != len(known):
            raise ValueError("duplicate terminal context card")
        unused = [card for card in range(52) if card not in known]
        if not other:
            other = tuple(unused[:2])
            unused = unused[2:]
        future = board + tuple(unused[: 5 - len(board)])
        first = holes + other if hero_seat == 0 else other + holes
        used = set(first + future)
        deck = first + tuple(card for card in range(52) if card not in used) + tuple(reversed(future))
        state = _terminal_state(terminal_response["action"], deck)
        if state.board != board:
            raise ValueError("terminal context board mismatch")
        for event in state.history:
            if event.player != hero_seat:
                self.counts[event.street, action_bucket(event.kind)] += 1
        self.completed_hands = hand
        self.context = context_features(self.counts)
        return self.metadata()

    def metadata(self) -> dict:
        digest = hashlib.sha256(self.counts.tobytes()).hexdigest()
        return {
            "context_completed_hands": self.completed_hands,
            "context_cold_start": self.cold_start,
            "context_counts_sha256": digest,
            "context_feature_vector": self.context.tolist(),
        }


def build_deployment_bundle(source_checkpoint, base_checkpoint, classifier_path, output, *, cold_start_hands=64, reliability_power=1.0):
    source_path = Path(source_checkpoint).resolve()
    base_path = Path(base_checkpoint).resolve()
    classifier_path = Path(classifier_path).resolve()
    output_path = Path(output).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)
    source = torch.load(source_path, map_location="cpu", weights_only=False)
    if source.get("schema") != "cardpilot.posterior_context_curve_checkpoint.v1":
        raise ValueError("unsupported posterior-context source checkpoint")
    base_sha = sha256_file(base_path)
    classifier_sha = sha256_file(classifier_path)
    if source.get("base_sha256") != base_sha or source.get("classifier_sha256") != classifier_sha:
        raise ValueError("source checkpoint parent identity mismatch")
    classifier_payload = torch.load(classifier_path, map_location="cpu", weights_only=False)
    classifier = classifier_payload["models"]["64"]
    state = source.get("residual_state_dict")
    if not isinstance(state, dict) or not state:
        raise ValueError("source checkpoint has no residual state")
    bundle = {
        "schema": DEPLOYMENT_SCHEMA, "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": CONTEXT_CONTRACT,
        "model_obs_version": "legacy-v4+native-v6+public-session-context",
        "base_checkpoint": str(base_path), "base_sha256": base_sha,
        "source_checkpoint": str(source_path), "source_checkpoint_sha256": sha256_file(source_path),
        "classifier_source": str(classifier_path), "classifier_sha256": classifier_sha,
        "classifier": {key: value.detach().cpu().clone() if torch.is_tensor(value) else np.asarray(value).copy() if isinstance(value, np.ndarray) else value for key, value in classifier.items()},
        "hidden": 128, "policy_delta_cap": 0.25,
        "cold_start_hands": int(cold_start_hands), "reliability_power": float(reliability_power),
        "source_learning_hands_per_group": source.get("learning_hands_per_group"),
        "residual_state_dict": {key: value.detach().cpu().clone() if torch.is_tensor(value) else value for key, value in state.items()},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(bundle, output_path)
    return {"path": str(output_path), "sha256": sha256_file(output_path), "base_sha256": base_sha, "classifier_sha256": classifier_sha, "source_checkpoint_sha256": sha256_file(source_path)}


def load_policy(path, base_checkpoint=None, device="cpu") -> ContextualExecutionPolicy:
    path = Path(path).resolve()
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    required = {
        "schema": DEPLOYMENT_SCHEMA, "policy_contract": CONTRACT_VERSION,
        "observation_bridge_contract": CONTEXT_CONTRACT,
        "model_obs_version": "legacy-v4+native-v6+public-session-context",
    }
    for key, value in required.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"contextual deployment requires {key}={value!r}")
    base_path = Path(base_checkpoint if base_checkpoint is not None else checkpoint["base_checkpoint"]).resolve()
    base_sha = sha256_file(base_path)
    if checkpoint.get("base_sha256") != base_sha:
        raise ValueError("contextual deployment base identity mismatch")
    classifier = checkpoint.get("classifier")
    if not isinstance(classifier, dict):
        raise ValueError("contextual deployment omits classifier")
    base_policy = load_base_policy(base_path, device)
    model = PosteriorCenteredResidualPolicy(
        base_policy.model, classifier, hidden=int(checkpoint["hidden"]),
        policy_delta_cap=float(checkpoint["policy_delta_cap"]),
        reliability_power=float(checkpoint["reliability_power"]),
    ).to(device)
    state = checkpoint.get("residual_state_dict")
    expected = {name for name in model.state_dict() if not name.startswith("base.")}
    if not isinstance(state, dict) or set(state) != expected:
        raise ValueError("contextual residual state keys do not match architecture")
    incompatible = model.load_state_dict(state, strict=False)
    if incompatible.unexpected_keys or set(incompatible.missing_keys) != {name for name in model.state_dict() if name.startswith("base.")}:
        raise ValueError("contextual residual load was not exact")
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return ContextualExecutionPolicy(
        model=model, base_policy=base_policy, checkpoint=checkpoint, path=path,
        sha256=sha256_file(path), base_path=base_path, base_sha256=base_sha,
        source_checkpoint_sha256=str(checkpoint["source_checkpoint_sha256"]),
        classifier_sha256=str(checkpoint["classifier_sha256"]),
        cold_start_hands=int(checkpoint["cold_start_hands"]), device=device,
    )


@torch.no_grad()
def decide(policy: ContextualExecutionPolicy, state, context, *, cold_start: bool, uniform: float, policy_mode="greedy"):
    if cold_start:
        action, metadata = base_decide(policy.base_policy, state, uniform=uniform, policy_mode=policy_mode)
        return action, {
            **metadata,
            "observation_bridge_contract": CONTEXT_CONTRACT,
            "contextual_deployment_sha256": policy.sha256,
            "base_checkpoint_sha256": policy.base_sha256,
            "source_checkpoint_sha256": policy.source_checkpoint_sha256,
            "classifier_sha256": policy.classifier_sha256,
            "context_cold_start": True,
            "context_feature_vector": np.asarray(context, dtype=np.float32).tolist(),
        }
    values, obs, table = state_inputs(policy.base_policy, state, policy.device)
    context_tensor = torch.as_tensor(context, dtype=torch.float32, device=policy.device).unsqueeze(0)
    logits, _ = policy.model(*values, context_tensor)
    legal = np.flatnonzero(obs["legal_mask"] > 0)
    legal_logits = logits[0, legal].detach().cpu().numpy().astype(np.float64)
    probabilities = np.exp(legal_logits - legal_logits.max())
    probabilities /= probabilities.sum()
    greedy = int(np.argmax(legal_logits))
    selected = greedy if policy_mode == "greedy" else min(int(np.searchsorted(np.cumsum(probabilities), uniform, side="right")), len(legal) - 1)
    legacy_slot = int(legal[selected])
    action = table[legacy_slot]
    native_mask, native_table = action_table(state)
    native_slot = native_table.index(action)
    behavior = np.zeros(9, dtype=np.float64)
    model_probs = np.zeros(9, dtype=np.float64)
    for index, legacy_action_slot in enumerate(legal):
        model_probs[native_table.index(table[int(legacy_action_slot)])] = probabilities[index]
    if policy_mode == "greedy":
        behavior[native_slot] = 1.0
    else:
        behavior[:] = model_probs
    return action, {
        "policy_contract": CONTRACT_VERSION, "observation_bridge_contract": CONTEXT_CONTRACT,
        "contextual_deployment_sha256": policy.sha256, "base_checkpoint_sha256": policy.base_sha256,
        "source_checkpoint_sha256": policy.source_checkpoint_sha256, "classifier_sha256": policy.classifier_sha256,
        "policy_mode": policy_mode, "temperature": 0.0 if policy_mode == "greedy" else 1.0,
        "uniform": float(uniform),
        "legacy_selected_action_slot": legacy_slot, "selected_action_slot": native_slot,
        "direct_increment": action, "behavior_action_probability": float(behavior[native_slot]),
        "behavior_probs": behavior.tolist(), "model_probs": model_probs.tolist(),
        "greedy_action_slot": int(native_table.index(table[int(legal[greedy])])),
        "legal_mask": native_mask.tolist(), "action_table": native_table,
        "context_cold_start": False, "context_feature_vector": np.asarray(context, dtype=np.float32).tolist(),
    }


def external_decision(policy, response, context, *, cold_start, uniform, device="cpu", policy_mode="greedy"):
    if device != policy.device:
        raise ValueError("contextual deployment device mismatch")
    state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
    return decide(policy, state, context, cold_start=cold_start, uniform=uniform, policy_mode=policy_mode)
