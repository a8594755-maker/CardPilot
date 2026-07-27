"""Independent RS005 implementation audit and exactly-two probe owner."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "5a01b095e04a242d79f0a20907a3e6f9"
IDENTITY = "5a01b095e04a242d79f0a20907a3e6f9d59c61780cf9a73765138cdb1f205bde"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_audit_{TOKEN}_20260723.json"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs005_fully_live_terminal_utility_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs005_fully_live_terminal_utility_launcher_{TOKEN}.ps1"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs005_fully_live_terminal_utility_audit_{TOKEN}.py"
THIS_FILE = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_qualification_{TOKEN}_20260723"
QUICK5K_ROOT = ROOT / "models" / f"bench_v55_rs005_{TOKEN}_greedy_quick5k_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"

EXPECTED = {
    PREREG: (22175, "70a232c8cbbef807e2530ba19e35f887b143d9e0f226cd443385d04e9a0a0c8c"),
    PREREG_AUDIT: (13101, "7f6b4800a7c22588f01fc02f8b1c632d8496fc2737fc8c0187faa39943d735c4"),
    RUNNER: (49471, "fc8ff1d434bb103293d0ddba50b189a0ce0172ab9a915ea06c6a8a73f34ca370"),
    LAUNCHER: (1837, "ffc27b6db951f3b2780376cb3d903e09baeae0436c069cf65e38bb0feab11dd5"),
    RESULT_AUDITOR: (12070, "759a7513eb53074b6559a9e90c3e9a424a0e5b172c0124312779ff7001063bd7"),
    PYTHON: (104952, "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
}
PROBES = ("RS005_PROBE_A_2034972297", "RS005_PROBE_B_2035972297")
SELFTEST_NONCE = "RS005_SELFTEST_2033972297"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json_line(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("{"):
            return json.loads(line)
    raise RuntimeError("child_json_missing")


def snapshot() -> dict[str, Any]:
    files = {}
    for base in (ROOT / "reports", ROOT / "scripts" / "alpha_holdem", ROOT / "models"):
        for path in base.rglob(f"*{TOKEN}*"):
            if path.is_file() and path.resolve() != RESULT.resolve():
                files[str(path.resolve())] = {"bytes": path.stat().st_size, "sha256": sha_file(path)}
    return {
        "files": dict(sorted(files.items())),
        "qualification_root_exists": QUAL_ROOT.exists(),
        "quick5k_root_exists": QUICK5K_ROOT.exists(),
        "implementation_result_exists": RESULT.exists(),
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }


def independent_census(prereg: dict[str, Any]) -> dict[str, Any]:
    by_hand: dict[tuple[str, int], list[int]] = defaultdict(list)
    prefixes, rows, hero_postflop = set(), 0, 0
    sources = [
        Path(item["path"])
        for item in prereg["frozen_authority_inputs"]
        if item["role"].startswith("h11_dump_part")
    ]
    for path in sources:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                rows += 1
                by_hand[(str(path.resolve()), int(raw["hand_idx"]))].append(int(raw["move_idx"]))
                prefixes.add(str(raw["action_str_before"]))
                hero_postflop += int(raw["who"] == "hero" and int(raw["street"]) > 0)
    contiguous = True
    transitions = 0
    for values in by_hand.values():
        values.sort()
        contiguous &= values == list(range(len(values)))
        transitions += max(0, len(values) - 1)
    return {
        "dump_files": len(sources), "ledger_rows": rows, "source_scoped_hands": len(by_hand),
        "distinct_prefixes": len(prefixes), "adjacent_transitions": transitions,
        "hero_postflop_live_interfaces": hero_postflop, "move_indices_contiguous": contiguous,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    if RESULT.exists() or QUAL_ROOT.exists() or QUICK5K_ROOT.exists():
        raise RuntimeError("fresh_output_boundary_failure")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, (size, expected_sha) in EXPECTED.items():
        check(
            f"bound_file_exact:{path.name}",
            path.is_file() and path.stat().st_size == size and sha_file(path) == expected_sha,
            {"bytes": size, "sha256": expected_sha},
        )
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check("identity_exact", prereg["identity"]["sha256"] == IDENTITY and prereg["identity"]["token"] == TOKEN)
    check("preregistration_audit_pass", prereg_audit.get("classification") == "PASS / RS005_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY")
    failed_inputs = []
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            failed_inputs.append(item["role"])
    check("all26_frozen_inputs_exact", len(prereg["frozen_authority_inputs"]) == 26 and not failed_inputs, failed_inputs)
    census = independent_census(prereg)
    check("source_scoped_census_exact", census == {
        "dump_files": 4, "ledger_rows": 29878, "source_scoped_hands": 5000,
        "distinct_prefixes": 584, "adjacent_transitions": 24878,
        "hero_postflop_live_interfaces": 6921, "move_indices_contiguous": True,
    }, census)
    check("four_fresh_files_present", all(path.is_file() for path in (RUNNER, LAUNCHER, RESULT_AUDITOR, THIS_FILE)))

    syntax_errors = []
    trees = {}
    for path in (RUNNER, RESULT_AUDITOR, THIS_FILE):
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}:{exc}")
    check("python_ast_3_of_3", not syntax_errors, syntax_errors)
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
    }
    check("forbidden_symbols_absent", not (names & forbidden_names), sorted(names & forbidden_names))
    deep_imports = [value for value in imports if value.startswith("deep_cfr")]
    check("only_pure_comparator_deep_import", deep_imports and set(deep_imports) == {"deep_cfr.hand_eval"}, deep_imports)
    runner_text = RUNNER.read_text(encoding="utf-8")
    science_markers = (
        "class FullyLiveState", "def apply_increment", "def action_table",
        "def _deal_to", "def _settle", "def terminal_cohort", "def determinizations",
        "def paired_stats", "PAIRED_LCB95_POSITIVE", "LCB_NO_CHANGE",
        "uncalled_refund_exact", "comparator_checks", "validate_adjacent_transitions",
    )
    check("science_markers_complete", all(marker in runner_text for marker in science_markers), [x for x in science_markers if x not in runner_text])
    check("no_rs004_runtime_dependency", "v5_rs004_live_native_paired_mc32" not in runner_text)
    check("no_network_execution", "requests.post" not in runner_text and "slumbot.com" not in runner_text)
    check("qualification_limits_frozen", all(marker in runner_text for marker in (
        '["p50"] <= 2.5', '["p95"] <= 8', '["p99"] <= 15', '["max"] <= 20',
        '["process_rss_mib"] <= 3072', '["gpu_peak_allocated_mib"] <= 1024',
        '["wall_seconds"] <= 1800',
    )))
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    launcher_markers = (
        str(PYTHON), str(RUNNER), str(RESULT_AUDITOR), str(QUAL_ROOT),
        "$env:CUDA_VISIBLE_DEVICES = '0'",
        "$env:RS005_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'",
        "$env:PYTHONDONTWRITEBYTECODE = '1'",
    )
    check("launcher_absolute_boundary", all(marker in launcher_text for marker in launcher_markers), [x for x in launcher_markers if x not in launcher_text])
    escaped = str(LAUNCHER).replace("'", "''")
    ps_parse = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}else{{'PASS'}}"],
        capture_output=True, text=True, timeout=60,
    )
    check("powershell_parse_pass", ps_parse.returncode == 0 and "PASS" in ps_parse.stdout, {"stdout": ps_parse.stdout, "stderr": ps_parse.stderr})
    check("future_outputs_fresh", not RESULT.exists() and not QUAL_ROOT.exists() and not QUICK5K_ROOT.exists())

    before = snapshot()
    selftest = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
         "-Mode", "SelfTest", "-Nonce", SELFTEST_NONCE, "-Level", "deep"],
        capture_output=True, text=True, timeout=600,
    )
    try:
        selftest_json = parse_json_line(selftest.stdout)
    except Exception as exc:
        selftest_json = {"parse_error": str(exc)}
    check("deep_self_test_exit0", selftest.returncode == 0, {"stdout": selftest.stdout[-4000:], "stderr": selftest.stderr[-4000:]})
    check("deep_self_test_pass", selftest_json.get("classification") == "RS005_DEEP_SELF_TEST_PASS" and selftest_json.get("files_written") == 0, selftest_json)

    probe_results = []
    for nonce in PROBES:
        child = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
             "-Mode", "ContractProbe", "-Nonce", nonce],
            capture_output=True, text=True, timeout=300,
        )
        try:
            payload = parse_json_line(child.stdout)
        except Exception as exc:
            payload = {"parse_error": str(exc)}
        probe_results.append({
            "nonce": nonce, "exit_code": child.returncode, "payload": payload,
            "stdout": child.stdout[-2000:], "stderr": child.stderr[-2000:],
        })
    after = snapshot()
    check("exactly_two_launcher_probes", len(probe_results) == 2 and [x["nonce"] for x in probe_results] == list(PROBES))
    for index, item in enumerate(probe_results):
        payload = item["payload"]
        check(f"probe_{index + 1}_exit0", item["exit_code"] == 0, item)
        check(
            f"probe_{index + 1}_contract_exact",
            payload.get("classification") == "RS005_CONTRACT_PROBE_PASS"
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
    all_pass = all(item["pass"] for item in checks)
    value = {
        "schema_version": "v5.rs005.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS005_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
            if all_pass else "FAIL_CLOSED / RS005_IMPLEMENTATION_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "bound_files": {
            str(path): {"bytes": path.stat().st_size, "sha256": sha_file(path)}
            for path in (PREREG, PREREG_AUDIT, RUNNER, LAUNCHER, RESULT_AUDITOR, THIS_FILE, PYTHON, CHECKPOINT)
        },
        "census": census,
        "deep_self_test": selftest_json,
        "contract_probes": probe_results,
        "snapshot_before": before,
        "snapshot_after": after,
        "qualification_authority": "ONE_ATTEMPT" if all_pass else "NONE",
        "quick5k_authority": "NONE",
        "network_or_slumbot_hands": 0,
    }
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
