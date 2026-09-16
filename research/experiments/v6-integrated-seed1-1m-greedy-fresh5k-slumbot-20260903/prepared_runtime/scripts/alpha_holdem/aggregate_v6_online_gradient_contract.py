"""Audit and summarize opt-in online opponent-seat PPO gradient geometry."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
import sys


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--first-iteration", type=int, required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--probes-per-iteration", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    metrics_path = args.run_dir / "h1_training_metrics.jsonl"
    manifest_path = args.run_dir / "run_manifest.json"
    checkpoint_path = args.run_dir / "latest.pt"
    rows = [
        json.loads(line)
        for line in metrics_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    wanted = list(range(args.first_iteration, args.first_iteration + args.iterations))
    selected = [row for row in rows if int(row["iteration"]) in wanted]
    probes = [
        probe
        for row in selected
        for probe in row.get("opponent_seat_gradient_diagnostics", [])
    ]
    by_objective: dict[str, list[float]] = defaultdict(list)
    for probe in probes:
        for name, alignment in zip(
            probe["objective_names"], probe["aggregate_alignments"]
        ):
            by_objective[name].append(float(alignment))

    iteration_coverage = [
        sum(
            float(probe["known_identity_fraction"])
            for probe in row.get("opponent_seat_gradient_diagnostics", [])
        ) / max(len(row.get("opponent_seat_gradient_diagnostics", [])), 1)
        for row in selected
    ]
    full_coverage = [
        probe for probe in probes
        if math.isclose(float(probe["known_identity_fraction"]), 1.0)
    ]
    finite = all(
        math.isfinite(float(value))
        for probe in probes
        for value in (
            probe["objective_gradient_l2"]
            + probe["aggregate_alignments"]
            + [probe["aggregate_gradient_l2"], probe["known_identity_fraction"]]
        )
    )
    gates = {
        "iterations_exact": [int(row["iteration"]) for row in selected] == wanted,
        "probe_count_exact": len(probes)
        == args.iterations * args.probes_per_iteration,
        "probe_schema_exact": all(
            probe.get("schema")
            == "cardpilot.ppo_opponent_seat_gradient_geometry.v1"
            for probe in probes
        ),
        "all_objective_support_positive": all(
            all(int(value) > 0 for value in probe["objective_support"].values())
            for probe in probes
        ),
        "finite_geometry": finite,
        "legacy_coverage_observed": bool(iteration_coverage)
        and iteration_coverage[0] < 1.0,
        "coverage_monotone": all(
            right + 1e-9 >= left
            for left, right in zip(iteration_coverage, iteration_coverage[1:])
        ),
        "full_coverage_reached": len(full_coverage)
        >= args.probes_per_iteration * 2,
        "source_kl_present": all(
            "source_kl" in probe["objective_names"] for probe in probes
        ),
        "manifest_finished": manifest.get("status") == "finished",
        "diagnostic_config_bound": int(
            manifest.get("config", {}).get(
                "opponent_seat_gradient_diagnostic_minibatches", -1
            )
        ) == args.probes_per_iteration // 2,
    }
    if not all(gates.values()):
        raise RuntimeError(f"online gradient contract gates failed: {gates}")

    objective_summary = {
        name: {
            "probes": len(values),
            "harmful_count": sum(value <= 0.0 for value in values),
            "mean_aggregate_alignment": sum(values) / len(values),
            "min_aggregate_alignment": min(values),
            "max_aggregate_alignment": max(values),
        }
        for name, values in sorted(by_objective.items())
    }
    all_probes_harmful = all(
        int(probe["aggregate_harmful_objective_count"]) > 0 for probe in probes
    )
    full_probes_harmful = all(
        int(probe["aggregate_harmful_objective_count"]) > 0
        for probe in full_coverage
    )
    result = {
        "schema": "cardpilot.integrated_online_gradient_contract.v1",
        "run_dir": str(args.run_dir.resolve()),
        "iterations": wanted,
        "probes": len(probes),
        "iteration_known_identity_fraction_mean": iteration_coverage,
        "full_coverage_probes": len(full_coverage),
        "all_probe_harmful_counts": [
            int(probe["aggregate_harmful_objective_count"]) for probe in probes
        ],
        "full_coverage_harmful_counts": [
            int(probe["aggregate_harmful_objective_count"])
            for probe in full_coverage
        ],
        "all_probes_have_harmful_objective": all_probes_harmful,
        "full_coverage_probes_have_harmful_objective": full_probes_harmful,
        "pairwise_negative_counts": [
            int(probe["pairwise_negative_count"]) for probe in probes
        ],
        "objective_summary": objective_summary,
        "gates": gates,
        "passed": all(gates.values()),
        "decision": (
            "ADMIT_ONLINE_CONFLICT_AWARE_TRAINER_SMOKE"
            if full_probes_harmful else "REJECT_ONLINE_CONFLICT_HYPOTHESIS"
        ),
        "hashes": {
            "metrics": sha256_path(metrics_path),
            "manifest": sha256_path(manifest_path),
            "checkpoint": sha256_path(checkpoint_path),
        },
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
