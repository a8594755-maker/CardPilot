"""Distill separate SB and BB policy teachers into one pure-weight policy.

The input observations are reconstructed from completed Slumbot decision dumps.
Targets come only from frozen neural-network teachers: the SB teacher supplies
position 1 targets and the BB teacher supplies position 0 targets.  Deployment
uses the resulting single network with no evaluator-side seat switch.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(THIS_DIR))

from compare_policy_on_slumbot_dumps import load_model
from alpha_holdem.network import AlphaHoldemNet
from offline_slumbot_awr import (
    atomic_torch_save,
    reservoir_rows,
    sha256_path,
)


def dump_files(directories: list[str]) -> list[Path]:
    files: list[Path] = []
    for value in directories:
        directory = Path(value).resolve()
        if not directory.is_dir():
            raise FileNotFoundError(f"dump directory does not exist: {directory}")
        files.extend(directory.glob("*_dump.jsonl"))
    selected = sorted(set(path.resolve() for path in files))
    if not selected:
        raise RuntimeError("no decision dump files found")
    return selected


def collect_rows(
    files: list[Path],
    max_rows_per_actor: int,
    seed: int,
    obs_version: str,
    raise_action_mapping: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ingest: dict[str, Any] = {}
    for offset, actor in enumerate(("hero", "opp")):
        actor_rows, actor_ingest = reservoir_rows(
            files=files,
            max_rows=max_rows_per_actor,
            seed=seed + offset,
            obs_version=obs_version,
            street_min=0,
            street_max=3,
            actor=actor,
            position=None,
            raise_action_mapping=raise_action_mapping,
        )
        rows.extend(actor_rows)
        ingest[actor] = actor_ingest
    random.Random(seed + 2).shuffle(rows)
    ingest["combined_rows"] = len(rows)
    ingest["position_counts"] = {
        str(key): int(value)
        for key, value in sorted(
            Counter(int(row["position"]) for row in rows).items()
        )
    }
    ingest["street_counts"] = {
        str(key): int(value)
        for key, value in sorted(
            Counter(int(row["street"]) for row in rows).items()
        )
    }
    return rows, ingest


def stack_rows(rows: list[dict[str, Any]]) -> TensorDataset:
    return TensorDataset(
        torch.from_numpy(np.stack([row["card"] for row in rows])),
        torch.from_numpy(np.stack([row["action"] for row in rows])),
        torch.from_numpy(np.stack([row["extra"] for row in rows])),
        torch.from_numpy(np.stack([row["legal"] for row in rows])),
        torch.tensor([row["position"] for row in rows], dtype=torch.long),
        torch.tensor([row["street"] for row in rows], dtype=torch.long),
    )


def model_extras(
    model: torch.nn.Module,
    extras: torch.Tensor,
    position: torch.Tensor,
) -> torch.Tensor:
    if int(getattr(model, "position_adapter_hidden", 0)) <= 0:
        return extras
    return torch.cat(
        [extras, position.to(extras.dtype).unsqueeze(1)],
        dim=1,
    )


def clone_with_position_adapter(
    source: AlphaHoldemNet,
    hidden: int,
) -> AlphaHoldemNet:
    if hidden <= 0:
        return source
    student = AlphaHoldemNet(
        num_actions=source.num_actions,
        norm_layer=source.norm_layer,
        separate_preflop_head=source.separate_preflop_head,
        preflop_adapter_hidden=source.preflop_adapter_hidden,
        preflop_raw_adapter_hidden=source.preflop_raw_adapter_hidden,
        preflop_raw_action_scale=source.preflop_raw_action_scale,
        preflop_raw_gate=source.preflop_raw_gate,
        flop_adapter_hidden=source.flop_adapter_hidden,
        postflop_adapter_hidden=source.postflop_adapter_hidden,
        position_adapter_hidden=hidden,
        critic_contract=source.critic_contract,
        critic_init_seed=source.critic_init_seed,
    )
    student.eval()
    with torch.no_grad():
        student(
            torch.zeros(2, 6, 4, 13),
            torch.zeros(2, 25, 4, 5),
            torch.zeros(2, 3),
        )
    incompatible = student.load_state_dict(
        source.state_dict(),
        strict=False,
    )
    expected_missing = {
        f"position_policy_adapters.{seat}.{layer}.{parameter}"
        for seat in (0, 1)
        for layer in (0, 2)
        for parameter in ("weight", "bias")
    }
    if set(incompatible.missing_keys) != expected_missing:
        raise RuntimeError(
            "unexpected missing keys while adding position adapter: "
            f"{incompatible.missing_keys}"
        )
    if incompatible.unexpected_keys:
        raise RuntimeError(
            "unexpected source keys while adding position adapter: "
            f"{incompatible.unexpected_keys}"
        )
    return student


def teacher_loss(
    student_logits: torch.Tensor,
    target_logits: torch.Tensor,
    position: torch.Tensor,
    temperature: float,
) -> tuple[torch.Tensor, dict[str, float]]:
    target_probability = F.softmax(target_logits / temperature, dim=-1)
    row_kl = (
        target_probability
        * (
            F.log_softmax(target_logits / temperature, dim=-1)
            - F.log_softmax(student_logits / temperature, dim=-1)
        )
    ).sum(dim=-1) * (temperature**2)
    losses: list[torch.Tensor] = []
    position_losses: dict[str, float] = {}
    for seat in (0, 1):
        mask = position == seat
        if bool(mask.any()):
            seat_loss = row_kl[mask].mean()
            losses.append(seat_loss)
            position_losses[f"p{seat}"] = float(seat_loss.detach())
    if len(losses) != 2:
        raise RuntimeError("a training batch is missing one position")
    return torch.stack(losses).mean(), position_losses


@torch.no_grad()
def evaluate(
    student: torch.nn.Module,
    sb_teacher: torch.nn.Module,
    bb_teacher: torch.nn.Module,
    loader: DataLoader,
    device: str,
    temperature: float,
) -> dict[str, Any]:
    student.eval()
    sb_teacher.eval()
    bb_teacher.eval()
    totals = Counter()
    agreements = Counter()
    kl_sums = Counter()
    for cards, actions, extras, legal, position, street in loader:
        cards = cards.to(device, non_blocking=True)
        actions = actions.to(device, non_blocking=True)
        extras = extras.to(device, non_blocking=True)
        legal = legal.to(device, non_blocking=True)
        position = position.to(device, non_blocking=True)
        street = street.to(device, non_blocking=True)
        student_logits, _ = student(
            cards,
            actions,
            model_extras(student, extras, position),
            legal,
        )
        sb_logits, _ = sb_teacher(
            cards,
            actions,
            model_extras(sb_teacher, extras, position),
            legal,
        )
        bb_logits, _ = bb_teacher(
            cards,
            actions,
            model_extras(bb_teacher, extras, position),
            legal,
        )
        target_logits = torch.where(
            (position == 0).unsqueeze(1),
            bb_logits,
            sb_logits,
        )
        student_action = student_logits.argmax(dim=-1)
        target_action = target_logits.argmax(dim=-1)
        target_probability = F.softmax(target_logits / temperature, dim=-1)
        row_kl = (
            target_probability
            * (
                F.log_softmax(target_logits / temperature, dim=-1)
                - F.log_softmax(student_logits / temperature, dim=-1)
            )
        ).sum(dim=-1)
        for seat in (0, 1):
            for street_index in (0, 1, 2, 3):
                mask = (position == seat) & (street == street_index)
                count = int(mask.sum())
                if count == 0:
                    continue
                key = f"p{seat}s{street_index}"
                totals[key] += count
                agreements[key] += int(
                    ((student_action == target_action) & mask).sum()
                )
                kl_sums[key] += float(row_kl[mask].sum())

    slice_metrics = {
        key: {
            "rows": int(count),
            "argmax_agreement": agreements[key] / count,
            "teacher_to_student_kl": kl_sums[key] / count,
        }
        for key, count in sorted(totals.items())
    }
    position_metrics: dict[str, Any] = {}
    for seat in (0, 1):
        keys = [key for key in totals if key.startswith(f"p{seat}s")]
        total = sum(totals[key] for key in keys)
        position_metrics[f"p{seat}"] = {
            "rows": int(total),
            "argmax_agreement": (
                sum(agreements[key] for key in keys) / max(total, 1)
            ),
            "teacher_to_student_kl": (
                sum(kl_sums[key] for key in keys) / max(total, 1)
            ),
        }
    p0 = float(position_metrics["p0"]["argmax_agreement"])
    p1 = float(position_metrics["p1"]["argmax_agreement"])
    selection_score = min(p0, p1) + 0.01 * (p0 + p1)
    return {
        "position": position_metrics,
        "slice": slice_metrics,
        "selection_score": selection_score,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkpoint", required=True)
    parser.add_argument("--sb-teacher", required=True)
    parser.add_argument("--bb-teacher", required=True)
    parser.add_argument("--dump-dir", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v4")
    parser.add_argument(
        "--raise-action-mapping",
        choices=(
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        default="legacy_total_over_pot",
    )
    parser.add_argument("--max-rows-per-actor", type=int, default=300_000)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--teacher-temperature", type=float, default=1.0)
    parser.add_argument("--position-adapter-hidden", type=int, default=0)
    parser.add_argument(
        "--train-policy-trunk",
        action="store_true",
        help=(
            "Optimize the shared actor feature extractors, trunk, policy "
            "heads and position adapters while keeping the critic frozen."
        ),
    )
    parser.add_argument("--val-fraction", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=20260843)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    if args.max_rows_per_actor <= 0:
        raise ValueError("--max-rows-per-actor must be positive")
    if args.epochs <= 0 or args.batch_size <= 1:
        raise ValueError("epochs must be positive and batch size must exceed one")
    if not 0.0 < args.val_fraction < 0.5:
        raise ValueError("--val-fraction must be in (0, 0.5)")
    if args.teacher_temperature <= 0.0:
        raise ValueError("--teacher-temperature must be positive")
    if args.position_adapter_hidden < 0:
        raise ValueError("--position-adapter-hidden must be non-negative")
    if args.train_policy_trunk and args.position_adapter_hidden <= 0:
        raise ValueError(
            "--train-policy-trunk requires --position-adapter-hidden > 0"
        )

    started = time.time()
    output = Path(args.out_dir).resolve()
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True)

    files = dump_files(args.dump_dir)
    rows, ingest = collect_rows(
        files=files,
        max_rows_per_actor=args.max_rows_per_actor,
        seed=args.seed,
        obs_version=args.obs_version,
        raise_action_mapping=args.raise_action_mapping,
    )
    if len(rows) < 10_000:
        raise RuntimeError(f"insufficient reconstructed observations: {len(rows)}")
    if set(int(row["position"]) for row in rows) != {0, 1}:
        raise RuntimeError("reconstructed observations do not cover both positions")

    order = np.random.default_rng(args.seed).permutation(len(rows))
    validation_count = max(1, int(len(rows) * args.val_fraction))
    validation_rows = [rows[int(index)] for index in order[:validation_count]]
    training_rows = [rows[int(index)] for index in order[validation_count:]]
    training_loader = DataLoader(
        stack_rows(training_rows),
        batch_size=args.batch_size,
        shuffle=True,
        pin_memory=True,
        drop_last=True,
    )
    validation_loader = DataLoader(
        stack_rows(validation_rows),
        batch_size=args.batch_size,
        shuffle=False,
        pin_memory=True,
    )

    source_path = Path(args.source_checkpoint).resolve()
    sb_path = Path(args.sb_teacher).resolve()
    bb_path = Path(args.bb_teacher).resolve()
    student, source_checkpoint = load_model(source_path, "cpu")
    sb_teacher, sb_checkpoint = load_model(sb_path, "cpu")
    bb_teacher, bb_checkpoint = load_model(bb_path, "cpu")
    for label, checkpoint in (
        ("source", source_checkpoint),
        ("SB teacher", sb_checkpoint),
        ("BB teacher", bb_checkpoint),
    ):
        overrides = (
            checkpoint.get("policy_logit_bias"),
            checkpoint.get("policy_range_override"),
            checkpoint.get("policy_context_override"),
            checkpoint.get("preflop_strategy_profile"),
        )
        if any(value is not None for value in overrides):
            raise RuntimeError(f"{label} contains an evaluator-side override")
        checkpoint_obs = str(checkpoint.get("obs_version", "v55"))
        if checkpoint_obs != args.obs_version:
            raise RuntimeError(
                f"{label} observation mismatch: "
                f"{checkpoint_obs} != {args.obs_version}"
            )
        checkpoint_mapping = str(
            checkpoint.get(
                "raise_action_mapping",
                (
                    "pot_fraction_v2"
                    if checkpoint.get("action_space_version")
                    == "9slot_pot_fraction_v2"
                    else "legacy_total_over_pot"
                ),
            )
        )
        if checkpoint_mapping != args.raise_action_mapping:
            raise RuntimeError(
                f"{label} action mapping mismatch: "
                f"{checkpoint_mapping} != {args.raise_action_mapping}"
            )
    del sb_checkpoint, bb_checkpoint

    student = clone_with_position_adapter(
        student,
        args.position_adapter_hidden,
    )
    student = student.to(args.device)
    sb_teacher = sb_teacher.to(args.device)
    bb_teacher = bb_teacher.to(args.device)
    for teacher in (sb_teacher, bb_teacher):
        teacher.eval()
        for parameter in teacher.parameters():
            parameter.requires_grad_(False)
    for name, parameter in student.named_parameters():
        if args.position_adapter_hidden > 0:
            if args.train_policy_trunk:
                # The value head is not used by either teacher and must remain
                # bitwise inherited. All other learned representation and
                # actor parameters are constrained by both position teachers.
                parameter.requires_grad_(
                    not name.startswith("value_head.")
                )
            else:
                parameter.requires_grad_(
                    name.startswith("position_policy_adapters.")
                )
        else:
            parameter.requires_grad_(
                name.startswith("policy_head.")
                or name.startswith("preflop_policy_head.")
            )
    trainable = [
        parameter for parameter in student.parameters() if parameter.requires_grad
    ]
    if not trainable:
        raise RuntimeError("no policy-head parameters selected for training")
    optimizer = torch.optim.AdamW(
        trainable,
        lr=args.lr,
        weight_decay=args.weight_decay,
    )

    history: list[dict[str, Any]] = []
    baseline = evaluate(
        student,
        sb_teacher,
        bb_teacher,
        validation_loader,
        args.device,
        args.teacher_temperature,
    )
    baseline["epoch"] = 0
    history.append(baseline)
    best_score = -math.inf
    best_path = output / "best.pt"
    for epoch in range(1, args.epochs + 1):
        student.train()
        batch_losses: list[float] = []
        position_loss_sums = Counter()
        for cards, actions, extras, legal, position, _ in training_loader:
            cards = cards.to(args.device, non_blocking=True)
            actions = actions.to(args.device, non_blocking=True)
            extras = extras.to(args.device, non_blocking=True)
            legal = legal.to(args.device, non_blocking=True)
            position = position.to(args.device, non_blocking=True)
            student_logits, _ = student(
                cards,
                actions,
                model_extras(student, extras, position),
                legal,
            )
            with torch.no_grad():
                sb_logits, _ = sb_teacher(
                    cards,
                    actions,
                    model_extras(sb_teacher, extras, position),
                    legal,
                )
                bb_logits, _ = bb_teacher(
                    cards,
                    actions,
                    model_extras(bb_teacher, extras, position),
                    legal,
                )
                target_logits = torch.where(
                    (position == 0).unsqueeze(1),
                    bb_logits,
                    sb_logits,
                )
            loss, position_losses = teacher_loss(
                student_logits,
                target_logits,
                position,
                args.teacher_temperature,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            optimizer.step()
            batch_losses.append(float(loss.detach()))
            for key, value in position_losses.items():
                position_loss_sums[key] += value

        metrics = evaluate(
            student,
            sb_teacher,
            bb_teacher,
            validation_loader,
            args.device,
            args.teacher_temperature,
        )
        metrics.update(
            {
                "epoch": epoch,
                "train_loss": float(np.mean(batch_losses)),
                "train_position_loss": {
                    key: float(value / max(len(batch_losses), 1))
                    for key, value in sorted(position_loss_sums.items())
                },
            }
        )
        history.append(metrics)
        print(json.dumps(metrics, sort_keys=True), flush=True)
        if float(metrics["selection_score"]) > best_score:
            best_score = float(metrics["selection_score"])
            payload = dict(source_checkpoint)
            payload.update(
                {
                    "model": student.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "version": "offline.position_teacher_distillation.v1",
                    "source_checkpoint": str(source_path),
                    "source_checkpoint_sha256": sha256_path(source_path),
                    "sb_teacher": str(sb_path),
                    "sb_teacher_sha256": sha256_path(sb_path),
                    "bb_teacher": str(bb_path),
                    "bb_teacher_sha256": sha256_path(bb_path),
                    "policy_logit_bias": None,
                    "policy_range_override": None,
                    "policy_context_override": None,
                    "preflop_strategy_profile": None,
                    "position_adapter_hidden": args.position_adapter_hidden,
                    "position_teacher_train_policy_trunk": (
                        args.train_policy_trunk
                    ),
                    "offline_decision_samples": len(rows),
                    "position_teacher_distillation": {
                        "epoch": epoch,
                        "selection_score": best_score,
                        "config": vars(args),
                        "ingest": ingest,
                        "history": history,
                    },
                }
            )
            atomic_torch_save(payload, best_path)

    report = {
        "status": "finished",
        "runtime_seconds": time.time() - started,
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256_path(source_path),
        "sb_teacher": str(sb_path),
        "sb_teacher_sha256": sha256_path(sb_path),
        "bb_teacher": str(bb_path),
        "bb_teacher_sha256": sha256_path(bb_path),
        "selected_files": [str(path) for path in files],
        "ingest": ingest,
        "training_rows": len(training_rows),
        "validation_rows": len(validation_rows),
        "baseline": baseline,
        "history": history,
        "best_selection_score": best_score,
        "best_checkpoint": str(best_path),
        "best_checkpoint_sha256": sha256_path(best_path),
        "pure_weight_policy": True,
        "evaluator_side_overrides": False,
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
