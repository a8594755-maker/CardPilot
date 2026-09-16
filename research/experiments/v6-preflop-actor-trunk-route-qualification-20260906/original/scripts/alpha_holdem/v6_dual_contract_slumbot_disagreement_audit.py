"""Replay Standard10 on frozen dual-contract Slumbot decision states."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_execution_v6 import (
    external_decision as dual_external_decision,
    load_policy as load_dual_policy,
)
from alpha_holdem.execution_v6 import sha256_file
from alpha_holdem.legacy_observation_bridge_v6 import (
    external_decision as base_external_decision,
    load_policy as load_base_policy,
)
from alpha_holdem.policy_contract_v6 import from_external


def mean_ci(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean_bb100": None, "ci95_low_bb100": None, "ci95_high_bb100": None}
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean() * 100)
    half = 0.0 if len(array) == 1 else 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array)) * 100
    return {
        "n": len(values), "mean_bb100": mean,
        "ci95_low_bb100": mean - half, "ci95_high_bb100": mean + half,
    }


def action_kind(action: str) -> str:
    return "raise" if action.startswith("b") else {"f": "fold", "c": "call", "k": "check"}[action]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--deployment-checkpoint", type=Path, required=True)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    base_path = args.base_checkpoint.resolve()
    deployment_path = args.deployment_checkpoint.resolve()
    base = load_base_policy(base_path, "cpu")
    deployment = load_dual_policy(deployment_path, base_path, "cpu")
    base_sha = sha256_file(base_path)
    deployment_sha = sha256_file(deployment_path)

    raw_path = args.out_dir / "decision_comparisons.jsonl.gz"
    decision_rows = []
    hands = []
    session_dirs = sorted(path for path in args.session_root.iterdir() if path.is_dir() and path.name.startswith("s"))
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as output:
        for session_dir in session_dirs:
            for line in (session_dir / "hands.jsonl").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                hand = json.loads(line)
                reward = float(hand["winnings_bb"])
                seat = int(hand["terminal_response"]["client_pos"])
                hand_key = f"{session_dir.name}:{hand['successful_hand']}"
                hand_disagreements = []
                hand_streets = set()
                for decision_index, decision in enumerate(hand["decisions"]):
                    response = decision["response"]
                    uniform = float(decision["uniform"])
                    candidate_action, candidate_info = dual_external_decision(
                        deployment, response, uniform=uniform, device="cpu", policy_mode="greedy"
                    )
                    if any(decision.get(key) != value for key, value in candidate_info.items()):
                        raise RuntimeError("Deployed checkpoint replay differs from raw decision evidence")
                    base_action, base_info = base_external_decision(
                        base, response, uniform=uniform, device="cpu", policy_mode="greedy"
                    )
                    candidate_probs = np.asarray(candidate_info["model_probs"], dtype=np.float64)
                    base_probs = np.asarray(base_info["model_probs"], dtype=np.float64)
                    tv = float(np.abs(candidate_probs - base_probs).sum() / 2)
                    positive = candidate_probs > 0
                    kl = float(np.sum(candidate_probs[positive] * np.log(
                        candidate_probs[positive] / np.maximum(base_probs[positive], 1e-300)
                    )))
                    state = from_external(
                        response["action"], response["hole_cards"], response.get("board", []), seat
                    )
                    disagreement = candidate_action != base_action
                    row = {
                        "session": session_dir.name,
                        "hand": int(hand["successful_hand"]),
                        "hand_key": hand_key,
                        "decision_index": decision_index,
                        "seat": seat,
                        "street": int(state.street),
                        "pot_chips": int(state.pot),
                        "to_call_chips": int(state.to_call),
                        "reward_bb": reward,
                        "candidate_action": candidate_action,
                        "candidate_kind": action_kind(candidate_action),
                        "base_action": base_action,
                        "base_kind": action_kind(base_action),
                        "disagreement": disagreement,
                        "tv": tv,
                        "kl_candidate_to_base": kl,
                    }
                    decision_rows.append(row)
                    output.write(json.dumps(row, sort_keys=True) + "\n")
                    if disagreement:
                        hand_disagreements.append(row)
                        hand_streets.add(int(state.street))
                hands.append({
                    "hand_key": hand_key, "session": session_dir.name, "seat": seat,
                    "reward_bb": reward, "decisions": len(hand["decisions"]),
                    "disagreements": len(hand_disagreements),
                    "disagreement_streets": sorted(hand_streets),
                })

    disagreements = [row for row in decision_rows if row["disagreement"]]
    disagreement_hands = [row for row in hands if row["disagreements"]]
    agreement_hands = [row for row in hands if not row["disagreements"]]
    total_negative = sum(-min(row["reward_bb"], 0.0) for row in hands)
    disagreement_negative = sum(-min(row["reward_bb"], 0.0) for row in disagreement_hands)

    strata = []
    negative_supported = 0
    for seat in (0, 1):
        for street in range(4):
            selected_decisions = [row for row in decision_rows if row["seat"] == seat and row["street"] == street]
            selected_hands = [
                row for row in hands
                if row["seat"] == seat and street in row["disagreement_streets"]
            ]
            outcome = mean_ci([row["reward_bb"] for row in selected_hands])
            supported = outcome["n"] >= 30
            negative_supported += int(supported and outcome["mean_bb100"] < 0)
            strata.append({
                "seat": seat, "street": street, "decisions": len(selected_decisions),
                "disagreements": sum(row["disagreement"] for row in selected_decisions),
                "disagreement_rate": (
                    sum(row["disagreement"] for row in selected_decisions) / len(selected_decisions)
                    if selected_decisions else None
                ),
                "disagreement_hand_outcome": outcome,
                "supported_at_30_hands": supported,
            })
    transition_counts = Counter(
        f"{row['base_kind']}:{row['base_action']}->{row['candidate_kind']}:{row['candidate_action']}"
        for row in disagreements
    )
    disagreement_rate = len(disagreements) / len(decision_rows)
    loss_fraction = disagreement_negative / total_negative if total_negative else 0.0
    panel_rate = 0.035482
    gates = {
        "all_prior_hands_reused_exactly": len(hands) == 5000,
        "all_prior_decisions_replayed_exactly": len(decision_rows) == 14975,
        "base_hash_exact": base.sha256 == base_sha == deployment.base_sha256,
        "deployment_hash_exact": deployment.sha256 == deployment_sha,
        "live_disagreement_exceeds_panel_plus_2pp": disagreement_rate > panel_rate + 0.02,
        "localized_loss_concentration": disagreement_rate <= 0.10 and loss_fraction >= 0.60,
        "broad_negative_supported_strata": negative_supported >= 3,
    }
    if gates["localized_loss_concentration"]:
        diagnosis = "LOCALIZED_RESIDUAL_FAILURE"
    elif gates["broad_negative_supported_strata"]:
        diagnosis = "BROAD_PROXY_TRANSFER_FAILURE"
    else:
        diagnosis = "MIXED_OR_UNDERPOWERED"
    summary = {
        "schema": "cardpilot.dual_contract_slumbot_disagreement_audit.v1",
        "status": "COMPLETED",
        "base_sha256": base_sha,
        "deployment_sha256": deployment_sha,
        "source_residual_sha256": deployment.source_residual_sha256,
        "reused_slumbot_hands": len(hands),
        "decision_rows": len(decision_rows),
        "disagreements": len(disagreements),
        "disagreement_rate": disagreement_rate,
        "mean_tv": float(np.mean([row["tv"] for row in decision_rows])),
        "mean_kl_candidate_to_base": float(np.mean([row["kl_candidate_to_base"] for row in decision_rows])),
        "hands_with_disagreement": len(disagreement_hands),
        "hand_disagreement_rate": len(disagreement_hands) / len(hands),
        "disagreement_hand_outcome": mean_ci([row["reward_bb"] for row in disagreement_hands]),
        "agreement_hand_outcome": mean_ci([row["reward_bb"] for row in agreement_hands]),
        "total_negative_bb": total_negative,
        "disagreement_hand_negative_bb": disagreement_negative,
        "disagreement_hand_loss_fraction": loss_fraction,
        "negative_supported_seat_street_strata": negative_supported,
        "seat_street_strata": strata,
        "top_action_transitions": [
            {"transition": key, "count": value, "fraction_of_disagreements": value / len(disagreements)}
            for key, value in transition_counts.most_common(20)
        ],
        "gates": gates,
        "diagnosis": diagnosis,
        "raw_comparisons_sha256": sha256_file(raw_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "causal_caveat": "Candidate-induced states and observed outcomes support descriptive attribution only, not counterfactual value claims.",
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
