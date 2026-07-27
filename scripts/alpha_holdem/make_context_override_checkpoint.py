"""Attach a compact street-context action override to a frozen checkpoint."""
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
    parser.add_argument("--rules-json", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    rules_path = Path(args.rules_json).resolve()
    output = Path(args.out).resolve()
    if not source.is_file() or not rules_path.is_file():
        raise FileNotFoundError("source checkpoint or rules JSON missing")
    if output.exists():
        raise FileExistsError(output)
    config = json.loads(rules_path.read_text(encoding="utf-8"))
    rules = config.get("rules") if isinstance(config, dict) else None
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules JSON must contain a non-empty rules list")
    required = {
        "street", "position", "facing", "strength",
        "replace_action", "force_action",
    }
    for rule in rules:
        if not isinstance(rule, dict) or not required.issubset(rule):
            raise ValueError(f"invalid context rule: {rule!r}")

    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    if checkpoint.get("policy_context_override") is not None:
        raise RuntimeError("source already contains policy_context_override")
    checkpoint["policy_context_override"] = config
    checkpoint["context_override_source"] = {
        "source_checkpoint": str(source),
        "source_checkpoint_sha256": sha256_path(source),
        "rules_json": str(rules_path),
        "rules_json_sha256": sha256_path(rules_path),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(output)
    print(json.dumps({
        "source": str(source),
        "source_sha256": sha256_path(source),
        "rules_json": str(rules_path),
        "rules_json_sha256": sha256_path(rules_path),
        "output": str(output),
        "output_sha256": sha256_path(output),
        "override": config,
    }, indent=2))


if __name__ == "__main__":
    main()
