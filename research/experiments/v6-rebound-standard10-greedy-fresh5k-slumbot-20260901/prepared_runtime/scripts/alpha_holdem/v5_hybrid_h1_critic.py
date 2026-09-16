"""HYBRID H1 critic-v1 to critic-v2 checkpoint/optimizer migration."""
from __future__ import annotations
import copy
import hashlib
import json
from typing import Any
import torch
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2

def actor_key(name: str) -> bool:
    return not name.startswith("value_head.")

def tensor_sha256(tensor: torch.Tensor) -> str:
    value = tensor.detach().cpu().contiguous()
    digest = hashlib.sha256()
    digest.update(json.dumps([str(value.dtype), list(value.shape)], separators=(",", ":")).encode("ascii"))
    digest.update(value.numpy().tobytes())
    return digest.hexdigest()

def initialize_model(model: AlphaHoldemNet, device: str = "cpu") -> None:
    with torch.no_grad():
        model(torch.zeros(2, 6, 4, 13, device=device), torch.zeros(2, 25, 4, 5, device=device), torch.zeros(2, 2, device=device))

def named_parameter_ids(model: AlphaHoldemNet, optimizer: torch.optim.Optimizer) -> dict[str, int]:
    names = [name for name, _ in model.named_parameters()]
    state = optimizer.state_dict()
    ids = [item for group in state["param_groups"] for item in group["params"]]
    if len(ids) != len(names):
        raise ValueError("optimizer parameter count does not match model")
    return dict(zip(names, ids))

def migrate_v1_checkpoint_to_v2(*, model: AlphaHoldemNet, optimizer: torch.optim.Optimizer, checkpoint: dict[str, Any], device: str) -> dict[str, Any]:
    if model.critic_contract != CRITIC_V2:
        raise ValueError("migration target must use critic_v2")
    source_model = checkpoint.get("model")
    source_optimizer = checkpoint.get("optimizer")
    if not isinstance(source_model, dict) or not isinstance(source_optimizer, dict):
        raise ValueError("source checkpoint model/optimizer missing")
    target_state = model.state_dict()
    source_actor = {name: value for name, value in source_model.items() if actor_key(name)}
    target_actor_keys = {name for name in target_state if actor_key(name)}
    target_actor_param_names = {name for name, _ in model.named_parameters() if actor_key(name)}
    if set(source_actor) != target_actor_keys:
        missing = sorted(target_actor_keys - set(source_actor))
        extra = sorted(set(source_actor) - target_actor_keys)
        raise ValueError(f"actor state keys mismatch missing={missing} extra={extra}")
    for name, value in source_actor.items():
        if target_state[name].shape != value.shape:
            raise ValueError(f"actor tensor shape mismatch: {name}")
    loaded = model.load_state_dict(source_actor, strict=False)
    if loaded.unexpected_keys:
        raise ValueError(f"unexpected actor keys: {loaded.unexpected_keys}")
    expected_missing = {name for name in target_state if not actor_key(name)}
    if set(loaded.missing_keys) != expected_missing:
        raise ValueError("migration missing-key set is not exactly critic_v2")
    baseline = AlphaHoldemNet(num_actions=model.num_actions, norm_layer=model.norm_layer, critic_contract=CRITIC_V1).to(device)
    initialize_model(baseline, device)
    source_names = [name for name, _ in baseline.named_parameters()]
    source_ids = [item for group in source_optimizer.get("param_groups", []) for item in group.get("params", [])]
    if len(source_names) != len(source_ids):
        raise ValueError("source optimizer/model parameter count mismatch")
    source_id_by_name = dict(zip(source_names, source_ids))
    target_id_by_name = named_parameter_ids(model, optimizer)
    target_optimizer = optimizer.state_dict()
    if len(source_optimizer.get("param_groups", [])) != len(target_optimizer.get("param_groups", [])):
        raise ValueError("optimizer group count mismatch")
    migrated_state: dict[int, Any] = {}
    source_state = source_optimizer.get("state", {})
    for name in sorted(target_actor_param_names):
        source_id = source_id_by_name[name]
        target_id = target_id_by_name[name]
        if source_id in source_state:
            migrated_state[target_id] = copy.deepcopy(source_state[source_id])
    migrated_groups = copy.deepcopy(source_optimizer["param_groups"])
    target_groups = target_optimizer["param_groups"]
    for index, group in enumerate(migrated_groups):
        group["params"] = target_groups[index]["params"]
    optimizer.load_state_dict({"state": migrated_state, "param_groups": migrated_groups})
    current = model.state_dict()
    mismatched = [name for name in sorted(target_actor_keys) if not torch.equal(current[name].detach().cpu(), source_actor[name].detach().cpu())]
    if mismatched:
        raise ValueError(f"actor migration is not bitwise exact: {mismatched[:3]}")
    critic_params = {param for name, param in model.named_parameters() if not actor_key(name)}
    if any(param in optimizer.state for param in critic_params):
        raise ValueError("new critic optimizer state is not empty")
    del baseline
    return {"status": "PASS", "critic_contract": CRITIC_V2, "actor_tensor_count": len(target_actor_keys), "actor_optimizer_state_count": len(migrated_state), "new_critic_optimizer_state_count": 0, "source_value_head_reused": False}