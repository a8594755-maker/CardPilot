"""Independent terminal arithmetic, identity, accounting, and gate review."""
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return sha256_file(Path(path))


def estimate(values):
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return {"n": len(values), "bb_per_100": mean, "standard_error": se,
            "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def close_enough(left, right, tol=1e-10):
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(close_enough(left[key], right[key], tol) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(close_enough(a, b, tol) for a, b in zip(left, right))
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tol
    return left == right


def main():
    analysis = read(BASE / "completed_analysis.json")
    execution = read(BASE / "recovery_execution.json")
    population = read(BASE / "population_manifest.json")
    candidates = read(BASE / "candidate_manifest.json")
    audit = read(BASE / "production/train/resume_session_audit.json")
    assert analysis["status"] == execution["status"] == "COMPLETED_PENDING_REVIEW"
    assert audit["status"] == "PASS" and analysis["slumbot_hands"] == 0
    assert len(population["members"]) == 10 and len({row["seed"] for row in population["members"]}) == 10
    assert {row["role"] for row in population["members"]} == {"train", "eval"}
    for row in population["members"]:
        assert sha(row["path"]) == row["sha256"]
    for row in candidates.values():
        assert sha(row["path"]) == row["sha256"]

    eval_members = [row for row in population["members"] if row["role"] == "eval"]
    values = {}
    decks = None
    for label, candidate in candidates.items():
        for anchor in eval_members:
            out = BASE / "matrix" / f"{label}_anchor{anchor['index']}"
            summary = read(out / "summary.json")
            assert summary["candidate_sha256"] == candidate["sha256"]
            assert summary["anchor_sha256"] == anchor["sha256"]
            assert summary["policy_mode"] == "greedy" and summary["pairs"] == 1024
            assert summary["pairs_sha256"] == sha(out / "pairs.jsonl")
            rows = [json.loads(line) for line in (out / "pairs.jsonl").read_text().splitlines()]
            assert [row["pair_index"] for row in rows] == list(range(1024))
            current = [row["deck"] for row in rows]
            if decks is None:
                decks = current
            assert current == decks
            values[label, anchor["index"]] = [sum(row["rewards_bb"]) * 50 for row in rows]
    contrasts = [{"anchor": index, **estimate([
        candidate - parent for candidate, parent in zip(values["candidate", index], values["parent", index])
    ])} for index in range(5)]
    aggregate = estimate([
        statistics.mean(values["candidate", index][pair] - values["parent", index][pair] for index in range(5))
        for pair in range(1024)
    ])
    assert close_enough(contrasts, analysis["per_anchor_contrasts"])
    assert close_enough(aggregate, analysis["aggregate_contrast"])

    state_rows = [json.loads(line) for line in (BASE / "parent_state_metrics.jsonl").read_text().splitlines()]
    preservation = analysis["preservation"]
    assert len(state_rows) == preservation["states"]
    mean_tv = statistics.mean(row["total_variation"] for row in state_rows)
    disagreement = statistics.mean(row["greedy_disagreement"] for row in state_rows)
    assert abs(mean_tv - preservation["mean_total_variation"]) < 1e-12
    assert abs(disagreement - preservation["greedy_disagreement_rate"]) < 1e-12
    preserve_pass = mean_tv <= 0.02 and disagreement <= 0.02
    passed = aggregate["ci95"][0] > 0 and sum(row["bb_per_100"] > 0 for row in contrasts) >= 4 and preserve_pass
    assert passed == analysis["gate_passed"]
    expected_decision = "ADMIT_SEPARATE_GREEDY_FRESH5K" if passed else "WEIGHT_POPULATION_SMOKE_NOT_PROMISING"
    assert analysis["decision"] == expected_decision
    matrix_hands = 2 * 2 * 5 * 1024
    assert analysis["evaluation_hands"] == matrix_hands + 2 * len(state_rows)
    review = {"status": "PASS", "decision": expected_decision,
              "candidate_sha256": candidates["candidate"]["sha256"],
              "new_training_hands": analysis["new_training_hands"],
              "lineage_environment_hands": analysis["lineage_environment_hands"],
              "evaluation_hands": analysis["evaluation_hands"], "slumbot_hands": 0,
              "aggregate_contrast": aggregate, "positive_anchors": sum(row["bb_per_100"] > 0 for row in contrasts),
              "mean_parent_state_tv": mean_tv, "parent_state_greedy_disagreement": disagreement,
              "reviewed_artifacts": {str(path.relative_to(ROOT)): sha(path) for path in (
                  BASE / "completed_analysis.json", BASE / "recovery_execution.json", BASE / "population_manifest.json",
                  BASE / "candidate_manifest.json", BASE / "parent_state_metrics.jsonl",
                  BASE / "production/train/resume_session_audit.json")}}
    atomic_json(BASE / "reviewed_analysis.json", review)
    summary = (f"Completed {analysis['new_training_hands']} new physical training hands and "
               f"{analysis['evaluation_hands']} offline evaluation hands; untouched-population candidate-minus-parent "
               f"was {aggregate['bb_per_100']:+.4f} bb/100 with CI[{aggregate['ci95'][0]:+.4f},{aggregate['ci95'][1]:+.4f}], "
               f"{review['positive_anchors']}/5 positive anchors; parent-state TV={mean_tv:.6f}, disagreement={disagreement:.6f}.")
    conclusion = ("The frozen seed-separated Standard10 weight population passed all evidence and preservation gates."
                  if passed else
                  "The frozen seed-separated Standard10 weight population did not pass the preregistered joint transfer-proxy and preservation gate.")
    next_step = ("Run one separately logged fresh5k generic-greedy Slumbot transfer gate on the exact frozen candidate."
                 if passed else
                 "Do not spend Slumbot hands or scale this weight-population route; choose a materially different self-play or opponent-generation mechanism.")
    command = [sys.executable, str(ROOT / "research/experiment_log.py"), "finish", BASE.name,
               "--status", "COMPLETED", "--count", f"new_training_hands={analysis['new_training_hands']}",
               "--count", f"lineage_training_hands={analysis['lineage_environment_hands']}",
               "--count", f"evaluation_hands={analysis['evaluation_hands']}", "--count", "slumbot_hands=0",
               "--metric", f"wall_time_seconds={execution['wall_time_seconds']}",
               "--metric", f"aggregate_delta_bb100={aggregate['bb_per_100']}",
               "--metric", f"aggregate_delta_ci_low={aggregate['ci95'][0]}",
               "--metric", f"parent_state_tv={mean_tv}", "--metric", f"parent_state_greedy_disagreement={disagreement}",
               "--artifact", str(BASE / "reviewed_analysis.json"), "--summary", summary,
               "--conclusion", conclusion, "--decision", expected_decision, "--next-step", next_step,
               "--note", "Independent reviewer regenerated every matrix contrast from raw pairs, recomputed state preservation from raw JSONL, and verified checkpoint hashes, seed separation, session audit, accounting, and the fixed gate."]
    subprocess.run(command, cwd=ROOT, check=True)
    print(json.dumps(review, sort_keys=True))


if __name__ == "__main__":
    main()
