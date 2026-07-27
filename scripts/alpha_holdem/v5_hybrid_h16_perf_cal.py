#!/usr/bin/env python3
"""Registered representative full-PPO pre-arm calibration for H16.

The calibration is reporting-only.  Every timed observation reconstructs the
exact frozen source model and optimizer, executes the complete Trinal-Clip PPO
update with a forced KL stop after epoch one, and therefore includes exactly
three sequential value-head catch-up epochs.  It never writes a checkpoint.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1  # noqa: E402
from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update  # noqa: E402


SCHEMA = "v5.hybrid.h16.representative_perf_cal.v1"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
THROUGHPUT_RATIO_MIN = 0.85
MSE_STABILITY_RATIO_MIN = 0.95
FORCED_OLD_LOG_PROB_OFFSET = 0.10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive and path.exists():
        raise FileExistsError(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if exclusive and path.exists():
        temporary.unlink(missing_ok=True)
        raise FileExistsError(path)
    temporary.replace(path)


def active_forbidden_processes() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    own_pid = os.getpid()
    for process in psutil.process_iter(["pid", "cmdline", "create_time", "exe"]):
        try:
            if process.pid == own_pid:
                continue
            command = " ".join(process.info.get("cmdline") or [])
            normalized = command.replace("\\", "/").lower()
            token = next(
                (
                    item
                    for item in (
                        "scripts/alpha_holdem/train_v5.py",
                        "v5_hybrid_h16_mirror.py",
                        "v5_slumbot",
                        "play_slumbot",
                        "slumbot_match",
                    )
                    if item in normalized
                ),
                None,
            )
            if token:
                found.append(
                    {
                        "pid": process.pid,
                        "token": token,
                        "command_line_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                        "creation_time": process.info.get("create_time"),
                        "executable": process.info.get("exe"),
                    }
                )
        except (psutil.Error, OSError):
            continue
    return found


def path1_identity(expected_pid: int, expected_workers: int) -> dict[str, Any]:
    coordinator = psutil.Process(expected_pid)
    command = " ".join(coordinator.cmdline())
    normalized = command.replace("\\", "/")
    if "solve-v3-parallel.ts" not in normalized or "--workers 6" not in command:
        raise ValueError("Path-1 coordinator command identity mismatch")
    if coordinator.nice() != psutil.BELOW_NORMAL_PRIORITY_CLASS:
        raise ValueError("Path-1 coordinator is not BelowNormal")
    workers = []
    for child in coordinator.children(recursive=False):
        child_command = " ".join(child.cmdline()).replace("\\", "/")
        if "solve-worker.ts" in child_command:
            workers.append(child.pid)
    if len(workers) != expected_workers:
        raise ValueError(f"Path-1 worker count {len(workers)} != {expected_workers}")
    return {
        "coordinator_pid": expected_pid,
        "coordinator_command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
        "priority": "BelowNormal",
        "worker_pids": sorted(workers),
        "worker_count": len(workers),
        "gpu_use": False,
        "changed": False,
    }


def build_model_and_optimizer(
    checkpoint: dict[str, Any], device: str
) -> tuple[AlphaHoldemNet, torch.optim.Adam]:
    if checkpoint.get("critic_contract") != CRITIC_V1:
        raise ValueError("H16 PERF-CAL requires critic_v1 source")
    config = checkpoint.get("config") or {}
    model = AlphaHoldemNet(
        num_actions=9,
        critic_contract=CRITIC_V1,
        critic_init_seed=int(config.get("h1_critic_init_seed", 2026071102)),
    ).to(device)
    with torch.no_grad():
        model(
            torch.zeros(1, 6, 4, 13, device=device),
            torch.zeros(1, 25, 4, 5, device=device),
            torch.zeros(1, 2, device=device),
            torch.ones(1, 9, device=device),
        )
    model.load_state_dict(checkpoint["model"])
    optimizer = torch.optim.Adam(model.parameters(), lr=float(config.get("lr", 3e-4)))
    optimizer.load_state_dict(copy.deepcopy(checkpoint["optimizer"]))
    return model, optimizer


def transition_sha256(transitions: list[tuple]) -> str:
    digest = hashlib.sha256()
    for transition in transitions:
        for value in transition:
            array = np.asarray(value)
            digest.update(str(array.dtype).encode("ascii"))
            digest.update(json.dumps(list(array.shape)).encode("ascii"))
            digest.update(array.tobytes())
    return digest.hexdigest()


def deterministic_transitions(
    checkpoint: dict[str, Any], device: str, seed: int, rows: int
) -> list[tuple]:
    rng = np.random.default_rng(seed)
    cards = rng.normal(0.0, 0.35, size=(rows, 6, 4, 13)).astype(np.float32)
    actions = rng.normal(0.0, 0.35, size=(rows, 25, 4, 5)).astype(np.float32)
    extras = rng.normal(0.0, 0.5, size=(rows, 2)).astype(np.float32)
    masks = np.ones((rows, 9), dtype=np.float32)
    selected = (np.arange(rows, dtype=np.int64) + seed) % 9
    rewards = np.zeros(rows, dtype=np.float32)
    dones = np.zeros(rows, dtype=np.float32)
    block = 32
    terminal_indices = np.arange(block - 1, rows, block)
    dones[terminal_indices] = 1.0
    rewards[terminal_indices] = rng.uniform(-200.0, 200.0, size=len(terminal_indices)).astype(np.float32)
    hero_chips = np.full(rows, 200.0, dtype=np.float32)
    villain_chips = np.full(rows, 200.0, dtype=np.float32)

    model, _ = build_model_and_optimizer(checkpoint, device)
    model.eval()
    log_probs: list[np.ndarray] = []
    values: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, rows, 1024):
            end = min(start + 1024, rows)
            logits, value = model(
                torch.from_numpy(cards[start:end]).to(device),
                torch.from_numpy(actions[start:end]).to(device),
                torch.from_numpy(extras[start:end]).to(device),
                torch.from_numpy(masks[start:end]).to(device),
            )
            chosen = torch.from_numpy(selected[start:end]).to(device)
            lp = torch.log_softmax(logits, dim=-1).gather(1, chosen[:, None]).squeeze(1)
            # A fixed positive offset makes old_lp-new_lp positive and forces
            # the registered KL stop after the first PPO epoch.
            log_probs.append((lp + FORCED_OLD_LOG_PROB_OFFSET).cpu().numpy())
            values.append(value.squeeze(-1).cpu().numpy())
    old_lp = np.concatenate(log_probs).astype(np.float32)
    old_values = np.concatenate(values).astype(np.float32)
    del model
    if device == "cuda":
        torch.cuda.empty_cache()
    return [
        (
            cards[i], actions[i], extras[i], masks[i], int(selected[i]), float(old_lp[i]),
            float(rewards[i]), float(old_values[i]), float(dones[i]), float(hero_chips[i]),
            float(villain_chips[i]), 1.0 if dones[i] else 0.0,
        )
        for i in range(rows)
    ]


def update_kwargs(loss_mode: str, mini_batch_size: int, epochs: int, target_kl: float) -> dict[str, Any]:
    return {
        "epochs": epochs,
        "mini_batch_size": mini_batch_size,
        "delta1": 3.0,
        "gamma": 0.999,
        "critic_contract": CRITIC_V1,
        "effective_stack_divisor": 1.0,
        "value_coef": 0.5,
        "entropy_coef": 0.05,
        "entropy_floor": 0.3,
        "action_prior_coef": 0.02,
        "action_prior_target": (0.15, 0.30, 0.52, 0.03),
        "action_prior_postflop_only": True,
        "preflop_action_prior_coef": 0.01,
        "preflop_action_prior_target": (0.24, 0.36, 0.38, 0.02),
        "target_kl": target_kl,
        "value_head_catchup": True,
        "value_head_catchup_loss": loss_mode,
        "value_head_catchup_smooth_l1_beta": 1.0,
    }


def one_full_update(
    checkpoint: dict[str, Any], transitions: list[tuple], device: str,
    loss_mode: str, seed: int, mini_batch_size: int, epochs: int, target_kl: float,
) -> tuple[float, dict[str, Any], dict[str, torch.Tensor], dict[str, dict[str, Any]]]:
    model, optimizer = build_model_and_optimizer(checkpoint, device)
    torch.manual_seed(seed)
    if device == "cuda":
        torch.cuda.manual_seed_all(seed)
        torch.cuda.synchronize()
    started = time.perf_counter()
    stats = trinal_clip_ppo_update(
        model, optimizer, transitions, device,
        **update_kwargs(loss_mode, mini_batch_size, epochs, target_kl),
    )
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    optimizer_state: dict[str, dict[str, Any]] = {}
    for name, parameter in model.named_parameters():
        optimizer_state[name] = {
            key: value.detach().cpu().clone() if torch.is_tensor(value) else copy.deepcopy(value)
            for key, value in optimizer.state.get(parameter, {}).items()
        }
    del optimizer, model
    if device == "cuda":
        torch.cuda.empty_cache()
    return elapsed, stats, state, optimizer_state


def states_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.keys() != right.keys():
        return False
    for key in left:
        lv, rv = left[key], right[key]
        if torch.is_tensor(lv):
            if not torch.equal(lv, rv):
                return False
        elif lv != rv:
            return False
    return True


def identity_pair(
    checkpoint: dict[str, Any], transitions: list[tuple], device: str, seed: int,
    mini_batch_size: int, epochs: int, target_kl: float,
) -> dict[str, Any]:
    _, mse_stats, mse_state, mse_opt = one_full_update(
        checkpoint, transitions, device, "mse", seed, mini_batch_size, epochs, target_kl
    )
    _, smooth_stats, smooth_state, smooth_opt = one_full_update(
        checkpoint, transitions, device, "smooth_l1", seed, mini_batch_size, epochs, target_kl
    )
    actor_model_equal = all(
        torch.equal(value, smooth_state[name])
        for name, value in mse_state.items()
        if not name.startswith("value_head.")
    )
    actor_optimizer_equal = all(
        states_equal(mse_opt[name], smooth_opt[name])
        for name in mse_opt
        if not name.startswith("value_head.")
    )
    value_head_differs = any(
        not torch.equal(value, smooth_state[name])
        for name, value in mse_state.items()
        if name.startswith("value_head.")
    )
    required_stats = (mse_stats, smooth_stats)
    finite = all(
        math.isfinite(float(stats[key]))
        for stats in required_stats
        for key in ("policy_loss", "value_loss", "entropy", "approx_kl", "value_head_catchup_loss")
    )
    forced_shape = all(
        bool(stats["kl_early_stop_triggered"])
        and int(stats["ppo_epochs_completed"]) == 1
        and int(stats["value_head_catchup_epochs"]) == epochs - 1
        and bool(stats["value_head_catchup_actor_state_unchanged"])
        for stats in required_stats
    )
    passed = actor_model_equal and actor_optimizer_equal and value_head_differs and finite and forced_shape
    return {
        "pass": passed,
        "actor_model_bitwise_equal": actor_model_equal,
        "actor_optimizer_bitwise_equal": actor_optimizer_equal,
        "value_head_differs": value_head_differs,
        "all_reported_numerics_finite": finite,
        "forced_kl_and_three_catchup_epochs": forced_shape,
        "mse_stats": {key: mse_stats[key] for key in (
            "ppo_epochs_completed", "kl_early_stop_triggered", "value_head_catchup_epochs",
            "value_head_catchup_minibatches", "value_head_catchup_actor_state_unchanged",
        )},
        "smooth_l1_stats": {key: smooth_stats[key] for key in (
            "ppo_epochs_completed", "kl_early_stop_triggered", "value_head_catchup_epochs",
            "value_head_catchup_minibatches", "value_head_catchup_actor_state_unchanged",
        )},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment", "offline-smoke"), required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--rows", type=int, default=4096)
    parser.add_argument("--mini-batch-size", type=int, default=1024)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--target-kl", type=float, default=1e-12)
    parser.add_argument("--warmup-updates", type=int, default=2)
    parser.add_argument("--timed-updates", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--path1-pid", type=int, default=23720)
    parser.add_argument("--path1-workers", type=int, default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve()
    out = args.out.resolve()
    try:
        if out.exists():
            raise FileExistsError(out)
        if not source.is_file() or sha256(source) != args.source_sha256.lower():
            raise ValueError("source checkpoint identity mismatch")
        if args.device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA unavailable")
        if (args.rows, args.mini_batch_size, args.ppo_epochs, args.target_kl,
                args.warmup_updates, args.timed_updates, args.repeats) != (
                4096, 1024, 4, 1e-12, 2, 8, 5):
            raise ValueError("registered representative calibration dimensions mismatch")
        forbidden = active_forbidden_processes()
        if forbidden:
            raise ValueError(f"forbidden active process(es): {forbidden}")
        path1 = path1_identity(args.path1_pid, args.path1_workers)
        checkpoint = torch.load(source, map_location="cpu", weights_only=False)
        if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(
            checkpoint.get("total_hands", -1)
        ) != SOURCE_HANDS:
            raise ValueError("source iteration/hands mismatch")
        transitions = deterministic_transitions(checkpoint, args.device, args.seed, args.rows)
        transition_hash = transition_sha256(transitions)

        identity = identity_pair(
            checkpoint, transitions, args.device, args.seed + 900000,
            args.mini_batch_size, args.ppo_epochs, args.target_kl,
        )
        samples: dict[str, list[list[float]]] = {"mse": [], "smooth_l1": []}
        order = ("mse", "smooth_l1")
        for warmup_index in range(args.warmup_updates):
            for mode in (order if warmup_index % 2 == 0 else tuple(reversed(order))):
                one_full_update(
                    checkpoint, transitions, args.device, mode,
                    args.seed + 100000 + warmup_index, args.mini_batch_size,
                    args.ppo_epochs, args.target_kl,
                )
        for repeat in range(args.repeats):
            modes = order if repeat % 2 == 0 else tuple(reversed(order))
            for mode in modes:
                repeat_samples = []
                for update_index in range(args.timed_updates):
                    elapsed, stats, _, _ = one_full_update(
                        checkpoint, transitions, args.device, mode,
                        args.seed + repeat * 100 + update_index,
                        args.mini_batch_size, args.ppo_epochs, args.target_kl,
                    )
                    if not (
                        stats["kl_early_stop_triggered"]
                        and int(stats["ppo_epochs_completed"]) == 1
                        and int(stats["value_head_catchup_epochs"]) == 3
                        and stats["value_head_catchup_actor_state_unchanged"]
                    ):
                        raise RuntimeError("timed update violated registered forced-KL/catch-up shape")
                    repeat_samples.append(elapsed)
                samples[mode].append(repeat_samples)

        repeat_medians = {
            mode: [float(statistics.median(values)) for values in repeats]
            for mode, repeats in samples.items()
        }
        mode_medians = {
            mode: float(statistics.median(values)) for mode, values in repeat_medians.items()
        }
        throughput_ratio = mode_medians["mse"] / mode_medians["smooth_l1"]
        mse_stability = min(repeat_medians["mse"]) / max(repeat_medians["mse"])
        passed = (
            throughput_ratio >= THROUGHPUT_RATIO_MIN
            and mse_stability >= MSE_STABILITY_RATIO_MIN
            and identity["pass"]
        )
        payload = {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS" if passed else "FAIL_CLOSED",
            "classification": (
                "H16_REPRESENTATIVE_PERF_CAL_PASS"
                if passed else "H16_REPRESENTATIVE_PERF_CAL_FAIL"
            ),
            "arm": args.arm,
            "source": {
                "path": str(source), "sha256": sha256(source),
                "iteration": int(checkpoint["iteration"]), "hands": int(checkpoint["total_hands"]),
                "optimizer_loaded": True,
            },
            "workload": {
                "seed": args.seed, "transition_sha256": transition_hash,
                "rows": args.rows, "mini_batch_size": args.mini_batch_size,
                "ppo_epochs": args.ppo_epochs, "target_kl": args.target_kl,
                "forced_old_log_prob_offset": FORCED_OLD_LOG_PROB_OFFSET,
                "warmup_updates_per_mode": args.warmup_updates,
                "timed_updates_per_repeat_per_mode": args.timed_updates,
                "repeats": args.repeats, "order": "ALTERNATING_MSE_SMOOTHL1",
                "device": args.device,
                "device_name": torch.cuda.get_device_name(0) if args.device == "cuda" else "cpu",
                "full_trinal_clip_ppo_update": True,
                "forced_kl_early_stop": True,
                "value_head_catchup_epochs": 3,
            },
            "timing": {
                "raw_seconds": samples,
                "repeat_median_seconds": repeat_medians,
                "mode_median_seconds": mode_medians,
                "full_update_throughput_ratio": throughput_ratio,
                "mse_repeat_stability_ratio": mse_stability,
            },
            "identity": identity,
            "gates": {
                "full_update_throughput_ratio_min": THROUGHPUT_RATIO_MIN,
                "full_update_throughput_ratio_pass": throughput_ratio >= THROUGHPUT_RATIO_MIN,
                "mse_repeat_stability_ratio_min": MSE_STABILITY_RATIO_MIN,
                "mse_repeat_stability_ratio_pass": mse_stability >= MSE_STABILITY_RATIO_MIN,
                "numerical_gradient_actor_scope_identity_pass": identity["pass"],
            },
            "path1": path1,
            "forbidden_processes": forbidden,
            "behavior_change": False,
            "checkpoint_changed": False,
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
            "tool_sha256": sha256(Path(__file__).resolve()),
        }
        atomic_json(out, payload, exclusive=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if passed else 2
    except Exception as exc:
        failure = {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "classification": "H16_REPRESENTATIVE_PERF_CAL_EXECUTION_FAILURE",
            "arm": args.arm,
            "error": f"{type(exc).__name__}: {exc}",
            "behavior_change": False,
            "official_hands": 0,
            "strength_claim": "FORBIDDEN",
        }
        if not out.exists():
            atomic_json(out, failure, exclusive=True)
        print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
