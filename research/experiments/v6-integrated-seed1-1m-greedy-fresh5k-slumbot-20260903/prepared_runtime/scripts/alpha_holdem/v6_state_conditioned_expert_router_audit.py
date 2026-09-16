"""Offline whole-hand frozen-expert router opportunity audit.

The two expert payoff streams use independent shuffled decks.  Consequently the
router value is estimated as sum_e E[1(g(X)=e) Y_e], never as a fictitious
paired difference.  Only hand-start private cards and seat are router inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time

import numpy as np


EXPERTS = (0, 5)  # Standard10, diverse_league5 in the source meta-game.
TRAIN_OPPONENTS = (1, 2, 3, 4)
HOLDOUT_OPPONENTS = (6, 7, 8)
RIDGE_ALPHAS = (1.0, 10.0, 100.0, 1000.0)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def private_features(deck: list[int], seat: int) -> np.ndarray:
    cards = deck[0:2] if seat == 0 else deck[2:4]
    ranks = sorted((cards[0] // 4, cards[1] // 4), reverse=True)
    high, low = ranks
    base = np.zeros(32, dtype=np.float64)
    base[high] = 1.0
    base[13 + low] = 1.0
    base[26] = float(high == low)
    base[27] = float(cards[0] % 4 == cards[1] % 4)
    base[28] = (high - low) / 12.0
    base[29] = high / 12.0
    base[30] = low / 12.0
    base[31] = float(high >= 8 and low >= 8)
    # Intercept, base features, and a full seat interaction.  Seat is public;
    # no opponent identity, future board card, or outcome enters X.
    return np.concatenate(([1.0], base, float(seat) * base, [float(seat)]))


def _expert_payoff(row: dict, expert: int, opponent: int, seat: int) -> float:
    if expert < opponent:
        if (row["left"], row["right"]) != (expert, opponent):
            raise ValueError("left-expert evidence identity mismatch")
        return float(row[f"left_reward_seat{seat}_bb"])
    if (row["left"], row["right"]) != (opponent, expert):
        raise ValueError("right-expert evidence identity mismatch")
    # In left_reward_seat1 the left policy occupies seat1, so the right policy
    # occupies seat0, and conversely for left_reward_seat0.
    return -float(row[f"left_reward_seat{1 - seat}_bb"])


def load_seed(path: Path, expected_sha256: str, seed_index: int) -> list[dict]:
    if sha256_path(path) != expected_sha256:
        raise ValueError(f"source evidence hash mismatch: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    if len(rows) != 9216:
        raise ValueError("expected exactly 9216 paired rows per source seed")
    if any(row["seed_index"] != seed_index for row in rows):
        raise ValueError("source seed identity mismatch")
    return rows


def extract_expert_rows(rows: list[dict], expert: int, opponents: tuple[int, ...]) -> list[dict]:
    wanted = set(opponents)
    output: list[dict] = []
    for row in rows:
        if expert == row["left"] and row["right"] in wanted:
            opponent = int(row["right"])
        elif expert == row["right"] and row["left"] in wanted:
            opponent = int(row["left"])
        else:
            continue
        for seat in (0, 1):
            output.append({
                "x": private_features(row["deck"], seat),
                "y": _expert_payoff(row, expert, opponent, seat),
                "opponent": opponent,
                "seat": seat,
                "seed_index": int(row["seed_index"]),
            })
    expected = len(opponents) * 256 * 2
    if len(output) != expected:
        raise ValueError(f"expert evidence coverage mismatch: {len(output)} != {expected}")
    return output


def arrays(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    return np.stack([row["x"] for row in rows]), np.asarray([row["y"] for row in rows])


def ridge_fit(rows: list[dict], alpha: float) -> np.ndarray:
    x, y = arrays(rows)
    penalty = np.eye(x.shape[1], dtype=np.float64) * alpha
    penalty[0, 0] = 0.0
    return np.linalg.solve(x.T @ x + penalty, x.T @ y)


def route_mask(rows: list[dict], beta0: np.ndarray, beta1: np.ndarray) -> np.ndarray:
    x, _ = arrays(rows)
    return (x @ beta1) > (x @ beta0)


def estimate(rows0: list[dict], rows1: list[dict], beta0: np.ndarray, beta1: np.ndarray,
             bootstrap: int = 0, seed: int = 0) -> dict:
    _, y0 = arrays(rows0)
    _, y1 = arrays(rows1)
    choose1_0 = route_mask(rows0, beta0, beta1)
    choose1_1 = route_mask(rows1, beta0, beta1)
    # Independent-stream unbiased value estimator.
    router = np.mean((~choose1_0) * y0) + np.mean(choose1_1 * y1)
    baseline = np.mean(y0)
    alternate = np.mean(y1)
    result = {
        "hands_per_expert": int(len(y0)),
        "router_bb100": float(router * 100.0),
        "standard10_bb100": float(baseline * 100.0),
        "alternate_bb100": float(alternate * 100.0),
        "delta_vs_standard10_bb100": float((router - baseline) * 100.0),
        "alternate_selection_fraction": float(0.5 * (choose1_0.mean() + choose1_1.mean())),
    }
    if bootstrap:
        rng = np.random.default_rng(seed)
        values = np.empty(bootstrap, dtype=np.float64)
        term0 = ((~choose1_0).astype(np.float64) - 1.0) * y0
        term1 = choose1_1.astype(np.float64) * y1
        for index in range(bootstrap):
            values[index] = (
                np.mean(term0[rng.integers(0, len(term0), len(term0))])
                + np.mean(term1[rng.integers(0, len(term1), len(term1))])
            ) * 100.0
        result["delta_ci95"] = [float(x) for x in np.quantile(values, (0.025, 0.975))]
        result["bootstrap_replicates"] = bootstrap
    return result


def select_alpha(train0: list[dict], train1: list[dict]) -> tuple[float, list[dict]]:
    reports = []
    for alpha in RIDGE_ALPHAS:
        folds = []
        for opponent in TRAIN_OPPONENTS:
            fit0 = [row for row in train0 if row["opponent"] != opponent]
            fit1 = [row for row in train1 if row["opponent"] != opponent]
            val0 = [row for row in train0 if row["opponent"] == opponent]
            val1 = [row for row in train1 if row["opponent"] == opponent]
            report = estimate(val0, val1, ridge_fit(fit0, alpha), ridge_fit(fit1, alpha))
            folds.append({"opponent": opponent, **report})
        reports.append({
            "alpha": alpha,
            "worst_delta_bb100": min(row["delta_vs_standard10_bb100"] for row in folds),
            "mean_delta_bb100": float(np.mean([row["delta_vs_standard10_bb100"] for row in folds])),
            "folds": folds,
        })
    selected = max(reports, key=lambda row: (row["worst_delta_bb100"], row["mean_delta_bb100"], -row["alpha"]))
    return float(selected["alpha"]), reports


def subset(rows: list[dict], *, opponent: int | None = None, seat: int | None = None,
           seed_index: int | None = None) -> list[dict]:
    return [row for row in rows if (opponent is None or row["opponent"] == opponent)
            and (seat is None or row["seat"] == seat)
            and (seed_index is None or row["seed_index"] == seed_index)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if args.bootstrap < 1000:
        parser.error("bootstrap must be at least 1000")
    started = time.time()
    source = json.loads(args.summary.read_text(encoding="utf-8"))
    if source.get("status") != "COMPLETED" or source.get("actual_environment_evaluation_hands") != 55296:
        raise ValueError("source PSRO experiment is incomplete")
    if [source["policies"][i]["label"] for i in EXPERTS] != ["standard10", "diverse_league5"]:
        raise ValueError("expert identity mismatch")
    root = args.summary.parent
    seed_rows = []
    verified = {}
    for seed_index in range(3):
        path = root / f"seed{seed_index}_payoffs.jsonl.gz"
        expected = source["artifact_sha256"][path.name]
        seed_rows.append(load_seed(path, expected, seed_index))
        verified[path.name] = expected
    train = {expert: [] for expert in EXPERTS}
    holdout = {expert: [] for expert in EXPERTS}
    for rows in seed_rows:
        for expert in EXPERTS:
            train[expert].extend(extract_expert_rows(rows, expert, TRAIN_OPPONENTS))
            holdout[expert].extend(extract_expert_rows(rows, expert, HOLDOUT_OPPONENTS))
    alpha, cv = select_alpha(train[0], train[5])
    beta0, beta1 = ridge_fit(train[0], alpha), ridge_fit(train[5], alpha)
    pooled = estimate(holdout[0], holdout[5], beta0, beta1, args.bootstrap, args.seed)
    opponents = {
        str(opponent): estimate(subset(holdout[0], opponent=opponent), subset(holdout[5], opponent=opponent),
                                beta0, beta1, args.bootstrap, args.seed + opponent)
        for opponent in HOLDOUT_OPPONENTS
    }
    seats = {
        str(seat): estimate(subset(holdout[0], seat=seat), subset(holdout[5], seat=seat),
                            beta0, beta1, args.bootstrap, args.seed + 100 + seat)
        for seat in (0, 1)
    }
    seeds = {
        str(seed_index): estimate(subset(holdout[0], seed_index=seed_index),
                                  subset(holdout[5], seed_index=seed_index), beta0, beta1,
                                  args.bootstrap, args.seed + 200 + seed_index)
        for seed_index in range(3)
    }
    gates = {
        "source_hashes_and_coverage_exact": len(train[0]) == len(train[5]) == 6144
            and len(holdout[0]) == len(holdout[5]) == 4608,
        "both_experts_retained_5_to_95pct": 0.05 <= pooled["alternate_selection_fraction"] <= 0.95,
        "pooled_delta_above_5bb100": pooled["delta_vs_standard10_bb100"] > 5.0,
        "pooled_bootstrap_lower_above_zero": pooled["delta_ci95"][0] > 0.0,
        "all_three_holdout_opponents_positive": all(row["delta_vs_standard10_bb100"] > 0 for row in opponents.values()),
        "both_seats_positive": all(row["delta_vs_standard10_bb100"] > 0 for row in seats.values()),
        "at_least_two_of_three_seeds_positive": sum(row["delta_vs_standard10_bb100"] > 0 for row in seeds.values()) >= 2,
    }
    admitted = all(gates.values())
    output = {
        "schema": "cardpilot.state_conditioned_expert_router_audit.v1",
        "status": "COMPLETED",
        "claim_scope": "OFFLINE_WHOLE_HAND_ROUTER_FEASIBILITY_ONLY",
        "source_summary": str(args.summary),
        "source_summary_sha256": sha256_path(args.summary),
        "verified_source_sha256": verified,
        "experts": {"0": source["policies"][0], "5": source["policies"][5]},
        "training_opponents": list(TRAIN_OPPONENTS),
        "holdout_opponents": list(HOLDOUT_OPPONENTS),
        "training_rows_per_expert": len(train[0]),
        "holdout_rows_per_expert": len(holdout[0]),
        "selected_alpha": alpha,
        "cross_validation": cv,
        "coefficients": {"standard10": beta0.tolist(), "diverse_league5": beta1.tolist()},
        "pooled_holdout": pooled,
        "by_holdout_opponent": opponents,
        "by_seat": seats,
        "by_seed": seeds,
        "gates": gates,
        "admit_router_training_smoke": admitted,
        "decision": "ADMIT_STATE_ROUTER_TRAINING_SMOKE" if admitted else "REJECT_STATE_ROUTER_OPPORTUNITY",
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": output["decision"], "gates": gates, "pooled": pooled}, sort_keys=True))


if __name__ == "__main__":
    main()
