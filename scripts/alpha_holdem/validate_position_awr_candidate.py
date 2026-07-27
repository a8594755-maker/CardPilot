"""Validate a seat-isolated offline-AWR checkpoint before external play."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

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
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--training-report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-source-kl", type=float, default=0.02)
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    candidate_path = Path(args.candidate).resolve()
    report_path = Path(args.training_report).resolve()
    output_path = Path(args.out).resolve()

    source = torch.load(source_path, map_location="cpu", weights_only=False)
    candidate = torch.load(
        candidate_path,
        map_location="cpu",
        weights_only=False,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source_state = source["model"]
    candidate_state = candidate["model"]

    source_changes = [
        key
        for key, source_value in source_state.items()
        if key not in candidate_state
        or not torch.equal(source_value, candidate_state[key])
    ]
    extra_keys = sorted(set(candidate_state) - set(source_state))
    expected_extra_keys = sorted(
        f"position_policy_adapters.{seat}.{layer}.{parameter}"
        for seat in (0, 1)
        for layer in (0, 2)
        for parameter in ("weight", "bias")
    )
    adapter0_output_nonzero = sum(
        int(torch.count_nonzero(value))
        for key, value in candidate_state.items()
        if key.startswith("position_policy_adapters.0.2.")
    )
    adapter1_output_nonzero = sum(
        int(torch.count_nonzero(value))
        for key, value in candidate_state.items()
        if key.startswith("position_policy_adapters.1.2.")
    )

    selected_epoch = int(candidate["epoch"])
    selected_metrics = next(
        row
        for row in report["history"]
        if int(row["epoch"]) == selected_epoch
    )
    baseline_weighted_nll = float(report["baseline"]["weighted_nll"])
    selected_objective = float(selected_metrics["validation_objective"])
    selected_source_kl = float(selected_metrics["source_kl"])
    checks: dict[str, bool] = {
        "source_tensors_bitwise_unchanged": not source_changes,
        "only_position_adapter_keys_added": (
            extra_keys == expected_extra_keys
        ),
        "bb_output_residual_trained": adapter0_output_nonzero > 0,
        "sb_output_residual_exact_zero": adapter1_output_nonzero == 0,
        "position_adapter_metadata_present": (
            int(candidate.get("position_adapter_hidden", 0)) > 0
        ),
        "validation_objective_improved": (
            selected_objective < baseline_weighted_nll
        ),
        "validation_source_kl_bounded": (
            selected_source_kl <= args.max_source_kl
        ),
    }
    decision = (
        "READY_FOR_PURE_FRESH5K"
        if all(checks.values())
        else "REJECT_INTERNAL_GATE"
    )
    result: dict[str, Any] = {
        "schema": "cardpilot.position_awr_validation.v1",
        "source": str(source_path),
        "source_sha256": sha256_path(source_path),
        "candidate": str(candidate_path),
        "candidate_sha256": sha256_path(candidate_path),
        "training_report": str(report_path),
        "selected_epoch": selected_epoch,
        "position_adapter_hidden": int(
            candidate.get("position_adapter_hidden", 0)
        ),
        "baseline_weighted_nll": baseline_weighted_nll,
        "selected_validation_objective": selected_objective,
        "selected_source_kl": selected_source_kl,
        "max_source_kl": args.max_source_kl,
        "source_changes": source_changes,
        "extra_keys": extra_keys,
        "adapter0_output_nonzero": adapter0_output_nonzero,
        "adapter1_output_nonzero": adapter1_output_nonzero,
        "checks": checks,
        "decision": decision,
    }
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    if decision != "READY_FOR_PURE_FRESH5K":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
