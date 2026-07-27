#!/usr/bin/env python3
"""Reporting-only common-deal audit of loss-kbest pool selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from v5_mirror_eval import (  # noqa: E402
    POLICY_MODE,
    Policy,
    configure_runtime,
    init_model,
    sha256_file,
    shuffled_deck,
    utc_now,
)
from v5_meas001_common_deal_eval import run_mirrored_role  # noqa: E402
from alpha_holdem.environment_v55 import HUNLEnvironmentV55  # noqa: E402


DESIGN_SCHEMA = "v5.pool_selection.measurement_design.v1"
RESULT_SCHEMA = "v5.pool_selection.measurement_result.v1"
PAIR_SCHEMA = "v5.pool_selection.pair.v1"
AUDIT_SCHEMA = "v5.pool_selection.bundle_audit.v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def payload_hash(value: dict[str, Any], field: str) -> str:
    unsigned = dict(value)
    unsigned.pop(field, None)
    return hashlib.sha256(canonical_bytes(unsigned)).hexdigest()


def state_dict_hash(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        meta = canonical_bytes([name, str(tensor.dtype), list(tensor.shape)])
        digest.update(len(meta).to_bytes(8, "big"))
        digest.update(meta)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()


def validate_design(design: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if design.get("schema_version") != DESIGN_SCHEMA:
        errors.append("design schema mismatch")
    if design.get("immutable") is not True:
        errors.append("design is not immutable")
    if design.get("design_payload_sha256") != payload_hash(design, "design_payload_sha256"):
        errors.append("design payload hash mismatch")
    panel = design.get("panel") if isinstance(design.get("panel"), list) else []
    ids = [row.get("id") for row in panel if isinstance(row, dict)]
    if len(panel) < 6 or len(ids) != len(panel) or len(set(ids)) != len(ids):
        errors.append("panel identities are incomplete or duplicated")
    if sum(bool(row.get("active_at_gate31400")) for row in panel if isinstance(row, dict)) != 5:
        errors.append("design must bind exactly five active snapshots")
    for row in panel:
        if not isinstance(row, dict):
            continue
        if not isinstance(row.get("state_sha256"), str) or len(row["state_sha256"]) != 64:
            errors.append(f"snapshot {row.get('id')} state hash invalid")
        if not isinstance(row.get("selection_loss"), (int, float)):
            errors.append(f"snapshot {row.get('id')} selection loss missing")
    rules = design.get("measurement") if isinstance(design.get("measurement"), dict) else {}
    if rules.get("pairs_per_edge") != 2000:
        errors.append("pairs_per_edge is not frozen at 2000")
    if rules.get("seat_order") != [0, 1] or rules.get("policy_mode") != POLICY_MODE:
        errors.append("seat or policy mode mismatch")
    if rules.get("starting_stack_bb") != 200.0 or rules.get("env_version") != "v55":
        errors.append("stack/env mismatch")
    if rules.get("no_adaptive_extension") is not True:
        errors.append("adaptive extension is not forbidden")
    decision = design.get("decision_rule") if isinstance(design.get("decision_rule"), dict) else {}
    if decision.get("meaningful_inversion_margin_bb100") != 10.0:
        errors.append("inversion margin mismatch")
    if decision.get("familywise_alpha") != 0.05 or decision.get("multiplicity") != "holm_bonferroni_active_vs_excluded":
        errors.append("multiplicity contract mismatch")
    if design.get("authority") != "REPORTING_ONLY_NO_LAUNCH":
        errors.append("authority mismatch")
    return errors


def inventory_snapshots(design: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    snapshots: dict[int, dict[str, Any]] = {}
    containers: list[dict[str, Any]] = []
    for source in design["containers"]:
        path = Path(source["path"])
        actual_hash = sha256_file(path)
        if actual_hash != source["sha256"]:
            raise ValueError(f"container hash mismatch: {path}")
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        if checkpoint.get("env_version") != "v55" or checkpoint.get("obs_version") != "v55":
            raise ValueError(f"container contract mismatch: {path}")
        containers.append({"path": str(path.resolve()), "sha256": actual_hash, "iteration": checkpoint.get("iteration")})
        for row in checkpoint.get("pool_snapshots", []):
            snapshot_id = int(row["id"])
            state_hash = state_dict_hash(row["state_dict"])
            candidate = {
                "id": snapshot_id,
                "iteration": int(row["iteration"]),
                "hands": int(row["hands"]),
                "selection_loss": float(row["selection_loss"]),
                "state_sha256": state_hash,
                "state_dict": row["state_dict"],
                "container_path": path,
                "checkpoint_metadata": {
                    "env_version": checkpoint.get("env_version"),
                    "obs_version": checkpoint.get("obs_version"),
                    "action_space_version": checkpoint.get("action_space_version"),
                    "starting_stack_bb": checkpoint.get("starting_stack_bb"),
                    "norm_layer": checkpoint.get("norm_layer", "bn"),
                },
            }
            prior = snapshots.get(snapshot_id)
            if prior and any(prior[key] != candidate[key] for key in ("iteration", "hands", "selection_loss", "state_sha256")):
                raise ValueError(f"snapshot identity conflict: {snapshot_id}")
            snapshots.setdefault(snapshot_id, candidate)
        del checkpoint
    for expected in design["panel"]:
        actual = snapshots.get(int(expected["id"]))
        if not actual:
            raise ValueError(f"snapshot missing: {expected['id']}")
        for key in ("iteration", "hands", "state_sha256"):
            if actual[key] != expected[key]:
                raise ValueError(f"snapshot {expected['id']} {key} mismatch")
        if not math.isclose(actual["selection_loss"], float(expected["selection_loss"]), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"snapshot {expected['id']} selection_loss mismatch")
    return snapshots, containers


def make_policy(snapshot: dict[str, Any], device: str) -> Policy:
    meta = snapshot["checkpoint_metadata"]
    checkpoint = {**meta, "model": snapshot["state_dict"], "iteration": snapshot["iteration"], "total_hands": snapshot["hands"]}
    return Policy(
        label=f"pool_id_{snapshot['id']}_iter_{snapshot['iteration']}",
        path=Path(snapshot["container_path"]),
        sha256=snapshot["state_sha256"],
        checkpoint=checkpoint,
        model=init_model(checkpoint, device),
        env_version="v55",
        obs_version="v55",
        emulate_raise_cap1_legality=False,
        device=device,
    )


def edge_stats(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean()) * 100.0
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    se = std / math.sqrt(max(len(array), 1)) * 100.0
    half = 1.96 * se
    return {"mean_bb100": mean, "se_bb100": se, "ci95_halfwidth_bb100": half, "ci95_lower_bb100": mean - half, "ci95_upper_bb100": mean + half}


def normal_one_sided_p(mean: float, se: float, margin: float) -> float:
    if se <= 0:
        return 0.0 if mean > margin else 1.0
    z = (mean - margin) / se
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def holm_decisions(rows: list[dict[str, Any]], alpha: float) -> None:
    ordered = sorted(rows, key=lambda row: row["p_one_sided_margin"])
    still_rejecting = True
    count = len(ordered)
    for rank, row in enumerate(ordered, start=1):
        threshold = alpha / (count - rank + 1)
        reject = still_rejecting and row["p_one_sided_margin"] <= threshold
        row["holm_rank"] = rank
        row["holm_threshold"] = threshold
        row["holm_reject"] = reject
        if not reject:
            still_rejecting = False


def classify_result(design: dict[str, Any], edges: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    active = {int(row["id"]) for row in design["panel"] if row["active_at_gate31400"]}
    margin = float(design["decision_rule"]["meaningful_inversion_margin_bb100"])
    comparisons: list[dict[str, Any]] = []
    for edge in edges:
        a, b = int(edge["a_id"]), int(edge["b_id"])
        if (a in active) == (b in active):
            continue
        excluded = b if a in active else a
        active_id = a if a in active else b
        mean = -float(edge["mean_a_bb100"]) if a in active else float(edge["mean_a_bb100"])
        se = float(edge["se_a_bb100"])
        comparisons.append({"excluded_id": excluded, "active_id": active_id, "excluded_minus_active_bb100": mean, "se_bb100": se, "p_one_sided_margin": normal_one_sided_p(mean, se, margin)})
    holm_decisions(comparisons, float(design["decision_rule"]["familywise_alpha"]))
    supported = [row for row in comparisons if row["holm_reject"] and row["excluded_minus_active_bb100"] > margin]
    excluded_counts: dict[int, int] = {}
    active_counts: dict[int, int] = {}
    for row in supported:
        excluded_counts[row["excluded_id"]] = excluded_counts.get(row["excluded_id"], 0) + 1
        active_counts[row["active_id"]] = active_counts.get(row["active_id"], 0) + 1
    passes = len(excluded_counts) >= 2 or any(count >= 2 for count in excluded_counts.values())
    if passes:
        return "PASS_EXP007_CANDIDATE_PERMISSION_NO_LAUNCH", comparisons
    z = statistics.NormalDist().inv_cdf(1.0 - 0.05 / max(len(comparisons), 1))
    all_no_material = all(row["excluded_minus_active_bb100"] + z * row["se_bb100"] <= margin for row in comparisons)
    return ("FAIL_NO_MATERIAL_MISRANKING" if all_no_material else "INCONCLUSIVE"), comparisons


def evaluate(design: dict[str, Any], out_pairs: Path, device: str) -> dict[str, Any]:
    errors = validate_design(design)
    if errors:
        raise ValueError("invalid design: " + "; ".join(errors))
    snapshots, containers = inventory_snapshots(design)
    panel = sorted(int(row["id"]) for row in design["panel"])
    pairs = int(design["measurement"]["pairs_per_edge"])
    seed = int(design["measurement"]["seed"])
    runtime_ceiling = float(design["measurement"]["runtime_ceiling_seconds"])
    env = HUNLEnvironmentV55(starting_stack=200.0)
    edges: list[dict[str, Any]] = []
    started = time.monotonic()
    with out_pairs.open("x", encoding="utf-8", newline="\n") as output:
        for i, a_id in enumerate(panel):
            for b_id in panel[i + 1 :]:
                policy_a = make_policy(snapshots[a_id], device)
                policy_b = make_policy(snapshots[b_id], device)
                rng = __import__("random").Random(seed)
                values: list[float] = []
                ood_a = ood_b = decisions_a = decisions_b = 0
                for index in range(pairs):
                    if time.monotonic() - started > runtime_ceiling:
                        raise TimeoutError("registered runtime ceiling exceeded")
                    deck = shuffled_deck(rng)
                    deck_hash = hashlib.sha256(bytes(deck)).hexdigest()
                    result = run_mirrored_role(env=env, deck=deck, candidate=policy_a, anchor=policy_b)
                    value = float(result["pair_mean_bb_per_hand"])
                    values.append(value)
                    ood_a += int(result["ood_nodes"]["candidate"])
                    ood_b += int(result["ood_nodes"]["anchor"])
                    decisions_a += int(result["policy_decisions"]["candidate"])
                    decisions_b += int(result["policy_decisions"]["anchor"])
                    output.write(json.dumps({"schema_version": PAIR_SCHEMA, "edge": f"{a_id}:{b_id}", "a_id": a_id, "b_id": b_id, "index": index, "deal_id": f"poolsel-{seed}-{index:04d}-{deck_hash[:16]}", "deck_sha256": deck_hash, "a_rewards_bb": result["candidate_rewards_bb"], "a_pair_mean_bb_per_hand": value}, sort_keys=True) + "\n")
                stats = edge_stats(values)
                edges.append({"a_id": a_id, "b_id": b_id, "pairs": pairs, "mean_a_bb100": stats["mean_bb100"], "se_a_bb100": stats["se_bb100"], "ci95_lower_a_bb100": stats["ci95_lower_bb100"], "ci95_upper_a_bb100": stats["ci95_upper_bb100"], "a_ood_rate": ood_a / max(decisions_a, 1), "b_ood_rate": ood_b / max(decisions_b, 1)})
                del policy_a.model, policy_b.model
                if device == "cuda":
                    torch.cuda.empty_cache()
    verdict, comparisons = classify_result(design, edges)
    max_ood = max(max(row["a_ood_rate"], row["b_ood_rate"]) for row in edges)
    if max_ood > float(design["measurement"]["max_ood_rate"]):
        verdict = "INCONCLUSIVE_OOD_INVALID"
    return {"schema_version": RESULT_SCHEMA, "checked_at": utc_now(), "design_payload_sha256": design["design_payload_sha256"], "status": verdict, "authority": "EXP007_CANDIDATE_PERMISSION_NO_LAUNCH" if verdict.startswith("PASS_") else "NO_CANDIDATE_NO_LAUNCH", "panel_ids": panel, "containers": containers, "pairs_per_edge": pairs, "edge_count": len(edges), "edges": edges, "active_vs_excluded": comparisons, "max_ood_rate": max_ood, "elapsed_seconds": time.monotonic() - started}


def audit_bundle(design: dict[str, Any], result: dict[str, Any], pair_rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = validate_design(design)
    if result.get("schema_version") != RESULT_SCHEMA:
        errors.append("result schema mismatch")
    if result.get("design_payload_sha256") != design.get("design_payload_sha256"):
        errors.append("result design identity mismatch")
    panel = sorted(int(row["id"]) for row in design.get("panel", []))
    expected_edges = len(panel) * (len(panel) - 1) // 2
    expected_rows = expected_edges * int(design.get("measurement", {}).get("pairs_per_edge", 0))
    if len(pair_rows) != expected_rows:
        errors.append("partial pair matrix")
    seen: set[tuple[str, int]] = set()
    deal_by_index: dict[int, tuple[str, str]] = {}
    for row in pair_rows:
        if row.get("schema_version") != PAIR_SCHEMA:
            errors.append("pair schema mismatch")
            break
        key = (str(row.get("edge")), int(row.get("index", -1)))
        if key in seen:
            errors.append("duplicate edge/index")
            break
        seen.add(key)
        index = int(row.get("index", -1))
        identity = (str(row.get("deal_id")), str(row.get("deck_sha256")))
        if index in deal_by_index and deal_by_index[index] != identity:
            errors.append("common deal identity mismatch")
            break
        deal_by_index.setdefault(index, identity)
        rewards = row.get("a_rewards_bb")
        if not isinstance(rewards, list) or len(rewards) != 2 or not all(isinstance(v, (int, float)) for v in rewards):
            errors.append("seat swap rewards missing")
            break
        if not math.isclose(float(row.get("a_pair_mean_bb_per_hand", math.nan)), (float(rewards[0]) + float(rewards[1])) / 2.0, abs_tol=1e-9):
            errors.append("pair mean mismatch")
            break
    if int(result.get("edge_count") or -1) != expected_edges:
        errors.append("result edge count mismatch")
    valid_statuses = {"PASS_EXP007_CANDIDATE_PERMISSION_NO_LAUNCH", "FAIL_NO_MATERIAL_MISRANKING", "INCONCLUSIVE", "INCONCLUSIVE_OOD_INVALID"}
    if result.get("status") not in valid_statuses:
        errors.append("invalid terminal status")
    if result.get("authority") not in {"EXP007_CANDIDATE_PERMISSION_NO_LAUNCH", "NO_CANDIDATE_NO_LAUNCH"}:
        errors.append("invalid authority")
    return {"schema_version": AUDIT_SCHEMA, "checked_at": utc_now(), "status": "PASS" if not errors else "FAIL_CLOSED", "errors": errors, "expected_edges": expected_edges, "expected_pair_rows": expected_rows, "observed_pair_rows": len(pair_rows), "behavior_launch_authorized": False, "slumbot_claim_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", required=True)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    parser.add_argument("--priority", choices=["below-normal", "normal"], default="below-normal")
    parser.add_argument("--torch-threads", type=int, default=1)
    parser.add_argument("--torch-interop-threads", type=int, default=1)
    parser.add_argument("--out-pairs", required=True)
    parser.add_argument("--out-result", required=True)
    parser.add_argument("--out-audit", required=True)
    args = parser.parse_args()
    for value in (args.out_pairs, args.out_result, args.out_audit):
        if Path(value).exists():
            raise FileExistsError(f"one-shot output exists: {value}")
    execution = configure_runtime(args)
    design = json.loads(Path(args.design).read_text(encoding="utf-8"))
    device = args.device if args.device == "cpu" or torch.cuda.is_available() else "cpu"
    result = evaluate(design, Path(args.out_pairs), device)
    result["execution"] = {**execution, "status": "COMPLETED", "finished_at": utc_now()}
    Path(args.out_result).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [json.loads(line) for line in Path(args.out_pairs).read_text(encoding="utf-8").splitlines() if line.strip()]
    audit = audit_bundle(design, result, rows)
    audit["design_sha256"] = sha256_file(Path(args.design))
    audit["result_sha256"] = sha256_file(Path(args.out_result))
    audit["pairs_sha256"] = sha256_file(Path(args.out_pairs))
    Path(args.out_audit).write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["status"], "audit": audit["status"]}, indent=2))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
