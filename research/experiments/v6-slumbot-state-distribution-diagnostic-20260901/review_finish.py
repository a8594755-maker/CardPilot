"""Independent aggregation review of per-state policy-distribution evidence."""
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def aggregate(rows):
    n = len(rows)
    return {
        "states": n,
        "greedy_disagreement_rate": math.fsum(row["greedy_disagreement"] for row in rows) / n,
        "total_variation": math.fsum(row["total_variation"] for row in rows) / n,
        "kl_raw_source": math.fsum(row["kl_raw_source"] for row in rows) / n,
        "kl_source_raw": math.fsum(row["kl_source_raw"] for row in rows) / n,
    }


def close(left, right): return abs(float(left) - float(right)) < 1e-12


def main():
    analysis = read(BASE / "analysis.json")
    execution = read(BASE / "execution.json")
    inputs = read(BASE / "input_manifest.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and execution["network_calls"] == 0
    assert sha256_file(Path(inputs["raw_checkpoint"]["path"])) == inputs["raw_checkpoint"]["sha256"]
    assert sha256_file(Path(inputs["source_checkpoint"]["path"])) == inputs["source_checkpoint"]["sha256"]
    for row in inputs["hands"]: assert sha256_file(Path(row["path"])) == row["sha256"]
    rows = [json.loads(line) for line in (BASE / "state_metrics.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == analysis["states"] and execution["evaluation_hands"] == 2 * len(rows)
    assert len({(row["session"], row["hand"], row["decision"]) for row in rows}) == len(rows)
    groups = defaultdict(list)
    for row in rows:
        assert set(row).isdisjoint({"winnings_chips", "winnings_bb", "outcome", "reward"})
        raw, source = row["raw_probs"], row["source_probs"]
        assert len(raw) == len(source) == 9
        assert close(math.fsum(raw), 1) and close(math.fsum(source), 1)
        assert all(value >= 0 and math.isfinite(value) for value in raw + source)
        tv = 0.5 * math.fsum(abs(left - right) for left, right in zip(raw, source))
        assert close(tv, row["total_variation"])
        assert row["greedy_disagreement"] == int(row["raw_greedy"] != row["source_greedy"])
        groups[f"street{row['street']}_seat{row['seat']}"] .append(row)
    overall = aggregate(rows)
    for key, value in overall.items(): assert close(value, analysis["overall"][key])
    supported = {}
    for key, values in groups.items():
        current = aggregate(values)
        for metric, value in current.items(): assert close(value, analysis["partitions"][key][metric])
        if len(values) >= 100: supported[key] = current
    largest_key, largest = max(supported.items(), key=lambda item: item[1]["total_variation"])
    assert largest_key == analysis["largest_supported_tv_partition"]
    informative = any(value["greedy_disagreement_rate"] > 0.25 or value["total_variation"] > 0.10 for value in supported.values())
    decision = "CONCENTRATED_POLICY_DRIFT_IDENTIFIED" if informative else "NO_CONCENTRATED_POLICY_DRIFT"
    assert decision == analysis["decision"] and analysis["slumbot_hands"] == 0 and not analysis["goal_achieved"]
    partition = analysis["partitions"][largest_key]
    deltas = partition["raw_minus_source_slot_probabilities"]
    top_increase = max(range(9), key=lambda slot: deltas[slot])
    top_decrease = min(range(9), key=lambda slot: deltas[slot])
    reviewed = {"status": "PASS", "decision": decision, "states": len(rows),
                "overall": overall, "largest_supported_tv_partition": largest_key,
                "largest_supported_tv": largest["total_variation"],
                "largest_partition_greedy_disagreement": largest["greedy_disagreement_rate"],
                "largest_partition_top_probability_increase_slot": top_increase,
                "largest_partition_top_probability_increase": deltas[top_increase],
                "largest_partition_top_probability_decrease_slot": top_decrease,
                "largest_partition_top_probability_decrease": deltas[top_decrease],
                "network_calls": 0, "slumbot_hands": 0, "goal_achieved": False}
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    (BASE / "result_summary.md").write_text(
        "# Preserved Slumbot-state distribution diagnostic\n\n"
        f"Decision: `{decision}` across {len(rows):,} audited raw-policy decision states. "
        f"Overall total variation is {overall['total_variation']:.6f}, greedy disagreement "
        f"{overall['greedy_disagreement_rate']:.3%}. Largest supported partition `{largest_key}` "
        f"has TV {largest['total_variation']:.6f} and disagreement "
        f"{largest['greedy_disagreement_rate']:.3%}; its largest probability shift is slot "
        f"{top_increase} ({deltas[top_increase]:+.6f}) and largest reduction is slot "
        f"{top_decrease} ({deltas[top_decrease]:+.6f}). No outcomes were used, no network calls "
        "or new Slumbot hands occurred, and the on-policy state corpus cannot estimate "
        "counterfactual source value. Goal not achieved.\n",
        encoding="utf-8",
    )
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__": main()
