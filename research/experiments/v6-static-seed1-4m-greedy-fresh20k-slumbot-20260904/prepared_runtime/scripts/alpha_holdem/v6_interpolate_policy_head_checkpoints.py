"""Create optimizer-free actor-only checkpoint interpolations for dose audits."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_alpha(value: str) -> float:
    alpha = float(value)
    if not 0.0 < alpha < 1.0:
        raise argparse.ArgumentTypeError("alpha must be in (0,1)")
    return alpha


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--control-sha256", required=True)
    parser.add_argument("--treatment", type=Path, required=True)
    parser.add_argument("--treatment-sha256", required=True)
    parser.add_argument("--alpha", action="append", type=parse_alpha, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    if len(set(args.alpha)) != len(args.alpha):
        parser.error("alphas must be unique")
    expected_hashes = {
        "control": args.control_sha256.lower(),
        "treatment": args.treatment_sha256.lower(),
    }
    actual_hashes = {
        "control": sha256_path(args.control),
        "treatment": sha256_path(args.treatment),
    }
    if actual_hashes != expected_hashes:
        raise ValueError(
            f"checkpoint hash mismatch: expected={expected_hashes} actual={actual_hashes}"
        )
    checkpoints = {
        "control": torch.load(args.control, map_location="cpu", weights_only=False),
        "treatment": torch.load(
            args.treatment, map_location="cpu", weights_only=False
        ),
    }
    control_model = checkpoints["control"]["model"]
    treatment_model = checkpoints["treatment"]["model"]
    if set(control_model) != set(treatment_model):
        raise ValueError("model state keys differ")
    actor_prefixes = ("policy_head.", "preflop_policy_head.")
    actor_keys = sorted(key for key in control_model if key.startswith(actor_prefixes))
    if not actor_keys:
        raise ValueError("no policy-head tensors found")
    for key in control_model:
        if control_model[key].shape != treatment_model[key].shape:
            raise ValueError(f"model tensor shape mismatch: {key}")

    args.out_dir.mkdir(parents=True)
    rows = []
    removable = {
        "optimizer",
        "ppo_replay_entries",
        "ppo_replay_rng_state",
        "rng_state",
        "numpy_rng_state",
        "torch_rng_state",
        "cuda_rng_state",
    }
    for alpha in sorted(args.alpha):
        model = {}
        for key, control_tensor in control_model.items():
            if key in actor_keys:
                model[key] = torch.lerp(
                    control_tensor.float(), treatment_model[key].float(), alpha
                ).to(dtype=control_tensor.dtype)
            else:
                model[key] = control_tensor.detach().clone()
        payload = {
            key: value
            for key, value in checkpoints["control"].items()
            if key not in removable and key != "model"
        }
        label = f"alpha_{alpha:g}".replace(".", "p")
        metadata = {
            "schema": "cardpilot.policy_head_interpolation.v1",
            "alpha": alpha,
            "control_path": str(args.control.resolve()),
            "control_sha256": actual_hashes["control"],
            "treatment_path": str(args.treatment.resolve()),
            "treatment_sha256": actual_hashes["treatment"],
            "actor_keys": actor_keys,
            "non_actor_source": "control",
            "optimizer_free": True,
            "resume_eligible": False,
        }
        payload.update(
            model=model,
            optimizer=None,
            resume_eligible=False,
            policy_head_interpolation=metadata,
        )
        output_path = args.out_dir / f"{label}.pt"
        torch.save(payload, output_path)
        reloaded = torch.load(output_path, map_location="cpu", weights_only=False)
        if reloaded["policy_head_interpolation"] != metadata:
            raise RuntimeError("interpolation metadata round-trip mismatch")
        rows.append(
            {
                "alpha": alpha,
                "path": str(output_path.resolve()),
                "sha256": sha256_path(output_path),
                "bytes": output_path.stat().st_size,
            }
        )
    manifest = {
        "schema": "cardpilot.policy_head_interpolation_manifest.v1",
        "inputs": {
            "control": {
                "path": str(args.control.resolve()),
                "sha256": actual_hashes["control"],
            },
            "treatment": {
                "path": str(args.treatment.resolve()),
                "sha256": actual_hashes["treatment"],
            },
        },
        "actor_keys": actor_keys,
        "interpolations": rows,
        "command": [sys.executable, *sys.argv],
    }
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
