#!/usr/bin/env python3
"""Frozen H18 40k three-endpoint common-deal mirror evaluator."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO / "scripts"))
from alpha_holdem.environment_v55 import HUNLEnvironmentV55
from v5_h1_calibration import ACTIVE_POOL_IDS, SOURCE_SHA, load_source_and_pool, play_trace
from v5_mirror_eval import configure_runtime, load_policy, sha256_file, shuffled_deck

PAIRS = 40000
SEED = 2026071905
REPS = 10000
BOOTSTRAP_SEED = 2026071906
PREREG_SHA = "8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481"
POOL_SOURCE = Path(r"C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709\v5_exp005_cutover_gate31400_checkpoint.pt")
ANCHOR_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TOOL = Path(__file__).resolve()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def payload_sha(value, field):
    copy = dict(value)
    copy.pop(field, None)
    return hashlib.sha256(canonical(copy)).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_lock(path: Path, expected: str, manifest: Path) -> dict:
    if sha256_file(path) != expected.lower():
        raise ValueError("measurement lock SHA mismatch")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("design_id") != "H18-MIRROR-001" or value.get("status") != "LOCKED":
        raise ValueError("measurement lock identity/status")
    if value.get("tool_sha256") != sha256_file(TOOL) or value.get("manifest_sha256") != sha256_file(manifest):
        raise ValueError("measurement lock tool/manifest binding")
    return value


def prepare(out: Path) -> dict:
    if out.exists():
        raise FileExistsError(out)
    _, _, identities = load_source_and_pool(POOL_SOURCE, "cpu")
    rng = random.Random(SEED)
    stream_hash = hashlib.sha256()
    deals = []
    for index in range(PAIRS):
        deck = shuffled_deck(rng)
        raw = bytes(deck)
        deck_hash = hashlib.sha256(raw).hexdigest()
        stream_hash.update(index.to_bytes(8, "big"))
        stream_hash.update(raw)
        deals.append(
            {
                "index": index,
                "deal_id": f"h18mirror-{SEED}-{index:05d}-{deck_hash[:16]}",
                "deck_sha256": deck_hash,
                "opponent_pool_id": ACTIVE_POOL_IDS[index % 5],
            }
        )
    value = {
        "schema_version": "v5.hybrid.h18.mirror_manifest.v1",
        "design_id": "H18",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": PREREG_SHA,
        "pairs": PAIRS,
        "hands_per_endpoint": PAIRS * 2,
        "seed": SEED,
        "seat_order": [0, 1],
        "starting_stack_bb": 200.0,
        "policy_mode": "greedy_argmax_both_sides",
        "source_checkpoint_sha256": ANCHOR_SHA,
        "active_pool_ids": ACTIVE_POOL_IDS,
        "identities": identities,
        "deal_stream_sha256": stream_hash.hexdigest(),
        "cluster": "whole common deal pair",
        "endpoints": ["control", "treatment", "anchor"],
        "adaptive_extension_allowed": False,
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "deals": deals,
    }
    value["manifest_payload_sha256"] = payload_sha(value, "manifest_payload_sha256")
    write_new(out, value)
    return value


def audit_manifest(value: dict) -> list[str]:
    errors = []
    if value.get("schema_version") != "v5.hybrid.h18.mirror_manifest.v1" or value.get("preregistration_sha256") != PREREG_SHA:
        errors.append("manifest identity")
    if value.get("pairs") != PAIRS or value.get("seed") != SEED or value.get("active_pool_ids") != ACTIVE_POOL_IDS:
        errors.append("manifest fixed fields")
    if value.get("manifest_payload_sha256") != payload_sha(value, "manifest_payload_sha256"):
        errors.append("manifest payload hash")
    deals = value.get("deals", [])
    if len(deals) != PAIRS or len({deal.get("deal_id") for deal in deals}) != PAIRS:
        errors.append("deal coverage/uniqueness")
    if any(
        deal.get("index") != index or deal.get("opponent_pool_id") != ACTIVE_POOL_IDS[index % 5]
        for index, deal in enumerate(deals)
    ):
        errors.append("deal order/panel assignment")
    return errors


def checkpoint_identity(path: Path, arm: str) -> dict:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    config = checkpoint.get("config") or {}
    if arm == "anchor":
        if sha256_file(path) != ANCHOR_SHA:
            raise ValueError("anchor endpoint hash")
        if checkpoint.get("h11_window_arm") != "control" or checkpoint.get("h11_catchup_loss") != "mse" or float(checkpoint.get("ppo_target_kl", -1)) != 0.03:
            raise ValueError("anchor H11-control identity")
        if int(checkpoint.get("iteration", -1)) != 35051 or int(checkpoint.get("total_hands", -1)) != 576021901:
            raise ValueError("anchor endpoint iteration/hands")
        return {
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "iteration": 35051,
            "hands": 576021901,
            "arm": arm,
            "source_identity": "H11_CONTROL_SOURCE_ANCHOR",
        }
    expected_loss = "mse" if arm == "control" else "smooth_l1"
    if checkpoint.get("h18_window_arm") != arm or abs(float(checkpoint.get("ppo_target_kl", -1)) - 0.03) > 1e-12:
        raise ValueError("endpoint H18 arm identity")
    if not bool(checkpoint.get("h8_value_head_catchup_after_kl_stop")):
        raise ValueError("endpoint H18 catch-up disabled")
    if checkpoint.get("h18_catchup_loss") != expected_loss or float(checkpoint.get("h18_catchup_smooth_l1_beta", -1)) != 1.0:
        raise ValueError("endpoint H18 catch-up loss identity")
    if config.get("h18_preregistration_sha256") != PREREG_SHA:
        raise ValueError("endpoint prereg identity")
    if not 596021901 <= int(checkpoint.get("total_hands", -1)) <= 596071901:
        raise ValueError("endpoint hands")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "iteration": int(checkpoint["iteration"]),
        "hands": int(checkpoint["total_hands"]),
        "arm": arm,
        "ppo_target_kl": 0.03,
        "value_head_catchup": True,
        "catchup_loss": expected_loss,
        "smooth_l1_beta_raw_bb": 1.0,
    }


def run_arm(manifest_path, endpoint, arm, out, device, lock_path, lock_sha, runtime):
    if out.exists():
        raise FileExistsError(out)
    load_lock(lock_path, lock_sha, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = audit_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    identity = checkpoint_identity(endpoint, arm)
    candidate = load_policy(arm, endpoint, device)
    _, pool, _ = load_source_and_pool(POOL_SOURCE, device)
    environment = HUNLEnvironmentV55(starting_stack=200.0)
    rng = random.Random(SEED)
    started = time.monotonic()
    ood = decisions = 0
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        for expected in manifest["deals"]:
            deck = shuffled_deck(rng)
            deck_hash = hashlib.sha256(bytes(deck)).hexdigest()
            if deck_hash != expected["deck_sha256"]:
                raise RuntimeError("deal replay mismatch")
            opponent = pool[int(expected["opponent_pool_id"])]
            rewards = []
            for seat in (0, 1):
                hand = play_trace(environment, deck, candidate, opponent, seat)
                rewards.append(float(hand["reward_bb"]))
                ood += int(hand["source_ood"])
                decisions += int(hand["source_decisions"])
            stream.write(
                json.dumps(
                    {
                        "schema_version": "v5.hybrid.h18.mirror_pair.v1",
                        "arm": arm,
                        "deal_id": expected["deal_id"],
                        "index": expected["index"],
                        "deck_sha256": deck_hash,
                        "opponent_pool_id": expected["opponent_pool_id"],
                        "candidate_rewards_bb": rewards,
                        "pair_mean_bb_per_hand": sum(rewards) / 2,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    summary = {
        "schema_version": "v5.hybrid.h18.mirror_arm_summary.v1",
        "arm": arm,
        "endpoint": identity,
        "manifest_sha256": sha256_file(manifest_path),
        "measurement_lock_sha256": sha256_file(lock_path),
        "tool_sha256": sha256_file(TOOL),
        "pairs": PAIRS,
        "hands": PAIRS * 2,
        "rows_sha256": sha256_file(out),
        "ood_rate": ood / max(decisions, 1),
        "elapsed_seconds": time.monotonic() - started,
        "runtime": runtime,
        "official_hands": 0,
    }
    write_new(out.with_suffix(".summary.json"), summary)
    return summary


def read_rows(path: Path, arm: str, manifest: dict):
    with path.open(encoding="utf-8") as stream:
        values = [json.loads(line) for line in stream if line.strip()]
    errors = []
    if len(values) != PAIRS:
        return values, ["row count"]
    for index, row in enumerate(values):
        expected = manifest["deals"][index]
        rewards = row.get("candidate_rewards_bb")
        if (
            row.get("schema_version") != "v5.hybrid.h18.mirror_pair.v1"
            or row.get("arm") != arm
            or row.get("index") != index
            or row.get("deal_id") != expected["deal_id"]
            or row.get("deck_sha256") != expected["deck_sha256"]
        ):
            errors.append(f"row alignment {index}")
            break
        if not isinstance(rewards, list) or len(rewards) != 2 or abs(float(row.get("pair_mean_bb_per_hand")) - sum(map(float, rewards)) / 2) > 1e-12:
            errors.append(f"row numeric {index}")
            break
    return values, errors


def audit_bundle(manifest_path, control, treatment, anchor, out, lock_path, lock_sha):
    load_lock(lock_path, lock_sha, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = audit_manifest(manifest)
    row_sets = {}
    for arm, path in (("control", control), ("treatment", treatment), ("anchor", anchor)):
        row_sets[arm], arm_errors = read_rows(path, arm, manifest)
        errors += arm_errors
        summary_path = path.with_suffix(".summary.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
        runtime = summary.get("runtime", {})
        priority = runtime.get("priority", {})
        if not (
            summary.get("rows_sha256") == sha256_file(path)
            and summary.get("pairs") == PAIRS
            and summary.get("ood_rate", 1) <= 0.15
            and summary.get("measurement_lock_sha256") == sha256_file(lock_path)
            and summary.get("tool_sha256") == sha256_file(TOOL)
            and runtime.get("torch_threads") == 1
            and runtime.get("torch_interop_threads") == 1
            and priority.get("requested") == "below-normal"
            and priority.get("applied") is True
        ):
            errors.append(f"{arm} summary/hash/OOD/lock/runtime")
    value = {
        "schema_version": "v5.hybrid.h18.mirror_audit.v1",
        "overall": "PASS_IMMUTABLE_H18_MIRROR" if not errors else "FAIL_CLOSED",
        "errors": errors,
        "manifest_sha256": sha256_file(manifest_path),
        "measurement_lock_sha256": sha256_file(lock_path),
        "tool_sha256": sha256_file(TOOL),
        "control_sha256": sha256_file(control),
        "treatment_sha256": sha256_file(treatment),
        "anchor_sha256": sha256_file(anchor),
        "pairs": len(row_sets["control"]) if not errors else None,
        "official_hands": 0,
    }
    write_new(out, value)
    return value


def comparison(differences, means, name):
    lower, upper = map(float, np.quantile(means, [0.025, 0.975]))
    status = "PASS" if lower >= -20.0 else ("FAIL" if upper < -20.0 else "INCONCLUSIVE")
    return {
        "name": name,
        "point_bb100": float(differences.mean()),
        "ci95_lower_bb100": lower,
        "ci95_upper_bb100": upper,
        "margin_bb100": -20.0,
        "status": status,
    }


def judge(manifest_path, control, treatment, anchor, audit, out, lock_path, lock_sha):
    load_lock(lock_path, lock_sha, manifest_path)
    audit_value = json.loads(audit.read_text(encoding="utf-8"))
    if audit_value.get("overall") != "PASS_IMMUTABLE_H18_MIRROR":
        raise ValueError("mirror audit not PASS")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    control_rows, _ = read_rows(control, "control", manifest)
    treatment_rows, _ = read_rows(treatment, "treatment", manifest)
    anchor_rows, _ = read_rows(anchor, "anchor", manifest)
    treatment_control_differences = np.asarray(
        [
            (float(treatment["pair_mean_bb_per_hand"]) - float(control["pair_mean_bb_per_hand"])) * 100
            for treatment, control in zip(treatment_rows, control_rows)
        ]
    )
    treatment_anchor_differences = np.asarray(
        [
            (float(treatment["pair_mean_bb_per_hand"]) - float(anchor["pair_mean_bb_per_hand"])) * 100
            for treatment, anchor in zip(treatment_rows, anchor_rows)
        ]
    )
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    treatment_control_means = np.empty(REPS)
    treatment_anchor_means = np.empty(REPS)
    for index in range(REPS):
        sample = rng.integers(0, PAIRS, PAIRS)
        treatment_control_means[index] = float(treatment_control_differences[sample].mean())
        treatment_anchor_means[index] = float(treatment_anchor_differences[sample].mean())
    treatment_control = comparison(
        treatment_control_differences,
        treatment_control_means,
        "treatment_minus_control",
    )
    treatment_anchor = comparison(
        treatment_anchor_differences,
        treatment_anchor_means,
        "treatment_minus_source_anchor",
    )
    statuses = (treatment_control["status"], treatment_anchor["status"])
    status = "FAIL" if "FAIL" in statuses else ("PASS" if statuses == ("PASS", "PASS") else "INCONCLUSIVE")
    value = {
        "schema_version": "v5.hybrid.h18.mirror_judgment.v1",
        "status": status,
        "pairs": PAIRS,
        "comparisons": {
            "treatment_vs_control": treatment_control,
            "treatment_vs_source_anchor": treatment_anchor,
        },
        "bootstrap_repetitions": REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "audit_sha256": sha256_file(audit),
        "official_hands": 0,
    }
    write_new(out, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    command = subparsers.add_parser("prepare")
    command.add_argument("--out", type=Path, required=True)
    command = subparsers.add_parser("run-arm")
    command.add_argument("--manifest", type=Path, required=True)
    command.add_argument("--endpoint", type=Path, required=True)
    command.add_argument("--arm", choices=["control", "treatment", "anchor"], required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--device", choices=["cpu"], default="cpu")
    command.add_argument("--priority", choices=["below-normal"], default="below-normal")
    command.add_argument("--torch-threads", type=int, choices=[1], default=1)
    command.add_argument("--torch-interop-threads", type=int, choices=[1], default=1)
    command.add_argument("--measurement-lock", type=Path, required=True)
    command.add_argument("--expected-lock-sha256", required=True)
    for mode in ("audit", "judge"):
        command = subparsers.add_parser(mode)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--control", type=Path, required=True)
        command.add_argument("--treatment", type=Path, required=True)
        command.add_argument("--anchor", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
        command.add_argument("--measurement-lock", type=Path, required=True)
        command.add_argument("--expected-lock-sha256", required=True)
        if mode == "judge":
            command.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare(args.out)
    elif args.mode == "run-arm":
        result = run_arm(
            args.manifest,
            args.endpoint,
            args.arm,
            args.out,
            args.device,
            args.measurement_lock,
            args.expected_lock_sha256,
            configure_runtime(args),
        )
    elif args.mode == "audit":
        result = audit_bundle(
            args.manifest,
            args.control,
            args.treatment,
            args.anchor,
            args.out,
            args.measurement_lock,
            args.expected_lock_sha256,
        )
    else:
        result = judge(
            args.manifest,
            args.control,
            args.treatment,
            args.anchor,
            args.audit,
            args.out,
            args.measurement_lock,
            args.expected_lock_sha256,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
