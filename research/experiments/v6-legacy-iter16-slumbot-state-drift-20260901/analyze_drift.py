#!/usr/bin/env python3
"""Outcome-blind parent/iter16 drift on audited Slumbot decision states."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import from_external  # noqa: E402

PARENT_MODEL = ROOT / "models/baseline/standard10/latest.pt"
CANDIDATE_MODEL = ROOT / "research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/checkpoints/checkpoint_iter000016_hands000000065966.pt"
PARENT_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CANDIDATE_SHA = "0b1b58a87637f620ae580754bc940ec7aca246d94762d77717c9b578aac9f290"
CORPORA = {
    "parent_onpolicy": ROOT / "research/experiments/v6-standard10-legacy-bridge-greedy-fresh20k-20260901/sessions",
    "candidate_onpolicy": ROOT / "research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/sessions",
}
BATCH_SIZE = 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@torch.no_grad()
def infer(model, observations: list[dict], device: str) -> np.ndarray:
    tensors = [
        torch.as_tensor(np.stack([obs[key] for obs in observations]), dtype=torch.float32, device=device)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    logits = logits.masked_fill(tensors[-1] <= 0, float("-inf"))
    return torch.softmax(logits, dim=-1).cpu().numpy()


def action_class(action: str, state) -> str:
    if action == "f":
        return "fold"
    if action in {"k", "c"}:
        return "check_call"
    amount = int(action[1:])
    return "all_in" if amount == state.max_to else "raise"


def bucket(value: float, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def summarize(rows: list[dict]) -> dict:
    tv = np.asarray([row["tv"] for row in rows], dtype=np.float64)
    disagree = np.asarray([row["greedy_disagreement"] for row in rows], dtype=np.float64)
    parent_margin = np.asarray([row["parent_margin"] for row in rows], dtype=np.float64)
    candidate_margin = np.asarray([row["candidate_margin"] for row in rows], dtype=np.float64)
    stakes = np.asarray([row["pot_bb"] + row["to_call_bb"] for row in rows], dtype=np.float64)
    return {
        "states": len(rows),
        "mean_tv": float(tv.mean()),
        "p95_tv": float(np.quantile(tv, 0.95)),
        "greedy_disagreements": int(disagree.sum()),
        "greedy_disagreement_rate": float(disagree.mean()),
        "stake_weighted_disagreement_rate": float(np.dot(disagree, stakes) / stakes.sum()),
        "mean_parent_margin": float(parent_margin.mean()),
        "mean_parent_margin_on_disagreement": float(parent_margin[disagree.astype(bool)].mean()) if disagree.any() else None,
        "mean_candidate_margin_on_disagreement": float(candidate_margin[disagree.astype(bool)].mean()) if disagree.any() else None,
    }


def main() -> None:
    started = time.time()
    device = "cuda"
    torch.set_num_threads(8)
    parent = load_policy(PARENT_MODEL, device)
    candidate = load_policy(CANDIDATE_MODEL, device)
    if parent.sha256 != PARENT_SHA or candidate.sha256 != CANDIDATE_SHA:
        raise RuntimeError("Frozen checkpoint mismatch")
    raw_path = HERE / "drift_raw.jsonl.gz"
    rows_by_corpus = defaultdict(list)
    pending = []
    logged_parity = Counter()

    def flush(handle) -> None:
        if not pending:
            return
        observations = [item["observation"] for item in pending]
        left_matrix = infer(parent.model, observations, device)
        right_matrix = infer(candidate.model, observations, device)
        for item, left, right in zip(pending, left_matrix, right_matrix):
            parent_slot = int(np.argmax(left))
            candidate_slot = int(np.argmax(right))
            state = item["state"]
            table = item["table"]
            parent_action = table[parent_slot]
            candidate_action = table[candidate_slot]
            logged_action = item["logged_action"]
            expected = parent_action if item["corpus"] == "parent_onpolicy" else candidate_action
            logged_parity["states"] += 1
            logged_parity["matches"] += int(logged_action == expected)
            parent_legal = np.sort(left[left > 0])
            candidate_legal = np.sort(right[right > 0])
            effective = min(state.stacks)
            spr = effective / max(state.pot, 1)
            row = {
                "corpus": item["corpus"],
                "session": item["session"],
                "hand": item["hand"],
                "decision": item["decision"],
                "street": state.street,
                "client_pos": item["client_pos"],
                "pot_bb": state.pot / 100.0,
                "to_call_bb": state.to_call / 100.0,
                "effective_stack_bb": effective / 100.0,
                "spr": spr,
                "pot_bucket": bucket(state.pot / 100.0, (4, 10, 30, float("inf")), ("lt4", "4to10", "10to30", "ge30")),
                "spr_bucket": bucket(spr, (1, 3, 8, float("inf")), ("lt1", "1to3", "3to8", "ge8")),
                "facing_bet": state.to_call > 0,
                "tv": float(0.5 * np.abs(left - right).sum()),
                "parent_slot": parent_slot,
                "candidate_slot": candidate_slot,
                "parent_action": parent_action,
                "candidate_action": candidate_action,
                "parent_action_class": action_class(parent_action, state),
                "candidate_action_class": action_class(candidate_action, state),
                "greedy_disagreement": parent_action != candidate_action,
                "parent_margin": float(parent_legal[-1] - parent_legal[-2]) if len(parent_legal) > 1 else 1.0,
                "candidate_margin": float(candidate_legal[-1] - candidate_legal[-2]) if len(candidate_legal) > 1 else 1.0,
                "logged_action_parity": logged_action == expected,
            }
            rows_by_corpus[item["corpus"]].append(row)
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        pending.clear()

    with gzip.open(raw_path, "wt", encoding="utf-8") as output:
        for corpus, directory in CORPORA.items():
            for session in range(1, 9):
                hands_path = directory / f"s{session:02d}/hands.jsonl"
                for hand_index, line in enumerate(hands_path.read_text(encoding="utf-8").splitlines(), 1):
                    # Deliberately inspect only decision-response fields. Outcome and
                    # cumulative result fields are neither read nor copied.
                    hand = json.loads(line)
                    for decision_index, decision in enumerate(hand["decisions"]):
                        response = decision["response"]
                        state = from_external(
                            response["action"], response["hole_cards"],
                            response.get("board", []), response["client_pos"],
                        )
                        observation, table = legacy_observation_from_state(state, restrict_to_v6_action_table=True)
                        pending.append({
                            "corpus": corpus, "session": session, "hand": hand_index,
                            "decision": decision_index, "client_pos": response["client_pos"],
                            "state": state, "observation": observation, "table": table,
                            "logged_action": decision["direct_increment"],
                        })
                        if len(pending) >= BATCH_SIZE:
                            flush(output)
        flush(output)

    breakdowns = {}
    for corpus, rows in rows_by_corpus.items():
        groups = {}
        for field in ("street", "client_pos", "pot_bucket", "spr_bucket", "facing_bet", "parent_action_class"):
            values = sorted({row[field] for row in rows}, key=str)
            groups[field] = {str(value): summarize([row for row in rows if row[field] == value]) for value in values}
        transitions = Counter(
            f"{row['parent_action_class']}->{row['candidate_action_class']}"
            for row in rows if row["greedy_disagreement"]
        )
        breakdowns[corpus] = {
            "overall": summarize(rows),
            "groups": groups,
            "disagreement_action_transitions": dict(transitions.most_common()),
        }
    result = {
        "schema": "cardpilot.legacy_iter16_slumbot_state_drift.v1",
        "status": "PASS" if logged_parity["states"] == logged_parity["matches"] else "FAIL",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "outcome_blind": True,
            "corpora": {key: str(value.resolve()) for key, value in CORPORA.items()},
            "breakdowns": ["street", "client_pos", "pot_bucket", "spr_bucket", "facing_bet", "parent_action_class"],
        },
        "parent": {"path": str(PARENT_MODEL.resolve()), "sha256": parent.sha256},
        "candidate": {"path": str(CANDIDATE_MODEL.resolve()), "sha256": candidate.sha256},
        "logged_policy_replay": dict(logged_parity),
        "corpora": breakdowns,
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_file(raw_path),
        "model_state_queries": sum(len(rows) for rows in rows_by_corpus.values()) * 2,
        "environment_training_hands": 0,
        "slumbot_hands": 0,
        "wall_time_seconds": time.time() - started,
    }
    (HERE / "drift_analysis.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
