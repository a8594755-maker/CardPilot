"""Independent final review of causal-TCN smoke evidence."""
import json
import math
import subprocess
import sys
import time

import psutil
import torch

import run_smoke as run


def gone(execution):
    try:
        return abs(
            psutil.Process(execution["pid"]).create_time() - execution["create_time"]
        ) > 0.001
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
    manifest = run.read(run.BASE / "input_manifest.json")
    for item in manifest["inputs"]:
        assert run.sha(item["source"]) == run.sha(item["path"]) == item["sha256"]
    for item in manifest["source_copies"]:
        assert run.sha(run.ROOT / item["copy"]) == item["sha256"]
    checkpoint = torch.load(
        run.BASE / "frozen/treatment.pt", map_location="cpu", weights_only=False
    )
    hands = checkpoint["environment_hand_accounting"]["completed_hands"]
    assert hands == execution["new_training_hands"] >= run.TARGET
    assert len(checkpoint["model"]) == 104
    assert len(checkpoint["optimizer"]["state"]) == 24
    assert run.read(run.BASE / "production/session_audit.json")["status"] == "PASS"
    rows = [
        json.loads(line)
        for line in (run.BASE / "evaluation/pairs.jsonl").read_text().splitlines()
    ]
    assert len(rows) == run.PAIRS
    assert [row["pair_index"] for row in rows] == list(range(run.PAIRS))
    contrast = run.estimate([math.fsum(row["rewards_bb"]) * 50 for row in rows])
    decision = (
        "ADMIT_MATCHED_CAUSAL_TCN_REWARD_PILOT"
        if contrast["mean"] > -20 else "CAUSAL_TCN_REWARD_SMOKE_NOT_PROMISING"
    )
    analysis = run.read(run.BASE / "analysis.json")
    assert analysis["decision"] == decision
    saved = analysis["source_contrast_bb_per_100"]
    assert abs(saved["mean"] - contrast["mean"]) <= 2e-12
    assert all(abs(left - right) <= 2e-12 for left, right in zip(saved["ci95"], contrast["ci95"]))
    report = {
        "status": "PASS", "decision": decision,
        "new_training_hands": hands, "evaluation_hands": 2 * run.PAIRS,
        "source_contrast_bb_per_100": contrast,
        "model_sha256": run.sha(run.BASE / "frozen/treatment.pt"),
        "session_audit_status": "PASS", "slumbot_hands": 0,
        "goal_achieved": False, "wall_time_seconds": execution["wall_time_seconds"],
        "review_wall_time_seconds": time.monotonic() - started,
        "interpretation": (
            "This fixed known-anchor internal smoke is only an architecture admission gate; "
            "it is neither external strength evidence nor a training-seed replication."
        ),
    }
    run.write(run.BASE / "reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(
        "# Causal-TCN reward smoke\n\n"
        f"{decision}\n\nSource contrast {contrast['mean']:.4f} bb/100, "
        f"CI95 {contrast['ci95']}. Training {hands} hands; evaluation "
        f"{2 * run.PAIRS} hands; 0 Slumbot.\n"
    )
    run.log(
        "--command", f"python research/experiments/{run.BASE.name}/review_finish.py",
        "--artifact", run.BASE / "reviewed_analysis.json",
        "--artifact", run.BASE / "result_summary.md",
        "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}",
    )
    next_step = (
        "Run the preregistered matched causal-TCN versus all-policy-heads control pilot "
        "with a fixed multi-anchor evaluation."
        if decision.startswith("ADMIT")
        else "End sequence-residual variants and test centralized-critic/EMA actor-critic training."
    )
    subprocess.run(
        [
            sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish",
            run.BASE.name, "--status", "COMPLETED",
            "--summary", f"Causal-TCN reward smoke completed: {decision}.",
            "--conclusion", report["interpretation"], "--decision", decision,
            "--next-step", next_step, "--count", f"new_training_hands={hands}",
            "--count", f"evaluation_hands={2 * run.PAIRS}", "--count", "slumbot_hands=0",
        ],
        cwd=run.ROOT,
        check=True,
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
