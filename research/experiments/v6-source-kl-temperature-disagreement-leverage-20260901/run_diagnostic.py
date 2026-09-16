"""Outcome-blind leverage profile of treatment-versus-Standard10 argmax flips."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-source-kl-temperature-65k-greedy-fresh5k-slumbot-20260901"
DRIFT = ROOT / "research/experiments/v6-source-kl-temperature-slumbot-state-drift-20260901"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, sha256_file  # noqa: E402
from alpha_holdem.policy_contract_v6 import action_table, from_external  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    atomic_json(Path(path), value)


def log(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def action_class(slot):
    if slot == 0:
        return "fold"
    if slot == 1:
        return "passive"
    if slot == 8:
        return "all_in"
    return "fractional_raise"


def aggregate(rows):
    total = len(rows)
    disagreements = [row for row in rows if row["greedy_disagreement"]]
    pot_total = math.fsum(row["pot_bb"] for row in rows)
    return {
        "states": total,
        "disagreements": len(disagreements),
        "greedy_disagreement_rate": len(disagreements) / total,
        "pot_weighted_disagreement_rate": (
            math.fsum(row["pot_bb"] for row in disagreements) / pot_total
            if pot_total else 0.0
        ),
        "mean_pot_bb_all": math.fsum(row["pot_bb"] for row in rows) / total,
        "mean_pot_bb_disagreements": (
            math.fsum(row["pot_bb"] for row in disagreements) / len(disagreements)
            if disagreements else 0.0
        ),
        "mean_to_call_bb_disagreements": (
            math.fsum(row["to_call_bb"] for row in disagreements) / len(disagreements)
            if disagreements else 0.0
        ),
        "fold_involved": sum(
            row["raw_greedy"] == 0 or row["source_greedy"] == 0 for row in disagreements
        ),
        "all_in_involved": sum(
            row["raw_greedy"] == 8 or row["source_greedy"] == 8 for row in disagreements
        ),
    }


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "leverage_rows.jsonl", "analysis.json")):
        raise ValueError("No restart")
    assert read(PARENT / "reviewed_analysis.json")["status"] == "PASS"
    assert read(DRIFT / "reviewed_analysis.json")["status"] == "PASS"
    drift_path = DRIFT / "state_metrics.jsonl"
    started = time.monotonic()
    write(BASE / "execution.json", {
        "status": "RUNNING",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "network_calls": 0,
        "new_training_hands": 0,
        "evaluation_hands": 0,
        "slumbot_hands": 0,
    })
    drift_rows = [json.loads(line) for line in drift_path.read_text(encoding="utf-8").splitlines()]
    by_key = {(row["session"], row["hand"], row["decision"]): row for row in drift_rows}
    assert len(by_key) == len(drift_rows) == 15078
    output_rows = []
    with (BASE / "leverage_rows.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for session in range(1, 9):
            hands_path = PARENT / "sessions" / f"s{session:02d}/hands.jsonl"
            for hand_index, line in enumerate(hands_path.read_text(encoding="utf-8").splitlines(), 1):
                hand = json.loads(line)
                for decision_index, decision in enumerate(hand["decisions"]):
                    key = (session, hand_index, decision_index)
                    drift = by_key.pop(key)
                    response = decision["response"]
                    state = from_external(
                        response["action"],
                        response["hole_cards"],
                        response.get("board", []),
                        response["client_pos"],
                    )
                    _, table = action_table(state)
                    raw_slot = int(drift["raw_greedy"])
                    source_slot = int(drift["source_greedy"])
                    row = {
                        "session": session,
                        "hand": hand_index,
                        "decision": decision_index,
                        "street": int(state.street),
                        "seat": int(state.actor),
                        "pot_bb": state.pot / 100.0,
                        "to_call_bb": state.to_call / 100.0,
                        "actor_stack_bb": state.stacks[state.actor] / 100.0,
                        "opponent_stack_bb": state.stacks[1 - state.actor] / 100.0,
                        "contestable_pot_if_all_in_bb": (
                            state.pot + 2 * min(state.stacks)
                        ) / 100.0,
                        "raw_greedy": raw_slot,
                        "source_greedy": source_slot,
                        "raw_action": table[raw_slot],
                        "source_action": table[source_slot],
                        "raw_action_class": action_class(raw_slot),
                        "source_action_class": action_class(source_slot),
                        "greedy_disagreement": int(raw_slot != source_slot),
                        "total_variation": float(drift["total_variation"]),
                    }
                    assert row["raw_action"] is not None and row["source_action"] is not None
                    output_rows.append(row)
                    output.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    assert not by_key and len(output_rows) == 15078
    pots = np.asarray([row["pot_bb"] for row in output_rows], dtype=np.float64)
    thresholds = {str(q): float(np.quantile(pots, q)) for q in (0.5, 0.75, 0.9, 0.95, 0.99)}
    tail_rates = {}
    for quantile, threshold in thresholds.items():
        selected = [row for row in output_rows if row["pot_bb"] >= threshold]
        tail_rates[quantile] = aggregate(selected)
    partitions = defaultdict(list)
    for row in output_rows:
        partitions[f"street{row['street']}_seat{row['seat']}"] .append(row)
    transitions = Counter(
        f"{row['source_greedy']}->{row['raw_greedy']}"
        for row in output_rows
        if row["greedy_disagreement"]
    )
    class_transitions = Counter(
        f"{row['source_action_class']}->{row['raw_action_class']}"
        for row in output_rows
        if row["greedy_disagreement"]
    )
    overall = aggregate(output_rows)
    analysis = {
        "status": "COMPLETED_PENDING_REVIEW",
        "decision": "HIGH_LEVERAGE_FLIPS_IDENTIFIED" if (
            overall["pot_weighted_disagreement_rate"] >= 2 * overall["greedy_disagreement_rate"]
            or overall["fold_involved"] + overall["all_in_involved"] >= overall["disagreements"] / 2
        ) else "NO_HIGH_LEVERAGE_FLIP_CONCENTRATION",
        "overall": overall,
        "pot_quantile_thresholds_bb": thresholds,
        "pot_tail_metrics": tail_rates,
        "partitions": {key: aggregate(value) for key, value in sorted(partitions.items())},
        "slot_transitions": dict(transitions.most_common()),
        "class_transitions": dict(class_transitions.most_common()),
        "states": len(output_rows),
        "network_calls": 0,
        "new_training_hands": 0,
        "evaluation_hands": 0,
        "slumbot_hands": 0,
        "goal_achieved": False,
        "outcomes_used": False,
    }
    write(BASE / "input_manifest.json", {
        "drift_rows": str(drift_path),
        "drift_rows_sha256": sha256_file(drift_path),
        "parent_audit": str(PARENT / "combined_audit.json"),
        "parent_audit_sha256": sha256_file(PARENT / "combined_audit.json"),
    })
    write(BASE / "analysis.json", analysis)
    elapsed = time.monotonic() - started
    write(BASE / "execution.json", {
        "status": "COMPLETED_PENDING_REVIEW",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "wall_time_seconds": elapsed,
        "network_calls": 0,
        "new_training_hands": 0,
        "evaluation_hands": 0,
        "slumbot_hands": 0,
    })
    log(
        "--artifact", BASE / "leverage_rows.jsonl",
        "--artifact", BASE / "analysis.json",
        "--artifact", BASE / "input_manifest.json",
        "--count", "new_training_hands=0",
        "--count", "evaluation_hands=0",
        "--count", "slumbot_hands=0",
        "--metric", f"wall_time_seconds={elapsed}",
    )
    print(json.dumps({
        "decision": analysis["decision"],
        "overall": overall,
        "top_transitions": transitions.most_common(5),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
