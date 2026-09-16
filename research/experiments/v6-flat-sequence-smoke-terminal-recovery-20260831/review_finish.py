"""Independent review of read-only flat-sequence terminal recovery."""
import json
import math
import subprocess
import sys
import time

import psutil
import torch

import run_recovery as run


def gone(execution):
    try:
        return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > .001
    except psutil.NoSuchProcess:
        return True


def main():
    if sys.argv[1:] or (run.BASE / "reviewed_analysis.json").exists():
        raise ValueError("No repeat")
    started = time.monotonic()
    execution = run.read(run.BASE / "execution.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and gone(execution)
    record = run.read(run.BASE / "experiment.json")
    assert record["status"] == "RUNNING"
    for path, expected in record["artifact_integrity"].items():
        assert run.sha(path) == expected["sha256"]
    run.protect()
    inputs = run.read(run.BASE / "input_manifest.json")
    for label in ("endpoint", "anchor"):
        assert run.sha(inputs[label]["source"]) == run.sha(inputs[label]["copy"]) == inputs[label]["sha256"]
    checkpoint = torch.load(run.BASE / "frozen/treatment.pt", map_location="cpu", weights_only=False)
    assert checkpoint["environment_hand_accounting"]["completed_hands"] == 35546
    assert len(checkpoint["model"]) == 100 and len(checkpoint["optimizer"]["state"]) == 20
    assert run.read(run.BASE / "session_audit.json")["status"] == "PASS"
    rows = [json.loads(line) for line in (run.BASE / "evaluation/pairs.jsonl").read_text().splitlines()]
    assert len(rows) == run.PAIRS and [row["pair_index"] for row in rows] == list(range(run.PAIRS))
    values = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    estimate = {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}
    decision = "ADMIT_MATCHED_FLAT_SEQUENCE_REWARD_PILOT" if mean > -20 else "FLAT_SEQUENCE_REWARD_SMOKE_NOT_PROMISING"
    analysis = run.read(run.BASE / "analysis.json")
    assert analysis["decision"] == decision and analysis["preserved_parent_status"] == "FAILED"
    assert abs(analysis["source_contrast_bb_per_100"]["mean"] - mean) <= 2e-12
    report = {"status": "PASS", "decision": decision, "preserved_parent_status": "FAILED", "preserved_endpoint_sha256": run.ENDPOINT_SHA, "parent_training_hands": 35546, "new_training_hands": 0, "evaluation_hands": 2 * run.PAIRS, "source_contrast_bb_per_100": estimate, "session_audit_status": "PASS", "slumbot_hands": 0, "goal_achieved": False, "wall_time_seconds": execution["wall_time_seconds"], "review_wall_time_seconds": time.monotonic() - started, "interpretation": "Read-only recovery validates the preserved smoke endpoint but does not retroactively complete the failed parent or establish external strength."}
    run.write(run.BASE / "reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(f"# Flat-sequence smoke terminal recovery\n\n{decision}\n\nPreserved parent endpoint:35546 hands, SHA {run.ENDPOINT_SHA}. Source contrast {mean:.4f} bb/100, CI95 {estimate['ci95']}. Session/raw evidence PASS; parent remains FAILED;0 new training/Slumbot hands.\n")
    run.log("--command", f"python research/experiments/{run.BASE.name}/review_finish.py", "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md", "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}")
    next_step = "Preregister a matched262144-hand flat-sequence treatment versus architecture-free control with fixed multi-anchor evaluation." if decision.startswith("ADMIT") else "Reject the flat-sequence reward architecture and move to a causal sequence-policy actor with centralized critic."
    subprocess.run([sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name, "--status", "COMPLETED", "--summary", f"Read-only flat-sequence terminal recovery completed: {decision}.", "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step, "--count", "new_training_hands=0", "--count", f"evaluation_hands={2 * run.PAIRS}", "--count", "slumbot_hands=0"], cwd=run.ROOT, check=True)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
