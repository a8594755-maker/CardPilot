#!/usr/bin/env python3
"""Compose independently trained preflop and postflop policy modules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import torch


PREFLOP_KEYS = {
    "preflop_policy_head.weight",
    "preflop_policy_head.bias",
}
POSTFLOP_PREFIX = "postflop_policy_adapter."
POSTFLOP_ALLOWED_AUXILIARY_PREFIXES = ("value_head.",)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_checkpoint(path: Path) -> dict[str, Any]:
    value = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(value, dict) or not isinstance(value.get("model"), dict):
        raise TypeError(f"{path} is not a model checkpoint")
    return value


def changed_keys(
    reference: dict[str, torch.Tensor],
    candidate: dict[str, torch.Tensor],
) -> set[str]:
    return {
        key
        for key in reference.keys() & candidate.keys()
        if not torch.equal(reference[key], candidate[key])
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--preflop", required=True)
    parser.add_argument("--postflop", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    preflop_path = Path(args.preflop).resolve()
    postflop_path = Path(args.postflop).resolve()
    output_path = Path(args.out).resolve()
    if output_path.exists():
        raise FileExistsError(output_path)

    source = load_checkpoint(source_path)
    preflop = load_checkpoint(preflop_path)
    postflop = load_checkpoint(postflop_path)
    source_state = source["model"]
    preflop_state = preflop["model"]
    postflop_state = postflop["model"]

    preflop_changes = changed_keys(source_state, preflop_state)
    if preflop_changes != PREFLOP_KEYS:
        raise RuntimeError(
            f"preflop branch changed unexpected keys: {sorted(preflop_changes)}"
        )
    postflop_common_changes = changed_keys(source_state, postflop_state)
    postflop_common_policy_changes = {
        key
        for key in postflop_common_changes
        if key.startswith(POSTFLOP_PREFIX)
    }
    unexpected_postflop_common_changes = {
        key
        for key in postflop_common_changes
        if (
            key not in postflop_common_policy_changes
            and not key.startswith(POSTFLOP_ALLOWED_AUXILIARY_PREFIXES)
        )
    }
    if unexpected_postflop_common_changes:
        raise RuntimeError(
            "postflop branch changed inherited source keys: "
            f"{sorted(unexpected_postflop_common_changes)}"
        )
    postflop_added = set(postflop_state) - set(source_state)
    if any(
        not key.startswith(POSTFLOP_PREFIX) for key in postflop_added
    ):
        raise RuntimeError(
            f"unexpected postflop-only keys: {sorted(postflop_added)}"
        )
    postflop_policy_changes = (
        postflop_common_policy_changes | postflop_added
    )
    if not postflop_policy_changes:
        raise RuntimeError("postflop branch contains no learned policy changes")

    for field in (
        "obs_version",
        "norm_layer",
        "action_space_version",
        "raise_action_mapping",
    ):
        values = {
            source.get(field),
            preflop.get(field),
            postflop.get(field),
        }
        if len(values) != 1:
            raise RuntimeError(
                f"checkpoint metadata mismatch for {field}: {values}"
            )

    composed_state = {
        key: value.detach().clone()
        for key, value in postflop_state.items()
    }
    for key in PREFLOP_KEYS:
        composed_state[key] = preflop_state[key].detach().clone()

    payload = dict(postflop)
    payload.pop("optimizer", None)
    payload["model"] = composed_state
    payload["version"] = "pure.composed.preflop_postflop.v2"
    payload["policy_composition"] = {
        "schema": "pure.composed.preflop_postflop.v2",
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256_path(source_path),
        "preflop_checkpoint": str(preflop_path),
        "preflop_checkpoint_sha256": sha256_path(preflop_path),
        "postflop_checkpoint": str(postflop_path),
        "postflop_checkpoint_sha256": sha256_path(postflop_path),
        "preflop_learned_keys": sorted(PREFLOP_KEYS),
        "postflop_learned_keys": sorted(postflop_policy_changes),
        "postflop_auxiliary_changed_keys": sorted(
            postflop_common_changes - postflop_common_policy_changes
        ),
        "source_training_hands": int(source.get("total_hands") or 0),
        "preflop_decision_samples": int(
            (preflop.get("ingest") or {}).get("sampled_rows") or 0
        ),
        "postflop_decision_samples": int(
            (postflop.get("ingest") or {}).get("sampled_rows") or 0
        ),
        "postflop_lineage_training_hands": int(
            postflop.get("total_hands") or 0
        ),
        "postflop_new_training_hands": max(
            0,
            int(postflop.get("total_hands") or 0)
            - int(source.get("total_hands") or 0),
        ),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(output_path)

    report = {
        **payload["policy_composition"],
        "output_checkpoint": str(output_path),
        "output_checkpoint_sha256": sha256_path(output_path),
        "status": "COMPLETE",
    }
    report_path = output_path.with_suffix(".json")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
