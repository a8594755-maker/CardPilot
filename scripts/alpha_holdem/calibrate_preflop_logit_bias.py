#!/usr/bin/env python3
"""Create a frozen checkpoint with calibrated first-decision preflop biases.

The neural weights are unchanged.  A small context-specific additive vector is
stored in the checkpoint and consumed by direct greedy inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from alpha_holdem.environment_v55 import NUM_ACTIONS
from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.play_slumbot import (
    build_action_table,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    parse_action,
    resolve_obs_version,
)
from alpha_holdem.v5_preflop_policy_probe import all_hole_combos


CASES = {
    "sb_open": ("", 1),
    "bb_vs_open": ("b200", 0),
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def class_rates(choices: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            np.mean(choices == 0),
            np.mean(choices == 1),
            np.mean((choices >= 2) & (choices <= 7)),
            np.mean(choices == 8),
        ],
        dtype=np.float64,
    )


def collect_logits(
    model: AlphaHoldemNet,
    obs_version: str,
    device: str,
    action_str: str,
    client_pos: int,
    batch_size: int,
) -> np.ndarray:
    state = parse_action(action_str)
    mask, _ = build_action_table(state)
    commitments = compute_commitments(state)
    stacks = [20_000 - commitments["hero_total"], 20_000 - commitments["opp_total"]]
    action_info = encode_action_history(
        state, client_pos, int(state["pos"]), obs_version=obs_version
    )
    extra = encode_extra(stacks)
    holes = all_hole_combos()
    outputs: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(holes), batch_size):
            batch_holes = holes[start : start + batch_size]
            cards = np.stack(
                [encode_cards(hole, [], int(state["st"])) for hole in batch_holes]
            ).astype(np.float32)
            actions = np.repeat(
                action_info[None, ...], len(batch_holes), axis=0
            ).astype(np.float32)
            extras = np.repeat(extra[None, ...], len(batch_holes), axis=0).astype(
                np.float32
            )
            masks = np.repeat(mask[None, ...], len(batch_holes), axis=0).astype(
                np.float32
            )
            logits, _ = model(
                torch.from_numpy(cards).to(device),
                torch.from_numpy(actions).to(device),
                torch.from_numpy(extras).to(device),
                torch.from_numpy(masks).to(device),
            )
            outputs.append(logits.cpu().numpy())
    return np.concatenate(outputs, axis=0)


def calibrate(
    logits: np.ndarray,
    target: np.ndarray,
    grid_min: float,
    grid_max: float,
    grid_step: float,
) -> tuple[list[float], np.ndarray, float]:
    grid = np.arange(grid_min, grid_max + grid_step * 0.5, grid_step)
    best: tuple[float, float, float, np.ndarray] | None = None
    for call_bias in grid:
        for raise_bias in grid:
            adjusted = logits.copy()
            adjusted[:, 1] += call_bias
            adjusted[:, 2:8] += raise_bias
            adjusted[:, 8] -= 8.0
            rates = class_rates(adjusted.argmax(axis=1))
            error = float(np.square(rates - target).sum())
            tie_break = abs(float(call_bias)) + abs(float(raise_bias))
            score = (error, tie_break, float(call_bias), rates)
            if best is None or score[:2] < best[:2]:
                best = score
                best_raise = float(raise_bias)
    assert best is not None
    _, _, best_call, rates = best
    vector = [0.0, best_call] + [best_raise] * 6 + [-8.0]
    return vector, rates, float(np.square(rates - target).sum())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--sb-target", default="0.25,0.35,0.40,0")
    parser.add_argument("--bb-target", default="0.35,0.35,0.30,0")
    parser.add_argument("--grid-min", type=float, default=-4.0)
    parser.add_argument("--grid-max", type=float, default=16.0)
    parser.add_argument("--grid-step", type=float, default=0.1)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    checkpoint = torch.load(source, map_location=args.device, weights_only=False)
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=str(checkpoint.get("norm_layer", "bn")),
    ).to(args.device)
    model.eval()
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=args.device),
            torch.zeros(2, 25, 4, 5, device=args.device),
            torch.zeros(2, 2, device=args.device),
        )
    model.load_state_dict(checkpoint["model"])
    model.eval()
    obs_version = resolve_obs_version(checkpoint, "auto")
    targets = {
        "sb_open": np.asarray([float(x) for x in args.sb_target.split(",")]),
        "bb_vs_open": np.asarray([float(x) for x in args.bb_target.split(",")]),
    }

    biases: dict[str, list[float]] = {}
    report: dict[str, dict] = {}
    for name, (action_str, client_pos) in CASES.items():
        logits = collect_logits(
            model,
            obs_version,
            args.device,
            action_str,
            client_pos,
            args.batch_size,
        )
        vector, rates, error = calibrate(
            logits, targets[name], args.grid_min, args.grid_max, args.grid_step
        )
        biases[name] = vector
        report[name] = {
            "target": targets[name].tolist(),
            "realized": rates.tolist(),
            "squared_error": error,
            "bias": vector,
        }

    checkpoint["policy_logit_bias"] = {
        "schema": "preflop_logit_bias.v1",
        "sb_open": biases["sb_open"],
        "bb_vs_open": biases["bb_vs_open"],
        "source_checkpoint": str(source),
        "source_checkpoint_sha256": sha256_path(source),
        "calibration": report,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    os.replace(temporary, output)
    result = {
        "source": str(source),
        "source_sha256": sha256_path(source),
        "output": str(output),
        "output_sha256": sha256_path(output),
        "obs_version": obs_version,
        "calibration": report,
    }
    report_path = output.with_suffix(".calibration.json")
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
