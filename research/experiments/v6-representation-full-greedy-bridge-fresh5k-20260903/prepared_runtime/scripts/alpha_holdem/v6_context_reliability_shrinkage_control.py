"""Fresh matched evaluation of fixed entropy shrinkage on frozen contextual policies."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.contextual_residual_v6 import PosteriorCenteredResidualPolicy
from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_broad_mgda_curve import load_frozen_policy
from alpha_holdem.v6_contextual_residual_mgda_smoke import greedy_reward, warmup_context
from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path
from alpha_holdem.v6_opponent_context_feasibility import context_features


def mean_ci95(values) -> dict:
    values = np.asarray(values, dtype=np.float64)
    half = 1.96 * float(values.std(ddof=1)) / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"units": len(values), "bb100": float(values.mean()) * 100.0, "ci95_half_bb100": half * 100.0}


def paired_units(rows: list[dict]) -> list[dict]:
    groups = {}
    for row in rows:
        groups.setdefault((row.get("seed_index", 0), row["opponent_label"], row["pair_index"]), []).append(row)
    units = []
    for (seed, label, pair), selected in sorted(groups.items()):
        if sorted(row["hero_seat"] for row in selected) != [0, 1] or selected[0]["deck"] != selected[1]["deck"]:
            raise ValueError("invalid paired-seat deck evidence")
        units.append({
            "seed_index": seed, "opponent_label": label, "pair_index": pair, "split": selected[0]["split"],
            "unshrunk_minus_base_bb": float(np.mean([r["unshrunk_minus_base_bb"] for r in selected])),
            "shrunk_minus_base_bb": float(np.mean([r["shrunk_minus_base_bb"] for r in selected])),
            "shrunk_minus_unshrunk_bb": float(np.mean([r["shrunk_minus_unshrunk_bb"] for r in selected])),
        })
    return units


def summarize(rows: list[dict]) -> dict:
    units = paired_units(rows)
    keys = ("unshrunk_minus_base_bb", "shrunk_minus_base_bb", "shrunk_minus_unshrunk_bb")
    result = {"paired_deck_units": len(units), "pooled": {key: mean_ci95([r[key] for r in units]) for key in keys}}
    result["splits"] = {}
    for split in ("training", "holdout"):
        selected = [r for r in units if r["split"] == split]
        result["splits"][split] = {key: mean_ci95([r[key] for r in selected]) for key in keys}
    result["seats"] = {}
    for seat in (0, 1):
        selected = [r for r in rows if r["hero_seat"] == seat]
        result["seats"][str(seat)] = {key: mean_ci95([r[key] for r in selected]) for key in keys}
    return result


def write_gz(path: Path, rows: list[dict]):
    with gzip.open(path, "xt", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--context-classifier", type=Path, required=True)
    parser.add_argument("--expected-context-classifier-sha256", required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--expected-checkpoint-sha256", action="append", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--warmup-hands", type=int, default=64)
    parser.add_argument("--pairs-per-policy", type=int, default=128)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--aggregate-existing", action="store_true")
    args = parser.parse_args()
    if len(args.checkpoint) != len(args.expected_checkpoint_sha256) or len(args.checkpoint) < 2:
        parser.error("checkpoint and SHA lists must match and contain at least two seeds")
    if args.out_dir.exists() and not args.aggregate_existing:
        raise FileExistsError(args.out_dir)
    classifier_sha = sha256_path(args.context_classifier)
    if classifier_sha != args.expected_context_classifier_sha256:
        raise ValueError("classifier SHA mismatch")
    started = time.time()
    if args.aggregate_existing:
        missing = [args.out_dir / f"seed{index}_fresh_evaluation.jsonl.gz" for index in range(len(args.checkpoint)) if not (args.out_dir / f"seed{index}_fresh_evaluation.jsonl.gz").is_file()]
        if missing:
            raise FileNotFoundError(f"aggregate-only recovery is missing evidence: {missing}")
        seed_results = []
        all_rows = []
        for seed_index, checkpoint_path in enumerate(args.checkpoint):
            checkpoint_sha = sha256_path(checkpoint_path)
            if checkpoint_sha != args.expected_checkpoint_sha256[seed_index]:
                raise ValueError(f"seed {seed_index} checkpoint SHA mismatch")
            evidence_path = args.out_dir / f"seed{seed_index}_fresh_evaluation.jsonl.gz"
            with gzip.open(evidence_path, "rt", encoding="utf-8") as handle:
                selected = [row for row in map(json.loads, handle) if "shrunk_minus_base_bb" in row]
            all_rows.extend(selected)
            seed_results.append({
                "seed_index": seed_index, "checkpoint_sha256": checkpoint_sha,
                "evaluation_environment_hands": 9 * 2 * args.warmup_hands + 3 * len(selected),
                "reliability_mean": None, "evaluation": summarize(selected),
                "evidence_sha256": sha256_path(evidence_path), "recovered_from_complete_raw_evidence": True,
            })
        pooled = summarize(all_rows)
        gates = {
            "all_artifact_hashes_exact": True,
            "evaluation_hands_exact": sum(r["evaluation_environment_hands"] for r in seed_results) == len(args.checkpoint) * (9 * 2 * args.warmup_hands + 9 * 2 * args.pairs_per_policy * 3),
            "both_seed_shrunk_minus_base_nonnegative": all(r["evaluation"]["pooled"]["shrunk_minus_base_bb"]["bb100"] >= 0 for r in seed_results),
            "both_seats_shrunk_minus_base_nonnegative": all(pooled["seats"][str(seat)]["shrunk_minus_base_bb"]["bb100"] >= 0 for seat in (0, 1)),
            "training_shrunk_minus_base_nonnegative": pooled["splits"]["training"]["shrunk_minus_base_bb"]["bb100"] >= 0,
            "holdout_shrunk_minus_base_nonnegative": pooled["splits"]["holdout"]["shrunk_minus_base_bb"]["bb100"] >= 0,
            "holdout_shrink_improves_unshrunk": pooled["splits"]["holdout"]["shrunk_minus_unshrunk_bb"]["bb100"] > 0,
        }
        admitted = all(gates.values())
        summary = {
            "schema": "cardpilot.context_reliability_shrinkage_control.v1", "status": "COMPLETED",
            "claim_scope": "FROZEN_BROAD_LEAGUE_CONTROL_NOT_SLUMBOT_STRENGTH", "new_environment_training_hands": 0,
            "evaluation_hands": sum(r["evaluation_environment_hands"] for r in seed_results),
            "classifier_sha256": classifier_sha, "reliability_power": 1.0,
            "seed_results": seed_results, "pooled": pooled, "gates": gates, "admitted": admitted,
            "decision": "ADMIT_RELIABILITY_SHRUNK_CONTEXTUAL_SCALE" if admitted else "REJECT_FIXED_RELIABILITY_SHRINKAGE",
            "aggregation_recovery": "seed_index_added_to_paired_unit_key; no hands regenerated",
            "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
            "command": [sys.executable, *sys.argv],
        }
        (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"evaluation_hands": summary["evaluation_hands"], "gates": gates, "decision": summary["decision"]}, sort_keys=True))
        return
    args.out_dir.mkdir(parents=True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    classifier = torch.load(args.context_classifier, map_location="cpu", weights_only=False)["models"]["64"]
    base_policy = load_policy(args.base_checkpoint, args.device)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    training = [load_frozen_policy(row, args.device) for row in spec["training_policies"]]
    holdouts = [load_frozen_policy(row, args.device) for row in spec["holdout_policies"]]
    policies = [("training", row) for row in training] + [("holdout", row) for row in holdouts]
    seed_results = []
    for seed_index, checkpoint_path in enumerate(args.checkpoint):
        checkpoint_sha = sha256_path(checkpoint_path)
        if checkpoint_sha != args.expected_checkpoint_sha256[seed_index]:
            raise ValueError(f"seed {seed_index} checkpoint SHA mismatch")
        payload = torch.load(checkpoint_path, map_location=args.device, weights_only=False)
        unshrunk = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=0).to(args.device).eval()
        shrunk = PosteriorCenteredResidualPolicy(base_policy.model, classifier, reliability_power=1).to(args.device).eval()
        for model in (unshrunk, shrunk):
            missing, unexpected = model.load_state_dict(payload["residual_state_dict"], strict=False)
            if unexpected or any(not name.startswith("base.") for name in missing):
                raise ValueError("invalid frozen checkpoint keys")
        run_seed = args.seed + seed_index * 10_007
        contexts = {}
        warmup_rows = []
        reliability = {"training": [], "holdout": []}
        for index, (split, opponent) in enumerate(policies):
            for seat in (0, 1):
                counts, local = warmup_context(base_policy, opponent, hero_seat=seat, hands=args.warmup_hands, seed=run_seed + index * 900_001 + seat * 70_001)
                context = context_features(counts)
                contexts[(index, seat)] = context
                with torch.no_grad():
                    posterior = unshrunk.context_posterior(torch.as_tensor(context, dtype=torch.float32, device=args.device).unsqueeze(0))[0]
                    entropy = float(-(posterior * posterior.clamp_min(1e-15).log()).sum().cpu())
                reliability[split].append(1.0 - entropy / math.log(unshrunk.classes))
                for row in local:
                    row.update({"seed_index": seed_index, "opponent_index": index, "opponent_label": opponent.label, "split": split})
                warmup_rows.extend(local)
        rows = []
        for index, (split, opponent) in enumerate(policies):
            rng = random.Random(run_seed + 40_000_003 * (index + 1))
            for pair_index in range(args.pairs_per_policy):
                deck = list(range(52))
                rng.shuffle(deck)
                for seat in (0, 1):
                    context = contexts[(index, seat)]
                    base, _ = greedy_reward(unshrunk, base_policy, opponent, deck, seat, context, args.device, "base")
                    plain, _ = greedy_reward(unshrunk, base_policy, opponent, deck, seat, context, args.device, "candidate")
                    safe, _ = greedy_reward(shrunk, base_policy, opponent, deck, seat, context, args.device, "candidate")
                    rows.append({
                        "seed_index": seed_index, "split": split, "opponent_index": index,
                        "opponent_label": opponent.label, "opponent_sha256": opponent.sha256,
                        "pair_index": pair_index, "hero_seat": seat, "deck": deck,
                        "base_reward_bb": base, "unshrunk_reward_bb": plain, "shrunk_reward_bb": safe,
                        "unshrunk_minus_base_bb": plain - base, "shrunk_minus_base_bb": safe - base,
                        "shrunk_minus_unshrunk_bb": safe - plain,
                    })
        evidence_path = args.out_dir / f"seed{seed_index}_fresh_evaluation.jsonl.gz"
        write_gz(evidence_path, warmup_rows + rows)
        seed_results.append({
            "seed_index": seed_index, "checkpoint_sha256": checkpoint_sha,
            "evaluation_environment_hands": len(warmup_rows) + 3 * len(rows),
            "reliability_mean": {split: float(np.mean(values)) for split, values in reliability.items()},
            "evaluation": summarize(rows), "evidence_sha256": sha256_path(evidence_path),
        })
        print(json.dumps({"seed": seed_index, "evaluation": seed_results[-1]["evaluation"]["pooled"]}), flush=True)
    all_rows = []
    for seed_index in range(len(args.checkpoint)):
        with gzip.open(args.out_dir / f"seed{seed_index}_fresh_evaluation.jsonl.gz", "rt", encoding="utf-8") as handle:
            all_rows.extend(row for row in map(json.loads, handle) if "shrunk_minus_base_bb" in row)
    pooled = summarize(all_rows)
    gates = {
        "all_artifact_hashes_exact": True,
        "evaluation_hands_exact": sum(r["evaluation_environment_hands"] for r in seed_results) == len(args.checkpoint) * (9 * 2 * args.warmup_hands + 9 * 2 * args.pairs_per_policy * 3),
        "both_seed_shrunk_minus_base_nonnegative": all(r["evaluation"]["pooled"]["shrunk_minus_base_bb"]["bb100"] >= 0 for r in seed_results),
        "both_seats_shrunk_minus_base_nonnegative": all(pooled["seats"][str(seat)]["shrunk_minus_base_bb"]["bb100"] >= 0 for seat in (0, 1)),
        "training_shrunk_minus_base_nonnegative": pooled["splits"]["training"]["shrunk_minus_base_bb"]["bb100"] >= 0,
        "holdout_shrunk_minus_base_nonnegative": pooled["splits"]["holdout"]["shrunk_minus_base_bb"]["bb100"] >= 0,
        "holdout_shrink_improves_unshrunk": pooled["splits"]["holdout"]["shrunk_minus_unshrunk_bb"]["bb100"] > 0,
    }
    admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.context_reliability_shrinkage_control.v1", "status": "COMPLETED",
        "claim_scope": "FROZEN_BROAD_LEAGUE_CONTROL_NOT_SLUMBOT_STRENGTH", "new_environment_training_hands": 0,
        "evaluation_hands": sum(r["evaluation_environment_hands"] for r in seed_results),
        "classifier_sha256": classifier_sha, "reliability_power": 1.0,
        "seed_results": seed_results, "pooled": pooled, "gates": gates, "admitted": admitted,
        "decision": "ADMIT_RELIABILITY_SHRUNK_CONTEXTUAL_SCALE" if admitted else "REJECT_FIXED_RELIABILITY_SHRINKAGE",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"evaluation_hands": summary["evaluation_hands"], "gates": gates, "decision": summary["decision"]}, sort_keys=True))


if __name__ == "__main__":
    main()
