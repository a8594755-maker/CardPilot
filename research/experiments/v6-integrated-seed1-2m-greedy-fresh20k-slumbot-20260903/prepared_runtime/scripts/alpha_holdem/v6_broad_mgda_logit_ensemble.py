"""Frozen cross-seed logit ensemble feasibility for broad MGDA residuals."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_league_domain_feasibility import collect_balanced_states, sha256_path
from alpha_holdem.v6_broad_mgda_curve import (
    load_frozen_policy,
    play_evaluation_hand,
    source_preservation,
    summarize_evaluation,
    write_gzip_jsonl,
)
from alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95


class LogitEnsemble(nn.Module):
    """Average independently initialized residual policies in output space."""

    def __init__(self, members: list[DualContractResidualPolicy]):
        super().__init__()
        if len(members) < 2:
            raise ValueError("logit ensemble requires at least two members")
        self.members = nn.ModuleList(members)

    @property
    def base(self):
        return self.members[0].base

    def forward(self, *inputs):
        outputs = [member(*inputs) for member in self.members]
        # Anchor the mean on one member. Directly summing identical float32
        # -1e9 illegal-action sentinels can shift them by one ULP (64), even
        # though legal logits are small. Relative averaging preserves the
        # common sentinel exactly and is algebraically identical on legal slots.
        anchor_logits, anchor_values = outputs[0]
        logits = anchor_logits + torch.stack(
            [output[0] - anchor_logits for output in outputs]
        ).mean(dim=0)
        values = anchor_values + torch.stack(
            [output[1] - anchor_values for output in outputs]
        ).mean(dim=0)
        return logits, values


def paired_ensemble_gain(rows: list[dict], dose_hands: int) -> dict:
    selected = [row for row in rows if row["dose_hands"] == dose_hands]
    index = {
        (row["holdout_label"], row["pair_index"], row["candidate_label"]): row
        for row in selected
    }
    gains = []
    seat_gains = [[], []]
    for holdout, pair in sorted({(row["holdout_label"], row["pair_index"]) for row in selected}):
        ensemble = index[(holdout, pair, "ensemble")]
        constituents = [index[(holdout, pair, f"seed{seed}")] for seed in range(3)]
        gains.append(ensemble["delta_bb"] - float(np.mean([row["delta_bb"] for row in constituents])))
        for seat in (0, 1):
            seat_gains[seat].append(
                ensemble["seat_delta_bb"][seat]
                - float(np.mean([row["seat_delta_bb"][seat] for row in constituents]))
            )
    mean, half = mean_ci95(gains)
    seats = []
    for seat in (0, 1):
        local_mean, local_half = mean_ci95(seat_gains[seat])
        seats.append({
            "seat": seat,
            "gain_bb100": local_mean * 100.0,
            "gain_ci95_half_bb100": local_half * 100.0,
        })
    return {
        "dose_hands": dose_hands,
        "pairs": len(gains),
        "gain_vs_mean_constituent_bb100": mean * 100.0,
        "gain_ci95_half_bb100": half * 100.0,
        "seats": seats,
    }


def _load_prior_decks(path: Path) -> set[tuple[int, ...]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return {tuple(json.loads(line)["deck"]) for line in handle}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--pairs-per-holdout", type=int, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.pairs_per_holdout < 128:
        parser.error("pairs-per-holdout must be at least 128")
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
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base_sha = sha256_path(base_path)
    identity_checks = {
        "base_sha256_matches": prior["base_sha256"] == base_sha,
        "spec_sha256_matches": prior["spec_sha256"] == sha256_path(spec_path),
        "three_source_seeds": len({row["seed_index"] for row in prior["checkpoints"]}) == 3,
        "three_holdouts": len(spec["holdout_policies"]) == 3,
    }
    if not all(identity_checks.values()):
        raise ValueError(f"source identity mismatch: {identity_checks}")

    base_policy = load_policy(base_path, args.device)
    holdouts = [load_frozen_policy(entry, args.device) for entry in spec["holdout_policies"]]
    expected_holdouts = [(row["label"], row["sha256"]) for row in prior["holdout_policies"]]
    identity_checks["holdout_identities_match"] = [
        (policy.label, policy.sha256) for policy in holdouts
    ] == expected_holdouts
    if not identity_checks["holdout_identities_match"]:
        raise ValueError("holdout identities differ from source run")

    doses = ((2, 16384), (4, 32768), (8, 65536))
    models: dict[tuple[int, str], nn.Module] = {}
    checkpoint_rows = []
    for chunk_index, dose_hands in doses:
        members = []
        for seed_index in range(3):
            row = next(
                item for item in prior["checkpoints"]
                if item["seed_index"] == seed_index and item["chunk_index"] == chunk_index
            )
            checkpoint_path = Path(row["path"])
            if sha256_path(checkpoint_path) != row["sha256"]:
                raise ValueError(f"checkpoint hash mismatch: {checkpoint_path}")
            checkpoint = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
            if checkpoint["completed_environment_hands"] != dose_hands or checkpoint["base_sha256"] != base_sha:
                raise ValueError(f"checkpoint metadata mismatch: {checkpoint_path}")
            model = DualContractResidualPolicy(
                base_policy.model, hidden=128, policy_delta_cap=0.25
            ).to(args.device).eval()
            model.load_state_dict(checkpoint["residual_state_dict"], strict=False)
            members.append(model)
            models[(dose_hands, f"seed{seed_index}")] = model
            checkpoint_rows.append({
                "dose_hands": dose_hands,
                "seed_index": seed_index,
                "path": str(checkpoint_path.resolve()),
                "sha256": row["sha256"],
            })
        models[(dose_hands, "ensemble")] = LogitEnsemble(members).to(args.device).eval()

    prior_evidence_path = run_dir / "evaluation_pairs.jsonl.gz"
    if sha256_path(prior_evidence_path) != prior["evaluation_evidence_sha256"]:
        raise ValueError("source evaluation evidence hash mismatch")
    prior_decks = _load_prior_decks(prior_evidence_path)
    deck_rows = []
    for holdout_index, holdout in enumerate(holdouts):
        rng = random.Random(args.seed + 30_000_007 * (holdout_index + 1))
        for pair_index in range(args.pairs_per_holdout):
            deck = list(range(52))
            rng.shuffle(deck)
            if tuple(deck) in prior_decks:
                raise ValueError("fresh evaluation deck overlaps source evidence")
            controls = []
            for seat in (0, 1):
                reward, _ = play_evaluation_hand(
                    residual=models[(16384, "ensemble")],
                    base_policy=base_policy,
                    opponent=holdout,
                    deck=deck,
                    hero_seat=seat,
                    treatment=False,
                    device=args.device,
                )
                controls.append(reward)
            deck_rows.append({
                "holdout_index": holdout_index,
                "holdout_label": holdout.label,
                "holdout_sha256": holdout.sha256,
                "pair_index": pair_index,
                "deck": deck,
                "control_rewards_bb": controls,
            })

    evaluation_rows = []
    candidate_labels = ("seed0", "seed1", "seed2", "ensemble")
    max_delta = 0.0
    for _, dose_hands in doses:
        for candidate_label in candidate_labels:
            model = models[(dose_hands, candidate_label)]
            for deck_row in deck_rows:
                opponent = holdouts[deck_row["holdout_index"]]
                treatment_rewards = []
                for seat in (0, 1):
                    reward, observed = play_evaluation_hand(
                        residual=model,
                        base_policy=base_policy,
                        opponent=opponent,
                        deck=deck_row["deck"],
                        hero_seat=seat,
                        treatment=True,
                        device=args.device,
                    )
                    treatment_rewards.append(reward)
                    max_delta = max(max_delta, observed)
                seat_delta = [
                    treatment_rewards[seat] - deck_row["control_rewards_bb"][seat]
                    for seat in (0, 1)
                ]
                evaluation_rows.append({
                    **deck_row,
                    "dose_hands": dose_hands,
                    "candidate_label": candidate_label,
                    "treatment_rewards_bb": treatment_rewards,
                    "seat_delta_bb": seat_delta,
                    "delta_bb": sum(seat_delta) / 2.0,
                })
            print(f"dose={dose_hands} candidate={candidate_label} pairs={len(deck_rows)}", flush=True)

    evaluation_path = args.out_dir / "evaluation_pairs.jsonl.gz"
    write_gzip_jsonl(evaluation_path, evaluation_rows)
    curve = []
    for _, dose_hands in doses:
        for candidate_label in candidate_labels:
            selected = [
                row for row in evaluation_rows
                if row["dose_hands"] == dose_hands and row["candidate_label"] == candidate_label
            ]
            curve.append({
                "dose_hands": dose_hands,
                "candidate_label": candidate_label,
                **summarize_evaluation(selected),
            })
    ensemble_curve = [row for row in curve if row["candidate_label"] == "ensemble"]
    paired_gains = [paired_ensemble_gain(evaluation_rows, dose_hands) for _, dose_hands in doses]

    preservation_states = collect_balanced_states(4096, int(spec["seed"]) + 1777)
    preservation = []
    for _, dose_hands in doses:
        metrics = source_preservation(
            models[(dose_hands, "ensemble")], base_policy, preservation_states, args.device
        )
        preservation.append({"dose_hands": dose_hands, **metrics})

    first = next(row for row in ensemble_curve if row["dose_hands"] == 16384)
    final = next(row for row in ensemble_curve if row["dose_hands"] == 65536)
    final_gain = next(row for row in paired_gains if row["dose_hands"] == 65536)
    gates = {
        **identity_checks,
        "all_checkpoint_hashes_match": len(checkpoint_rows) == 9,
        "source_evidence_hash_matches": True,
        "fresh_decks_disjoint_from_source_evidence": True,
        "evaluation_row_count_exact": len(evaluation_rows) == len(doses) * len(candidate_labels) * len(deck_rows),
        "ensemble_source_overall_at_least_95pct_every_dose": all(
            row["overall_agreement"] >= 0.95 for row in preservation
        ),
        "ensemble_source_partitions_at_least_90pct_every_dose": all(
            row["minimum_partition_agreement"] >= 0.90 for row in preservation
        ),
        "residual_cap_respected": max_delta <= 0.250001,
        "ensemble_16k_to_65k_slope_positive": final["pooled_delta_bb100"] > first["pooled_delta_bb100"],
        "final_ensemble_pooled_delta_nonnegative": final["pooled_delta_bb100"] >= 0.0,
        "final_ensemble_at_least_two_holdouts_nonnegative": sum(
            row["delta_bb100"] >= 0.0 for row in final["holdouts"]
        ) >= 2,
        "final_ensemble_both_seats_nonnegative": all(
            row["delta_bb100"] >= 0.0 for row in final["seats"]
        ),
        "final_ensemble_gain_vs_mean_constituent_positive": (
            final_gain["gain_vs_mean_constituent_bb100"] > 0.0
        ),
    }
    admitted = all(gates.values())
    control_hands = len(deck_rows) * 2
    treatment_hands = len(evaluation_rows) * 2
    result = {
        "schema": "cardpilot.broad_mgda_logit_ensemble.v1",
        "status": "COMPLETED",
        "source_run": str(run_dir),
        "source_summary_sha256": sha256_path(run_dir / "summary.json"),
        "source_evaluation_sha256": sha256_path(prior_evidence_path),
        "base_sha256": base_sha,
        "spec_sha256": sha256_path(spec_path),
        "checkpoint_rows": checkpoint_rows,
        "holdout_policies": [
            {"label": policy.label, "sha256": policy.sha256, "observation_style": policy.observation_style}
            for policy in holdouts
        ],
        "fresh_evaluation_seed": args.seed,
        "pairs_per_holdout": args.pairs_per_holdout,
        "control_hands": control_hands,
        "treatment_hands": treatment_hands,
        "evaluation_hands": control_hands + treatment_hands,
        "evaluation_evidence_sha256": sha256_path(evaluation_path),
        "curve": curve,
        "ensemble_slope_16k_to_65k_bb100": final["pooled_delta_bb100"] - first["pooled_delta_bb100"],
        "paired_ensemble_gains": paired_gains,
        "source_preservation": preservation,
        "maximum_observed_residual_logit": max_delta,
        "gates": gates,
        "admitted": admitted,
        "decision": (
            "ADMIT_INDEPENDENT_LOGIT_ENSEMBLE_REPLICATION"
            if admitted else "CLOSE_CROSS_SEED_LOGIT_ENSEMBLE"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "evaluation_hands": result["evaluation_hands"],
        "ensemble_slope_bb100": result["ensemble_slope_16k_to_65k_bb100"],
        "gates": gates,
        "decision": result["decision"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
