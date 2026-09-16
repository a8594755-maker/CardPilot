#!/usr/bin/env python3
"""Fail-closed EXP-W1 value-head-only warmup.

The treatment consumes the first normal on-policy rollout batch, trains only
value_head on a preregistered whole-hand training split, and then returns control
to the unchanged PPO loop. It never changes reward semantics, the shared trunk,
policy weights, or policy logits.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn.functional as F


SCHEMA_VERSION = "v5.exp_w1.value_head_warmup.v1"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clone_tree(value: Any) -> Any:
    if torch.is_tensor(value):
        return value.detach().cpu().clone()
    if isinstance(value, dict):
        return {key: _clone_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_clone_tree(item) for item in value)
    return copy.deepcopy(value)


def _tree_equal(left: Any, right: Any) -> bool:
    if torch.is_tensor(left) and torch.is_tensor(right):
        return left.dtype == right.dtype and left.shape == right.shape and torch.equal(left.detach().cpu(), right.detach().cpu())
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_tree_equal(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, type(left)):
        return len(left) == len(right) and all(_tree_equal(a, b) for a, b in zip(left, right))
    return left == right


def _whole_hand_split(transitions: list[tuple], heldout_fraction: float, seed: int) -> tuple[np.ndarray, np.ndarray, int]:
    if not 0.05 <= heldout_fraction <= 0.5:
        raise ValueError("heldout_fraction must be in [0.05, 0.5]")
    blocks: list[list[int]] = []
    current: list[int] = []
    for index, transition in enumerate(transitions):
        if len(transition) <= 11:
            raise ValueError("EXP-W1 requires exact actual-hand markers at transition[11]")
        current.append(index)
        if float(transition[11]) > 0.5:
            blocks.append(current)
            current = []
    if current:
        raise ValueError("transition batch ends with an incomplete actual hand")
    if len(blocks) < 10:
        raise ValueError(f"EXP-W1 requires at least 10 complete hands, got {len(blocks)}")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(blocks))
    heldout_hands = max(1, int(round(len(blocks) * heldout_fraction)))
    heldout_ids = set(int(item) for item in order[:heldout_hands])
    train_rows = [row for hand_id, block in enumerate(blocks) if hand_id not in heldout_ids for row in block]
    heldout_rows = [row for hand_id, block in enumerate(blocks) if hand_id in heldout_ids for row in block]
    if not train_rows or not heldout_rows:
        raise ValueError("whole-hand split produced an empty partition")
    return np.asarray(train_rows, dtype=np.int64), np.asarray(heldout_rows, dtype=np.int64), len(blocks)


def _calibration(prediction: np.ndarray, target: np.ndarray) -> dict[str, float]:
    prediction = prediction.astype(np.float64, copy=False)
    target = target.astype(np.float64, copy=False)
    residual = target - prediction
    mse = float(np.mean(np.square(residual)))
    target_std = float(np.std(target, ddof=1)) if target.size > 1 else 0.0
    target_var = float(np.var(target, ddof=1)) if target.size > 1 else 0.0
    explained_variance = 1.0 - float(np.var(residual, ddof=1)) / target_var if target_var > 0 else float("nan")
    prediction_var = float(np.var(prediction, ddof=1)) if prediction.size > 1 else 0.0
    slope = float(np.cov(prediction, target, ddof=1)[0, 1]) / prediction_var if prediction_var > 0 else float("nan")
    intercept = float(np.mean(target) - slope * np.mean(prediction)) if math.isfinite(slope) else float("nan")
    return {
        "mse": mse,
        "rmse": math.sqrt(mse),
        "target_std": target_std,
        "rmse_over_target_std": math.sqrt(mse) / target_std if target_std > 0 else float("inf"),
        "explained_variance": explained_variance,
        "calibration_slope": slope,
        "calibration_intercept": intercept,
    }


def run_value_head_warmup(
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    transitions: list[tuple],
    device: str,
    compute_gae_fn: Callable[..., tuple[np.ndarray, np.ndarray]],
    epochs: int,
    mini_batch_size: int,
    gamma: float,
    heldout_fraction: float,
    min_relative_mse_reduction: float,
    split_seed: int,
    max_grad_norm: float = 0.5,
) -> dict[str, Any]:
    if epochs <= 0:
        raise ValueError("treatment warmup epochs must be positive")
    if mini_batch_size <= 0:
        raise ValueError("mini_batch_size must be positive")
    if not 0.0 < min_relative_mse_reduction < 1.0:
        raise ValueError("min_relative_mse_reduction must be in (0, 1)")
    if not transitions:
        raise ValueError("empty transition batch")
    if not hasattr(model, "value_head") or model.value_head is None:
        raise ValueError("model has no initialized value_head")

    train_rows, heldout_rows, hand_count = _whole_hand_split(transitions, heldout_fraction, split_seed)
    card_arr = np.asarray([item[0].reshape(6, 4, 13) for item in transitions], dtype=np.float32)
    action_arr = np.asarray([item[1].reshape(25, 4, 5) for item in transitions], dtype=np.float32)
    extra_arr = np.asarray([item[2] for item in transitions], dtype=np.float32)
    mask_arr = np.asarray([item[3] for item in transitions], dtype=np.float32)
    reward_arr = np.asarray([item[6] for item in transitions], dtype=np.float32)
    old_value_arr = np.asarray([item[7] for item in transitions], dtype=np.float32)
    done_arr = np.asarray([item[8] for item in transitions], dtype=np.float32)
    hero_chips = np.asarray([item[9] for item in transitions], dtype=np.float32)
    villain_chips = np.asarray([item[10] for item in transitions], dtype=np.float32)
    _, returns = compute_gae_fn(reward_arr, old_value_arr, done_arr, gamma=gamma)
    targets = np.maximum(np.minimum(np.asarray(returns, dtype=np.float32), villain_chips), -hero_chips)

    cards = torch.as_tensor(card_arr, device=device)
    actions = torch.as_tensor(action_arr, device=device)
    extras = torch.as_tensor(extra_arr, device=device)
    masks = torch.as_tensor(mask_arr, device=device)
    target_t = torch.as_tensor(targets, device=device)
    heldout_t = torch.as_tensor(heldout_rows, dtype=torch.long, device=device)

    original_training = model.training
    original_requires_grad = {name: parameter.requires_grad for name, parameter in model.named_parameters()}
    value_parameters = list(model.value_head.parameters())
    value_ids = {id(parameter) for parameter in value_parameters}
    non_value_state_before = {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.state_dict().items()
        if not name.startswith("value_head.")
    }
    non_value_optimizer_before = {
        id(parameter): _clone_tree(optimizer.state.get(parameter, {}))
        for group in optimizer.param_groups
        for parameter in group["params"]
        if id(parameter) not in value_ids
    }
    value_before = [parameter.detach().cpu().clone() for parameter in value_parameters]

    model.eval()
    with torch.no_grad():
        logits_before, values_before = model(cards[heldout_t], actions[heldout_t], extras[heldout_t], masks[heldout_t])
    reference_logits_before = logits_before[: min(4096, logits_before.shape[0])].detach().cpu().clone()
    before = _calibration(values_before.squeeze(-1).detach().cpu().numpy(), targets[heldout_rows])

    for parameter in model.parameters():
        parameter.requires_grad_(False)
    for parameter in value_parameters:
        parameter.requires_grad_(True)

    rng = np.random.default_rng(split_seed + 1)
    epoch_train_mse: list[float] = []
    work_rows = train_rows.copy()
    try:
        for _ in range(epochs):
            rng.shuffle(work_rows)
            losses: list[float] = []
            for start in range(0, len(work_rows), mini_batch_size):
                rows = torch.as_tensor(work_rows[start : start + mini_batch_size], dtype=torch.long, device=device)
                _, values = model(cards[rows], actions[rows], extras[rows], masks[rows])
                loss = F.mse_loss(values.squeeze(-1), target_t[rows])
                if not torch.isfinite(loss):
                    raise RuntimeError("non-finite EXP-W1 warmup loss")
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(value_parameters, max_grad_norm)
                optimizer.step()
                losses.append(float(loss.detach().cpu()))
            epoch_train_mse.append(float(np.mean(losses)))
    finally:
        for name, parameter in model.named_parameters():
            parameter.requires_grad_(original_requires_grad[name])
        model.train(original_training)

    model.eval()
    with torch.no_grad():
        logits_after, values_after = model(cards[heldout_t], actions[heldout_t], extras[heldout_t], masks[heldout_t])
    after = _calibration(values_after.squeeze(-1).detach().cpu().numpy(), targets[heldout_rows])
    policy_delta = float((logits_after[: reference_logits_before.shape[0]].detach().cpu() - reference_logits_before).abs().max())
    non_value_model_unchanged = all(
        torch.equal(non_value_state_before[name], tensor.detach().cpu())
        for name, tensor in model.state_dict().items()
        if name in non_value_state_before
    )
    non_value_optimizer_unchanged = all(
        _tree_equal(non_value_optimizer_before[id(parameter)], optimizer.state.get(parameter, {}))
        for group in optimizer.param_groups
        for parameter in group["params"]
        if id(parameter) in non_value_optimizer_before
    )
    value_delta = max(
        float((parameter.detach().cpu() - baseline).abs().max())
        for parameter, baseline in zip(value_parameters, value_before)
    )
    relative_mse_reduction = (before["mse"] - after["mse"]) / max(before["mse"], 1e-12)
    finite_metrics = all(math.isfinite(value) for value in (before["mse"], after["mse"], relative_mse_reduction))
    model.train(original_training)
    checks = {
        "finite_metrics": finite_metrics,
        "heldout_relative_mse_reduction": relative_mse_reduction >= min_relative_mse_reduction,
        "policy_logits_bitwise_unchanged": policy_delta == 0.0,
        "non_value_model_state_bitwise_unchanged": non_value_model_unchanged,
        "non_value_optimizer_state_unchanged": non_value_optimizer_unchanged,
        "value_head_changed": value_delta > 0.0,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "treatment": "VALUE_HEAD_ONLY_FIRST_ROLLOUT_WARMUP",
        "epochs": epochs,
        "mini_batch_size": mini_batch_size,
        "gamma": gamma,
        "split_seed": split_seed,
        "heldout_fraction": heldout_fraction,
        "minimum_relative_mse_reduction": min_relative_mse_reduction,
        "hands": hand_count,
        "transitions": len(transitions),
        "train_transitions": int(train_rows.size),
        "heldout_transitions": int(heldout_rows.size),
        "before": before,
        "after": after,
        "relative_mse_reduction": relative_mse_reduction,
        "policy_logits_max_abs_delta": policy_delta,
        "value_head_max_abs_delta": value_delta,
        "epoch_train_mse": epoch_train_mse,
        "checks": checks,
    }


def write_immutable_report(path: Path, payload: dict[str, Any]) -> str:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite immutable EXP-W1 report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    if os.name == "nt":
        os.chmod(path, stat.S_IREAD)
    else:
        os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return sha256_path(path)
