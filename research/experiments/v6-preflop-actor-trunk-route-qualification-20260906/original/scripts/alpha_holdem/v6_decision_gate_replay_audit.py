"""Replay-complete optimizer and geometry audit for a decision-gate run."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_decision_expert_gate_smoke import ExpertGate, train_gate
from alpha_holdem.v6_decision_gate_gradient_conflict_audit import arrays_to_rows, load_transition_arrays
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--robust-mgda", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    optimizer_config = summary["optimizer"]
    if bool(optimizer_config["robust_mgda"]) != args.robust_mgda:
        raise ValueError("replay aggregator does not match run summary")
    reports = []
    for seed_index in range(3):
        checkpoint_path = args.run_dir / f"seed{seed_index}_gate.pt"
        payload = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        torch.manual_seed(int(payload["seed"]))
        gate = ExpertGate(int(payload["feature_dim"]), hidden=int(payload["hidden"])).to(args.device)
        optimizer = torch.optim.Adam(gate.parameters(), lr=float(optimizer_config["learning_rate"]))
        metrics = []
        transition_manifest = []
        for offset in (0, 1024, 2048, 3072):
            path = args.run_dir / f"seed{seed_index}_chunk{offset:05d}_transitions.npz"
            rows = arrays_to_rows(load_transition_arrays(path))
            chunk_metrics = train_gate(
                gate, optimizer, rows, epochs=int(optimizer_config["epochs_per_chunk"]),
                groups=12, device=args.device,
                reference_kl_coef=float(optimizer_config["reference_kl_coef"]),
                robust_mgda=args.robust_mgda,
            )
            metrics.extend({"chunk_offset": offset, **row} for row in chunk_metrics)
            transition_manifest.append({"path": str(path), "sha256": sha256_path(path), "rows": len(rows)})
        errors = {
            key: float((gate.state_dict()[key].detach().cpu() - payload["state_dict"][key].cpu()).abs().max())
            for key in payload["state_dict"]
        }
        reports.append({
            "seed_index": seed_index, "seed": int(payload["seed"]),
            "checkpoint_sha256": sha256_path(checkpoint_path),
            "endpoint_replay_max_abs_error": max(errors.values()),
            "transition_manifest": transition_manifest, "metrics": metrics,
        })
    all_metrics = [metric for report in reports for metric in report["metrics"]]
    output = {
        "schema": "cardpilot.decision_gate_replay_audit.v1", "status": "PASS",
        "run_summary_sha256": sha256_path(args.run_dir / "summary.json"),
        "robust_mgda": args.robust_mgda, "reports": reports,
        "total_transitions": sum(row["rows"] for report in reports for row in report["transition_manifest"]),
        "optimizer_steps": len(all_metrics),
        "endpoint_replay_max_abs_error": max(report["endpoint_replay_max_abs_error"] for report in reports),
        "minimum_applied_worst_alignment": (
            min(metric["applied_worst_alignment"] for metric in all_metrics) if args.robust_mgda else None
        ),
        "all_applied_worst_alignments_positive": (
            all(metric["applied_worst_alignment"] > 0 for metric in all_metrics) if args.robust_mgda else None
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: output[key] for key in (
        "status", "total_transitions", "optimizer_steps", "endpoint_replay_max_abs_error",
        "minimum_applied_worst_alignment", "all_applied_worst_alignments_positive",
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
