#!/usr/bin/env python3
"""Build a read-only next-action queue for the V5 L6 run.

This turns scattered watcher state into an ordered list of trigger-driven
actions. It deliberately separates operational actions from strength claims.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from v5_run_dashboard import build_summary, format_duration

POST_GATE_REFRESH_STATES = {"PENDING_EVIDENCE", "DUE_EVIDENCE_REFRESH"}
EXP003_NATIVE_MIRROR_TARGET_HANDS = 408_064_575
EXP003_CUTOVER_HANDS = 358_064_575
EXP003_NATIVE_ANCHOR_HANDS = 75_479_020
EXP003_MIRROR_PAIRS = 25_000
EXP003_MIRROR_SEED = 20_260_709
EXP003_MIRROR_POLICY_MODE = "greedy_argmax_both_sides"
EXP003_MIRROR_OOD_MAX = 0.15
EXP003_PRE_SHA256 = "60d3b7ffbfe750cc8c0d1e4dfcd80a308d6a3f406a4b5e5265b9d9563d8877d5"
EXP003_NATIVE_SHA256 = "47318cf20388f0f2cfdc63d9d76bd6c5519d39de54ab0e24589fcb1f90fc8f63"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        and _int_or_none(execution.get("torch_threads")) == 1
        and _int_or_none(execution.get("torch_interop_threads")) == 1
    )
    stem = str(path)[:-5] if str(path).lower().endswith(".json") else str(path)
    companion_paths = {
        "markdown": Path(stem + ".md"),
        "stdout": Path(stem + ".stdout.log"),
        "stderr": Path(stem + ".stderr.log"),
        "execution": Path(stem + ".execution.json"),
    }
    companions_ok = all(companion.exists() for companion in companion_paths.values())
    stderr_empty = companion_paths["stderr"].exists() and companion_paths["stderr"].stat().st_size == 0
    ood_ok = bool(gate.get("all_anchors_pass_ood_gate"))
    if "all_anchors_pass_ood_gate" not in gate:
        ood_ok = bool(anchor.get("anchor_ood_valid"))
    if ood_rate is not None:
        ood_ok = ood_ok and ood_rate <= EXP003_MIRROR_OOD_MAX
    ci_ok = bool(gate.get("passes_ci_gate"))
    usable = (
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
        and execution_ok
        and companions_ok
        and stderr_empty
        and ci_ok
        and ood_ok
    )
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
        "ood_ok": ood_ok,
        "ood_rate": ood_rate,
        "ood_threshold": ood_threshold,
        "device": str(mirror.get("device") or ""),
        "execution_ok": execution_ok,
        "companions_ok": companions_ok,
        "stderr_empty": stderr_empty,
        "companion_paths": {key: str(value) for key, value in companion_paths.items()},
        "candidate_bb100": finite_float(anchor.get("candidate_bb100")),
        "candidate_ci95_bb100": finite_float(anchor.get("candidate_ci95_bb100")),
        "usable": usable,
    }


def _first_eligible_exp003_gate(run_dir: Path, target_hands: int) -> dict[str, Any] | None:
    eligible: list[dict[str, Any]] = []
    for path in run_dir.glob("gate_*_status.json"):
        gate = load_json(path)
        if gate.get("_missing") or gate.get("_load_error"):
            continue
        iteration = _int_or_none(gate.get("checkpoint_iteration"))
        hands = _int_or_none(gate.get("checkpoint_hands"))
        if str(gate.get("overall") or "").upper() != "PASS" or iteration is None or hands is None:
            continue
        if hands >= target_hands:
            eligible.append({"path": str(path), "iteration": iteration, "hands": hands})
    if not eligible:
        return None
    return sorted(eligible, key=lambda row: (row["iteration"], row["hands"]))[0]


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
        "gate_iteration": _int_or_none(gate.get("iteration")),
        "gate_hands": _int_or_none(gate.get("checkpoint_hands") or gate.get("hands")),
        "archive_path": str(archive.get("path") or ""),
        "archive_sha256": str(archive.get("sha256") or "").lower(),
        "archive_iteration": _int_or_none(checkpoint.get("iteration")),
        "archive_hands": _int_or_none(checkpoint.get("total_hands")),
    }


def _latest_exp003_judgment(
    run_dir: Path,
    candidate_hands: int,
    candidate_sha256: str,
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
            decision_consistent = False
            if decision == "ADOPT":
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
                and judgment.get("measurement_status") == "REVIEW_READY"
                and judgment.get("decision_valid") is True
                and str(judgment.get("candidate_checkpoint_sha256") or "").lower() == candidate_sha256.lower()
                and isinstance(judgment.get("mirror_artifact_sha256"), dict)
                and set(judgment["mirror_artifact_sha256"]) == {
                    "pre_vs_native",
                    "post_vs_native",
                    "post_vs_pre_direct",
                }
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
    checkpoint directly vs the pre-cutover checkpoint.  A valid bundle is
    review-ready; only a separate judgment artifact can mark the queue DONE.
    """

    first_gate = _first_eligible_exp003_gate(run_dir, target_hands)
    freeze = _exp003_freeze_record(run_dir, target_hands)
    if first_gate is not None:
        freeze_valid = bool(
            freeze
            and freeze["target_hands"] == target_hands
            and freeze["gate_iteration"] == first_gate["iteration"]
            and freeze["gate_hands"] == first_gate["hands"]
            and freeze["archive_iteration"] == first_gate["iteration"]
            and freeze["archive_hands"] == first_gate["hands"]
            and bool(freeze["archive_path"])
            and bool(freeze["archive_sha256"])
            and Path(freeze["archive_path"]).exists()
        )
    else:
        freeze_valid = False

    records: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("v5_mirror_eval_exp003_*.json")):
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

    def choose(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        return sorted(rows, key=lambda row: (bool(row["usable"]), row["checked_at"]))[-1]

    roles = {
        "pre_vs_native": choose(pre_native),
        "post_vs_native": choose(post_native),
        "post_vs_pre_direct": choose(post_direct),
    }
    missing = [name for name, row in roles.items() if row is None]
    if not freeze_valid:
        missing.append("first_eligible_pass_freeze")
    if missing:
        status = "STALE" if candidate_hands is None and records else "INCOMPLETE"
        return {
            "status": status,
            "detail": f"EXP-003 causal mirror bundle missing roles: {', '.join(missing)}",
            "roles": roles,
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "freeze": freeze,
        }

    role_rows = [row for row in roles.values() if isinstance(row, dict)]
    protocol_keys = {
        (row["pairs"], row["seed"], row["policy_mode"], row["starting_stack"])
        for row in role_rows
    }
    invalid_roles = [name for name, row in roles.items() if not bool((row or {}).get("usable"))]
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
            "candidate_checkpoint_hands": candidate_hands,
            "first_eligible_gate": first_gate,
            "freeze": freeze,
        }

    assert candidate_hands is not None
    judgment = _latest_exp003_judgment(run_dir, candidate_hands, str(freeze["archive_sha256"]))
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
            "first_eligible_gate": first_gate,
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
        "first_eligible_gate": first_gate,
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
                    or post_gate_overall in {"PENDING_EVIDENCE", "DUE_EVIDENCE_REFRESH"}
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
        queue.append(
            item(
                priority=45,
                key="exp003_native_anchor_mirror_408064575",
                status=mirror_queue_status,
                trigger=f"checkpoint hands >= {EXP003_NATIVE_MIRROR_TARGET_HANDS}",
                action=(
                    f"At the first PASS checkpoint >= target, freeze that checkpoint and run the registered {EXP003_MIRROR_PAIRS:,}-pair "
                    f"three-role causal bundle with seed {EXP003_MIRROR_SEED}: gate21800 vs native75M, candidate vs native75M, "
                    "and candidate directly vs gate21800. Require identical protocol and OOD <= 0.15; then write a separate "
                    "ADOPT/ROLLBACK judgment artifact."
                ),
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
