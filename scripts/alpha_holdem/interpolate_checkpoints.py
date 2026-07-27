#!/usr/bin/env python3
"""Create a frozen linear weight interpolation of two compatible checkpoints."""

from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path

import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--alpha", required=True, type=float)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if not 0.0 <= args.alpha <= 1.0:
        raise ValueError("--alpha must be in [0, 1]")
    source_path = Path(args.source).resolve()
    candidate_path = Path(args.candidate).resolve()
    out_path = Path(args.out).resolve()
    if out_path.exists():
        raise FileExistsError(out_path)

    source = torch.load(source_path, map_location="cpu", weights_only=False)
    candidate = torch.load(candidate_path, map_location="cpu", weights_only=False)
    source_state = source["model"]
    candidate_state = candidate["model"]
    if source_state.keys() != candidate_state.keys():
        missing = sorted(source_state.keys() - candidate_state.keys())
        extra = sorted(candidate_state.keys() - source_state.keys())
        raise ValueError(f"incompatible model keys: missing={missing}, extra={extra}")

    blended_state: dict[str, torch.Tensor] = {}
    for name, source_tensor in source_state.items():
        candidate_tensor = candidate_state[name]
        if source_tensor.shape != candidate_tensor.shape:
            raise ValueError(
                f"shape mismatch for {name}: "
                f"{tuple(source_tensor.shape)} != {tuple(candidate_tensor.shape)}"
            )
        if source_tensor.is_floating_point():
            blended_state[name] = source_tensor.lerp(candidate_tensor, args.alpha)
        else:
            if not torch.equal(source_tensor, candidate_tensor):
                raise ValueError(f"non-floating tensor differs: {name}")
            blended_state[name] = source_tensor.clone()

    output = copy.deepcopy(source)
    output["model"] = blended_state
    output["optimizer"] = {}
    output["interpolation"] = {
        "source_checkpoint": str(source_path),
        "source_sha256": sha256_path(source_path),
        "candidate_checkpoint": str(candidate_path),
        "candidate_sha256": sha256_path(candidate_path),
        "alpha": args.alpha,
        "formula": "(1-alpha)*source + alpha*candidate",
    }
    output["resume"] = None
    output["lineage_parent_checkpoint"] = str(source_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(output, out_path)
    print(f"wrote={out_path}")
    print(f"sha256={sha256_path(out_path)}")


if __name__ == "__main__":
    main()
