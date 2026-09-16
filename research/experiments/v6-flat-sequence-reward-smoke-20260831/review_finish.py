"""Independent terminal review of the measured flat-sequence reward smoke."""
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
    manifest = run.read(run.BASE / "input_manifest.json")
    for item in manifest["inputs"]:
        assert run.sha(item["source"]) == run.sha(item["path"]) == item["sha256"]
    for item in manifest["source_copies"]:
        assert run.sha(run.ROOT / item["original"]) == run.sha(run.ROOT / item["copy"]) == item["sha256"]
    source = torch.load(run.SOURCE, map_location="cpu", weights_only=False)
    checkpoint = torch.load(run.BASE / "frozen/treatment.pt", map_location="cpu", weights_only=False)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= run.TARGET and account["prefix_complete"]
    assert len(checkpoint["model"]) == 100 and len(checkpoint["optimizer"]["state"]) == 20
    new_keys = [key for key in checkpoint["model"] if key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters."))]
    assert len(new_keys) == 14 and all(torch.isfinite(checkpoint["model"][key]).all() for key in new_keys)
    assert all(torch.equal(checkpoint["model"][key], value) for key, value in source["model"].items() if not key.startswith("value_head."))
    assert run.read(run.BASE / "production/session_audit.json")["status"] == "PASS"
    pairs = [json.loads(line) for line in (run.BASE / "evaluation/pairs.jsonl").read_text().splitlines()]
    assert len(pairs) == run.PAIRS and [row["pair_index"] for row in pairs] == list(range(run.PAIRS))
    values = [math.fsum(row["rewards_bb"]) * 50 for row in pairs]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    estimate = {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}
    passed = mean > -20
    decision = "ADMIT_MATCHED_FLAT_SEQUENCE_REWARD_PILOT" if passed else "FLAT_SEQUENCE_REWARD_SMOKE_NOT_PROMISING"
    analysis = run.read(run.BASE / "analysis.json")
    assert analysis["decision"] == decision and abs(analysis["source_contrast_bb_per_100"]["mean"] - mean) <= 2e-12
    report = {
        "status": "PASS", "decision": decision, "new_training_hands": account["completed_hands"],
        "evaluation_hands": 2 * run.PAIRS, "source_contrast_bb_per_100": estimate,
        "model_sha256": run.sha(run.BASE / "frozen/treatment.pt"), "source_sha256": run.SOURCE_SHA,
        "model_tensors": 100, "optimizer_state_tensors": 20, "flat_sequence_tensors": 14,
        "session_audit_status": "PASS", "slumbot_hands": 0, "goal_achieved": False,
        "wall_time_seconds": execution["wall_time_seconds"], "review_wall_time_seconds": time.monotonic() - started,
        "interpretation": "Measured production smoke and one small internal source contrast are not external strength evidence.",
    }
    run.write(run.BASE / "reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(
        f"# Flat-sequence reward smoke\n\n{decision}\n\n"
        f"Training hands {account['completed_hands']}; source contrast {mean:.4f} bb/100, CI95 {estimate['ci95']}. "
        "Session/model/optimizer/raw-pair audit PASS; 0 Slumbot hands.\n"
    )
    run.log("--command", f"python research/experiments/{run.BASE.name}/review_finish.py", "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md", "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}")
    next_step = "Preregister a matched262144-hand flat-sequence treatment versus architecture-free control with fixed multi-anchor evaluation." if passed else "Reject the flat-sequence reward architecture and move to a causal sequence-policy actor with centralized critic."
    subprocess.run(
        [sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name,
         "--status", "COMPLETED", "--summary", f"Flat-sequence reward smoke completed: {decision}.",
         "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step,
         "--count", f"new_training_hands={account['completed_hands']}", "--count", f"evaluation_hands={2 * run.PAIRS}", "--count", "slumbot_hands=0"],
        cwd=run.ROOT, check=True,
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
