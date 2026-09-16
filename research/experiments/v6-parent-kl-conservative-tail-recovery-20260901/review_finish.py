"""Independent evidence review for the parent-KL conservative tail."""
import hashlib
import json
import math
from pathlib import Path

import torch


BASE = Path(__file__).resolve().parent
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
TAIL_SHA = "1c050edb088eaaf4bdc653a7b7b4708191854a7ca216f913ca2b7c1c6cd412c4"
PAIRS = 1024


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def estimate(values):
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def review():
    execution = load(BASE / "execution.json")
    analysis = load(BASE / "analysis.json")
    audit = load(BASE / "production/train/session_audit.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW"
    assert execution["children"][-1]["exit_code"] == 0 and audit["status"] == "PASS"
    assert sha(BASE / "frozen/parent_raw.pt") == PARENT_SHA
    assert sha(BASE / "frozen/tail_raw.pt") == TAIL_SHA
    parent = torch.load(BASE / "frozen/parent_raw.pt", map_location="cpu", weights_only=False)
    tail = torch.load(BASE / "frozen/tail_raw.pt", map_location="cpu", weights_only=False)
    assert parent["iteration"] == 27 and tail["iteration"] == 40
    assert parent["environment_hand_accounting"]["completed_hands"] == 132553
    assert tail["environment_hand_accounting"]["completed_hands"] == 197617
    assert tail["environment_hand_accounting"]["prefix_complete"] is True
    assert tail["config"]["source_policy_kl_coef"] == 0.1
    assert Path(tail["config"]["source_policy_reference_checkpoint"]).name == "parent_raw.pt"
    assert tail["actor_ema_updates"] == tail["iteration"]
    assert len(parent["optimizer"]["state"]) == len(tail["optimizer"]["state"]) == 10
    assert math.isclose(parent["optimizer"]["param_groups"][0]["lr"], tail["optimizer"]["param_groups"][0]["lr"], rel_tol=0, abs_tol=1e-15)
    rows = [json.loads(line) for line in (BASE / "production/train/h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert [row["iteration"] for row in rows] == list(range(1, 41))
    assert rows[26]["environment_hand_accounting"]["completed_hands"] == 132553
    assert rows[-1]["environment_hand_accounting"]["completed_hands"] == 197617
    assert rows[-1]["reference_policy_kl"] < 0.002

    values = {}
    decks = None
    for candidate in ("source", "parent", "tail"):
        for anchor in range(5):
            directory = BASE / "matrix" / f"{candidate}_anchor{anchor}"
            assert load(directory / "summary.json")["policy_mode"] == "greedy"
            pairs = [json.loads(line) for line in (directory / "pairs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            assert len(pairs) == PAIRS
            current = [row["deck"] for row in pairs]
            if decks is None:
                decks = current
            assert current == decks
            values[candidate, anchor] = [math.fsum(row["rewards_bb"]) * 50 for row in pairs]
    by_anchor = [estimate([tail_value - parent_value for tail_value, parent_value in zip(values["tail", anchor], values["parent", anchor])]) for anchor in range(5)]
    tail_parent = estimate([math.fsum(values["tail", anchor][pair] - values["parent", anchor][pair] for anchor in range(5)) / 5 for pair in range(PAIRS)])
    tail_source = estimate([math.fsum(values["tail", anchor][pair] - values["source", anchor][pair] for anchor in range(5)) / 5 for pair in range(PAIRS)])
    positive = sum(row["mean"] > 0 for row in by_anchor)
    assert tail_parent["ci95"][0] > 0 and tail_source["mean"] > 0 and positive >= 3
    assert math.isclose(tail_parent["mean"], analysis["tail_parent"]["mean"], abs_tol=1e-12)
    return {"status": "PASS", "decision": "ADMIT_OUTCOME_FREE_PARENT_DRIFT_GATE",
            "new_training_hands": 65064, "lineage_physical_hands": 197617,
            "evaluation_hands": 30720, "slumbot_hands": 0,
            "terminal_parent_kl": rows[-1]["reference_policy_kl"],
            "tail_parent": tail_parent, "tail_source": tail_source,
            "positive_tail_parent_anchors": positive, "tail_sha256": TAIL_SHA,
            "training_matrix_is_generalization_evidence": False, "goal_achieved": False}


def main():
    result = review()
    (BASE / "reviewed_analysis.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    ci = result["tail_parent"]["ci95"]
    (BASE / "result_summary.md").write_text(
        "# Parent-KL conservative actor-tail result\n\n"
        f"Decision: `{result['decision']}`. Added 65,064 physical hands to 197,617 lineage hands while preserving Adam/LR/counters/EMA/league evidence. Terminal parent-reference KL was {result['terminal_parent_kl']:.6f}. The generic-greedy training-opponent matrix gave treatment minus parent {result['tail_parent']['mean']:+.6f} bb/100, paired 95% CI [{ci[0]:+.6f}, {ci[1]:+.6f}], with {result['positive_tail_parent_anchors']}/5 positive anchors. Audit and independent review passed. This matrix is not generalization evidence; zero Slumbot hands were used. The endpoint is admitted only to a separate outcome-free parent-drift gate. Goal not achieved.\n",
        encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

