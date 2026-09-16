"""Independent terminal review of flattened-sequence development."""
import json
import math
import subprocess
import sys
import time

import numpy as np
import psutil
import torch

import run_development as run


def process_gone(execution):
    try:
        return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > 0.001
    except psutil.NoSuchProcess:
        return True


def main():
    if sys.argv[1:] or (run.BASE / "reviewed_analysis.json").exists():
        raise ValueError("No repeat")
    started = time.monotonic()
    execution = run.read(run.BASE / "execution.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW" and process_gone(execution)
    record = run.read(run.BASE / "experiment.json")
    assert record["status"] == "RUNNING"
    for path, expected in record["artifact_integrity"].items():
        assert run.sha(path) == expected["sha256"]
    for item in run.read(run.BASE / "input_manifest.json"):
        assert run.sha(item["path"]) == item["sha256"]
    checkpoint = torch.load(run.BASE / "latest.pt", map_location="cpu", weights_only=False)
    assert checkpoint["architecture"] == "flat_sequence_residual_v1"
    assert checkpoint["source_weights_sha256"] == run.SOURCE_SHA
    assert checkpoint["epoch"] == 8 and checkpoint["optimizer_steps"] == 2048
    assert checkpoint["total_hands"] == checkpoint["new_training_hands"] == 0
    assert len(checkpoint["adapter"]) == 14 and all(torch.isfinite(value).all() for value in checkpoint["adapter"].values())
    assert len(checkpoint["optimizer"]["state"]) == 14
    assert all(float(state["step"]) == 2048 for state in checkpoint["optimizer"]["state"].values())
    rows = [json.loads(line) for line in (run.BASE / "training_metrics.jsonl").read_text().splitlines()]
    assert len(rows) == 2048 and [row["step"] for row in rows] == list(range(1, 2049))
    assert all(row["rows"] == 1024 and math.isfinite(row["loss"]) and math.isfinite(row["gradient_norm"]) for row in rows)
    cpu = np.load(run.BASE / "cpu_probabilities.npy")
    gpu = np.load(run.BASE / "gpu_probabilities.npy")
    assert cpu.shape == gpu.shape == (69516, 9)
    assert np.isfinite(cpu).all() and np.isfinite(gpu).all()
    parity = run.parity_metrics(cpu, gpu)
    targets = np.load(run.REACH / "validation_relabel/validation_targets.npy")
    metadata = np.load(run.REACH / "validation_relabel/validation_metadata.npz")
    source_probabilities = np.load(run.SOURCE / "development_probabilities.npy")
    treatment_hand, _ = run.hero_tv(gpu, targets, metadata["hands"], metadata["actors"])
    source_hand, _ = run.hero_tv(source_probabilities, targets, metadata["hands"], metadata["actors"])
    gate = run.development_gate(treatment_hand, source_hand)
    decision = "ADMIT_FLAT_SEQUENCE_RUNTIME_INTEGRATION" if gate["passed"] and parity["passed"] else "FLAT_SEQUENCE_DEVELOPMENT_NOT_PROMISING"
    analysis = run.read(run.BASE / "analysis.json")
    assert analysis["decision"] == decision and analysis["runtime_parity"]["passed"] == parity["passed"]
    assert gate["passed"] == analysis["development_gate"]["passed"]
    assert abs(gate["improvement"] - analysis["development_gate"]["improvement"]) <= 2e-12
    assert np.allclose(gate["treatment"]["ci95"], analysis["development_gate"]["treatment"]["ci95"], atol=2e-12, rtol=0)
    for name, value in parity.items():
        if isinstance(value, float):
            assert abs(value - analysis["runtime_parity"][name]) <= 2e-12
    report = {
        "status": "PASS", "decision": decision, "development_gate": gate,
        "runtime_parity": parity, "model_sha256": run.sha(run.BASE / "latest.pt"),
        "source_weights_sha256": run.SOURCE_SHA, "adapter_parameter_tensors": 14,
        "optimizer_steps": 2048, "optimizer_rows_processed": 2097152,
        "model_state_queries": execution["model_state_queries"], "independent_review_model_state_queries": 0,
        "new_training_hands": 0, "evaluation_hands": 0, "strength_hands": 0,
        "slumbot_hands": 0, "goal_achieved": False, "wall_time_seconds": execution["wall_time_seconds"],
        "review_wall_time_seconds": time.monotonic() - started,
        "interpretation": "Known-cohort flattened-sequence development is not confirmatory poker-strength evidence.",
    }
    run.write("reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(
        "# Flattened-sequence residual development\n\n"
        f"{decision}\n\nTV {gate['treatment']['mean']:.6f}; improvement {gate['improvement']:.6f}; "
        f"paired CI {gate['paired_source_minus_treatment']['ci95']}; parity {parity}.\n\n"
        "0 new hands, strength hands, or Slumbot hands.\n"
    )
    run.log(
        "--command", f"python research/experiments/{run.BASE.name}/review_finish.py",
        "--artifact", run.BASE / "reviewed_analysis.json", "--artifact", run.BASE / "result_summary.md",
        "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}",
    )
    next_step = (
        "Implement and independently test the exact flat-sequence production loader, then preregister untouched native validation."
        if decision.startswith("ADMIT") else
        "Stop supervised residual fitting and test a full sequence-policy reward-training architecture."
    )
    subprocess.run(
        [sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name,
         "--status", "COMPLETED", "--summary", f"Flattened-sequence development completed: {decision}.",
         "--conclusion", report["interpretation"], "--decision", decision, "--next-step", next_step,
         "--count", "new_training_hands=0", "--count", "evaluation_hands=0", "--count", "slumbot_hands=0"],
        cwd=run.ROOT, check=True,
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
