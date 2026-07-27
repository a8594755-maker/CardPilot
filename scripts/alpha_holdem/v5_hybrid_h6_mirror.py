#!/usr/bin/env python3
"""Frozen H6 40k common-deal, fixed-pool mirror evaluator and audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from alpha_holdem.environment_v55 import HUNLEnvironmentV55
from v5_h1_calibration import ACTIVE_POOL_IDS, SOURCE_SHA, load_source_and_pool, play_trace
from v5_mirror_eval import configure_runtime, load_policy, sha256_file, shuffled_deck


PAIRS = 40_000
SEED = 2026071601
BOOTSTRAP_REPS = 10_000
BOOTSTRAP_SEED = 2026071601
PREREG_SHA = "6b8ba0e4b396d74e1daf15bc9cb93a1018b671ec064f2ad591957c897ea46225"
SOURCE_PATH = Path(r"C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709\v5_exp005_cutover_gate31400_checkpoint.pt")
TOOL_PATH = Path(__file__).resolve()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def payload_sha(value: dict, field: str) -> str:
    copy = dict(value)
    copy.pop(field, None)
    return hashlib.sha256(canonical(copy)).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def load_lock(path: Path, expected_sha: str, manifest: Path) -> dict[str, Any]:
    if sha256_file(path) != expected_sha.lower():
        raise ValueError("measurement lock SHA mismatch")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("design_id") != "H6-MIRROR-001" or value.get("status") != "LOCKED":
        raise ValueError("measurement lock identity/status")
    if value.get("tool_sha256") != sha256_file(TOOL_PATH) or value.get("manifest_sha256") != sha256_file(manifest):
        raise ValueError("measurement lock tool/manifest binding")
    return value


def prepare(out: Path) -> dict:
    if out.exists():
        raise FileExistsError(out)
    _, _, identities = load_source_and_pool(SOURCE_PATH, "cpu")
    rng = random.Random(SEED)
    stream_hash = hashlib.sha256()
    deals = []
    for index in range(PAIRS):
        deck = shuffled_deck(rng)
        raw = bytes(deck)
        deck_sha = hashlib.sha256(raw).hexdigest()
        stream_hash.update(index.to_bytes(8, "big"))
        stream_hash.update(raw)
        deals.append({
            "index": index,
            "deal_id": f"h6mirror-{SEED}-{index:05d}-{deck_sha[:16]}",
            "deck_sha256": deck_sha,
            "opponent_pool_id": ACTIVE_POOL_IDS[index % len(ACTIVE_POOL_IDS)],
        })
    value = {
        "schema_version": "v5.hybrid.h6.mirror_manifest.v1",
        "design_id": "H6",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": PREREG_SHA,
        "pairs": PAIRS,
        "hands_per_arm": PAIRS * 2,
        "seed": SEED,
        "seat_order": [0, 1],
        "starting_stack_bb": 200.0,
        "policy_mode": "greedy_argmax_both_sides",
        "source_checkpoint_sha256": SOURCE_SHA,
        "active_pool_ids": ACTIVE_POOL_IDS,
        "identities": identities,
        "deal_stream_sha256": stream_hash.hexdigest(),
        "cluster": "whole common deal pair",
        "adaptive_extension_allowed": False,
        "training_use": "FORBIDDEN_HOLDOUT_ONLY",
        "deals": deals,
    }
    value["manifest_payload_sha256"] = payload_sha(value, "manifest_payload_sha256")
    write_new(out, value)
    return value


def audit_manifest(value: dict) -> list[str]:
    errors = []
    if value.get("schema_version") != "v5.hybrid.h6.mirror_manifest.v1" or value.get("preregistration_sha256") != PREREG_SHA:
        errors.append("manifest identity")
    if value.get("pairs") != PAIRS or value.get("seed") != SEED or value.get("active_pool_ids") != ACTIVE_POOL_IDS:
        errors.append("manifest fixed fields")
    if value.get("manifest_payload_sha256") != payload_sha(value, "manifest_payload_sha256"):
        errors.append("manifest payload hash")
    deals = value.get("deals", [])
    if len(deals) != PAIRS or len({item.get("deal_id") for item in deals}) != PAIRS:
        errors.append("deal coverage/uniqueness")
    if any(item.get("index") != index or item.get("opponent_pool_id") != ACTIVE_POOL_IDS[index % 5] for index, item in enumerate(deals)):
        errors.append("deal order/panel assignment")
    return errors


def checkpoint_identity(path: Path, arm: str) -> dict:
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    config = checkpoint.get("config") or {}
    if int(checkpoint.get("total_hands", -1)) < 535989661 or int(checkpoint.get("total_hands", -1)) > 536039661:
        raise ValueError("endpoint hands outside registration")
    if arm == "control":
        if checkpoint.get("h2_window_arm") != "control" or bool(checkpoint.get("h2_showdown_ev_value_targets")):
            raise ValueError("control endpoint identity")
        if sha256_file(path) != "f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b":
            raise ValueError("control endpoint frozen hash")
    else:
        if checkpoint.get("h6_window_arm") != "treatment" or abs(float(checkpoint.get("ppo_target_kl", -1)) - 0.03) > 1e-12:
            raise ValueError("treatment endpoint identity")
        if config.get("h6_preregistration_sha256") != PREREG_SHA:
            raise ValueError("treatment preregistration identity")
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "iteration": int(checkpoint["iteration"]),
        "hands": int(checkpoint["total_hands"]),
        "arm": arm,
    }


def run_arm(manifest_path: Path, endpoint: Path, arm: str, out: Path, device: str, lock_path: Path, lock_sha: str, runtime: dict) -> dict:
    if out.exists():
        raise FileExistsError(out)
    load_lock(lock_path, lock_sha, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = audit_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    identity = checkpoint_identity(endpoint, arm)
    candidate = load_policy(arm, endpoint, device)
    _, pool, _ = load_source_and_pool(SOURCE_PATH, device)
    environment = HUNLEnvironmentV55(starting_stack=200.0)
    rng = random.Random(SEED)
    started = time.monotonic()
    ood = decisions = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8", newline="\n") as stream:
        for expected in manifest["deals"]:
            deck = shuffled_deck(rng)
            deck_sha = hashlib.sha256(bytes(deck)).hexdigest()
            if deck_sha != expected["deck_sha256"]:
                raise RuntimeError("deal replay mismatch")
            opponent = pool[int(expected["opponent_pool_id"])]
            rewards = []
            for seat in (0, 1):
                hand = play_trace(environment, deck, candidate, opponent, seat)
                rewards.append(float(hand["reward_bb"]))
                ood += int(hand["source_ood"])
                decisions += int(hand["source_decisions"])
            row = {
                "schema_version": "v5.hybrid.h6.mirror_pair.v1",
                "arm": arm,
                "deal_id": expected["deal_id"],
                "index": expected["index"],
                "deck_sha256": deck_sha,
                "opponent_pool_id": expected["opponent_pool_id"],
                "candidate_rewards_bb": rewards,
                "pair_mean_bb_per_hand": sum(rewards) / 2.0,
            }
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    summary = {
        "schema_version": "v5.hybrid.h6.mirror_arm_summary.v1",
        "arm": arm,
        "endpoint": identity,
        "manifest_sha256": sha256_file(manifest_path),
        "measurement_lock_sha256": sha256_file(lock_path),
        "tool_sha256": sha256_file(TOOL_PATH),
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


def read_rows(path: Path, arm: str, manifest: dict) -> tuple[list[dict], list[str]]:
    with path.open(encoding="utf-8") as stream:
        values = [json.loads(line) for line in stream if line.strip()]
    errors = []
    if len(values) != PAIRS:
        errors.append("row count")
        return values, errors
    for index, row in enumerate(values):
        expected = manifest["deals"][index]
        if row.get("arm") != arm or row.get("index") != index or row.get("deal_id") != expected["deal_id"] or row.get("deck_sha256") != expected["deck_sha256"]:
            errors.append(f"row alignment {index}")
            break
        rewards = row.get("candidate_rewards_bb")
        if not isinstance(rewards, list) or len(rewards) != 2 or abs(float(row.get("pair_mean_bb_per_hand")) - sum(map(float, rewards)) / 2) > 1e-12:
            errors.append(f"row numeric {index}")
            break
    return values, errors


def audit_bundle(manifest_path: Path, control_path: Path, treatment_path: Path, out: Path, lock_path: Path, lock_sha: str) -> dict:
    load_lock(lock_path, lock_sha, manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = audit_manifest(manifest)
    control, control_errors = read_rows(control_path, "control", manifest)
    treatment, treatment_errors = read_rows(treatment_path, "treatment", manifest)
    errors += control_errors + treatment_errors
    for arm, path in (("control", control_path), ("treatment", treatment_path)):
        summary_path = path.with_suffix(".summary.json")
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
        runtime = summary.get("runtime", {})
        priority = runtime.get("priority", {})
        valid = (
            summary.get("rows_sha256") == sha256_file(path)
            and summary.get("pairs") == PAIRS
            and summary.get("ood_rate", 1) <= 0.15
            and summary.get("measurement_lock_sha256") == sha256_file(lock_path)
            and summary.get("tool_sha256") == sha256_file(TOOL_PATH)
            and runtime.get("torch_threads") == 1
            and runtime.get("torch_interop_threads") == 1
            and priority.get("requested") == "below-normal"
            and priority.get("applied") is True
        )
        if not valid:
            errors.append(f"{arm} summary/hash/OOD/lock/runtime")
    value = {
        "schema_version": "v5.hybrid.h6.mirror_audit.v1",
        "overall": "PASS_IMMUTABLE_H6_MIRROR" if not errors else "FAIL_CLOSED",
        "errors": errors,
        "manifest_sha256": sha256_file(manifest_path),
        "measurement_lock_sha256": sha256_file(lock_path),
        "tool_sha256": sha256_file(TOOL_PATH),
        "control_sha256": sha256_file(control_path),
        "treatment_sha256": sha256_file(treatment_path),
        "pairs": len(control) if not errors else None,
        "official_hands": 0,
    }
    write_new(out, value)
    return value


def judge(manifest_path: Path, control_path: Path, treatment_path: Path, audit_path: Path, out: Path, lock_path: Path, lock_sha: str) -> dict:
    load_lock(lock_path, lock_sha, manifest_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("overall") != "PASS_IMMUTABLE_H6_MIRROR":
        raise ValueError("mirror audit not PASS")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    control, _ = read_rows(control_path, "control", manifest)
    treatment, _ = read_rows(treatment_path, "treatment", manifest)
    deltas = np.array([(float(t["pair_mean_bb_per_hand"]) - float(c["pair_mean_bb_per_hand"])) * 100 for c, t in zip(control, treatment)])
    point = float(deltas.mean())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_REPS)
    for index in range(BOOTSTRAP_REPS):
        means[index] = float(deltas[rng.integers(0, PAIRS, PAIRS)].mean())
    lower, upper = map(float, np.quantile(means, [0.025, 0.975]))
    status = "PASS" if lower >= -20 else ("FAIL" if upper < -20 else "INCONCLUSIVE")
    value = {
        "schema_version": "v5.hybrid.h6.mirror_judgment.v1",
        "status": status,
        "pairs": PAIRS,
        "treatment_minus_control_bb100": point,
        "ci95_lower_bb100": lower,
        "ci95_upper_bb100": upper,
        "margin_bb100": -20.0,
        "bootstrap_repetitions": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "audit_sha256": sha256_file(audit_path),
        "official_hands": 0,
    }
    write_new(out, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--out", type=Path, required=True)
    run_parser = subparsers.add_parser("run-arm")
    run_parser.add_argument("--manifest", type=Path, required=True)
    run_parser.add_argument("--endpoint", type=Path, required=True)
    run_parser.add_argument("--arm", choices=["control", "treatment"], required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--device", choices=["cpu"], default="cpu")
    run_parser.add_argument("--priority", choices=["below-normal"], default="below-normal")
    run_parser.add_argument("--torch-threads", type=int, choices=[1], default=1)
    run_parser.add_argument("--torch-interop-threads", type=int, choices=[1], default=1)
    run_parser.add_argument("--measurement-lock", type=Path, required=True)
    run_parser.add_argument("--expected-lock-sha256", required=True)
    for mode in ("audit", "judge"):
        child = subparsers.add_parser(mode)
        child.add_argument("--manifest", type=Path, required=True)
        child.add_argument("--control", type=Path, required=True)
        child.add_argument("--treatment", type=Path, required=True)
        if mode == "judge":
            child.add_argument("--audit", type=Path, required=True)
        child.add_argument("--out", type=Path, required=True)
        child.add_argument("--measurement-lock", type=Path, required=True)
        child.add_argument("--expected-lock-sha256", required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        value = prepare(args.out)
    elif args.mode == "run-arm":
        value = run_arm(args.manifest, args.endpoint, args.arm, args.out, args.device, args.measurement_lock, args.expected_lock_sha256, configure_runtime(args))
    elif args.mode == "audit":
        value = audit_bundle(args.manifest, args.control, args.treatment, args.out, args.measurement_lock, args.expected_lock_sha256)
    else:
        value = judge(args.manifest, args.control, args.treatment, args.audit, args.out, args.measurement_lock, args.expected_lock_sha256)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
