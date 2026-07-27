"""Independent RS007 implementation audit and sole self-test/probe owner."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "bf43f304c4709f356af131d60ef6e35a"
IDENTITY = "bf43f304c4709f356af131d60ef6e35a52a7456d215987abce8180419c4ed6d0"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_preregistration_audit_{TOKEN}_20260723.json"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_launcher_{TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs007_dual_domain_fully_live_resolver_audit_{TOKEN}.py"
THIS_FILE = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs007_dual_domain_fully_live_resolver_qualification_{TOKEN}_20260723"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs007_{TOKEN}_greedy_quick5k_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"

EXPECTED = {
    PREREG: (21218, "0b881b6b5651a23dea03f625cb0e8d4880752e5286f7f2cd145eda46980beeeb"),
    PREREG_AUDIT: (9251, "aa0f6582ac80a814f7d116a736d245440121ddcf1cc46b126a0adf67adff7a97"),
    RUNNER: (64961, "049d779556fd89fc0e93f5bbb32f5e1a1a9594372cece2dcfa0c526ba46a5e94"),
    LAUNCHER: (1848, "c91f91397e770af5d2cd0c684c778944720e9b374743603065d618e976f74477"),
    RESULT_AUDITOR: (13133, "bce42611096975a958ac4bcd131b2fcca355a771f9fd26749d285d7685e9d4ba"),
    PYTHON: (104952, "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
}
PROBES = ("RS007_PROBE_A_2034972299", "RS007_PROBE_B_2035972299")
SELFTEST = "RS007_SELFTEST_2033972299"
SCENARIOS = (
    "CHECK_OPEN", "CHECK_CLOSE", "CALL_CLOSE", "FOLD",
    "FULL_OPEN_MINIMUM", "FULL_OPEN_ABOVE_MINIMUM",
    "FULL_RAISE_MINIMUM", "FULL_RAISE_ABOVE_MINIMUM",
    "SHORT_ALLIN_OPEN", "SHORT_ALLIN_RAISE_NO_REOPEN",
    "FULL_RAISE_REOPENS", "RAISE_RIGHT_CLOSED_REJECT",
    "OPPONENT_ALLIN_RAISE_REJECT", "UNDER_MINIMUM_NONALLIN_REJECT",
    "OVERSTACK_REJECT", "POSTTERMINAL_REJECT",
)
RAISE_FRACTIONS = (0.33, 0.50, 0.67, 0.75, 1.00, 1.50)
PREFLOP_FRACTIONS = (0.50, 1.00, 1.50)


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def last_json(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_json_missing")


def snapshot() -> dict[str, Any]:
    files = {}
    for base in (ROOT / "reports", ROOT / "scripts" / "alpha_holdem", ROOT / "models"):
        for path in base.rglob(f"*{TOKEN}*"):
            if path.is_file() and path.resolve() != RESULT.resolve():
                files[str(path.resolve())] = {
                    "bytes": path.stat().st_size,
                    "sha256": sha_file(path),
                }
    return {
        "files": dict(sorted(files.items())),
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "implementation_result_exists": RESULT.exists(),
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }


def source_action_table(row: dict[str, Any]) -> list[str | None]:
    """Independent reproduction of the frozen live V5.5 sparse action table."""
    facing = int(row["last_bet_size"]) > 0
    total_bet = int(row["total_last_bet_to"])
    street_bet = int(row["street_last_bet_to"])
    last_bet = int(row["last_bet_size"])
    if facing:
        mover_total = max(total_bet - last_bet, 0)
        opponent_total = total_bet
        mover_street = max(street_bet - last_bet, 0)
        opponent_street = street_bet
        to_call = last_bet
    else:
        mover_total = opponent_total = total_bet
        mover_street = opponent_street = street_bet
        to_call = 0
    pot = max(mover_total + opponent_total, 1)
    stack = max(20000 - mover_total, 0)
    table: list[str | None] = [None] * 9
    distance = [float("inf")] * 9
    if facing:
        table[0] = "f"
    table[1] = "c" if facing else "k"
    if stack <= to_call:
        return table
    maximum = 20000 - (mover_total - mover_street)
    if maximum <= street_bet:
        return table
    fractions = PREFLOP_FRACTIONS if int(row["street"]) == 0 else RAISE_FRACTIONS
    minimum = street_bet + max(last_bet, 100)
    for fraction in fractions:
        target = street_bet + int((pot + to_call if facing else pot) * fraction)
        target = max(target, minimum)
        if target >= maximum:
            continue
        slot = min(range(2, 8), key=lambda index: abs(target / pot - RAISE_FRACTIONS[index - 2]))
        candidate_distance = abs(target - RAISE_FRACTIONS[slot - 2] * pot)
        if candidate_distance < distance[slot]:
            table[slot] = f"b{target}"
            distance[slot] = candidate_distance
    table[8] = f"b{maximum}"
    if len([value for value in table if value is not None]) != len(set(value for value in table if value is not None)):
        raise RuntimeError("independent_table_collision")
    return table


def independent_census(prereg: dict[str, Any]) -> dict[str, Any]:
    by_hand: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    prefixes: set[str] = set()
    counts: dict[str, int] = defaultdict(int)
    for item in prereg["frozen_authority_inputs"]:
        if not item["role"].startswith("h11_dump_part"):
            continue
        source = str(Path(item["path"]).resolve())
        with Path(item["path"]).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                by_hand[(source, int(row["hand_idx"]))].append(row)
                prefixes.add(str(row["action_str_before"]))
                counts["rows"] += 1
                counts["hero"] += int(row["who"] == "hero")
                counts["opponent"] += int(row["who"] == "opp")
                counts["hero_postflop"] += int(row["who"] == "hero" and int(row["street"]) > 0)
                increment = f"b{int(row['action_amount'])}" if row["action_move"] == "b" else str(row["action_move"])
                table = source_action_table(row)
                matches = sum(value == increment for value in table)
                if matches > 1:
                    raise RuntimeError("independent_source_collision")
                counts["in_slot"] += int(matches == 1)
                counts["external"] += int(matches == 0)
                counts["hero_slot"] += int(row["who"] == "hero" and matches == 1)
                counts["opponent_slot"] += int(row["who"] == "opp" and matches == 1)
                counts["opponent_external"] += int(row["who"] == "opp" and matches == 0)
                if row["action_move"] == "b":
                    facing = int(row["to_call"]) > 0
                    mover_street = int(row["street_last_bet_to"]) - int(row["to_call"]) if facing else int(row["street_last_bet_to"])
                    maximum = mover_street + int(row["stack_remaining"])
                    threshold = int(row["street_last_bet_to"]) + max(int(row["last_bet_size"]), 100)
                    short_allin = int(row["action_amount"]) == maximum and int(row["action_amount"]) < threshold
                    counts["short_allin_open"] += int(short_allin and not facing)
                    counts["short_allin_raise"] += int(short_allin and facing)
    contiguous = True
    adjacent = 0
    for rows in by_hand.values():
        indices = sorted(int(row["move_idx"]) for row in rows)
        contiguous &= indices == list(range(len(indices)))
        adjacent += max(0, len(indices) - 1)
    return {
        **dict(counts),
        "hands": len(by_hand),
        "prefixes": len(prefixes),
        "adjacent": adjacent,
        "contiguous": int(contiguous),
    }


def method_source(tree: ast.Module, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.unparse(node)
    raise RuntimeError(f"method_missing:{name}")


def write_result(checks: list[dict[str, Any]], extra: dict[str, Any]) -> int:
    passed = all(item["pass"] for item in checks)
    value = {
        "schema_version": "v5.rs007.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
            if passed else "FAIL_CLOSED / RS007_IMPLEMENTATION_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "bound_files": {
            str(path): {"bytes": path.stat().st_size, "sha256": sha_file(path)}
            for path in (PREREG, PREREG_AUDIT, RUNNER, LAUNCHER, RESULT_AUDITOR, THIS_FILE, PYTHON, CHECKPOINT)
            if path.is_file()
        },
        **extra,
        "qualification_authority": "ONE_ATTEMPT" if passed else "NONE",
        "quick5k_authority": "NONE",
        "network_or_slumbot_hands": 0,
    }
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


def main() -> int:
    argparse.ArgumentParser().parse_args()
    if RESULT.exists() or QUAL_ROOT.exists() or QUICK5K_ROOT.exists():
        raise RuntimeError("fresh_output_boundary_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, expected_sha) in EXPECTED.items():
        observed = {
            "exists": path.is_file(),
            "bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha_file(path) if path.is_file() else None,
        }
        check(
            f"bound_file_exact:{path.name}",
            observed["exists"] and observed["bytes"] == size and observed["sha256"] == expected_sha,
            observed,
        )
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check("identity_exact", prereg["identity"] == {
        "basis": prereg["identity"]["basis"],
        "sha256": IDENTITY,
        "token": TOKEN,
        "token_rule": "FIRST_32_LOWERCASE_HEX",
        "collision_rule": "ONE_CONTENT_ADDRESSED_RS007_CHAIN_ONLY",
    })
    check(
        "preregistration_audit_pass",
        prereg_audit.get("classification")
        == "PASS / RS007_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY",
    )
    failed_inputs = []
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            failed_inputs.append(item["role"])
    check("all22_frozen_inputs_exact", len(prereg["frozen_authority_inputs"]) == 22 and not failed_inputs, failed_inputs)
    census = independent_census(prereg)
    expected_census = {
        "rows": 29878, "hero": 12564, "opponent": 17314, "hero_postflop": 6921,
        "in_slot": 28220, "external": 1658, "hero_slot": 12564,
        "opponent_slot": 15656, "opponent_external": 1658,
        "short_allin_open": 0, "short_allin_raise": 19,
        "hands": 5000, "prefixes": 584, "adjacent": 24878, "contiguous": 1,
    }
    check("independent_source_census_exact", census == expected_census, {"observed": census, "expected": expected_census})
    check("four_fresh_files_present", all(path.is_file() for path in (RUNNER, LAUNCHER, RESULT_AUDITOR, THIS_FILE)))

    trees: dict[Path, ast.Module] = {}
    syntax_errors = []
    for path in (RUNNER, RESULT_AUDITOR, THIS_FILE):
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}:{exc}")
    check("python_ast_3_of_3", not syntax_errors, syntax_errors)
    if syntax_errors:
        return write_result(checks, {
            "census": census, "deep_self_test": None, "contract_probes": [],
            "snapshot_before": None, "snapshot_after": None,
        })
    runner_tree = trees[RUNNER]
    imports = []
    names = set()
    for node in ast.walk(runner_tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            names.add(node.name)
    forbidden_names = {
        "HUNLGameState", "GameConfig", "Action", "ActionType", "Street",
        "mirror_from_ledger", "mirror_action_for_increment", "assert_mirror_public",
        "importlib", "monkeypatch",
    }
    check("forbidden_symbols_absent", not (names & forbidden_names), sorted(names & forbidden_names))
    deep_imports = [value for value in imports if value.startswith("deep_cfr")]
    check("only_pure_comparator_deep_import", deep_imports and set(deep_imports) == {"deep_cfr.hand_eval"}, deep_imports)
    runner_text = RUNNER.read_text(encoding="utf-8")
    check("no_rs005_rs006_dependency", not re.search(r"v5_rs00[56]|RS00[56]", runner_text))
    check("no_network_execution", "requests.post" not in runner_text and "slumbot.com" not in runner_text)
    public_source = method_source(runner_tree, "apply_public_increment")
    policy_source = method_source(runner_tree, "apply_policy_slot")
    check("public_api_policy_independent", "policy_table" not in public_source and "apply_policy_slot" not in public_source)
    check(
        "policy_api_exact_delegate",
        "self.policy_table()" in policy_source
        and 'self.apply_public_increment(increment, "POLICY_SLOT")' in policy_source,
    )
    science_markers = (
        "class DualDomainState", "def public_legality", "def apply_public_increment",
        "def apply_policy_slot", "def source_transition_evidence", "def boundary_matrix",
        "SHORT_ALLIN_RAISE_NO_REOPEN", "FULL_RAISE_REOPENS",
        "OPPONENT_ALLIN_RAISE_REJECT", "def terminal_utility_rows",
        "def comparator_evidence", "def determinizations", "def paired_statistics",
        "PAIRED_LCB95_POSITIVE", "LCB_NO_CHANGE",
    )
    check("science_markers_complete", all(marker in runner_text for marker in science_markers), [m for m in science_markers if m not in runner_text])
    check("boundary_domain_exact", len(SCENARIOS) * 4 * 2 * 32 == 4096 and all(repr(name) in runner_text or f'"{name}"' in runner_text for name in SCENARIOS))
    check("qualification_limits_frozen", all(marker in runner_text for marker in (
        '["p50"] <= 2.5', '["p95"] <= 8', '["p99"] <= 15', '["max"] <= 20',
        '["process_rss_mib"] <= 3072', '["gpu_peak_allocated_mib"] <= 1024',
        '["wall_seconds"] <= 1800', '["projected_quick5k_hours"] <= 12',
    )))
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    launcher_markers = (
        str(PYTHON), str(RUNNER), str(RESULT_AUDITOR), str(QUAL_ROOT),
        "$env:CUDA_VISIBLE_DEVICES = '0'",
        "$env:RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'",
        "$env:PYTHONDONTWRITEBYTECODE = '1'",
        "$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'",
    )
    check("launcher_absolute_boundary", all(marker in launcher_text for marker in launcher_markers), [m for m in launcher_markers if m not in launcher_text])
    escaped = str(LAUNCHER).replace("'", "''")
    parsed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}else{{'PASS'}}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    check("powershell_parse_pass", parsed.returncode == 0 and "PASS" in parsed.stdout, {"stdout": parsed.stdout, "stderr": parsed.stderr})
    check("future_outputs_fresh", not RESULT.exists() and not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists())
    if not all(item["pass"] for item in checks):
        return write_result(checks, {
            "census": census, "deep_self_test": None, "contract_probes": [],
            "snapshot_before": snapshot(), "snapshot_after": snapshot(),
        })

    before = snapshot()
    selftest_child = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER), "-Mode", "SelfTest",
            "-Nonce", SELFTEST, "-Level", "deep",
        ],
        capture_output=True, text=True, timeout=600,
    )
    try:
        selftest_json = last_json(selftest_child.stdout)
    except Exception as exc:
        selftest_json = {"parse_error": str(exc)}
    check("one_deep_selftest_exit0", selftest_child.returncode == 0, {
        "stdout": selftest_child.stdout[-4000:], "stderr": selftest_child.stderr[-4000:],
    })
    expected_source = {
        "rows": 29878, "adjacent": 24878, "hero": 12564, "opponent": 17314,
        "in_slot": 28220, "external": 1658, "hero_slot": 12564,
        "opponent_slot": 15656, "opponent_external": 1658,
        "dual_path_exact": 12564, "hands": 5000, "prefixes": 584, "contiguous": 1,
    }
    self_checks = selftest_json.get("checks", {})
    check(
        "deep_selftest_exact_pass",
        selftest_json.get("classification") == "RS007_DEEP_SELFTEST_PASS"
        and selftest_json.get("level") == "deep"
        and selftest_json.get("files_written") == 0
        and self_checks.get("source_transition_rows") == 29878
        and self_checks.get("source_counters") == expected_source
        and self_checks.get("boundary_rows") == 4096
        and self_checks.get("boundary_cells") == 128
        and self_checks.get("terminal_rows") == 1280
        and self_checks.get("terminal_cells") == 20
        and self_checks.get("terminal_exact") is True
        and all(value == 8192 for value in self_checks.get("comparator", {}).values()),
        selftest_json,
    )

    probe_results = []
    for nonce in PROBES:
        child = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(LAUNCHER), "-Mode", "ContractProbe", "-Nonce", nonce,
            ],
            capture_output=True, text=True, timeout=300,
        )
        try:
            payload = last_json(child.stdout)
        except Exception as exc:
            payload = {"parse_error": str(exc)}
        probe_results.append({
            "nonce": nonce,
            "exit_code": child.returncode,
            "payload": payload,
            "stdout": child.stdout[-2000:],
            "stderr": child.stderr[-2000:],
        })
    after = snapshot()
    check("exactly_two_launcher_probes", [item["nonce"] for item in probe_results] == list(PROBES))
    for index, item in enumerate(probe_results):
        payload = item["payload"]
        check(f"probe_{index + 1}_exit0", item["exit_code"] == 0, item)
        check(
            f"probe_{index + 1}_contract_exact",
            payload.get("classification") == "RS007_CONTRACT_PROBE_PASS"
            and payload.get("identity_sha256") == IDENTITY
            and payload.get("nonce") == PROBES[index]
            and payload.get("device_mode") == "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK"
            and payload.get("cuda_visible_devices") == "0"
            and payload.get("torch_imported") is False
            and payload.get("files_written") == 0,
            payload,
        )
    check("selftest_and_probes_zero_file_diff", before == after, {"before": before, "after": after})
    check("checkpoint_unchanged_after_children", sha_file(CHECKPOINT) == EXPECTED[CHECKPOINT][1])
    return write_result(checks, {
        "census": census,
        "deep_self_test": {
            "exit_code": selftest_child.returncode,
            "payload": selftest_json,
            "stdout": selftest_child.stdout[-4000:],
            "stderr": selftest_child.stderr[-4000:],
        },
        "contract_probes": probe_results,
        "snapshot_before": before,
        "snapshot_after": after,
    })


if __name__ == "__main__":
    raise SystemExit(main())
