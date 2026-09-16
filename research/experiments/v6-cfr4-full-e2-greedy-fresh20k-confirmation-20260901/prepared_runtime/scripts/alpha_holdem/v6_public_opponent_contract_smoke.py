"""Replay and legality smoke for the frozen public opponent contract."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.public_opponent_v6 import decide, load_public_opponent, strategy
from alpha_holdem.rules_v6 import ChipState


EXPECTED_OPPONENT_SHA = "a3e796e54b54711bf9cc3143b09387efc5ba8180b6d0e92a9de313e20c66d1ee"
EXPECTED_STANDARD10_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _alter_actor_holes(state: ChipState) -> ChipState:
    used = set((*state.holes[0], *state.holes[1], *state.board))
    replacements = tuple(card for card in range(52) if card not in used)[:2]
    holes = list(state.holes)
    holes[state.actor] = replacements
    return replace(state, holes=tuple(holes))


def _play(deck, hero_seat, public_policy, standard10, seed, invariance):
    state = ChipState.new(deck)
    rng = np.random.default_rng(seed)
    actions = []
    public_slots = []
    public_streets = []
    private_errors = []
    while not state.terminal:
        if state.actor == hero_seat:
            action, _ = legacy_decide(
                standard10, state, uniform=0.5, policy_mode="greedy"
            )
            actor = "standard10"
            slot = None
        else:
            if invariance["checked"] < invariance["target"]:
                original = strategy(public_policy, state)
                altered = strategy(public_policy, _alter_actor_holes(state))
                private_errors.append(float(np.max(np.abs(original - altered))))
                invariance["checked"] += 1
            action, metadata = decide(public_policy, state, rng)
            actor = "public_opponent"
            slot = metadata["selected_action_slot"]
            public_slots.append(slot)
            public_streets.append(state.street)
        actions.append({"actor": actor, "street": state.street, "action": action, "slot": slot})
        state = apply_incr(state, action)
    return {
        "hero_seat": hero_seat,
        "hero_reward_bb": state.payoffs()[hero_seat] / 100.0,
        "actions": actions,
        "public_slots": public_slots,
        "public_streets": public_streets,
        "private_errors": private_errors,
    }


def _cohort(path, decks, public_policy, standard10, seed):
    slots = []
    streets = []
    errors = []
    rewards = []
    invariance = {"checked": 0, "target": 256}
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for pair_index, deck in enumerate(decks):
            hands = []
            for seat in range(2):
                hand = _play(
                    deck, seat, public_policy, standard10,
                    seed + pair_index * 10 + seat, invariance,
                )
                hands.append(hand)
                slots.extend(hand.pop("public_slots"))
                streets.extend(hand.pop("public_streets"))
                errors.extend(hand.pop("private_errors"))
                rewards.append(hand["hero_reward_bb"])
            stream.write(json.dumps({
                "pair_index": pair_index, "deck": deck, "hands": hands,
            }, separators=(",", ":")) + "\n")
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "hands": 2 * len(decks),
        "public_decisions": len(slots),
        "slot_counts": np.bincount(slots, minlength=9).tolist(),
        "street_counts": np.bincount(streets, minlength=4).tolist(),
        "private_invariance_states": len(errors),
        "max_private_invariance_error": max(errors, default=0.0),
        "standard10_bb100": 100.0 * float(np.mean(rewards)),
    }


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    public_policy = load_public_opponent(args.opponent_model)
    standard10 = load_policy(args.standard10, "cpu")
    if public_policy.sha256 != EXPECTED_OPPONENT_SHA:
        raise ValueError(f"public opponent hash mismatch: {public_policy.sha256}")
    if standard10.sha256 != EXPECTED_STANDARD10_SHA:
        raise ValueError(f"Standard10 hash mismatch: {standard10.sha256}")
    deck_rng = np.random.default_rng(args.seed + 1_000_000)
    decks = [deck_rng.permutation(52).tolist() for _ in range(args.pairs)]
    first = _cohort(
        args.output_dir / "cohort_a.jsonl", decks, public_policy, standard10, args.seed
    )
    second = _cohort(
        args.output_dir / "cohort_b.jsonl", decks, public_policy, standard10, args.seed
    )
    gates = {
        "logical_trajectory_replay_exact": first["sha256"] == second["sha256"],
        "private_hole_invariance_exact": (
            first["private_invariance_states"] == 256
            and second["private_invariance_states"] == 256
            and first["max_private_invariance_error"] == 0.0
            and second["max_private_invariance_error"] == 0.0
        ),
        "every_street_covered": all(count > 0 for count in first["street_counts"]),
        "fold_call_and_raise_covered": (
            first["slot_counts"][0] > 0
            and first["slot_counts"][1] > 0
            and sum(first["slot_counts"][2:]) > 0
        ),
        "at_least_four_raise_slots_covered": sum(
            count > 0 for count in first["slot_counts"][2:]
        ) >= 4,
        "decision_accounting_replays": first["public_decisions"] == second["public_decisions"],
    }
    result = {
        "schema_version": 1,
        "config": {"pairs": args.pairs, "seed": args.seed},
        "source": {
            "public_opponent": str(args.opponent_model),
            "public_opponent_sha256": public_policy.sha256,
            "standard10": str(args.standard10),
            "standard10_sha256": standard10.sha256,
        },
        "accounting": {
            "environment_training_hands": 0,
            "evaluation_hands": first["hands"] + second["hands"],
            "unique_deal_hands": first["hands"],
            "replay_duplicate_hands": second["hands"],
        },
        "cohorts": {"a": first, "b": second},
        "gates": gates,
        "elapsed_seconds": time.time() - started,
    }
    result["admit_worker_integration_smoke"] = all(gates.values())
    result["decision"] = (
        "ADMIT_PUBLIC_OPPONENT_WORKER_INTEGRATION"
        if result["admit_worker_integration_smoke"]
        else "REJECT_PUBLIC_OPPONENT_EXECUTION_CONTRACT"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opponent-model", type=Path, required=True)
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=60915)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
