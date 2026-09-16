"""Independent raw-hand/evidence review for tail generic-greedy fresh5k."""
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
STATS_DIR = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
sys.path[:0] = [str(STATS_DIR), str(ROOT)]
from pilot_stats import summarize
from research.experiment_log import atomic_json, sha256_file

MODEL_SHA = "6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def review():
    execution = read(BASE / "execution.json")
    analysis = read(BASE / "completed_analysis.json")
    audit = read(BASE / "combined_audit.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW"
    assert execution["evaluation_hands"] == execution["slumbot_hands"] == 5000
    assert sha256_file(BASE / "frozen/final.pt") == MODEL_SHA
    assert audit["status"] == "PASS" and audit["successful_hands"] == 5000
    assert audit["model_sha256"] == MODEL_SHA and audit["token_chains_disjoint"]
    sessions = []
    for index in range(1, 9):
        rows = [json.loads(line) for line in (BASE / "sessions" / f"s{index:02d}/hands.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 625 and [row["successful_hand"] for row in rows] == list(range(1, 626))
        assert all(row["session_id"] == f"v6_actor_tail_greedy_fresh5k_20260901_s{index:02d}" for row in rows)
        assert all(row["model_sha256"] == MODEL_SHA and row["strict_policy_execution"] for row in rows)
        assert all(row["policy_mode"] == "greedy" and row["policy_temperature"] == 0 and row["policy_seed"] == 2026110200 + index for row in rows)
        for row in rows:
            assert row["terminal_validation"]["status"] == "PASS"
            for decision in row["decisions"]:
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_probs"] == [float(slot == decision["selected_action_slot"]) for slot in range(9)]
        sessions.append([row["winnings_chips"] for row in rows])
    statistics = summarize(sessions)
    assert statistics == analysis["statistics"]
    new_tokens = {token for row in audit["results"] for token in row["token_sha256"]}
    old_tokens = set()
    audits = 0
    for path in sorted((ROOT / "research/experiments").glob("*/*combined_audit.json")):
        if BASE in path.parents:
            continue
        try:
            report = read(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if report.get("status") != "PASS":
            continue
        audits += 1
        old_tokens.update(token for row in report.get("results", []) for token in row.get("token_sha256", []))
    assert not new_tokens.intersection(old_tokens)
    admitted = statistics["bb_per_100"] > 0 and statistics["positive_sessions"] >= 4
    decision = "ADMIT_SEPARATE_FRESH20K" if admitted else "FRESH5K_TRANSFER_GATE_NOT_PASSED"
    assert decision == analysis["decision"] and not analysis["goal_achieved"]
    return {"status": "PASS", "decision": decision, "model_sha256": MODEL_SHA,
            "statistics": statistics, "prior_audits_checked": audits,
            "prior_token_hashes_checked": len(old_tokens), "slumbot_hands": 5000,
            "goal_achieved": False}


def main():
    reviewed = review()
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    statistics = reviewed["statistics"]
    raw_ci, session_ci = statistics["raw_hand_ci95"], statistics["session_t7_ci95"]
    (BASE / "result_summary.md").write_text(
        "# Low-LR actor tail generic-greedy fresh5k result\n\n"
        f"Decision: `{reviewed['decision']}`. Frozen tail: {statistics['bb_per_100']:+.6f} bb/100; "
        f"raw-hand 95% CI [{raw_ci[0]:+.6f}, {raw_ci[1]:+.6f}], session-t7 CI "
        f"[{session_ci[0]:+.6f}, {session_ci[1]:+.6f}], positive sessions "
        f"{statistics['positive_sessions']}/8. All 5,000 raw hands and every learned-logit "
        "greedy decision passed full replay audit; token chains were disjoint from prior passing "
        "cohorts. The internal convergence gain did not transfer, so no fresh20k is admitted. "
        "These are pilot, not qualification, hands; Goal not achieved.\n",
        encoding="utf-8")
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__":
    main()

