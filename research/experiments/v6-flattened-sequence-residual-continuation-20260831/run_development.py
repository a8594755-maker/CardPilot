"""Exact fixed continuation of the backend-stable flat-sequence adapter."""
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
PARENT = ROOT / "research/experiments/v6-flattened-sequence-residual-development-20260831"
PARENT_SHA = "32e491e0967e097ef77ce036d6441cd466260c136453b2d53e5f9f46ee8e68ba"
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def load_parent_module():
    spec = importlib.util.spec_from_file_location("flat_sequence_parent", PARENT / "run_development.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


parent = load_parent_module()
QUERIES = {"cpu": 0, "cuda": 0}


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    atomic_json(BASE / name, value)


def log(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )


def validate_parent_checkpoint(checkpoint):
    assert checkpoint["architecture"] == "flat_sequence_residual_v1"
    assert checkpoint["source_weights_sha256"] == parent.SOURCE_SHA
    assert checkpoint["epoch"] == 8 and checkpoint["optimizer_steps"] == 2048
    assert checkpoint["total_hands"] == checkpoint["new_training_hands"] == 0
    assert len(checkpoint["adapter"]) == 14
    assert len(checkpoint["optimizer"]["state"]) == 14
    assert all(float(state["step"]) == 2048 for state in checkpoint["optimizer"]["state"].values())


def reconstructed_generator(rows):
    generator = np.random.default_rng(parent.SEED)
    for _ in range(8):
        generator.permutation(rows)
    return generator


@torch.no_grad()
def infer(model, arrays, device, count=True):
    output = []
    model.eval()
    for begin in range(0, len(arrays["legal_mask"]), 512):
        end = min(begin + 512, len(arrays["legal_mask"]))
        tensors = [torch.as_tensor(arrays[key][begin:end], dtype=torch.float32, device=device) for key in parent.KEYS]
        output.append(parent.softmax_legal(model(*tensors)[0].cpu().numpy(), arrays["legal_mask"][begin:end]))
        if count:
            QUERIES[device] += end - begin
    return np.concatenate(output)


def capture_code():
    destination = BASE / "execution_code"
    destination.mkdir()
    paths = [
        "research/experiment_log.py",
        PARENT.relative_to(ROOT).as_posix() + "/run_development.py",
    ] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, destination, paths)
    for relative in paths:
        target = destination / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def process_guard():
    forbidden = {"train_v5.py", "run_pilot.py", "run_development.py", "review_finish.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (os.getpid(), os.getppid()):
            continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def main():
    if sys.argv[1:] or (BASE / "execution.json").exists():
        raise ValueError("No restart")
    assert torch.cuda.is_available()
    assert read(PARENT / "experiment.json")["status"] == "COMPLETED"
    assert sha(PARENT / "latest.pt") == PARENT_SHA
    process_guard()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    started = time.monotonic()
    execution = {
        "status": "RUNNING", "pid": os.getpid(), "create_time": psutil.Process().create_time(),
        "started_at": datetime.now(timezone.utc).isoformat(), "new_training_hands": 0,
        "new_hands": 0, "model_state_queries": 0, "network_attempts": 0,
    }
    write("execution.json", execution)
    success = False
    try:
        capture_code()
        inputs = [
            PARENT / "latest.pt", PARENT / "gpu_probabilities.npy", PARENT / "training_metrics.jsonl",
            parent.SOURCE / "latest.pt", parent.SOURCE / "development_probabilities.npy",
            parent.DATA / "reservoir.pt", parent.REACH / "training_relabel/reach_targets.npy",
            parent.ACTORS / "retained_actors.npy", parent.REACH / "validation_relabel/validation_arrays.npz",
            parent.REACH / "validation_relabel/validation_targets.npy",
            parent.REACH / "validation_relabel/validation_metadata.npz",
        ]
        write("input_manifest.json", [{"path": str(path), "sha256": sha(path)} for path in inputs])
        socket.socket = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network forbidden"))
        checkpoint = torch.load(PARENT / "latest.pt", map_location="cpu", weights_only=False)
        validate_parent_checkpoint(checkpoint)
        parent_rows = [json.loads(line) for line in (PARENT / "training_metrics.jsonl").read_text().splitlines()]
        means = [np.mean([row["loss"] for row in parent_rows if row["epoch"] == epoch]) for epoch in range(1, 9)]
        assert len(parent_rows) == 2048 and all(left > right for left, right in zip(means, means[1:]))
        reservoir = torch.load(parent.DATA / "reservoir.pt", map_location="cpu", weights_only=False)
        actors = np.load(parent.ACTORS / "retained_actors.npy")
        training = parent.arrays_actor(reservoir["arrays"], actors)
        targets = np.load(parent.REACH / "training_relabel/reach_targets.npy").astype(np.float32)
        with np.load(parent.REACH / "validation_relabel/validation_arrays.npz") as archive:
            raw = {key: archive[key] for key in archive.files}
        metadata = np.load(parent.REACH / "validation_relabel/validation_metadata.npz")
        validation = parent.arrays_actor(raw, metadata["actors"])
        validation_targets = np.load(parent.REACH / "validation_relabel/validation_targets.npy")
        source_probabilities = np.load(parent.SOURCE / "development_probabilities.npy")
        parent_probabilities = np.load(PARENT / "gpu_probabilities.npy")
        model = parent.build("cuda", checkpoint["adapter"])
        epoch8 = infer(model, validation, "cuda", count=False)
        assert np.allclose(epoch8, parent_probabilities, atol=2e-5, rtol=0)
        parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith("base.")]
        assert len(parameters) == 14 and all(parameter.requires_grad for parameter in parameters)
        optimizer = torch.optim.Adam(parameters, lr=1e-4)
        optimizer.load_state_dict(checkpoint["optimizer"])
        generator = reconstructed_generator(len(targets))
        rows = []
        steps = 2048
        for epoch in range(9, 17):
            order = generator.permutation(len(targets))
            model.train()
            for begin in range(0, len(targets), 1024):
                indices = order[begin:begin + 1024]
                tensors = [torch.as_tensor(training[key][indices], dtype=torch.float32, device="cuda") for key in parent.KEYS]
                target = torch.as_tensor(targets[indices], device="cuda")
                logits = model(*tensors)[0].masked_fill(tensors[-1] <= 0, -1e9)
                loss = (torch.softmax(logits, dim=1) - target).abs().sum(dim=1).mean() / 2
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                gradient_norm = torch.nn.utils.clip_grad_norm_(parameters, 1)
                optimizer.step()
                steps += 1
                assert torch.isfinite(loss) and torch.isfinite(gradient_norm)
                rows.append({"epoch": epoch, "step": steps, "rows": len(indices), "loss": float(loss), "gradient_norm": float(gradient_norm)})
        assert steps == 4096
        gpu_probabilities = infer(model, validation, "cuda")
        adapter = model.adapter_state()
        torch.save({
            "architecture": "flat_sequence_residual_v1", "adapter": adapter,
            "source_weights_sha256": parent.SOURCE_SHA, "parent_weights_sha256": PARENT_SHA,
            "seed": parent.SEED, "optimizer": optimizer.state_dict(), "epoch": 16,
            "optimizer_steps": steps, "total_hands": 0, "new_training_hands": 0,
        }, BASE / "latest.pt")
        np.save(BASE / "gpu_probabilities.npy", gpu_probabilities)
        (BASE / "training_metrics.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        cpu_probabilities = infer(parent.build("cpu", adapter), validation, "cpu")
        np.save(BASE / "cpu_probabilities.npy", cpu_probabilities)
        parity = parent.parity_metrics(cpu_probabilities, gpu_probabilities)
        treatment_hand, _ = parent.hero_tv(gpu_probabilities, validation_targets, metadata["hands"], metadata["actors"])
        source_hand, _ = parent.hero_tv(source_probabilities, validation_targets, metadata["hands"], metadata["actors"])
        gate = parent.development_gate(treatment_hand, source_hand)
        decision = "ADMIT_FLAT_SEQUENCE_RUNTIME_INTEGRATION" if gate["passed"] and parity["passed"] else "FLAT_SEQUENCE_CONTINUATION_NOT_PROMISING"
        write("qualification.json", {"status": "PASS" if parity["passed"] else "FAIL", **parity})
        write("analysis.json", {
            "status": "COMPLETED_PENDING_REVIEW", "decision": decision,
            "development_gate": gate, "runtime_parity": parity,
            "model_sha256": sha(BASE / "latest.pt"), "source_weights_sha256": parent.SOURCE_SHA,
            "parent_weights_sha256": PARENT_SHA, "adapter_parameter_tensors": len(adapter),
            "optimizer_steps": steps, "optimizer_rows_processed": 2097152,
            "cpu_model_state_queries": QUERIES["cpu"], "gpu_model_state_queries": QUERIES["cuda"],
            "model_state_queries": sum(QUERIES.values()), "new_training_hands": 0, "new_hands": 0,
            "strength_hands": 0, "slumbot_hands": 0, "network_attempts": 0, "goal_achieved": False,
        })
        success = True
    except BaseException:
        (BASE / "failure.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        execution.update({
            "status": "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED",
            "cpu_model_state_queries": QUERIES["cpu"], "gpu_model_state_queries": QUERIES["cuda"],
            "model_state_queries": sum(QUERIES.values()), "finished_at": datetime.now(timezone.utc).isoformat(),
            "wall_time_seconds": time.monotonic() - started,
        })
        write("execution.json", execution)
        artifacts = []
        for path in BASE.iterdir():
            if path.is_file() and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts.extend(("--artifact", path))
        log(
            *artifacts, "--count", "new_training_hands=0", "--count", "evaluation_hands=0",
            "--count", "slumbot_hands=0", "--count", f"model_state_queries={sum(QUERIES.values())}",
            "--metric", f"wall_time_seconds={execution['wall_time_seconds']}",
        )
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
