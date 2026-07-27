#!/usr/bin/env python3
"""Build a read-only next-action queue for the V5 L6 run.

This turns scattered watcher state into an ordered list of trigger-driven
actions. It deliberately separates operational actions from strength claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from v5_run_dashboard import build_summary, format_duration

POST_GATE_REFRESH_STATES = {
    "PENDING_EVIDENCE",
    "DUE_EVIDENCE_REFRESH",
    "QUARANTINED_INTERNAL_PROBE_IDENTITY",
    "QUARANTINED_GATE_IDENTITY",
}
EXP003_NATIVE_MIRROR_TARGET_HANDS = 408_064_575
EXP003_CUTOVER_ITERATION = 21_800
EXP003_CUTOVER_HANDS = 358_064_575
EXP003_NATIVE_ANCHOR_HANDS = 75_479_020
EXP003_MIRROR_PAIRS = 25_000
EXP003_MIRROR_SEED = 20_260_709
EXP003_MIRROR_POLICY_MODE = "greedy_argmax_both_sides"
EXP003_MIRROR_OOD_MAX = 0.15
EXP003_PRE_SHA256 = "60d3b7ffbfe750cc8c0d1e4dfcd80a308d6a3f406a4b5e5265b9d9563d8877d5"
EXP003_NATIVE_SHA256 = "47318cf20388f0f2cfdc63d9d76bd6c5519d39de54ab0e24589fcb1f90fc8f63"
EXP003_EVALUATOR_SHA256 = "2f9e81eae19e0da37da0d9be05dafbf820e812ac8366604cd2ad13f6aa7f0013"
EXP003_CI_PRECISION_FAILED = "CI_PRECISION_FAILED"
EXP003_CONTENTION_REAUDIT_SCHEMA_VERSION = "v5.exp003.contention_reaudit.v1"
EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER = {
    "command_line_sha256": "44c3ed8b57ec746601e187d31dded536e9a623d532128050779f216deb423b0c",
    "script_sha256": "a7ba0c5f2fd8e44c0200472e5b3a2f00fb442a275e66d41709e160d43e155cba",
    "pid": 24724,
    "creation_date": "/Date(1783638953136)/",
    "checked_at": "2026-07-09T23:15:53.851103+00:00",
    "snapshot_sha256": "c9a31754090c9ad844e5d2ea452c7f6d11e9ea1d21d1b819bac01bd646fbf231",
    "launcher_sha256": "2b13d4f25c9a7eb179f4909b01548c47dba4eaa86cc157768b458dd49b03b9f7",
    "quarantine_sha256": "70ab1895b4fe42896ab48f564ac52dec37014428908025ef365e8b167db0a848",
}
EXP003_CONTENTION_RECOVERY_SCOPE = (
    "publish_exact_existing_staged_role_only_no_new_pairs_then_continue_remaining_fixed_role"
)
EXP003_LEGACY_PRE_RUN_ID = "v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709"
EXP003_LEGACY_PRE_RESULT_NAME = "v5_mirror_eval_exp003_pre_vs_native_gate21800_25kp.json"
EXP003_LEGACY_PRE_SCHEMA_VERSION = "v5.exp003.pre_vs_native.legacy_provenance.v1"
EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION = "v5.exp003.pre_vs_native.legacy_provenance_audit.v1"
EXP003_LEGACY_PRE_ARTIFACTS = {
    "result": {"sha256": "492fcba3bd3d545a36dcefc97e948333b1037c1cf3a3609e599bf9a099739ffe", "bytes": 5983},
    "markdown": {"sha256": "a1c4751c90f2171abe8852b71181fd9793c3726d109c27843b73177b848b4b14", "bytes": 1355},
    "stdout": {"sha256": "492fcba3bd3d545a36dcefc97e948333b1037c1cf3a3609e599bf9a099739ffe", "bytes": 5983},
    "stderr": {"sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "bytes": 0},
    "execution": {"sha256": "f8a742c54236ed44f180aea895765967c8197d3da8136886aa0661861060a4f6", "bytes": 2200},
    "launcher": {"sha256": "d1e780eabcc79c4ddc44769de41f4b8fd36de7491e285c0caaa57be05e34def0", "bytes": 598},
}
EXP003_LEGACY_PRE_OPS_ROWS = {
    "exp003_mirror_pre_native_rerun1_start_20260709_1745": "5bb22e6e6bc552da667ad3de875fde7f2425f3c2831148e872c76a03574adbe8",
    "exp003_mirror_evaluator_pin_20260709_1800": "f8436ebb1ad15d97473530b38db7cbe72277912697dbc6694461fc10cc230ca1",
    "exp003_mirror_pre_native_result_20260709_1801": "01e7eabc2c6afe5ebadc929df3f11e42c7667470e178e67664db81ecb2f0f7c1",
    "exp003_mirror_pre_native_independent_audit_20260709_1805": "52de8caddeffe36be77dd35ebc2e9a6c9b46d506681fbefd5e42e4a5c11e5180",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} root is not an object"}


def load_intervention_plan(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[int, str, Path, dict[str, Any]]] = []
    patterns = [
        "v5_context_preflop_intervention_plan_*.json",
        "v5_preflop_intervention_plan.json",
    ]
    for priority, pattern in enumerate(patterns):
        for path in sorted(run_dir.glob(pattern)):
            plan = load_json(path)
            if plan.get("_missing") or plan.get("_load_error"):
                continue
            checked_at = str(plan.get("checked_at") or "")
            target_iteration = plan.get("target_iteration")
            target_sort = int(target_iteration) if isinstance(target_iteration, int) else -1
            candidates.append((priority, f"{target_sort:010d}:{checked_at}", path, plan))
    if not candidates:
        path = run_dir / "v5_preflop_intervention_plan.json"
        return path, load_json(path)
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, _, selected_path, selected_plan = candidates[-1]
    return selected_path, selected_plan


def pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except Exception:
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def resolve_artifact_path(path_text: Any) -> Path | None:
    if not path_text:
        return None
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    return path


def sibling_artifact_from_ci(ci_path: Path | None, suffix: str) -> Path | None:
    if ci_path is None:
        return None
    text = str(ci_path)
    ci_suffix = "_ci_summary.json"
    if not text.endswith(ci_suffix):
        return None
    return Path(text[: -len(ci_suffix)] + suffix)


def latest_promotion20k_prerequisite(output_dir: Path, run_id: str) -> dict[str, Any]:
    paths = sorted(output_dir.glob(f"bench_v55_*{run_id}*promotion20k*_promotion_gate.json"))
    if not paths:
        return {
            "status": "BLOCKED",
            "detail": "no promotion20k promotion_gate.json found for this run",
            "path": None,
            "promotion_20k_candidate": False,
            "promotion_20k_strong": False,
        }

    best: tuple[int, str, Path, dict[str, Any]] | None = None
    for path in paths:
        gate = load_json(path)
        if gate.get("_missing") or gate.get("_load_error"):
            continue
        checkpoint = gate.get("checkpoint") if isinstance(gate.get("checkpoint"), dict) else {}
        hands = checkpoint.get("total_hands")
        try:
            hands_key = int(hands)
        except (TypeError, ValueError):
            hands_key = -1
        checked_at = str(gate.get("checked_at") or "")
        item_key = (hands_key, checked_at, path, gate)
        if best is None or item_key[:2] > best[:2]:
            best = item_key

    if best is None:
        return {
            "status": "BLOCKED",
            "detail": "promotion20k gate artifacts were found but none were readable",
            "path": None,
            "promotion_20k_candidate": False,
            "promotion_20k_strong": False,
        }

    _, _, path, gate = best
    decisions = gate.get("decisions") if isinstance(gate.get("decisions"), dict) else {}
    strong = bool(decisions.get("promotion_20k_strong"))
    candidate = bool(decisions.get("promotion_20k_candidate"))
    if strong:
        status = "PASS"
        detail = f"promotion20k strong gate passed: {path}"
    else:
        status = "BLOCKED"
        detail = (
            f"latest promotion20k gate is not strong: candidate={candidate}, "
            f"strong={strong}, path={path}"
        )
    return {
        "status": status,
        "detail": detail,
        "path": str(path),
        "promotion_20k_candidate": candidate,
        "promotion_20k_strong": strong,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _exp003_mirror_record(path: Path, mirror: dict[str, Any]) -> dict[str, Any]:
    anchors = mirror.get("anchors") if isinstance(mirror.get("anchors"), list) else []
    anchors = [row for row in anchors if isinstance(row, dict)]
    anchor = anchors[0] if len(anchors) == 1 else {}
    candidate_hands = _int_or_none(pick(mirror, "candidate", "checkpoint", "total_hands"))
    anchor_hands = _int_or_none(pick(anchor, "anchor_checkpoint", "total_hands"))
    gate = mirror.get("gate") if isinstance(mirror.get("gate"), dict) else {}
    pairs = _int_or_none(mirror.get("pairs"))
    seed = _int_or_none(mirror.get("seed"))
    policy_mode = str(mirror.get("policy_mode") or anchor.get("policy_mode") or "")
    starting_stack = finite_float(mirror.get("starting_stack"))
    ood_rate = finite_float(anchor.get("anchor_ood_node_rate"))
    ood_threshold = finite_float(anchor.get("anchor_ood_valid_threshold"))
    if ood_threshold is None:
        ood_threshold = finite_float(gate.get("anchor_ood_valid_threshold"))
    candidate_sha256 = str(pick(mirror, "candidate", "sha256") or "").lower()
    anchor_sha256 = str(anchor.get("anchor_sha256") or "").lower()
    candidate_path = str(pick(mirror, "candidate", "path") or "")
    anchor_path = str(anchor.get("anchor_path") or "")
    candidate_iteration = _int_or_none(pick(mirror, "candidate", "checkpoint", "iteration"))
    anchor_iteration = _int_or_none(pick(anchor, "anchor_checkpoint", "iteration"))
    execution = mirror.get("execution") if isinstance(mirror.get("execution"), dict) else {}
    priority = execution.get("priority") if isinstance(execution.get("priority"), dict) else {}
    priority_ok = bool(priority.get("applied")) and str(priority.get("actual_label") or "").lower() == "belownormal"
    execution_ok = (
        str(execution.get("status") or "").upper() == "COMPLETED"
        and priority_ok
        and (_int_or_none(execution.get("pid")) or 0) > 0
        and isinstance(execution.get("command"), list)
        and len(execution.get("command")) > 1
        and bool(execution.get("working_directory"))
        and _int_or_none(execution.get("torch_threads")) == 1
        and _int_or_none(execution.get("torch_interop_threads")) == 1
    )
    stem = str(path)[:-5] if str(path).lower().endswith(".json") else str(path)
    companion_paths = {
        "markdown": Path(stem + ".md"),
        "stdout": Path(stem + ".stdout.log"),
        "stderr": Path(stem + ".stderr.log"),
        "execution": Path(stem + ".execution.json"),
        "launcher": Path(stem + ".launcher.json"),
    }
    companion_execution = load_json(companion_paths["execution"])
    launcher = load_json(companion_paths["launcher"])
    stdout_summary = load_json(companion_paths["stdout"])
    expected_input_sha256 = {
        "evaluator": EXP003_EVALUATOR_SHA256,
        "candidate": candidate_sha256,
        "anchor": anchor_sha256,
    }
    launcher_contention_snapshots = launcher.get("contention_snapshots")
    launcher_monitor_errors = launcher.get("contention_monitor_errors")
    # Canonical publication normally proves that the evaluator completed with
    # exactly the pinned inputs and that its monitor saw no contention.  Do
    # not infer this from a result JSON alone: an exceptional recovered path
    # is considered separately and must carry a forensic certificate.
    launcher_clean = (
        str(launcher.get("state") or "").upper() == "COMPLETED"
        and _int_or_none(launcher.get("return_code")) == 0
        and launcher.get("input_sha256_pre") == expected_input_sha256
        and launcher.get("input_sha256_post") == expected_input_sha256
        and launcher.get("posthash_error") in {None, ""}
        and launcher.get("contention_detected") is False
        and isinstance(launcher_contention_snapshots, list)
        and not launcher_contention_snapshots
        and isinstance(launcher_monitor_errors, list)
        and not launcher_monitor_errors
    )
    companions_ok = (
        all(companion.exists() for companion in companion_paths.values())
        and companion_paths["markdown"].stat().st_size > 0
        and companion_paths["stdout"].stat().st_size > 0
        and not companion_execution.get("_missing")
        and not companion_execution.get("_load_error")
        and companion_execution == execution
        and not launcher.get("_missing")
        and not launcher.get("_load_error")
        and str(launcher.get("evaluator_sha256") or "").lower() == EXP003_EVALUATOR_SHA256
        and _int_or_none(launcher.get("pid")) == _int_or_none(execution.get("pid"))
        and _int_or_none(launcher.get("pairs")) == EXP003_MIRROR_PAIRS
        and _int_or_none(launcher.get("seed")) == EXP003_MIRROR_SEED
        and finite_float(launcher.get("starting_stack")) == 200.0
        and str(launcher.get("device") or "").lower() == "cpu"
        and str(launcher.get("priority") or "").lower() == "below-normal"
        and not stdout_summary.get("_missing")
        and not stdout_summary.get("_load_error")
        and stdout_summary == mirror
    )
    stderr_empty = companion_paths["stderr"].exists() and companion_paths["stderr"].stat().st_size == 0
    candidate_bb100 = finite_float(anchor.get("candidate_bb100"))
    candidate_ci95_bb100 = finite_float(anchor.get("candidate_ci95_bb100"))
    numeric_fields_present = (
        ood_rate is not None
        and candidate_bb100 is not None
        and candidate_ci95_bb100 is not None
    )
    ci_precision_within_limit = bool(
        candidate_ci95_bb100 is not None
        and abs(candidate_ci95_bb100) <= 20.0
    )
    ci_gate_value = gate.get("passes_ci_gate")
    ci_gate_declared = isinstance(ci_gate_value, bool)
    ci_ok = bool(ci_gate_value) if ci_gate_declared else False
    # At the registered fixed 25k-pair protocol the evaluator's CI gate is
    # exactly the <=20 bb/100 precision threshold.  A missing or inconsistent
    # declaration is an artifact/protocol problem, not an inconclusive result.
    ci_precision_consistent = bool(
        ci_gate_declared and ci_ok == ci_precision_within_limit
    )
    ci_precision_failed = bool(
        ci_precision_consistent and not ci_ok
    )
    numeric_ok = bool(numeric_fields_present and ci_precision_within_limit)
    ood_ok = bool(gate.get("all_anchors_pass_ood_gate"))
    if "all_anchors_pass_ood_gate" not in gate:
        ood_ok = bool(anchor.get("anchor_ood_valid"))
    if ood_rate is not None:
        ood_ok = ood_ok and ood_rate <= EXP003_MIRROR_OOD_MAX
    non_launcher_structural_ok = (
        len(anchors) == 1
        and pairs is not None
        and pairs == EXP003_MIRROR_PAIRS
        and seed == EXP003_MIRROR_SEED
        and policy_mode == EXP003_MIRROR_POLICY_MODE
        and starting_stack == 200.0
        and str(mirror.get("device") or "").lower() == "cpu"
        and ood_threshold == EXP003_MIRROR_OOD_MAX
        and bool(candidate_sha256)
        and bool(anchor_sha256)
        and numeric_fields_present
        and execution_ok
        and companions_ok
        and stderr_empty
        and ood_ok
    )
    # "judgmentable" deliberately excludes the *precision outcome*, but not
    # any structural, protocol, execution, OOD, or identity evidence.  This
    # lets a complete fixed-window bundle honestly terminate as inconclusive
    # when precision alone failed, while keeping all other invalid artifacts
    # fail-closed.
    base_judgmentable = bool(non_launcher_structural_ok and ci_precision_consistent)
    launcher_evidence_ok = launcher_clean
    judgmentable = bool(base_judgmentable and launcher_evidence_ok)
    usable = bool(judgmentable and ci_ok)
    return {
        "path": str(path),
        "checked_at": str(mirror.get("checked_at") or ""),
        "candidate_hands": candidate_hands,
        "anchor_hands": anchor_hands,
        "candidate_iteration": candidate_iteration,
        "anchor_iteration": anchor_iteration,
        "candidate_path": candidate_path,
        "anchor_path": anchor_path,
        "candidate_sha256": candidate_sha256,
        "anchor_sha256": anchor_sha256,
        "pairs": pairs,
        "seed": seed,
        "policy_mode": policy_mode,
        "starting_stack": starting_stack,
        "ci_ok": ci_ok,
        "ci_gate_declared": ci_gate_declared,
        "ci_precision_within_limit": ci_precision_within_limit,
        "ci_precision_consistent": ci_precision_consistent,
        "ci_precision_failed": ci_precision_failed,
        "ood_ok": ood_ok,
        "ood_rate": ood_rate,
        "ood_threshold": ood_threshold,
        "device": str(mirror.get("device") or ""),
        "execution_ok": execution_ok,
        "companions_ok": companions_ok,
        "stderr_empty": stderr_empty,
        "expected_input_sha256": expected_input_sha256,
        "launcher_clean": launcher_clean,
        "launcher_evidence_ok": launcher_evidence_ok,
        "base_judgmentable": base_judgmentable,
        "companion_paths": {key: str(value) for key, value in companion_paths.items()},
        "candidate_bb100": candidate_bb100,
        "candidate_ci95_bb100": candidate_ci95_bb100,
        "numeric_ok": numeric_ok,
        "judgmentable": judgmentable,
        "usable": usable,
    }


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _same_existing_path(value: Any, path: Path) -> bool:
    try:
        return Path(str(value)).resolve() == path.resolve()
    except (OSError, ValueError):
        return str(value) == str(path)


def _fingerprint_matches_path(fingerprint: Any, path: Path, *, require_path: bool = True) -> bool:
    if not isinstance(fingerprint, dict) or not path.is_file():
        return False
    if require_path and not _same_existing_path(fingerprint.get("path"), path):
        return False
    return bool(
        str(fingerprint.get("sha256") or "").lower() == sha256_file(path)
        and _int_or_none(fingerprint.get("bytes")) == path.stat().st_size
    )


def _exp003_contention_reaudit_path(record: dict[str, Any]) -> Path:
    raw = str(record.get("path") or "")
    stem = raw[:-5] if raw.lower().endswith(".json") else raw
    return Path(stem + ".contention_reaudit.json")


def _recovered_launcher_certificate(
    record: dict[str, Any],
    role_name: str,
) -> dict[str, Any]:
    """Validate the one registered false-positive contention recovery.

    This is intentionally a narrow verifier, not a generic exception for a
    launcher that reports contention.  It re-proves the immutable certificate,
    its retained staged sources, the current canonical copies, and the exact
    historical observer identity before the role can become judgmentable.
    """

    certificate_path = _exp003_contention_reaudit_path(record)
    certificate = load_json(certificate_path)
    failure = lambda reason: {
        "status": "FAIL",
        "path": str(certificate_path),
        "reason": reason,
    }
    if certificate.get("_missing") or certificate.get("_load_error"):
        return failure("canonical contention re-audit certificate is missing or unreadable")
    required_truths = {
        "recovery_eligible": True,
        "forensic_verdict": "PASS",
        "all_saved_contention_snapshots_reclassified": True,
        "no_slumbot_blocking_state": True,
        "no_monitor_errors": True,
        "raw_identity_protocol_audit_pass": True,
        "original_launcher_and_quarantine_preserved": True,
    }
    if certificate.get("schema_version") != EXP003_CONTENTION_REAUDIT_SCHEMA_VERSION:
        return failure("contention re-audit schema version does not match the registered verifier")
    if str(certificate.get("state") or "").upper() != "FALSE_POSITIVE_CONTENTION_REAUDIT_PASS":
        return failure("contention re-audit is not an explicit PASS certificate")
    if str(certificate.get("role") or "") != role_name or _int_or_none(certificate.get("attempt")) != 1:
        return failure("contention re-audit role or attempt does not match the canonical role")
    if not _same_existing_path(certificate.get("canonical_companion_path"), certificate_path):
        return failure("contention re-audit canonical companion path does not bind this role")
    if certificate.get("recovery_scope") != EXP003_CONTENTION_RECOVERY_SCOPE:
        return failure("contention re-audit recovery scope is not the registered no-new-pairs scope")
    if any(certificate.get(key) != expected for key, expected in required_truths.items()):
        return failure("contention re-audit required PASS flags are incomplete or false")

    staged_certificate_path = Path(str(certificate.get("staged_companion_path") or ""))
    if not staged_certificate_path.is_file() or sha256_file(staged_certificate_path) != sha256_file(certificate_path):
        return failure("staged immutable contention certificate is missing or no longer byte-identical")

    source = certificate.get("source") if isinstance(certificate.get("source"), dict) else {}
    raw_artifacts = source.get("raw_artifacts") if isinstance(source.get("raw_artifacts"), dict) else {}
    raw_names = {"result", "markdown", "stdout", "stderr", "execution", "launcher"}
    if set(raw_artifacts) != raw_names:
        return failure("contention re-audit does not bind the complete raw artifact set")
    current_paths = {
        "result": Path(str(record.get("path") or "")),
        **{
            name: Path(str(path))
            for name, path in (record.get("companion_paths") or {}).items()
            if name in raw_names
        },
    }
    if set(current_paths) != raw_names:
        return failure("canonical role has an incomplete raw companion-path set")
    for name in sorted(raw_names):
        saved = raw_artifacts.get(name)
        staged_path = Path(str((saved or {}).get("path") or ""))
        canonical_path = current_paths[name]
        if not _fingerprint_matches_path(saved, staged_path):
            return failure(f"contention re-audit staged raw artifact fingerprint failed: {name}")
        if not canonical_path.is_file():
            return failure(f"canonical raw artifact is missing: {name}")
        if (
            sha256_file(canonical_path) != str((saved or {}).get("sha256") or "").lower()
            or canonical_path.stat().st_size != _int_or_none((saved or {}).get("bytes"))
        ):
            return failure(f"canonical raw artifact no longer matches re-audited staged bytes: {name}")

    source_launcher = source.get("launcher")
    source_quarantine = source.get("quarantine")
    source_terminal_status = source.get("terminal_status")
    if source_launcher != raw_artifacts.get("launcher"):
        return failure("contention re-audit launcher fingerprint is not bound to raw launcher bytes")
    launcher_path = Path(str((source_launcher or {}).get("path") or ""))
    quarantine_path = Path(str((source_quarantine or {}).get("path") or ""))
    if not _fingerprint_matches_path(source_launcher, launcher_path):
        return failure("retained staged launcher fingerprint does not verify")
    if not _fingerprint_matches_path(source_quarantine, quarantine_path):
        return failure("retained staged quarantine fingerprint does not verify")
    terminal_snapshot = certificate.get("terminal_status_snapshot")
    expected_terminal_path = Path(str(record.get("path") or "")).parent / "v5_exp003_bundle_watch_status.json"
    if not isinstance(terminal_snapshot, dict):
        return failure("contention re-audit does not retain the pre-recovery terminal status snapshot")
    if not _same_existing_path((source_terminal_status or {}).get("path"), expected_terminal_path):
        return failure("contention re-audit terminal-status source path is not the canonical bundle watcher status")
    if not (
        str((source_terminal_status or {}).get("sha256") or "").lower()
        == _canonical_json_sha256(terminal_snapshot)
        and certificate.get("terminal_status_snapshot_sha256")
        == str((source_terminal_status or {}).get("sha256") or "").lower()
        and _int_or_none((source_terminal_status or {}).get("bytes"))
        == len((json.dumps(terminal_snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        and terminal_snapshot.get("terminal") is True
        and str(terminal_snapshot.get("overall") or "").upper() == "FAIL"
        and str(terminal_snapshot.get("state") or "") == "MEASUREMENT_CONTENTION_QUARANTINED"
    ):
        return failure("contention re-audit terminal status does not bind the original contention-quarantined failure")
    if str((source_launcher or {}).get("sha256") or "").lower() != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["launcher_sha256"]:
        return failure("retained launcher hash is not the exact registered false-positive source")
    if str((source_quarantine or {}).get("sha256") or "").lower() != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["quarantine_sha256"]:
        return failure("retained quarantine hash is not the exact registered false-positive source")

    raw_launcher = load_json(launcher_path)
    quarantine = load_json(quarantine_path)
    if raw_launcher.get("_missing") or raw_launcher.get("_load_error"):
        return failure("retained staged launcher cannot be read")
    if quarantine.get("_missing") or quarantine.get("_load_error"):
        return failure("retained staged quarantine cannot be read")
    expected_inputs = record.get("expected_input_sha256")
    if not isinstance(expected_inputs, dict):
        return failure("canonical role lacks expected launcher input hashes")
    if not (
        str(raw_launcher.get("state") or "").upper() == "COMPLETED"
        and _int_or_none(raw_launcher.get("return_code")) == 0
        and raw_launcher.get("input_sha256_pre") == expected_inputs
        and raw_launcher.get("input_sha256_post") == expected_inputs
        and raw_launcher.get("posthash_error") in {None, ""}
        and raw_launcher.get("contention_detected") is True
        and raw_launcher.get("contention_monitor_errors") == []
    ):
        return failure("retained launcher does not prove clean execution except the exact contention flag")
    if not (
        str(quarantine.get("state") or "").upper() == "QUARANTINED"
        and quarantine.get("published") is False
        and str(quarantine.get("role") or "") == role_name
    ):
        return failure("retained quarantine does not prove this exact role stayed unpublished")

    snapshots = raw_launcher.get("contention_snapshots")
    quarantine_snapshots = quarantine.get("evidence")
    if (
        not isinstance(snapshots, list)
        or len(snapshots) != 1
        or not isinstance(quarantine_snapshots, list)
        or _canonical_json_sha256(snapshots) != _canonical_json_sha256(quarantine_snapshots)
    ):
        return failure("retained launcher/quarantine contention snapshots are incomplete or differ")
    snapshot = snapshots[0]
    if not isinstance(snapshot, dict):
        return failure("retained contention snapshot is not an object")
    if (
        _canonical_json_sha256(snapshot) != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["snapshot_sha256"]
        or str(snapshot.get("checked_at") or "") != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["checked_at"]
        or snapshot.get("busy") is not True
        or snapshot.get("slumbot_running_statuses") != []
    ):
        return failure("retained contention snapshot is not the exact registered false positive")
    processes = snapshot.get("processes")
    if not isinstance(processes, list) or len(processes) != 1 or not isinstance(processes[0], dict):
        return failure("retained contention snapshot does not contain exactly one observer process")
    process = processes[0]
    if (
        _int_or_none(process.get("pid")) != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["pid"]
        or str(process.get("creation_date") or "") != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["creation_date"]
        or hashlib.sha256(str(process.get("command_line") or "").encode("utf-8")).hexdigest()
        != EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["command_line_sha256"]
    ):
        return failure("retained observer PID, CreationDate, or command bytes are not allowlisted")

    classifier = certificate.get("classifier") if isinstance(certificate.get("classifier"), dict) else {}
    classified = classifier.get("snapshots") if isinstance(classifier.get("snapshots"), list) else []
    if not (
        str(classifier.get("status") or "").upper() == "PASS"
        and classifier.get("all_saved_snapshots_covered") is True
        and classifier.get("launcher_quarantine_snapshots_exact_match") is True
        and _int_or_none(classifier.get("launcher_snapshot_count")) == 1
        and _int_or_none(classifier.get("quarantine_snapshot_count")) == 1
        and len(classified) == 1
        and isinstance(classified[0], dict)
    ):
        return failure("contention classifier does not prove every saved snapshot was reclassified")
    classified_snapshot = classified[0]
    snapshot_allowlist = classified_snapshot.get("historical_allowlist")
    expected_snapshot_allowlist = {
        "pid": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["pid"],
        "creation_date": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["creation_date"],
        "checked_at": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["checked_at"],
        "snapshot_sha256": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["snapshot_sha256"],
    }
    classified_processes = classified_snapshot.get("processes")
    if not (
        str(classified_snapshot.get("status") or "").upper() == "PASS"
        and classified_snapshot.get("snapshot_sha256") == EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["snapshot_sha256"]
        and snapshot_allowlist == expected_snapshot_allowlist
        and classified_snapshot.get("busy") is True
        and classified_snapshot.get("slumbot_running_statuses") == []
        and isinstance(classified_processes, list)
        and len(classified_processes) == 1
        and isinstance(classified_processes[0], dict)
    ):
        return failure("certificate classifier snapshot is not the exact allowlisted observer evidence")
    classified_process = classified_processes[0]
    classification = classified_process.get("classification") if isinstance(classified_process.get("classification"), dict) else {}
    expected_command_allowlist = {
        "command_line_sha256": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["command_line_sha256"],
        "script_sha256": EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["script_sha256"],
    }
    if not (
        str(classified_process.get("status") or "").upper() == "PASS"
        and _int_or_none(classified_process.get("pid")) == EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["pid"]
        and str(classified_process.get("creation_date") or "") == EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["creation_date"]
        and str(classification.get("status") or "").upper() == "PASS"
        and classification.get("command_line_sha256") == EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["command_line_sha256"]
        and classification.get("script_sha256") == EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER["script_sha256"]
        and classification.get("corrected_eval_invocation") == []
        and classification.get("historical_allowlist") == expected_command_allowlist
    ):
        return failure("certificate classifier process does not bind the exact observer command and script")

    raw_audit = certificate.get("raw_audit") if isinstance(certificate.get("raw_audit"), dict) else {}
    structural_checks = raw_audit.get("structural_checks") if isinstance(raw_audit.get("structural_checks"), dict) else {}
    if not (
        str(raw_audit.get("status") or "").upper() == "PASS"
        and bool(structural_checks)
        and all(value is True for value in structural_checks.values())
        and raw_audit.get("input_sha256_actual") == expected_inputs
        and raw_audit.get("raw_contention_clean") is False
        and raw_audit.get("reaudited_contention_exception_used") is True
    ):
        return failure("contention re-audit does not prove identity/protocol validation under only the exception")
    return {
        "status": "PASS",
        "path": str(certificate_path),
        "sha256": sha256_file(certificate_path),
        "reason": "exact hash-bound historical false-positive contention certificate verified",
    }


def _apply_exp003_launcher_evidence(record: dict[str, Any], role_name: str) -> None:
    """Make a role judgmentable only with clean or certified launcher evidence."""

    companion_paths = record.get("companion_paths") if isinstance(record.get("companion_paths"), dict) else {}
    launcher = load_json(Path(str(companion_paths.get("launcher") or "")))
    execution = load_json(Path(str(companion_paths.get("execution") or "")))
    launcher_identity_ok = bool(
        not launcher.get("_missing")
        and not launcher.get("_load_error")
        and str(launcher.get("role") or "") == role_name
        and _int_or_none(launcher.get("attempt")) == 1
        and _int_or_none(launcher.get("pid")) == _int_or_none(execution.get("pid"))
        and bool(launcher.get("process_creation_date"))
        and bool(launcher.get("process_command_line"))
    )
    clean = bool(record.get("launcher_clean") and launcher_identity_ok)
    legacy = {"status": "NOT_APPLICABLE", "reason": "not the exact legacy pre-vs-native role"}
    if clean:
        recovery = {"status": "NOT_NEEDED", "reason": "launcher completed with clean monitored evidence"}
    elif role_name == "pre_vs_native":
        recovery = {"status": "NOT_APPLICABLE", "reason": "role1 uses only the separate legacy provenance path"}
        legacy = _legacy_pre_provenance_certificate(record, role_name)
    else:
        recovery = _recovered_launcher_certificate(record, role_name)
    recovered = recovery.get("status") == "PASS"
    legacy_valid = legacy.get("status") == "PASS"
    if recovered:
        companion_paths["contention_reaudit"] = str(recovery["path"])
        record["companion_paths"] = companion_paths
    if legacy_valid:
        # This companion proves artifact provenance only.  It deliberately
        # does *not* retrofit clean launcher/eval-slot telemetry, so it cannot
        # make the role usable or turn a fully precise bundle into REVIEW_READY.
        companion_paths["legacy_provenance"] = str(legacy["path"])
        companion_paths["legacy_provenance_audit"] = str(legacy["audit_path"])
        record["companion_paths"] = companion_paths
    record["launcher_identity_ok"] = launcher_identity_ok
    record["launcher_recovery"] = recovery
    record["legacy_provenance"] = legacy
    record["legacy_inconclusive_only"] = legacy_valid
    record["launcher_evidence_ok"] = bool(clean or recovered)
    record["judgmentable"] = bool(
        record.get("base_judgmentable") and record.get("launcher_evidence_ok")
    )
    record["usable"] = bool(record.get("judgmentable") and record.get("ci_ok"))


def _legacy_pre_artifact_paths(run_dir: Path) -> dict[str, Path]:
    result = run_dir / EXP003_LEGACY_PRE_RESULT_NAME
    stem = str(result)[:-5]
    return {
        "result": result,
        "markdown": Path(stem + ".md"),
        "stdout": Path(stem + ".stdout.log"),
        "stderr": Path(stem + ".stderr.log"),
        "execution": Path(stem + ".execution.json"),
        "launcher": Path(stem + ".launcher.json"),
    }


def _legacy_pre_artifact_fingerprints(run_dir: Path) -> dict[str, dict[str, Any]]:
    paths = _legacy_pre_artifact_paths(run_dir)
    fingerprints: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"legacy pre-role artifact is missing: {name}={path}")
        fingerprints[name] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return fingerprints


def _legacy_pre_ops_evidence() -> dict[str, dict[str, Any]]:
    ledger_path = REPO_ROOT / "reports" / "v5_experiment_ledger.md"
    if not ledger_path.is_file():
        raise RuntimeError(f"legacy pre-role Ops ledger is missing: {ledger_path}")
    # Bind the append-only history by its original bytes, never a decoded and
    # re-encoded approximation.  This keeps the one-off exception safe even
    # if historical text contains a legacy encoding anomaly elsewhere.
    rows = ledger_path.read_bytes().split(b"\n")
    evidence: dict[str, dict[str, Any]] = {}
    for event_id, expected_sha in EXP003_LEGACY_PRE_OPS_ROWS.items():
        marker = f"[event_id={event_id}]".encode("ascii")
        matches = [row for row in rows if marker in row]
        if len(matches) != 1:
            raise RuntimeError(f"legacy pre-role Ops row count for {event_id} is {len(matches)}, expected exactly 1")
        row = matches[0]
        actual_sha = hashlib.sha256(row).hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(f"legacy pre-role Ops row hash mismatch for {event_id}")
        evidence[event_id] = {
            "ledger_path": str(ledger_path),
            "row_sha256": actual_sha,
            "row_utf8_display": row.decode("utf-8", errors="replace"),
        }
    return evidence


def build_exp003_pre_legacy_provenance_audit(run_dir: Path) -> dict[str, Any]:
    """Recompute one known historical role without claiming missing telemetry.

    This deliberately cannot certify eval-slot exclusion or retrofit a clean
    launcher.  It only records immutable file/protocol evidence for the single
    gate21800-vs-native role, which downstream logic caps at INCONCLUSIVE.
    """

    run_dir = Path(run_dir).resolve()
    if run_dir.name != EXP003_LEGACY_PRE_RUN_ID:
        raise RuntimeError("legacy pre-role provenance is pinned to one known EXP-003 run only")
    paths = _legacy_pre_artifact_paths(run_dir)
    fingerprints = _legacy_pre_artifact_fingerprints(run_dir)
    for name, expected in EXP003_LEGACY_PRE_ARTIFACTS.items():
        actual = fingerprints.get(name) or {}
        if actual.get("sha256") != expected["sha256"] or actual.get("bytes") != expected["bytes"]:
            raise RuntimeError(f"legacy pre-role artifact hash/size mismatch: {name}")
    result = load_json(paths["result"])
    execution = load_json(paths["execution"])
    launcher = load_json(paths["launcher"])
    stdout = load_json(paths["stdout"])
    if any(value.get("_missing") or value.get("_load_error") for value in (result, execution, launcher, stdout)):
        raise RuntimeError("legacy pre-role JSON artifact is missing or unreadable")
    anchor_rows = result.get("anchors") if isinstance(result.get("anchors"), list) else []
    anchor = anchor_rows[0] if len(anchor_rows) == 1 and isinstance(anchor_rows[0], dict) else {}
    command = execution.get("command") if isinstance(execution.get("command"), list) else []

    def option_value(flag: str) -> str | None:
        try:
            index = command.index(flag)
        except ValueError:
            return None
        return str(command[index + 1]) if index + 1 < len(command) else None

    protocol_checks = {
        "result_stdout_byte_identical": stdout == result,
        "embedded_execution_matches_companion": result.get("execution") == execution,
        "stderr_empty": paths["stderr"].stat().st_size == 0,
        "result_candidate_iteration_hands": (
            _int_or_none(pick(result, "candidate", "checkpoint", "iteration")) == EXP003_CUTOVER_ITERATION
            and _int_or_none(pick(result, "candidate", "checkpoint", "total_hands")) == EXP003_CUTOVER_HANDS
        ),
        "result_candidate_hash": str(pick(result, "candidate", "sha256") or "").lower() == EXP003_PRE_SHA256,
        "result_anchor_iteration_hands": (
            _int_or_none(pick(anchor, "anchor_checkpoint", "iteration")) == 4600
            and _int_or_none(pick(anchor, "anchor_checkpoint", "total_hands")) == EXP003_NATIVE_ANCHOR_HANDS
        ),
        "result_anchor_hash": str(anchor.get("anchor_sha256") or "").lower() == EXP003_NATIVE_SHA256,
        "pairs_seed_stack_policy": (
            _int_or_none(result.get("pairs")) == EXP003_MIRROR_PAIRS
            and _int_or_none(result.get("seed")) == EXP003_MIRROR_SEED
            and finite_float(result.get("starting_stack")) == 200.0
            and str(result.get("policy_mode") or "") == EXP003_MIRROR_POLICY_MODE
        ),
        "ood_gate": (
            anchor.get("anchor_ood_valid") is True
            and finite_float(anchor.get("anchor_ood_node_rate")) == 0.0
            and finite_float(anchor.get("anchor_ood_valid_threshold")) == EXP003_MIRROR_OOD_MAX
            and pick(result, "gate", "all_anchors_pass_ood_gate") is True
        ),
        "execution_completed_cpu_below_normal_threads": (
            str(execution.get("status") or "").upper() == "COMPLETED"
            and _int_or_none(execution.get("pid")) == 11176
            and str(pick(execution, "priority", "actual_label") or "").lower() == "belownormal"
            and _int_or_none(execution.get("torch_threads")) == 1
            and _int_or_none(execution.get("torch_interop_threads")) == 1
        ),
        "execution_command_protocol": (
            option_value("--pairs") == "25000"
            and option_value("--seed") == "20260709"
            and option_value("--starting-stack") == "200"
            and option_value("--device") == "cpu"
            and option_value("--priority") == "below-normal"
            and option_value("--torch-threads") == "1"
            and option_value("--torch-interop-threads") == "1"
            and option_value("--anchor-ood-valid-threshold") == "0.15"
        ),
        "legacy_launcher_known_identity": (
            _int_or_none(launcher.get("pid")) == 11176
            and str(launcher.get("evaluator_sha256") or "").lower() == EXP003_EVALUATOR_SHA256
            and str(launcher.get("candidate_sha256") or "").lower() == EXP003_PRE_SHA256
            and str(launcher.get("anchor_sha256") or "").lower() == EXP003_NATIVE_SHA256
            and _int_or_none(launcher.get("pairs")) == EXP003_MIRROR_PAIRS
            and _int_or_none(launcher.get("seed")) == EXP003_MIRROR_SEED
            and finite_float(launcher.get("starting_stack")) == 200.0
            and str(launcher.get("device") or "").lower() == "cpu"
            and str(launcher.get("priority") or "").lower() == "below-normal"
            and _int_or_none(launcher.get("torch_threads")) == 1
            and _int_or_none(launcher.get("torch_interop_threads")) == 1
        ),
    }
    ops_evidence = _legacy_pre_ops_evidence()
    return {
        "schema_version": EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION,
        "audit_mode": "post_hoc_read_only_recomputation_not_recovered_historical_audit",
        "claim_scope": "exp003_pre_vs_native_artifact_provenance_only_not_strength_not_eval_slot_proof",
        "run_id": EXP003_LEGACY_PRE_RUN_ID,
        "role": "pre_vs_native",
        "candidate_iteration": EXP003_CUTOVER_ITERATION,
        "candidate_hands": EXP003_CUTOVER_HANDS,
        "candidate_sha256": EXP003_PRE_SHA256,
        "anchor_iteration": 4600,
        "anchor_hands": EXP003_NATIVE_ANCHOR_HANDS,
        "anchor_sha256": EXP003_NATIVE_SHA256,
        "evaluator_sha256": EXP003_EVALUATOR_SHA256,
        "artifact_fingerprints": fingerprints,
        "protocol_checks": protocol_checks,
        "ops_timeline_evidence": ops_evidence,
        "historical_independent_audit_artifact": {
            "status": "NOT_FOUND_AT_TAKEOVER",
            "limitation": "The contemporaneous Ops row is hash-bound below, but no standalone immutable audit artifact was found.",
            "ops_event_id": "exp003_mirror_pre_native_independent_audit_20260709_1805",
        },
        "contention_telemetry": "LEGACY_UNAVAILABLE",
        "decision_capability": "INCONCLUSIVE_ONLY",
        "overall": "PASS" if all(protocol_checks.values()) else "FAIL",
    }


def _immutable_write_canonical_json(path: Path, payload: dict[str, Any]) -> str:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    expected_sha = hashlib.sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
    except FileExistsError:
        if not path.is_file() or sha256_file(path) != expected_sha:
            raise RuntimeError(f"immutable provenance artifact exists with different bytes: {path}")
    if sha256_file(path) != expected_sha:
        raise RuntimeError(f"immutable provenance artifact hash mismatch after write: {path}")
    return expected_sha


def build_exp003_pre_legacy_provenance_certificate(run_dir: Path, audit_path: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    audit_path = Path(audit_path).resolve()
    audit = load_json(audit_path)
    expected_audit = build_exp003_pre_legacy_provenance_audit(run_dir)
    if audit != expected_audit or audit.get("overall") != "PASS":
        raise RuntimeError("legacy pre-role audit does not exactly match the registered read-only recomputation")
    result_path = _legacy_pre_artifact_paths(run_dir)["result"]
    certificate_path = Path(str(result_path)[:-5] + ".legacy_provenance.json")
    return {
        "schema_version": EXP003_LEGACY_PRE_SCHEMA_VERSION,
        "state": "LEGACY_PROVENANCE_INCONCLUSIVE_ONLY_PASS",
        "role": "pre_vs_native",
        "run_id": EXP003_LEGACY_PRE_RUN_ID,
        "result_path": str(result_path),
        "candidate_iteration": EXP003_CUTOVER_ITERATION,
        "candidate_hands": EXP003_CUTOVER_HANDS,
        "candidate_sha256": EXP003_PRE_SHA256,
        "anchor_iteration": 4600,
        "anchor_hands": EXP003_NATIVE_ANCHOR_HANDS,
        "anchor_sha256": EXP003_NATIVE_SHA256,
        "evaluator_sha256": EXP003_EVALUATOR_SHA256,
        "artifact_fingerprints": expected_audit["artifact_fingerprints"],
        "post_hoc_read_only_audit": {
            "path": str(audit_path),
            "sha256": sha256_file(audit_path),
            "schema_version": EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION,
            "overall": "PASS",
        },
        "ops_timeline_evidence": expected_audit["ops_timeline_evidence"],
        "contention_telemetry": "LEGACY_UNAVAILABLE",
        "decision_capability": "INCONCLUSIVE_ONLY",
        "recovery_scope": "exact_pre_vs_native_gate21800_only_no_new_pairs_no_adopt_no_rollback",
        "generic_fallback": False,
        "canonical_companion_path": str(certificate_path),
    }


def write_exp003_pre_legacy_provenance(run_dir: Path) -> dict[str, Any]:
    """Write the one-off immutable post-hoc audit and INCONCLUSIVE-only cert."""

    run_dir = Path(run_dir).resolve()
    result_path = _legacy_pre_artifact_paths(run_dir)["result"]
    audit_path = Path(str(result_path)[:-5] + ".legacy_provenance_audit.json")
    audit = build_exp003_pre_legacy_provenance_audit(run_dir)
    if audit.get("overall") != "PASS":
        raise RuntimeError("legacy pre-role recomputation did not pass; refusing provenance certificate")
    audit_sha = _immutable_write_canonical_json(audit_path, audit)
    certificate_path = Path(str(result_path)[:-5] + ".legacy_provenance.json")
    certificate = build_exp003_pre_legacy_provenance_certificate(run_dir, audit_path)
    certificate_sha = _immutable_write_canonical_json(certificate_path, certificate)
    return {
        "audit_path": str(audit_path),
        "audit_sha256": audit_sha,
        "certificate_path": str(certificate_path),
        "certificate_sha256": certificate_sha,
    }


def _legacy_pre_provenance_certificate(record: dict[str, Any], role_name: str) -> dict[str, Any]:
    expected_run_dir = (
        REPO_ROOT
        / "models"
        / "alpha_holdem_v5_from_zero"
        / EXP003_LEGACY_PRE_RUN_ID
    ).resolve()
    expected_result_path = (expected_run_dir / EXP003_LEGACY_PRE_RESULT_NAME).resolve()
    expected_certificate_path = Path(str(expected_result_path)[:-5] + ".legacy_provenance.json").resolve()
    expected_audit_path = Path(str(expected_result_path)[:-5] + ".legacy_provenance_audit.json").resolve()
    certificate_path = expected_certificate_path
    failure = lambda reason: {"status": "FAIL", "path": str(certificate_path), "reason": reason}
    if role_name != "pre_vs_native":
        return failure("legacy provenance is not available for this role")
    try:
        record_result_path = Path(str(record.get("path") or "")).resolve()
    except OSError:
        return failure("legacy provenance role path cannot be resolved")
    if record_result_path != expected_result_path:
        return failure("legacy provenance is pinned to one exact pre-vs-native result path")
    run_dir = expected_run_dir
    certificate = load_json(certificate_path)
    if certificate.get("_missing") or certificate.get("_load_error"):
        return failure("legacy provenance certificate is missing or unreadable")
    if str(certificate.get("canonical_companion_path") or "") != str(expected_certificate_path):
        return failure("legacy provenance certificate canonical companion path is not the exact role1 path")
    try:
        audit_path = Path(str(certificate.get("post_hoc_read_only_audit", {}).get("path") or "")).resolve()
    except OSError:
        return failure("legacy provenance audit path cannot be resolved")
    if audit_path != expected_audit_path:
        return failure("legacy provenance audit path is not the exact role1 companion path")
    if not audit_path.is_file():
        return failure("legacy provenance post-hoc audit is missing")
    try:
        expected = build_exp003_pre_legacy_provenance_certificate(run_dir, audit_path)
    except Exception as exc:
        return failure(f"legacy provenance recomputation failed: {type(exc).__name__}: {exc}")
    if certificate != expected:
        return failure("legacy provenance certificate does not exactly bind the known role1 audit/evidence")
    audit = load_json(audit_path)
    if audit.get("overall") != "PASS" or sha256_file(audit_path) != str(pick(certificate, "post_hoc_read_only_audit", "sha256") or ""):
        return failure("legacy provenance audit hash or verdict no longer matches certificate")
    return {
        "status": "PASS",
        "path": str(certificate_path),
        "sha256": sha256_file(certificate_path),
        "audit_path": str(audit_path),
        "audit_sha256": sha256_file(audit_path),
        "reason": "exact role1 post-hoc provenance verified; telemetry remains legacy-unavailable and inconclusive-only",
    }


def _legacy_preflight_contract(
    roles: dict[str, Any],
    freeze: dict[str, Any] | None,
    target_hands: int,
) -> dict[str, Any] | None:
    """Expose a narrow role3-preflight exception, never a role1 override.

    This exists only after the exact legacy role1 certificate *and* an
    independently recovered, structurally valid post-vs-native result have
    failed the fixed CI precision gate.  It intentionally cannot help launch
    or rehabilitate that post result.
    """

    record = roles.get("pre_vs_native") if isinstance(roles.get("pre_vs_native"), dict) else {}
    post = roles.get("post_vs_native") if isinstance(roles.get("post_vs_native"), dict) else {}
    provenance = record.get("legacy_provenance") if isinstance(record.get("legacy_provenance"), dict) else {}
    recovery = post.get("launcher_recovery") if isinstance(post.get("launcher_recovery"), dict) else {}
    post_companions = post.get("companion_paths") if isinstance(post.get("companion_paths"), dict) else {}
    post_reaudit_path = Path(str(post_companions.get("contention_reaudit") or ""))
    if not (
        record.get("legacy_inconclusive_only") is True
        and provenance.get("status") == "PASS"
        and record.get("base_judgmentable") is True
        and record.get("launcher_evidence_ok") is False
        and record.get("judgmentable") is False
        and record.get("usable") is False
        and isinstance(freeze, dict)
        and _int_or_none(freeze.get("archive_hands")) is not None
        and _int_or_none(freeze.get("archive_hands")) >= target_hands
        and bool(freeze.get("archive_path"))
        and bool(freeze.get("archive_sha256"))
        and post.get("base_judgmentable") is True
        and post.get("launcher_evidence_ok") is True
        and post.get("judgmentable") is True
        and post.get("ci_precision_failed") is True
        and post.get("ci_ok") is False
        and recovery.get("status") == "PASS"
        and str(recovery.get("path") or "") == str(post_reaudit_path)
        and post_reaudit_path.is_file()
        and str(recovery.get("sha256") or "") == sha256_file(post_reaudit_path)
        and post.get("anchor_sha256") == EXP003_NATIVE_SHA256
        and post.get("candidate_hands") == _int_or_none(freeze.get("archive_hands"))
        and post.get("candidate_sha256") == freeze.get("archive_sha256")
        and post.get("candidate_path") == freeze.get("archive_path")
    ):
        return None
    return {
        "schema_version": "v5.exp003.pre_vs_native.legacy_preflight_contract.v1",
        "role": "pre_vs_native",
        "run_id": EXP003_LEGACY_PRE_RUN_ID,
        "result_path": str(record.get("path") or ""),
        "candidate_iteration": EXP003_CUTOVER_ITERATION,
        "candidate_hands": EXP003_CUTOVER_HANDS,
        "candidate_sha256": EXP003_PRE_SHA256,
        "anchor_iteration": 4600,
        "anchor_hands": EXP003_NATIVE_ANCHOR_HANDS,
        "anchor_sha256": EXP003_NATIVE_SHA256,
        "provenance_path": str(provenance.get("path") or ""),
        "provenance_sha256": str(provenance.get("sha256") or ""),
        "audit_path": str(provenance.get("audit_path") or ""),
        "audit_sha256": str(provenance.get("audit_sha256") or ""),
        "post_vs_native_result_path": str(post.get("path") or ""),
        "post_vs_native_candidate_iteration": _int_or_none(post.get("candidate_iteration")),
        "post_vs_native_candidate_hands": _int_or_none(post.get("candidate_hands")),
        "post_vs_native_candidate_sha256": str(post.get("candidate_sha256") or ""),
        "post_vs_native_contention_reaudit_path": str(post_reaudit_path),
        "post_vs_native_contention_reaudit_sha256": str(recovery.get("sha256") or ""),
        "required_ci_precision_failed_roles": ["post_vs_native"],
        "inconclusive_only": True,
        "requires_post_vs_native_ci_failure": True,
        "forbids_review_ready": True,
        "forbids_additional_pairs": True,
        "normal_launcher_evidence": False,
    }


def _strict_gate_iteration(value: Any) -> int | None:
    """Accept only integer-like gate identity fields, never bools or floats."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text and text.isascii() and text.isdecimal():
            return int(text)
    return None


def _gate_checkpoint_field(
    gate: dict[str, Any],
    *,
    top_level: str,
    nested: str,
) -> tuple[int | None, str | None, str | None]:
    """Read an immutable gate checkpoint field without masking malformed data.

    Older V5 gate statuses store checkpoint identity inside ``checkpoint``;
    newer statuses mirror it at top level.  A single form is accepted.  If
    both forms are present they must agree; never fall back from a malformed
    top-level field to a valid nested value.
    """

    checkpoint = gate.get("checkpoint") if isinstance(gate.get("checkpoint"), dict) else {}
    top_present = top_level in gate
    nested_present = nested in checkpoint
    top_value = _strict_gate_iteration(gate.get(top_level)) if top_present else None
    nested_value = _strict_gate_iteration(checkpoint.get(nested)) if nested_present else None
    nested_source = f"checkpoint.{nested}"
    if top_present and nested_present:
        if top_value is None or nested_value is None:
            return None, None, f"{top_level} or {nested_source} is not a strict integer"
        if top_value != nested_value:
            return None, None, f"{top_level} conflicts with {nested_source}"
        return top_value, f"{top_level}+{nested_source}", None
    if top_present:
        if top_value is None:
            return None, None, f"{top_level} is not a strict integer"
        return top_value, top_level, None
    if nested_present:
        if nested_value is None:
            return None, None, f"{nested_source} is not a strict integer"
        return nested_value, nested_source, None
    return None, None, f"{top_level} / {nested_source} is missing"


def _gate_status_identity(path: Path, gate: dict[str, Any]) -> dict[str, Any]:
    """Prove a gate status belongs to exactly the checkpoint its name claims.

    Gate files are operational evidence, so a copied or stale JSON must not
    acquire authority from its filename.  This is a logical quarantine only:
    the queue never modifies the source artifact.  The target iteration is
    mandatory; older V5 records are supported only through their nested
    checkpoint representation.
    """

    name = path.name
    prefix = "gate_"
    suffix = "_status.json"
    token = name[len(prefix):-len(suffix)] if name.startswith(prefix) and name.endswith(suffix) else ""
    filename_iteration = _strict_gate_iteration(token)
    target_iteration = _strict_gate_iteration(gate.get("target_iteration"))
    checkpoint_iteration, checkpoint_iteration_source, checkpoint_iteration_problem = _gate_checkpoint_field(
        gate,
        top_level="checkpoint_iteration",
        nested="iteration",
    )
    audit = {
        "path": str(path),
        "filename_iteration": filename_iteration,
        "target_iteration": target_iteration,
        "checkpoint_iteration": checkpoint_iteration,
        "checkpoint_iteration_source": checkpoint_iteration_source,
    }
    if checkpoint_iteration_problem is not None:
        return {
            "status": "QUARANTINED",
            **audit,
            "reason": checkpoint_iteration_problem,
        }
    if filename_iteration is None or target_iteration is None or checkpoint_iteration is None:
        return {
            "status": "QUARANTINED",
            **audit,
            "reason": "gate filename, target_iteration, and checkpoint_iteration must all be strict integers",
        }
    if filename_iteration != target_iteration or target_iteration != checkpoint_iteration:
        return {
            "status": "QUARANTINED",
            **audit,
            "reason": "gate filename, target_iteration, and checkpoint_iteration disagree",
        }
    return {"status": "PASS", **audit, "identity_schema": "FILENAME_TARGET_CHECKPOINT"}


def _eligible_exp003_gates(run_dir: Path, target_hands: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return only identity-consistent PASS gates plus read-only quarantines."""

    eligible: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("gate_*_status.json")):
        gate = load_json(path)
        if gate.get("_missing") or gate.get("_load_error"):
            quarantined.append(
                {
                    "status": "QUARANTINED",
                    "path": str(path),
                    "filename_iteration": _strict_gate_iteration(
                        path.name[len("gate_"):-len("_status.json")]
                    ),
                    "target_iteration": None,
                    "checkpoint_iteration": None,
                    "reason": "gate status JSON is unreadable",
                }
            )
            continue
        # A pending/failed gate is already ineligible and may legitimately
        # name a future target while reporting the current checkpoint.  The
        # strict three-way identity proof applies before any PASS gate can
        # participate in frozen-checkpoint selection.
        if str(gate.get("overall") or "").upper() != "PASS":
            continue
        identity = _gate_status_identity(path, gate)
        if identity["status"] != "PASS":
            quarantined.append(identity)
            continue
        hands, hands_source, hands_problem = _gate_checkpoint_field(
            gate,
            top_level="checkpoint_hands",
            nested="total_hands",
        )
        if hands_problem is not None or hands is None:
            quarantined.append(
                {
                    **identity,
                    "status": "QUARANTINED",
                    "checkpoint_hands": hands,
                    "checkpoint_hands_source": hands_source,
                    "reason": hands_problem or "checkpoint_hands is not a strict integer",
                }
            )
            continue
        if hands >= target_hands:
            eligible.append(
                {
                    "path": str(path),
                    "iteration": identity["checkpoint_iteration"],
                    "hands": hands,
                    "filename_iteration": identity["filename_iteration"],
                    "target_iteration": identity["target_iteration"],
                    "checkpoint_iteration": identity["checkpoint_iteration"],
                    "checkpoint_iteration_source": identity["checkpoint_iteration_source"],
                    "checkpoint_hands_source": hands_source,
                    "identity_schema": identity["identity_schema"],
                }
            )
    return sorted(eligible, key=lambda row: (row["iteration"], row["hands"], row["path"])), quarantined


def _first_eligible_exp003_gate(run_dir: Path, target_hands: int) -> dict[str, Any] | None:
    eligible, _quarantined = _eligible_exp003_gates(run_dir, target_hands)
    return eligible[0] if eligible else None


def _exp003_freeze_record(run_dir: Path, target_hands: int) -> dict[str, Any] | None:
    status_path = run_dir / "exp003_judgment_freeze_status.json"
    status = load_json(status_path)
    if status.get("_missing") or status.get("_load_error") or str(status.get("overall") or "").upper() != "PASS":
        return None
    gate = status.get("selected_gate") if isinstance(status.get("selected_gate"), dict) else {}
    archive = status.get("archive") if isinstance(status.get("archive"), dict) else {}
    checkpoint = archive.get("checkpoint") if isinstance(archive.get("checkpoint"), dict) else {}
    return {
        "status_path": str(status_path),
        "target_hands": _int_or_none(status.get("target_hands")),
        "gate_path": str(gate.get("path") or ""),
        "gate_iteration": _int_or_none(gate.get("iteration")),
        "gate_hands": _int_or_none(gate.get("checkpoint_hands") or gate.get("hands")),
        "archive_path": str(archive.get("path") or ""),
        "archive_sha256": str(archive.get("sha256") or "").lower(),
        "archive_iteration": _int_or_none(checkpoint.get("iteration")),
        "archive_hands": _int_or_none(checkpoint.get("total_hands")),
    }


_EXP003_LEGACY_CONTRACT_PATH_FIELDS = frozenset(
    {
        "result_path",
        "provenance_path",
        "audit_path",
        "post_vs_native_result_path",
        "post_vs_native_contention_reaudit_path",
    }
)


def _canonical_exp003_path(value: Any) -> str | None:
    """Return a filesystem-identity path for hash-bound EXP-003 evidence."""

    if not isinstance(value, str) or not value:
        return None
    try:
        path = Path(value)
        if not path.is_absolute():
            path = REPO_ROOT / path
        return str(path.resolve())
    except (OSError, ValueError):
        return None


def _canonical_exp003_artifact_hashes(value: Any) -> dict[str, dict[str, str]] | None:
    """Normalize path spelling only; preserve the exact role/path/hash set."""

    if not isinstance(value, dict):
        return None
    normalized: dict[str, dict[str, str]] = {}
    for role, role_hashes in value.items():
        if not isinstance(role, str) or not isinstance(role_hashes, dict):
            return None
        canonical_role: dict[str, str] = {}
        for raw_path, digest in role_hashes.items():
            path = _canonical_exp003_path(raw_path)
            digest_text = digest.lower() if isinstance(digest, str) else ""
            if (
                path is None
                or len(digest_text) != 64
                or any(char not in "0123456789abcdef" for char in digest_text)
                or path in canonical_role
            ):
                return None
            canonical_role[path] = digest_text
        normalized[role] = canonical_role
    return normalized


def _canonical_exp003_legacy_contract(value: Any) -> dict[str, Any] | None:
    """Compare a legacy contract by canonical paths and exact non-path pins."""

    if not isinstance(value, dict):
        return None
    normalized = dict(value)
    for field in _EXP003_LEGACY_CONTRACT_PATH_FIELDS:
        path = _canonical_exp003_path(normalized.get(field))
        if path is None:
            return None
        normalized[field] = path
    return normalized


def _latest_exp003_judgment(
    run_dir: Path,
    candidate_hands: int,
    candidate_sha256: str,
    roles: dict[str, Any],
    measurement_status: str,
    ci_precision_failed_roles: list[str],
    legacy_preflight_contract: dict[str, Any] | None,
) -> dict[str, Any] | None:
    judgments: list[tuple[str, Path, dict[str, Any]]] = []
    for pattern in ("v5_exp003_judgment*.json", "exp003_judgment*.json"):
        for path in sorted(run_dir.glob(pattern)):
            judgment = load_json(path)
            if judgment.get("_missing") or judgment.get("_load_error"):
                continue
            judged_hands = _int_or_none(
                judgment.get("candidate_checkpoint_hands")
                or pick(judgment, "candidate", "checkpoint", "total_hands")
            )
            decision = str(
                judgment.get("decision") or judgment.get("verdict") or judgment.get("overall") or ""
            ).upper()
            effects = judgment.get("effects") if isinstance(judgment.get("effects"), dict) else {}
            native_status = str(pick(effects, "native_axis", "status") or "").upper()
            direct_status = str(pick(effects, "direct_causal", "status") or "").upper()
            hard_status = str(pick(judgment, "hard_guards", "status") or "").upper()
            value_status = str(pick(judgment, "method_support", "value_loss", "status") or "").upper()
            shape_status = str(pick(judgment, "method_support", "postflop_raise_plus_allin", "status") or "").upper()
            pre = roles.get("pre_vs_native") or {}
            post = roles.get("post_vs_native") or {}
            direct = roles.get("post_vs_pre_direct") or {}
            expected_native_status = ""
            expected_direct_status = ""
            try:
                native_delta = float(post["candidate_bb100"]) - float(pre["candidate_bb100"])
                native_half = math.sqrt(
                    float(pre["candidate_ci95_bb100"]) ** 2
                    + float(post["candidate_ci95_bb100"]) ** 2
                )
                direct_point = float(direct["candidate_bb100"])
                direct_half = abs(float(direct["candidate_ci95_bb100"]))
                expected_native_status = (
                    "PASS" if native_delta - native_half > 0 else
                    "REGRESSION" if native_delta + native_half < 0 else
                    "INCONCLUSIVE"
                )
                expected_direct_status = (
                    "PASS" if direct_point - direct_half > 0 else
                    "REGRESSION" if direct_point + direct_half < 0 else
                    "INCONCLUSIVE"
                )
            except (KeyError, TypeError, ValueError):
                pass
            expected_artifact_hashes: dict[str, dict[str, str]] = {}
            for role_name, record in roles.items():
                if not isinstance(record, dict):
                    continue
                role_paths = [Path(str(record.get("path") or ""))]
                companions = record.get("companion_paths") if isinstance(record.get("companion_paths"), dict) else {}
                role_paths.extend(Path(str(value)) for value in companions.values())
                if all(path.is_file() for path in role_paths):
                    expected_artifact_hashes[role_name] = {
                        str(path): sha256_file(path) for path in role_paths
                    }
            artifact_hashes_match = (
                _canonical_exp003_artifact_hashes(judgment.get("mirror_artifact_sha256"))
                == _canonical_exp003_artifact_hashes(expected_artifact_hashes)
            )
            legacy_contract_matches = (
                legacy_preflight_contract is None
                or (
                    _canonical_exp003_legacy_contract(judgment.get("legacy_preflight_contract"))
                    == _canonical_exp003_legacy_contract(legacy_preflight_contract)
                )
            )
            decision_consistent = False
            ci_precision = (
                judgment.get("ci_precision_gate")
                if isinstance(judgment.get("ci_precision_gate"), dict)
                else {}
            )
            reported_failed_roles = ci_precision.get("failed_roles")
            if not isinstance(reported_failed_roles, list):
                reported_failed_roles = []
            if measurement_status == EXP003_CI_PRECISION_FAILED:
                # A failed registered precision gate cannot support either
                # direction of a causal decision.  Require a matching,
                # explicit inconclusive artifact rather than inferring one.
                decision_consistent = (
                    decision == "INCONCLUSIVE"
                    and str(ci_precision.get("status") or "").upper() == "FAIL"
                    and sorted(str(name) for name in reported_failed_roles)
                    == sorted(ci_precision_failed_roles)
                    and (
                        legacy_preflight_contract is None
                        or (
                            ci_precision_failed_roles == ["post_vs_native"]
                            and legacy_contract_matches
                            and judgment.get("legacy_inconclusive_roles") == ["pre_vs_native"]
                        )
                    )
                )
            elif decision == "ADOPT":
                decision_consistent = (
                    native_status == direct_status == hard_status == value_status == shape_status == "PASS"
                )
            elif decision == "ROLLBACK":
                decision_consistent = (
                    hard_status == "FAIL"
                    or "REGRESSION" in {native_status, direct_status, value_status}
                    or shape_status == "COLLAPSE"
                )
            elif decision == "INCONCLUSIVE":
                decision_consistent = (
                    hard_status == "PASS"
                    and "REGRESSION" not in {native_status, direct_status, value_status}
                    and shape_status != "COLLAPSE"
                    and not (
                        native_status == direct_status == value_status == shape_status == "PASS"
                    )
                )
            schema_ok = (
                judgment.get("schema_version") == "v5.exp003.judgment.v1"
                and judgment.get("measurement_status") == measurement_status
                and judgment.get("decision_valid") is True
                and str(judgment.get("candidate_checkpoint_sha256") or "").lower() == candidate_sha256.lower()
                and isinstance(judgment.get("mirror_artifact_sha256"), dict)
                and artifact_hashes_match
                and native_status == expected_native_status
                and direct_status == expected_direct_status
                and (
                    legacy_contract_matches
                )
            )
            if judged_hands == candidate_hands and schema_ok and decision_consistent:
                judgments.append((str(judgment.get("checked_at") or ""), path, judgment))
    if not judgments:
        return None
    judgments.sort(key=lambda item: item[0])
    _, path, judgment = judgments[-1]
    return {"path": str(path), "decision": str(judgment.get("decision") or judgment.get("verdict") or judgment.get("overall"))}


def exp003_mirror_bundle_status(run_dir: Path, target_hands: int) -> dict[str, Any]:
    """Require a causal EXP-003 mirror bundle, not a single valid measurement.

    The three roles are: pre-cutover vs native anchor, the first eligible
    post-cutover checkpoint vs the same native anchor, and that same post
    checkpoint directly vs the pre-cutover checkpoint.  A fully usable bundle
    is review-ready; a structurally valid fixed-CI precision failure is instead
    judgmentable only for an explicit INCONCLUSIVE close.  Only a separate
    judgment artifact can mark the queue DONE/blocked.
    """

    eligible_gates, quarantined_gate_statuses = _eligible_exp003_gates(run_dir, target_hands)
    first_gate = eligible_gates[0] if eligible_gates else None
    freeze = _exp003_freeze_record(run_dir, target_hands)
    if first_gate is not None:
        archive_path = Path(str((freeze or {}).get("archive_path") or ""))
        archive_actual_sha256 = sha256_file(archive_path) if archive_path.is_file() else ""
        if freeze is not None:
            freeze["archive_actual_sha256"] = archive_actual_sha256
        freeze_valid = bool(
            freeze
            and freeze["target_hands"] == target_hands
            and _same_existing_path(freeze["gate_path"], Path(first_gate["path"]))
            and freeze["gate_iteration"] == first_gate["iteration"]
            and freeze["gate_hands"] == first_gate["hands"]
            and freeze["archive_iteration"] == first_gate["iteration"]
            and freeze["archive_hands"] == first_gate["hands"]
            and bool(freeze["archive_path"])
            and bool(freeze["archive_sha256"])
            and archive_actual_sha256 == freeze["archive_sha256"]
        )
    else:
        freeze_valid = False

    records: list[dict[str, Any]] = []
    auxiliary_suffixes = (
        ".execution.json",
        ".launcher.json",
        ".contention_reaudit.json",
        ".legacy_provenance.json",
        ".legacy_provenance_audit.json",
    )
    for path in sorted(run_dir.glob("v5_mirror_eval_exp003_*.json")):
        if path.name.lower().endswith(auxiliary_suffixes):
            continue
        mirror = load_json(path)
        if mirror.get("_missing") or mirror.get("_load_error"):
            continue
        records.append(_exp003_mirror_record(path, mirror))

    if not records:
        return {
            "status": "MISSING",
            "detail": "no EXP-003 causal mirror-bundle artifacts found",
            "roles": {},
            "candidate_checkpoint_hands": None,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }

    pre_native = [
        row
        for row in records
        if row["candidate_hands"] == EXP003_CUTOVER_HANDS
        and row["anchor_hands"] == EXP003_NATIVE_ANCHOR_HANDS
    ]
    eligible_post_hands = sorted(
        {
            int(row["candidate_hands"])
            for row in records
            if row["candidate_hands"] is not None and int(row["candidate_hands"]) >= target_hands
        }
    )
    candidate_hands = first_gate["hands"] if first_gate is not None else None
    post_native = [
        row
        for row in records
        if candidate_hands is not None
        and row["candidate_hands"] == candidate_hands
        and row["anchor_hands"] == EXP003_NATIVE_ANCHOR_HANDS
    ]
    post_direct = [
        row
        for row in records
        if candidate_hands is not None
        and row["candidate_hands"] == candidate_hands
        and row["anchor_hands"] == EXP003_CUTOVER_HANDS
    ]

    role_candidates = {
        "pre_vs_native": pre_native,
        "post_vs_native": post_native,
        "post_vs_pre_direct": post_direct,
    }
    duplicate_role_artifacts = {
        name: [str(row.get("path") or "") for row in rows]
        for name, rows in role_candidates.items()
        if len(rows) > 1
    }

    def choose(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        return sorted(rows, key=lambda row: (bool(row["usable"]), row["checked_at"]))[-1]

    roles = {
        name: choose(rows)
        for name, rows in role_candidates.items()
    }
    # The fixed bundle permits exactly one canonical result per causal role.
    # Never choose a preferred duplicate (even a more usable/newer one): an
    # extra same-role artifact could conceal unregistered pairs or a later
    # measurement, and must block both ordinary and CI-only judgment paths.
    if duplicate_role_artifacts:
        return {
            "status": "REVIEW",
            "detail": (
                "duplicate canonical EXP-003 artifacts for roles: "
                + "; ".join(
                    f"{name}={','.join(paths)}"
                    for name, paths in sorted(duplicate_role_artifacts.items())
                )
            ),
            "roles": roles,
            "duplicate_role_artifacts": duplicate_role_artifacts,
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }

    # Apply strict launcher/forensic evidence to every present role before
    # deciding whether another causal role is missing.  In particular, once
    # role2 has been exactly recovered and CI-failed, the still-missing role3
    # watcher can see the narrowly scoped legacy preflight contract below.
    # Duplicate roles returned above remain fail-closed and are never exposed
    # through this path.
    for role_name, record in roles.items():
        if isinstance(record, dict):
            _apply_exp003_launcher_evidence(record, role_name)
    legacy_inconclusive_roles = [
        name for name, row in roles.items() if bool((row or {}).get("legacy_inconclusive_only"))
    ]
    ci_precision_failed_roles = [
        name
        for name, row in roles.items()
        if bool((row or {}).get("judgmentable"))
        and bool((row or {}).get("ci_precision_failed"))
    ]
    legacy_preflight_contract = _legacy_preflight_contract(
        roles,
        freeze if freeze_valid else None,
        target_hands,
    )
    missing = [name for name, row in roles.items() if row is None]
    if not freeze_valid:
        missing.append("first_eligible_pass_freeze")
    if missing:
        status = "STALE" if candidate_hands is None and records else "INCOMPLETE"
        return {
            "status": status,
            "detail": f"EXP-003 causal mirror bundle missing roles: {', '.join(missing)}",
            "roles": roles,
            "legacy_inconclusive_roles": legacy_inconclusive_roles,
            "ci_precision_failed_roles": ci_precision_failed_roles,
            "legacy_preflight_contract": legacy_preflight_contract,
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }

    role_rows = [row for row in roles.values() if isinstance(row, dict)]
    protocol_keys = {
        (row["pairs"], row["seed"], row["policy_mode"], row["starting_stack"])
        for row in role_rows
    }
    invalid_roles = [
        name
        for name, row in roles.items()
        if not bool((row or {}).get("judgmentable")) and name not in legacy_inconclusive_roles
    ]
    identity_problems: list[str] = []
    pre = roles.get("pre_vs_native") or {}
    post_native_row = roles.get("post_vs_native") or {}
    post_direct_row = roles.get("post_vs_pre_direct") or {}
    if pre.get("candidate_sha256") != EXP003_PRE_SHA256 or post_direct_row.get("anchor_sha256") != EXP003_PRE_SHA256:
        identity_problems.append("pre-cutover hash mismatch")
    if pre.get("anchor_sha256") != EXP003_NATIVE_SHA256 or post_native_row.get("anchor_sha256") != EXP003_NATIVE_SHA256:
        identity_problems.append("native-anchor hash mismatch")
    if not freeze or post_native_row.get("candidate_sha256") != freeze.get("archive_sha256"):
        identity_problems.append("post candidate hash does not match freeze")
    if post_direct_row.get("candidate_sha256") != post_native_row.get("candidate_sha256"):
        identity_problems.append("post candidate differs across roles")
    if freeze and (
        post_native_row.get("candidate_path") != freeze.get("archive_path")
        or post_direct_row.get("candidate_path") != freeze.get("archive_path")
    ):
        identity_problems.append("post candidate path is not frozen archive")
    if len(protocol_keys) != 1 or invalid_roles or identity_problems:
        problems = []
        if len(protocol_keys) != 1:
            problems.append("protocol mismatch across roles")
        if invalid_roles:
            problems.append(f"unusable roles={','.join(invalid_roles)}")
        problems.extend(identity_problems)
        return {
            "status": "REVIEW",
            "detail": "; ".join(problems),
            "roles": roles,
            "legacy_inconclusive_roles": legacy_inconclusive_roles,
            "ci_precision_failed_roles": ci_precision_failed_roles,
            "legacy_preflight_contract": legacy_preflight_contract,
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }

    # The role1 legacy certificate is intentionally weaker than normal
    # launcher proof.  It may accompany an already-failed *post* CI gate to
    # preserve the fixed window as INCONCLUSIVE, but it cannot manufacture a
    # CI_PRECISION_FAILED state or permit a REVIEW_READY/ADOPT path by itself.
    if legacy_inconclusive_roles and (
        legacy_inconclusive_roles != ["pre_vs_native"]
        or ci_precision_failed_roles != ["post_vs_native"]
        or legacy_preflight_contract is None
    ):
        return {
            "status": "REVIEW",
            "detail": (
                "legacy pre-vs-native provenance is INCONCLUSIVE-only and requires an independently "
                "recovered post-vs-native fixed-CI failure only; REVIEW_READY/ADOPT is forbidden"
            ),
            "roles": roles,
            "legacy_inconclusive_roles": legacy_inconclusive_roles,
            "ci_precision_failed_roles": ci_precision_failed_roles,
            "legacy_preflight_contract": legacy_preflight_contract,
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }

    assert candidate_hands is not None
    measurement_status = (
        EXP003_CI_PRECISION_FAILED
        if ci_precision_failed_roles
        else "REVIEW_READY"
    )
    judgment = _latest_exp003_judgment(
        run_dir,
        candidate_hands,
        str(freeze["archive_sha256"]),
        roles,
        measurement_status,
        ci_precision_failed_roles,
        legacy_preflight_contract,
    )
    if judgment is not None:
        decision = str(judgment["decision"]).upper()
        if decision == "ADOPT":
            judgment_status = "ADOPT_CLOSED"
            detail = "causal mirror bundle judged ADOPT; EXP-003 behavior window is closed"
        elif decision == "ROLLBACK":
            judgment_status = "ROLLBACK_REQUIRED"
            detail = "causal mirror bundle judged ROLLBACK; window stays open until rollback is executed and verified"
        else:
            judgment_status = "INCONCLUSIVE_BLOCKED"
            detail = "fixed-window judgment is INCONCLUSIVE; no later checkpoint substitution or new behavior window is allowed"
        return {
            "status": judgment_status,
            "detail": detail,
            "roles": roles,
            "candidate_checkpoint_hands": candidate_hands,
            "judgment": judgment,
            "measurement_status": measurement_status,
            "ci_precision_failed_roles": ci_precision_failed_roles,
            "legacy_inconclusive_roles": legacy_inconclusive_roles,
            "legacy_preflight_contract": legacy_preflight_contract,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }
    if measurement_status == EXP003_CI_PRECISION_FAILED:
        return {
            "status": EXP003_CI_PRECISION_FAILED,
            "detail": (
                "three-role causal bundle is structurally valid, but the fixed CI precision gate "
                f"failed for roles: {', '.join(ci_precision_failed_roles)}; write an explicit "
                "INCONCLUSIVE judgment and do not substitute a later checkpoint"
            ),
            "roles": roles,
            "candidate_checkpoint_hands": candidate_hands,
            "measurement_status": measurement_status,
            "ci_precision_failed_roles": ci_precision_failed_roles,
            "legacy_inconclusive_roles": legacy_inconclusive_roles,
            "legacy_preflight_contract": legacy_preflight_contract,
            "first_eligible_gate": first_gate,
            "quarantined_gate_statuses": quarantined_gate_statuses,
            "freeze": freeze,
        }
    return {
        "status": "REVIEW_READY",
        "detail": (
            f"three-role causal bundle is valid for candidate_hands={candidate_hands}; "
            "measurement validity is not an ADOPT/ROLLBACK decision"
        ),
        "roles": roles,
        "candidate_checkpoint_hands": candidate_hands,
        "measurement_status": measurement_status,
        "ci_precision_failed_roles": ci_precision_failed_roles,
        "legacy_inconclusive_roles": legacy_inconclusive_roles,
        "legacy_preflight_contract": legacy_preflight_contract,
        "first_eligible_gate": first_gate,
        "quarantined_gate_statuses": quarantined_gate_statuses,
        "freeze": freeze,
    }


def external_eval_descriptor(stage: Any, target_hands: int) -> dict[str, str]:
    stage_name = str(stage or "quick5k")
    descriptors = {
        "quick5k": {
            "key": f"slumbot_quick5k_{target_hands}",
            "noun": "official greedy-direct quick5k Slumbot screen",
            "action": (
                "Launch the official greedy-direct quick5k through the duplicate-safe cadence pipeline, then require "
                "the complete hand-level bundle before any training adjustment."
            ),
        },
        "promotion20k": {
            "key": f"slumbot_promotion20k_{target_hands}",
            "noun": "official greedy-direct promotion20k Slumbot screen",
            "action": (
                "Launch official greedy-direct promotion20k through the duplicate-safe cadence pipeline; audit the full "
                "bundle and launch formal100k only if promotion_20k_strong=true."
            ),
        },
        "formal100k": {
            "key": f"slumbot_formal100k_{target_hands}",
            "noun": "official greedy-direct formal100k Slumbot benchmark",
            "action": (
                "Launch official greedy-direct formal100k only after the strong promotion prerequisite passes, and retain "
                "the complete L5/L6-eligible evidence bundle."
            ),
        },
    }
    return descriptors.get(stage_name, descriptors["quick5k"])


def exp003_mirror_queue_instruction(mirror_state: Any) -> tuple[str, str]:
    """Keep an explicitly inconclusive fixed window from being re-measured."""

    if str(mirror_state or "") == "INCONCLUSIVE_BLOCKED":
        return (
            "EXP-003 fixed causal window is explicitly INCONCLUSIVE_BLOCKED by its hash/protocol-bound judgment",
            (
                "Do not rerun the mirror bundle, add pairs, or substitute another checkpoint. "
                "Register a new measurement design before any behavior change."
            ),
        )
    return (
        f"checkpoint hands >= {EXP003_NATIVE_MIRROR_TARGET_HANDS}",
        (
            f"At the first PASS checkpoint >= target, freeze that checkpoint and run the registered {EXP003_MIRROR_PAIRS:,}-pair "
            f"three-role causal bundle with seed {EXP003_MIRROR_SEED}: gate21800 vs native75M, candidate vs native75M, "
            "and candidate directly vs gate21800. Require identical protocol and OOD <= 0.15; then write a separate "
            "ADOPT/ROLLBACK/INCONCLUSIVE judgment artifact."
        ),
    )


def throughput_queue_policy(
    *,
    run_id: str,
    exp003_mirror_status: str | None,
    throughput_overall: Any,
    effective_hps: Any,
) -> tuple[str, str, str]:
    exp003_closed_states = {"ADOPT_CLOSED", "ROLLBACK_CLOSED"}
    if "exp003" in run_id.lower() and exp003_mirror_status not in exp003_closed_states:
        return (
            "BLOCKED",
            (
                f"EXP-003 remains the sole open behavior window (state={exp003_mirror_status}); "
                "the sweep plan is planning-only and must not be executed."
            ),
            "Do not execute a throughput sweep until EXP-003 is ADOPT_CLOSED or a required rollback is executed and verified.",
        )
    if throughput_overall == "WARN":
        return (
            "WATCH",
            f"throughput WARN; effective_hps={fmt(effective_hps)}. Prepare only for a registered controlled window.",
            "Use the inherited-config sweep plan only in a separately registered controlled window.",
        )
    return (
        "PASS",
        f"throughput={throughput_overall}; effective_hps={fmt(effective_hps)}.",
        "No throughput action is due.",
    )


def build_slumbot_loss_trend_item(
    *,
    trend_ledger: dict[str, Any],
    latest_ci_path: Path | None,
) -> dict[str, Any] | None:
    if latest_ci_path is None:
        return None

    official_loss_rows = trend_ledger.get("official_slumbot_loss_trend")
    official_loss_rows = official_loss_rows if isinstance(official_loss_rows, list) else []
    official_loss_rows = [row for row in official_loss_rows if isinstance(row, dict)]
    latest_loss = official_loss_rows[-1] if official_loss_rows else {}
    latest_loss_ci_path = resolve_artifact_path(latest_loss.get("ci_path")) if latest_loss else None
    loss_missing_parts: list[str] = []
    if not latest_loss:
        loss_missing_parts.append("official_slumbot_loss_trend")
    elif latest_loss_ci_path is None or latest_loss_ci_path != latest_ci_path:
        loss_missing_parts.append("latest_loss_trend_ci_mismatch")
    if latest_loss:
        if not latest_loss.get("loss_report_exists"):
            loss_missing_parts.append("loss_report")
        if not latest_loss.get("hand_review_exists"):
            loss_missing_parts.append("hand_review")
        if latest_loss.get("artifact_audit_overall") != "PASS":
            loss_missing_parts.append("artifact_audit_pass")

    if loss_missing_parts:
        loss_trend_status = "REVIEW"
        loss_trend_reason = (
            "Latest official Slumbot CI exists, but loss-trend evidence is incomplete/stale: "
            f"{', '.join(loss_missing_parts)}. Regenerate v5_trend_ledger.json/md from current artifacts "
            "before any training adjustment."
        )
    else:
        position = latest_loss.get("position") if isinstance(latest_loss.get("position"), dict) else {}
        terminal = latest_loss.get("terminal") if isinstance(latest_loss.get("terminal"), dict) else {}
        delta = latest_loss.get("delta_vs_previous") if isinstance(latest_loss.get("delta_vs_previous"), dict) else {}
        worst_preflop = latest_loss.get("worst_first_preflop_decisions")
        worst_preflop = worst_preflop if isinstance(worst_preflop, list) else []
        top_preflop = ", ".join(
            str(row.get("key"))
            for row in worst_preflop[:3]
            if isinstance(row, dict) and row.get("key")
        )
        loss_trend_status = "WATCH"
        loss_trend_reason = (
            f"official loss-trend rows={len(official_loss_rows)}; "
            f"latest bb100={fmt(latest_loss.get('bb_per_100'))}, "
            f"delta_vs_previous={fmt(delta.get('bb_per_100'))}; "
            f"SB/BB={fmt(position.get('sb_bb100'))}/{fmt(position.get('bb_bb100'))}; "
            f"hero_fold/showdown={fmt(terminal.get('hero_fold_bb100'))}/{fmt(terminal.get('showdown_bb100'))}; "
            f"top preflop loss buckets={top_preflop or 'n/a'}. "
            "Use this cross-benchmark loss trend before interpreting whether Slumbot performance is improving."
        )
    return item(
        priority=42,
        key="slumbot_loss_trend_latest",
        status=loss_trend_status,
        trigger="latest official Slumbot CI updates or official loss-trend evidence is missing/stale",
        action="Compare latest official Slumbot loss trend against previous official results before any training adjustment.",
        owner="v5_trend_ledger.py / v5_slumbot_loss_report.py",
        reason=loss_trend_reason,
        blocks_strength_claim=bool(loss_missing_parts),
    )


def claim_reference_from_strength(strength: dict[str, Any], latest_official: dict[str, Any]) -> dict[str, Any]:
    hands = strength.get("hands")
    bb100 = strength.get("bb_per_100")
    lower = strength.get("ci_lower")
    if (hands in {None, 0} or bb100 is None or lower is None) and latest_official:
        hands = latest_official.get("hands")
        bb100 = latest_official.get("bb_per_100")
        lower = latest_official.get("lower_bound_bb_per_100")
    return {"hands": hands, "bb_per_100": bb100, "ci_lower": lower}


def iteration_eta(
    *,
    target_iteration: int,
    live_iteration: int,
    checkpoint_iteration: int,
    iteration_seconds: float | None,
) -> str | None:
    if iteration_seconds is None or iteration_seconds <= 0:
        return None
    remaining_live = max(0, int(target_iteration) - int(live_iteration))
    if remaining_live > 0:
        remaining = remaining_live
    elif int(checkpoint_iteration) < int(target_iteration):
        remaining = 0
    else:
        remaining = 0
    return format_duration(remaining * iteration_seconds)


def item(
    *,
    priority: int,
    key: str,
    status: str,
    trigger: str,
    action: str,
    owner: str,
    reason: str,
    eta: str | None = None,
    blocks_strength_claim: bool = False,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "key": key,
        "status": status,
        "trigger": trigger,
        "action": action,
        "owner": owner,
        "reason": reason,
        "eta": eta,
        "blocks_strength_claim": blocks_strength_claim,
    }


def gate_detail(dashboard: dict[str, Any]) -> tuple[int | None, dict[str, Any] | None]:
    next_pending = pick(dashboard, "gates", "next_pending")
    if isinstance(next_pending, dict):
        return next_pending.get("target_iteration"), next_pending
    return None, None


def post_gate_needs_refresh(run_dir: Path, target_iteration: Any) -> bool:
    if target_iteration is None:
        return False
    try:
        target = int(target_iteration)
    except (TypeError, ValueError):
        return False
    review = load_json(run_dir / f"v5_post_gate_review_{target}.json")
    return bool(review.get("_missing") or review.get("overall") in POST_GATE_REFRESH_STATES)


def build_queue(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    dashboard = build_summary(run_dir, output_dir)
    evidence = load_json(run_dir / "v5_evidence_watchdog.json")
    cutover = load_json(run_dir / "v5_cutover_decision.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    throughput = load_json(run_dir / "v5_throughput_audit.json")
    l6_status = load_json(run_dir / "v5_l6_status_brief.json")
    preflop_plan_path, preflop_plan = load_intervention_plan(run_dir)
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")
    checkpoint_delta = load_json(run_dir / "v5_checkpoint_delta.json")
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    trend_ledger = load_json(run_dir / "v5_trend_ledger.json")

    latest = pick(dashboard, "training", "latest", default={}) or {}
    checkpoint = dashboard.get("checkpoint") if isinstance(dashboard.get("checkpoint"), dict) else {}
    live_iteration = int(latest.get("iteration") or checkpoint.get("iteration") or 0)
    live_hands = int(pick(dashboard, "training", "current_hands") or checkpoint.get("total_hands") or 0)
    checkpoint_iteration = int(checkpoint.get("iteration") or 0)
    checkpoint_hands = int(checkpoint.get("total_hands") or 0)
    run_id = str(checkpoint.get("run_id") or run_dir.name)
    health = pick(dashboard, "health", "overall")
    hps = pick(dashboard, "training", "recent_hands_per_second")
    iteration_seconds = finite_float(pick(throughput, "latest_window", "iteration_total_seconds_mean"))

    queue: list[dict[str, Any]] = []

    next_gate_target, next_gate = gate_detail(dashboard)
    if next_gate_target is not None:
        if checkpoint_iteration >= int(next_gate_target) and (next_gate or {}).get("overall") != "PASS":
            gate_status = "DUE"
            gate_reason = f"checkpoint {checkpoint_iteration} reached target {next_gate_target}; gate should refresh."
        elif live_iteration >= int(next_gate_target) and checkpoint_iteration < int(next_gate_target):
            gate_status = "DUE"
            gate_reason = f"live iter {live_iteration} reached target {next_gate_target}; waiting for checkpoint save."
        else:
            gate_status = "WAITING"
            remaining = max(0, int(next_gate_target) - live_iteration)
            gate_reason = f"live iter {live_iteration} < target {next_gate_target}; remaining {remaining} iterations."
        queue.append(
            item(
                priority=10,
                key=f"gate_{next_gate_target}",
                status=gate_status,
                trigger=f"iteration >= {next_gate_target} and checkpoint >= {next_gate_target}",
                action="Let gate watcher validate lineage, env/action-space, health, and checkpoint freshness.",
                owner="v5_gate_sequence_watch.py",
                reason=gate_reason,
                eta=iteration_eta(
                    target_iteration=int(next_gate_target),
                    live_iteration=live_iteration,
                    checkpoint_iteration=checkpoint_iteration,
                    iteration_seconds=iteration_seconds,
                ),
                blocks_strength_claim=True,
            )
        )

    internal_watcher = pick(dashboard, "watchers", "internal_strength", default={}) or {}
    internal_target = internal_watcher.get("next_target")
    if internal_target is None:
        internal_target = pick(cadence, "internal_probe", "next_due")
    if internal_target is None:
        internal_target = pick(cadence, "internal", "next_internal_probe_target")
    if internal_target is None:
        evidence_internal_target = pick(evidence, "cadence", "internal_latest_target")
        evidence_internal_overall = pick(evidence, "cadence", "internal_latest_overall")
        if evidence_internal_target is not None and evidence_internal_overall != "PASS":
            internal_target = evidence_internal_target
    internal_target_int: int | None = None
    if internal_target is not None:
        internal_target_int = int(internal_target)
        completed_internal = {
            int(target)
            for target in (internal_watcher.get("completed") or [])
            if isinstance(target, int)
        }
        if checkpoint_iteration >= internal_target_int:
            if internal_target_int in completed_internal:
                internal_status = "PASS"
                internal_reason = f"internal probe target {internal_target_int} already completed."
            else:
                internal_status = "DUE"
                internal_reason = f"checkpoint {checkpoint_iteration} is ready for internal probe target {internal_target_int}."
        else:
            internal_status = "WAITING"
            internal_reason = f"checkpoint {checkpoint_iteration} < target {internal_target_int}."
        queue.append(
            item(
                priority=20,
                key=f"internal_probe_{internal_target_int}",
                status=internal_status,
                trigger=f"checkpoint iteration >= {internal_target_int}",
                action="Run/allow internal strength probe and compare against fixed opponent pool.",
                owner="v5_internal_strength_watch.py",
                reason=internal_reason,
                eta=iteration_eta(
                    target_iteration=internal_target_int,
                    live_iteration=live_iteration,
                    checkpoint_iteration=checkpoint_iteration,
                    iteration_seconds=iteration_seconds,
                ),
                blocks_strength_claim=False,
            )
        )

    latest_internal = l6_status.get("internal_strength") if isinstance(l6_status.get("internal_strength"), dict) else {}
    latest_internal_iteration = latest_internal.get("latest_iteration")
    latest_internal_verdict = latest_internal.get("latest_verdict")
    if latest_internal_iteration is not None and latest_internal_verdict:
        latest_internal_delta = latest_internal.get("latest_delta_mean_bb100")
        latest_internal_lower = latest_internal.get("latest_delta_lower_bb100")
        if latest_internal_verdict == "REGRESSION_RISK_INTERNAL":
            regression_status = "WATCH"
            regression_key = f"internal_regression_review_{latest_internal_iteration}"
            regression_reason = (
                f"latest internal probe verdict={latest_internal_verdict}; "
                f"delta mean/lower bb100={fmt(latest_internal_delta)} / {fmt(latest_internal_lower)}. "
                "Carry this into intervention review, but do not restart from internal evidence alone."
            )
        elif latest_internal_verdict == "MIXED_INTERNAL":
            regression_status = "WATCH"
            regression_key = f"internal_mixed_review_{latest_internal_iteration}"
            regression_reason = (
                f"latest internal probe verdict={latest_internal_verdict}; "
                f"delta mean/lower bb100={fmt(latest_internal_delta)} / {fmt(latest_internal_lower)}. "
                "Use as local direction evidence only."
            )
        else:
            regression_status = "PASS"
            regression_key = f"internal_strength_review_{latest_internal_iteration}"
            regression_reason = (
                f"latest internal probe verdict={latest_internal_verdict}; "
                f"delta mean/lower bb100={fmt(latest_internal_delta)} / {fmt(latest_internal_lower)}."
            )
        queue.append(
            item(
                priority=21,
                key=regression_key,
                status=regression_status,
                trigger="latest internal probe verdict changes or repeats regression risk",
                action="Review internal fixed-opponent direction together with preflop probes and Slumbot hand-loss evidence before any training intervention.",
                owner="v5_l6_status_brief.py / v5_post_gate_review.py",
                reason=regression_reason,
                blocks_strength_claim=False,
            )
        )

    checkpoint_delta_overall = checkpoint_delta.get("overall")
    checkpoint_delta_recommendation = checkpoint_delta.get("recommendation")
    preflop_probe_overall = preflop_probe.get("overall")
    preflop_checkpoint_iteration = preflop_probe.get("checkpoint_iteration")
    preflop_warning_count = preflop_probe.get("warning_count")
    if (
        checkpoint_delta_overall == "LOCAL_GUARDRAILS_REGRESSED"
        or preflop_probe_overall in {"WARN", "FAIL"}
    ):
        probe_delta = checkpoint_delta.get("probe_delta") if isinstance(checkpoint_delta.get("probe_delta"), dict) else {}
        preflop_key_iteration = preflop_checkpoint_iteration or checkpoint_iteration
        if preflop_probe_overall == "FAIL":
            preflop_status = "REVIEW"
        else:
            preflop_status = "WATCH"
        preflop_reason = (
            f"preflop probe={preflop_probe_overall}; warning_count={fmt(preflop_warning_count)}; "
            f"checkpoint_delta={checkpoint_delta_overall}; "
            f"warning_delta={fmt(probe_delta.get('warning_count'))}; "
            f"mean_call_delta={fmt(probe_delta.get('mean_call'))}; "
            f"mean_fold_delta={fmt(probe_delta.get('mean_fold'))}; "
            f"mean_raise_delta={fmt(probe_delta.get('mean_raise'))}. "
            f"{checkpoint_delta_recommendation or 'Review local guardrail shape before any intervention.'}"
        )
        queue.append(
            item(
                priority=21,
                key=f"preflop_guardrail_review_{preflop_key_iteration}",
                status=preflop_status,
                trigger="latest preflop probe warning/failure or checkpoint-delta regression",
                action="Review fold/call/raise shape with internal probe and Slumbot hand-loss evidence before any cutover, promotion, or training intervention.",
                owner="v5_preflop_policy_probe.py / v5_checkpoint_delta.py",
                reason=preflop_reason,
                blocks_strength_claim=False,
            )
        )

    latest_pass_target = pick(dashboard, "gates", "latest_pass", "target_iteration")
    post_gate_candidates = []
    if post_gate_needs_refresh(run_dir, latest_pass_target):
        post_gate_candidates.append(int(latest_pass_target))
    post_gate_candidates.extend(
        int(target)
        for target in (next_gate_target, internal_target_int)
        if target is not None
    )
    post_gate_target = min(post_gate_candidates) if post_gate_candidates else None
    if post_gate_target is not None:
        post_gate_target_int = int(post_gate_target)
        post_gate_review_path = run_dir / f"v5_post_gate_review_{post_gate_target_int}.json"
        post_gate_review = load_json(post_gate_review_path)
        post_gate_overall = post_gate_review.get("overall")
        post_gate_recommendation = post_gate_review.get("recommendation")
        post_gate_blockers = post_gate_review.get("blockers") if isinstance(post_gate_review.get("blockers"), list) else []
        post_gate_internal = post_gate_review.get("internal_probe") if isinstance(post_gate_review.get("internal_probe"), dict) else {}
        post_gate_internal_state = post_gate_internal.get("state")
        post_gate_internal_scheduled = post_gate_internal.get("scheduled")
        internal_not_scheduled = (
            post_gate_internal_state == "NOT_SCHEDULED"
            or post_gate_internal_scheduled is False
            or (
                post_gate_review.get("_missing")
                and next_gate_target == post_gate_target_int
                and internal_target_int is not None
                and internal_target_int != post_gate_target_int
            )
        )
        if internal_not_scheduled:
            post_gate_trigger = (
                f"gate evidence available for iteration {post_gate_target_int}; "
                "no internal probe scheduled for this target"
            )
        else:
            post_gate_trigger = f"gate and internal probe evidence available for iteration {post_gate_target_int}"
        if post_gate_review.get("_missing"):
            post_gate_status = "WAITING"
            post_gate_reason = "post-gate review artifact is not written yet; dashboard watcher should refresh it."
        elif post_gate_overall == "PENDING_EVIDENCE":
            post_gate_status = "WAITING"
            post_gate_reason = post_gate_recommendation or "post-gate review is waiting on gate/internal evidence."
        elif post_gate_overall == "DUE_EVIDENCE_REFRESH":
            post_gate_status = "DUE"
            post_gate_reason = post_gate_recommendation or "post-gate evidence is ready for watcher refresh."
        elif post_gate_overall == "QUARANTINED_INTERNAL_PROBE_IDENTITY":
            post_gate_status = "REVIEW"
            post_gate_reason = (
                post_gate_recommendation
                or "target-named internal probe has an embedded checkpoint mismatch and is local-only."
            )
        elif post_gate_overall == "QUARANTINED_GATE_IDENTITY":
            post_gate_status = "REVIEW"
            post_gate_reason = (
                post_gate_recommendation
                or "raw PASS gate has a filename/target/checkpoint identity mismatch and is local-only."
            )
        elif post_gate_overall in {"REVIEW_REQUIRED_NO_AUTO_RESTART", "FORMAL_STRENGTH_REVIEW_REQUIRED"}:
            post_gate_status = "REVIEW"
            post_gate_reason = post_gate_recommendation or f"post-gate review overall={post_gate_overall}."
        elif post_gate_overall:
            post_gate_status = "PASS"
            post_gate_reason = post_gate_recommendation or f"post-gate review overall={post_gate_overall}."
        else:
            post_gate_status = "WATCH"
            post_gate_reason = f"post-gate review is unreadable or incomplete at {post_gate_review_path}."
        queue.append(
            item(
                priority=22,
                key=f"post_gate_review_{post_gate_target_int}",
                status=post_gate_status,
                trigger=post_gate_trigger,
                action="Review consolidated post-gate evidence before restart, cutover, checkpoint promotion, or strength claims.",
                owner="v5_post_gate_review.py / v5_dashboard_watch.py",
                reason=post_gate_reason,
                eta=iteration_eta(
                    target_iteration=post_gate_target_int,
                    live_iteration=live_iteration,
                    checkpoint_iteration=checkpoint_iteration,
                    iteration_seconds=iteration_seconds,
                ),
                blocks_strength_claim=bool(
                    post_gate_review.get("_missing")
                    or post_gate_overall
                    in {
                        "PENDING_EVIDENCE",
                        "DUE_EVIDENCE_REFRESH",
                        "QUARANTINED_INTERNAL_PROBE_IDENTITY",
                        "QUARANTINED_GATE_IDENTITY",
                    }
                    or any(blocker.get("name") == "formal_slumbot_claim" for blocker in post_gate_blockers)
                ),
            )
        )

    health_diag_overall = health_diag.get("overall")
    health_diag_metrics = health_diag.get("metrics") if isinstance(health_diag.get("metrics"), dict) else {}
    if health_diag_overall and not health_diag.get("_missing"):
        if health_diag_overall == "FAIL_COLLAPSE_RISK":
            health_diag_status = "REVIEW"
            health_diag_reason = "rolling health diagnosis indicates collapse risk."
        elif health_diag_overall == "PREFLOP_ALLIN_SUSTAINED_WARN":
            health_diag_status = "WATCH"
            health_diag_reason = (
                f"preflop all-in sustained high: mean={fmt(health_diag_metrics.get('preflop_allin_mean'))}, "
                f"latest={fmt(health_diag_metrics.get('preflop_allin_latest'))}, "
                f"warn_frac={fmt(health_diag_metrics.get('preflop_allin_warn_fraction'))}."
            )
        elif health_diag_overall in {"HEALTH_WARN_TRANSIENT_OR_LOCAL", "WATCH"}:
            health_diag_status = "WATCH"
            health_diag_reason = f"health diagnosis={health_diag_overall}; monitor until window clears."
        else:
            health_diag_status = "PASS"
            health_diag_reason = f"health diagnosis={health_diag_overall}."
        queue.append(
            item(
                priority=25,
                key="health_warning_diagnosis",
                status=health_diag_status,
                trigger="rolling health window detects sustained warning or collapse risk",
                action="Carry sustained warnings into the current intervention review; do not restart before the current gate unless collapse risk appears.",
                owner="v5_health_warning_diagnosis.py",
                reason=health_diag_reason,
                blocks_strength_claim=False,
            )
        )

    cutover_target = cutover.get("target_iteration") or preflop_plan.get("target_iteration")
    if cutover_target is not None:
        cutover_target_int = int(cutover_target)
        cutover_decision = cutover.get("decision")
        intervention_overall = cutover.get("intervention_overall") or preflop_plan.get("overall")
        if cutover_decision == "HOLD_NO_CUTOVER":
            cutover_status = "PASS"
            cutover_reason = (
                f"cutover decision={cutover_decision}; intervention={intervention_overall}; "
                "no restart/cutover is queued."
            )
        elif checkpoint_iteration >= cutover_target_int:
            cutover_status = "REVIEW"
            cutover_reason = f"checkpoint {checkpoint_iteration} reached cutover target {cutover_target_int}; review probes before changing params."
        else:
            cutover_status = "WAITING"
            cutover_reason = f"cutover target {cutover_target_int} not reached by checkpoint {checkpoint_iteration}."
        queue.append(
            item(
                priority=30,
                key=f"preflop_intervention_review_{cutover_target_int}",
                status=cutover_status,
                trigger=f"checkpoint iteration >= {cutover_target_int}",
                action="Review preflop guardrail, internal probe, and dry-run command before any restart.",
                owner="v5_preflop_intervention_plan.py",
                reason=cutover_reason,
                eta=iteration_eta(
                    target_iteration=cutover_target_int,
                    live_iteration=live_iteration,
                    checkpoint_iteration=checkpoint_iteration,
                    iteration_seconds=iteration_seconds,
                ),
                blocks_strength_claim=False,
            )
        )

    active_selector = pick(evidence, "cadence", "active_selector_pair_diagnostic", default={}) or {}
    active_selector_token = active_selector.get("token")
    if active_selector_token:
        active_selector_state = active_selector.get("state")
        active_selector_min_hands = active_selector.get("min_training_hands")
        active_selector_checkpoint_hands = active_selector.get("checkpoint_hands")
        active_selector_readiness = active_selector.get("readiness_by_policy")
        active_selector_planned = active_selector.get("planned_hands_per_policy")
        if active_selector_state == "RUNNING":
            active_selector_status = "WATCH"
            active_selector_reason = (
                f"selector pair `{active_selector_token}` is running; planned_hands_per_policy="
                f"{active_selector_planned}."
            )
        elif active_selector_state == "READY":
            active_selector_status = "DUE"
            active_selector_reason = (
                f"selector pair `{active_selector_token}` is ready to freeze/run; readiness="
                f"{active_selector_readiness}."
            )
        elif active_selector_state == "FAIL":
            active_selector_status = "REVIEW"
            active_selector_reason = f"selector pair `{active_selector_token}` failed; inspect watcher status/log."
        elif active_selector_state == "PASS":
            active_selector_status = "DONE"
            active_selector_reason = f"selector pair `{active_selector_token}` completed."
        elif (
            active_selector_min_hands is not None
            and checkpoint_hands >= int(active_selector_min_hands)
        ):
            active_selector_status = "DUE"
            active_selector_reason = (
                f"checkpoint_hands={checkpoint_hands} reached min_hands={active_selector_min_hands}; "
                "watcher should freeze and run."
            )
        else:
            active_selector_status = "WAITING"
            active_selector_reason = (
                f"state={active_selector_state}; checkpoint_hands={active_selector_checkpoint_hands}; "
                f"min_hands={active_selector_min_hands}; readiness={active_selector_readiness}."
            )
        queue.append(
            item(
                priority=35,
                key=f"selector_pair_{active_selector_token}",
                status=active_selector_status,
                trigger=f"checkpoint hands >= {active_selector_min_hands}",
                action="Let the selector-pair watcher run diagnostic-only greedy/callguard Slumbot hand-log comparison, then review loss and hand artifacts before any training change.",
                owner="v5_selector_pair_watch.py",
                reason=active_selector_reason,
                blocks_strength_claim=False,
            )
        )

    next_external = cadence.get("next_external_eval") if isinstance(cadence.get("next_external_eval"), dict) else {}
    external_queue_key: str | None = None
    ext_target = next_external.get("target_hands")
    if ext_target is not None:
        ext_target_int = int(ext_target)
        ext_state = next_external.get("state")
        ext_descriptor = external_eval_descriptor(next_external.get("stage"), ext_target_int)
        external_queue_key = ext_descriptor["key"]
        if ext_state == "DUE":
            ext_status = "DUE"
            ext_reason = f"checkpoint hands {checkpoint_hands} reached {ext_target_int}; {ext_descriptor['noun']} is due."
        elif ext_state == "DONE":
            ext_status = "DONE"
            ext_reason = f"{ext_descriptor['noun']} for {ext_target_int} already has CI evidence."
        else:
            ext_status = "WAITING"
            ext_reason = f"checkpoint hands {checkpoint_hands} < {ext_target_int}; live hands {live_hands}."
        queue.append(
            item(
                priority=40,
                key=ext_descriptor["key"],
                status=ext_status,
                trigger=f"checkpoint hands >= {ext_target_int}",
                action=ext_descriptor["action"],
                owner="v5_eval_cadence_watch.py / v5_slumbot_benchmark_watch.py",
                reason=ext_reason,
                eta=next_external.get("eta_duration_live"),
                blocks_strength_claim=True,
            )
        )

    latest_official = trend_ledger.get("latest_official") if isinstance(trend_ledger.get("latest_official"), dict) else {}
    latest_ci_path = resolve_artifact_path(latest_official.get("path"))
    latest_hand_review_path = sibling_artifact_from_ci(latest_ci_path, "_hand_review.json")
    latest_loss_report_path = sibling_artifact_from_ci(latest_ci_path, "_loss_report.json")
    latest_artifact_audit_path = sibling_artifact_from_ci(latest_ci_path, "_artifact_audit.json")
    if latest_ci_path is not None:
        hand_review = load_json(latest_hand_review_path) if latest_hand_review_path is not None else {"_missing": True}
        loss_report = load_json(latest_loss_report_path) if latest_loss_report_path is not None else {"_missing": True}
        artifact_audit = load_json(latest_artifact_audit_path) if latest_artifact_audit_path is not None else {"_missing": True}
        missing_parts = []
        if hand_review.get("_missing") or hand_review.get("_load_error"):
            missing_parts.append("hand_review")
        if loss_report.get("_missing") or loss_report.get("_load_error"):
            missing_parts.append("loss_report")
        if artifact_audit.get("_missing") or artifact_audit.get("_load_error"):
            missing_parts.append("artifact_audit")
        if missing_parts:
            latest_review_status = "REVIEW"
            latest_review_reason = (
                f"latest official Slumbot CI exists but missing/unreadable artifacts: {', '.join(missing_parts)}; "
                f"ci={latest_ci_path}."
            )
        else:
            latest_review_status = "WATCH"
            latest_review_reason = (
                f"latest official Slumbot: hands={latest_official.get('hands')}, "
                f"bb100={fmt(latest_official.get('bb_per_100'))}, "
                f"lower={fmt(latest_official.get('lower_bound_bb_per_100'))}; "
                f"hand_review={hand_review.get('overall')}, "
                f"evidence_class={hand_review.get('evidence_class')}, "
                f"training_adjustment={hand_review.get('training_adjustment')}; "
                f"artifact_audit={artifact_audit.get('overall')}. "
                "Use this hand review/loss report as required evidence before tuning; quick screens remain noisy."
            )
        queue.append(
            item(
                priority=41,
                key="slumbot_hand_review_latest",
                status=latest_review_status,
                trigger="latest official Slumbot CI updates or required hand-review artifacts are missing",
                action="Read the latest official Slumbot hand review and loss report before any training adjustment; never tune from bb/100 alone.",
                owner="v5_trend_ledger.py / v5_slumbot_hand_review.py",
                reason=latest_review_reason,
                blocks_strength_claim=bool(missing_parts),
            )
        )

    loss_trend_item = build_slumbot_loss_trend_item(trend_ledger=trend_ledger, latest_ci_path=latest_ci_path)
    if loss_trend_item is not None:
        queue.append(loss_trend_item)

    exp003_mirror_state: str | None = None
    if "exp003" in run_id:
        mirror_status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
        exp003_mirror_state = str(mirror_status.get("status") or "")
        remaining_checkpoint_hands = max(0, EXP003_NATIVE_MIRROR_TARGET_HANDS - checkpoint_hands)
        if mirror_status.get("status") in {"ADOPT_CLOSED", "ROLLBACK_CLOSED"}:
            mirror_queue_status = "DONE"
            mirror_reason = str(mirror_status.get("detail"))
        elif mirror_status.get("status") == "ROLLBACK_REQUIRED":
            mirror_queue_status = "DUE"
            mirror_reason = str(mirror_status.get("detail"))
        elif mirror_status.get("status") == "INCONCLUSIVE_BLOCKED":
            mirror_queue_status = "BLOCKED"
            mirror_reason = str(mirror_status.get("detail"))
        elif checkpoint_hands >= EXP003_NATIVE_MIRROR_TARGET_HANDS:
            mirror_queue_status = (
                "DUE"
                if mirror_status.get("status") in {"MISSING", "STALE", "INCOMPLETE"}
                else "REVIEW"
            )
            mirror_reason = (
                f"checkpoint_hands={checkpoint_hands} reached target {EXP003_NATIVE_MIRROR_TARGET_HANDS}; "
                f"{mirror_status.get('detail')}."
            )
        else:
            mirror_queue_status = "WAITING"
            mirror_reason = (
                f"checkpoint_hands={checkpoint_hands} < target {EXP003_NATIVE_MIRROR_TARGET_HANDS}; "
                f"remaining_checkpoint_hands={remaining_checkpoint_hands}; {mirror_status.get('detail')}."
            )
        mirror_eta = None
        hps_value = finite_float(pick(throughput, "latest_window", "effective_hps_mean"))
        if hps_value is None or hps_value <= 0:
            hps_value = finite_float(throughput.get("effective_hps_latest"))
        if hps_value and hps_value > 0 and remaining_checkpoint_hands > 0:
            mirror_eta = format_duration(remaining_checkpoint_hands / hps_value)
        mirror_trigger, mirror_action = exp003_mirror_queue_instruction(mirror_status.get("status"))
        queue.append(
            item(
                priority=45,
                key="exp003_native_anchor_mirror_408064575",
                status=mirror_queue_status,
                trigger=mirror_trigger,
                action=mirror_action,
                owner="v5_mirror_eval.py / operator",
                reason=mirror_reason,
                eta=mirror_eta,
                blocks_strength_claim=False,
            )
        )

    next_promotion = cadence.get("next_promotion_eval") if isinstance(cadence.get("next_promotion_eval"), dict) else {}
    promotion_target = next_promotion.get("target_hands")
    if promotion_target is not None:
        promotion_target_int = int(promotion_target)
        promotion_key = f"slumbot_promotion20k_{promotion_target_int}"
        promotion_state = next_promotion.get("state")
        promotion_status = "DUE" if promotion_state == "DUE" else "WAITING"
        if promotion_state == "DONE":
            promotion_status = "DONE"
        if promotion_key != external_queue_key:
            queue.append(
                item(
                    priority=50,
                    key=promotion_key,
                    status=promotion_status,
                    trigger=f"checkpoint hands >= {promotion_target_int}",
                    action="Run promotion20k only after checkpoint eligibility, then review hand JSONL, loss report, artifact audit, and hand review; this still cannot prove L5/L6 alone.",
                    owner="slumbot_promotion20k_launch watcher",
                    reason=f"state={promotion_state}; checkpoint_hands={checkpoint_hands}.",
                    eta=next_promotion.get("eta_duration_live"),
                    blocks_strength_claim=True,
                )
            )

    next_formal = cadence.get("next_formal_eval") if isinstance(cadence.get("next_formal_eval"), dict) else {}
    formal_target = next_formal.get("target_hands")
    if formal_target is not None:
        formal_target_int = int(formal_target)
        formal_state = next_formal.get("state")
        formal_prereq = latest_promotion20k_prerequisite(output_dir, run_id)
        formal_status = "DUE" if formal_state == "DUE" else "WAITING"
        if formal_state == "DONE":
            formal_status = "DONE"
        elif formal_prereq.get("status") != "PASS":
            formal_status = "BLOCKED"
        queue.append(
            item(
                priority=60,
                key=f"slumbot_formal100k_{formal_target_int}",
                status=formal_status,
                trigger=f"promotion20k strong gate PASS and checkpoint hands >= {formal_target_int}",
                action="Run formal100k Slumbot benchmark, require complete hand logs/loss report/artifact audit/hand review, then apply the 100k+ CI rule; only this tier can prove L5/L6.",
                owner="slumbot_formal100k_launch watcher",
                reason=(
                    f"state={formal_state}; checkpoint_hands={checkpoint_hands}; "
                    f"promotion20k_prerequisite={formal_prereq.get('status')}: {formal_prereq.get('detail')}."
                ),
                eta=next_formal.get("eta_duration_live"),
                blocks_strength_claim=True,
            )
        )

    throughput_overall = pick(throughput, "classification", "overall")
    effective_hps = pick(throughput, "latest_window", "effective_hps_mean")
    speed_status, speed_reason, speed_action = throughput_queue_policy(
        run_id=run_id,
        exp003_mirror_status=exp003_mirror_state,
        throughput_overall=throughput_overall,
        effective_hps=effective_hps,
    )
    queue.append(
        item(
            priority=70,
            key="throughput_optimization",
            status=speed_status,
            trigger="after the current method experiment closes and a separate speed window is registered",
            action=speed_action,
            owner="v5_throughput_sweep_plan.py",
            reason=speed_reason,
            blocks_strength_claim=False,
        )
    )

    strength = evidence.get("slumbot_strength") if isinstance(evidence.get("slumbot_strength"), dict) else {}
    can_l5 = bool(strength.get("can_claim_l5"))
    can_l6 = bool(strength.get("can_claim_l6"))
    claim_reference = claim_reference_from_strength(strength, latest_official)
    if can_l6:
        claim_status = "L6_READY"
        claim_reason = "formal Slumbot evidence meets L6 rule."
    elif can_l5:
        claim_status = "L5_READY"
        claim_reason = "formal Slumbot evidence meets L5 rule."
    else:
        claim_status = "BLOCKED"
        claim_reason = (
            f"latest Slumbot: hands={claim_reference.get('hands')}, "
            f"bb100={fmt(claim_reference.get('bb_per_100'))}, "
            f"lower={fmt(claim_reference.get('ci_lower'))}; formal rule not met."
        )
    queue.append(
        item(
            priority=80,
            key="strength_claim_gate",
            status=claim_status,
            trigger="100k+ Slumbot hands, bb/100 > 0, CI lower > 0; L6 near +11.1 bb/100",
            action="Do not claim stronger-than-V4/L5/L6 until formal Slumbot evidence satisfies the rule.",
            owner="v5_evidence_watchdog.py / v5_baseline_gap.py",
            reason=claim_reason,
            blocks_strength_claim=not (can_l5 or can_l6),
        )
    )

    queue.sort(key=lambda entry: int(entry["priority"]))
    due = [entry for entry in queue if entry["status"] in {"DUE", "REVIEW", "L5_READY", "L6_READY"}]
    watch = [entry for entry in queue if entry["status"] == "WATCH"]
    health_watch = [entry for entry in watch if entry["key"] == "health_warning_diagnosis"]
    blocked = [entry for entry in queue if entry["status"] == "BLOCKED"]
    waiting = [entry for entry in queue if entry["status"] == "WAITING"]

    if health not in {"PASS", "WARN"}:
        overall = "HEALTH_ATTENTION"
        recommendation = "Inspect health before evidence or speed decisions."
    elif due:
        overall = "ACTION_READY"
        recommendation = f"Handle `{due[0]['key']}` first."
    elif health == "WARN" or health_watch:
        overall = "WAITING_WITH_HEALTH_WARN"
        if waiting:
            recommendation = f"Wait for `{waiting[0]['key']}` while tracking `{health_watch[0]['key'] if health_watch else 'health'}`."
        else:
            recommendation = f"Track `{health_watch[0]['key']}`." if health_watch else "Track health warnings."
    elif blocked and not waiting:
        overall = "BLOCKED_ON_FORMAL_EVIDENCE"
        recommendation = "No operational action is due; formal strength claim remains blocked."
    else:
        overall = "WAITING_FOR_NEXT_TRIGGER"
        recommendation = f"Wait for `{waiting[0]['key']}`." if waiting else "No queued action."

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "overall": overall,
        "recommendation": recommendation,
        "training": {
            "health": health,
            "live_iteration": live_iteration,
            "checkpoint_iteration": checkpoint_iteration,
            "live_hands": live_hands,
            "checkpoint_hands": checkpoint_hands,
            "recent_hps": hps,
            "iteration_seconds_mean": iteration_seconds,
        },
        "queue": queue,
        "due_count": len(due),
        "waiting_count": len(waiting),
        "blocked_count": len(blocked),
        "source_artifacts": {
            "preflop_plan": str(preflop_plan_path),
            "cutover": str(run_dir / "v5_cutover_decision.json"),
            "evidence": str(run_dir / "v5_evidence_watchdog.json"),
            "cadence": str(run_dir / "v5_eval_cadence.json"),
            "l6_status_brief": str(run_dir / "v5_l6_status_brief.json"),
            "checkpoint_delta": str(run_dir / "v5_checkpoint_delta.json"),
            "preflop_probe": str(run_dir / "v5_preflop_probe_latest.json"),
            "trend_ledger": str(run_dir / "v5_trend_ledger.json"),
            "post_gate_review": str(run_dir / f"v5_post_gate_review_{post_gate_target}.json") if post_gate_target is not None else None,
        },
        "claim_rule": "Only formal Slumbot CI can prove strength: 100k+ hands, bb/100 > 0, CI lower > 0; L6 also needs near +11.1 bb/100.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    training = summary["training"]
    lines = [
        "# V5 Next Action Queue",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Training health: `{training['health']}`",
        f"- Live/checkpoint iteration: `{training['live_iteration']}` / `{training['checkpoint_iteration']}`",
        f"- Live/checkpoint hands: `{training['live_hands']}` / `{training['checkpoint_hands']}`",
        f"- Recent h/s: `{fmt(training['recent_hps'])}`",
        f"- Mean seconds/iteration: `{fmt(training.get('iteration_seconds_mean'))}`",
        "",
        "Queue:",
        "",
    ]
    for entry in summary["queue"]:
        eta = f"; ETA `{entry['eta']}`" if entry.get("eta") else ""
        claim = "; blocks strength claim" if entry.get("blocks_strength_claim") else ""
        lines.append(f"- {entry['status']}: `{entry['key']}`{eta}{claim}")
        lines.append(f"  - Trigger: {entry['trigger']}")
        lines.append(f"  - Action: {entry['action']}")
        lines.append(f"  - Owner: `{entry['owner']}`")
        lines.append(f"  - Reason: {entry['reason']}")
    lines.extend(["", "Claim rule:", "", f"- {summary['claim_rule']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only V5 next-action queue.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_queue(Path(args.run_dir), Path(args.output_dir))
    print(f"overall={summary['overall']}")
    print(f"recommendation={summary['recommendation']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
