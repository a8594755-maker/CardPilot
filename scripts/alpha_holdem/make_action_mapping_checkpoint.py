"""Create a checkpoint variant with an explicit live/training action mapping."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import torch


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--mapping",
        choices=(
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        required=True,
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    source_sha256 = sha256_path(source)
    mapping_metadata = {
        "legacy_total_over_pot": ("9slot_v5", "v55v4obs"),
        "preflop_pot_fraction_v2": (
            "9slot_preflop_pot_fraction_v2",
            "v55preflopv2v4obs",
        ),
        "pot_fraction_v2": ("9slot_pot_fraction_v2", "v55pfv2v4obs"),
    }
    action_space_version, env_version = mapping_metadata[args.mapping]
    checkpoint["raise_action_mapping"] = args.mapping
    checkpoint["action_space_version"] = action_space_version
    checkpoint["env_version"] = env_version
    checkpoint["obs_version"] = "v4"
    checkpoint["action_mapping_variant"] = {
        "source_checkpoint": str(source),
        "source_sha256": source_sha256,
        "mapping": args.mapping,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(output)
    print(
        json.dumps(
            {
                "source": str(source),
                "source_sha256": source_sha256,
                "output": str(output),
                "output_sha256": sha256_path(output),
                "mapping": args.mapping,
                "action_space_version": action_space_version,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
