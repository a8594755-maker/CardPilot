"""Independent raw/evidence review and closure for conservative soup fresh5k."""
import json
from pathlib import Path
import subprocess
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
STATS_DIR = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
sys.path[:0] = [str(STATS_DIR), str(ROOT)]
from pilot_stats import summarize
from research.experiment_log import atomic_json, sha256_file


MODEL_SHA = "914c8d186d4cdb4f2139ff64d2b32b7558eb1c5761b553c09457bd756aaec8e5"
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    execution, analysis, audit = load(BASE / "execution.json"), load(BASE / "completed_analysis.json"), load(BASE / "combined_audit.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and execution["slumbot_hands"] == 5000
    assert sha256_file(BASE / "frozen/final.pt") == MODEL_SHA
    assert audit["status"] == "PASS" and audit["successful_hands"] == 5000 and audit["model_sha256"] == MODEL_SHA and audit["token_chains_disjoint"]
    sessions = []
    for index in range(1, 9):
        rows = [json.loads(line) for line in (BASE / "sessions" / f"s{index:02d}/hands.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 625 and [row["successful_hand"] for row in rows] == list(range(1, 626))
        assert all(row["session_id"] == f"v6_standard10_parent_soup_greedy_fresh5k_20260901_s{index:02d}" and row["policy_seed"] == 2026110500 + index for row in rows)
        assert all(row["model_sha256"] == MODEL_SHA and row["policy_mode"] == "greedy" and row["policy_temperature"] == 0 for row in rows)
        for row in rows:
            assert row["terminal_validation"]["status"] == "PASS"
            assert all(decision["selected_action_slot"] == decision["greedy_action_slot"] and decision["behavior_probs"] == [float(slot == decision["selected_action_slot"]) for slot in range(9)] for decision in row["decisions"])
        sessions.append([row["winnings_chips"] for row in rows])
    statistics = summarize(sessions); assert statistics == analysis["statistics"]
    new_tokens = {token for row in audit["results"] for token in row["token_sha256"]}; old_tokens = set()
    for path in sorted((ROOT / "research/experiments").glob("*/combined_audit.json")):
        if BASE in path.parents: continue
        try: report = load(path)
        except (OSError, UnicodeError, json.JSONDecodeError): continue
        if report.get("status") == "PASS": old_tokens.update(token for row in report.get("results", []) for token in row.get("token_sha256", []))
    assert not new_tokens.intersection(old_tokens)
    admitted = statistics["bb_per_100"] > 0 and statistics["positive_sessions"] >= 4
    decision = "ADMIT_SEPARATE_FRESH20K" if admitted else "FRESH5K_TRANSFER_GATE_NOT_PASSED"
    assert decision == analysis["decision"]
    review = {"status": "PASS", "decision": decision, "model_sha256": MODEL_SHA, "statistics": statistics,
              "prior_token_hashes_checked": len(old_tokens), "slumbot_hands": 5000, "goal_achieved": False}
    atomic_json(BASE / "reviewed_analysis.json", review)
    s = statistics
    summary = f"Exact conservative soup completed 5000 fresh generic-greedy hands: {s['bb_per_100']:+.4f} bb/100, raw CI[{s['raw_hand_ci95'][0]:+.4f},{s['raw_hand_ci95'][1]:+.4f}], session-t7 CI[{s['session_t7_ci95'][0]:+.4f},{s['session_t7_ci95'][1]:+.4f}], positive sessions {s['positive_sessions']}/8; full independent audit PASS."
    conclusion = ("The fixed soup passed the preregistered point/session breadth pilot gate; this does not establish a positive CI."
                  if admitted else "The fixed soup failed the preregistered external transfer pilot and is not extended.")
    next_step = ("Run a separately preregistered fresh20k on the same SHA with no pooling; require evidence before any100k qualification."
                 if admitted else "Stop the model-soup route and retain the raw parent as the best learned external point.")
    subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "finish", BASE.name, "--status", "COMPLETED",
                    "--count", "new_training_hands=0", "--count", "evaluation_hands=5000", "--count", "slumbot_hands=5000",
                    "--metric", f"wall_time_seconds={execution['wall_time_seconds']}", "--metric", f"bb_per_100={s['bb_per_100']}",
                    "--metric", f"raw_ci_low={s['raw_hand_ci95'][0]}", "--metric", f"session_ci_low={s['session_t7_ci95'][0]}",
                    "--artifact", str(BASE / "reviewed_analysis.json"), "--summary", summary, "--conclusion", conclusion,
                    "--decision", decision, "--next-step", next_step,
                    "--note", "Independent reviewer recomputed raw/session statistics from all5000 hand JSONL rows and verified model/mode/decision/terminal/token/session independence; no prior hands pooled."], cwd=ROOT, check=True)
    print(json.dumps(review, sort_keys=True))


if __name__ == "__main__": main()
