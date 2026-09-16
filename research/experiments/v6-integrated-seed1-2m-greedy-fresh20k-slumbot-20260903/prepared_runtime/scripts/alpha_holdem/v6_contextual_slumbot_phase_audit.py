"""Read-only phase and action-drift audit for contextual Slumbot sessions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_execution_v6 import SessionContextTracker, load_policy
from alpha_holdem.legacy_observation_bridge_v6 import decide as base_decide
from alpha_holdem.policy_contract_v6 import from_external


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def estimate(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array)) if len(array) > 1 else float("nan")
    mean = float(array.mean())
    return {"hands": len(values), "bb_per_100": mean, "ci95_lower": mean - half, "ci95_upper": mean + half}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", action="append", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.out_json.exists():
        raise FileExistsError(args.out_json)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    policy = load_policy(args.model, args.base_model, "cpu")
    phase_values = {"cold_start": [], "context_active": []}
    seat_values = {0: [], 1: []}
    sessions = []
    cold_decisions = active_decisions = cold_disagreements = active_disagreements = 0
    active_reliability = []
    active_changed_hand_values, active_unchanged_hand_values = [], []
    for directory in args.session_dir:
        rows = read_jsonl(directory / "hands.jsonl")
        tracker = SessionContextTracker(policy.cold_start_hands)
        session_values = []
        for index, row in enumerate(rows, start=1):
            start = tracker.start_hand(index)
            cold = bool(start["context_cold_start"])
            changed = False
            if not cold:
                context_tensor = torch.as_tensor(tracker.context, dtype=torch.float32).unsqueeze(0)
                with torch.no_grad():
                    posterior = policy.model.context_posterior(context_tensor)[0]
                    entropy = float(-(posterior * posterior.clamp_min(1e-15).log()).sum())
                active_reliability.append(1.0 - entropy / math.log(policy.model.classes))
            for decision in row["decisions"]:
                response = decision["response"]
                state = from_external(response["action"], response["hole_cards"], response["board"], response["client_pos"])
                base_action, _ = base_decide(
                    policy.base_policy, state, uniform=float(decision["uniform"]), policy_mode="greedy"
                )
                different = base_action != decision["direct_increment"]
                changed = changed or different
                if cold:
                    cold_decisions += 1
                    cold_disagreements += int(different)
                else:
                    active_decisions += 1
                    active_disagreements += int(different)
            end = tracker.finish_hand(index, row["terminal_response"])
            if end != row["session_policy_state"]:
                raise ValueError("raw session context state does not replay exactly")
            value = float(row["winnings_chips"])
            phase_values["cold_start" if cold else "context_active"].append(value)
            seat_values[int(row["terminal_response"]["client_pos"])].append(value)
            session_values.append(value)
            if not cold:
                (active_changed_hand_values if changed else active_unchanged_hand_values).append(value)
        sessions.append({"session_id": rows[0]["session_id"], **estimate(session_values)})
    result = {
        "schema": "cardpilot.posterior_context_slumbot_phase_audit.v1",
        "status": "PASS", "claim_scope": "DESCRIPTIVE_SAME-RUN_AUDIT_NOT_CAUSAL_CONTROL",
        "model_sha256": policy.sha256,
        "phases": {key: estimate(values) for key, values in phase_values.items()},
        "seats": {str(key): estimate(values) for key, values in seat_values.items()},
        "sessions": sessions,
        "cold_start_decisions": cold_decisions,
        "cold_start_action_disagreements_vs_standard10": cold_disagreements,
        "context_active_decisions": active_decisions,
        "context_active_action_disagreements_vs_standard10": active_disagreements,
        "context_active_action_disagreement_rate": active_disagreements / active_decisions,
        "active_mean_context_reliability": float(np.mean(active_reliability)),
        "active_changed_hands": estimate(active_changed_hand_values),
        "active_unchanged_hands": estimate(active_unchanged_hand_values),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
