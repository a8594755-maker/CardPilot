#!/usr/bin/env python3
"""Load held-out-safe all-legal-action targets for Action-Q replay."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import torch


REPLAY_METADATA_CONTRACT_FIELDS = (
    "dataset_sha256",
    "total_rows",
    "training_rows",
    "validation_rows_held_out",
    "test_rows_held_out",
    "split_seed",
    "validation_fraction",
    "test_fraction",
    "effective_stack_divisor",
    "uncertainty_floor_bb",
    "max_weight_ratio",
    "uncertainty_standard_error_mode",
    "continuation_styles_for_cluster_se",
    "uncertainty_target_basis",
    "reliability_precision_normalization",
    "train_mean_precision",
    "split_stratification",
    "position_street_coverage",
    "position_street_trajectory_coverage",
    "trajectory_opponent_styles",
    "target",
)

REPLAY_TRAINING_CONFIG_FIELDS = (
    "policy_advantage_normalization",
    "action_normalization_min_rows",
    "action_q_hidden",
    "action_q_advantage",
    "action_q_loss_coef",
    "action_q_residual_l2_coef",
    "action_q_support_prior_rows",
    "action_q_policy_mix",
    "action_q_dueling",
    "action_q_counterfactual_dataset_sha256",
    "action_q_counterfactual_loss_coef",
    "action_q_counterfactual_policy_loss_coef",
    "action_q_counterfactual_policy_target_clip",
    "action_q_counterfactual_policy_temperature",
    "action_q_counterfactual_policy_reliability_mode",
    "action_q_counterfactual_target_mode",
    "action_q_counterfactual_lcb_z",
    "action_q_counterfactual_loss_decay_hands",
    "action_q_counterfactual_batch_size",
    "action_q_counterfactual_max_batches_per_update",
    "action_q_counterfactual_split_seed",
    "action_q_counterfactual_validation_fraction",
    "action_q_counterfactual_test_fraction",
    "action_q_counterfactual_stratify_trajectory_opponent",
    "action_q_counterfactual_uncertainty_floor_bb",
    "action_q_counterfactual_max_weight_ratio",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def conservative_continuation_cluster_se(
    q_se: np.ndarray,
    legal: np.ndarray,
    continuation_se: np.ndarray | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Guard marginal-Q uncertainty against shared-deal continuation correlation.

    Continuation policies are evaluated on common hidden deals and runouts.  Their
    errors therefore are not independent.  When per-continuation standard errors
    are available, the mean of those standard errors is an upper bound on the
    standard error of their equally weighted marginal mean under arbitrary
    cross-continuation correlation.  Never reduce the producer's naive pooled SE.
    """
    q_se = np.asarray(q_se, dtype=np.float32)
    legal = np.asarray(legal, dtype=bool)
    if q_se.shape != legal.shape:
        raise ValueError("Q-target SE and legal-mask shapes differ")
    if not np.array_equal(np.isfinite(q_se), legal):
        raise ValueError("every and only legal actions must have finite Q uncertainty")
    if (q_se[legal] < 0.0).any():
        raise ValueError("Q-target standard errors must be nonnegative")
    if continuation_se is None:
        return q_se.copy(), {
            "mode": "producer_pooled_outcome_se",
            "continuation_styles": 0,
            "legal_entries_increased": 0,
            "legal_entries_increased_rate": 0.0,
        }

    continuation_se = np.asarray(continuation_se, dtype=np.float32)
    if continuation_se.ndim != 3:
        raise ValueError(
            "continuation SE shape must be rows x styles x actions; "
            f"actual={continuation_se.shape}"
        )
    expected_shape = (q_se.shape[0], continuation_se.shape[1], q_se.shape[1])
    if continuation_se.shape != expected_shape:
        raise ValueError(
            "continuation SE shape must be rows x styles x actions; "
            f"expected={expected_shape} actual={continuation_se.shape}"
        )
    if continuation_se.shape[1] < 1:
        raise ValueError("continuation SE needs at least one style")
    expected_finite = np.broadcast_to(legal[:, None, :], continuation_se.shape)
    if not np.array_equal(np.isfinite(continuation_se), expected_finite):
        raise ValueError(
            "every and only legal continuation actions must have finite uncertainty"
        )
    if (continuation_se[expected_finite] < 0.0).any():
        raise ValueError("continuation standard errors must be nonnegative")

    cluster_upper = np.nansum(continuation_se, axis=1) / float(
        continuation_se.shape[1]
    )
    cluster_upper = np.where(legal, cluster_upper, np.nan)
    effective = np.where(legal, np.maximum(q_se, cluster_upper), np.nan).astype(
        np.float32
    )
    increased = legal & (effective > q_se + 1e-12)
    return effective, {
        "mode": "max_producer_se_and_per_continuation_perfect_correlation_bound",
        "continuation_styles": int(continuation_se.shape[1]),
        "legal_entries_increased": int(increased.sum()),
        "legal_entries_increased_rate": float(increased.sum() / legal.sum()),
        "mean_producer_legal_se_bb": float(q_se[legal].mean()),
        "mean_effective_legal_se_bb": float(effective[legal].mean()),
    }


def _split_stratum(
    indices: np.ndarray,
    *,
    rng: np.random.Generator,
    validation_fraction: float,
    test_fraction: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    shuffled = np.asarray(indices, dtype=np.int64).copy()
    rng.shuffle(shuffled)
    count = len(shuffled)
    if count < 3:
        raise ValueError(
            "each position/street stratum needs at least three rows for "
            "train/validation/test isolation"
        )
    validation_count = max(1, int(round(count * validation_fraction)))
    test_count = max(1, int(round(count * test_fraction)))
    if validation_count + test_count >= count:
        validation_count = 1
        test_count = 1
    test = shuffled[:test_count]
    validation = shuffled[test_count : test_count + validation_count]
    train = shuffled[test_count + validation_count :]
    if not len(train):
        raise ValueError("counterfactual replay split produced no training rows")
    return train, validation, test


def position_street_split_indices(
    target_player: np.ndarray,
    street: np.ndarray,
    *,
    seed: int,
    validation_fraction: float,
    test_fraction: float,
    require_balanced_flop_turn: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, dict[str, int]]]:
    """Split every seat/street group independently and report exact coverage."""
    target_player = np.asarray(target_player, dtype=np.int64)
    street = np.asarray(street, dtype=np.int64)
    if target_player.shape != street.shape or target_player.ndim != 1:
        raise ValueError("target_player and street must be equal-length 1-D arrays")
    if not np.isin(target_player, (0, 1)).all():
        raise ValueError("target_player must contain only 0=BB or 1=SB")
    if not np.isin(street, (1, 2)).all():
        raise ValueError("counterfactual replay is scoped to flop/turn only")

    present = {
        (int(player), int(street_id))
        for player, street_id in zip(target_player, street)
    }
    required = {(0, 1), (0, 2), (1, 1), (1, 2)}
    if require_balanced_flop_turn and present != required:
        raise ValueError(
            "balanced replay requires BB/SB x flop/turn coverage; "
            f"present={sorted(present)}"
        )

    rng = np.random.default_rng(seed)
    train_parts: list[np.ndarray] = []
    validation_parts: list[np.ndarray] = []
    test_parts: list[np.ndarray] = []
    coverage: dict[str, dict[str, int]] = {}
    for player, street_id in sorted(present):
        group = np.flatnonzero(
            (target_player == player) & (street == street_id)
        )
        train, validation, test = _split_stratum(
            group,
            rng=rng,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
        )
        label = f"{'bb' if player == 0 else 'sb'}_{'flop' if street_id == 1 else 'turn'}"
        coverage[label] = {
            "total": int(len(group)),
            "train": int(len(train)),
            "validation": int(len(validation)),
            "test": int(len(test)),
        }
        train_parts.append(train)
        validation_parts.append(validation)
        test_parts.append(test)

    train = np.concatenate(train_parts)
    validation = np.concatenate(validation_parts)
    test = np.concatenate(test_parts)
    rng.shuffle(train)
    rng.shuffle(validation)
    rng.shuffle(test)
    return train, validation, test, coverage


def position_street_trajectory_split_indices(
    target_player: np.ndarray,
    street: np.ndarray,
    trajectory_opponent_index: np.ndarray,
    *,
    seed: int,
    validation_fraction: float,
    test_fraction: float,
    require_balanced_flop_turn: bool = True,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, dict[str, int]],
    dict[str, dict[str, int]],
]:
    """Split every seat/street/trajectory group independently.

    This prevents opponent styles that reach a target street less frequently
    from disappearing from validation or test and keeps the split contract
    independent of their naturally unequal state counts.
    """
    target_player = np.asarray(target_player, dtype=np.int64)
    street = np.asarray(street, dtype=np.int64)
    trajectory = np.asarray(trajectory_opponent_index, dtype=np.int64)
    if (
        target_player.shape != street.shape
        or target_player.shape != trajectory.shape
        or target_player.ndim != 1
    ):
        raise ValueError(
            "player, street, and trajectory opponent must be equal-length 1-D arrays"
        )
    if not np.isin(target_player, (0, 1)).all():
        raise ValueError("target_player must contain only 0=BB or 1=SB")
    if not np.isin(street, (1, 2)).all():
        raise ValueError("counterfactual replay is scoped to flop/turn only")
    if (trajectory < 0).any():
        raise ValueError("trajectory opponent indices must be nonnegative")
    styles = sorted(set(trajectory.tolist()))
    if not styles:
        raise ValueError("trajectory-stratified replay has no opponent styles")
    required_cells = {(0, 1), (0, 2), (1, 1), (1, 2)}
    present_cells = set(zip(target_player.tolist(), street.tolist()))
    if require_balanced_flop_turn and present_cells != required_cells:
        raise ValueError(
            "balanced replay requires BB/SB x flop/turn coverage; "
            f"present={sorted(present_cells)}"
        )
    if not present_cells or not present_cells.issubset(required_cells):
        raise ValueError(f"invalid position/street cells: {sorted(present_cells)}")
    split_cells = required_cells if require_balanced_flop_turn else present_cells

    rng = np.random.default_rng(seed)
    train_parts: list[np.ndarray] = []
    validation_parts: list[np.ndarray] = []
    test_parts: list[np.ndarray] = []
    trajectory_coverage: dict[str, dict[str, int]] = {}
    position_coverage = {
        f"{'bb' if player == 0 else 'sb'}_{'flop' if street_id == 1 else 'turn'}": {
            "total": 0,
            "train": 0,
            "validation": 0,
            "test": 0,
        }
        for player, street_id in sorted(split_cells)
    }
    for player, street_id in sorted(split_cells):
        cell_label = (
            f"{'bb' if player == 0 else 'sb'}_"
            f"{'flop' if street_id == 1 else 'turn'}"
        )
        for style in styles:
            group = np.flatnonzero(
                (target_player == player)
                & (street == street_id)
                & (trajectory == style)
            )
            if len(group) < 3:
                raise ValueError(
                    "every position/street/trajectory stratum needs at least "
                    f"three rows; {cell_label}_trajectory{style} has {len(group)}"
                )
            train, validation, test = _split_stratum(
                group,
                rng=rng,
                validation_fraction=validation_fraction,
                test_fraction=test_fraction,
            )
            label = f"{cell_label}_trajectory{style}"
            counts = {
                "total": int(len(group)),
                "train": int(len(train)),
                "validation": int(len(validation)),
                "test": int(len(test)),
            }
            trajectory_coverage[label] = counts
            for key, value in counts.items():
                position_coverage[cell_label][key] += value
            train_parts.append(train)
            validation_parts.append(validation)
            test_parts.append(test)

    train = np.concatenate(train_parts)
    validation = np.concatenate(validation_parts)
    test = np.concatenate(test_parts)
    rng.shuffle(train)
    rng.shuffle(validation)
    rng.shuffle(test)
    return train, validation, test, position_coverage, trajectory_coverage


def train_normalized_reliability_weights(
    q_se: np.ndarray,
    legal: np.ndarray,
    train_idx: np.ndarray,
    *,
    uncertainty_floor_bb: float,
    max_weight_ratio: float,
) -> tuple[np.ndarray, float]:
    """Build reliability weights without consulting held-out uncertainty.

    The normalization constant and clipping scale are calibrated exclusively
    from legal actions in the training split.  Validation and test rows still
    receive weights for evaluation, but changing their uncertainty cannot
    alter any training weight.
    """
    q_se = np.asarray(q_se, dtype=np.float32)
    legal = np.asarray(legal, dtype=bool)
    train_idx = np.asarray(train_idx, dtype=np.int64)
    if q_se.shape != legal.shape:
        raise ValueError("q_se and legal masks must have identical shapes")
    if train_idx.ndim != 1 or train_idx.size == 0:
        raise ValueError("train_idx must be a nonempty one-dimensional array")
    if np.any((train_idx < 0) | (train_idx >= len(q_se))):
        raise ValueError("train_idx contains an out-of-range row")
    if uncertainty_floor_bb <= 0.0:
        raise ValueError("uncertainty_floor_bb must be positive")
    if max_weight_ratio < 1.0:
        raise ValueError("max_weight_ratio must be at least one")

    precision = np.where(
        legal,
        1.0
        / (
            np.square(np.nan_to_num(q_se, nan=0.0))
            + float(uncertainty_floor_bb) ** 2
        ),
        0.0,
    )
    train_legal = legal[train_idx]
    if not train_legal.any():
        raise ValueError("training split contains no legal actions")
    train_mean_precision = float(precision[train_idx][train_legal].mean())
    reliability = np.where(
        legal,
        np.clip(
            precision / max(train_mean_precision, 1e-12),
            1.0 / float(max_weight_ratio),
            float(max_weight_ratio),
        ),
        0.0,
    ).astype(np.float32)
    return reliability, train_mean_precision


def load_counterfactual_q_replay(
    dataset_path: str | Path,
    *,
    expected_sha256: str,
    device: str | torch.device,
    effective_stack_divisor: float,
    split_seed: int,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    uncertainty_floor_bb: float = 0.25,
    max_weight_ratio: float = 20.0,
    target_mode: str = "mean",
    lcb_z: float = 1.96,
    initial_cursor: int = 0,
    initial_total_draws: int = 0,
    stratify_trajectory_opponent: bool = False,
    require_balanced_flop_turn: bool = True,
) -> dict[str, Any]:
    """Load only the training split; validation/test rows never reach PPO."""
    path = Path(dataset_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_sha256 = sha256_file(path)
    if not expected_sha256 or actual_sha256 != expected_sha256.lower():
        raise ValueError(
            "counterfactual dataset SHA256 mismatch: "
            f"expected={expected_sha256!r} actual={actual_sha256}"
        )
    if effective_stack_divisor <= 0.0:
        raise ValueError("effective_stack_divisor must be positive")
    if uncertainty_floor_bb <= 0.0:
        raise ValueError("uncertainty_floor_bb must be positive")
    if max_weight_ratio < 1.0:
        raise ValueError("max_weight_ratio must be at least one")
    if target_mode not in {"mean", "advantage_lcb"}:
        raise ValueError("target_mode must be mean or advantage_lcb")
    if lcb_z < 0.0:
        raise ValueError("lcb_z must be nonnegative")
    if int(initial_total_draws) < 0:
        raise ValueError("initial replay total draws must be nonnegative")
    if (
        validation_fraction <= 0.0
        or test_fraction <= 0.0
        or validation_fraction + test_fraction >= 0.8
    ):
        raise ValueError(
            "validation/test fractions must be positive and sum to less than 0.8"
        )

    with np.load(path) as data:
        required = {
            "card_info",
            "action_info",
            "extra_info",
            "legal_mask",
            "q_target_bb",
            "q_target_se_bb",
            "target_player",
            "street",
        }
        missing = sorted(required - set(data.files))
        if missing:
            raise ValueError(f"counterfactual dataset missing arrays: {missing}")
        cards = np.asarray(data["card_info"], dtype=np.float32)
        actions = np.asarray(data["action_info"], dtype=np.float32)
        extras = np.asarray(data["extra_info"], dtype=np.float32)
        masks = np.asarray(data["legal_mask"], dtype=np.float32)
        raw_q = np.asarray(data["q_target_bb"], dtype=np.float32)
        absolute_q_se = np.asarray(data["q_target_se_bb"], dtype=np.float32)
        paired_uncertainty = (
            "q_target_anchor_advantage_se_bb" in data.files
            and "q_target_anchor_advantage_by_continuation_se_bb" in data.files
        )
        if paired_uncertainty:
            q_se = np.asarray(
                data["q_target_anchor_advantage_se_bb"], dtype=np.float32
            )
            continuation_se = np.asarray(
                data[
                    "q_target_anchor_advantage_by_continuation_se_bb"
                ],
                dtype=np.float32,
            )
            anchor_slot = np.asarray(data["anchor_slot"], dtype=np.int64)
            uncertainty_target_basis = (
                "paired_action_minus_anchor_common_random_numbers"
            )
        else:
            q_se = absolute_q_se
            continuation_se = (
                np.asarray(
                    data["q_target_by_continuation_se_bb"], dtype=np.float32
                )
                if "q_target_by_continuation_se_bb" in data.files
                else None
            )
            anchor_slot = None
            uncertainty_target_basis = "absolute_action_return"
        target_player = np.asarray(data["target_player"], dtype=np.int64)
        street = np.asarray(data["street"], dtype=np.int64)
        trajectory_opponent_index = (
            np.asarray(data["trajectory_opponent_index"], dtype=np.int64)
            if "trajectory_opponent_index" in data.files
            else None
        )

    count = len(cards)
    expected_shapes = {
        "card_info": (count, 6, 4, 13),
        "action_info": (count, 25, 4, 5),
        "extra_info": (count, 3),
        "legal_mask": (count, 9),
        "q_target_bb": (count, 9),
        "q_target_se_bb": (count, 9),
        "target_player": (count,),
        "street": (count,),
    }
    actual_shapes = {
        "card_info": cards.shape,
        "action_info": actions.shape,
        "extra_info": extras.shape,
        "legal_mask": masks.shape,
        "q_target_bb": raw_q.shape,
        "q_target_se_bb": q_se.shape,
        "target_player": target_player.shape,
        "street": street.shape,
    }
    bad_shapes = {
        key: {"expected": expected_shapes[key], "actual": actual_shapes[key]}
        for key in expected_shapes
        if actual_shapes[key] != expected_shapes[key]
    }
    if bad_shapes:
        raise ValueError(f"counterfactual dataset shape mismatch: {bad_shapes}")
    if count == 0:
        raise ValueError("counterfactual dataset is empty")
    if not np.isfinite(cards).all() or not np.isfinite(actions).all():
        raise ValueError("counterfactual observations contain non-finite values")
    if not np.isfinite(extras).all() or not np.isfinite(masks).all():
        raise ValueError("counterfactual metadata contains non-finite values")
    if not np.isin(masks, (0.0, 1.0)).all():
        raise ValueError("legal_mask must be binary")
    legal = masks > 0.5
    if not np.array_equal(np.isfinite(raw_q), legal):
        raise ValueError("every and only legal actions must have finite Q targets")
    q_se, uncertainty_se_contract = conservative_continuation_cluster_se(
        q_se,
        legal,
        continuation_se,
    )
    if anchor_slot is not None:
        if anchor_slot.shape != (count,):
            raise ValueError("anchor_slot shape mismatch")
        row = np.arange(count)
        if np.any((anchor_slot < 0) | (anchor_slot >= raw_q.shape[1])):
            raise ValueError("anchor_slot is out of range")
        if not legal[row, anchor_slot].all():
            raise ValueError("anchor_slot must be legal on every replay row")
        if not np.allclose(
            q_se[row, anchor_slot],
            0.0,
            rtol=0.0,
            atol=1e-7,
        ):
            raise ValueError("paired anchor-action uncertainty must be zero")
    uncertainty_se_contract["target_basis"] = uncertainty_target_basis
    uncertainty_se_contract["mean_absolute_action_legal_se_bb"] = float(
        absolute_q_se[legal].mean()
    )
    if not np.array_equal(extras[:, 2], target_player.astype(np.float32)):
        raise ValueError("target_player disagrees with the observation position feature")

    trajectory_coverage: dict[str, dict[str, int]] | None = None
    if stratify_trajectory_opponent:
        if trajectory_opponent_index is None:
            raise ValueError(
                "trajectory-stratified replay requires trajectory_opponent_index"
            )
        (
            train_idx,
            validation_idx,
            test_idx,
            coverage,
            trajectory_coverage,
        ) = position_street_trajectory_split_indices(
            target_player,
            street,
            trajectory_opponent_index,
            seed=split_seed,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            require_balanced_flop_turn=require_balanced_flop_turn,
        )
    else:
        train_idx, validation_idx, test_idx, coverage = position_street_split_indices(
            target_player,
            street,
            seed=split_seed,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
            require_balanced_flop_turn=require_balanced_flop_turn,
        )

    fit_raw_q = raw_q
    if target_mode == "advantage_lcb":
        if anchor_slot is None or not paired_uncertainty:
            raise ValueError(
                "advantage_lcb replay requires paired anchor-action "
                "common-random-number uncertainty"
            )
        row = np.arange(count)
        q_se_zero = np.nan_to_num(q_se, nan=0.0)
        anchor_se = q_se_zero[row, anchor_slot][:, None]
        penalty = float(lcb_z) * np.sqrt(
            np.square(q_se_zero) + np.square(anchor_se)
        )
        fit_raw_q = np.where(
            legal,
            raw_q - penalty,
            np.nan,
        ).astype(np.float32)
        fit_raw_q[row, anchor_slot] = raw_q[row, anchor_slot]

    q_zero = np.where(legal, fit_raw_q, 0.0)
    legal_count = legal.sum(axis=1, keepdims=True)
    if (legal_count == 0).any():
        raise ValueError("every replay state must have at least one legal action")
    q_center = q_zero.sum(axis=1, keepdims=True) / legal_count
    q_target = np.where(legal, q_zero - q_center, 0.0)
    q_target /= float(effective_stack_divisor)

    reliability, train_mean_precision = train_normalized_reliability_weights(
        q_se,
        legal,
        train_idx,
        uncertainty_floor_bb=uncertainty_floor_bb,
        max_weight_ratio=max_weight_ratio,
    )

    train_idx_t = torch.from_numpy(train_idx)
    replay_device = torch.device(device)
    replay: dict[str, Any] = {
        "cards": torch.from_numpy(cards)[train_idx_t].to(replay_device),
        "actions": torch.from_numpy(actions)[train_idx_t].to(replay_device),
        "extras": torch.from_numpy(extras)[train_idx_t].to(replay_device),
        "masks": torch.from_numpy(masks)[train_idx_t].to(replay_device),
        "q_target": torch.from_numpy(q_target.astype(np.float32))[train_idx_t].to(
            replay_device
        ),
        "weights": torch.from_numpy(reliability)[train_idx_t].to(replay_device),
        "cursor": int(initial_cursor) % len(train_idx),
        "total_draws": int(initial_total_draws),
        "metadata": {
            "schema": "cardpilot.counterfactual_q_replay.v1",
            "dataset": str(path),
            "dataset_sha256": actual_sha256,
            "total_rows": int(count),
            "training_rows": int(len(train_idx)),
            "validation_rows_held_out": int(len(validation_idx)),
            "test_rows_held_out": int(len(test_idx)),
            "split_seed": int(split_seed),
            "validation_fraction": float(validation_fraction),
            "test_fraction": float(test_fraction),
            "effective_stack_divisor": float(effective_stack_divisor),
            "uncertainty_floor_bb": float(uncertainty_floor_bb),
            "max_weight_ratio": float(max_weight_ratio),
            "uncertainty_standard_error_mode": str(
                uncertainty_se_contract["mode"]
            ),
            "continuation_styles_for_cluster_se": int(
                uncertainty_se_contract["continuation_styles"]
            ),
            "uncertainty_target_basis": uncertainty_target_basis,
            "reliability_precision_normalization": "train_legal_mean_only",
            "train_mean_precision": float(train_mean_precision),
            "uncertainty_standard_error_diagnostic": uncertainty_se_contract,
            "split_stratification": (
                "position_street_trajectory"
                if stratify_trajectory_opponent
                else "position_street"
            ),
            "position_street_coverage": coverage,
            "position_street_trajectory_coverage": trajectory_coverage,
            "trajectory_opponent_styles": (
                sorted(set(trajectory_opponent_index.tolist()))
                if trajectory_opponent_index is not None
                else None
            ),
            "target": {
                "mode": str(target_mode),
                "centered_over_legal_actions": True,
                "effective_stack_divisor": float(effective_stack_divisor),
                "lcb_z": (
                    float(lcb_z) if target_mode == "advantage_lcb" else None
                ),
                "anchor_action_unchanged": bool(
                    target_mode == "advantage_lcb"
                ),
            },
        },
    }
    return replay


def replay_checkpoint_state(replay: dict[str, Any] | None) -> dict[str, Any] | None:
    if replay is None:
        return None
    return {
        **dict(replay["metadata"]),
        "cursor": int(replay["cursor"]),
        "total_draws": int(replay.get("total_draws", 0)),
    }


def restore_replay_progress(
    resumed_state: dict[str, Any] | None,
    *,
    requested_sha256: str,
    current_lineage_hands: int,
) -> tuple[int, int, int]:
    """Restore cursor and the original loss-decay origin across a resume."""
    current_lineage_hands = int(current_lineage_hands)
    if current_lineage_hands < 0:
        raise ValueError("current lineage hands must be nonnegative")
    if not resumed_state:
        return 0, current_lineage_hands, 0
    resumed_sha = str(resumed_state.get("dataset_sha256") or "").lower()
    requested_sha = str(requested_sha256 or "").lower()
    if not requested_sha or resumed_sha != requested_sha:
        raise ValueError(
            "resumed counterfactual replay dataset identity changed: "
            f"source={resumed_sha} requested={requested_sha}"
        )
    cursor = int(resumed_state.get("cursor", 0))
    if cursor < 0:
        raise ValueError("resumed counterfactual replay cursor must be nonnegative")
    total_draws = int(resumed_state.get("total_draws", 0))
    if total_draws < 0:
        raise ValueError("resumed counterfactual replay total draws must be nonnegative")
    start_hands = int(
        resumed_state.get("start_lineage_training_hands", current_lineage_hands)
    )
    if start_hands < 0 or start_hands > current_lineage_hands:
        raise ValueError(
            "resumed counterfactual replay decay origin is outside lineage: "
            f"start={start_hands} current={current_lineage_hands}"
        )
    return cursor, start_hands, total_draws


def decayed_replay_coefficient(
    base_coefficient: float,
    *,
    current_lineage_hands: int,
    start_lineage_hands: int,
    decay_hands: int,
) -> tuple[float, int]:
    """Return a resume-invariant linear replay coefficient and elapsed hands."""
    elapsed_hands = max(
        int(current_lineage_hands) - int(start_lineage_hands),
        0,
    )
    coefficient = float(base_coefficient)
    if int(decay_hands) > 0:
        coefficient *= max(
            0.0,
            1.0 - elapsed_hands / float(decay_hands),
        )
    return coefficient, elapsed_hands


def validate_replay_metadata_contract(
    resumed_state: dict[str, Any],
    current_metadata: dict[str, Any],
) -> None:
    """Fail if identical data are reinterpreted under another split/weighting."""
    for field in REPLAY_METADATA_CONTRACT_FIELDS:
        if field not in resumed_state or field not in current_metadata:
            raise ValueError(f"counterfactual replay metadata lacks {field}")
        if resumed_state[field] != current_metadata[field]:
            raise ValueError(
                "counterfactual replay metadata contract changed: "
                f"{field} source={resumed_state[field]!r} "
                f"requested={current_metadata[field]!r}"
            )


def validate_replay_training_config(
    previous_config: dict[str, Any],
    requested_config: dict[str, Any],
) -> None:
    """Keep supervision and target semantics exact across optimizer resumes."""
    for field in REPLAY_TRAINING_CONFIG_FIELDS:
        if field not in previous_config or field not in requested_config:
            raise ValueError(f"counterfactual replay config lacks {field}")
        previous = previous_config[field]
        requested = requested_config[field]
        if field.endswith("sha256"):
            previous = str(previous or "").lower()
            requested = str(requested or "").lower()
        if previous != requested:
            raise ValueError(
                "counterfactual replay training contract changed: "
                f"{field} source={previous!r} requested={requested!r}"
            )
