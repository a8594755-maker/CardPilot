"""Independent raw-evidence review for causal-TCN terminal recovery."""
import json
import math
import subprocess
import sys
import time

import psutil

import run_recovery as run


def gone(execution):
    try: return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > 0.001
    except psutil.NoSuchProcess: return True


def estimate(values):
    values = [float(value) for value in values]; mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def main():
    if sys.argv[1:] or (run.BASE / "reviewed_analysis.json").exists(): raise ValueError("No repeat")
    started = time.monotonic(); execution = run.read(run.BASE / "execution.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and gone(execution)
    record = run.read(run.BASE / "experiment.json"); assert record["status"] == "RUNNING"
    for path, expected in record["artifact_integrity"].items(): assert run.sha(path) == expected["sha256"]
    manifest = run.read(run.BASE / "input_manifest.json")
    assert run.sha(manifest["parent_record"]["path"]) == manifest["parent_record"]["sha256"]
    for item in manifest["checkpoints"] + manifest["raw_evidence"]: assert run.sha(item["path"]) == item["sha256"]
    values = {}; decks = None
    for name in ("source", "control", "treatment"):
        for index in range(5):
            rows = [json.loads(line) for line in (run.PARENT / f"matrix/{name}_anchor{index}/pairs.jsonl").read_text().splitlines()]
            assert len(rows) == run.PAIRS and [row["pair_index"] for row in rows] == list(range(run.PAIRS))
            current = [row["deck"] for row in rows]
            if decks is None: decks = current
            assert current == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
    per_anchor = [estimate([t - c for t, c in zip(values["treatment", index], values["control", index])]) for index in range(5)]
    tc = estimate([math.fsum(values["treatment", index][row] - values["control", index][row] for index in range(5)) / 5 for row in range(run.PAIRS)])
    ts = estimate([math.fsum(values["treatment", index][row] - values["source", index][row] for index in range(5)) / 5 for row in range(run.PAIRS)])
    points = [item["mean"] for item in per_anchor]
    decision = "ADMIT_CAUSAL_TCN_TRAINING_SEED_CONFIRMATION" if tc["ci95"][0] > 0 and ts["ci95"][0] > 0 and sum(value > 0 for value in points) >= 3 else "CAUSAL_TCN_MATCHED_REWARD_GATE_NOT_PASSED"
    analysis = run.read(run.BASE / "analysis.json"); assert analysis["decision"] == decision and analysis["preserved_parent_status"] == "FAILED"
    for computed, saved in ((tc, analysis["treatment_control"]), (ts, analysis["treatment_source"])):
        assert abs(computed["mean"] - saved["mean"]) <= 2e-12 and all(abs(a - b) <= 2e-12 for a, b in zip(computed["ci95"], saved["ci95"]))
    report = {"status": "PASS", "decision": decision, "preserved_parent_status": "FAILED", "parent_training_hands": 532300, "new_training_hands": 0, "source_evaluation_hands": 122880, "evaluation_hands": 0, "treatment_control": tc, "treatment_source": ts, "treatment_control_by_anchor": per_anchor, "positive_treatment_control_anchors": sum(value > 0 for value in points), "slumbot_hands": 0, "goal_achieved": False, "wall_time_seconds": execution["wall_time_seconds"], "review_wall_time_seconds": time.monotonic() - started, "interpretation": "Read-only recovery validates complete parent evidence but does not retroactively complete the failed parent or establish external strength."}
    run.write(run.BASE / "reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(f"# Matched causal-TCN terminal recovery\n\n{decision}\n\nTreatment-control {tc['mean']:.4f} CI95 {tc['ci95']}; treatment-source {ts['mean']:.4f} CI95 {ts['ci95']}; positive anchors {report['positive_treatment_control_anchors']}/5. Parent training 532300 hands; reused evaluation evidence 122880 hands; zero new hands; parent remains FAILED.\n")
    run.log("--command", f"python research/experiments/{run.BASE.name}/review_finish.py", "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md", "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}")
    next_step = "Preregister an independent causal-TCN training-seed confirmation before external evaluation." if decision.startswith("ADMIT") else "Close sequence-residual variants and test centralized-critic/EMA actor-critic training."
    subprocess.run([sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name, "--status", "COMPLETED", "--summary", f"Read-only matched causal-TCN recovery completed: {decision}.", "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step, "--count", "new_training_hands=0", "--count", "evaluation_hands=0", "--count", "slumbot_hands=0"], cwd=run.ROOT, check=True)
    print(json.dumps(report), flush=True)


if __name__ == "__main__": main()
