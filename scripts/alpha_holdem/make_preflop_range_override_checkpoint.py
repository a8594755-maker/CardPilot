"""Attach a compact causal preflop range override to a frozen checkpoint."""
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
        choices=("sb_top20", "sb_top10_raise"),
        default=None,
    )
    parser.add_argument(
        "--rules-json",
        default=None,
        help="JSON file containing the complete policy_range_override object.",
    )
    args = parser.parse_args()

    source = Path(args.source).resolve()
    output = Path(args.out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(output)
    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    if checkpoint.get("policy_range_override") is not None:
        raise RuntimeError("source already contains policy_range_override")

    if bool(args.profile) == bool(args.rules_json):
        raise ValueError("provide exactly one of --profile or --rules-json")

    if args.rules_json:
        rules_path = Path(args.rules_json).resolve()
        override = json.loads(rules_path.read_text(encoding="utf-8"))
        if not isinstance(override, dict):
            raise ValueError("rules JSON must contain an object")
        for context in ("sb_open", "bb_vs_open", "bb_vs_limp"):
            rules = override.get(context)
            if rules is None:
                continue
            if not isinstance(rules, list):
                raise ValueError(f"{context} must be a list")
            for rule in rules:
                required = {
                    "percentile_min", "percentile_max",
                    "replace_action", "force_action",
                }
                if not isinstance(rule, dict) or not required.issubset(rule):
                    raise ValueError(f"invalid {context} rule: {rule!r}")
    elif args.profile in {"sb_top20", "sb_top10_raise"}:
        sb_rules = [
            {
                "percentile_min": 0.0,
                "percentile_max": 0.1,
                "replace_action": 0,
                "force_action": 7,
                "reason": "top-decile sampled raise exceeded fold",
            },
        ]
        if args.profile == "sb_top20":
            sb_rules.append({
                "percentile_min": 0.1,
                "percentile_max": 0.2,
                "replace_action": 0,
                "force_action": 1,
                "reason": "second-decile sampled limp-call exceeded fold",
            })
        override = {
            "schema": "preflop_range_override.v1",
            "evidence": (
                "14k temperature-2.5 randomized Slumbot hands; "
                "SB-open self-normalized propensity estimates"
            ),
            "sb_open": sb_rules,
        }
    else:
        raise AssertionError(args.profile)

    checkpoint["policy_range_override"] = override
    checkpoint["range_override_source"] = {
        "source_checkpoint": str(source),
        "source_checkpoint_sha256": sha256_path(source),
        "profile": args.profile,
        "rules_json": str(Path(args.rules_json).resolve()) if args.rules_json else None,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    torch.save(checkpoint, temporary)
    temporary.replace(output)
    print(json.dumps({
        "source": str(source),
        "source_sha256": sha256_path(source),
        "output": str(output),
        "output_sha256": sha256_path(output),
        "override": override,
    }, indent=2))


if __name__ == "__main__":
    main()
