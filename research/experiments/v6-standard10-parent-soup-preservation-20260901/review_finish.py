"""Independent raw-state terminal review and experiment closure."""
import json
from pathlib import Path
import statistics
import subprocess
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    analysis, execution = read(BASE / "analysis.json"), read(BASE / "execution.json")
    rows = [json.loads(line) for line in (BASE / "state_metrics.jsonl").read_text().splitlines()]
    mean_tv = statistics.mean(row["total_variation"] for row in rows)
    disagreement = statistics.mean(row["greedy_disagreement"] for row in rows)
    assert len(rows) == analysis["states"] == 14963
    assert abs(mean_tv - analysis["mean_total_variation"]) < 1e-12
    assert abs(disagreement - analysis["greedy_disagreement_rate"]) < 1e-12
    assert sha256_file(BASE / "frozen/candidate.pt") == analysis["candidate_sha256"]
    passed = mean_tv <= 0.02 and disagreement <= 0.02
    assert passed == analysis["gate_passed"]
    decision = "ADMIT_SEPARATE_GREEDY_FRESH5K" if passed else "CONSERVATIVE_SOUP_PRESERVATION_NOT_PASSED"
    assert decision == analysis["decision"]
    review = {"status": "PASS", "decision": decision, "states": len(rows), "mean_total_variation": mean_tv,
              "greedy_disagreement_rate": disagreement, "candidate_sha256": analysis["candidate_sha256"],
              "state_metrics_sha256": sha256_file(BASE / "state_metrics.jsonl")}
    atomic_json(BASE / "reviewed_analysis.json", review)
    summary = f"Fixed 75/25 parent-Standard10 actor soup replayed {len(rows)} audited parent states: TV={mean_tv:.6f}, greedy disagreement={disagreement:.3%}; independent review PASS."
    conclusion = ("The single preregistered conservative actor soup passed the outcome-free parent-preservation gate."
                  if passed else "The single preregistered conservative actor soup failed the outcome-free parent-preservation gate.")
    next_step = ("Run one separately logged exact-checkpoint generic-greedy fresh5k Slumbot gate; do not claim strength from preservation."
                 if passed else "Do not spend Slumbot hands or search interpolation weights; retain the raw parent.")
    subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "finish", BASE.name, "--status", "COMPLETED",
                    "--count", "new_training_hands=0", "--count", f"evaluation_hands={2 * len(rows)}", "--count", "slumbot_hands=0",
                    "--metric", f"wall_time_seconds={execution['wall_time_seconds']}", "--metric", f"parent_state_tv={mean_tv}",
                    "--metric", f"parent_state_greedy_disagreement={disagreement}", "--artifact", str(BASE / "reviewed_analysis.json"),
                    "--summary", summary, "--conclusion", conclusion, "--decision", decision, "--next-step", next_step,
                    "--note", "Independent reviewer recomputed both preservation metrics from all raw state rows and verified candidate SHA256; no outcomes, network calls, training, or new Slumbot hands."], cwd=ROOT, check=True)
    print(json.dumps(review, sort_keys=True))


if __name__ == "__main__": main()
