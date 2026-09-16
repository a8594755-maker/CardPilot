"""Independent terminal review for the full-cohort backend diagnostic."""
import json
import subprocess
import sys
import time

import numpy as np
import psutil
import torch

import run_diagnostic as run


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
    assert run.read(run.FAILED / "experiment.json")["status"] == "FAILED"
    assert run.sha(run.FAILED / "latest.pt") == run.EXPECTED_ENDPOINT_SHA
    for path, expected in record["artifact_integrity"].items():
        assert run.sha(path) == expected["sha256"]
    for item in run.read(run.BASE / "input_manifest.json"):
        assert run.sha(item["path"]) == item["sha256"]
    cpu = np.load(run.BASE / "cpu_probabilities.npy")
    gpu = np.load(run.BASE / "gpu_probabilities.npy")
    assert cpu.shape == gpu.shape == (69516, 9)
    assert np.isfinite(cpu).all() and np.isfinite(gpu).all()
    assert np.allclose(cpu.sum(axis=1), 1, atol=2e-6, rtol=0)
    assert np.allclose(gpu.sum(axis=1), 1, atol=2e-6, rtol=0)
    uniforms = np.random.default_rng(run.UNIFORM_SEED).random(len(cpu))
    metrics = run.backend_metrics(cpu, gpu, uniforms)
    targets = np.load(run.REACH / "validation_relabel/validation_targets.npy")
    metadata = np.load(run.REACH / "validation_relabel/validation_metadata.npz")
    parent_probabilities = np.load(run.PARENT / "development_probabilities.npy")
    cpu_hand_tv, _ = run.continuation.hero_tv(cpu, targets, metadata["hands"], metadata["actors"])
    gpu_hand_tv, _ = run.continuation.hero_tv(gpu, targets, metadata["hands"], metadata["actors"])
    parent_hand_tv, _ = run.continuation.hero_tv(parent_probabilities, targets, metadata["hands"], metadata["actors"])
    backend_pair = np.abs(cpu_hand_tv - gpu_hand_tv)
    metrics.update({
        "absolute_hero_tv_mean_difference": abs(float(np.nanmean(cpu_hand_tv)) - float(np.nanmean(gpu_hand_tv))),
        "mean_absolute_paired_hand_tv_difference": float(np.nanmean(backend_pair)),
        "max_absolute_paired_hand_tv_difference": float(np.nanmax(backend_pair)),
        "stored_gpu_probability_max_delta": float(np.abs(gpu - np.load(run.FAILED / "development_probabilities.npy")).max()),
    })
    bounded = all(metrics[name] <= threshold for name, threshold in run.THRESHOLDS.items())
    decision = "BACKEND_DRIFT_BOUNDED_REQUIRES_EXPLICIT_RUNTIME_CONTRACT" if bounded else "BACKEND_DRIFT_MATERIAL"
    analysis = run.read(run.BASE / "analysis.json")
    assert analysis["decision"] == decision and analysis["failed_parent_status_preserved"]
    for name, value in metrics.items():
        if isinstance(value, float):
            assert abs(value - analysis["backend_metrics"][name]) <= 2e-12
        else:
            assert value == analysis["backend_metrics"][name]
    cpu_gate = run.original_gate(cpu_hand_tv, parent_hand_tv)
    gpu_gate = run.original_gate(gpu_hand_tv, parent_hand_tv)
    for computed, recorded in ((cpu_gate, analysis["cpu_original_continuation_gate"]), (gpu_gate, analysis["gpu_original_continuation_gate"])):
        assert computed["passed"] == recorded["passed"]
        assert abs(computed["improvement"] - recorded["improvement"]) <= 2e-12
        assert np.allclose(computed["treatment"]["ci95"], recorded["treatment"]["ci95"], atol=2e-12, rtol=0)
        assert np.allclose(computed["paired_parent_minus_treatment"]["ci95"], recorded["paired_parent_minus_treatment"]["ci95"], atol=2e-12, rtol=0)
    report = {
        "status": "PASS",
        "decision": decision,
        "thresholds": run.THRESHOLDS,
        "backend_metrics": metrics,
        "cpu_original_continuation_gate": cpu_gate,
        "gpu_original_continuation_gate": gpu_gate,
        "endpoint_sha256": run.EXPECTED_ENDPOINT_SHA,
        "failed_parent_status_preserved": True,
        "execution_model_state_queries": execution["model_state_queries"],
        "failed_review_attempt_model_state_queries": 1280,
        "successful_review_model_state_queries": 0,
        "independent_review_model_state_queries": 1280,
        "review_linkage": "SHA-locked execution snapshot plus preserved full-cohort arrays; repeated CUDA linkage exceeded1e-4 and is preserved as attempt3 failure.",
        "new_training_hands": 0,
        "evaluation_hands": 0,
        "strength_hands": 0,
        "slumbot_hands": 0,
        "goal_achieved": False,
        "wall_time_seconds": execution["wall_time_seconds"],
        "review_wall_time_seconds": time.monotonic() - started,
        "interpretation": "This numeric diagnostic preserves the parent failure and is neither endpoint qualification nor poker-strength evidence.",
    }
    run.write("reviewed_analysis.json", report)
    (run.BASE / "result_summary.md").write_text(
        "# Sequence-continuation backend diagnostic\n\n"
        f"{decision}\n\n"
        f"Full-cohort metrics: {json.dumps(metrics, sort_keys=True)}\n\n"
        f"CPU original gate={cpu_gate['passed']}; GPU original gate={gpu_gate['passed']}. "
        "The failed parent remains failed. 0 new hands, strength hands, or Slumbot hands.\n"
    )
    run.log(
        "--command", f"python research/experiments/{run.BASE.name}/review_finish.py",
        "--artifact", run.BASE / "reviewed_analysis.json",
        "--artifact", run.BASE / "result_summary.md",
        "--count", "failed_review_attempt_model_state_queries=1280",
        "--count", "successful_review_model_state_queries=0",
        "--count", "independent_review_model_state_queries=1280",
        "--metric", f"review_wall_time_seconds={report['review_wall_time_seconds']}",
    )
    if decision == "BACKEND_DRIFT_BOUNDED_REQUIRES_EXPLICIT_RUNTIME_CONTRACT":
        next_step = "Build and test an explicit single-backend sequence runtime, then preregister untouched native validation without reopening the failed parent."
    else:
        next_step = "Reject the continuation endpoint and move to a backend-stable sequence architecture or reward-trained route."
    subprocess.run(
        [
            sys.executable, str(run.ROOT / "research/experiment_log.py"), "finish", run.BASE.name,
            "--status", "COMPLETED",
            "--summary", f"Frozen full-cohort backend diagnostic completed: {decision}.",
            "--conclusion", report["interpretation"],
            "--decision", decision,
            "--next-step", next_step,
            "--count", "new_training_hands=0",
            "--count", "evaluation_hands=0",
            "--count", "slumbot_hands=0",
        ],
        cwd=run.ROOT,
        check=True,
    )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
