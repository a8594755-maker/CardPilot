"""Independent raw-pair and preserved-state review for entropy penalty smoke."""
import importlib.util
import json, math
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, sha256_file

spec = importlib.util.spec_from_file_location("entropy_smoke_review_source", BASE / "run_smoke.py")
smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def estimate(values):
    values = [float(value) for value in values]; mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def main():
    analysis = read(BASE / "analysis.json"); execution = read(BASE / "execution.json"); manifest = read(BASE / "candidate_manifest.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and read(BASE / "production/treatment/session_audit.json")["status"] == "PASS"
    for name, row in manifest.items(): assert sha256_file(Path(row["path"])) == row["sha256"] == analysis["candidate_sha256"][name]
    values = {}; decks = None
    for name in ("source", "control", "treatment"):
        for anchor in range(5):
            rows = [json.loads(line) for line in (BASE / "matrix" / f"{name}_anchor{anchor}/pairs.jsonl").read_text().splitlines()]
            assert len(rows) == 2048 and [row["pair_index"] for row in rows] == list(range(2048))
            current = [row["deck"] for row in rows]
            if decks is None: decks = current
            assert current == decks
            values[name, anchor] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
    by_anchor = [estimate([t - c for t, c in zip(values["treatment", i], values["control", i])]) for i in range(5)]
    tc = estimate([math.fsum(values["treatment", i][p] - values["control", i][p] for i in range(5)) / 5 for p in range(2048)])
    ts = estimate([math.fsum(values["treatment", i][p] - values["source", i][p] for i in range(5)) / 5 for p in range(2048)])
    mechanism = smoke.state_mechanism(Path(manifest["control"]["path"]), Path(manifest["treatment"]["path"]))
    for expected, actual in ((tc, analysis["treatment_control"]), (ts, analysis["treatment_source"])):
        assert abs(expected["mean"] - actual["mean"]) < 1e-12 and all(abs(a-b) < 1e-12 for a,b in zip(expected["ci95"], actual["ci95"]))
    assert all(abs(mechanism[key] - analysis["mechanism"][key]) < 1e-12 for key in mechanism)
    positive = sum(row["mean"] > 0 for row in by_anchor)
    passed = tc["mean"] > 0 and ts["mean"] > 0 and positive >= 3 and mechanism["control_entropy"] - mechanism["treatment_entropy"] >= .03 and mechanism["treatment_control_tv"] < .10
    decision = "ADMIT_ENTROPY_PENALTY_PILOT" if passed else "ENTROPY_PENALTY_SMOKE_NOT_PROMISING"
    assert decision == analysis["decision"] and analysis["slumbot_hands"] == 0 and not analysis["goal_achieved"]
    reviewed = {"status": "PASS", "decision": decision, "treatment_control": tc, "treatment_source": ts,
                "treatment_control_by_anchor": by_anchor, "positive_treatment_control_anchors": positive,
                "mechanism": mechanism, "new_training_hands": analysis["new_training_hands"],
                "evaluation_hands": analysis["evaluation_hands"], "slumbot_hands": 0, "goal_achieved": False}
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    (BASE / "result_summary.md").write_text(
        "# Entropy-penalty actor smoke result\n\n"
        f"Decision: `{decision}`. Greedy treatment-minus-control {tc['mean']:+.6f} bb/100, "
        f"95% CI [{tc['ci95'][0]:+.6f}, {tc['ci95'][1]:+.6f}]; treatment-minus-source "
        f"{ts['mean']:+.6f}, positive anchors {positive}/5. Preserved-state entropy changed "
        f"from {mechanism['control_entropy']:.6f} to {mechanism['treatment_entropy']:.6f}; "
        f"TV {mechanism['treatment_control_tv']:.6f}. No Slumbot hands; Goal not achieved.\n",
        encoding="utf-8")
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__": main()
