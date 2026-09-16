"""Independent raw-hand review and terminal decision for bridge fresh5k."""
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path[:0] = [str(BASE), str(ROOT)]
from pilot_stats import summarize  # noqa: E402
from research.experiment_log import atomic_json, sha256_file  # noqa: E402

MODEL_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
BRIDGE = "hunl_v6_physical_legacy_v4_observation_bridge_v1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def session_id(index):
    return f"v6_standard10_legacy_bridge_greedy_fresh5k_20260901_s{index:02d}"


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
        summary = read(BASE / "sessions" / f"s{index:02d}" / "summary.json")
        assert summary["observation_bridge_contract"] == BRIDGE
        assert summary["model_obs_version"] == "v4"
        path = BASE / "sessions" / f"s{index:02d}" / "hands.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 625
        assert [row["successful_hand"] for row in rows] == list(range(1, 626))
        assert all(
            row["model_sha256"] == MODEL_SHA
            and row["strict_policy_execution"]
            and row["session_id"] == session_id(index)
            and row["policy_seed"] == 2026112100 + index
            and row["policy_mode"] == "greedy"
            and row["policy_temperature"] == 0
            for row in rows
        )
        for row in rows:
            assert row["terminal_validation"]["status"] == "PASS"
            for decision in row["decisions"]:
                assert decision["observation_bridge_contract"] == BRIDGE
                assert decision["source_checkpoint_sha256"] == MODEL_SHA
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_action_probability"] == 1
                assert decision["direct_increment"] in decision["v6_action_table"]
        sessions.append([row["winnings_chips"] for row in rows])
    statistics = summarize(sessions)
    assert statistics == analysis["statistics"]
    new_tokens = {token for result in audit["results"] for token in result["token_sha256"]}
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
            token for result in report.get("results", [])
            for token in result.get("token_sha256", [])
        )
    assert not new_tokens.intersection(old_tokens)
    decision = (
        "ADMIT_BRIDGE_GREEDY_FRESH20K"
        if statistics["supports_separate_fresh20k"]
        else "BRIDGE_GREEDY_FRESH5K_GATE_NOT_PASSED"
    )
    reviewed = {
        "status": "PASS",
        "decision": decision,
        "model_sha256": MODEL_SHA,
        "observation_bridge_contract": BRIDGE,
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
        "# Standard10 legacy-observation bridge generic-greedy fresh5k\n\n"
        f"Decision: `{decision}`. Frozen policy: {statistics['bb_per_100']:+.6f} bb/100; "
        f"raw-hand 95% CI [{ci[0]:+.6f}, {ci[1]:+.6f}], session-t7 CI "
        f"[{session_ci[0]:+.6f}, {session_ci[1]:+.6f}], positive sessions "
        f"{statistics['positive_sessions']}/8. Delta versus naive v6 rebound "
        f"{statistics['point_delta_vs_naive_v6_rebound']:+.6f}; unpaired delta versus historical "
        f"old-contract {statistics['point_delta_vs_historical_old_contract']:+.6f}. All actions and "
        "evidence passed bridge-aware replay audit. Pilot hands are not qualification hands.\n",
        encoding="utf-8",
    )
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__":
    main()
