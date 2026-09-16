"""Build and validate a public-state Slumbot opponent action model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import time

import numpy as np
import torch
from torch import nn

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import PhysicalV6Encoder, legal_slot_actions
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from deep_cfr.hand_eval import card_from_str


ACTION_RE = re.compile(r"b[0-9]+|[fkc/]")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _deck_for_public(hole_cards, board, player):
    holes = tuple(card_from_str(card) for card in hole_cards)
    public = tuple(card_from_str(card) for card in board)
    if player not in (0, 1) or len(holes) != 2 or len(public) not in (0, 3, 4, 5):
        raise ValueError("invalid external cards or seat")
    known = set((*holes, *public))
    if len(known) != len(holes) + len(public):
        raise ValueError("duplicate observed card")
    unused = [card for card in range(52) if card not in known]
    opponent = tuple(unused[:2])
    future = public + tuple(unused[2 : 2 + 5 - len(public)])
    first = (*holes, *opponent) if player == 0 else (*opponent, *holes)
    used = set((*first, *future))
    return (*first, *(card for card in range(52) if card not in used), *reversed(future))


def _slot_for_observed(state: ChipState, action: str):
    slot_actions = legal_slot_actions(state)
    exact = [slot for slot, legal_action in slot_actions if legal_action == action]
    if exact:
        return exact[0], True, 0.0
    if not action.startswith("b"):
        raise ValueError(f"non-raise action {action!r} missing from physical table")
    target = int(action[1:])
    raises = [
        (slot, int(legal_action[1:]))
        for slot, legal_action in slot_actions if legal_action.startswith("b")
    ]
    if not raises:
        raise ValueError("observed raise at a state with no legal physical raise")
    slot, nearest = min(raises, key=lambda item: (abs(item[1] - target), item[0]))
    relative_error = abs(nearest - target) / max(state.pot + state.to_call, 100)
    return slot, False, relative_error


def _extract_hand(record, session_index):
    response = record["terminal_response"]
    action_string = response["action"]
    tokens = ACTION_RE.findall(action_string)
    if "".join(tokens) != action_string:
        raise ValueError("malformed terminal action prefix")
    player = int(response["client_pos"])
    state = ChipState.new(_deck_for_public(
        response["hole_cards"], response.get("board", []), player
    ))
    rows = []
    separator_allowed = False
    for token in tokens:
        if token == "/":
            # Slumbot serializes all-in runout street boundaries after the
            # betting state is already terminal (for example ``c///``).
            if state.terminal:
                continue
            if not separator_allowed:
                raise ValueError("unexpected street separator")
            separator_allowed = False
            continue
        if state.terminal:
            raise ValueError("action after terminal state")
        if state.actor != player:
            encoded = PhysicalV6Encoder.encode(state)
            encoded[0] = -1.0  # Never expose placeholder or showdown bot cards.
            mask = PhysicalV6Encoder.legal_mask(state)
            slot, exact, error = _slot_for_observed(state, token)
            rows.append((encoded, mask, slot, state.street, exact, error, session_index))
        old_street = state.street
        state = apply_incr(state, token)
        separator_allowed = not state.terminal and state.street > old_street
    if not state.terminal:
        raise ValueError("terminal record did not replay to a terminal state")
    observed_board = tuple(card_from_str(card) for card in response.get("board", []))
    if state.board != observed_board:
        raise ValueError("replayed board mismatch")
    return rows


def _load(sessions_dir: Path, session_names):
    features = []
    masks = []
    labels = []
    streets = []
    exacts = []
    errors = []
    sessions = []
    input_files = []
    hand_counts = {}
    replay_failures = []
    for session_index, name in enumerate(session_names):
        path = sessions_dir / name / "hands.jsonl"
        input_files.append({"path": str(path), "sha256": _sha256(path), "bytes": path.stat().st_size})
        hands = 0
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                hands += 1
                try:
                    rows = _extract_hand(json.loads(line), session_index)
                except Exception as exc:
                    replay_failures.append({
                        "session": name, "line": line_number, "error": str(exc)
                    })
                    continue
                for feature, mask, label, street, exact, error, row_session in rows:
                    features.append(feature)
                    masks.append(mask)
                    labels.append(label)
                    streets.append(street)
                    exacts.append(exact)
                    errors.append(error)
                    sessions.append(row_session)
        hand_counts[name] = hands
    return {
        "features": np.asarray(features, dtype=np.float32),
        "masks": np.asarray(masks, dtype=np.float32),
        "labels": np.asarray(labels, dtype=np.int64),
        "streets": np.asarray(streets, dtype=np.int64),
        "exacts": np.asarray(exacts, dtype=np.bool_),
        "errors": np.asarray(errors, dtype=np.float32),
        "sessions": np.asarray(sessions, dtype=np.int64),
        "session_names": list(session_names),
        "hand_counts": hand_counts,
        "input_files": input_files,
        "replay_failures": replay_failures,
    }


class PublicOpponentModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(PhysicalV6Encoder.RAW_DIM, 128), nn.ReLU(),
            nn.Linear(128, 128), nn.ReLU(), nn.Linear(128, 9),
        )

    def forward(self, features, masks):
        return self.layers(features).masked_fill(masks <= 0, -1e9)


def _baseline(train, split):
    counts = np.ones((4, 9), dtype=np.float64)
    for street, label in zip(train["streets"], train["labels"]):
        counts[street, label] += 1.0
    probabilities = []
    predictions = []
    for street, mask, label in zip(split["streets"], split["masks"], split["labels"]):
        weights = counts[street] * mask
        weights /= weights.sum()
        probabilities.append(float(weights[label]))
        predictions.append(int(np.argmax(weights)))
    return {
        "nll": float(-np.mean(np.log(np.maximum(probabilities, 1e-12)))),
        "accuracy": float(np.mean(np.asarray(predictions) == split["labels"])),
    }


@torch.no_grad()
def _evaluate(model, split):
    model.eval()
    logits = model(torch.from_numpy(split["features"]), torch.from_numpy(split["masks"]))
    labels = torch.from_numpy(split["labels"])
    return {
        "nll": float(nn.functional.cross_entropy(logits, labels).item()),
        "accuracy": float((logits.argmax(-1) == labels).float().mean().item()),
    }


def _train(model, train, epochs, seed):
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    rng = np.random.default_rng(seed)
    losses = []
    model.train()
    for epoch in range(epochs):
        order = rng.permutation(len(train["labels"]))
        epoch_losses = []
        for start in range(0, len(order), 1024):
            indices = order[start : start + 1024]
            logits = model(
                torch.from_numpy(train["features"][indices]),
                torch.from_numpy(train["masks"][indices]),
            )
            labels = torch.from_numpy(train["labels"][indices])
            loss = nn.functional.cross_entropy(logits, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_losses.append(float(loss.item()))
        losses.append(float(np.mean(epoch_losses)))
    model.eval()
    return losses


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    all_sessions = args.train_sessions + args.validation_sessions
    loaded = _load(args.sessions_dir, all_sessions)
    train_indices = np.flatnonzero(loaded["sessions"] < len(args.train_sessions))
    validation_indices = np.flatnonzero(loaded["sessions"] >= len(args.train_sessions))
    fields = ("features", "masks", "labels", "streets", "exacts", "errors", "sessions")
    train = {key: loaded[key][train_indices] for key in fields}
    validation = {key: loaded[key][validation_indices] for key in fields}
    baseline = _baseline(train, validation)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    model = PublicOpponentModel()
    losses = _train(model, train, args.epochs, args.seed)
    learned = _evaluate(model, validation)
    checkpoint_path = args.output_dir / "public_opponent_model.pt"
    torch.save({
        "schema_version": 1,
        "model": "PublicOpponentModel56x128x128x9",
        "private_card_contract": "masked_combo_feature_minus_one",
        "action_contract": "physical_v6_nearest_9slot_v1",
        "state_dict": model.state_dict(),
        "train_sessions": args.train_sessions,
        "validation_sessions": args.validation_sessions,
        "source_files": loaded["input_files"],
    }, checkpoint_path)
    dataset_path = args.output_dir / "dataset.npz"
    np.savez_compressed(dataset_path, **{key: loaded[key] for key in fields})
    all_errors = loaded["errors"]
    gates = {
        "all_20000_hands_loaded": sum(loaded["hand_counts"].values()) == 20_000,
        "zero_replay_failures": not loaded["replay_failures"],
        "at_least_30000_bot_decisions": len(loaded["labels"]) >= 30_000,
        "private_combo_feature_always_masked": bool(np.all(loaded["features"][:, 0] == -1.0)),
        "exact_or_near_action_coverage": float(np.mean(all_errors <= 0.10)) >= 0.99,
        "validation_nll_improves_5pct": learned["nll"] <= 0.95 * baseline["nll"],
        "validation_accuracy_improves_2pt": learned["accuracy"] >= baseline["accuracy"] + 0.02,
    }
    result = {
        "schema_version": 1,
        "config": {
            "train_sessions": args.train_sessions,
            "validation_sessions": args.validation_sessions,
            "epochs": args.epochs,
            "seed": args.seed,
        },
        "accounting": {
            "environment_training_hands": 0,
            "offline_source_hands": sum(loaded["hand_counts"].values()),
            "offline_supervised_samples": len(loaded["labels"]),
            "train_samples": len(train["labels"]),
            "validation_samples": len(validation["labels"]),
            "evaluation_hands": 0,
        },
        "data": {
            "hand_counts": loaded["hand_counts"],
            "source_files": loaded["input_files"],
            "replay_failures": loaded["replay_failures"][:100],
            "exact_action_fraction": float(np.mean(loaded["exacts"])),
            "within_0_10_pot_fraction": float(np.mean(all_errors <= 0.10)),
            "median_nearest_relative_error": float(np.median(all_errors)),
            "p95_nearest_relative_error": float(np.quantile(all_errors, 0.95)),
            "street_counts": np.bincount(loaded["streets"], minlength=4).tolist(),
            "slot_counts": np.bincount(loaded["labels"], minlength=9).tolist(),
        },
        "training": {"epoch_losses": losses},
        "validation": {
            "street_frequency_baseline": baseline,
            "learned_public_state_model": learned,
            "relative_nll_improvement": 1.0 - learned["nll"] / baseline["nll"],
            "accuracy_point_improvement": learned["accuracy"] - baseline["accuracy"],
        },
        "artifacts": {
            "checkpoint": str(checkpoint_path),
            "checkpoint_sha256": _sha256(checkpoint_path),
            "dataset": str(dataset_path),
            "dataset_sha256": _sha256(dataset_path),
        },
        "gates": gates,
        "elapsed_seconds": time.time() - started,
    }
    result["admit_diverse_league_opponent_smoke"] = all(gates.values())
    result["decision"] = (
        "ADMIT_PUBLIC_OPPONENT_MODEL_CONTRACT_SMOKE"
        if result["admit_diverse_league_opponent_smoke"]
        else "REJECT_SLUMBOT_PUBLIC_OPPONENT_MODEL_FEASIBILITY"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions-dir", type=Path, required=True)
    parser.add_argument("--train-sessions", nargs="+", required=True)
    parser.add_argument("--validation-sessions", nargs="+", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=60914)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if set(args.train_sessions) & set(args.validation_sessions):
        raise ValueError("train and validation sessions must be disjoint")
    torch.set_num_threads(1)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
