"""Attach a deterministic preflop strategy profile to a frozen checkpoint."""
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
        "--profile",
        choices=(
            "pokerskill_v1",
            "pokerskill_sb_v1",
            "pokerskill_sb_bbsize_v1",
            "pokerskill_sb_jamguard_v2",
            "pokerskill_v2",
        ),
        default="pokerskill_v1",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)

    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    if checkpoint.get("preflop_strategy_profile") is not None:
        raise RuntimeError("source already contains a preflop strategy profile")
    checkpoint["preflop_strategy_profile"] = args.profile
    checkpoint["preflop_strategy_profile_source"] = {
        "source_checkpoint": str(source),
        "source_sha256": sha256_path(source),
        "profile": args.profile,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(output)
    print(
        json.dumps(
            {
                "source": str(source),
                "source_sha256": sha256_path(source),
                "output": str(output),
                "output_sha256": sha256_path(output),
                "profile": args.profile,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
