"""Independent fail-closed audit of the immutable TN001 qualification bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path
from typing import Any

DESIGN_ID = "PHASE_FA_TN001_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY"
DESIGN_SHA256 = "3dae3b32ec4af21ed41d6b14050f76e87b896ab07d4cbd54fc2a431ac1c50dd1"
DESIGN_AUDIT_SHA256 = "a0f2b992444482910eb6590473eee2967c67609e8bb37880433412d8b3d59423"
TEMPERATURES = (1.0, 5.0, 10.0, 25.0, 100.0)
EXPECTED_FILES = {
    "constructive_witnesses.jsonl", "discovery_states.jsonl", "quality_rows.jsonl",
    "hidden_invariance_pairs.jsonl", "raw_metrics.json", "input_manifest.json",
    "execution_manifest.json", "result.json",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, 1):
            if not line.endswith("\n"):
                raise RuntimeError(f"jsonl_missing_newline:{path}:{line_number}")
            rows.append(json.loads(line))
    return rows


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, math.floor((len(ordered) - 1) * q))])


def recompute_temperature(rows: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    summary: dict[str, Any] = {}
    selected: float | None = None
    for temperature in TEMPERATURES:
        key = str(temperature)
        scopes: dict[str, Any] = {}
        for scope in ("GLOBAL", "200", "100", "50"):
            chosen = rows if scope == "GLOBAL" else [r for r in rows if r["depth"] == int(scope)]
            l1s = [float(x) for row in chosen for x in row["temperature_metrics"][key]["six_pairwise_l1"]]
            top = sum(bool(row["temperature_metrics"][key]["three_of_four_top_agreement"]) for row in chosen) / len(chosen)
            entropy = sum(float(row["temperature_metrics"][key]["normalized_entropy"]) for row in chosen) / len(chosen)
            metrics = {
                "six_pairwise_batch_distribution_l1_mean": sum(l1s) / len(l1s),
                "six_pairwise_batch_distribution_l1_p95": percentile(l1s, 0.95),
                "states_with_three_of_four_batch_top_action_agreement_fraction": top,
                "mean_normalized_entropy": entropy,
            }
            metrics["passes"] = (
                metrics["six_pairwise_batch_distribution_l1_mean"] <= 0.35
                and metrics["six_pairwise_batch_distribution_l1_p95"] <= 0.8
                and top >= 0.7 and entropy <= 0.9
            )
            scopes[scope] = metrics
        summary[key] = {"scopes": scopes, "passes": all(v["passes"] for v in scopes.values())}
        if selected is None and summary[key]["passes"]:
            selected = temperature
    return selected, summary


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, indent=2, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def audit(args: argparse.Namespace) -> int:
    if os.environ.get("TN001_AUDIT_INVOCATION") != "LAUNCHER_OWNED_ABSOLUTE_PATHS":
        raise RuntimeError("audit_launcher_ownership_failure")
    root = Path(args.root)
    audit_path = root / "result_audit.json"
    if audit_path.exists():
        raise RuntimeError("immutable_audit_exists")
    observed_files = {p.name for p in root.iterdir() if p.is_file()}
    if observed_files != EXPECTED_FILES:
        raise RuntimeError(f"preaudit_file_set_failure:{sorted(observed_files)}")
    design_path, design_audit_path, implementation_path = map(
        Path, (args.design, args.design_audit, args.implementation_audit)
    )
    runner_path, launcher_path = Path(args.runner), Path(args.launcher)
    design = json.loads(design_path.read_text(encoding="utf-8"))
    design_audit = json.loads(design_audit_path.read_text(encoding="utf-8"))
    implementation = json.loads(implementation_path.read_text(encoding="utf-8"))
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    metrics = json.loads((root / "raw_metrics.json").read_text(encoding="utf-8"))
    inputs = json.loads((root / "input_manifest.json").read_text(encoding="utf-8"))
    execution = json.loads((root / "execution_manifest.json").read_text(encoding="utf-8"))
    constructive = load_jsonl(root / "constructive_witnesses.jsonl")
    discovery = load_jsonl(root / "discovery_states.jsonl")
    quality = load_jsonl(root / "quality_rows.jsonl")
    hidden = load_jsonl(root / "hidden_invariance_pairs.jsonl")
    selected, temperature_summary = recompute_temperature(quality)
    cell_counts = Counter(row["cell"] for row in constructive)
    quality_counts = Counter(row["cell"] for row in quality)
    checks: dict[str, bool] = {}
    checks["design_identity_exact"] = (
        sha256_file(design_path) == DESIGN_SHA256
        and design.get("design_id") == DESIGN_ID
        and result.get("design_id") == DESIGN_ID
    )
    checks["design_audit_pass148_exact"] = (
        sha256_file(design_audit_path) == DESIGN_AUDIT_SHA256
        and design_audit.get("overall") == "PASS" and design_audit.get("checks_total") == 148
    )
    checks["implementation_audit_hash_and_pass"] = (
        sha256_file(implementation_path) == args.implementation_audit_sha256
        and implementation.get("overall") == "PASS"
        and implementation.get("contract_probes_passed") == 2
    )
    checks["runner_launcher_auditor_bound"] = (
        sha256_file(runner_path) == implementation.get("runner_sha256") == result["identities"]["runner_sha256"]
        and sha256_file(launcher_path) == implementation.get("launcher_sha256")
        and sha256_file(Path(__file__)) == implementation.get("auditor_sha256")
    )
    checks["raw_file_hashes_exact"] = all(
        sha256_file(root / f"{name}.jsonl" if name in {"constructive_witnesses", "discovery_states", "quality_rows", "hidden_invariance_pairs"}
                    else root / f"{name}.json")
        == payload["sha256"]
        for name, payload in result["files"].items()
    )
    checks["all16_frozen_inputs_rehashed"] = (
        len(inputs.get("verified_inputs", [])) == 16
        and all(sha256_file(Path(item["path"])) == item["sha256"] for item in inputs["verified_inputs"])
    )
    checks["constructive_768_24x32"] = len(constructive) == 768 and len(cell_counts) == 24 and set(cell_counts.values()) == {32}
    checks["constructive_schema_privacy"] = all(
        row.get("classification") == "FORBIDDEN_DIAGNOSTIC_ONLY"
        and "hole" not in canonical_json(row).lower() and "deck" not in canonical_json(row).lower()
        for row in constructive
    )
    checks["discovery_3072_trajectories"] = (
        len({(row["depth"], row["trajectory"]) for row in discovery}) == 3072
        and all(0 <= int(row["decision"]) < 64 for row in discovery)
    )
    checks["discovery_schema_privacy"] = all(
        row.get("classification") == "FORBIDDEN_DIAGNOSTIC_ONLY"
        and "hole" not in canonical_json(row).lower() and "deck" not in canonical_json(row).lower()
        for row in discovery
    )
    checks["quality_192_24x8"] = len(quality) == 192 and len(quality_counts) == 24 and set(quality_counts.values()) == {8}
    checks["quality_row_ids_exact"] = [row["row_id"] for row in quality] == list(range(192))
    checks["quality_mc32_shapes_exact"] = all(
        row["rollouts_per_action"] == 32 and len(row["batch_values"]) == 4
        and all(len(batch) == 9 for batch in row["batch_values"])
        and set(row["temperature_metrics"]) == {str(t) for t in TEMPERATURES}
        for row in quality
    )
    checks["quality_probabilities_and_illegal_mass"] = all(
        all(
            len(probs) == 9 and abs(sum(probs) - 1.0) <= 1e-6
            and all(math.isfinite(float(x)) and float(x) >= 0 for x in probs)
            and sum(probs[i] for i in range(9) if row["legal_mask9"][i] == 0.0) == 0.0
            for probs in row["teacher_probabilities_by_temperature"].values()
        ) for row in quality
    )
    checks["quality_no_hidden_payload"] = all(
        "actor_hole" not in row and "opponent" not in canonical_json(row).lower()
        and "deck" not in canonical_json(row).lower() for row in quality
    )
    checks["hidden_pairs_24_exact"] = len(hidden) == 24 and [row["pair_id"] for row in hidden] == list(range(24))
    checks["hidden_invariance_zero_failures"] = all(
        row["source_hidden_different"] is True and row["allowed_information_identical"] is True
        and row["label_identity_sha256_a"] == row["label_identity_sha256_b"]
        and row["source_hidden_payload_serialized"] is False for row in hidden
    )
    checks["same_seed_repeat_zero"] = metrics["same_seed_repeats"] == 24 and metrics["same_seed_repeat_failures"] == 0
    checks["temperature_summary_independent_exact"] = (
        selected == metrics["selected_temperature"] and temperature_summary == metrics["temperature_summary"]
    )
    checks["temperature_selection_lowest_rule"] = (
        selected is None or (
            temperature_summary[str(selected)]["passes"]
            and all(not temperature_summary[str(t)]["passes"] for t in TEMPERATURES if t < selected)
        )
    )
    checks["resource_gates_truth"] = (
        result["gates"]["wall_under_900s"] == (result["resources"]["wall_seconds"] <= 900.0)
        and result["gates"]["process_tree_peak_rss_under_2048mb"] == (result["resources"]["process_tree_peak_rss_mb"] <= 2048.0)
        and result["gates"]["diagnostic_output_under_512mib"] == (result["resources"]["bundle_bytes_before_result_and_audit"] <= 536_870_912)
        and result["gates"]["projection_under_24h"] == (metrics["projected_four_worker_wall_seconds_1m"] <= 86_400.0)
        and result["gates"]["row_p99_under_8192"] == (metrics["uncompressed_quality_row_bytes_p99"] <= 8192)
        and result["gates"]["projection_bytes_under_10gb"] == (metrics["projected_uncompressed_bytes_1m"] <= 10_000_000_000)
    )
    device = execution["device_contract"]
    checks["runtime_device_workers_exact"] = (
        device["CUDA_VISIBLE_DEVICES"] == "-1"
        and device["TN001_DEVICE_MODE"] == "CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK"
        and device["TN001_CONTRACT_NONCE"] == "2026472291"
        and device["torch_in_sys_modules"] is False and execution["workers"] == 4 and execution["gpu"] is False
    )
    recomputed_gate_subset = {
        "frozen_inputs_16_exact": checks["all16_frozen_inputs_rehashed"],
        "witnesses_24_of_24": len(cell_counts) == 24 and metrics["witness_failures"] == 0,
        "constructive_states_768": len(constructive) == 768,
        "cell_minimums_32": all(int(v) >= 32 for v in metrics["unique_keys_by_cell"].values()),
        "exploratory_trajectories_3072": len({(row["depth"], row["trajectory"]) for row in discovery}) == 3072,
        "quality_rows_192": len(quality) == 192,
        "mc32_exact": checks["quality_mc32_shapes_exact"],
        "hidden_invariance_24_zero_failures": len(hidden) == 24 and metrics["hidden_invariance_failures"] == 0,
        "same_seed_repeats_24_zero_failures": checks["same_seed_repeat_zero"],
        "illegal_mass_zero": checks["quality_probabilities_and_illegal_mass"],
        "global_temperature_selected": selected is not None,
        "rollout_step_limit": all(row["max_rollout_steps"] <= 128 for row in quality),
    }
    checks["runner_gate_subset_independently_exact"] = all(
        result["gates"][name] == value for name, value in recomputed_gate_subset.items()
    )
    all_runner_gates = all(result["gates"].values())
    checks["verdict_classification_exact"] = (
        result["verdict"] == ("PASS" if all_runner_gates else "NONPASS")
        and result["classification"] == (
            "TN001_PASS_TRAJECTORY_NATIVE_INFOSET_MC32_AND_BOUNDED_DISCOVERY_FEASIBLE"
            if all_runner_gates else "TN001_NONPASS_TRAJECTORY_NATIVE_INFOSET_MC32_OR_BOUNDED_DISCOVERY_FEASIBILITY"
        )
    )
    checks["authority_scope_exact"] = result["authority"] == {
        "training_eligibility": "FORBIDDEN", "asset_generation": "NONE",
        "model_or_checkpoint_change": "NONE", "slumbot": "NONE", "official_hands": 0,
        "pass_next": "SEPARATELY_REGISTER_ONE_BOUNDED_TEACHER_ASSET_DESIGN",
        "nonpass_next": "RERANK_TO_OPPONENT_LEAGUE_FAMILY",
    } and result.get("strength") == "L0"
    failed = [name for name, passed in checks.items() if not passed]
    audit_result = {
        "schema_version": "v5.tn001.trajectory_native_qualification.result_audit.v1",
        "classification": "TN001_RESULT_AUDIT_PASS_EXACT_JUDGMENT" if not failed else "TN001_RESULT_AUDIT_FAIL_CLOSED",
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks": checks, "checks_passed": sum(checks.values()), "checks_total": len(checks),
        "checks_failed": failed, "qualification_verdict": result["verdict"],
        "qualification_classification": result["classification"],
        "result_sha256": sha256_file(root / "result.json"),
        "raw_bundle_sha256": hashlib.sha256(
            "\n".join(f"{name}\t{sha256_file(root / name)}" for name in sorted(EXPECTED_FILES)).encode("utf-8")
        ).hexdigest(),
        "exact_judgment": (
            "TN001_PASS_PROCEED_TO_SEPARATE_BOUNDED_ASSET_PREREGISTRATION"
            if not failed and result["verdict"] == "PASS"
            else "TN001_NONPASS_RERANK_TO_OPPONENT_LEAGUE_NO_REPAIR_OR_EXTENSION"
            if not failed else "EVIDENCE_BUNDLE_FAIL_CLOSED"
        ),
    }
    write_json(audit_path, audit_result)
    print(canonical_json({"overall": audit_result["overall"],
                          "checks": f"{audit_result['checks_passed']}/{audit_result['checks_total']}",
                          "judgment": audit_result["exact_judgment"], "audit": str(audit_path)}))
    return 0 if not failed else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in ("root", "design", "design-audit", "implementation-audit",
                 "implementation-audit-sha256", "runner", "launcher"):
        parser.add_argument(f"--{name}", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(audit(parse_args()))
