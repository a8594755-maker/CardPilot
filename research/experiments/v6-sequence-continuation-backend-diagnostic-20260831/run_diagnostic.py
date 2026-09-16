"""Frozen full-cohort CPU/GPU materiality diagnostic for a failed endpoint."""
from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import traceback

import numpy as np
import psutil
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
FAILED = ROOT / "research/experiments/v6-sequence-residual-continuation-development-20260831"
PARENT = ROOT / "research/experiments/v6-sequence-residual-reach-development-20260831"
REACH = ROOT / "research/experiments/v6-reach-target-average-pilot-20260831"
EXPECTED_ENDPOINT_SHA = "0c23549877cc01c5f46fa8f24ede31c7806a0d29bfc696054042864f54c7c9ac"
EXPECTED_PARENT_SHA = "96913cf9ae4a0574ab2e5f95bc93abd4b39fdad43395a7882050cc95781172b2"
UNIFORM_SEED = 2026102901
THRESHOLDS = {
    "max_probability_delta": 1e-4,
    "mean_backend_tv": 1e-5,
    "greedy_disagreement": 1e-4,
    "sampled_disagreement": 1e-4,
    "absolute_hero_tv_mean_difference": 1e-4,
}

sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def load_continuation_module():
    path = FAILED / "run_development.py"
    spec = importlib.util.spec_from_file_location("failed_sequence_continuation", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


continuation = load_continuation_module()


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    atomic_json(BASE / name, value)


def log(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def interval(values):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    mean = math.fsum(values.tolist()) / len(values)
    se = math.sqrt(math.fsum((float(x) - mean) ** 2 for x in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def sampled_actions(probabilities, uniforms):
    cumulative = np.cumsum(np.asarray(probabilities, dtype=np.float64), axis=1)
    cumulative[:, -1] = 1.0
    return np.minimum((uniforms[:, None] > cumulative).sum(axis=1), cumulative.shape[1] - 1)


def backend_metrics(cpu_probabilities, gpu_probabilities, uniforms):
    cpu = np.asarray(cpu_probabilities, dtype=np.float64)
    gpu = np.asarray(gpu_probabilities, dtype=np.float64)
    assert cpu.shape == gpu.shape and len(cpu) == len(uniforms)
    delta = np.abs(cpu - gpu)
    per_state_tv = 0.5 * delta.sum(axis=1)
    cpu_sample = sampled_actions(cpu, uniforms)
    gpu_sample = sampled_actions(gpu, uniforms)
    return {
        "states": len(cpu),
        "max_probability_delta": float(delta.max()),
        "mean_backend_tv": float(per_state_tv.mean()),
        "max_backend_tv": float(per_state_tv.max()),
        "greedy_disagreement": float(np.mean(np.argmax(cpu, axis=1) != np.argmax(gpu, axis=1))),
        "sampled_disagreement": float(np.mean(cpu_sample != gpu_sample)),
    }


def original_gate(current_hand_tv, parent_hand_tv):
    use = np.isfinite(current_hand_tv) & np.isfinite(parent_hand_tv)
    treatment = interval(current_hand_tv[use])
    paired = interval(parent_hand_tv[use] - current_hand_tv[use])
    improvement = float(np.nanmean(parent_hand_tv) - np.nanmean(current_hand_tv))
    passed = paired["ci95"][0] > 0 and improvement >= 0.005 and treatment["mean"] <= 0.15
    return {"passed": bool(passed), "treatment": treatment, "paired_parent_minus_treatment": paired, "improvement": improvement}


@torch.no_grad()
def infer(model, arrays, device, counter):
    chunks = []
    model.eval()
    for begin in range(0, len(arrays["legal_mask"]), 512):
        end = min(begin + 512, len(arrays["legal_mask"]))
        tensors = [torch.as_tensor(arrays[key][begin:end], dtype=torch.float32, device=device) for key in continuation.KEYS]
        logits = model(*tensors)[0].cpu().numpy()
        chunks.append(continuation.softmax_legal(logits, arrays["legal_mask"][begin:end]))
        counter[device] += end - begin
    return np.concatenate(chunks)


def capture_code():
    destination = BASE / "execution_code"
    destination.mkdir()
    paths = [
        "research/experiment_log.py",
        FAILED.relative_to(ROOT).as_posix() + "/run_development.py",
    ] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, destination, paths)
    for relative in paths:
        target = destination / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def process_guard():
    forbidden = {"train_v5.py", "run_pilot.py", "run_development.py", "run_diagnostic.py", "review_finish.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (os.getpid(), os.getppid()):
            continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def main():
    if sys.argv[1:] or (BASE / "execution.json").exists():
        raise ValueError("No restart")
    assert torch.cuda.is_available()
    assert read(FAILED / "experiment.json")["status"] == "FAILED"
    assert read(PARENT / "experiment.json")["status"] == "COMPLETED"
    assert sha(FAILED / "latest.pt") == EXPECTED_ENDPOINT_SHA
    assert sha(PARENT / "latest.pt") == EXPECTED_PARENT_SHA
    process_guard()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    start = time.monotonic()
    counts = {"cpu": 0, "cuda": 0}
    execution = {
        "status": "RUNNING",
        "pid": os.getpid(),
        "create_time": psutil.Process().create_time(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cpu_model_state_queries": 0,
        "gpu_model_state_queries": 0,
        "model_state_queries": 0,
        "new_training_hands": 0,
        "new_hands": 0,
        "network_attempts": 0,
    }
    write("execution.json", execution)
    success = False
    try:
        capture_code()
        inputs = [
            FAILED / "latest.pt",
            FAILED / "development_probabilities.npy",
            FAILED / "run_development.py",
            PARENT / "latest.pt",
            PARENT / "development_probabilities.npy",
            REACH / "validation_relabel/validation_arrays.npz",
            REACH / "validation_relabel/validation_targets.npy",
            REACH / "validation_relabel/validation_metadata.npz",
        ]
        write("input_manifest.json", [{"path": str(path), "sha256": sha(path)} for path in inputs])
        socket.socket = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network forbidden"))
        checkpoint = torch.load(FAILED / "latest.pt", map_location="cpu", weights_only=False)
        assert checkpoint["epoch"] == 16 and checkpoint["optimizer_steps"] == 4096
        assert checkpoint["total_hands"] == checkpoint["new_training_hands"] == 0
        with np.load(REACH / "validation_relabel/validation_arrays.npz") as archive:
            raw = {key: archive[key] for key in archive.files}
        metadata = np.load(REACH / "validation_relabel/validation_metadata.npz")
        arrays = continuation.arrays_actor(raw, metadata["actors"])
        targets = np.load(REACH / "validation_relabel/validation_targets.npy")
        parent_probabilities = np.load(PARENT / "development_probabilities.npy")
        assert len(targets) == len(parent_probabilities) == len(arrays["legal_mask"]) == 69516
        cpu_model = continuation.build("cpu", checkpoint["adapter"])
        cpu_probabilities = infer(cpu_model, arrays, "cpu", counts)
        del cpu_model
        gpu_model = continuation.build("cuda", checkpoint["adapter"])
        gpu_probabilities = infer(gpu_model, arrays, "cuda", counts)
        np.save(BASE / "cpu_probabilities.npy", cpu_probabilities)
        np.save(BASE / "gpu_probabilities.npy", gpu_probabilities)
        stored_gpu = np.load(FAILED / "development_probabilities.npy")
        stored_gpu_max_delta = float(np.abs(gpu_probabilities - stored_gpu).max())
        uniforms = np.random.default_rng(UNIFORM_SEED).random(len(targets))
        metrics = backend_metrics(cpu_probabilities, gpu_probabilities, uniforms)
        cpu_hand_tv, _ = continuation.hero_tv(cpu_probabilities, targets, metadata["hands"], metadata["actors"])
        gpu_hand_tv, _ = continuation.hero_tv(gpu_probabilities, targets, metadata["hands"], metadata["actors"])
        parent_hand_tv, _ = continuation.hero_tv(parent_probabilities, targets, metadata["hands"], metadata["actors"])
        paired_backend = np.abs(cpu_hand_tv - gpu_hand_tv)
        metrics.update({
            "absolute_hero_tv_mean_difference": abs(float(np.nanmean(cpu_hand_tv)) - float(np.nanmean(gpu_hand_tv))),
            "mean_absolute_paired_hand_tv_difference": float(np.nanmean(paired_backend)),
            "max_absolute_paired_hand_tv_difference": float(np.nanmax(paired_backend)),
            "stored_gpu_probability_max_delta": stored_gpu_max_delta,
        })
        bounded = all(metrics[name] <= threshold for name, threshold in THRESHOLDS.items())
        decision = "BACKEND_DRIFT_BOUNDED_REQUIRES_EXPLICIT_RUNTIME_CONTRACT" if bounded else "BACKEND_DRIFT_MATERIAL"
        analysis = {
            "status": "COMPLETED_PENDING_REVIEW",
            "decision": decision,
            "thresholds": THRESHOLDS,
            "backend_metrics": metrics,
            "cpu_original_continuation_gate": original_gate(cpu_hand_tv, parent_hand_tv),
            "gpu_original_continuation_gate": original_gate(gpu_hand_tv, parent_hand_tv),
            "endpoint_sha256": sha(FAILED / "latest.pt"),
            "failed_parent_status_preserved": True,
            "uniform_seed": UNIFORM_SEED,
            "cpu_model_state_queries": counts["cpu"],
            "gpu_model_state_queries": counts["cuda"],
            "model_state_queries": counts["cpu"] + counts["cuda"],
            "new_training_hands": 0,
            "new_hands": 0,
            "strength_hands": 0,
            "slumbot_hands": 0,
            "network_attempts": 0,
            "goal_achieved": False,
        }
        assert counts == {"cpu": 69516, "cuda": 69516}
        write("analysis.json", analysis)
        success = True
    except BaseException:
        (BASE / "failure.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        execution.update({
            "status": "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED",
            "cpu_model_state_queries": counts["cpu"],
            "gpu_model_state_queries": counts["cuda"],
            "model_state_queries": counts["cpu"] + counts["cuda"],
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_seconds": time.monotonic() - start,
        })
        write("execution.json", execution)
        artifact_args = []
        for path in BASE.iterdir():
            if path.is_file() and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifact_args.extend(("--artifact", path))
        log(
            *artifact_args,
            "--count", "new_training_hands=0",
            "--count", "evaluation_hands=0",
            "--count", "slumbot_hands=0",
            "--count", f"model_state_queries={counts['cpu'] + counts['cuda']}",
            "--metric", f"wall_time_seconds={execution['wall_time_seconds']}",
        )
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
