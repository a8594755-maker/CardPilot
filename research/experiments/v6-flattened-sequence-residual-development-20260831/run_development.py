"""Backend-stable flattened action-sequence residual development."""
from datetime import datetime, timezone
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
from torch import nn

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / "research/experiments/v6-explicit-position-reach-development-20260831"
ACTORS = ROOT / "research/experiments/v6-metric-aligned-reach-development-20260831"
REACH = ROOT / "research/experiments/v6-reach-target-average-pilot-20260831"
DATA = ROOT / "research/experiments/v6-fictitious-average-phase2-20260831"
RUNTIME = DATA / "execution_code/source_files/scripts"
sys.path[:0] = [str(ROOT), str(RUNTIME), str(REACH), str(DATA)]

from research.experiment_log import atomic_json, capture_code_provenance, sha256_file
from alpha_holdem.execution_v6 import load_policy
from temporal_average import softmax_legal
from fit_metrics import hero_tv

SOURCE_SHA = "3b33549547bd1792f2a17b8981976ce560247f787ebd0d2ca1cf837e80ed9526"
SEED = 2026103001
SAMPLE_SEED = 2026103002
KEYS = ("card_info", "action_info", "extra_info", "legal_mask")
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


def arrays_actor(arrays, actors):
    result = {key: arrays[key] for key in KEYS}
    result["extra_info"] = np.concatenate(
        [arrays["extra_info"][:, :2], np.asarray(actors, dtype=np.float32)[:, None]], axis=1
    )
    return result


class FlatSequenceResidual(nn.Module):
    def __init__(self, base, seed=SEED):
        super().__init__()
        self.base = base
        for parameter in base.parameters():
            parameter.requires_grad_(False)
        torch.manual_seed(seed)
        self.sequence = nn.Sequential(
            nn.Linear(500, 512), nn.ReLU(), nn.Linear(512, 256), nn.ReLU()
        )
        self.trunk_norm = nn.LayerNorm(256)
        self.experts = nn.ModuleList(
            [nn.Sequential(nn.Linear(514, 128), nn.ReLU(), nn.Linear(128, 9)) for _ in range(2)]
        )
        for expert in self.experts:
            nn.init.zeros_(expert[-1].weight)
            nn.init.zeros_(expert[-1].bias)
        self._hidden = None
        self._hook = self.base.trunk.register_forward_hook(
            lambda module, args, output: setattr(self, "_hidden", output.detach())
        )

    def train(self, mode=True):
        super().train(mode)
        self.base.eval()
        return self

    def forward(self, card, action, extra, mask):
        logits, value = self.base(card, action, extra, mask)
        assert self._hidden is not None
        sequence = self.sequence(action.flatten(1))
        seat = extra[:, 2].round().long().clamp(0, 1)
        features = torch.cat(
            [self.trunk_norm(self._hidden), sequence, torch.nn.functional.one_hot(seat, 2).to(sequence.dtype)],
            dim=1,
        )
        deltas = torch.stack([expert(features) for expert in self.experts], dim=1)
        deltas = deltas.gather(1, seat[:, None, None].expand(-1, 1, 9)).squeeze(1)
        return logits + deltas, value

    def adapter_state(self):
        return {key: value.cpu() for key, value in self.state_dict().items() if not key.startswith("base.")}


def build(device, adapter=None):
    base, _, digest = load_policy(SOURCE / "latest.pt", device)
    assert digest == SOURCE_SHA
    model = FlatSequenceResidual(base).to(device)
    if adapter is not None:
        model.load_state_dict({"base." + key: value for key, value in base.state_dict().items()} | adapter)
    return model


@torch.no_grad()
def infer(model, arrays, device, count=True):
    output = []
    model.eval()
    for begin in range(0, len(arrays["legal_mask"]), 512):
        end = min(begin + 512, len(arrays["legal_mask"]))
        tensors = [torch.as_tensor(arrays[key][begin:end], dtype=torch.float32, device=device) for key in KEYS]
        output.append(softmax_legal(model(*tensors)[0].cpu().numpy(), arrays["legal_mask"][begin:end]))
        if count:
            QUERIES[device] += end - begin
    return np.concatenate(output)


def interval(values):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    mean = math.fsum(values.tolist()) / len(values)
    se = math.sqrt(math.fsum((float(x) - mean) ** 2 for x in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def development_gate(treatment_hand, source_hand):
    valid = np.isfinite(treatment_hand) & np.isfinite(source_hand)
    treatment = interval(treatment_hand[valid])
    paired = interval(source_hand[valid] - treatment_hand[valid])
    improvement = float(np.nanmean(source_hand) - np.nanmean(treatment_hand))
    passed = paired["ci95"][0] > 0 and improvement >= 0.005 and treatment["mean"] <= 0.15
    return {"passed": bool(passed), "treatment": treatment, "paired_source_minus_treatment": paired, "improvement": improvement}


def sampled_actions(probabilities, uniforms):
    cumulative = np.cumsum(np.asarray(probabilities, dtype=np.float64), axis=1)
    cumulative[:, -1] = 1.0
    return np.minimum((uniforms[:, None] > cumulative).sum(axis=1), cumulative.shape[1] - 1)


def parity_metrics(cpu, gpu):
    delta = np.abs(np.asarray(cpu, dtype=np.float64) - np.asarray(gpu, dtype=np.float64))
    uniforms = np.random.default_rng(SAMPLE_SEED).random(len(cpu))
    result = {
        "states": len(cpu),
        "max_probability_delta": float(delta.max()),
        "mean_backend_tv": float((0.5 * delta.sum(axis=1)).mean()),
        "greedy_disagreement": float(np.mean(np.argmax(cpu, axis=1) != np.argmax(gpu, axis=1))),
        "sampled_disagreement": float(np.mean(sampled_actions(cpu, uniforms) != sampled_actions(gpu, uniforms))),
    }
    result["passed"] = bool(
        result["max_probability_delta"] <= 2e-5
        and result["mean_backend_tv"] <= 2e-6
        and result["greedy_disagreement"] == 0
        and result["sampled_disagreement"] == 0
    )
    return result


def capture_code():
    destination = BASE / "execution_code"
    destination.mkdir()
    paths = ["research/experiment_log.py"] + [
        path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")
    ]
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
    assert read(SOURCE / "experiment.json")["status"] == "COMPLETED"
    assert sha(SOURCE / "latest.pt") == SOURCE_SHA
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
            SOURCE / "latest.pt", SOURCE / "development_probabilities.npy", DATA / "reservoir.pt",
            REACH / "training_relabel/reach_targets.npy", ACTORS / "retained_actors.npy",
            REACH / "validation_relabel/validation_arrays.npz",
            REACH / "validation_relabel/validation_targets.npy",
            REACH / "validation_relabel/validation_metadata.npz",
        ]
        write("input_manifest.json", [{"path": str(path), "sha256": sha(path)} for path in inputs])
        socket.socket = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network forbidden"))
        torch.manual_seed(SEED)
        torch.cuda.manual_seed_all(SEED)
        reservoir = torch.load(DATA / "reservoir.pt", map_location="cpu", weights_only=False)
        actors = np.load(ACTORS / "retained_actors.npy")
        training = arrays_actor(reservoir["arrays"], actors)
        targets = np.load(REACH / "training_relabel/reach_targets.npy").astype(np.float32)
        with np.load(REACH / "validation_relabel/validation_arrays.npz") as archive:
            raw = {key: archive[key] for key in archive.files}
        metadata = np.load(REACH / "validation_relabel/validation_metadata.npz")
        validation = arrays_actor(raw, metadata["actors"])
        validation_targets = np.load(REACH / "validation_relabel/validation_targets.npy")
        source_probabilities = np.load(SOURCE / "development_probabilities.npy")
        model = build("cuda")
        epoch0 = infer(model, validation, "cuda", count=False)
        assert np.allclose(epoch0, source_probabilities, atol=2e-5, rtol=0)
        parameters = [parameter for name, parameter in model.named_parameters() if not name.startswith("base.")]
        assert len(parameters) == 14 and all(parameter.requires_grad for parameter in parameters)
        optimizer = torch.optim.Adam(parameters, lr=1e-4)
        generator = np.random.default_rng(SEED)
        rows = []
        steps = 0
        for epoch in range(1, 9):
            order = generator.permutation(len(targets))
            model.train()
            for begin in range(0, len(targets), 1024):
                indices = order[begin:begin + 1024]
                tensors = [torch.as_tensor(training[key][indices], dtype=torch.float32, device="cuda") for key in KEYS]
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
        assert steps == 2048
        gpu_probabilities = infer(model, validation, "cuda")
        adapter = model.adapter_state()
        torch.save({
            "architecture": "flat_sequence_residual_v1", "adapter": adapter,
            "source_weights_sha256": SOURCE_SHA, "seed": SEED,
            "optimizer": optimizer.state_dict(), "epoch": 8, "optimizer_steps": steps,
            "total_hands": 0, "new_training_hands": 0,
        }, BASE / "latest.pt")
        np.save(BASE / "gpu_probabilities.npy", gpu_probabilities)
        (BASE / "training_metrics.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        cpu_model = build("cpu", adapter)
        cpu_probabilities = infer(cpu_model, validation, "cpu")
        np.save(BASE / "cpu_probabilities.npy", cpu_probabilities)
        parity = parity_metrics(cpu_probabilities, gpu_probabilities)
        treatment_hand, _ = hero_tv(gpu_probabilities, validation_targets, metadata["hands"], metadata["actors"])
        source_hand, _ = hero_tv(source_probabilities, validation_targets, metadata["hands"], metadata["actors"])
        gate = development_gate(treatment_hand, source_hand)
        decision = "ADMIT_FLAT_SEQUENCE_RUNTIME_INTEGRATION" if gate["passed"] and parity["passed"] else "FLAT_SEQUENCE_DEVELOPMENT_NOT_PROMISING"
        write("qualification.json", {"status": "PASS" if parity["passed"] else "FAIL", "thresholds": {"max_probability_delta": 2e-5, "mean_backend_tv": 2e-6, "greedy_disagreement": 0, "sampled_disagreement": 0}, **parity})
        write("analysis.json", {
            "status": "COMPLETED_PENDING_REVIEW", "decision": decision,
            "development_gate": gate, "runtime_parity": parity,
            "model_sha256": sha(BASE / "latest.pt"), "source_weights_sha256": SOURCE_SHA,
            "adapter_parameter_tensors": len(adapter), "optimizer_steps": steps,
            "optimizer_rows_processed": 2097152,
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
