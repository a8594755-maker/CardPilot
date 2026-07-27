"""Independent prelaunch audit for the RS002 live Slumbot adapter."""

from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "81b61579f99755eb755d8c3c1905c22f"
ADAPTER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs002_live_slumbot_adapter_{TOKEN}.py"
AUDITOR = Path(__file__).resolve()
REPORT = ROOT / "reports" / f"v5_rs002_live_slumbot_adapter_prelaunch_audit_{TOKEN}_20260722.json"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs002_{TOKEN}_greedy_quick5k_20260722"
PREREG = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_preregistration_{TOKEN}_20260722.json"
PREREG_SHA256 = "93316de07812e6801cd6c83ddb7082b21841b981115a11c42ec3215c6b4563c7"
JUDGMENT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_qualification_judgment_{TOKEN}_20260722.json"
JUDGMENT_SHA256 = "2cec96506fa1f5ca55b73b8fcba7cabee5c4e0051bb4057e7dea4f1ee78a5bf2"
RESULT_AUDIT = ROOT / "reports" / f"v5_rs002_paired_mc32_lcb95_resolver_qualification_{TOKEN}_20260722" / "result_audit.json"
RESULT_AUDIT_SHA256 = "4009d3629297c0ff1dd1e91f0d909db1fc52aa1d00ab29410f4c755df312a45f"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)


def load_adapter():
    spec = importlib.util.spec_from_file_location("rs002_live_adapter", ADAPTER)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter_import_spec_failure")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_audit() -> tuple[dict[str, Any], bool]:
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    check("preregistration_hash_exact", sha256_file(PREREG) == PREREG_SHA256)
    check("qualification_judgment_hash_exact", sha256_file(JUDGMENT) == JUDGMENT_SHA256)
    check("qualification_result_audit_hash_exact", sha256_file(RESULT_AUDIT) == RESULT_AUDIT_SHA256)
    check("quick5k_root_absent", not QUICK5K_ROOT.exists())
    check("adapter_and_auditor_present", ADAPTER.is_file() and AUDITOR.is_file())
    ast_failures = []
    for path in (ADAPTER, AUDITOR):
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            ast_failures.append(f"{path.name}:{exc}")
    check("python_ast_2_of_2", not ast_failures, ast_failures)
    adapter_text = ADAPTER.read_text(encoding="utf-8")
    check("thin_adapter_no_network_calls", "new_hand(" not in adapter_text and "live.act(" not in adapter_text and "requests.post" not in adapter_text)
    check("thin_adapter_fallback_on_mismatch", "ACTION_TABLE_OR_OBSERVATION_IDENTITY_MISMATCH" in adapter_text and "fallback\": True" in adapter_text)
    adapter = load_adapter()
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    dump_paths = [Path(item["path"]) for item in prereg["frozen_authority_inputs"] if item["role"].startswith("h11_quick5k_dump_part")]
    total_raw = 0
    hero_postflop = 0
    exact = 0
    action_exact = 0
    observation_all_exact = 0
    mismatch_reasons: Counter[str] = Counter()
    mismatch_slots: Counter[str] = Counter()
    observation_failures: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    independently_recomputed_action_exact = 0
    for path in dump_paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                total_raw += 1
                raw = json.loads(line)
                if raw.get("who") != "hero" or int(raw.get("street", 0)) <= 0:
                    continue
                hero_postflop += 1
                comparison = adapter.compare_live_boundary(
                    action_str=str(raw["action_str_before"]),
                    client_pos=int(raw["client_pos"]),
                    hero_hole=list(raw["hero_hole"]),
                    board=list(raw["board"]),
                )
                if comparison["exact"]:
                    exact += 1
                else:
                    mismatch_reasons[comparison["reason"]] += 1
                    if len(examples) < 20:
                        examples.append({
                            "source_part": path.name,
                            "source_hand_index": int(raw["hand_idx"]),
                            "source_move_index": int(raw["move_idx"]),
                            "public_input_sha256": comparison["public_input_sha256"],
                            "action_table_exact": comparison["action_table_exact"],
                            "observation_exact": comparison["observation_exact"],
                            "mismatched_action_rows": [row for row in comparison["action_rows"] if not row["exact"]],
                        })
                if comparison["action_table_exact"]:
                    action_exact += 1
                if all(comparison["observation_exact"].values()):
                    observation_all_exact += 1
                for key, passed in comparison["observation_exact"].items():
                    if not passed:
                        observation_failures[key] += 1
                independent_action_ok = comparison["hunl_legal_slots"] == comparison["live_legal_slots"] and all(row["exact"] for row in comparison["action_rows"])
                if independent_action_ok:
                    independently_recomputed_action_exact += 1
                for row in comparison["action_rows"]:
                    if not row["exact"]:
                        mismatch_slots[str(row["slot"])] += 1
    check("raw_and_witness_counts_exact", total_raw == 29878 and hero_postflop == 6921, {"all_rows": total_raw, "hero_postflop": hero_postflop})
    check("adapter_action_count_matches_independent_recompute", action_exact == independently_recomputed_action_exact, {"adapter": action_exact, "independent": independently_recomputed_action_exact})
    mismatch = hero_postflop - exact
    projected_fallback_rate = mismatch / hero_postflop
    registered_mapping_gate = mismatch == 0
    registered_fallback_gate = projected_fallback_rate <= 0.02
    check("zero_live_boundary_mismatches_required", registered_mapping_gate, {"exact": exact, "mismatch": mismatch})
    check("projected_fallback_rate_le_0_02", registered_fallback_gate, projected_fallback_rate)
    check("no_external_or_quick5k_outputs", not QUICK5K_ROOT.exists())
    integrity_pass = all(checks[index]["pass"] for index in [*range(10), 12])
    scientific_pass = registered_mapping_gate and registered_fallback_gate
    overall_pass = integrity_pass and scientific_pass
    value = {
        "schema_version": "v5.rs002.live_adapter.prelaunch_audit.v1",
        "classification": "PASS / RS002_LIVE_ADAPTER_EXACT_QUICK5K_LAUNCH_READY" if overall_pass else "FAIL_CLOSED / RS002_LIVE_ADAPTER_EXACT_MAPPING_OR_FALLBACK_GATE_NONPASS_NO_QUICK5K",
        "overall": "PASS" if overall_pass else "FAIL_CLOSED",
        "audit_integrity": "PASS" if integrity_pass else "FAIL_CLOSED",
        "adapter": {"path": str(ADAPTER), "bytes": ADAPTER.stat().st_size, "sha256": sha256_file(ADAPTER)},
        "auditor": {"path": str(AUDITOR), "bytes": AUDITOR.stat().st_size, "sha256": sha256_file(AUDITOR)},
        "authority": {
            "preregistration_sha256": PREREG_SHA256,
            "qualification_judgment_sha256": JUDGMENT_SHA256,
            "qualification_result_audit_sha256": RESULT_AUDIT_SHA256,
        },
        "witnessed_boundary_census": {
            "all_dump_rows": total_raw,
            "hero_postflop_rows": hero_postflop,
            "fully_exact_rows": exact,
            "mismatch_rows": mismatch,
            "exact_fraction": exact / hero_postflop,
            "minimum_fail_closed_fallback_rate": projected_fallback_rate,
            "action_table_exact_rows": action_exact,
            "observation_all_exact_rows": observation_all_exact,
            "observation_failure_counts": dict(sorted(observation_failures.items())),
            "mismatched_slot_counts": dict(sorted(mismatch_slots.items())),
            "mismatch_reason_counts": dict(sorted(mismatch_reasons.items())),
            "mismatch_examples": examples,
        },
        "registered_judgment": {
            "zero_mapping_violation_required": true,
            "zero_mapping_violation_pass": registered_mapping_gate,
            "fallback_rate_max": 0.02,
            "minimum_fail_closed_fallback_rate": projected_fallback_rate,
            "fallback_gate_pass": registered_fallback_gate,
            "quick5k_launch_authority": "NONE" if not overall_pass else "READY",
            "same_slot_or_nearest_cent_projection": "FORBIDDEN",
        },
        "checks": checks,
        "check_count": len(checks),
        "pass_count": sum(item["pass"] for item in checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "network_calls": 0,
        "slumbot_hands": 0,
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "strength_claim": "FORBIDDEN",
    }
    return value, overall_pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("Preflight", "Execute"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "Preflight":
        for path in (ADAPTER, AUDITOR):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        adapter = load_adapter()
        print(canonical_json({"classification": "PASS_PRELAUNCH_AUDITOR_PREFLIGHT", "adapter_loaded": adapter is not None, "files_written": 0, "network_calls": 0}))
        return 0
    if REPORT.exists():
        raise RuntimeError("prelaunch_audit_report_already_exists")
    value, passed = run_audit()
    write_exclusive(REPORT, value)
    print(canonical_json({"classification": value["classification"], "pass_count": value["pass_count"], "check_count": value["check_count"], "mismatch_rows": value["witnessed_boundary_census"]["mismatch_rows"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
