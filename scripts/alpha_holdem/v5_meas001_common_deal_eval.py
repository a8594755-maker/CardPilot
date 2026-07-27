#!/usr/bin/env python3
"""MEAS-001 prospective common-deal causal evaluator.

This is a reporting-only evaluator for a future, separately registered V5
behavior experiment.  It intentionally does not modify or replace
``v5_mirror_eval.py`` because that evaluator is hash-bound into historical
EXP-001/EXP-003 evidence.

The three registered roles run on one deterministic deal stream:

* pre-change versus native anchor;
* post-change versus native anchor;
* post-change directly versus pre-change.

Every mirrored pair is retained in an aligned JSONL artifact.  The native-axis
effect is computed from the paired per-deal difference, not from two independent
summary intervals.  Output paths are one-shot: an existing artifact is never
overwritten, and a partial bundle is preserved and rejected by validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))

from v5_mirror_eval import (  # noqa: E402
    POLICY_MODE,
    Policy,
    checkpoint_summary,
    configure_runtime,
    load_policy,
    play_hand,
    sha256_file,
    shuffled_deck,
    utc_now,
)
from alpha_holdem.environment_v55 import HUNLEnvironmentV55  # noqa: E402


SCHEMA_VERSION = "v5.meas001.common_deal.v1"
MANIFEST_SCHEMA_VERSION = "v5.meas001.deal_manifest.v1"
SOURCE_BUNDLE_SCHEMA_VERSION = "v5.meas001.source_bundle.v1"
PAIRS_SCHEMA_VERSION = "v5.meas001.aligned_pair.v1"
REGISTERED_PAIRS = 100_000
REGISTERED_STACK_BB = 200.0
REGISTERED_OOD_MAX = 0.15
REGISTERED_CI95_HALFWIDTH_MAX_BB100 = 20.0
ROLE_NAMES = ("pre_vs_native", "post_vs_native", "post_vs_pre_direct")
TERMINAL_OUTCOMES = ("PASS", "FAIL", "INCONCLUSIVE")

PlayHandFn = Callable[..., dict[str, Any]]


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_text_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_json_exclusive(path: Path, value: Any) -> None:
    write_text_exclusive(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def replace_json(path: Path, value: Any) -> None:
    """Replace the evaluator-owned execution status without touching evidence."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def ensure_output_paths_absent(paths: Iterable[Path]) -> None:
    collisions = [str(path) for path in paths if path.exists()]
    if collisions:
        raise FileExistsError("MEAS-001 is one-shot; refusing existing artifacts: " + ", ".join(collisions))


def critical_source_paths() -> list[Path]:
    paths = [
        Path(__file__).resolve(),
        THIS_DIR / "v5_mirror_eval.py",
        THIS_DIR / "environment_v55.py",
        THIS_DIR / "environment.py",
        THIS_DIR / "network.py",
        THIS_DIR.parent / "deep_cfr" / "game_state.py",
    ]
    resolved: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        item = path.resolve()
        key = str(item).lower()
        if key not in seen:
            if not item.exists():
                raise FileNotFoundError(f"critical evaluator source missing: {item}")
            resolved.append(item)
            seen.add(key)
    return resolved


def build_source_bundle(*, created_at: str | None = None) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in critical_source_paths():
        raw_content = path.read_bytes()
        content = raw_content.decode("utf-8")
        try:
            relative = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative = path.name
        files.append(
            {
                "repo_relative_path": relative,
                "sha256": sha256_bytes(raw_content),
                "content_utf8": content,
            }
        )
    payload = {
        "schema_version": SOURCE_BUNDLE_SCHEMA_VERSION,
        "design_id": "MEAS-001",
        "created_at": created_at or utc_now(),
        "entry_point": Path(__file__).resolve().relative_to(REPO_ROOT).as_posix(),
        "files": files,
    }
    payload["source_bundle_payload_sha256"] = payload_sha256(payload)
    return payload


def verify_source_bundle_integrity(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if bundle.get("schema_version") != SOURCE_BUNDLE_SCHEMA_VERSION:
        errors.append("source bundle schema mismatch")
    expected = bundle.get("source_bundle_payload_sha256")
    unsigned = dict(bundle)
    unsigned.pop("source_bundle_payload_sha256", None)
    if expected != payload_sha256(unsigned):
        errors.append("source bundle payload hash mismatch")
    files = bundle.get("files")
    if not isinstance(files, list) or not files:
        errors.append("source bundle has no files")
        return errors
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"source bundle file {index} is not an object")
            continue
        relative = item.get("repo_relative_path")
        if not isinstance(relative, str) or not relative:
            errors.append(f"source bundle path missing at {index}")
        elif relative in seen:
            errors.append(f"duplicate source bundle path {relative}")
        else:
            seen.add(relative)
        content = item.get("content_utf8")
        if not isinstance(content, str):
            errors.append(f"source bundle content missing at {index}")
        elif item.get("sha256") != sha256_bytes(content.encode("utf-8")):
            errors.append(f"source bundle content hash mismatch at {index}")
    if bundle.get("entry_point") not in seen:
        errors.append("source bundle entry point is not archived")
    return errors


def checkpoint_identity(policy: Policy) -> dict[str, Any]:
    summary = checkpoint_summary(policy.checkpoint)
    return {
        "label": policy.label,
        "path": str(policy.path.resolve()),
        "sha256": policy.sha256,
        "iteration": summary.get("iteration"),
        "total_hands": summary.get("total_hands"),
        "env_version": policy.env_version,
        "obs_version": policy.obs_version,
        "checkpoint": summary,
    }


def require_exact_policy_identity(
    policy: Policy,
    *,
    role: str,
    expected_iteration: int,
    expected_hands: int,
) -> dict[str, Any]:
    identity = checkpoint_identity(policy)
    actual_iteration = identity["iteration"]
    actual_hands = identity["total_hands"]
    if isinstance(actual_iteration, bool) or not isinstance(actual_iteration, int):
        raise ValueError(f"{role} checkpoint iteration is not an exact integer: {actual_iteration!r}")
    if isinstance(actual_hands, bool) or not isinstance(actual_hands, int):
        raise ValueError(f"{role} checkpoint total_hands is not an exact integer: {actual_hands!r}")
    if actual_iteration != expected_iteration:
        relation = "late" if actual_iteration > expected_iteration else "early"
        raise ValueError(
            f"{role} checkpoint iteration mismatch ({relation}): "
            f"actual={actual_iteration}, expected={expected_iteration}"
        )
    if actual_hands != expected_hands:
        raise ValueError(
            f"{role} checkpoint hands mismatch: actual={actual_hands}, expected={expected_hands}"
        )
    identity["expected_iteration"] = expected_iteration
    identity["expected_hands"] = expected_hands
    identity["identity_status"] = "PASS"
    return identity


def require_distinct_checkpoint_hashes(bindings: dict[str, dict[str, Any]]) -> None:
    hashes = [str(bindings[role]["sha256"]).lower() for role in ("pre", "post", "native")]
    if len(set(hashes)) != len(hashes):
        raise ValueError("pre/post/native checkpoint hashes must be distinct")
    if any(len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value) for value in hashes):
        raise ValueError("all checkpoint hashes must be lowercase 64-hex SHA256 values")


def make_deal_entry(index: int, seed: int, deck: list[int]) -> dict[str, Any]:
    deck_bytes = bytes(deck)
    deck_sha256 = sha256_bytes(deck_bytes)
    return {
        "index": index,
        "deal_id": f"meas001-{seed}-{index:06d}-{deck_sha256[:16]}",
        "deck_sha256": deck_sha256,
    }


def build_deal_manifest(
    *,
    pairs: int,
    seed: int,
    starting_stack: float,
    bindings: dict[str, dict[str, Any]],
    evaluator_path: Path,
    source_bundle_binding: dict[str, Any],
    created_at: str | None = None,
) -> dict[str, Any]:
    if pairs <= 0:
        raise ValueError("pairs must be positive")
    rng = __import__("random").Random(seed)
    deals: list[dict[str, Any]] = []
    stream_digest = hashlib.sha256()
    for index in range(pairs):
        deck = shuffled_deck(rng)
        entry = make_deal_entry(index, seed, deck)
        deals.append(entry)
        stream_digest.update(index.to_bytes(8, "big", signed=False))
        stream_digest.update(bytes(deck))

    evaluator_resolved = evaluator_path.resolve()
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "design_id": "MEAS-001",
        "created_at": created_at or utc_now(),
        "pairs": pairs,
        "hands_per_role": pairs * 2,
        "seed": seed,
        "starting_stack_bb": starting_stack,
        "policy_mode": POLICY_MODE,
        "seat_order": [0, 1],
        "role_names": list(ROLE_NAMES),
        "role_seeds": {role: seed for role in ROLE_NAMES},
        "deal_generator": "python_random_mt19937_shuffle_range52_v1",
        "deal_stream_sha256": stream_digest.hexdigest(),
        "deals": deals,
        "bindings": bindings,
        "evaluator": {
            "path": str(evaluator_resolved),
            "sha256": sha256_file(evaluator_resolved),
            "source_bundle": source_bundle_binding,
        },
    }
    payload["manifest_payload_sha256"] = payload_sha256(payload)
    return payload


def verify_manifest_integrity(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest schema mismatch")
    expected_hash = manifest.get("manifest_payload_sha256")
    unsigned = dict(manifest)
    unsigned.pop("manifest_payload_sha256", None)
    if expected_hash != payload_sha256(unsigned):
        errors.append("manifest payload hash mismatch")
    pairs = manifest.get("pairs")
    deals = manifest.get("deals")
    if isinstance(pairs, bool) or not isinstance(pairs, int) or pairs <= 0:
        errors.append("manifest pairs is not a positive exact integer")
        return errors
    if not isinstance(deals, list) or len(deals) != pairs:
        errors.append("manifest deal count does not equal pairs")
        return errors
    seen: set[str] = set()
    for index, deal in enumerate(deals):
        if not isinstance(deal, dict):
            errors.append(f"manifest deal {index} is not an object")
            continue
        if deal.get("index") != index:
            errors.append(f"manifest deal index mismatch at {index}")
        deal_id = deal.get("deal_id")
        if not isinstance(deal_id, str) or not deal_id:
            errors.append(f"manifest deal_id missing at {index}")
        elif deal_id in seen:
            errors.append(f"duplicate manifest deal_id {deal_id}")
        else:
            seen.add(deal_id)
        deck_hash = deal.get("deck_sha256")
        if not isinstance(deck_hash, str) or len(deck_hash) != 64:
            errors.append(f"manifest deck hash invalid at {index}")
    if manifest.get("role_names") != list(ROLE_NAMES):
        errors.append("manifest role set/order mismatch")
    role_seeds = manifest.get("role_seeds")
    if role_seeds != {role: manifest.get("seed") for role in ROLE_NAMES}:
        errors.append("roles do not share the registered common seed")
    if manifest.get("seat_order") != [0, 1]:
        errors.append("manifest seat order is not the required swap [0, 1]")
    evaluator = manifest.get("evaluator") if isinstance(manifest.get("evaluator"), dict) else {}
    source_binding = evaluator.get("source_bundle") if isinstance(evaluator.get("source_bundle"), dict) else {}
    for name in ("sha256", "payload_sha256"):
        value = source_binding.get(name)
        if not isinstance(value, str) or len(value) != 64:
            errors.append(f"manifest source bundle {name} is invalid")
    return errors


def run_mirrored_role(
    *,
    env: HUNLEnvironmentV55,
    deck: list[int],
    candidate: Policy,
    anchor: Policy,
    play_hand_fn: PlayHandFn = play_hand,
) -> dict[str, Any]:
    hands = [
        play_hand_fn(env=env, deck=deck, candidate=candidate, anchor=anchor, candidate_seat=seat)
        for seat in (0, 1)
    ]
    rewards = [float(hand["candidate_reward_bb"]) for hand in hands]
    pair_mean = sum(rewards) / 2.0
    return {
        "candidate_seats": [0, 1],
        "hands": 2,
        "candidate_rewards_bb": rewards,
        "pair_mean_bb_per_hand": pair_mean,
        "decisions": sum(int(hand.get("decisions", 0)) for hand in hands),
        "policy_decisions": {
            key: sum(int(hand.get("policy_decisions", {}).get(key, 0)) for hand in hands)
            for key in ("candidate", "anchor")
        },
        "ood_nodes": {
            key: sum(int(hand.get("ood_nodes", {}).get(key, 0)) for hand in hands)
            for key in ("candidate", "anchor")
        },
    }


def mean_ci(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0, "lower": 0.0, "upper": 0.0}
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    halfwidth = 1.96 * std / math.sqrt(len(array))
    return {
        "mean": mean,
        "std": std,
        "ci95": halfwidth,
        "lower": mean - halfwidth,
        "upper": mean + halfwidth,
    }


def bb100_stats(values: list[float]) -> dict[str, float]:
    stats = mean_ci(values)
    return {
        "mean_bb100": stats["mean"] * 100.0,
        "std_bb_per_hand": stats["std"],
        "ci95_halfwidth_bb100": stats["ci95"] * 100.0,
        "ci95_lower_bb100": stats["lower"] * 100.0,
        "ci95_upper_bb100": stats["upper"] * 100.0,
    }


def update_role_aggregate(aggregate: dict[str, Any], result: dict[str, Any]) -> None:
    value = float(result["pair_mean_bb_per_hand"])
    aggregate["values"].append(value)
    if value > 0.0001:
        aggregate["wins"] += 1
    elif value < -0.0001:
        aggregate["losses"] += 1
    else:
        aggregate["draws"] += 1
    aggregate["decisions"] += int(result["decisions"])
    for key in ("candidate", "anchor"):
        aggregate["policy_decisions"][key] += int(result["policy_decisions"][key])
        aggregate["ood_nodes"][key] += int(result["ood_nodes"][key])


def new_role_aggregate() -> dict[str, Any]:
    return {
        "values": [],
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "decisions": 0,
        "policy_decisions": {"candidate": 0, "anchor": 0},
        "ood_nodes": {"candidate": 0, "anchor": 0},
    }


def summarize_role(aggregate: dict[str, Any]) -> dict[str, Any]:
    result = bb100_stats(aggregate["values"])
    result.update(
        {
            "pairs": len(aggregate["values"]),
            "hands": len(aggregate["values"]) * 2,
            "pair_wins": aggregate["wins"],
            "pair_losses": aggregate["losses"],
            "pair_draws": aggregate["draws"],
            "decisions": aggregate["decisions"],
            "policy_decisions": aggregate["policy_decisions"],
            "ood_nodes": aggregate["ood_nodes"],
            "candidate_ood_node_rate": aggregate["ood_nodes"]["candidate"]
            / max(aggregate["policy_decisions"]["candidate"], 1),
            "anchor_ood_node_rate": aggregate["ood_nodes"]["anchor"]
            / max(aggregate["policy_decisions"]["anchor"], 1),
        }
    )
    return result


def evaluate_common_deals(
    *,
    manifest: dict[str, Any],
    policies: dict[str, Policy],
    pairs_jsonl_path: Path,
    play_hand_fn: PlayHandFn = play_hand,
) -> dict[str, Any]:
    manifest_errors = verify_manifest_integrity(manifest)
    if manifest_errors:
        raise ValueError("invalid deal manifest: " + "; ".join(manifest_errors))
    required_policies = {"pre", "post", "native"}
    if set(policies) != required_policies:
        raise ValueError(f"policy roles mismatch: {sorted(policies)}")

    pairs_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    rng = __import__("random").Random(int(manifest["seed"]))
    env = HUNLEnvironmentV55(starting_stack=float(manifest["starting_stack_bb"]))
    aggregates = {role: new_role_aggregate() for role in ROLE_NAMES}
    native_axis_values: list[float] = []
    direct_values: list[float] = []
    started = time.monotonic()

    with pairs_jsonl_path.open("x", encoding="utf-8", newline="\n") as output:
        for expected in manifest["deals"]:
            index = int(expected["index"])
            deck = shuffled_deck(rng)
            actual = make_deal_entry(index, int(manifest["seed"]), deck)
            if actual != expected:
                raise RuntimeError(f"deal replay mismatch at index {index}")

            roles = {
                "pre_vs_native": run_mirrored_role(
                    env=env,
                    deck=deck,
                    candidate=policies["pre"],
                    anchor=policies["native"],
                    play_hand_fn=play_hand_fn,
                ),
                "post_vs_native": run_mirrored_role(
                    env=env,
                    deck=deck,
                    candidate=policies["post"],
                    anchor=policies["native"],
                    play_hand_fn=play_hand_fn,
                ),
                "post_vs_pre_direct": run_mirrored_role(
                    env=env,
                    deck=deck,
                    candidate=policies["post"],
                    anchor=policies["pre"],
                    play_hand_fn=play_hand_fn,
                ),
            }
            native_delta = (
                float(roles["post_vs_native"]["pair_mean_bb_per_hand"])
                - float(roles["pre_vs_native"]["pair_mean_bb_per_hand"])
            )
            direct = float(roles["post_vs_pre_direct"]["pair_mean_bb_per_hand"])
            record = {
                "schema_version": PAIRS_SCHEMA_VERSION,
                "index": index,
                "deal_id": expected["deal_id"],
                "deck_sha256": expected["deck_sha256"],
                "seat_order": [0, 1],
                "roles": roles,
                "native_axis_delta_bb_per_hand": native_delta,
                "direct_causal_bb_per_hand": direct,
            }
            output.write(canonical_json_bytes(record).decode("utf-8") + "\n")
            for role, result in roles.items():
                update_role_aggregate(aggregates[role], result)
            native_axis_values.append(native_delta)
            direct_values.append(direct)

    role_summaries = {role: summarize_role(aggregate) for role, aggregate in aggregates.items()}
    return {
        "pairs": int(manifest["pairs"]),
        "elapsed_seconds": time.monotonic() - started,
        "roles": role_summaries,
        "primary_effects": {
            "paired_native_axis_delta": bb100_stats(native_axis_values),
            "post_vs_pre_direct": bb100_stats(direct_values),
        },
        "pairs_jsonl": {
            "path": str(pairs_jsonl_path.resolve()),
            "sha256": sha256_file(pairs_jsonl_path),
            "rows": int(manifest["pairs"]),
        },
    }


def validate_aligned_pairs(
    *,
    manifest: dict[str, Any],
    pairs_jsonl_path: Path,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    errors = verify_manifest_integrity(manifest)
    if not pairs_jsonl_path.exists():
        errors.append("aligned pairs JSONL is missing")
        return {"status": "FAIL", "errors": errors, "rows": 0, "sha256": None}
    actual_sha256 = sha256_file(pairs_jsonl_path)
    if expected_sha256 and actual_sha256 != expected_sha256:
        errors.append("aligned pairs JSONL hash mismatch")

    rows = 0
    seen: set[str] = set()
    with pairs_jsonl_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                errors.append(f"blank aligned-pair row at line {line_number}")
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSONL at line {line_number}: {exc}")
                continue
            index = rows
            if index >= len(manifest.get("deals", [])):
                errors.append("aligned pairs has more rows than manifest")
                rows += 1
                continue
            expected = manifest["deals"][index]
            if record.get("schema_version") != PAIRS_SCHEMA_VERSION:
                errors.append(f"pair schema mismatch at index {index}")
            if record.get("index") != index:
                errors.append(f"pair index mismatch at index {index}")
            if record.get("deal_id") != expected.get("deal_id"):
                errors.append(f"deal_id mismatch at index {index}")
            if record.get("deck_sha256") != expected.get("deck_sha256"):
                errors.append(f"deck hash mismatch at index {index}")
            deal_id = record.get("deal_id")
            if deal_id in seen:
                errors.append(f"duplicate aligned deal_id {deal_id}")
            elif isinstance(deal_id, str):
                seen.add(deal_id)
            if record.get("seat_order") != [0, 1]:
                errors.append(f"seat-swap marker mismatch at index {index}")
            roles = record.get("roles")
            if not isinstance(roles, dict) or set(roles.keys()) != set(ROLE_NAMES):
                errors.append(f"role set mismatch at index {index}")
            else:
                for role in ROLE_NAMES:
                    result = roles[role]
                    if result.get("candidate_seats") != [0, 1] or result.get("hands") != 2:
                        errors.append(f"incomplete seat swap for {role} at index {index}")
                native_delta = (
                    float(roles["post_vs_native"]["pair_mean_bb_per_hand"])
                    - float(roles["pre_vs_native"]["pair_mean_bb_per_hand"])
                )
                direct = float(roles["post_vs_pre_direct"]["pair_mean_bb_per_hand"])
                if not math.isclose(
                    float(record.get("native_axis_delta_bb_per_hand", math.nan)),
                    native_delta,
                    abs_tol=1e-12,
                ):
                    errors.append(f"native-axis alignment mismatch at index {index}")
                if not math.isclose(
                    float(record.get("direct_causal_bb_per_hand", math.nan)),
                    direct,
                    abs_tol=1e-12,
                ):
                    errors.append(f"direct-effect alignment mismatch at index {index}")
            rows += 1

    if rows != int(manifest.get("pairs", -1)):
        errors.append(f"aligned row count {rows} != manifest pairs {manifest.get('pairs')}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "rows": rows,
        "sha256": actual_sha256,
    }


def verify_summary_payload(summary: dict[str, Any]) -> bool:
    expected = summary.get("result_payload_sha256")
    unsigned = dict(summary)
    unsigned.pop("result_payload_sha256", None)
    return isinstance(expected, str) and expected == payload_sha256(unsigned)


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{label} is not a JSON object: {path}")
    return value


def audit_completed_bundle(
    *,
    summary_path: Path,
    manifest_path: Path,
    source_bundle_path: Path,
    pairs_jsonl_path: Path,
    execution_path: Path,
) -> dict[str, Any]:
    """Independently audit a terminal MEAS-001 artifact bundle."""
    errors: list[str] = []
    for label, path in (
        ("summary", summary_path),
        ("manifest", manifest_path),
        ("source bundle", source_bundle_path),
        ("aligned pairs", pairs_jsonl_path),
        ("execution", execution_path),
    ):
        if not path.exists():
            errors.append(f"{label} artifact missing: {path}")
    if errors:
        return {"status": "FAIL", "errors": errors}

    try:
        summary = load_json_object(summary_path, "summary")
        manifest = load_json_object(manifest_path, "manifest")
        source_bundle = load_json_object(source_bundle_path, "source bundle")
        execution = load_json_object(execution_path, "execution")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "errors": [f"bundle JSON load failed: {type(exc).__name__}: {exc}"]}

    if summary.get("schema_version") != SCHEMA_VERSION:
        errors.append("summary schema mismatch")
    if summary.get("design_id") != "MEAS-001":
        errors.append("summary design_id mismatch")
    if not verify_summary_payload(summary):
        errors.append("summary result payload hash mismatch")
    summary_file_sha = sha256_file(summary_path)
    if execution.get("status") != "COMPLETED":
        errors.append(f"execution is not terminal COMPLETED: {execution.get('status')}")
    measurement = summary.get("measurement") if isinstance(summary.get("measurement"), dict) else {}
    if measurement.get("status") not in TERMINAL_OUTCOMES:
        errors.append("summary measurement status is not terminal")
    if execution.get("measurement_status") != measurement.get("status"):
        errors.append("execution/summary measurement status mismatch")
    if execution.get("summary_sha256") != summary_file_sha:
        errors.append("execution summary SHA256 mismatch")

    manifest_errors = verify_manifest_integrity(manifest)
    errors.extend(f"manifest: {error}" for error in manifest_errors)
    manifest_file_sha = sha256_file(manifest_path)
    summary_manifest = summary.get("manifest") if isinstance(summary.get("manifest"), dict) else {}
    if summary_manifest.get("sha256") != manifest_file_sha:
        errors.append("summary manifest file SHA256 mismatch")
    if summary_manifest.get("payload_sha256") != manifest.get("manifest_payload_sha256"):
        errors.append("summary manifest payload SHA256 mismatch")
    if summary_manifest.get("deal_stream_sha256") != manifest.get("deal_stream_sha256"):
        errors.append("summary deal-stream SHA256 mismatch")
    if summary.get("bindings") != manifest.get("bindings"):
        errors.append("summary/manifest checkpoint bindings mismatch")
    if summary.get("pairs") != manifest.get("pairs") or summary.get("seed") != manifest.get("seed"):
        errors.append("summary/manifest pairs or seed mismatch")

    evaluator = manifest.get("evaluator") if isinstance(manifest.get("evaluator"), dict) else {}
    source_binding = evaluator.get("source_bundle") if isinstance(evaluator.get("source_bundle"), dict) else {}
    source_bundle_errors = verify_source_bundle_integrity(source_bundle)
    errors.extend(f"source bundle: {error}" for error in source_bundle_errors)
    source_bundle_file_sha = sha256_file(source_bundle_path)
    if source_binding.get("sha256") != source_bundle_file_sha:
        errors.append("manifest source bundle file SHA256 mismatch")
    if source_binding.get("payload_sha256") != source_bundle.get("source_bundle_payload_sha256"):
        errors.append("manifest source bundle payload SHA256 mismatch")
    entry_point = source_bundle.get("entry_point")
    archived_entry = next(
        (
            item
            for item in source_bundle.get("files", [])
            if isinstance(item, dict) and item.get("repo_relative_path") == entry_point
        ),
        None,
    )
    if not isinstance(archived_entry, dict) or evaluator.get("sha256") != archived_entry.get("sha256"):
        errors.append("manifest evaluator SHA256 does not match frozen source entry point")

    summary_pairs = summary.get("pairs_jsonl") if isinstance(summary.get("pairs_jsonl"), dict) else {}
    aligned_validation = validate_aligned_pairs(
        manifest=manifest,
        pairs_jsonl_path=pairs_jsonl_path,
        expected_sha256=summary_pairs.get("sha256"),
    )
    errors.extend(f"aligned pairs: {error}" for error in aligned_validation["errors"])
    if summary_pairs.get("rows") != aligned_validation.get("rows"):
        errors.append("summary/aligned-pairs row count mismatch")
    embedded_validation = summary.get("bundle_validation")
    if not isinstance(embedded_validation, dict) or embedded_validation.get("status") != "PASS":
        errors.append("summary embedded bundle validation is not PASS")

    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "summary_sha256": summary_file_sha,
        "manifest_sha256": manifest_file_sha,
        "source_bundle_sha256": source_bundle_file_sha,
        "pairs_jsonl_sha256": aligned_validation.get("sha256"),
        "pairs": aligned_validation.get("rows"),
        "measurement_status": measurement.get("status"),
    }


def classify_measurement(
    *,
    primary_effects: dict[str, dict[str, float]],
    role_summaries: dict[str, dict[str, Any]],
    bundle_validation: dict[str, Any],
    ci95_halfwidth_max_bb100: float,
    anchor_ood_max: float,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    add(
        "bundle_validation",
        bundle_validation.get("status") == "PASS",
        f"status={bundle_validation.get('status')}, rows={bundle_validation.get('rows')}",
    )
    for role in ROLE_NAMES:
        summary = role_summaries[role]
        rate = float(summary.get("anchor_ood_node_rate", 0.0))
        add(f"{role}_anchor_ood", rate <= anchor_ood_max, f"rate={rate:.6f}, max={anchor_ood_max:.6f}")
    for effect_name in ("paired_native_axis_delta", "post_vs_pre_direct"):
        effect = primary_effects[effect_name]
        halfwidth = float(effect["ci95_halfwidth_bb100"])
        add(
            f"{effect_name}_precision",
            halfwidth <= ci95_halfwidth_max_bb100,
            f"halfwidth={halfwidth:.6f}, max={ci95_halfwidth_max_bb100:.6f}",
        )

    validity_ok = all(check["status"] == "PASS" for check in checks if "precision" not in check["name"])
    precision_ok = all(check["status"] == "PASS" for check in checks if "precision" in check["name"])
    lowers = [float(primary_effects[name]["ci95_lower_bb100"]) for name in primary_effects]
    uppers = [float(primary_effects[name]["ci95_upper_bb100"]) for name in primary_effects]

    if not validity_ok:
        status = "FAIL"
        reason = "VALIDITY_FAILED"
    elif not precision_ok:
        status = "INCONCLUSIVE"
        reason = "CI_PRECISION_FAILED"
    elif all(lower > 0.0 for lower in lowers):
        status = "PASS"
        reason = "BOTH_PRIMARY_LOWER_BOUNDS_POSITIVE"
    elif any(upper < 0.0 for upper in uppers):
        status = "FAIL"
        reason = "PRIMARY_EFFECT_PRECISE_REGRESSION"
    else:
        status = "INCONCLUSIVE"
        reason = "PRIMARY_EFFECT_OVERLAPS_ZERO"
    return {
        "status": status,
        "reason": reason,
        "checks": checks,
        "terminal": status in TERMINAL_OUTCOMES,
        "claim_scope": "method_measurement_only_not_slumbot_not_v4_l5_l6",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    effects = summary["primary_effects"]
    lines = [
        "# MEAS-001 Common-Deal Causal Measurement",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Status: `{summary['measurement']['status']}`",
        f"- Reason: `{summary['measurement']['reason']}`",
        f"- Pairs: `{summary['pairs']}`",
        f"- Common seed: `{summary['seed']}`",
        f"- Manifest SHA256: `{summary['manifest']['sha256']}`",
        f"- Aligned pairs SHA256: `{summary['pairs_jsonl']['sha256']}`",
        "",
        "This is method-measurement evidence only. It is not a Slumbot, V4, L5, or L6 strength result.",
        "",
        "## Primary Effects",
        "",
        "| estimand | bb/100 | 95% CI |",
        "|---|---:|---:|",
    ]
    for name in ("paired_native_axis_delta", "post_vs_pre_direct"):
        effect = effects[name]
        lines.append(
            f"| {name} | {effect['mean_bb100']:+.3f} | "
            f"[{effect['ci95_lower_bb100']:+.3f}, {effect['ci95_upper_bb100']:+.3f}] |"
        )
    lines.extend(["", "## Validation", ""])
    for check in summary["measurement"]["checks"]:
        lines.append(f"- `{check['status']}` {check['name']}: {check['detail']}")
    write_text_exclusive(path, "\n".join(lines) + "\n")


def validate_registered_args(args: argparse.Namespace) -> None:
    if args.pairs != REGISTERED_PAIRS:
        raise ValueError(f"MEAS-001 requires exactly {REGISTERED_PAIRS} pairs; got {args.pairs}")
    if not math.isclose(args.starting_stack, REGISTERED_STACK_BB, abs_tol=1e-12):
        raise ValueError(f"MEAS-001 requires starting stack {REGISTERED_STACK_BB}")
    if args.device != "cpu":
        raise ValueError("MEAS-001 requires CPU execution")
    if args.priority != "below-normal":
        raise ValueError("MEAS-001 requires BelowNormal priority")
    if not math.isclose(args.anchor_ood_max, REGISTERED_OOD_MAX, abs_tol=1e-12):
        raise ValueError(f"MEAS-001 anchor OOD maximum is fixed at {REGISTERED_OOD_MAX}")
    paths = [
        Path(args.out_source_bundle),
        Path(args.out_manifest),
        Path(args.out_pairs_jsonl),
        Path(args.out_json),
        Path(args.out_md),
        Path(args.execution_json),
    ]
    if len({str(path.resolve()).lower() for path in paths}) != len(paths):
        raise ValueError("all MEAS-001 artifact paths must be distinct")
    ensure_output_paths_absent(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MEAS-001 prospective common-deal causal evaluator")
    parser.add_argument("--pre", required=True)
    parser.add_argument("--post", required=True)
    parser.add_argument("--native", required=True)
    parser.add_argument("--pre-label", default="pre")
    parser.add_argument("--post-label", default="post")
    parser.add_argument("--native-label", default="native")
    parser.add_argument("--expected-pre-iteration", type=int, required=True)
    parser.add_argument("--expected-pre-hands", type=int, required=True)
    parser.add_argument("--expected-post-iteration", type=int, required=True)
    parser.add_argument("--expected-post-hands", type=int, required=True)
    parser.add_argument("--expected-native-iteration", type=int, required=True)
    parser.add_argument("--expected-native-hands", type=int, required=True)
    parser.add_argument("--pairs", type=int, default=REGISTERED_PAIRS)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--starting-stack", type=float, default=REGISTERED_STACK_BB)
    parser.add_argument("--anchor-ood-max", type=float, default=REGISTERED_OOD_MAX)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--priority", choices=["below-normal", "normal"], default="below-normal")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--torch-interop-threads", type=int, default=1)
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--out-source-bundle", required=True)
    parser.add_argument("--out-pairs-jsonl", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--execution-json", required=True)
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    validate_registered_args(args)
    execution_path = Path(args.execution_json)
    started = time.monotonic()
    execution = configure_runtime(args)
    write_json_exclusive(execution_path, execution)
    try:
        policies = {
            "pre": load_policy(args.pre_label, Path(args.pre), args.device),
            "post": load_policy(args.post_label, Path(args.post), args.device),
            "native": load_policy(args.native_label, Path(args.native), args.device),
        }
        bindings = {
            "pre": require_exact_policy_identity(
                policies["pre"],
                role="pre",
                expected_iteration=args.expected_pre_iteration,
                expected_hands=args.expected_pre_hands,
            ),
            "post": require_exact_policy_identity(
                policies["post"],
                role="post",
                expected_iteration=args.expected_post_iteration,
                expected_hands=args.expected_post_hands,
            ),
            "native": require_exact_policy_identity(
                policies["native"],
                role="native",
                expected_iteration=args.expected_native_iteration,
                expected_hands=args.expected_native_hands,
            ),
        }
        require_distinct_checkpoint_hashes(bindings)
        source_bundle_path = Path(args.out_source_bundle)
        source_bundle = build_source_bundle()
        source_bundle_errors = verify_source_bundle_integrity(source_bundle)
        if source_bundle_errors:
            raise RuntimeError("source bundle self-check failed: " + "; ".join(source_bundle_errors))
        write_json_exclusive(source_bundle_path, source_bundle)
        source_bundle_binding = {
            "path": str(source_bundle_path.resolve()),
            "sha256": sha256_file(source_bundle_path),
            "payload_sha256": source_bundle["source_bundle_payload_sha256"],
        }
        manifest_path = Path(args.out_manifest)
        manifest = build_deal_manifest(
            pairs=args.pairs,
            seed=args.seed,
            starting_stack=args.starting_stack,
            bindings=bindings,
            evaluator_path=Path(__file__),
            source_bundle_binding=source_bundle_binding,
        )
        write_json_exclusive(manifest_path, manifest)
        manifest_sha256 = sha256_file(manifest_path)

        evidence = evaluate_common_deals(
            manifest=manifest,
            policies=policies,
            pairs_jsonl_path=Path(args.out_pairs_jsonl),
        )
        validation = validate_aligned_pairs(
            manifest=manifest,
            pairs_jsonl_path=Path(args.out_pairs_jsonl),
            expected_sha256=evidence["pairs_jsonl"]["sha256"],
        )
        measurement = classify_measurement(
            primary_effects=evidence["primary_effects"],
            role_summaries=evidence["roles"],
            bundle_validation=validation,
            ci95_halfwidth_max_bb100=REGISTERED_CI95_HALFWIDTH_MAX_BB100,
            anchor_ood_max=args.anchor_ood_max,
        )
        summary = {
            "schema_version": SCHEMA_VERSION,
            "design_id": "MEAS-001",
            "checked_at": utc_now(),
            "claim_scope": "method_measurement_only_not_slumbot_not_v4_l5_l6",
            "pairs": args.pairs,
            "seed": args.seed,
            "starting_stack_bb": args.starting_stack,
            "policy_mode": POLICY_MODE,
            "bindings": bindings,
            "manifest": {
                "path": str(manifest_path.resolve()),
                "sha256": manifest_sha256,
                "payload_sha256": manifest["manifest_payload_sha256"],
                "deal_stream_sha256": manifest["deal_stream_sha256"],
            },
            "source_bundle": source_bundle_binding,
            **evidence,
            "bundle_validation": validation,
            "measurement": measurement,
            "external_guards_required_for_future_method_judgment": [
                "health PASS",
                "trainer stderr empty",
                "no action or entropy collapse",
                "experiment-specific counters valid",
                "throughput inside the separately registered experiment band",
            ],
        }
        summary["result_payload_sha256"] = payload_sha256(summary)
        write_json_exclusive(Path(args.out_json), summary)
        write_markdown(summary, Path(args.out_md))
        execution.update(
            {
                "status": "COMPLETED",
                "measurement_status": measurement["status"],
                "finished_at": utc_now(),
                "elapsed_seconds": time.monotonic() - started,
                "summary_path": str(Path(args.out_json).resolve()),
                "summary_sha256": sha256_file(Path(args.out_json)),
            }
        )
        replace_json(execution_path, execution)
        return summary
    except Exception as exc:
        execution.update(
            {
                "status": "FAILED",
                "finished_at": utc_now(),
                "elapsed_seconds": time.monotonic() - started,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        replace_json(execution_path, execution)
        raise


def main() -> int:
    args = build_parser().parse_args()
    summary = run(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
