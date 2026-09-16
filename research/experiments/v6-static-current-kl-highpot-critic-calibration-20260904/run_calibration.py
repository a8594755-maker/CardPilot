"""Fresh internal on-policy critic-calibration audit for 262k versus 1M endpoints."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import _observation

GAMMA = 0.999
VALUE_SCALE = 200.0
BUCKETS = ("lt10", "10to30", "ge30")
ANCHORS = (
    ("standard10", REPO / "models/baseline/standard10/latest.pt"),
    ("cfr4", REPO / "research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt"),
    ("legacy_iter16", REPO / "research/experiments/v6-legacy-iter16-greedy-fresh20k-20260901/frozen/final.pt"),
    ("legacy_mixed65k", REPO / "research/experiments/v6-legacy-contract-mixed-league-65k-pilot-20260901/training/latest.pt"),
)
PRIOR_RAW_GLOBS = (
    "research/experiments/v6-static-current-kl-262k-scale-20260903/eval_seed*/common_deck_pairs.jsonl.gz",
    "research/experiments/v6-static-current-kl-262k-fresh-confirmation-20260903/eval_seed*/common_deck_pairs.jsonl.gz",
    "research/experiments/v6-static-current-kl-1m-scale-20260903/eval_seed*/common_deck_pairs.jsonl.gz",
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deck_digest(deck: list[int] | tuple[int, ...]) -> str:
    return hashlib.sha256(bytes(deck)).hexdigest()


def pot_bucket(pot_bb: float) -> str:
    if pot_bb < 10.0:
        return "lt10"
    if pot_bb < 30.0:
        return "10to30"
    return "ge30"


def mean_ci(values: list[float]) -> dict[str, float | int]:
    array = np.asarray(values, dtype=np.float64)
    count = int(array.size)
    mean = float(array.mean()) if count else float("nan")
    half = float(1.96 * array.std(ddof=1) / math.sqrt(count)) if count > 1 else float("nan")
    return {
        "count": count,
        "mean": mean,
        "ci95_low": mean - half if count > 1 else float("nan"),
        "ci95_high": mean + half if count > 1 else float("nan"),
        "ci95_halfwidth": half,
    }


def calibration_stats(rows: list[dict]) -> dict:
    predictions = np.asarray([row["prediction_bb"] for row in rows], dtype=np.float64)
    targets = np.asarray([row["target_bb"] for row in rows], dtype=np.float64)
    residuals = targets - predictions
    if len(rows) >= 2 and float(np.var(predictions)) > 1e-12:
        slope, intercept = np.polyfit(predictions, targets, 1)
    else:
        slope = intercept = float("nan")
    residual_ci = mean_ci(residuals.tolist())
    return {
        "count": len(rows),
        "prediction_mean_bb": float(predictions.mean()) if len(rows) else float("nan"),
        "target_mean_bb": float(targets.mean()) if len(rows) else float("nan"),
        "residual_bias_bb": residual_ci["mean"],
        "residual_ci95_low_bb": residual_ci["ci95_low"],
        "residual_ci95_high_bb": residual_ci["ci95_high"],
        "mae_bb": float(np.mean(np.abs(residuals))) if len(rows) else float("nan"),
        "rmse_bb": float(np.sqrt(np.mean(np.square(residuals)))) if len(rows) else float("nan"),
        "calibration_intercept_bb": float(intercept),
        "calibration_slope": float(slope),
    }


def paired_delta(control: dict, treatment: dict, *, squared: bool) -> float:
    c = float(control["target_bb"]) - float(control["prediction_bb"])
    t = float(treatment["target_bb"]) - float(treatment["prediction_bb"])
    if squared:
        return t * t - c * c
    return abs(t) - abs(c)


def load_prior_decks() -> tuple[set[str], dict[str, str]]:
    digests: set[str] = set()
    hashes: dict[str, str] = {}
    for pattern in PRIOR_RAW_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            hashes[str(path.relative_to(REPO))] = sha256_path(path)
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    row = json.loads(line)
                    digests.add(deck_digest(row["deck"]))
    if not hashes:
        raise RuntimeError("no prior raw deck evidence found")
    return digests, hashes


@torch.no_grad()
def act_and_value(model, state: ChipState, device: str):
    obs, action_table = _observation(model, state, "legacy_v4")
    tensors = [
        torch.as_tensor(obs[key], dtype=torch.float32, device=device).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, value = model(*tensors)
    legal = np.flatnonzero(obs["legal_mask"])
    scores = logits[0].detach().cpu().numpy().astype(np.float64)
    if not len(legal) or not np.isfinite(scores[legal]).all():
        raise RuntimeError("invalid legal policy logits")
    slot = int(legal[int(np.argmax(scores[legal]))])
    action = action_table[slot]
    if action is None:
        raise RuntimeError("selected empty action slot")
    value_bb = float(value.squeeze().detach().cpu()) * VALUE_SCALE
    if not math.isfinite(value_bb):
        raise RuntimeError("non-finite critic value")
    return action, value_bb


def play_hand(candidate, anchor, deck, *, candidate_seat: int, device: str) -> list[dict]:
    state = ChipState.new(deck)
    retained: dict[str, dict] = {}
    candidate_decisions = 0
    while not state.terminal:
        if state.actor == candidate_seat:
            action, value_bb = act_and_value(candidate, state, device)
            bucket = pot_bucket(float(state.pot) / 100.0)
            if bucket not in retained:
                retained[bucket] = {
                    "bucket": bucket,
                    "street": int(state.street),
                    "pot_bb": float(state.pot) / 100.0,
                    "exposure_bb": float(state.initial[candidate_seat] - state.stacks[candidate_seat]) / 100.0,
                    "prediction_bb": value_bb,
                    "candidate_decision_index": candidate_decisions,
                }
            candidate_decisions += 1
        else:
            action, _ = act_and_value(anchor, state, device)
        state = apply_incr(state, action)
    reward_bb = float(state.payoffs()[candidate_seat]) / 100.0
    for row in retained.values():
        remaining = candidate_decisions - int(row["candidate_decision_index"]) - 1
        row["candidate_decisions_total"] = candidate_decisions
        row["remaining_candidate_decisions"] = remaining
        row["terminal_reward_bb"] = reward_bb
        row["target_bb"] = reward_bb * (GAMMA ** remaining)
        row["residual_bb"] = row["target_bb"] - row["prediction_bb"]
    return [retained[bucket] for bucket in BUCKETS if bucket in retained]


def analyze(rows: list[dict]) -> dict:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["policy"], row["seed"], row["bucket"])].append(row)
    descriptive = {}
    for (policy, seed, bucket), values in sorted(grouped.items()):
        descriptive.setdefault(policy, {}).setdefault(str(seed), {})[bucket] = calibration_stats(values)

    lookup = {
        (row["policy"], row["seed"], row["anchor"], row["pair_index"], row["candidate_seat"], row["bucket"]): row
        for row in rows
    }
    high_by_seed: dict[int, list[float]] = defaultdict(list)
    high_abs_by_seed: dict[int, list[float]] = defaultdict(list)
    did_by_seed: dict[int, list[float]] = defaultdict(list)
    for seed in sorted({int(row["seed"]) for row in rows}):
        identities = sorted({
            (row["anchor"], int(row["pair_index"]), int(row["candidate_seat"]))
            for row in rows if int(row["seed"]) == seed
        })
        for anchor, pair_index, seat in identities:
            def get(policy, bucket):
                return lookup.get((policy, seed, anchor, pair_index, seat, bucket))
            ch, th = get("control262k", "ge30"), get("treatment1m", "ge30")
            if ch is None or th is None:
                continue
            high = paired_delta(ch, th, squared=True)
            high_by_seed[seed].append(high)
            high_abs_by_seed[seed].append(paired_delta(ch, th, squared=False))
            cl, tl = get("control262k", "lt10"), get("treatment1m", "lt10")
            if cl is not None and tl is not None:
                did_by_seed[seed].append(high - paired_delta(cl, tl, squared=True))

    all_high = [value for seed in sorted(high_by_seed) for value in high_by_seed[seed]]
    all_high_abs = [value for seed in sorted(high_abs_by_seed) for value in high_abs_by_seed[seed]]
    all_did = [value for seed in sorted(did_by_seed) for value in did_by_seed[seed]]
    comparisons = {
        "highpot_squared_error_delta_by_seed": {str(seed): mean_ci(values) for seed, values in sorted(high_by_seed.items())},
        "highpot_absolute_error_delta_by_seed": {str(seed): mean_ci(values) for seed, values in sorted(high_abs_by_seed.items())},
        "highpot_specific_squared_error_did_by_seed": {str(seed): mean_ci(values) for seed, values in sorted(did_by_seed.items())},
        "pooled_highpot_squared_error_delta": mean_ci(all_high),
        "pooled_highpot_absolute_error_delta": mean_ci(all_high_abs),
        "pooled_highpot_specific_squared_error_did": mean_ci(all_did),
    }
    seeds = sorted(high_by_seed)
    count_gate = len(seeds) == 3 and all(len(high_by_seed[seed]) >= 100 for seed in seeds)
    positive_high_seeds = sum(mean_ci(high_by_seed[s])["mean"] > 0 for s in seeds)
    positive_did_seeds = sum(mean_ci(did_by_seed[s])["mean"] > 0 for s in seeds if did_by_seed[s])
    pooled_high = comparisons["pooled_highpot_squared_error_delta"]
    pooled_did = comparisons["pooled_highpot_specific_squared_error_did"]
    biased_seeds = 0
    bias_signs = []
    for seed in seeds:
        stat = descriptive["treatment1m"][str(seed)]["ge30"]
        excludes = stat["residual_ci95_low_bb"] > 0 or stat["residual_ci95_high_bb"] < 0
        if excludes:
            biased_seeds += 1
            bias_signs.append(1 if stat["residual_bias_bb"] > 0 else -1)
    same_sign_bias = biased_seeds >= 2 and (bias_signs.count(1) >= 2 or bias_signs.count(-1) >= 2)
    gates = {
        "at_least_100_common_highpot_per_seed": count_gate,
        "positive_highpot_squared_error_delta_at_least_two_seeds": positive_high_seeds >= 2,
        "pooled_highpot_squared_error_delta_ci_low_above_zero": pooled_high["ci95_low"] > 0,
        "positive_highpot_specific_did_at_least_two_seeds": positive_did_seeds >= 2,
        "pooled_highpot_specific_did_ci_low_above_zero": pooled_did["ci95_low"] > 0,
        "treatment_highpot_bias_same_sign_significant_at_least_two_seeds": same_sign_bias,
    }
    admit = all(gates.values())
    return {
        "descriptive": descriptive,
        "comparisons": comparisons,
        "gates": gates,
        "decision": "ADMIT_GENERAL_HIGHPOT_VALUE_INTERVENTION" if admit else "NO_HIGHPOT_VALUE_INTERVENTION",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs-per-anchor", type=int, default=512)
    parser.add_argument("--seed-base", type=int, default=20263120)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    if args.pairs_per_anchor < 2:
        parser.error("pairs-per-anchor must be at least two")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.time()
    prior_decks, prior_hashes = load_prior_decks()
    inputs: dict[str, Path] = {}
    for seed in (1, 2, 3):
        inputs[f"control262k_seed{seed}"] = REPO / f"research/experiments/v6-static-current-kl-262k-scale-20260903/seed{seed}/latest.pt"
        inputs[f"treatment1m_seed{seed}"] = REPO / f"research/experiments/v6-static-current-kl-1m-scale-20260903/seed{seed}/latest.pt"
    inputs.update({f"anchor:{name}": path for name, path in ANCHORS})
    input_hashes = {name: sha256_path(path) for name, path in inputs.items()}
    checkpoints = {name: read_checkpoint(path) for name, path in inputs.items()}
    for name in [key for key in checkpoints if key.startswith(("control", "treatment"))]:
        checkpoint = checkpoints[name]
        contract = checkpoint.get("critic_contract") or (checkpoint.get("config") or {}).get("critic_contract")
        divisor = (checkpoint.get("config") or {}).get("h1_effective_stack_divisor", 200.0)
        if contract != "critic_v2" or float(divisor) != VALUE_SCALE:
            raise RuntimeError(f"{name} lacks required critic_v2/200 contract")

    raw_path = args.out_dir / "calibration_raw.jsonl.gz"
    summary_path = args.out_dir / "analysis.json"
    if raw_path.exists() or summary_path.exists():
        raise FileExistsError("refusing to overwrite completed calibration evidence")
    rows: list[dict] = []
    generated_decks: set[str] = set()
    with gzip.open(raw_path, "xt", encoding="utf-8", newline="\n") as raw:
        for seed in (1, 2, 3):
            control = init_model(checkpoints[f"control262k_seed{seed}"], args.device).eval()
            treatment = init_model(checkpoints[f"treatment1m_seed{seed}"], args.device).eval()
            for anchor_index, (anchor_name, _) in enumerate(ANCHORS):
                anchor = init_model(checkpoints[f"anchor:{anchor_name}"], args.device).eval()
                rng_seed = int(args.seed_base) + seed + 1_000_003 * anchor_index
                rng = random.Random(rng_seed)
                decks = []
                for pair_index in range(args.pairs_per_anchor):
                    deck = list(range(52))
                    rng.shuffle(deck)
                    digest = deck_digest(deck)
                    if digest in generated_decks or digest in prior_decks:
                        raise RuntimeError("fresh-deck uniqueness/disjointness violation")
                    generated_decks.add(digest)
                    decks.append((pair_index, deck, digest))
                for policy_name, candidate in (("control262k", control), ("treatment1m", treatment)):
                    for pair_index, deck, digest in decks:
                        for seat in (0, 1):
                            hand_rows = play_hand(candidate, anchor, deck, candidate_seat=seat, device=args.device)
                            for row in hand_rows:
                                complete = {
                                    "policy": policy_name,
                                    "seed": seed,
                                    "anchor": anchor_name,
                                    "anchor_seed": rng_seed,
                                    "pair_index": pair_index,
                                    "candidate_seat": seat,
                                    "deck_sha256": digest,
                                    **row,
                                }
                                rows.append(complete)
                                raw.write(json.dumps(complete, sort_keys=True) + "\n")
                del anchor
            del control, treatment

    analysis = analyze(rows)
    for name, path in inputs.items():
        if sha256_path(path) != input_hashes[name]:
            raise RuntimeError(f"input changed during evaluation: {name}")
    analysis.update({
        "schema": "cardpilot.static_current_kl_highpot_critic_calibration.v1",
        "status": "COMPLETED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
        "design": {
            "pairs_per_anchor": args.pairs_per_anchor,
            "seed_base": args.seed_base,
            "training_seeds": 3,
            "anchors": [name for name, _ in ANCHORS],
            "both_candidate_seats": True,
            "policy_mode": "greedy",
            "observation_style": "legacy_v4",
            "gamma": GAMMA,
            "value_scale_bb": VALUE_SCALE,
            "slumbot_hands": 0,
        },
        "accounting": {
            "evaluation_hands": 3 * len(ANCHORS) * args.pairs_per_anchor * 2 * 2,
            "hands_per_checkpoint_stage": 3 * len(ANCHORS) * args.pairs_per_anchor * 2,
            "retained_decision_rows": len(rows),
            "unique_fresh_decks": len(generated_decks),
            "prior_deck_digests_checked": len(prior_decks),
            "slumbot_hands": 0,
            "training_hands": 0,
        },
        "input_paths": {name: str(path) for name, path in inputs.items()},
        "input_sha256": input_hashes,
        "prior_raw_sha256": prior_hashes,
        "raw_sha256": sha256_path(raw_path),
        "wall_time_seconds": time.time() - started,
    })
    summary_path.write_text(json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"decision": analysis["decision"], "gates": analysis["gates"], "accounting": analysis["accounting"], "wall_time_seconds": analysis["wall_time_seconds"]}, sort_keys=True))


if __name__ == "__main__":
    main()

