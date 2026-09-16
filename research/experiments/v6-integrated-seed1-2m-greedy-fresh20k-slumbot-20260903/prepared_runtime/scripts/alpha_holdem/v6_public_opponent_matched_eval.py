"""Untouched common-deck multi-anchor evaluation for matched learned policies."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import summarize_models


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_ci95(values) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean()) if len(array) else 0.0
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    return mean, 1.96 * std / math.sqrt(max(len(array), 1))


def parse_anchor(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("anchor must be NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("anchor must be NAME=PATH")
    return name, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--anchor", action="append", type=parse_anchor, required=True)
    parser.add_argument("--pairs-per-anchor", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.pairs_per_anchor < 2:
        parser.error("--pairs-per-anchor must be at least two")
    names = [name for name, _ in args.anchor]
    if len(names) != len(set(names)):
        parser.error("anchor names must be unique")
    if "standard10" not in names:
        parser.error("one anchor must be named standard10")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    input_paths = {
        "control": args.control.resolve(),
        "treatment": args.treatment.resolve(),
        **{f"anchor:{name}": path.resolve() for name, path in args.anchor},
    }
    input_hashes = {name: sha256_path(path) for name, path in input_paths.items()}
    control = init_model(read_checkpoint(input_paths["control"]), args.device).eval()
    treatment = init_model(read_checkpoint(input_paths["treatment"]), args.device).eval()

    raw_path = args.out_dir / "common_deck_pairs.jsonl.gz"
    anchor_summaries = []
    pooled_deltas = []
    pooled_seat_deltas = [[], []]
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as raw:
        for anchor_index, (name, _) in enumerate(args.anchor):
            anchor = init_model(
                read_checkpoint(input_paths[f"anchor:{name}"]), args.device
            ).eval()
            anchor_seed = int(args.seed) + 1_000_003 * anchor_index
            control_result = summarize_models(
                candidate=control,
                anchor=anchor,
                pairs=args.pairs_per_anchor,
                seed=anchor_seed,
                starting_stack=200.0,
                candidate_observation_style="legacy_v4",
                anchor_observation_style="legacy_v4",
                device=args.device,
                include_pair_outcomes=True,
            )
            treatment_result = summarize_models(
                candidate=treatment,
                anchor=anchor,
                pairs=args.pairs_per_anchor,
                seed=anchor_seed,
                starting_stack=200.0,
                candidate_observation_style="legacy_v4",
                anchor_observation_style="legacy_v4",
                device=args.device,
                include_pair_outcomes=True,
            )
            control_pairs = control_result.pop("paired_outcomes")
            treatment_pairs = treatment_result.pop("paired_outcomes")
            deltas = []
            seat_deltas = [[], []]
            for control_row, treatment_row in zip(control_pairs, treatment_pairs):
                if (
                    control_row["pair_index"] != treatment_row["pair_index"]
                    or control_row["deck"] != treatment_row["deck"]
                ):
                    raise RuntimeError("control/treatment common-deck identity mismatch")
                seat_delta = [
                    float(treatment_row["candidate_rewards_bb"][seat])
                    - float(control_row["candidate_rewards_bb"][seat])
                    for seat in (0, 1)
                ]
                delta = float(treatment_row["candidate_pair_mean_bb"]) - float(
                    control_row["candidate_pair_mean_bb"]
                )
                deltas.append(delta)
                pooled_deltas.append(delta)
                for seat in (0, 1):
                    seat_deltas[seat].append(seat_delta[seat])
                    pooled_seat_deltas[seat].append(seat_delta[seat])
                raw.write(json.dumps({
                    "anchor": name,
                    "anchor_seed": anchor_seed,
                    "pair_index": control_row["pair_index"],
                    "deck": control_row["deck"],
                    "control_rewards_bb": control_row["candidate_rewards_bb"],
                    "treatment_rewards_bb": treatment_row["candidate_rewards_bb"],
                    "treatment_minus_control_rewards_bb": seat_delta,
                    "control_pair_mean_bb": control_row["candidate_pair_mean_bb"],
                    "treatment_pair_mean_bb": treatment_row["candidate_pair_mean_bb"],
                    "treatment_minus_control_pair_mean_bb": delta,
                }, sort_keys=True) + "\n")
            delta_mean, delta_ci = mean_ci95(deltas)
            seat_stats = []
            for seat in (0, 1):
                seat_mean, seat_ci = mean_ci95(seat_deltas[seat])
                seat_stats.append({
                    "seat": seat,
                    "delta_bb100": seat_mean * 100.0,
                    "delta_ci95_bb100": seat_ci * 100.0,
                })
            anchor_summaries.append({
                "anchor": name,
                "anchor_path": str(input_paths[f"anchor:{name}"]),
                "anchor_sha256": input_hashes[f"anchor:{name}"],
                "seed": anchor_seed,
                "pairs": args.pairs_per_anchor,
                "evaluation_hands_per_candidate": args.pairs_per_anchor * 2,
                "control": control_result,
                "treatment": treatment_result,
                "treatment_minus_control_bb100": delta_mean * 100.0,
                "treatment_minus_control_ci95_bb100": delta_ci * 100.0,
                "seat_deltas": seat_stats,
            })
            del anchor

    pooled_mean, pooled_ci = mean_ci95(pooled_deltas)
    pooled_seat_stats = []
    for seat in (0, 1):
        seat_mean, seat_ci = mean_ci95(pooled_seat_deltas[seat])
        pooled_seat_stats.append({
            "seat": seat,
            "delta_bb100": seat_mean * 100.0,
            "delta_ci95_bb100": seat_ci * 100.0,
        })
    positive_anchors = sum(
        row["treatment_minus_control_bb100"] > 0 for row in anchor_summaries
    )
    standard10_delta = next(
        row["treatment_minus_control_bb100"]
        for row in anchor_summaries if row["anchor"] == "standard10"
    )
    gates = {
        "positive_delta_on_at_least_three_of_four_anchors": (
            len(anchor_summaries) == 4 and positive_anchors >= 3
        ),
        "pooled_delta_positive": pooled_mean > 0,
        "standard10_delta_nonnegative": standard10_delta >= 0,
        "both_pooled_seat_deltas_nonnegative": all(
            row["delta_bb100"] >= 0 for row in pooled_seat_stats
        ),
    }
    for name, path in input_paths.items():
        if sha256_path(path) != input_hashes[name]:
            raise RuntimeError(f"input changed during evaluation: {name}")
    summary = {
        "schema": "cardpilot.public_opponent_matched_multi_anchor_eval.v1",
        "status": "COMPLETED",
        "policy_mode": "greedy",
        "observation_style": "legacy_v4",
        "starting_stack_bb": 200,
        "pairs_per_anchor": args.pairs_per_anchor,
        "anchor_count": len(anchor_summaries),
        "evaluation_hands": args.pairs_per_anchor * 2 * 2 * len(anchor_summaries),
        "input_paths": {name: str(path) for name, path in input_paths.items()},
        "input_sha256": input_hashes,
        "anchors": anchor_summaries,
        "pooled_treatment_minus_control_bb100": pooled_mean * 100.0,
        "pooled_treatment_minus_control_ci95_bb100": pooled_ci * 100.0,
        "pooled_seat_deltas": pooled_seat_stats,
        "positive_anchor_count": positive_anchors,
        "gates": gates,
        "promote": all(gates.values()),
        "decision": (
            "PROMOTE_PUBLIC_OPPONENT_TREATMENT"
            if all(gates.values())
            else "REJECT_PUBLIC_OPPONENT_TREATMENT"
        ),
        "raw_pairs_sha256": sha256_path(raw_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
