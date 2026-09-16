"""Independent raw-hand/evidence review for the procedural-soup fresh5k."""

import json
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path[:0] = [str(BASE), str(ROOT)]
from pilot_stats import summarize  # noqa: E402
from research.experiment_log import atomic_json, sha256_file  # noqa: E402


MODEL_SHA = "66c2254d96e36710c1b326d17026099e6ccabdec70d8e2333cfbef26a63c4a6c"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def session_id(index):
    return f"v6_procedural_iter32_soup_greedy_fresh5k_20260901_s{index:02d}"


def main():
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
        path = BASE / "sessions" / f"s{index:02d}/hands.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 625
        assert [row["successful_hand"] for row in rows] == list(range(1, 626))
        assert all(
            row["model_sha256"] == MODEL_SHA
            and row["strict_policy_execution"]
            and row["session_id"] == session_id(index)
            and row["policy_seed"] == 2026111100 + index
            and row["policy_mode"] == "greedy"
            and row["policy_temperature"] == 0
            for row in rows
        )
        for row in rows:
            assert row["terminal_validation"]["status"] == "PASS"
            for decision in row["decisions"]:
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_action_probability"] == 1
                assert decision["behavior_probs"] == [
                    float(slot == decision["selected_action_slot"]) for slot in range(9)
                ]
        sessions.append([row["winnings_chips"] for row in rows])
    statistics = summarize(sessions)
    assert statistics == analysis["statistics"]
    new_tokens = {
        token for result in audit["results"] for token in result["token_sha256"]
    }
    old_tokens = set()
    prior_audits = 0
    for path in sorted((ROOT / "research/experiments").glob("*/*combined_audit.json")):
        if BASE in path.parents:
            continue
        try:
            report = read(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if report.get("status") != "PASS":
            continue
        prior_audits += 1
        old_tokens.update(
            token
            for result in report.get("results", [])
            for token in result.get("token_sha256", [])
        )
    assert not new_tokens.intersection(old_tokens)
    decision = (
        "ADMIT_SEPARATE_FRESH20K"
        if statistics["supports_separate_fresh20k"]
        else "FRESH5K_TRANSFER_GATE_NOT_PASSED"
    )
    assert decision == analysis["decision"] and not analysis["goal_achieved"]
    reviewed = {
        "status": "PASS",
        "decision": decision,
        "model_sha256": MODEL_SHA,
        "statistics": statistics,
        "prior_audits_checked": prior_audits,
        "prior_token_hashes_checked": len(old_tokens),
        "slumbot_hands": 5000,
        "goal_achieved": False,
    }
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    ci = statistics["raw_hand_ci95"]
    session_ci = statistics["session_t7_ci95"]
    (BASE / "result_summary.md").write_text(
        "# Preserved procedural-soup generic-greedy fresh5k\n\n"
        f"Decision: `{decision}`. Frozen policy: {statistics['bb_per_100']:+.6f} bb/100; "
        f"raw-hand 95% CI [{ci[0]:+.6f}, {ci[1]:+.6f}], session-t7 CI "
        f"[{session_ci[0]:+.6f}, {session_ci[1]:+.6f}], positive sessions "
        f"{statistics['positive_sessions']}/8. Historical unpaired delta versus raw parent "
        f"{statistics['point_delta_vs_raw_parent_historical']:+.6f} bb/100. All actions were "
        "audited learned-logit legal argmax decisions. Pilot hands are not qualification hands.\n",
        encoding="utf-8",
    )
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__":
    main()
