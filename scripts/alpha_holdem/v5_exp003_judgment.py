#!/usr/bin/env python3
"""Build the fixed-window EXP-003 causal judgment.

This is a reporting-only evaluator. It consumes the immutable first-eligible
checkpoint, the registered three-role mirror bundle, and training evidence. It
does not change trainer state or implement a rollback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))

from v5_monitor import LOG_RE, parse_log
from v5_next_action_queue import (
    EXP003_CI_PRECISION_FAILED,
    EXP003_NATIVE_MIRROR_TARGET_HANDS,
    exp003_mirror_bundle_status,
)
from v5_throughput_audit import summarize_window, with_effective_metrics


SCHEMA_VERSION = "v5.exp003.judgment.v1"
CUTOVER_ITERATION = 21_800
CUTOVER_HANDS = 358_064_575
BOOTSTRAP_SEED = 20_260_709
BOOTSTRAP_REPLICATES = 5_000
BOOTSTRAP_BLOCK_ROWS = 20
METHOD_WINDOW_ROWS = 200
BASELINE_EFFECTIVE_HPS = 1565.4
MIN_EFFECTIVE_HPS_RATIO = 0.80
MAX_MIRROR_OUTSTANDING = 22 * 16

DEFAULT_BASELINE_RUN = (
    REPO_ROOT
    / "models"
    / "alpha_holdem_v5_from_zero"
    / "v5_zero_l6_exp004_pre001_exp002_multienv_rollback_r1_20260708"
)
DEFAULT_BASELINE_AUDIT_SHA256 = "66bc083a2f9c933f7a738b2fdc52c94296100a3ceb1fcb4b1b1ef34963c0e38f"
DEFAULT_TRAINER_SHA256 = "8b951a43e3b86f6eb38600a69c33ce793c3b4658047325ac06d6e11f6a0b8b31"
DEFAULT_REVIEW_SHA256 = "163f45ed6ee76bdc62d8f1df5dbf865845799b53769c8b58cf0bb1fc2c3b1bf6"
DEFAULT_TRACE_SHA256 = "253abc2859e94c68c8440c2255aaddf2ec4c0a3a8eeace486d3e2c95a2ed38ef"
DEFAULT_EVALUATOR_SHA256 = "2f9e81eae19e0da37da0d9be05dafbf820e812ac8366604cd2ad13f6aa7f0013"
PRE_SHA256 = "60d3b7ffbfe750cc8c0d1e4dfcd80a308d6a3f406a4b5e5265b9d9563d8877d5"
NATIVE_SHA256 = "47318cf20388f0f2cfdc63d9d76bd6c5519d39de54ab0e24589fcb1f90fc8f63"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise TypeError(f"{path} is not a JSON object")
    return obj


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, passed: bool, detail: str, *, hard: bool = True) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if passed else "FAIL", "detail": detail, "hard": hard}


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def circular_block_sample(values: list[float], rng: random.Random, block_rows: int) -> list[float]:
    sampled: list[float] = []
    while len(sampled) < len(values):
        start = rng.randrange(len(values))
        sampled.extend(values[(start + offset) % len(values)] for offset in range(block_rows))
    return sampled[: len(values)]


def value_loss_support(pre: list[float], post: list[float]) -> dict[str, Any]:
    if len(pre) != METHOD_WINDOW_ROWS or len(post) != METHOD_WINDOW_ROWS:
        raise ValueError(f"value-loss windows must each contain {METHOD_WINDOW_ROWS} rows")
    rng = random.Random(BOOTSTRAP_SEED)
    differences: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        pre_sample = circular_block_sample(pre, rng, BOOTSTRAP_BLOCK_ROWS)
        post_sample = circular_block_sample(post, rng, BOOTSTRAP_BLOCK_ROWS)
        differences.append(statistics.fmean(pre_sample) - statistics.fmean(post_sample))
    delta = statistics.fmean(pre) - statistics.fmean(post)
    lower = percentile(differences, 0.025)
    upper = percentile(differences, 0.975)
    if lower > 0.0:
        status = "PASS"
    elif upper < 0.0:
        status = "REGRESSION"
    else:
        status = "INCONCLUSIVE"
    return {
        "status": status,
        "pre_mean": statistics.fmean(pre),
        "post_mean": statistics.fmean(post),
        "pre_minus_post": delta,
        "ci95_lower": lower,
        "ci95_upper": upper,
        "window_rows": METHOD_WINDOW_ROWS,
        "block_rows": BOOTSTRAP_BLOCK_ROWS,
        "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
    }


def effect_status(point: float, halfwidth: float) -> str:
    if point - halfwidth > 0.0:
        return "PASS"
    if point + halfwidth < 0.0:
        return "REGRESSION"
    return "INCONCLUSIVE"


def mirror_effects(bundle: dict[str, Any]) -> dict[str, Any]:
    roles = bundle["roles"]
    pre = roles["pre_vs_native"]
    post = roles["post_vs_native"]
    direct = roles["post_vs_pre_direct"]
    pre_point = float(pre["candidate_bb100"])
    post_point = float(post["candidate_bb100"])
    pre_half = abs(float(pre["candidate_ci95_bb100"]))
    post_half = abs(float(post["candidate_ci95_bb100"]))
    direct_point = float(direct["candidate_bb100"])
    direct_half = abs(float(direct["candidate_ci95_bb100"]))
    native_delta = post_point - pre_point
    native_half = math.sqrt(pre_half**2 + post_half**2)
    return {
        "native_axis": {
            "status": effect_status(native_delta, native_half),
            "pre_bb100": pre_point,
            "pre_ci95_halfwidth_bb100": pre_half,
            "post_bb100": post_point,
            "post_ci95_halfwidth_bb100": post_half,
            "delta_bb100": native_delta,
            "combined_ci95_halfwidth_bb100": native_half,
            "ci95_lower_bb100": native_delta - native_half,
            "ci95_upper_bb100": native_delta + native_half,
            "formula": "post-pre; combined halfwidth=sqrt(pre_halfwidth^2+post_halfwidth^2)",
        },
        "direct_causal": {
            "status": effect_status(direct_point, direct_half),
            "point_bb100": direct_point,
            "ci95_halfwidth_bb100": direct_half,
            "ci95_lower_bb100": direct_point - direct_half,
            "ci95_upper_bb100": direct_point + direct_half,
        },
    }


def raw_counter_audit(log_path: Path, candidate_iteration: int) -> dict[str, Any]:
    required = (
        "mirror_replay_hands",
        "mirror_source_hands",
        "allin_ev_replacements",
        "allin_ev_runouts",
        "allin_ev_skipped_hands",
        "allin_ev_skipped_runouts",
    )
    rows = 0
    missing_rows: list[int] = []
    invalid_runout_rows: list[int] = []
    skipped_rows: list[int] = []
    outstanding = 0
    min_outstanding = 0
    max_outstanding = 0
    totals = {key: 0 for key in required}
    latest_iteration = None
    latest_hands = None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = LOG_RE.search(line)
        if not match:
            continue
        data = match.groupdict()
        iteration = int(data["iteration"])
        if iteration <= CUTOVER_ITERATION or iteration > candidate_iteration:
            continue
        rows += 1
        latest_iteration = iteration
        latest_hands = int(data["hands"].replace(",", ""))
        if any(data.get(key) is None for key in required):
            missing_rows.append(iteration)
            continue
        values = {key: int(data[key]) for key in required}
        for key, value in values.items():
            totals[key] += value
        replacements = values["allin_ev_replacements"]
        runouts = values["allin_ev_runouts"]
        if (replacements == 0 and runouts != 0) or (replacements > 0 and not (0 < runouts <= 200 * replacements)):
            invalid_runout_rows.append(iteration)
        if values["allin_ev_skipped_hands"] or values["allin_ev_skipped_runouts"]:
            skipped_rows.append(iteration)
        outstanding += values["mirror_source_hands"] - values["mirror_replay_hands"]
        min_outstanding = min(min_outstanding, outstanding)
        max_outstanding = max(max_outstanding, outstanding)
    passed = bool(
        rows > 0
        and latest_iteration == candidate_iteration
        and not missing_rows
        and not invalid_runout_rows
        and not skipped_rows
        and totals["allin_ev_replacements"] > 0
        and totals["allin_ev_runouts"] > 0
        and totals["mirror_source_hands"] > 0
        and totals["mirror_replay_hands"] > 0
        and min_outstanding >= 0
        and max_outstanding <= MAX_MIRROR_OUTSTANDING
        and 0 <= outstanding <= MAX_MIRROR_OUTSTANDING
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "rows": rows,
        "latest_iteration": latest_iteration,
        "latest_hands": latest_hands,
        "missing_counter_rows": missing_rows[:20],
        "invalid_runout_rows": invalid_runout_rows[:20],
        "skipped_rows": skipped_rows[:20],
        "totals": totals,
        "mirror_outstanding_final": outstanding,
        "mirror_outstanding_min": min_outstanding,
        "mirror_outstanding_max": max_outstanding,
        "mirror_outstanding_limit": MAX_MIRROR_OUTSTANDING,
    }


def gate_guard(run_dir: Path, candidate_iteration: int, candidate_hands: int) -> dict[str, Any]:
    expected = [candidate_iteration - 200, candidate_iteration - 100, candidate_iteration]
    rows: list[dict[str, Any]] = []
    for iteration in expected:
        path = run_dir / f"gate_{iteration}_status.json"
        gate = load_json(path) if path.exists() else {}
        rows.append(
            {
                "path": str(path),
                "iteration": iteration,
                "checkpoint_iteration": gate.get("checkpoint_iteration"),
                "checkpoint_hands": gate.get("checkpoint_hands"),
                "overall": gate.get("overall"),
                "health_overall": gate.get("health_overall"),
            }
        )
    ending = rows[-1]
    all_pass = all(
        row["checkpoint_iteration"] == row["iteration"]
        and str(row["overall"]).upper() == "PASS"
        and str(row["health_overall"]).upper() == "PASS"
        for row in rows
    )
    all_pass = all_pass and ending["checkpoint_hands"] == candidate_hands
    window_failures: list[str] = []
    for path in run_dir.glob("gate_*_status.json"):
        gate = load_json(path)
        iteration = int(gate.get("checkpoint_iteration") or 0)
        if CUTOVER_ITERATION < iteration <= candidate_iteration and str(gate.get("overall") or "").upper() == "FAIL":
            window_failures.append(str(path))
    return {
        "status": "PASS" if all_pass and not window_failures else "FAIL",
        "last_three": rows,
        "window_failures": window_failures,
    }


def config_guard(manifest: dict[str, Any]) -> dict[str, Any]:
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    expected = {
        "rollout_mode": "multi",
        "rollout_envs_per_worker": 16,
        "inference_min_batch_slots": 256,
        "inference_batch_deadline_us": 1000.0,
        "mirror_self_play_deals": True,
        "allin_runout_ev": True,
        "allin_runout_ev_max_runouts": 200,
        "preflop_action_prior_coef": 0.01,
        "postflop_action_prior_coef": 0.02,
        "workers": 22,
        "starting_stack": 200.0,
    }
    mismatches = {key: {"actual": config.get(key), "expected": value} for key, value in expected.items() if config.get(key) != value}
    return {"status": "PASS" if not mismatches else "FAIL", "expected": expected, "mismatches": mismatches}


def artifact_guard(path: Path, expected_sha256: str) -> dict[str, Any]:
    actual = sha256_file(path) if path.exists() else ""
    return {
        "status": "PASS" if actual == expected_sha256 else "FAIL",
        "path": str(path),
        "expected_sha256": expected_sha256,
        "actual_sha256": actual,
    }


def model_input_guard(bundle: dict[str, Any]) -> dict[str, Any]:
    roles = bundle.get("roles") if isinstance(bundle.get("roles"), dict) else {}
    freeze = bundle.get("freeze") if isinstance(bundle.get("freeze"), dict) else {}
    post_sha = str(freeze.get("archive_sha256") or "").lower()
    specifications = [
        ("pre_vs_native", "candidate", PRE_SHA256),
        ("pre_vs_native", "anchor", NATIVE_SHA256),
        ("post_vs_native", "candidate", post_sha),
        ("post_vs_native", "anchor", NATIVE_SHA256),
        ("post_vs_pre_direct", "candidate", post_sha),
        ("post_vs_pre_direct", "anchor", PRE_SHA256),
    ]
    cache: dict[str, str] = {}
    checks: list[dict[str, Any]] = []
    for role_name, side, expected in specifications:
        record = roles.get(role_name) if isinstance(roles.get(role_name), dict) else {}
        path_text = str(record.get(f"{side}_path") or "")
        claimed = str(record.get(f"{side}_sha256") or "").lower()
        path = Path(path_text)
        if path_text and path.is_file():
            if str(path) not in cache:
                cache[str(path)] = sha256_file(path)
            actual = cache[str(path)]
        else:
            actual = ""
        passed = bool(expected and claimed == expected and actual == expected)
        checks.append(
            {
                "role": role_name,
                "side": side,
                "path": path_text,
                "expected_sha256": expected,
                "claimed_sha256": claimed,
                "actual_sha256": actual,
                "status": "PASS" if passed else "FAIL",
            }
        )
    return {"status": "PASS" if all(row["status"] == "PASS" for row in checks) else "FAIL", "checks": checks}


def legacy_preflight_contract_guard(
    bundle: dict[str, Any],
    roles: dict[str, Any],
    ci_precision_failed_roles: list[str],
) -> dict[str, Any]:
    """Validate the one legacy exception without treating it as launcher proof."""

    contract = bundle.get("legacy_preflight_contract")
    legacy_roles = sorted(
        name
        for name, record in roles.items()
        if isinstance(record, dict) and record.get("legacy_inconclusive_only") is True
    )
    if contract is None:
        return {
            "status": "NOT_APPLICABLE" if not legacy_roles else "FAIL",
            "legacy_roles": legacy_roles,
            "reason": "no legacy role" if not legacy_roles else "legacy role lacks queue-verified preflight contract",
        }
    if not isinstance(contract, dict):
        return {"status": "FAIL", "legacy_roles": legacy_roles, "reason": "legacy preflight contract is not an object"}
    pre = roles.get("pre_vs_native") if isinstance(roles.get("pre_vs_native"), dict) else {}
    post = roles.get("post_vs_native") if isinstance(roles.get("post_vs_native"), dict) else {}
    pre_companions = pre.get("companion_paths") if isinstance(pre.get("companion_paths"), dict) else {}
    post_companions = post.get("companion_paths") if isinstance(post.get("companion_paths"), dict) else {}
    required = (
        legacy_roles == ["pre_vs_native"]
        and ci_precision_failed_roles == ["post_vs_native"]
        and contract.get("schema_version") == "v5.exp003.pre_vs_native.legacy_preflight_contract.v1"
        and contract.get("role") == "pre_vs_native"
        and contract.get("candidate_iteration") == CUTOVER_ITERATION
        and contract.get("candidate_hands") == CUTOVER_HANDS
        and str(contract.get("candidate_sha256") or "").lower() == PRE_SHA256
        and str(contract.get("anchor_sha256") or "").lower() == NATIVE_SHA256
        and contract.get("result_path") == pre.get("path")
        and contract.get("provenance_path") == pre_companions.get("legacy_provenance")
        and contract.get("audit_path") == pre_companions.get("legacy_provenance_audit")
        and bool(contract.get("provenance_sha256"))
        and bool(contract.get("audit_sha256"))
        and contract.get("post_vs_native_result_path") == post.get("path")
        and contract.get("post_vs_native_candidate_iteration") == post.get("candidate_iteration")
        and contract.get("post_vs_native_candidate_hands") == post.get("candidate_hands")
        and contract.get("post_vs_native_candidate_sha256") == post.get("candidate_sha256")
        and contract.get("post_vs_native_contention_reaudit_path") == post_companions.get("contention_reaudit")
        and bool(contract.get("post_vs_native_contention_reaudit_sha256"))
        and contract.get("required_ci_precision_failed_roles") == ["post_vs_native"]
        and contract.get("inconclusive_only") is True
        and contract.get("requires_post_vs_native_ci_failure") is True
        and contract.get("forbids_review_ready") is True
        and contract.get("forbids_additional_pairs") is True
        and contract.get("normal_launcher_evidence") is False
        and pre.get("launcher_evidence_ok") is False
        and pre.get("judgmentable") is False
        and pre.get("usable") is False
        and post.get("launcher_evidence_ok") is True
        and post.get("judgmentable") is True
        and post.get("ci_precision_failed") is True
    )
    if not required:
        return {"status": "FAIL", "legacy_roles": legacy_roles, "reason": "legacy preflight contract fields do not bind the allowed role1/role2 state"}
    hashed_paths = (
        (contract["provenance_path"], contract["provenance_sha256"]),
        (contract["audit_path"], contract["audit_sha256"]),
        (contract["post_vs_native_contention_reaudit_path"], contract["post_vs_native_contention_reaudit_sha256"]),
    )
    for path_text, expected_sha in hashed_paths:
        path = Path(str(path_text))
        if not path.is_file() or sha256_file(path) != str(expected_sha):
            return {"status": "FAIL", "legacy_roles": legacy_roles, "reason": f"legacy contract companion hash mismatch: {path}"}
    return {"status": "PASS", "legacy_roles": legacy_roles, "contract": contract}


def build_judgment(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    bundle = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
    measurement_status = str(bundle.get("status") or "").upper()
    if measurement_status not in {"REVIEW_READY", EXP003_CI_PRECISION_FAILED}:
        raise RuntimeError(
            "EXP-003 bundle is not judgmentable: "
            f"{bundle.get('status')} {bundle.get('detail')}"
        )
    roles = bundle.get("roles") if isinstance(bundle.get("roles"), dict) else {}
    expected_roles = {"pre_vs_native", "post_vs_native", "post_vs_pre_direct"}
    ci_precision_failed_roles = sorted(
        name
        for name in expected_roles
        if isinstance(roles.get(name), dict)
        and bool(roles[name].get("ci_precision_failed"))
    )
    legacy_contract = legacy_preflight_contract_guard(bundle, roles, ci_precision_failed_roles)
    if measurement_status == EXP003_CI_PRECISION_FAILED:
        nonjudgmentable = sorted(
            name
            for name in expected_roles
            if not isinstance(roles.get(name), dict)
            or not bool(roles[name].get("judgmentable"))
        )
        legacy_exception = legacy_contract["status"] == "PASS"
        allowed_nonjudgmentable = ["pre_vs_native"] if legacy_exception else []
        if (
            nonjudgmentable != allowed_nonjudgmentable
            or not ci_precision_failed_roles
            or (legacy_contract["status"] == "FAIL")
        ):
            raise RuntimeError(
                "EXP-003 CI precision state lacks a complete structurally valid bundle: "
                f"nonjudgmentable_roles={nonjudgmentable}, "
                f"ci_precision_failed_roles={ci_precision_failed_roles}, "
                f"legacy_contract={legacy_contract}"
            )
    model_inputs = model_input_guard(bundle)
    if model_inputs["status"] != "PASS":
        raise RuntimeError(f"EXP-003 model input integrity failed: {json.dumps(model_inputs, sort_keys=True)}")
    freeze = bundle["freeze"]
    candidate_iteration = int(freeze["archive_iteration"])
    candidate_hands = int(freeze["archive_hands"])
    effects = mirror_effects(bundle)

    candidate_rows = [row for row in parse_log(run_dir / "latest_train.log") if int(row["iteration"]) <= candidate_iteration]
    baseline_run = Path(args.baseline_run_dir).resolve()
    baseline_rows = [row for row in parse_log(baseline_run / "latest_train.log") if int(row["iteration"]) <= CUTOVER_ITERATION]
    if not candidate_rows or int(candidate_rows[-1]["iteration"]) != candidate_iteration:
        raise RuntimeError("candidate training log does not end at the frozen candidate iteration")
    if len(candidate_rows) < METHOD_WINDOW_ROWS or len(baseline_rows) < METHOD_WINDOW_ROWS:
        raise RuntimeError("insufficient rows for registered 200-row method windows")
    candidate_window = candidate_rows[-METHOD_WINDOW_ROWS:]
    baseline_window = baseline_rows[-METHOD_WINDOW_ROWS:]

    enriched = with_effective_metrics(candidate_rows)
    throughput_window = summarize_window(enriched[-60:], "candidate_tail60_at_frozen_checkpoint")
    candidate_effective = float(throughput_window.get("effective_hps_mean") or 0.0)
    throughput_ratio = candidate_effective / BASELINE_EFFECTIVE_HPS

    value_support = value_loss_support(
        [float(row["value_loss"]) for row in baseline_window],
        [float(row["value_loss"]) for row in candidate_window],
    )
    shape_values = [
        float(row["postflop_action_mix"]["raise"]) + float(row["postflop_action_mix"]["allin"])
        for row in candidate_window
        if isinstance(row.get("postflop_action_mix"), dict)
    ]
    shape_mean = statistics.fmean(shape_values) if len(shape_values) == METHOD_WINDOW_ROWS else None
    if shape_mean is None:
        shape_status = "INVALID"
    elif 0.30 <= shape_mean <= 0.60:
        shape_status = "PASS"
    elif shape_mean < 0.05 or shape_mean > 0.90:
        shape_status = "COLLAPSE"
    else:
        shape_status = "INCONCLUSIVE"
    method_support = {
        "value_loss": value_support,
        "postflop_raise_plus_allin": {
            "status": shape_status,
            "mean": shape_mean,
            "window_rows": len(shape_values),
            "support_band": [0.30, 0.60],
            "collapse_bands": ["<0.05", ">0.90"],
        },
    }

    manifest = load_json(run_dir / "run_manifest.json")
    candidate_gate = load_json(run_dir / f"gate_{candidate_iteration}_status.json")
    checkpoint_meta = candidate_gate.get("checkpoint") if isinstance(candidate_gate.get("checkpoint"), dict) else {}
    counter_audit = raw_counter_audit(run_dir / "latest_train.log", candidate_iteration)
    gates = gate_guard(run_dir, candidate_iteration, candidate_hands)
    config = config_guard(manifest)
    baseline_audit = baseline_run / "v5_throughput_audit.json"
    review_path = REPO_ROOT / "reports" / "v5_exp003_bounded_k_adversarial_review_20260709.md"
    trace_path = REPO_ROOT / "tmp" / "exp003_bounded_validation_20260709_0945" / "det_a" / "trace.txt"
    trainer_path = (
        run_dir
        / "exp003_judgment_inputs"
        / "train_v5_pinned_8b951a43e3b86f6eb38600a69c33ce793c3b4658047325ac06d6e11f6a0b8b31.py"
    )
    evaluator_path = (
        run_dir
        / "exp003_judgment_inputs"
        / "v5_mirror_eval_pinned_2f9e81eae19e0da37da0d9be05dafbf820e812ac8366604cd2ad13f6aa7f0013.py"
    )

    hard_checks = [
        check("candidate_gate_streak", gates["status"] == "PASS", json.dumps(gates, sort_keys=True)),
        check("effective_throughput", len(enriched[-60:]) == 60 and throughput_ratio >= MIN_EFFECTIVE_HPS_RATIO, f"tail60={candidate_effective:.1f}, baseline={BASELINE_EFFECTIVE_HPS:.1f}, ratio={throughput_ratio:.4f}"),
        check("trainer_stderr_empty", (run_dir / "console.err.log").exists() and (run_dir / "console.err.log").stat().st_size == 0, str(run_dir / "console.err.log")),
        check("exp003_live_counters", counter_audit["status"] == "PASS", json.dumps(counter_audit, sort_keys=True)),
        check("registered_config", config["status"] == "PASS", json.dumps(config, sort_keys=True)),
        check("fresh_from_zero_lineage", checkpoint_meta.get("fresh_from_zero_lineage") is True, f"checkpoint={checkpoint_meta.get('fresh_from_zero_lineage')!r}"),
        check("actual_hand_accounting", checkpoint_meta.get("actual_hand_accounting") is True, f"checkpoint={checkpoint_meta.get('actual_hand_accounting')!r}"),
        check("candidate_entropy_floor", float(candidate_rows[-1]["entropy"]) >= 0.3, f"entropy={candidate_rows[-1]['entropy']}"),
        check("value_loss_no_10x_explosion", statistics.fmean(float(row["value_loss"]) for row in candidate_window) <= 10.0 * statistics.fmean(float(row["value_loss"]) for row in baseline_window), "candidate 200-row mean must be <=10x pre mean"),
        check("postflop_no_hard_collapse", shape_status != "COLLAPSE" and shape_status != "INVALID", f"shape_status={shape_status}, mean={shape_mean}"),
    ]
    reference_artifacts = {
        "baseline_throughput_audit": artifact_guard(baseline_audit, DEFAULT_BASELINE_AUDIT_SHA256),
        "trainer": artifact_guard(trainer_path, DEFAULT_TRAINER_SHA256),
        "mirror_evaluator": artifact_guard(evaluator_path, DEFAULT_EVALUATOR_SHA256),
        "offline_adversarial_review": artifact_guard(review_path, DEFAULT_REVIEW_SHA256),
        "offline_determinism_trace": artifact_guard(trace_path, DEFAULT_TRACE_SHA256),
    }
    failed_reference_artifacts = {
        name: result for name, result in reference_artifacts.items() if result["status"] != "PASS"
    }
    if failed_reference_artifacts:
        raise RuntimeError(
            "EXP-003 reference artifact integrity failed: "
            + json.dumps(failed_reference_artifacts, sort_keys=True)
        )

    hard_guard_status = "PASS" if all(row["status"] == "PASS" for row in hard_checks if row["hard"]) else "FAIL"
    effect_statuses = [effects["native_axis"]["status"], effects["direct_causal"]["status"]]
    ci_precision_gate = {
        "status": "FAIL" if measurement_status == EXP003_CI_PRECISION_FAILED else "PASS",
        "failed_roles": ci_precision_failed_roles,
        "target_ci95_halfwidth_bb100": 20.0,
        "rule": (
            "The fixed 25k-pair precision gate failed; this frozen measurement may only be recorded "
            "as INCONCLUSIVE and cannot be extended or substituted."
            if measurement_status == EXP003_CI_PRECISION_FAILED
            else "All registered mirror roles passed the fixed 25k-pair precision gate."
        ),
        "legacy_inconclusive_roles": legacy_contract.get("legacy_roles", []),
    }
    if measurement_status == EXP003_CI_PRECISION_FAILED:
        # The protocol fixes both the sample size and checkpoint.  A precision
        # failure is evidence about measurement resolution, not causal effect,
        # so it must close the window as explicit INCONCLUSIVE rather than turn
        # a broad interval into ADOPT or ROLLBACK.
        decision = "INCONCLUSIVE"
        reason = (
            "complete structurally valid fixed-window bundle failed the registered CI precision gate "
            f"for roles: {', '.join(ci_precision_failed_roles)}"
        )
    elif hard_guard_status == "FAIL" or "REGRESSION" in effect_statuses or value_support["status"] == "REGRESSION" or shape_status == "COLLAPSE":
        decision = "ROLLBACK"
        reason = "hard abort guard or statistically significant registered regression"
    elif effect_statuses == ["PASS", "PASS"] and value_support["status"] == "PASS" and shape_status == "PASS":
        decision = "ADOPT"
        reason = "both causal mirror gates, all hard guards, and both pre-registered method-support gates pass"
    else:
        decision = "INCONCLUSIVE"
        reason = "valid fixed-window bundle has no decisive hard regression, but at least one effect/support interval includes zero or lacks support"

    role_artifacts: dict[str, Any] = {}
    for role, record in bundle["roles"].items():
        paths = [Path(record["path"]), *(Path(value) for value in record["companion_paths"].values())]
        role_artifacts[role] = {str(path): sha256_file(path) for path in paths}

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now_iso(),
        "experiment_id": "EXP-003",
        "claim_scope": "method_judgment_only_not_slumbot_not_l5_l6",
        "measurement_status": measurement_status,
        "decision": decision,
        "decision_valid": True,
        "decision_reason": reason,
        "candidate_checkpoint_iteration": candidate_iteration,
        "candidate_checkpoint_hands": candidate_hands,
        "candidate_checkpoint_path": freeze["archive_path"],
        "candidate_checkpoint_sha256": freeze["archive_sha256"],
        "registered_target_hands": EXP003_NATIVE_MIRROR_TARGET_HANDS,
        "effects": effects,
        "ci_precision_gate": ci_precision_gate,
        "legacy_inconclusive_roles": legacy_contract.get("legacy_roles", []),
        "legacy_preflight_contract": legacy_contract.get("contract"),
        "hard_guards": {"status": hard_guard_status, "checks": hard_checks},
        "method_support": method_support,
        "throughput": {
            "status": "PASS" if throughput_ratio >= MIN_EFFECTIVE_HPS_RATIO else "FAIL",
            "baseline_effective_hps_tail60": BASELINE_EFFECTIVE_HPS,
            "candidate": throughput_window,
            "ratio": throughput_ratio,
            "minimum_ratio": MIN_EFFECTIVE_HPS_RATIO,
        },
        "counter_audit": counter_audit,
        "gate_guard": gates,
        "config_guard": config,
        "reference_artifacts": reference_artifacts,
        "model_input_guard": model_inputs,
        "mirror_artifact_sha256": role_artifacts,
        "bundle": bundle,
        "next_rule": (
            "retain EXP-003 and close its behavior window" if decision == "ADOPT" else
            "execute the registered rollback before opening another behavior window" if decision == "ROLLBACK" else
            "do not extend or substitute the checkpoint; register the next measurement design before any behavior change"
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    native = result["effects"]["native_axis"]
    direct = result["effects"]["direct_causal"]
    value = result["method_support"]["value_loss"]
    shape = result["method_support"]["postflop_raise_plus_allin"]
    ci_precision = result.get("ci_precision_gate") if isinstance(result.get("ci_precision_gate"), dict) else {}
    lines = [
        "# EXP-003 Fixed-Window Judgment",
        "",
        f"- Measurement status: `{result.get('measurement_status')}`",
        f"- Decision: `{result['decision']}`",
        f"- Reason: {result['decision_reason']}",
        f"- Candidate iter/hands: `{result['candidate_checkpoint_iteration']}` / `{result['candidate_checkpoint_hands']:,}`",
        f"- Frozen checkpoint SHA256: `{result['candidate_checkpoint_sha256']}`",
        f"- Native-axis delta: `{native['delta_bb100']:+.3f} +/- {native['combined_ci95_halfwidth_bb100']:.3f} bb/100` -> `{native['status']}`",
        f"- Direct post-vs-pre: `{direct['point_bb100']:+.3f} +/- {direct['ci95_halfwidth_bb100']:.3f} bb/100` -> `{direct['status']}`",
        f"- Hard guards: `{result['hard_guards']['status']}`",
        f"- Effective h/s ratio: `{result['throughput']['ratio']:.4f}` (minimum `{result['throughput']['minimum_ratio']}`)",
        f"- Value-loss pre-minus-post: `{value['pre_minus_post']:+.3f}` CI `[{value['ci95_lower']:+.3f}, {value['ci95_upper']:+.3f}]` -> `{value['status']}`",
        f"- Postflop raise+all-in mean: `{shape['mean']}` -> `{shape['status']}`",
        f"- Fixed CI precision gate: `{ci_precision.get('status')}`; failed roles: `{', '.join(ci_precision.get('failed_roles') or []) or 'none'}`",
        "",
        "This is an EXP-003 method judgment only. It is not Slumbot evidence and cannot support V4, L5, or L6 strength claims.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the registered EXP-003 fixed-window judgment.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--baseline-run-dir", default=str(DEFAULT_BASELINE_RUN))
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    result = build_judgment(args)
    write_json(Path(args.out_json), result)
    write_markdown(result, Path(args.out_md))
    print(json.dumps({"decision": result["decision"], "candidate_checkpoint_hands": result["candidate_checkpoint_hands"], "out_json": args.out_json}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
