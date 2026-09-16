"""Replay saved posterior-context evaluations to audit argmax support and value."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_broad_mgda_curve import frozen_decide, load_frozen_policy
from alpha_holdem.v6_contextual_residual_mgda_smoke import warmup_context
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path, state_inputs


def read_gz(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def load_endpoint(path: Path, base_policy, classifier, device: str):
    payload = torch.load(path, map_location=device, weights_only=False)
    model = PosteriorCenteredResidualPolicy(
        base_policy.model, classifier, hidden=128, policy_delta_cap=0.25, reliability_power=1
    ).to(device).eval()
    missing, unexpected = model.load_state_dict(payload["residual_state_dict"], strict=False)
    if unexpected or any(not key.startswith("base.") for key in missing):
        raise ValueError("endpoint residual state did not load exactly")
    return payload, model


@torch.no_grad()
def action_details(model, base_policy, state, context, device: str) -> dict:
    values, obs, table = state_inputs(base_policy, state, device)
    context_tensor = torch.as_tensor(context, dtype=torch.float32, device=device).unsqueeze(0)
    candidate_logits = model(*values, context_tensor)[0][0].detach().cpu().numpy().astype(np.float64)
    base_logits = model.base(values[0], values[1], values[2], values[6])[0][0].detach().cpu().numpy().astype(np.float64)
    legal = np.flatnonzero(obs["legal_mask"] > 0)
    base_slot = int(legal[int(np.argmax(base_logits[legal]))])
    candidate_slot = int(legal[int(np.argmax(candidate_logits[legal]))])
    flip = base_slot != candidate_slot
    return {
        "base_action": table[base_slot], "candidate_action": table[candidate_slot],
        "flip": flip, "street": state.street, "actor": state.actor,
        "base_margin_over_candidate": float(base_logits[base_slot] - base_logits[candidate_slot]),
        "candidate_margin_over_base": float(candidate_logits[candidate_slot] - candidate_logits[base_slot]),
        "max_abs_logit_delta": float(np.max(np.abs(candidate_logits - base_logits))),
    }


def replay_arm(model, base_policy, opponent, deck, hero_seat: int, context, device: str, arm: str):
    state = ChipState.new(deck)
    decisions = []
    while not state.terminal:
        if state.actor == hero_seat:
            details = action_details(model, base_policy, state, context, device)
            decisions.append(details)
            if arm == "base":
                action, _ = legacy_decide(base_policy, state, uniform=0.0, policy_mode="greedy")
                if action != details["base_action"]:
                    raise ValueError("base action reconstruction mismatch")
            else:
                action = details["candidate_action"]
        else:
            action = frozen_decide(opponent, state, uniform=None)
        state = apply_incr(state, action)
    return float(state.payoffs()[hero_seat]) / 100.0, decisions


def aggregate(rows: list[dict]) -> dict:
    def local(selected: list[dict]) -> dict:
        candidate_decisions = sum(row["candidate_path_decisions"] for row in selected)
        candidate_flips = sum(row["candidate_path_flips"] for row in selected)
        base_decisions = sum(row["base_path_decisions"] for row in selected)
        base_flips = sum(row["base_path_counterfactual_flips"] for row in selected)
        deltas = np.asarray([row["delta_bb"] for row in selected], dtype=np.float64)
        return {
            "hands": len(selected), "delta_bb100": float(deltas.mean() * 100.0),
            "nonzero_delta_hands": int(np.count_nonzero(deltas)),
            "positive_delta_hands": int(np.sum(deltas > 0)), "negative_delta_hands": int(np.sum(deltas < 0)),
            "candidate_path_decisions": candidate_decisions, "candidate_path_flips": candidate_flips,
            "candidate_path_flip_rate": candidate_flips / candidate_decisions,
            "base_path_decisions": base_decisions, "base_path_counterfactual_flips": base_flips,
            "base_path_counterfactual_flip_rate": base_flips / base_decisions,
            "hands_with_candidate_path_flip": sum(row["candidate_path_flips"] > 0 for row in selected),
            "hands_with_base_path_counterfactual_flip": sum(row["base_path_counterfactual_flips"] > 0 for row in selected),
        }
    result = {"pooled": local(rows)}
    result["splits"] = {split: local([row for row in rows if row["split"] == split]) for split in ("training", "holdout")}
    result["seats"] = {str(seat): local([row for row in rows if row["hero_seat"] == seat]) for seat in (0, 1)}
    result["streets"] = {}
    for street in range(4):
        events = [event for row in rows for event in row["candidate_flip_events"] if event["street"] == street]
        result["streets"][str(street)] = {
            "candidate_path_flips": len(events),
            "mean_base_margin_over_candidate": float(np.mean([event["base_margin_over_candidate"] for event in events])) if events else None,
            "mean_candidate_margin_over_base": float(np.mean([event["candidate_margin_over_base"] for event in events])) if events else None,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--pairs-per-policy", type=int, default=64)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if args.seeds < 3 or args.pairs_per_policy != 64:
        parser.error("audit requires the exact three-seed 64-pair saved curve")
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    base_policy = load_policy(args.base_checkpoint, args.device)
    classifier = torch.load(args.context_classifier, map_location="cpu", weights_only=False)["models"]["64"]
    policies = [("training", load_frozen_policy(row, args.device)) for row in spec["training_policies"]]
    policies += [("holdout", load_frozen_policy(row, args.device)) for row in spec["holdout_policies"]]
    all_results = []
    evidence_paths = []
    total_rows = total_warmup_rows = 0
    for seed_index in range(args.seeds):
        run_seed = args.seed + seed_index * 10_007
        endpoint_results = []
        for endpoint_index, endpoint in enumerate((128, 512)):
            checkpoint_path = args.run_dir / f"seed{seed_index}_endpoint{endpoint}.pt"
            _, model = load_endpoint(checkpoint_path, base_policy, classifier, args.device)
            saved = read_gz(args.run_dir / f"seed{seed_index}_endpoint{endpoint}_evaluation.jsonl.gz")
            warmup_count = len(policies) * 2 * 64
            saved_warmup, saved_rows = saved[:warmup_count], saved[warmup_count:]
            eval_seed = run_seed + 80_000_003 + endpoint_index * 9_000_001
            contexts = {}
            reconstructed_warmup = []
            for policy_index, (_, opponent) in enumerate(policies):
                for seat in (0, 1):
                    counts, rows = warmup_context(
                        base_policy, opponent, hero_seat=seat, hands=64,
                        seed=eval_seed + policy_index * 900_001 + seat * 70_001,
                    )
                    from alpha_holdem.v6_opponent_context_feasibility import context_features
                    contexts[(policy_index, seat)] = context_features(counts)
                    reconstructed_warmup.extend(rows)
            if reconstructed_warmup != saved_warmup:
                raise ValueError("saved warmup evidence did not reconstruct exactly")
            audit_rows = []
            for row in saved_rows:
                policy_index = int(row["opponent_index"])
                opponent = policies[policy_index][1]
                context = contexts[(policy_index, int(row["hero_seat"]))]
                base_reward, base_events = replay_arm(
                    model, base_policy, opponent, row["deck"], int(row["hero_seat"]), context, args.device, "base"
                )
                candidate_reward, candidate_events = replay_arm(
                    model, base_policy, opponent, row["deck"], int(row["hero_seat"]), context, args.device, "candidate"
                )
                if base_reward != row["base_reward_bb"] or candidate_reward != row["correct_reward_bb"]:
                    raise ValueError("saved paired reward did not replay exactly")
                flip_events = [event for event in candidate_events if event["flip"]]
                audit_rows.append({
                    "seed_index": seed_index, "endpoint": endpoint, "split": row["split"],
                    "opponent_index": policy_index, "hero_seat": int(row["hero_seat"]),
                    "pair_index": int(row["pair_index"]), "delta_bb": candidate_reward - base_reward,
                    "base_path_decisions": len(base_events),
                    "base_path_counterfactual_flips": sum(event["flip"] for event in base_events),
                    "candidate_path_decisions": len(candidate_events),
                    "candidate_path_flips": len(flip_events), "candidate_flip_events": flip_events,
                })
            evidence_path = args.out_dir / f"seed{seed_index}_endpoint{endpoint}_action_support.jsonl.gz"
            with gzip.open(evidence_path, "xt", encoding="utf-8", newline="\n") as handle:
                for row in audit_rows:
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
            evidence_paths.append(evidence_path)
            total_rows += len(audit_rows)
            total_warmup_rows += len(saved_warmup)
            endpoint_results.append({
                "endpoint": endpoint, "checkpoint_sha256": sha256_path(checkpoint_path),
                "saved_evaluation_sha256": sha256_path(args.run_dir / f"seed{seed_index}_endpoint{endpoint}_evaluation.jsonl.gz"),
                "action_support_sha256": sha256_path(evidence_path), "audit": aggregate(audit_rows),
            })
        all_results.append({"seed_index": seed_index, "seed": run_seed, "endpoints": endpoint_results})
    final = [row["endpoints"][1]["audit"] for row in all_results]
    gates = {
        "all_saved_warmups_exact": total_warmup_rows == args.seeds * 2 * len(policies) * 2 * 64,
        "all_saved_paired_rewards_exact": total_rows == args.seeds * 2 * len(policies) * 2 * args.pairs_per_policy,
        "endpoint512_flip_support_at_least_one_percent_all_seeds": all(row["pooled"]["candidate_path_flip_rate"] >= 0.01 for row in final),
        "endpoint512_both_seats_have_at_least_ten_flip_hands_all_seeds": all(
            row["seats"][str(seat)]["hands_with_candidate_path_flip"] >= 10 for row in final for seat in (0, 1)
        ),
        "endpoint512_holdout_has_at_least_ten_flip_hands_all_seeds": all(row["splits"]["holdout"]["hands_with_candidate_path_flip"] >= 10 for row in final),
        "endpoint512_holdout_delta_positive_at_least_two_seeds": sum(row["splits"]["holdout"]["delta_bb100"] > 0 for row in final) >= 2,
        "endpoint512_pooled_delta_positive_all_seeds": all(row["pooled"]["delta_bb100"] > 0 for row in final),
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.posterior_context_proxy_action_support_audit.v1", "status": "COMPLETED",
        "claim_scope": "EXACT_REPLAY_OF_PREEXISTING_INTERNAL_EVALUATION_NO_NEW_ENVIRONMENT_HANDS",
        "new_training_hands": 0, "new_evaluation_hands": 0,
        "replayed_warmup_rows": total_warmup_rows, "replayed_paired_evaluation_rows": total_rows,
        "seeds": all_results, "gates": gates,
        "admit_margin_aware_context_objective": admitted,
        "decision": "ADMIT_MARGIN_AWARE_CONTEXT_OBJECTIVE_SMOKE" if admitted else "PIVOT_FROM_CURRENT_CONTEXT_PROXY",
        "artifact_sha256": {path.name: sha256_path(path) for path in evidence_paths},
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(), "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "decision": summary["decision"], "rows": total_rows}, sort_keys=True))


if __name__ == "__main__":
    main()
