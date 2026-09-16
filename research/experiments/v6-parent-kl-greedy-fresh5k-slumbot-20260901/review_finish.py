"""Independent raw/evidence review for parent-KL fresh5k."""
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
STATS_DIR = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
sys.path[:0] = [str(STATS_DIR), str(ROOT)]
from pilot_stats import summarize
from research.experiment_log import atomic_json, sha256_file

MODEL_SHA = "1c050edb088eaaf4bdc653a7b7b4708191854a7ca216f913ca2b7c1c6cd412c4"


def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def review():
    execution, analysis, audit = load(BASE / "execution.json"), load(BASE / "completed_analysis.json"), load(BASE / "combined_audit.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and execution["slumbot_hands"] == 5000
    assert sha256_file(BASE / "frozen/final.pt") == MODEL_SHA
    assert audit["status"] == "PASS" and audit["successful_hands"] == 5000 and audit["model_sha256"] == MODEL_SHA and audit["token_chains_disjoint"]
    sessions = []
    for index in range(1, 9):
        rows = [json.loads(line) for line in (BASE / "sessions" / f"s{index:02d}/hands.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 625 and [row["successful_hand"] for row in rows] == list(range(1, 626))
        assert all(row["session_id"] == f"v6_parent_kl_greedy_fresh5k_20260901_s{index:02d}" and row["policy_seed"] == 2026110300 + index for row in rows)
        assert all(row["model_sha256"] == MODEL_SHA and row["policy_mode"] == "greedy" and row["policy_temperature"] == 0 for row in rows)
        for row in rows:
            assert row["terminal_validation"]["status"] == "PASS"
            assert all(decision["selected_action_slot"] == decision["greedy_action_slot"] and decision["behavior_probs"] == [float(slot == decision["selected_action_slot"]) for slot in range(9)] for decision in row["decisions"])
        sessions.append([row["winnings_chips"] for row in rows])
    statistics = summarize(sessions)
    assert statistics == analysis["statistics"]
    new_tokens = {token for row in audit["results"] for token in row["token_sha256"]}
    old_tokens = set()
    for path in sorted((ROOT / "research/experiments").glob("*/*combined_audit.json")):
        if BASE in path.parents: continue
        try: report = load(path)
        except (OSError, UnicodeError, json.JSONDecodeError): continue
        if report.get("status") == "PASS": old_tokens.update(token for row in report.get("results", []) for token in row.get("token_sha256", []))
    assert not new_tokens.intersection(old_tokens)
    admitted = statistics["bb_per_100"] > 0 and statistics["positive_sessions"] >= 4
    decision = "ADMIT_SEPARATE_FRESH20K" if admitted else "FRESH5K_TRANSFER_GATE_NOT_PASSED"
    assert decision == analysis["decision"]
    return {"status": "PASS", "decision": decision, "model_sha256": MODEL_SHA, "statistics": statistics,
            "prior_token_hashes_checked": len(old_tokens), "slumbot_hands": 5000, "goal_achieved": False}


def main():
    result = review()
    atomic_json(BASE / "reviewed_analysis.json", result)
    s = result["statistics"]
    (BASE / "result_summary.md").write_text(
        "# Parent-KL generic-greedy fresh5k result\n\n"
        f"Decision: `{result['decision']}`. Frozen candidate scored {s['bb_per_100']:+.6f} bb/100; raw-hand 95% CI [{s['raw_hand_ci95'][0]:+.6f}, {s['raw_hand_ci95'][1]:+.6f}], session-t7 CI [{s['session_t7_ci95'][0]:+.6f}, {s['session_t7_ci95'][1]:+.6f}], positive sessions {s['positive_sessions']}/8. All raw hands, model decisions, terminal counters, and token chains passed audit and independent recomputation. No fresh20k is admitted; pilot hands are not qualification hands. Goal not achieved.\n",
        encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()

