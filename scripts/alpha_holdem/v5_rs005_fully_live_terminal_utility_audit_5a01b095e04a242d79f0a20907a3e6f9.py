"""Independent RS005 qualification-result auditor."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "5a01b095e04a242d79f0a20907a3e6f9"
IDENTITY = "5a01b095e04a242d79f0a20907a3e6f9d59c61780cf9a73765138cdb1f205bde"
PREREG = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_SHA = "70a232c8cbbef807e2530ba19e35f887b143d9e0f226cd443385d04e9a0a0c8c"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_audit_{TOKEN}_20260723.json"
PREREG_AUDIT_SHA = "7f6b4800a7c22588f01fc02f8b1c632d8496fc2737fc8c0187faa39943d735c4"
IMPLEMENTATION_AUDIT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_qualification_{TOKEN}_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_rows(path: Path) -> tuple[list[dict[str, Any]], str]:
    rows, digest = [], hashlib.sha256()
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
        raise RuntimeError("root_identity_failure")
    result_path = root / "result.json"
    output_path = root / "result_audit.json"
    if not root.is_dir() or not result_path.is_file() or output_path.exists():
        raise RuntimeError("result_bundle_presence_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    check("preregistration_exact", PREREG.stat().st_size == 22175 and sha_file(PREREG) == PREREG_SHA)
    check("preregistration_audit_exact", PREREG_AUDIT.stat().st_size == 13101 and sha_file(PREREG_AUDIT) == PREREG_AUDIT_SHA)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    input_failures = []
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            input_failures.append(item["role"])
    check("all26_frozen_inputs_exact", len(prereg["frozen_authority_inputs"]) == 26 and not input_failures, input_failures)
    check("checkpoint_unchanged", sha_file(CHECKPOINT) == CHECKPOINT_SHA)
    check("implementation_audit_sha_exact", IMPLEMENTATION_AUDIT.is_file() and sha_file(IMPLEMENTATION_AUDIT) == implementation_sha)
    implementation = json.loads(IMPLEMENTATION_AUDIT.read_text(encoding="utf-8"))
    check("implementation_audit_pass", implementation.get("classification") == "PASS / RS005_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    check("result_identity_exact", result.get("identity_sha256") == IDENTITY)
    expected_files = (
        "ledger_rows.jsonl.gz", "prefix_rows.jsonl.gz", "hero_live_interfaces.jsonl.gz",
        "synthetic_states.jsonl.gz", "terminal_utility_rows.jsonl.gz",
        "resolution_rows.jsonl.gz", "repeat_rows.jsonl.gz", "fault_rows.jsonl.gz",
    )
    loaded: dict[str, list[dict[str, Any]]] = {}
    for name in expected_files:
        path = root / name
        try:
            rows, logical_sha = read_rows(path)
            loaded[name] = rows
            manifest = result["artifact_manifest"][name]
            passed = (
                int(manifest["rows"]) == len(rows)
                and manifest["logical_sha256"] == logical_sha
                and manifest["file_sha256"] == sha_file(path)
                and int(manifest["bytes"]) == path.stat().st_size
            )
            check(f"artifact_exact:{name}", passed, {"rows": len(rows), "logical_sha256": logical_sha})
        except Exception as exc:
            check(f"artifact_exact:{name}", False, str(exc))
            loaded[name] = []

    ledger = loaded["ledger_rows.jsonl.gz"]
    prefixes = loaded["prefix_rows.jsonl.gz"]
    live = loaded["hero_live_interfaces.jsonl.gz"]
    synthetic = loaded["synthetic_states.jsonl.gz"]
    terminal = loaded["terminal_utility_rows.jsonl.gz"]
    resolutions = loaded["resolution_rows.jsonl.gz"]
    repeats = loaded["repeat_rows.jsonl.gz"]
    faults = loaded["fault_rows.jsonl.gz"]
    check("ledger_rows_29878", len(ledger) == 29878)
    check("ledger_every_exact", all(row.get("exact") is True for row in ledger))
    check("source_scoped_hand_keys", all(isinstance(row.get("source_scoped_hand_key"), list) and len(row["source_scoped_hand_key"]) == 2 for row in ledger))
    check("prefix_rows_584", len(prefixes) == 584)
    check("prefix_every_exact", all(row.get("exact") is True for row in prefixes))
    check("live_interfaces_6921", len(live) == 6921)
    check("live_no_forbidden_objects", all(row.get("exact_cent_state") is True and row.get("forbidden_runtime_object_count") == 0 for row in live))
    check("synthetic_states_8192", len(synthetic) == 8192)
    check("synthetic_every_exact", all(row.get("exact") is True for row in synthetic))
    cells = {row.get("cell") for row in terminal}
    check("terminal_rows_1280", len(terminal) == 1280)
    check("terminal_cells_20", len(cells) == 20, sorted(str(x) for x in cells))
    check("fold_cell_balance", all(sum(row.get("cell") == f"FOLD_PLAYER{player}" and row.get("street_balance") == street for row in terminal) == 16 for player in (0, 1) for street in ("PREFLOP", "FLOP", "TURN", "RIVER")))
    payout_exact = True
    card_exact = True
    for row in terminal:
        payout = row.get("payout_cents", [])
        totals = row.get("totals", [])
        payout_exact &= len(payout) == 2 and sum(payout) == 0 and all(abs(int(x)) <= 20000 for x in payout)
        if row.get("terminal_kind") == "FOLD":
            folded = int(row["folded_player"])
            payout_exact &= payout[folded] == -totals[folded] and payout[1 - folded] == totals[folded]
        else:
            matched = min(totals)
            sign = int(row["comparator_sign"])
            expected = [matched, -matched] if sign > 0 else [-matched, matched] if sign < 0 else [0, 0]
            payout_exact &= payout == expected and len(row.get("board", [])) == 5
            cards = [*row.get("holes", [[], []])[0], *row.get("holes", [[], []])[1], *row.get("board", [])]
            card_exact &= len(cards) == len(set(cards)) == 9 and all(0 <= int(x) <= 51 for x in cards)
    check("terminal_payout_equations_exact", payout_exact)
    check("terminal_showdown_cards_exact", card_exact)
    check("resolutions_1280", len(resolutions) == 1280)
    nonfallback = [row for row in resolutions if not row.get("error_fallback")]
    fallback_rate = (len(resolutions) - len(nonfallback)) / max(1, len(resolutions))
    change_rate = sum(row.get("selected_slot") != row.get("baseline_slot") for row in nonfallback) / max(1, len(nonfallback))
    check("mc32_distinct_pairs", all(row.get("determinizations", {}).get("distinct_pair_count") == 32 for row in nonfallback))
    check("fallback_rate_le_0_02", fallback_rate <= .02, fallback_rate)
    check("change_rate_ge_0_01", change_rate >= .01, change_rate)
    check("repeats_192_exact", len(repeats) == 192 and all(row.get("exact") is True for row in repeats))
    check("faults_128_baseline_exact", len(faults) == 128 and all(row.get("baseline_exact") is True and row.get("error_fallback") is True for row in faults))

    metrics = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    recomputed = {
        "ledger_rows": len(ledger),
        "distinct_prefixes": len(prefixes),
        "hero_postflop_live_interfaces": len(live),
        "balanced_synthetic_states": len(synthetic),
        "terminal_utility_cells": len(cells),
        "terminal_utility_rows": len(terminal),
        "resolution_rows": len(resolutions),
        "repeat_rows": len(repeats),
        "repeat_exact": sum(bool(row.get("exact")) for row in repeats),
        "fault_rows": len(faults),
        "fault_baseline_exact": sum(bool(row.get("baseline_exact")) for row in faults),
        "fallback_rate": fallback_rate,
        "selected_slot_change_rate": change_rate,
    }
    check("metrics_recomputed_exact", all(metrics.get(key) == value for key, value in recomputed.items()), recomputed)
    registered_limits = {
        "p50": 2.5, "p95": 8.0, "p99": 15.0, "max": 20.0,
        "rss": 3072.0, "gpu": 1024.0, "wall": 1800.0, "projection": 12.0,
    }
    check("latency_limits", all(metrics["latency_seconds"][key] <= registered_limits[key] for key in ("p50", "p95", "p99", "max")), metrics["latency_seconds"])
    check("rss_limit", metrics["process_rss_mib"] <= registered_limits["rss"], metrics["process_rss_mib"])
    check("gpu_limit", metrics["gpu_peak_allocated_mib"] <= registered_limits["gpu"], metrics["gpu_peak_allocated_mib"])
    check("wall_limit", metrics["wall_seconds"] <= registered_limits["wall"], metrics["wall_seconds"])
    check("projection_limit", metrics["projected_quick5k_hours"] <= registered_limits["projection"], metrics["projected_quick5k_hours"])
    gates = result.get("gates", {})
    recomputed_all_pass = all(item["pass"] for item in checks) and all(gates.values())
    expected_classification = (
        "PASS / RS005_FULLY_LIVE_TERMINAL_UTILITY_QUALIFICATION_PASS"
        if all(gates.values())
        else "NONPASS / RS005_QUALIFICATION_GATE_NONPASS"
    )
    check("result_classification_exact", result.get("classification") == expected_classification)
    check("result_gate_count_exact", result.get("pass_count") == sum(gates.values()) and result.get("check_count") == len(gates))
    all_pass = all(item["pass"] for item in checks)
    audit_result = {
        "schema_version": "v5.rs005.qualification.result_audit.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS005_INDEPENDENT_RESULT_AUDIT_PASS"
            if all_pass
            else "FAIL_CLOSED / RS005_INDEPENDENT_RESULT_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "qualification_classification": result.get("classification"),
        "quick5k_authority": (
            "AUTHORIZED_LATER_SEPARATE_BOUNDARY"
            if all_pass and result.get("classification", "").startswith("PASS /")
            else "NONE"
        ),
        "network_or_slumbot_hands": 0,
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }
    write_exclusive(output_path, audit_result)
    return 0 if all_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--implementation-audit-sha256", required=True)
    args = parser.parse_args()
    return audit(Path(args.root), args.implementation_audit_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
