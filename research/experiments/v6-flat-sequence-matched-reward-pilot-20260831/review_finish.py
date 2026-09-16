"""Independent final review of matched flat-sequence reward evidence."""
import json
import math
import subprocess
import sys
import time

import psutil
import torch

import run_pilot as run


def gone(execution):
    try: return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > .001
    except psutil.NoSuchProcess: return True


def main():
    if sys.argv[1:] or (run.BASE / "reviewed_analysis.json").exists(): raise ValueError("No repeat")
    started = time.monotonic(); execution = run.read(run.BASE / "execution.json"); assert execution["status"] == "COMPLETED_PENDING_REVIEW" and gone(execution)
    record = run.read(run.BASE / "experiment.json"); assert record["status"] == "RUNNING"
    for path, expected in record["artifact_integrity"].items(): assert run.sha(path) == expected["sha256"]
    manifest = run.read(run.BASE / "input_manifest.json")
    for item in manifest["inputs"]: assert run.sha(item["source"]) == run.sha(item["path"]) == item["sha256"]
    for item in manifest["source_copies"]: assert run.sha(run.ROOT / item["original"]) == run.sha(run.ROOT / item["copy"]) == item["sha256"]
    candidates = run.read(run.BASE / "candidate_manifest.json")
    for item in candidates.values(): assert run.sha(item["path"]) == item["sha256"]
    for arm in run.ARMS:
        checkpoint = torch.load(run.BASE / f"frozen/{arm}.pt", map_location="cpu", weights_only=False)
        assert checkpoint["environment_hand_accounting"]["completed_hands"] == execution["arm_training_hands"][arm] >= run.TARGET
        assert run.read(run.BASE / f"production/{arm}/session_audit.json")["status"] == "PASS"
    values = {}; decks = None
    for name in ("source", "control", "treatment"):
        for index in range(5):
            rows = [json.loads(line) for line in (run.BASE / f"matrix/{name}_anchor{index}/pairs.jsonl").read_text().splitlines()]
            assert len(rows) == run.PAIRS and [row["pair_index"] for row in rows] == list(range(run.PAIRS))
            current = [row["deck"] for row in rows]
            if decks is None: decks = current
            assert current == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
    per_anchor = [run.estimate([t - c for t, c in zip(values["treatment", index], values["control", index])]) for index in range(5)]
    tc = run.estimate([math.fsum(values["treatment", index][row] - values["control", index][row] for index in range(5)) / 5 for row in range(run.PAIRS)])
    ts = run.estimate([math.fsum(values["treatment", index][row] - values["source", index][row] for index in range(5)) / 5 for row in range(run.PAIRS)])
    points = [item["mean"] for item in per_anchor]; passed = run.gate(tc, ts, points); decision = "ADMIT_FLAT_SEQUENCE_TRAINING_SEED_CONFIRMATION" if passed else "FLAT_SEQUENCE_MATCHED_REWARD_GATE_NOT_PASSED"
    analysis = run.read(run.BASE / "analysis.json"); assert analysis["decision"] == decision and analysis["positive_treatment_control_anchors"] == sum(value > 0 for value in points)
    for computed, saved in ((tc, analysis["treatment_control"]), (ts, analysis["treatment_source"])): assert abs(computed["mean"] - saved["mean"]) <= 2e-12 and all(abs(a - b) <= 2e-12 for a, b in zip(computed["ci95"], saved["ci95"]))
    report = {"status": "PASS", "decision": decision, "arm_training_hands": execution["arm_training_hands"], "new_training_hands": execution["new_training_hands"], "evaluation_hands": execution["evaluation_hands"], "treatment_control": tc, "treatment_source": ts, "treatment_control_by_anchor": per_anchor, "positive_treatment_control_anchors": sum(value > 0 for value in points), "candidate_sha256": {name: item["sha256"] for name, item in candidates.items()}, "slumbot_hands": 0, "goal_achieved": False, "wall_time_seconds": execution["wall_time_seconds"], "review_wall_time_seconds": time.monotonic() - started, "interpretation": "Matched known-anchor internal evidence is not external strength or a training-seed replication."}
    run.write(run.BASE / "reviewed_analysis.json", report); (run.BASE / "result_summary.md").write_text(f"# Matched flat-sequence reward pilot\n\n{decision}\n\nTreatment-control {tc['mean']:.4f} CI95 {tc['ci95']}; treatment-source {ts['mean']:.4f} CI95 {ts['ci95']}; positive anchors {report['positive_treatment_control_anchors']}/5. Training {execution['new_training_hands']} hands; evaluation {execution['evaluation_hands']} hands;0 Slumbot.\n")
    run.log("--command", f"python research/experiments/{run.BASE.name}/review_finish.py", "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md", "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}")
    next_step = "Run a separately preregistered independent training-seed confirmation before any external pilot." if passed else "Reject this flat-sequence PPO route and implement a causal sequence actor with centralized critic/EMA evaluation."
    subprocess.run([sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name, "--status", "COMPLETED", "--summary", f"Matched flat-sequence reward pilot completed: {decision}.", "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step, "--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0"], cwd=run.ROOT, check=True); print(json.dumps(report), flush=True)


if __name__ == "__main__": main()
