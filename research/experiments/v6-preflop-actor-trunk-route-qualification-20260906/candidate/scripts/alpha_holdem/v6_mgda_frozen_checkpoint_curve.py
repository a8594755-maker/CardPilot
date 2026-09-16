"""Evaluate a frozen MGDA continuation against its exact parent checkpoint."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import sys
import time

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_dual_contract_mgda_fresh_curve import summarize_delta
from alpha_holdem.v6_dual_contract_residual_training_smoke import (
    mean_ci95,
    play_candidate_hand,
    sha256_path,
)
from alpha_holdem.v6_mgda_source_objective_continuation import panel_metric


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--opponent", action="append", type=Path, required=True)
    parser.add_argument("--earlier-checkpoint", type=Path, required=True)
    parser.add_argument("--later-checkpoint", type=Path, required=True)
    parser.add_argument("--state-panel", type=Path, required=True)
    parser.add_argument("--pairs-per-anchor", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.opponent) != 3:
        parser.error("exactly three opponents required")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    base_path = args.base_checkpoint.resolve()
    earlier_path = args.earlier_checkpoint.resolve()
    later_path = args.later_checkpoint.resolve()
    panel_path = args.state_panel.resolve()
    base_sha = sha256_path(base_path)
    earlier_sha = sha256_path(earlier_path)
    later_sha = sha256_path(later_path)
    earlier = torch.load(earlier_path, map_location=args.device, weights_only=False)
    later = torch.load(later_path, map_location=args.device, weights_only=False)
    lineage_valid = (
        earlier["base_sha256"] == base_sha
        and later["base_sha256"] == base_sha
        and later["start_checkpoint_sha256"] == earlier_sha
        and earlier["dose_hands"] == 8192
        and later["dose_hands"] == 12288
    )
    if not lineage_valid:
        raise RuntimeError("checkpoint lineage mismatch")
    base_policy = load_policy(base_path, args.device)
    opponents = [load_policy(path.resolve(), args.device) for path in args.opponent]
    models = {}
    for name, checkpoint in (("earlier", earlier), ("later", later)):
        model = DualContractResidualPolicy(
            base_policy.model, hidden=128, policy_delta_cap=0.25
        ).to(args.device).eval()
        model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
        models[name] = model
    panel_metrics = {
        name: panel_metric(model, base_policy, panel_path, args.device)
        for name, model in models.items()
    }

    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    rows = []
    max_deltas = {"earlier": 0.0, "later": 0.0}
    with gzip.open(evaluation_path, "xt", encoding="utf-8", newline="\n") as handle:
        for anchor_index, anchor in enumerate(opponents):
            rng = random.Random(args.seed + 50_000_017 * (anchor_index + 1))
            for pair_index in range(args.pairs_per_anchor):
                deck = list(range(52))
                rng.shuffle(deck)
                rewards = {"earlier": [], "later": []}
                for seat in (0, 1):
                    for name in ("earlier", "later"):
                        reward, observed = play_candidate_hand(
                            models[name], base_policy, anchor, deck, seat, args.device
                        )
                        rewards[name].append(reward)
                        max_deltas[name] = max(max_deltas[name], observed)
                seat_delta = [
                    rewards["later"][seat] - rewards["earlier"][seat]
                    for seat in (0, 1)
                ]
                row = {
                    "anchor_index": anchor_index,
                    "anchor_sha256": anchor.sha256,
                    "pair_index": pair_index,
                    "deck": deck,
                    "earlier_rewards_bb": rewards["earlier"],
                    "later_rewards_bb": rewards["later"],
                    "seat_delta_bb": seat_delta,
                    "delta_bb": sum(seat_delta) / 2.0,
                }
                rows.append(row)
                handle.write(json.dumps(row, sort_keys=True) + "\n")
            selected = [row for row in rows if row["anchor_index"] == anchor_index]
            mean, half = mean_ci95([row["delta_bb"] for row in selected])
            print(f"anchor={anchor_index} later_earlier={mean*100:+.4f} +/- {half*100:.4f}", flush=True)

    evaluation = summarize_delta(rows)
    disagreement_growth = (
        panel_metrics["later"]["greedy_disagreement"]
        - panel_metrics["earlier"]["greedy_disagreement"]
    )
    gates = {
        "exact_lineage_valid": lineage_valid,
        "pooled_delta_positive": evaluation["pooled_delta_bb100"] > 0,
        "standard10_delta_nonnegative": evaluation["anchors"][0]["delta_bb100"] >= 0,
        "positive_delta_on_at_least_two_anchors": sum(row["delta_bb100"] > 0 for row in evaluation["anchors"]) >= 2,
        "both_seat_deltas_nonnegative": all(row["delta_bb100"] >= 0 for row in evaluation["seats"]),
        "later_agreement_at_least_95pct": panel_metrics["later"]["greedy_agreement"] >= 0.95,
        "disagreement_growth_at_most_2pp": disagreement_growth <= 0.02,
        "both_residual_caps_respected": max(max_deltas.values()) <= 0.250001,
    }
    admit = all(gates.values())
    summary = {
        "schema": "cardpilot.mgda_frozen_checkpoint_curve.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "earlier_checkpoint_sha256": earlier_sha,
        "later_checkpoint_sha256": later_sha,
        "state_panel_sha256": sha256_path(panel_path),
        "panel_metrics": panel_metrics,
        "disagreement_growth_8k_to_12k": disagreement_growth,
        "evaluation_hands": len(rows) * 4,
        "evaluation": evaluation,
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "max_abs_residual_logit": max_deltas,
        "gates": gates,
        "admit_seed1_continuation_replication": admit,
        "decision": "ADMIT_SEED1_12K_REPLICATION" if admit else "HOLD_SIX_OBJECTIVE_MGDA_AT_8K",
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
