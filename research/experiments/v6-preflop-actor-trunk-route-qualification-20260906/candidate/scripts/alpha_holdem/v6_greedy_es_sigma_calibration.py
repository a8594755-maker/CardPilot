"""Outcome-blind greedy-boundary calibration for mirrored ES perturbations."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states
from alpha_holdem.v6_dual_contract_residual_training_smoke import state_inputs
from alpha_holdem.v6_greedy_es_smoke import policy_vector, set_policy_vector


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def choose_sigma(rows: list[dict], target: float = 0.03) -> float | None:
    eligible = [
        row
        for row in rows
        if 0.01 <= row["median_disagreement"] <= 0.08
        and row["minimum_disagreement"] > 0
        and row["maximum_abs_residual_logit"] <= 0.250001
    ]
    if not eligible:
        return None
    return float(
        min(eligible, key=lambda row: (abs(row["median_disagreement"] - target), row["sigma"]))[
            "sigma"
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--state-seed", type=int, required=True)
    parser.add_argument("--states", type=int, default=4096)
    parser.add_argument("--directions", type=int, default=8)
    parser.add_argument("--sigma", action="append", type=float, required=True)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    sigmas = sorted(set(args.sigma))
    if args.states < 512 or args.directions < 4 or any(value <= 0 for value in sigmas):
        parser.error("invalid state, direction, or sigma grid")
    started = time.time()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    base_path = args.base_checkpoint.resolve()
    base_sha = sha256_path(base_path)
    base_policy = load_policy(base_path, args.device)
    torch.manual_seed(args.seed)
    model = DualContractResidualPolicy(
        base_policy.model, hidden=128, policy_delta_cap=0.25
    ).to(args.device).eval()
    center = policy_vector(model)
    states = collect_balanced_states(args.states, args.state_seed)
    inputs = []
    streets = []
    seats = []
    for state in states:
        tensors, _, _ = state_inputs(base_policy, state, args.device)
        inputs.append(tuple(tensor.squeeze(0).cpu().numpy() for tensor in tensors))
        streets.append(int(state.street))
        seats.append(int(state.actor))
    stacked = [
        torch.as_tensor(np.stack([row[index] for row in inputs]), dtype=torch.float32, device=args.device)
        for index in range(8)
    ]

    def query(vector: np.ndarray) -> tuple[np.ndarray, float]:
        set_policy_vector(model, vector)
        slots = []
        maximum = 0.0
        with torch.inference_mode():
            for start in range(0, args.states, args.batch_size):
                batch = [tensor[start : start + args.batch_size] for tensor in stacked]
                logits, _ = model(*batch)
                base_logits = model.base(batch[0], batch[1], batch[2], batch[6])[0]
                masked = logits + (1.0 - batch[6]) * -1e9
                slots.extend(masked.argmax(dim=1).cpu().numpy().tolist())
                maximum = max(maximum, float((logits - base_logits).abs().max()))
        return np.asarray(slots, dtype=np.int64), maximum

    base_slots, base_maximum = query(center)
    if base_maximum != 0.0:
        raise RuntimeError("zero residual is not base exact")
    rng = np.random.default_rng(args.seed + 71)
    directions = rng.standard_normal((args.directions, center.size))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    rows = []
    detail = []
    streets_array = np.asarray(streets)
    seats_array = np.asarray(seats)
    for sigma in sigmas:
        rates = []
        maximum = 0.0
        for direction_index, direction in enumerate(directions):
            for sign in (1, -1):
                slots, observed = query(center + sign * sigma * direction)
                changed = slots != base_slots
                rate = float(np.mean(changed))
                rates.append(rate)
                maximum = max(maximum, observed)
                partitions = []
                for street in range(4):
                    for seat in (0, 1):
                        selected = (streets_array == street) & (seats_array == seat)
                        partitions.append(
                            {
                                "street": street,
                                "seat": seat,
                                "states": int(np.sum(selected)),
                                "disagreement": float(np.mean(changed[selected])),
                            }
                        )
                detail.append(
                    {
                        "sigma": sigma,
                        "direction": direction_index,
                        "sign": sign,
                        "disagreement": rate,
                        "changed_states": int(np.sum(changed)),
                        "maximum_abs_residual_logit": observed,
                        "partitions": partitions,
                    }
                )
        rows.append(
            {
                "sigma": sigma,
                "queries": len(rates),
                "minimum_disagreement": float(np.min(rates)),
                "median_disagreement": float(np.median(rates)),
                "maximum_disagreement": float(np.max(rates)),
                "maximum_abs_residual_logit": maximum,
            }
        )
        print(
            f"sigma={sigma:g} disagreement=[{rows[-1]['minimum_disagreement']:.4f},"
            f"{rows[-1]['median_disagreement']:.4f},{rows[-1]['maximum_disagreement']:.4f}] "
            f"max_delta={maximum:.4f}",
            flush=True,
        )
    selected_sigma = choose_sigma(rows)
    output = {
        "schema": "cardpilot.greedy_es_sigma_calibration.v1",
        "status": "COMPLETED",
        "claim_scope": "OUTCOME_BLIND_GREEDY_BOUNDARY_ACTIVATION_NOT_STRENGTH",
        "base_sha256": base_sha,
        "seed": args.seed,
        "state_seed": args.state_seed,
        "states": args.states,
        "directions": args.directions,
        "policy_parameter_count": int(center.size),
        "grid": rows,
        "detail": detail,
        "selected_sigma": selected_sigma,
        "target_disagreement": 0.03,
        "admitted": selected_sigma is not None,
        "decision": (
            "ADMIT_CALIBRATED_GREEDY_ES_MINIMAL_RETRY"
            if selected_sigma is not None
            else "EXPAND_GREEDY_ES_SIGMA_GRID"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: output[key] for key in ("selected_sigma", "decision")}, sort_keys=True))


if __name__ == "__main__":
    main()
