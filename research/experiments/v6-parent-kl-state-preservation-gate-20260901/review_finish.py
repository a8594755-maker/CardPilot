"""Independent aggregation and identity review of preservation-gate states."""
from collections import defaultdict
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file


BASE = Path(__file__).resolve().parent


def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def close(a, b): return abs(float(a) - float(b)) < 1e-12


def aggregate(rows):
    n = len(rows)
    return {"states": n, "total_variation": math.fsum(row["total_variation"] for row in rows) / n,
            "greedy_disagreement_rate": math.fsum(row["greedy_disagreement"] for row in rows) / n,
            "kl_raw_source": math.fsum(row["kl_raw_source"] for row in rows) / n,
            "kl_source_raw": math.fsum(row["kl_source_raw"] for row in rows) / n}


def review():
    analysis = load(BASE / "analysis.json")
    execution = load(BASE / "execution.json")
    inputs = load(BASE / "input_manifest.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and execution["network_calls"] == 0
    assert sha256_file(Path(inputs["candidate_checkpoint"]["path"])) == inputs["candidate_checkpoint"]["sha256"]
    assert sha256_file(Path(inputs["parent_checkpoint"]["path"])) == inputs["parent_checkpoint"]["sha256"]
    for item in inputs["hands"]: assert sha256_file(Path(item["path"])) == item["sha256"]
    rows = [json.loads(line) for line in (BASE / "state_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 14963 == analysis["states"]
    assert len({(row["session"], row["hand"], row["decision"]) for row in rows}) == len(rows)
    groups = defaultdict(list)
    for row in rows:
        assert set(row).isdisjoint({"winnings_chips", "winnings_bb", "reward", "outcome"})
        assert close(math.fsum(row["raw_probs"]), 1) and close(math.fsum(row["source_probs"]), 1)
        assert close(0.5 * math.fsum(abs(a - b) for a, b in zip(row["raw_probs"], row["source_probs"])), row["total_variation"])
        groups[f"street{row['street']}_seat{row['seat']}"] .append(row)
    overall = aggregate(rows)
    for key, value in overall.items(): assert close(value, analysis["overall"][key])
    partitions = {}
    for key, values in groups.items():
        current = aggregate(values)
        partitions[key] = current
        for metric, value in current.items(): assert close(value, analysis["partitions"][key][metric])
    supported = [value for value in partitions.values() if value["states"] >= 100]
    passed = overall["total_variation"] <= 0.01 and overall["greedy_disagreement_rate"] <= 0.01 and all(value["total_variation"] <= 0.025 and value["greedy_disagreement_rate"] <= 0.05 for value in supported)
    assert passed and analysis["decision"] == "ADMIT_INDEPENDENT_GREEDY_FRESH5K"
    return {"status": "PASS", "decision": analysis["decision"], "states": len(rows),
            "overall": overall, "max_partition_tv": max(value["total_variation"] for value in supported),
            "max_partition_greedy_disagreement": max(value["greedy_disagreement_rate"] for value in supported),
            "network_calls": 0, "evaluation_hands": 2 * len(rows), "slumbot_hands": 0,
            "outcomes_used": False, "goal_achieved": False}


def main():
    result = review()
    atomic_json(BASE / "reviewed_analysis.json", result)
    (BASE / "result_summary.md").write_text(
        "# Parent-KL outcome-free state-preservation result\n\n"
        f"Decision: `{result['decision']}` across {result['states']:,} audited parent-policy decision states. Overall candidate-parent TV was {result['overall']['total_variation']:.6f}, greedy disagreement {result['overall']['greedy_disagreement_rate']:.3%}; maximum supported partition TV was {result['max_partition_tv']:.6f} and disagreement {result['max_partition_greedy_disagreement']:.3%}. All preregistered preservation thresholds passed. The preregistration's 15,056 count came from the separate sampled cohort; the raw generic-greedy corpus contains 14,963 decisions and no rows were added or removed. No outcomes, network calls, or new Slumbot hands were used. This is preservation, not strength evidence; Goal not achieved.\n",
        encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()
