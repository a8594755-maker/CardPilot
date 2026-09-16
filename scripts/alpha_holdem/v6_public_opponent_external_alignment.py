"""Audit whether a frozen public-opponent model ranks externally tested policies.

This is an evaluation-only diagnostic.  Each candidate uses the exact greedy
execution adapter recorded by its fresh Slumbot experiment.  All candidates
play both seats on common decks, with deterministic per-deal public-opponent
sampling seeds.
"""
from __future__ import annotations

import argparse
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

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.dual_contract_execution_v6 import (
    decide as dual_decide,
    load_policy as load_dual_policy,
)
from alpha_holdem.legacy_observation_bridge_v6 import (
    decide as legacy_decide,
    load_policy as load_legacy_policy,
)
from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.public_opponent_v6 import decide as public_decide
from alpha_holdem.public_opponent_v6 import load_public_opponent
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint
from alpha_holdem.v6_elo_eval import greedy_action


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_ci95(values) -> dict:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array))
    return {
        "count": int(len(array)),
        "bb100": mean * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def rankdata(values) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def spearman(x, y) -> float:
    rx, ry = rankdata(x), rankdata(y)
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def pearson(x, y) -> float:
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def kendall_tau(x, y) -> float:
    concordant = discordant = 0
    for left in range(len(x)):
        for right in range(left + 1, len(x)):
            product = (x[left] - x[right]) * (y[left] - y[right])
            concordant += product > 0
            discordant += product < 0
    total = concordant + discordant
    return float((concordant - discordant) / total) if total else 0.0


def load_candidate(spec: dict, device: str):
    path = Path(spec["checkpoint"]).resolve()
    contract = spec["contract"]
    if contract == "legacy_v4":
        policy = load_legacy_policy(path, device)

        def decide(state):
            return legacy_decide(policy, state, uniform=0.5, policy_mode="greedy")[0]

    elif contract == "native_v6":
        model = init_model(read_checkpoint(path), device).eval()

        def decide(state):
            return greedy_action(model, state, observation_style="v6", device=device)

    elif contract == "dual_contract":
        base = Path(spec["base_checkpoint"]).resolve()
        policy = load_dual_policy(path, base, device)

        def decide(state):
            return dual_decide(policy, state, uniform=0.5, policy_mode="greedy")[0]

    else:
        raise ValueError(f"unknown candidate contract: {contract}")
    return decide


def play_hand(candidate_decide, public_policy, deck, candidate_seat: int, seed: int):
    state = ChipState.new(deck)
    rng = np.random.default_rng(seed)
    public_decisions = 0
    decisions = 0
    while not state.terminal:
        if state.actor == candidate_seat:
            action = candidate_decide(state)
        else:
            action, _ = public_decide(public_policy, state, rng)
            public_decisions += 1
        state = apply_incr(state, action)
        decisions += 1
    return float(state.payoffs()[candidate_seat]) / 100.0, decisions, public_decisions


def correlations(external, proxy, seat0, seat1) -> dict:
    return {
        "spearman": spearman(external, proxy),
        "pearson": pearson(external, proxy),
        "kendall_tau": kendall_tau(external, proxy),
        "seat0_spearman": spearman(external, seat0),
        "seat1_spearman": spearman(external, seat1),
    }


def bootstrap_alignment(pair_matrix, external, external_se, seed: int, samples: int):
    rng = np.random.default_rng(seed)
    fixed = []
    joint = []
    pair_count = pair_matrix.shape[1]
    for _ in range(samples):
        indices = rng.integers(0, pair_count, size=pair_count)
        proxy = pair_matrix[:, indices].mean(axis=1) * 100.0
        fixed.append(spearman(external, proxy))
        noisy_external = rng.normal(external, external_se)
        joint.append(spearman(noisy_external, proxy))
    fixed = np.asarray(fixed)
    joint = np.asarray(joint)
    return {
        "samples": int(samples),
        "fixed_external_spearman_p05": float(np.quantile(fixed, 0.05)),
        "fixed_external_spearman_median": float(np.median(fixed)),
        "fixed_external_probability_positive": float(np.mean(fixed > 0)),
        "joint_measurement_probability_positive": float(np.mean(joint > 0)),
        "joint_measurement_spearman_median": float(np.median(joint)),
    }


def summarize_alignment(rows, pair_matrix, args, manifest, raw_path, started, *, recovered):
    external = np.asarray([row["external_bb100"] for row in rows])
    external_se = np.asarray([
        (row["external_ci95_high_bb100"] - row["external_ci95_low_bb100"]) / 3.92
        for row in rows
    ])
    proxy = np.asarray([row["proxy"]["bb100"] for row in rows])
    seat0 = np.asarray([row["seat0"]["bb100"] for row in rows])
    seat1 = np.asarray([row["seat1"]["bb100"] for row in rows])
    alignment = correlations(external, proxy, seat0, seat1)
    bootstrap = bootstrap_alignment(
        pair_matrix, external, external_se, args.seed + 77_777_777, args.bootstrap_samples
    )
    external_top3 = set(np.argsort(external)[-3:].tolist())
    proxy_top3 = set(np.argsort(proxy)[-3:].tolist())
    decisive_total = decisive_correct = 0
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if abs(external[left] - external[right]) >= 10.0:
                decisive_total += 1
                decisive_correct += int(
                    (external[left] - external[right]) * (proxy[left] - proxy[right]) > 0
                )
    gates = {
        "six_or_more_fresh20k_policies": bool(
            len(rows) >= 6 and all(row["external_hands"] >= 20_000 for row in rows)
        ),
        "fixed_spearman_at_least_0_6": bool(alignment["spearman"] >= 0.6),
        "kendall_tau_at_least_0_5": bool(alignment["kendall_tau"] >= 0.5),
        "both_seat_spearman_positive": bool(
            alignment["seat0_spearman"] > 0 and alignment["seat1_spearman"] > 0
        ),
        "paired_bootstrap_spearman_p05_positive": bool(
            bootstrap["fixed_external_spearman_p05"] > 0
        ),
        "joint_measurement_probability_positive_at_least_0_75": bool(
            bootstrap["joint_measurement_probability_positive"] >= 0.75
        ),
        "top3_overlap_at_least_two": bool(len(external_top3 & proxy_top3) >= 2),
        "decisive_pair_accuracy_at_least_two_thirds": bool(
            decisive_total > 0 and decisive_correct / decisive_total >= 2.0 / 3.0
        ),
    }
    return {
        "schema": "cardpilot.public_opponent_external_alignment.v1",
        "status": "COMPLETED",
        "policy_mode": "greedy",
        "starting_stack_bb": 200,
        "pairs_per_candidate": args.pairs,
        "evaluation_hands": 2 * args.pairs * len(rows),
        "environment_training_hands": 0,
        "manifest": str(args.manifest.resolve()),
        "manifest_sha256": sha256_path(args.manifest),
        "public_opponent_sha256": manifest["public_opponent_sha256"],
        "candidates": rows,
        "alignment": alignment,
        "bootstrap": bootstrap,
        "external_top3": [rows[index]["name"] for index in sorted(external_top3)],
        "proxy_top3": [rows[index]["name"] for index in sorted(proxy_top3)],
        "decisive_pairs": {
            "minimum_external_gap_bb100": 10.0,
            "correct": int(decisive_correct),
            "total": int(decisive_total),
            "accuracy": float(decisive_correct / decisive_total),
        },
        "gates": gates,
        "proxy_admitted": all(gates.values()),
        "decision": (
            "ADMIT_PUBLIC_OPPONENT_AS_EXTERNAL_ALIGNMENT_PROXY"
            if all(gates.values())
            else "REJECT_PUBLIC_OPPONENT_AS_EXTERNAL_ALIGNMENT_PROXY"
        ),
        "raw_path": str(raw_path.resolve()),
        "raw_sha256": sha256_path(raw_path),
        "recovered_from_completed_raw": bool(recovered),
        "reporting_interruption": (
            "Initial evaluation completed every raw pair, then summary JSON serialization "
            "rejected numpy.bool_; recovery recomputed only from immutable raw rows."
            if recovered else None
        ),
        "wall_time_seconds": time.time() - started,
        "command": [sys.executable, *sys.argv],
    }


def recover_completed_raw(args, manifest, raw_path: Path, started: float) -> dict:
    candidates = manifest["candidates"]
    grouped = {spec["name"]: [] for spec in candidates}
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["candidate"] not in grouped:
                raise ValueError(f"unknown raw candidate: {row['candidate']}")
            grouped[row["candidate"]].append(row)
    expected_pairs = set(range(args.pairs))
    canonical_decks = None
    rows = []
    pair_matrix = []
    for spec in candidates:
        raw_rows = grouped[spec["name"]]
        if len(raw_rows) != args.pairs:
            raise ValueError(f"incomplete raw cohort for {spec['name']}: {len(raw_rows)}")
        raw_rows.sort(key=lambda row: row["pair_index"])
        if {row["pair_index"] for row in raw_rows} != expected_pairs:
            raise ValueError(f"raw pair index mismatch: {spec['name']}")
        decks = [row["deck"] for row in raw_rows]
        if canonical_decks is None:
            canonical_decks = decks
        elif decks != canonical_decks:
            raise ValueError(f"common-deck identity mismatch: {spec['name']}")
        pairs = [float(row["candidate_pair_mean_bb"]) for row in raw_rows]
        seats = [
            [float(row["candidate_rewards_bb"][seat]) for row in raw_rows]
            for seat in (0, 1)
        ]
        pair_matrix.append(pairs)
        rows.append({
            "name": spec["name"],
            "contract": spec["contract"],
            "checkpoint": str(Path(spec["checkpoint"]).resolve()),
            "checkpoint_sha256": spec["checkpoint_sha256"],
            "external_record": spec["external_record"],
            "external_hands": int(spec["external_hands"]),
            "external_bb100": float(spec["external_bb100"]),
            "external_ci95_low_bb100": float(spec["external_ci95_low_bb100"]),
            "external_ci95_high_bb100": float(spec["external_ci95_high_bb100"]),
            "proxy": mean_ci95(pairs),
            "seat0": mean_ci95(seats[0]),
            "seat1": mean_ci95(seats[1]),
            "decisions": None,
            "public_decisions": None,
        })
    return summarize_alignment(
        rows, np.asarray(pair_matrix), args, manifest, raw_path, started, recovered=True
    )


def run(args) -> dict:
    if args.output_dir.exists():
        raise FileExistsError(args.output_dir)
    args.output_dir.mkdir(parents=True)
    started = time.time()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    candidates = manifest["candidates"]
    if len(candidates) < 6 or len({row["name"] for row in candidates}) != len(candidates):
        raise ValueError("alignment audit requires at least six uniquely named candidates")
    public_path = Path(manifest["public_opponent_checkpoint"]).resolve()
    public_policy = load_public_opponent(public_path)
    if public_policy.sha256 != manifest["public_opponent_sha256"]:
        raise ValueError("public-opponent checkpoint SHA mismatch")
    for spec in candidates:
        if sha256_path(Path(spec["checkpoint"]).resolve()) != spec["checkpoint_sha256"]:
            raise ValueError(f"candidate checkpoint SHA mismatch: {spec['name']}")
        if spec["contract"] == "dual_contract":
            if sha256_path(Path(spec["base_checkpoint"]).resolve()) != spec["base_sha256"]:
                raise ValueError(f"candidate base SHA mismatch: {spec['name']}")

    deck_rng = random.Random(args.seed)
    decks = []
    for _ in range(args.pairs):
        deck = list(range(52))
        deck_rng.shuffle(deck)
        decks.append(deck)

    raw_path = args.output_dir / "common_deck_outcomes.jsonl.gz"
    rows = []
    pair_matrix = []
    with gzip.open(raw_path, "wt", encoding="utf-8", newline="\n") as raw:
        for candidate_index, spec in enumerate(candidates):
            candidate_decide = load_candidate(spec, args.device)
            pairs = []
            seats = [[], []]
            decision_count = public_decision_count = 0
            for pair_index, deck in enumerate(decks):
                rewards = []
                for seat in (0, 1):
                    reward, decisions, public_decisions = play_hand(
                        candidate_decide,
                        public_policy,
                        deck,
                        seat,
                        args.seed + 10_000_019 * pair_index + seat,
                    )
                    rewards.append(reward)
                    seats[seat].append(reward)
                    decision_count += decisions
                    public_decision_count += public_decisions
                pair_mean = float(np.mean(rewards))
                pairs.append(pair_mean)
                raw.write(json.dumps({
                    "candidate": spec["name"],
                    "candidate_index": candidate_index,
                    "pair_index": pair_index,
                    "deck": deck,
                    "candidate_rewards_bb": rewards,
                    "candidate_pair_mean_bb": pair_mean,
                }, separators=(",", ":"), sort_keys=True) + "\n")
            pair_matrix.append(pairs)
            rows.append({
                "name": spec["name"],
                "contract": spec["contract"],
                "checkpoint": str(Path(spec["checkpoint"]).resolve()),
                "checkpoint_sha256": spec["checkpoint_sha256"],
                "external_record": spec["external_record"],
                "external_hands": int(spec["external_hands"]),
                "external_bb100": float(spec["external_bb100"]),
                "external_ci95_low_bb100": float(spec["external_ci95_low_bb100"]),
                "external_ci95_high_bb100": float(spec["external_ci95_high_bb100"]),
                "proxy": mean_ci95(pairs),
                "seat0": mean_ci95(seats[0]),
                "seat1": mean_ci95(seats[1]),
                "decisions": decision_count,
                "public_decisions": public_decision_count,
            })

    pair_matrix = np.asarray(pair_matrix, dtype=np.float64)
    summary = summarize_alignment(
        rows, pair_matrix, args, manifest, raw_path, started, recovered=False
    )
    for spec in candidates:
        if sha256_path(Path(spec["checkpoint"]).resolve()) != spec["checkpoint_sha256"]:
            raise RuntimeError(f"candidate mutated during audit: {spec['name']}")
    if sha256_path(public_path) != manifest["public_opponent_sha256"]:
        raise RuntimeError("public opponent mutated during audit")
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=60925)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--recover-raw", type=Path)
    args = parser.parse_args()
    if args.pairs < 256:
        parser.error("--pairs must be at least 256")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if args.recover_raw is not None:
        started = time.time()
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        summary_path = args.output_dir / "summary.json"
        if summary_path.exists():
            raise FileExistsError(summary_path)
        summary = recover_completed_raw(args, manifest, args.recover_raw.resolve(), started)
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, sort_keys=True))
    else:
        print(json.dumps(run(args), sort_keys=True))


if __name__ == "__main__":
    main()
