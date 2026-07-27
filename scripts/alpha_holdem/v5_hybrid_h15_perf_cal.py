#!/usr/bin/env python3
"""Resource-matched, reporting-only performance calibration for H15.

This tool never updates a campaign checkpoint.  It reconstructs the exact frozen
source model and optimizer in memory, generates one deterministic synthetic batch,
and times otherwise identical value-head-only catch-up steps under MSE and
SmoothL1(beta=1).  A treatment-arm invocation additionally binds and compares the
common MSE baseline produced immediately before the control arm.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1  # noqa: E402


SCHEMA = "v5.hybrid.h15.perf_cal.v1"
LOSS_RATIO_MIN = 0.95
COMMON_BASELINE_RATIO_MIN = 0.95


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


def tensor_sha256(tensors: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(tensors):
        tensor = tensors[name].detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(json.dumps(list(tensor.shape)).encode("ascii"))
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def deterministic_batch(seed: int, batch_size: int) -> dict[str, torch.Tensor]:
    generator = torch.Generator(device="cpu")
    generator.manual_seed(seed)
    return {
        "cards": torch.randn(batch_size, 6, 4, 13, generator=generator),
        "actions": torch.randn(batch_size, 25, 4, 5, generator=generator),
        "extras": torch.randn(batch_size, 2, generator=generator),
        "masks": torch.ones(batch_size, 9),
        "targets": torch.empty(batch_size).uniform_(-200.0, 200.0, generator=generator),
    }


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
                        "v5_hybrid_h15_mirror.py",
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
                        "command_line": command,
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
        child_command = " ".join(child.cmdline())
        if "solve-worker.ts" in child_command.replace("\\", "/"):
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


def build_model_and_optimizer(checkpoint: dict[str, Any], device: str) -> tuple[AlphaHoldemNet, torch.optim.Adam]:
    if checkpoint.get("critic_contract") != CRITIC_V1:
        raise ValueError("H15 PERF-CAL requires critic_v1 source")
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


def one_step(
    model: AlphaHoldemNet,
    optimizer: torch.optim.Adam,
    batch: dict[str, torch.Tensor],
    loss_mode: str,
) -> None:
    if model.training:
        raise RuntimeError("PERF-CAL catch-up step requires model.eval() to preserve actor buffers")
    _, values = model(batch["cards"], batch["actions"], batch["extras"], batch["masks"])
    if loss_mode == "mse":
        loss = F.mse_loss(values.squeeze(-1), batch["targets"])
    elif loss_mode == "smooth_l1":
        loss = F.smooth_l1_loss(values.squeeze(-1), batch["targets"], beta=1.0)
    else:
        raise ValueError(loss_mode)
    optimizer.zero_grad(set_to_none=True)
    (0.5 * loss).backward()
    value_parameters = list(model.value_head.parameters())
    if any(parameter.grad is not None for name, parameter in model.named_parameters() if not name.startswith("value_head.")):
        raise RuntimeError("PERF-CAL leaked a gradient outside value_head")
    torch.nn.utils.clip_grad_norm_(value_parameters, 0.5)
    optimizer.step()


def timed_trial(
    checkpoint: dict[str, Any],
    cpu_batch: dict[str, torch.Tensor],
    device: str,
    loss_mode: str,
    warmup: int,
    steps: int,
) -> float:
    model, optimizer = build_model_and_optimizer(checkpoint, device)
    model.eval()
    for name, parameter in model.named_parameters():
        parameter.requires_grad_(name.startswith("value_head."))
    batch = {name: tensor.to(device) for name, tensor in cpu_batch.items()}
    for _ in range(warmup):
        one_step(model, optimizer, batch, loss_mode)
    if device == "cuda":
        torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(steps):
        one_step(model, optimizer, batch, loss_mode)
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    del optimizer, model, batch
    if device == "cuda":
        torch.cuda.empty_cache()
    return elapsed / steps


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("empty benchmark samples")
    return float(statistics.median(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment", "offline-smoke"), required=True)
    parser.add_argument("--control-baseline", type=Path)
    parser.add_argument("--seed", type=int, default=2026071901)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--repeats", type=int, default=3)
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
        forbidden = active_forbidden_processes()
        if forbidden:
            raise ValueError(f"forbidden active process(es): {forbidden}")
        path1 = path1_identity(args.path1_pid, args.path1_workers)
        checkpoint = torch.load(source, map_location="cpu", weights_only=False)
        if int(checkpoint.get("iteration", -1)) != 35051 or int(checkpoint.get("total_hands", -1)) != 576021901:
            raise ValueError("source iteration/hands mismatch")
        cpu_batch = deterministic_batch(args.seed, args.batch_size)
        batch_hash = tensor_sha256(cpu_batch)
        samples: dict[str, list[float]] = {"mse": [], "smooth_l1": []}
        order = ("mse", "smooth_l1")
        for repeat in range(args.repeats):
            for mode in (order if repeat % 2 == 0 else tuple(reversed(order))):
                samples[mode].append(
                    timed_trial(checkpoint, cpu_batch, args.device, mode, args.warmup, args.steps)
                )
        medians = {mode: median(values) for mode, values in samples.items()}
        loss_ratio = medians["mse"] / medians["smooth_l1"]
        common_ratio = 1.0
        control_baseline = None
        if args.arm == "treatment":
            if args.control_baseline is None or not args.control_baseline.is_file():
                raise ValueError("treatment calibration requires control baseline")
            control_baseline = json.loads(args.control_baseline.read_text(encoding="utf-8-sig"))
            if control_baseline.get("overall") != "PASS" or control_baseline.get("arm") != "control":
                raise ValueError("control baseline authority invalid")
            if control_baseline.get("source", {}).get("sha256") != sha256(source):
                raise ValueError("control baseline source mismatch")
            if control_baseline.get("batch", {}).get("sha256") != batch_hash:
                raise ValueError("control baseline batch mismatch")
            control_mse = float(control_baseline["timing"]["mse_seconds_per_step_median"])
            common_ratio = min(control_mse, medians["mse"]) / max(control_mse, medians["mse"])
        passed = loss_ratio >= LOSS_RATIO_MIN and common_ratio >= COMMON_BASELINE_RATIO_MIN
        payload = {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS" if passed else "FAIL_CLOSED",
            "classification": "H15_PERF_CAL_PASS" if passed else "H15_PERF_CAL_FAIL",
            "arm": args.arm,
            "source": {
                "path": str(source),
                "sha256": sha256(source),
                "iteration": int(checkpoint["iteration"]),
                "hands": int(checkpoint["total_hands"]),
            },
            "batch": {"seed": args.seed, "size": args.batch_size, "sha256": batch_hash},
            "benchmark": {
                "device": args.device,
                "device_name": torch.cuda.get_device_name(0) if args.device == "cuda" else "cpu",
                "torch": torch.__version__,
                "warmup_steps": args.warmup,
                "timed_steps": args.steps,
                "repeats": args.repeats,
                "order": "alternating_mse_smoothl1",
                "value_head_only": True,
                "optimizer_state_loaded": True,
            },
            "timing": {
                "mse_seconds_per_step_samples": samples["mse"],
                "smooth_l1_seconds_per_step_samples": samples["smooth_l1"],
                "mse_seconds_per_step_median": medians["mse"],
                "smooth_l1_seconds_per_step_median": medians["smooth_l1"],
                "smooth_l1_over_mse_throughput_ratio": loss_ratio,
                "common_mse_baseline_match_ratio": common_ratio,
            },
            "gates": {
                "loss_throughput_ratio_min": LOSS_RATIO_MIN,
                "loss_throughput_ratio_pass": loss_ratio >= LOSS_RATIO_MIN,
                "common_mse_baseline_ratio_min": COMMON_BASELINE_RATIO_MIN,
                "common_mse_baseline_ratio_pass": common_ratio >= COMMON_BASELINE_RATIO_MIN,
            },
            "control_baseline": None if args.control_baseline is None else {
                "path": str(args.control_baseline.resolve()),
                "sha256": sha256(args.control_baseline.resolve()),
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
            "classification": "H15_PERF_CAL_EXECUTION_FAILURE",
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
