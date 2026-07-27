"""Independent RS007 qualification result auditor."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "bf43f304c4709f356af131d60ef6e35a"
IDENTITY = "bf43f304c4709f356af131d60ef6e35a52a7456d215987abce8180419c4ed6d0"
PREREG = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_SHA = "0b881b6b5651a23dea03f625cb0e8d4880752e5286f7f2cd145eda46980beeeb"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_preregistration_audit_{TOKEN}_20260723.json"
PREREG_AUDIT_SHA = "aa0f6582ac80a814f7d116a736d245440121ddcf1cc46b126a0adf67adff7a97"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_qualification_{TOKEN}_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    rows = []
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for line in handle:
            digest.update(line)
            rows.append(json.loads(line))
    return rows, digest.hexdigest()


def write_exclusive(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def audit(root: Path, implementation_sha: str) -> int:
    if root.resolve(strict=False) != QUAL_ROOT.resolve(strict=False):
        raise RuntimeError("qualification_root_identity_failure")
    result_path = root / "result.json"
    output_path = root / "result_audit.json"
    if not root.is_dir() or not result_path.is_file() or output_path.exists():
        raise RuntimeError("qualification_bundle_presence_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    check("preregistration_exact", PREREG.stat().st_size == 21218 and sha_file(PREREG) == PREREG_SHA)
    check("preregistration_audit_exact", PREREG_AUDIT.stat().st_size == 9251 and sha_file(PREREG_AUDIT) == PREREG_AUDIT_SHA)
    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    input_failures = []
    for item in registration["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            input_failures.append(item["role"])
    check("all22_inputs_exact", len(registration["frozen_authority_inputs"]) == 22 and not input_failures, input_failures)
    check("implementation_audit_sha_exact", IMPL_AUDIT.is_file() and sha_file(IMPL_AUDIT) == implementation_sha)
    implementation = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    check("implementation_audit_pass", implementation.get("classification") == "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY")
    check("checkpoint_unchanged", sha_file(CHECKPOINT) == CHECKPOINT_SHA)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    check("result_identity_exact", result.get("identity_sha256") == IDENTITY)
    artifact_names = (
        "source_transition_rows.jsonl.gz",
        "boundary_matrix_rows.jsonl.gz",
        "terminal_utility_rows.jsonl.gz",
        "live_interface_rows.jsonl.gz",
        "resolution_rows.jsonl.gz",
        "repeat_rows.jsonl.gz",
        "fault_rows.jsonl.gz",
    )
    loaded: dict[str, list[dict[str, Any]]] = {}
    for name in artifact_names:
        try:
            path = root / name
            rows, logical = read_rows(path)
            manifest = result["artifact_manifest"][name]
            exact = (
                int(manifest["rows"]) == len(rows)
                and manifest["logical_sha256"] == logical
                and manifest["file_sha256"] == sha_file(path)
                and int(manifest["bytes"]) == path.stat().st_size
            )
            loaded[name] = rows
            check(f"artifact_exact:{name}", exact, {"rows": len(rows), "logical_sha256": logical})
        except Exception as error:
            loaded[name] = []
            check(f"artifact_exact:{name}", False, str(error))

    source = loaded["source_transition_rows.jsonl.gz"]
    boundary = loaded["boundary_matrix_rows.jsonl.gz"]
    terminal = loaded["terminal_utility_rows.jsonl.gz"]
    interfaces = loaded["live_interface_rows.jsonl.gz"]
    resolutions = loaded["resolution_rows.jsonl.gz"]
    repeats = loaded["repeat_rows.jsonl.gz"]
    faults = loaded["fault_rows.jsonl.gz"]
    check("source_rows_29878", len(source) == 29878)
    check("source_public_legal_all", all(row.get("public_legal") is True for row in source))
    check("source_adjacent_exact_all", all(row.get("adjacent_exact") is True for row in source))
    external = [row for row in source if row.get("policy_membership") is False]
    hero = [row for row in source if row.get("who") == "hero"]
    opponent = [row for row in source if row.get("who") == "opp"]
    check("external_1658_opponent_only", len(external) == 1658 and all(row.get("who") == "opp" and row.get("policy_slot") is None for row in external))
    check("hero_12564_slot_exact", len(hero) == 12564 and all(row.get("policy_membership") is True and row.get("hero_dual_path_exact") is True for row in hero))
    check("opponent_partition_exact", len(opponent) == 17314 and sum(row.get("policy_membership") is True for row in opponent) == 15656)
    check("source_scoped_keys_exact", all(isinstance(row.get("source_scoped_hand_key"), list) and len(row["source_scoped_hand_key"]) == 2 for row in source))

    cells = {(row.get("street"), row.get("actor"), row.get("scenario")) for row in boundary}
    check("boundary_rows_4096", len(boundary) == 4096)
    check("boundary_cells_128", len(cells) == 128)
    check("boundary_every_exact", all(row.get("exact") is True and row.get("expected_legal") == row.get("observed_legal") for row in boundary))
    scenario_counts = {}
    for row in boundary:
        scenario_counts[row["scenario"]] = scenario_counts.get(row["scenario"], 0) + 1
    check("boundary_scenarios16_balanced256", len(scenario_counts) == 16 and all(value == 256 for value in scenario_counts.values()), scenario_counts)
    short_rows = [row for row in boundary if row.get("scenario") == "SHORT_ALLIN_RAISE_NO_REOPEN"]
    reopen_rows = [row for row in boundary if row.get("scenario") == "FULL_RAISE_REOPENS"]
    check("short_allin_no_reopen_exact", len(short_rows) == 256 and all(row.get("raise_right", [True, True])[row.get("post_actor")] is False for row in short_rows))
    check("full_raise_reopen_exact", len(reopen_rows) == 256 and all(row.get("raise_right", [False, False])[row.get("post_actor")] is True for row in reopen_rows))

    terminal_cells = {row.get("cell") for row in terminal}
    check("terminal_rows_1280", len(terminal) == 1280)
    check("terminal_cells_20", len(terminal_cells) == 20)
    payout_exact = True
    cards_exact = True
    for row in terminal:
        payout = row.get("payout_cents", [])
        totals = row.get("totals", [])
        payout_exact &= len(payout) == 2 and sum(payout) == 0 and all(abs(int(value)) <= 20000 for value in payout)
        if row.get("terminal_kind") == "FOLD":
            folded = int(row["folded_player"])
            payout_exact &= payout[folded] == -totals[folded] and payout[1 - folded] == totals[folded]
        else:
            matched = min(totals)
            sign = int(row["comparator_sign"])
            expected = [matched, -matched] if sign > 0 else [-matched, matched] if sign < 0 else [0, 0]
            payout_exact &= payout == expected and len(row.get("board", [])) == 5
            cards = [*row.get("holes", [[], []])[0], *row.get("holes", [[], []])[1], *row.get("board", [])]
            cards_exact &= len(cards) == len(set(cards)) == 9
    check("terminal_payout_equations_exact", payout_exact)
    check("terminal_cards_exact", cards_exact)
    check("live_interfaces_6921", len(interfaces) == 6921)
    check("live_interfaces_all_exact", all(row.get("array_exact") and row.get("table_exact") and row.get("logits_slot_exact") for row in interfaces))

    check("resolution_rows_1280", len(resolutions) == 1280)
    nonfallback = [row for row in resolutions if not row.get("error_fallback")]
    fallback_rate = (len(resolutions) - len(nonfallback)) / max(1, len(resolutions))
    change_rate = sum(row.get("selected_slot") != row.get("baseline_slot") for row in nonfallback) / max(1, len(nonfallback))
    check("mc32_distinct_all", all(row.get("determinizations", {}).get("distinct_pair_count") == 32 for row in nonfallback))
    check("public_policy_contract_violations_zero", all(row.get("public_policy_contract_violations") == 0 for row in resolutions))
    check("fallback_rate_le_002", fallback_rate <= .02, fallback_rate)
    check("change_rate_ge_001", change_rate >= .01, change_rate)
    check("repeat_192_exact", len(repeats) == 192 and all(row.get("exact") is True for row in repeats))
    check("fault_128_exact", len(faults) == 128 and all(row.get("baseline_exact") is True and row.get("error_fallback") is True for row in faults))

    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    recomputed = {
        "rows": len(source),
        "external": len(external),
        "hero": len(hero),
        "opponent": len(opponent),
        "dual_path_exact": sum(row.get("hero_dual_path_exact") is True for row in hero),
        "boundary_rows": len(boundary),
        "boundary_cells": len(cells),
        "terminal_rows": len(terminal),
        "terminal_cells": len(terminal_cells),
        "live_interfaces": len(interfaces),
        "resolution_rows": len(resolutions),
        "repeat_rows": len(repeats),
        "repeat_exact": sum(row.get("exact") is True for row in repeats),
        "fault_rows": len(faults),
        "fault_baseline_exact": sum(row.get("baseline_exact") is True for row in faults),
        "fallback_rate": fallback_rate,
        "selected_slot_change_rate": change_rate,
    }
    check("metrics_recomputed_exact", all(metrics.get(key) == value for key, value in recomputed.items()), recomputed)
    check("latency_limits", metrics["latency_seconds"]["p50"] <= 2.5 and metrics["latency_seconds"]["p95"] <= 8 and metrics["latency_seconds"]["p99"] <= 15 and metrics["latency_seconds"]["max"] <= 20, metrics["latency_seconds"])
    check("rss_limit", metrics["process_rss_mib"] <= 3072, metrics["process_rss_mib"])
    check("gpu_limit", metrics["gpu_peak_allocated_mib"] <= 1024, metrics["gpu_peak_allocated_mib"])
    check("wall_limit", metrics["wall_seconds"] <= 1800, metrics["wall_seconds"])
    check("projection_limit", metrics["projected_quick5k_hours"] <= 12, metrics["projected_quick5k_hours"])
    gates = result.get("gates", {})
    expected_classification = "PASS / RS007_DUAL_DOMAIN_QUALIFICATION_PASS" if all(gates.values()) else "NONPASS / RS007_QUALIFICATION_GATE_NONPASS"
    check("result_classification_exact", result.get("classification") == expected_classification)
    check("result_gate_counts_exact", result.get("pass_count") == sum(gates.values()) and result.get("check_count") == len(gates))
    passed = all(item["pass"] for item in checks)
    audit_result = {
        "schema_version": "v5.rs007.qualification.result_audit.v1",
        "identity_sha256": IDENTITY,
        "classification": "PASS / RS007_INDEPENDENT_RESULT_AUDIT_PASS" if passed else "FAIL_CLOSED / RS007_INDEPENDENT_RESULT_AUDIT_FAILURE",
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "qualification_classification": result.get("classification"),
        "quick5k_authority": "AUTHORIZED_LATER_SEPARATE_BOUNDARY" if passed and result.get("classification", "").startswith("PASS /") else "NONE",
        "checkpoint_sha256": sha_file(CHECKPOINT),
        "network_or_slumbot_hands": 0,
    }
    write_exclusive(output_path, audit_result)
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    args = parser.parse_args()
    return audit(Path(args.root), args.implementation_audit_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
