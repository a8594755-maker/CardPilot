"""Independent read-only review of the low-LR tail evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import torch


BASE = Path(__file__).resolve().parent
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
TAIL_SHA = "6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b"
PAIRS = 2048


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def estimate(values):
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def review():
    recovery = load(BASE / "recovery_execution.json")
    prefix = load(BASE / "prefix_manifest.json")
    analysis = load(BASE / "analysis.json")
    audit = load(BASE / "production/train/session_audit.json")
    record = load(BASE / "experiment.json")
    startup_log = (BASE / "train_stdout.log").read_text(encoding="utf-8")
    startup_failure = (BASE / "failure.txt").read_text(encoding="utf-8")
    assert "--preserve-resumed-optimizer-lr requires --resume" in startup_log
    assert "--no-reset-optimizer" in startup_log
    assert "trainer failed; evidence preserved without retry" in startup_failure
    trainer_commands = [row["command"] for row in record["commands"] if "train_v5.py" in row["command"]]
    assert len(trainer_commands) >= 2
    assert "--no-reset-optimizer" not in trainer_commands[0]
    assert "--no-reset-optimizer" in trainer_commands[-1]
    assert recovery["status"] == "COMPLETED_PENDING_REVIEW"
    assert recovery["children"][-1]["exit_code"] == 0
    assert "--no-reset-optimizer" in recovery["children"][-1]["command"]
    assert audit["status"] == "PASS"
    assert sha(BASE / "frozen/parent_raw.pt") == PARENT_SHA
    assert sha(BASE / "frozen/tail_raw.pt") == TAIL_SHA
    parent = torch.load(BASE / "frozen/parent_raw.pt", map_location="cpu", weights_only=False)
    tail = torch.load(BASE / "frozen/tail_raw.pt", map_location="cpu", weights_only=False)
    assert parent["iteration"] == 27 and tail["iteration"] == 53
    assert parent["environment_hand_accounting"]["completed_hands"] == 132553
    assert tail["environment_hand_accounting"]["completed_hands"] == 263022
    assert tail["environment_hand_accounting"]["prefix_complete"] is True
    assert tail["actor_ema_updates"] == tail["iteration"]
    assert len(parent["optimizer"]["state"]) == len(tail["optimizer"]["state"]) == 10
    assert math.isclose(parent["optimizer"]["param_groups"][0]["lr"], tail["optimizer"]["param_groups"][0]["lr"], rel_tol=0, abs_tol=1e-15)
    rows = [json.loads(line) for line in (BASE / "production/train/h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["iteration"] for row in rows] == list(range(1, 54))
    assert rows[26]["environment_hand_accounting"]["completed_hands"] == 132553
    assert rows[-1]["environment_hand_accounting"]["completed_hands"] == 263022
    assert sha(BASE / "production/train/h1_training_metrics.jsonl") != prefix["metrics_sha256"]
    assert sha(BASE / "production/train/opponent_assignments.jsonl") != prefix["assignments_sha256"]

    values = {}
    decks = None
    for candidate in ("source", "parent", "tail"):
        for anchor in range(5):
            directory = BASE / "matrix" / f"{candidate}_anchor{anchor}"
            summary = load(directory / "summary.json")
            assert summary["policy_mode"] == "greedy"
            pairs = [json.loads(line) for line in (directory / "pairs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            assert len(pairs) == PAIRS and [row["pair_index"] for row in pairs] == list(range(PAIRS))
            current_decks = [row["deck"] for row in pairs]
            if decks is None:
                decks = current_decks
            assert current_decks == decks
            values[candidate, anchor] = [math.fsum(row["rewards_bb"]) * 50 for row in pairs]
    by_anchor = [estimate([tail_value - parent_value for tail_value, parent_value in zip(values["tail", anchor], values["parent", anchor])]) for anchor in range(5)]
    tail_parent = estimate([math.fsum(values["tail", anchor][pair] - values["parent", anchor][pair] for anchor in range(5)) / 5 for pair in range(PAIRS)])
    tail_source = estimate([math.fsum(values["tail", anchor][pair] - values["source", anchor][pair] for anchor in range(5)) / 5 for pair in range(PAIRS)])
    positive = sum(row["mean"] > 0 for row in by_anchor)
    assert tail_parent["mean"] > 0 and tail_parent["ci95"][0] > 0
    assert tail_source["mean"] > 0 and positive >= 3
    assert math.isclose(tail_parent["mean"], analysis["tail_parent"]["mean"], abs_tol=1e-12)
    assert math.isclose(tail_source["mean"], analysis["tail_source"]["mean"], abs_tol=1e-12)
    assert analysis["decision"] == "ADMIT_INDEPENDENT_GREEDY_FRESH5K"
    return {
        "status": "PASS",
        "decision": analysis["decision"],
        "zero_hand_startup_failure_preserved": True,
        "optimizer_continuity_verified": True,
        "physical_lineage_hands": 263022,
        "new_training_hands": 130469,
        "evaluation_hands": 61440,
        "slumbot_hands": 0,
        "tail_parent": tail_parent,
        "tail_source": tail_source,
        "positive_tail_parent_anchors": positive,
        "training_matrix_is_generalization_evidence": False,
        "tail_sha256": TAIL_SHA,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = review()
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
