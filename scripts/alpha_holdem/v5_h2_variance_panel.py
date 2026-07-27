#!/usr/bin/env python3
"""Generate, compute, and fail-closed audit the immutable H2-VAR-001 panel."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import random
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from v5_h1_calibration import (
    ACTIVE_POOL_IDS,
    SOURCE_SHA,
    load_source_and_pool,
    choose,
)
from v5_mirror_eval import configure_runtime, make_fixed_state, sha256_file, shuffled_deck, utc_now
from v5_hybrid_h2_targets import h2_showdown_critic_target_pairs
from alpha_holdem.environment_v55 import HUNLEnvironmentV55


DESIGN_ID = "H2-VAR-001"
DRAFT_SHA = "b450ccb93de36c08fa064cc938693ef7c499942e6a7bfa080144997fe2ef5ca2"
PAIRS = 10_000
DEAL_SEED = 2026071404
REPLICATE_SEEDS = tuple(2026071401 + i for i in range(32))
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_SEED = 2026071402
STACK = 200.0
CONTROL_K = 1
TREATMENT_K = 200
MANIFEST_SCHEMA = "v5.hybrid.h2.variance_manifest.v1"
HAND_SCHEMA = "v5.hybrid.h2.variance_hand.v1"
CLUSTER_SCHEMA = "v5.hybrid.h2.variance_cluster.v1"
SUMMARY_SCHEMA = "v5.hybrid.h2.variance_summary.v1"
AUDIT_SCHEMA = "v5.hybrid.h2.variance_audit.v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_sha(value: dict[str, Any], field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(field, None)
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


@torch.no_grad()
def play_hand(env, deck, source, opponent, source_seat: int) -> dict[str, Any]:
    state = make_fixed_state(env, deck)
    row_boards = []
    source_decisions = source_ood = opponent_decisions = opponent_ood = 0
    while not state.is_terminal():
        player = int(state.current_player)
        is_source = player == int(source_seat)
        policy = source if is_source else opponent
        _slot, action, ood, _obs, _value = choose(policy, state, player)
        if is_source:
            row_boards.append(list(map(int, state.board)))
            source_decisions += 1
            source_ood += int(ood)
        else:
            opponent_decisions += 1
            opponent_ood += int(ood)
        state = state.apply(action)
    return {
        "row_boards": row_boards,
        "source_decisions": source_decisions,
        "source_ood": source_ood,
        "opponent_decisions": opponent_decisions,
        "opponent_ood": opponent_ood,
        "folded_player": int(state.folded_player),
        "hole_cards": [list(map(int, state.hole_cards[0])), list(map(int, state.hole_cards[1]))],
        "final_board": list(map(int, state.board)),
        "committed": [float(STACK - state.stacks[0]), float(STACK - state.stacks[1])],
        "terminal_reward_bb": float(state.payoff(source_seat)),
    }


def make_manifest(source_path: Path, identity: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(DEAL_SEED)
    deals = []
    stream = hashlib.sha256()
    for index in range(PAIRS):
        deck = shuffled_deck(rng)
        deck_sha = hashlib.sha256(bytes(deck)).hexdigest()
        pool_id = ACTIVE_POOL_IDS[index % len(ACTIVE_POOL_IDS)]
        deal_id = f"h2var-{DEAL_SEED}-{index:05d}-{deck_sha[:16]}"
        deals.append({"index": index, "deal_id": deal_id, "deck_sha256": deck_sha, "opponent_pool_id": pool_id})
        stream.update(bytes(deck))
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "design_id": DESIGN_ID,
        "created_at": utc_now(),
        "draft_sha256": DRAFT_SHA,
        "source_checkpoint_path": str(source_path.resolve()),
        "source_checkpoint_sha256": SOURCE_SHA,
        "pairs": PAIRS,
        "hands": PAIRS * 2,
        "deal_seed": DEAL_SEED,
        "seat_order": [0, 1],
        "starting_stack_bb": STACK,
        "policy_mode": "greedy_argmax_both_sides",
        "replicate_target_seeds": list(REPLICATE_SEEDS),
        "control_max_runouts": CONTROL_K,
        "treatment_max_runouts": TREATMENT_K,
        "common_runout_scope": "within_hand_board_snapshot_across_seats_and_repeated_decisions",
        "cluster": "whole_deal_id_both_seat_swaps_all_eligible_source_decisions",
        "cluster_estimator": "equal_weight_deal_cluster_mean_then_pooled_within_cluster_sample_variance",
        "target_units": "raw_bb_then_divide_200_for_mean_bias",
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "bootstrap_repetitions": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "identities": identity,
        "deal_stream_sha256": stream.hexdigest(),
        "deals": deals,
        "tooling": {"generator_sha256": sha256_file(Path(__file__))},
    }
    manifest["manifest_payload_sha256"] = payload_sha(manifest, "manifest_payload_sha256")
    return manifest


def generate_hands(source_path: Path, out_dir: Path, device: str) -> dict[str, Any]:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise FileExistsError("H2-VAR output directory is not empty")
    out_dir.mkdir(parents=True, exist_ok=True)
    source, pool, identity = load_source_and_pool(source_path, device)
    manifest = make_manifest(source_path, identity)
    manifest_path = out_dir / "manifest.json"
    hands_path = out_dir / "hands.jsonl"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    env = HUNLEnvironmentV55(starting_stack=STACK)
    rng = random.Random(DEAL_SEED)
    source_decisions = source_ood = opponent_decisions = opponent_ood = eligible_rows = showdown_hands = 0
    started = time.monotonic()
    with hands_path.open("x", encoding="utf-8", newline="\n") as output:
        for expected in manifest["deals"]:
            deck = shuffled_deck(rng)
            deck_sha = hashlib.sha256(bytes(deck)).hexdigest()
            if deck_sha != expected["deck_sha256"]:
                raise RuntimeError("deal replay mismatch")
            opponent = pool[int(expected["opponent_pool_id"])]
            for seat in (0, 1):
                hand = play_hand(env, deck, source, opponent, seat)
                eligible = hand["folded_player"] < 0
                if eligible:
                    showdown_hands += 1
                    eligible_rows += sum(len(board) < 5 for board in hand["row_boards"])
                record = {
                    "schema_version": HAND_SCHEMA,
                    "design_id": DESIGN_ID,
                    "hand_id": f"{expected['deal_id']}-s{seat}",
                    "deal_id": expected["deal_id"],
                    "deal_index": expected["index"],
                    "deck_sha256": deck_sha,
                    "source_seat": seat,
                    "opponent_pool_id": expected["opponent_pool_id"],
                    **hand,
                }
                output.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                source_decisions += hand["source_decisions"]
                source_ood += hand["source_ood"]
                opponent_decisions += hand["opponent_decisions"]
                opponent_ood += hand["opponent_ood"]
    status = {
        "schema_version": "v5.hybrid.h2.variance_hands_status.v1",
        "status": "HANDS_GENERATED_TARGET_COMPUTE_PENDING",
        "checked_at": utc_now(),
        "pairs": PAIRS,
        "hands": PAIRS * 2,
        "showdown_hands": showdown_hands,
        "eligible_rows": eligible_rows,
        "source_decisions": source_decisions,
        "source_ood_rate": source_ood / max(source_decisions, 1),
        "opponent_decisions": opponent_decisions,
        "opponent_ood_rate": opponent_ood / max(opponent_decisions, 1),
        "elapsed_seconds": time.monotonic() - started,
        "manifest_sha256": sha256_file(manifest_path),
        "hands_sha256": sha256_file(hands_path),
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "launch_authority": "NONE",
    }
    (out_dir / "hands_status.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return status


def _cluster_targets(item: tuple[str, list[dict[str, Any]]]) -> dict[str, Any]:
    deal_id, hands = item
    control = []
    treatment = []
    eligible_rows = sum(sum(len(board) < 5 for board in hand["row_boards"]) for hand in hands if hand["folded_player"] < 0)
    if eligible_rows:
        for seed in REPLICATE_SEEDS:
            control_rows = []
            treatment_rows = []
            for hand in hands:
                if hand["folded_player"] >= 0:
                    continue
                state = SimpleNamespace(
                    is_done=True,
                    folded_player=-1,
                    hole_cards=hand["hole_cards"],
                )
                boards = [tuple(board) for board in hand["row_boards"]]
                c_map = h2_showdown_critic_target_pairs(
                    state, row_boards=boards, deal_identity=hand["hand_id"],
                    committed=hand["committed"], max_runouts=CONTROL_K, target_seed=seed,
                )
                t_map = h2_showdown_critic_target_pairs(
                    state, row_boards=boards, deal_identity=hand["hand_id"],
                    committed=hand["committed"], max_runouts=TREATMENT_K, target_seed=seed,
                )
                seat = int(hand["source_seat"])
                for board in boards:
                    if len(board) < 5:
                        control_rows.append(float(c_map[board]["target_bb"][seat]))
                        treatment_rows.append(float(t_map[board]["target_bb"][seat]))
            control.append(float(np.mean(control_rows)))
            treatment.append(float(np.mean(treatment_rows)))
    return {
        "schema_version": CLUSTER_SCHEMA,
        "design_id": DESIGN_ID,
        "deal_id": deal_id,
        "deal_index": int(hands[0]["deal_index"]),
        "eligible_rows": int(eligible_rows),
        "replicate_seeds": list(REPLICATE_SEEDS),
        "control_cluster_means_bb": control,
        "treatment_cluster_means_bb": treatment,
    }


def summarize_clusters(clusters: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in clusters if row["eligible_rows"] > 0]
    if not eligible:
        raise ValueError("no eligible clusters")
    control = np.asarray([row["control_cluster_means_bb"] for row in eligible], dtype=np.float64)
    treatment = np.asarray([row["treatment_cluster_means_bb"] for row in eligible], dtype=np.float64)
    control_var = np.var(control, axis=1, ddof=1)
    treatment_var = np.var(treatment, axis=1, ddof=1)
    pooled_control = float(control_var.mean())
    pooled_treatment = float(treatment_var.mean())
    point = 1.0 - pooled_treatment / pooled_control
    paired = (treatment - control) / STACK
    mean_bias_signed = float(paired.mean())
    mean_bias_abs = abs(mean_bias_signed)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    reduction_samples = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    bias_abs_samples = np.empty(BOOTSTRAP_REPS, dtype=np.float64)
    n = len(eligible)
    for index in range(BOOTSTRAP_REPS):
        chosen = rng.integers(0, n, n)
        reduction_samples[index] = 1.0 - float(treatment_var[chosen].mean() / control_var[chosen].mean())
        bias_abs_samples[index] = abs(float(paired[chosen].mean()))
    lower, upper = np.quantile(reduction_samples, [0.025, 0.975])
    bias_upper = float(np.quantile(bias_abs_samples, 0.975))
    gates = {
        "variance_point_ge_0_30": bool(point >= 0.30),
        "variance_ci95_lower_ge_0_20": bool(lower >= 0.20),
        "mean_bias_abs_point_le_0_01": bool(mean_bias_abs <= 0.01),
        "mean_bias_abs_ci95_upper_le_0_02": bool(bias_upper <= 0.02),
    }
    return {
        "schema_version": SUMMARY_SCHEMA,
        "checked_at": utc_now(),
        "design_id": DESIGN_ID,
        "status": "PASS_H2_VAR_001" if all(gates.values()) else "FAIL_H2_VAR_001",
        "deal_clusters_total": len(clusters),
        "eligible_deal_clusters": len(eligible),
        "eligible_rows": int(sum(row["eligible_rows"] for row in eligible)),
        "replicates": len(REPLICATE_SEEDS),
        "pooled_control_variance_bb2": pooled_control,
        "pooled_treatment_variance_bb2": pooled_treatment,
        "variance_reduction_point": point,
        "variance_reduction_ci95_lower": float(lower),
        "variance_reduction_ci95_upper": float(upper),
        "mean_bias_signed_effective_stack_fraction": mean_bias_signed,
        "mean_bias_abs_point": mean_bias_abs,
        "mean_bias_abs_ci95_upper": bias_upper,
        "bootstrap_repetitions": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "gates": gates,
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "launch_authority": "NONE",
        "official_hands_authorized": 0,
    }


def compute_targets(bundle_dir: Path, workers: int) -> dict[str, Any]:
    clusters_path = bundle_dir / "clusters.jsonl"
    summary_path = bundle_dir / "summary.json"
    if clusters_path.exists() or summary_path.exists():
        raise FileExistsError("target outputs already exist")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for hand in read_jsonl(bundle_dir / "hands.jsonl"):
        grouped.setdefault(hand["deal_id"], []).append(hand)
    if len(grouped) != PAIRS or any(len(rows) != 2 for rows in grouped.values()):
        raise ValueError("partial deal/seat coverage before target compute")
    items = sorted(grouped.items(), key=lambda item: item[1][0]["deal_index"])
    started = time.monotonic()
    if workers == 1:
        clusters = [_cluster_targets(item) for item in items]
    else:
        with mp.get_context("spawn").Pool(processes=workers) as pool:
            clusters = list(pool.imap(_cluster_targets, items, chunksize=8))
    with clusters_path.open("x", encoding="utf-8", newline="\n") as output:
        for cluster in clusters:
            output.write(json.dumps(cluster, sort_keys=True, separators=(",", ":")) + "\n")
    summary = summarize_clusters(clusters)
    summary.update({
        "elapsed_seconds": time.monotonic() - started,
        "manifest_sha256": sha256_file(bundle_dir / "manifest.json"),
        "hands_sha256": sha256_file(bundle_dir / "hands.jsonl"),
        "clusters_sha256": sha256_file(clusters_path),
        "tool_sha256": sha256_file(Path(__file__)),
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def audit_bundle(bundle_dir: Path) -> dict[str, Any]:
    errors = []
    try:
        manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
        hands_status = json.loads((bundle_dir / "hands_status.json").read_text(encoding="utf-8"))
        summary = json.loads((bundle_dir / "summary.json").read_text(encoding="utf-8"))
        clusters = list(read_jsonl(bundle_dir / "clusters.jsonl"))
        hands = list(read_jsonl(bundle_dir / "hands.jsonl"))
    except Exception as exc:
        return {"schema_version": AUDIT_SCHEMA, "status": "FAIL_CLOSED", "errors": [f"missing/unreadable bundle: {exc}"], "launch_authority": "NONE"}
    if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("manifest_payload_sha256") != payload_sha(manifest, "manifest_payload_sha256"):
        errors.append("manifest integrity")
    exact = {
        "design_id": DESIGN_ID, "draft_sha256": DRAFT_SHA, "source_checkpoint_sha256": SOURCE_SHA,
        "pairs": PAIRS, "hands": PAIRS * 2, "deal_seed": DEAL_SEED, "seat_order": [0, 1],
        "replicate_target_seeds": list(REPLICATE_SEEDS), "control_max_runouts": CONTROL_K,
        "treatment_max_runouts": TREATMENT_K, "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "bootstrap_repetitions": BOOTSTRAP_REPS, "bootstrap_seed": BOOTSTRAP_SEED,
    }
    for key, value in exact.items():
        if manifest.get(key) != value:
            errors.append(f"manifest exact field {key}")
    hand_keys = {(row.get("deal_id"), row.get("source_seat")) for row in hands}
    expected_keys = {(row["deal_id"], seat) for row in manifest.get("deals", []) for seat in (0, 1)}
    if len(hands) != PAIRS * 2 or hand_keys != expected_keys:
        errors.append("partial/duplicate hand seat coverage")
    if len(clusters) != PAIRS or len({row.get("deal_id") for row in clusters}) != PAIRS:
        errors.append("partial/duplicate cluster coverage")
    try:
        recomputed = summarize_clusters(clusters)
        for key in (
            "status", "eligible_deal_clusters", "eligible_rows", "pooled_control_variance_bb2",
            "pooled_treatment_variance_bb2", "variance_reduction_point", "variance_reduction_ci95_lower",
            "variance_reduction_ci95_upper", "mean_bias_signed_effective_stack_fraction",
            "mean_bias_abs_point", "mean_bias_abs_ci95_upper", "gates",
        ):
            if recomputed.get(key) != summary.get(key):
                errors.append(f"summary recompute mismatch {key}")
    except Exception as exc:
        errors.append(f"summary recompute failed: {exc}")
    hashes = {
        "manifest_sha256": sha256_file(bundle_dir / "manifest.json"),
        "hands_sha256": sha256_file(bundle_dir / "hands.jsonl"),
        "clusters_sha256": sha256_file(bundle_dir / "clusters.jsonl"),
    }
    for key, value in hashes.items():
        if summary.get(key) != value:
            errors.append(f"summary hash mismatch {key}")
    if hands_status.get("source_ood_rate", 1.0) > 0.15 or hands_status.get("opponent_ood_rate", 1.0) > 0.15:
        errors.append("OOD threshold")
    if manifest.get("tooling", {}).get("generator_sha256") != sha256_file(Path(__file__)) or summary.get("tool_sha256") != sha256_file(Path(__file__)):
        errors.append("tool identity")
    return {
        "schema_version": AUDIT_SCHEMA,
        "checked_at": utc_now(),
        "status": "PASS_IMMUTABLE_H2_VAR_001" if not errors and summary.get("status") == "PASS_H2_VAR_001" else "FAIL_CLOSED",
        "method_result": summary.get("status"),
        "errors": errors,
        **hashes,
        "summary_sha256": sha256_file(bundle_dir / "summary.json"),
        "hands_status_sha256": sha256_file(bundle_dir / "hands_status.json"),
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "launch_authority": "NONE",
        "official_hands_authorized": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    g = sub.add_parser("generate-hands")
    g.add_argument("--source", required=True)
    g.add_argument("--out-dir", required=True)
    g.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    g.add_argument("--priority", choices=("below-normal", "normal"), default="below-normal")
    g.add_argument("--torch-threads", type=int, default=1)
    g.add_argument("--torch-interop-threads", type=int, default=1)
    c = sub.add_parser("compute")
    c.add_argument("--bundle-dir", required=True)
    c.add_argument("--workers", type=int, default=4)
    a = sub.add_parser("audit")
    a.add_argument("--bundle-dir", required=True)
    a.add_argument("--out-json", required=True)
    args = parser.parse_args()
    if args.mode == "generate-hands":
        configure_runtime(args)
        device = args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu"
        result = generate_hands(Path(args.source), Path(args.out_dir), device)
    elif args.mode == "compute":
        if args.workers < 1:
            parser.error("--workers must be >= 1")
        result = compute_targets(Path(args.bundle_dir), args.workers)
    else:
        result = audit_bundle(Path(args.bundle_dir))
        Path(args.out_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.mode == "audit" and result["status"] != "PASS_IMMUTABLE_H2_VAR_001":
        return 2
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
