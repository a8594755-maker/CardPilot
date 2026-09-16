"""Audit base-exact arithmetic for a frozen cross-seed logit ensemble."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states, sha256_path
from alpha_holdem.v6_dual_contract_residual_training_smoke import state_inputs
from alpha_holdem.v6_broad_mgda_logit_ensemble import LogitEnsemble


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--dose-hands", type=int, required=True)
    parser.add_argument("--states", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.states < 512:
        parser.error("states must be at least 512")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()

    run_dir = args.run_dir.resolve()
    spec_path = args.spec.resolve()
    base_path = args.base_checkpoint.resolve()
    prior = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    base_sha = sha256_path(base_path)
    if prior["base_sha256"] != base_sha or prior["spec_sha256"] != sha256_path(spec_path):
        raise ValueError("source run identity mismatch")
    base_policy = load_policy(base_path, args.device)

    members = []
    checkpoint_rows = []
    for seed_index in range(3):
        row = next(
            item for item in prior["checkpoints"]
            if item["seed_index"] == seed_index and item["hands"] == args.dose_hands
        )
        checkpoint_path = Path(row["path"])
        if sha256_path(checkpoint_path) != row["sha256"]:
            raise ValueError(f"checkpoint hash mismatch: {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
        model = DualContractResidualPolicy(
            base_policy.model, hidden=128, policy_delta_cap=0.25
        ).to(args.device).eval()
        model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
        members.append(model)
        checkpoint_rows.append({
            "seed_index": seed_index,
            "path": str(checkpoint_path.resolve()),
            "sha256": row["sha256"],
        })
    ensemble = LogitEnsemble(members).to(args.device).eval()
    states = collect_balanced_states(args.states, args.seed)

    action_matches = 0
    max_legal_logit_change = 0.0
    max_old_all_slot_delta = 0.0
    max_new_all_slot_delta = 0.0
    max_old_legal_delta = 0.0
    max_new_legal_delta = 0.0
    with torch.inference_mode():
        for state in states:
            inputs, _, _ = state_inputs(base_policy, state, args.device)
            outputs = [member(*inputs) for member in members]
            old_logits = torch.stack([output[0] for output in outputs]).mean(dim=0)
            new_logits, _ = ensemble(*inputs)
            base_logits = ensemble.base(inputs[0], inputs[1], inputs[2], inputs[6])[0]
            legal = torch.nonzero(inputs[6][0] > 0.5, as_tuple=False).flatten()
            old_action = legal[old_logits[0, legal].argmax()].item()
            new_action = legal[new_logits[0, legal].argmax()].item()
            action_matches += int(old_action == new_action)
            max_legal_logit_change = max(
                max_legal_logit_change,
                float((old_logits[0, legal] - new_logits[0, legal]).abs().max()),
            )
            max_old_all_slot_delta = max(
                max_old_all_slot_delta, float((old_logits - base_logits).abs().max())
            )
            max_new_all_slot_delta = max(
                max_new_all_slot_delta, float((new_logits - base_logits).abs().max())
            )
            max_old_legal_delta = max(
                max_old_legal_delta,
                float((old_logits[0, legal] - base_logits[0, legal]).abs().max()),
            )
            max_new_legal_delta = max(
                max_new_legal_delta,
                float((new_logits[0, legal] - base_logits[0, legal]).abs().max()),
            )

    gates = {
        "three_checkpoint_hashes_match": len(checkpoint_rows) == 3,
        "all_old_new_greedy_actions_match": action_matches == len(states),
        "maximum_legal_logit_change_at_most_1e_5": max_legal_logit_change <= 1e-5,
        "old_all_slot_sentinel_artifact_reproduced": max_old_all_slot_delta >= 1.0,
        "old_legal_residual_cap_respected": max_old_legal_delta <= 0.250001,
        "new_all_slot_residual_cap_respected": max_new_all_slot_delta <= 0.250001,
        "new_legal_residual_cap_respected": max_new_legal_delta <= 0.250001,
    }
    passed = all(gates.values())
    result = {
        "schema": "cardpilot.logit_ensemble_contract_audit.v1",
        "status": "COMPLETED",
        "source_run": str(run_dir),
        "source_summary_sha256": sha256_path(run_dir / "summary.json"),
        "base_sha256": base_sha,
        "spec_sha256": sha256_path(spec_path),
        "dose_hands": args.dose_hands,
        "states": len(states),
        "checkpoint_rows": checkpoint_rows,
        "action_matches": action_matches,
        "max_legal_logit_change": max_legal_logit_change,
        "max_old_all_slot_delta": max_old_all_slot_delta,
        "max_new_all_slot_delta": max_new_all_slot_delta,
        "max_old_legal_delta": max_old_legal_delta,
        "max_new_legal_delta": max_new_legal_delta,
        "gates": gates,
        "passed": passed,
        "decision": "ENSEMBLE_BASE_EXACT_REPAIR_VERIFIED" if passed else "ENSEMBLE_REPAIR_FAILED",
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "states": len(states),
        "action_matches": action_matches,
        "max_legal_logit_change": max_legal_logit_change,
        "max_old_all_slot_delta": max_old_all_slot_delta,
        "max_new_all_slot_delta": max_new_all_slot_delta,
        "gates": gates,
        "decision": result["decision"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
