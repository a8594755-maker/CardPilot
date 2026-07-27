"""Independent RS009 materialization audit and sole final-launcher probe owner."""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "72e9bb6b8a4f4618aa6657710b66c5c9"
IDENTITY = "72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4"
PYTHON = Path(r"C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe")
PREREG = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_audit_{TOKEN}_20260723.json"
PARENT_RUNNER = ROOT / "scripts" / "alpha_holdem" / "v5_rs007_dual_domain_fully_live_resolver_bf43f304c4709f356af131d60ef6e35a.py"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_direct_materialized_resolver_{TOKEN}.py"
PARENT_RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / "v5_rs007_dual_domain_fully_live_resolver_audit_bf43f304c4709f356af131d60ef6e35a.py"
RESULT_AUDITOR = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_direct_materialized_resolver_audit_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs009_direct_materialized_resolver_launcher_{TOKEN}.ps1"
THIS_FILE = Path(__file__).resolve()
RESULT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_qualification_{TOKEN}_20260723"
QUICK_ROOT = ROOT / "models" / f"bench_v55_rs009_{TOKEN}_greedy_quick5k_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
RS007C1_PASS = ROOT / "reports" / "v5_rs007c1_quote_insensitive_implementation_audit_ac09e2283fc6459f887b83e1d1e22b6d_20260723.json"
PROBE_NONCE = "RS009_FINAL_IMPORT_PROBE_2034972301"

EXPECTED = {
    PREREG: (14797, "54b081b37171449d782b6b64ffaf84e9c553eea2c0bae426a00533790d229aea"),
    PREREG_AUDIT: (7135, "4d22631cdb6d58d8a4a3d543daf4fe30f0aa9ea474214af4336e7796963465c6"),
    PARENT_RUNNER: (64961, "049d779556fd89fc0e93f5bbb32f5e1a1a9594372cece2dcfa0c526ba46a5e94"),
    RUNNER: (65017, "8c764d35c1fe5eefd28bcf2173c1181504b8b33242d8d50d8d89a43acb97780f"),
    PARENT_RESULT_AUDITOR: (13133, "bce42611096975a958ac4bcd131b2fcca355a771f9fd26749d285d7685e9d4ba"),
    RESULT_AUDITOR: (13121, "10c7f8b4912bdcb956880889c35f137f460aac62797e7e79909f2cb17a36cc48"),
    LAUNCHER: (1644, "120e9bad1df9fcee366bc168f7819e918beb5359c48bae487b0ee01559fa5044"),
    PYTHON: (104952, "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a"),
    CHECKPOINT: (261417230, "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"),
    RS007C1_PASS: (28246, "bccb55981fd8bcce4388c73b5fbee200385dd9d6b8f25f961652be494b0a2804"),
}
RUNNER_CONTROL = {
    "TOKEN", "IDENTITY", "PREREG", "PREREG_SHA", "PREREG_AUDIT",
    "PREREG_AUDIT_SHA", "IMPL_AUDIT", "QUAL_ROOT",
}
AUDITOR_CONTROL = {"TOKEN", "IDENTITY", "PREREG", "PREREG_AUDIT", "IMPL_AUDIT", "QUAL_ROOT"}


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


def top_assignments(tree: ast.Module) -> dict[str, list[ast.Assign]]:
    output: dict[str, list[ast.Assign]] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            output.setdefault(node.targets[0].id, []).append(node)
    return output


class RunnerNormalizer(ast.NodeTransformer):
    def __init__(self, candidate: bool):
        self.candidate = candidate

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = [
            item for item in node.body
            if not (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id in {"PREREG_BYTES", "PREREG_AUDIT_BYTES"}
            )
        ]
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node = self.generic_visit(node)
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in RUNNER_CONTROL
        ):
            node.value = ast.Constant(value="CONTROL")
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not self.candidate and node.value == 21218:
            return ast.copy_location(ast.Name(id="SIZE_PREREG", ctx=ast.Load()), node)
        if not self.candidate and node.value == 9251:
            return ast.copy_location(ast.Name(id="SIZE_AUDIT", ctx=ast.Load()), node)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if self.candidate and isinstance(node.ctx, ast.Load) and node.id == "PREREG_BYTES":
            return ast.copy_location(ast.Name(id="SIZE_PREREG", ctx=ast.Load()), node)
        if self.candidate and isinstance(node.ctx, ast.Load) and node.id == "PREREG_AUDIT_BYTES":
            return ast.copy_location(ast.Name(id="SIZE_AUDIT", ctx=ast.Load()), node)
        return node


def normalize_result_auditor(tree: ast.Module) -> ast.Module:
    value = copy.deepcopy(tree)
    for node in value.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in AUDITOR_CONTROL
        ):
            node.value = ast.Constant(value="CONTROL")
    return ast.fix_missing_locations(value)


def forbidden_runtime(tree: ast.Module) -> dict[str, Any]:
    imports, calls, sys_writes = [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                alias.name for alias in node.names
                if alias.name in {"importlib", "runpy"} or alias.name.startswith(("importlib.", "runpy."))
            )
        elif isinstance(node, ast.ImportFrom):
            name = node.module or ""
            if name in {"importlib", "runpy"} or name.startswith(("importlib.", "runpy.")):
                imports.append(name)
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in {"exec", "eval", "__import__"} or name.startswith(("importlib.", "runpy.")):
                calls.append({"line": node.lineno, "call": name})
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                text = ast.unparse(target)
                if "sys.modules" in text:
                    sys_writes.append({"line": node.lineno, "target": text})
    return {"imports": imports, "calls": calls, "sys_modules_writes": sys_writes}


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
        "quick5k_root_exists": QUICK_ROOT.exists(),
        "implementation_result_exists": RESULT.exists(),
        "checkpoint_sha256": sha_file(CHECKPOINT),
    }


def main() -> int:
    argparse.ArgumentParser().parse_args()
    if RESULT.exists() or QUAL_ROOT.exists() or QUICK_ROOT.exists():
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
            f"bound_exact:{path.name}",
            observed == {"exists": True, "bytes": size, "sha256": expected_sha},
            observed,
        )

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    prereg_audit = json.loads(PREREG_AUDIT.read_text(encoding="utf-8"))
    check("identity_exact", prereg["identity"]["sha256"] == IDENTITY and prereg["identity"]["token"] == TOKEN)
    check(
        "preregistration_audit_pass",
        prereg_audit["classification"]
        == "PASS / RS009_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY",
    )
    failed_inputs = []
    for item in prereg["frozen_authority_inputs"] + prereg["control_lineage_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            failed_inputs.append(item["role"])
    check(
        "all29_registered_inputs_exact",
        len(prereg["frozen_authority_inputs"]) == 22
        and len(prereg["control_lineage_inputs"]) == 7
        and not failed_inputs,
        failed_inputs,
    )
    inherited = json.loads(RS007C1_PASS.read_text(encoding="utf-8"))
    check(
        "inherited_deep_test_probe_evidence_pass",
        inherited["classification"] == "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
        and inherited["deep_self_test"]["payload"]["classification"] == "RS007_DEEP_SELFTEST_PASS"
        and len(inherited["contract_probes"]) == 2,
    )

    syntax_errors = []
    trees: dict[Path, ast.Module] = {}
    for path in (PARENT_RUNNER, RUNNER, PARENT_RESULT_AUDITOR, RESULT_AUDITOR, THIS_FILE):
        try:
            trees[path] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            syntax_errors.append(f"{path.name}:{exc}")
    check("python_ast_5_of_5", not syntax_errors, syntax_errors)
    if syntax_errors:
        raise RuntimeError(f"implementation_static_failure:{syntax_errors}")

    parent_tree = trees[PARENT_RUNNER]
    runner_tree = trees[RUNNER]
    parent_assignments = top_assignments(parent_tree)
    runner_assignments = top_assignments(runner_tree)
    check("runner_control_constants_parent_once", all(len(parent_assignments.get(name, [])) == 1 for name in RUNNER_CONTROL))
    check("runner_control_constants_candidate_once", all(len(runner_assignments.get(name, [])) == 1 for name in RUNNER_CONTROL))
    check(
        "two_added_size_constants_exact",
        len(runner_assignments.get("PREREG_BYTES", [])) == 1
        and len(runner_assignments.get("PREREG_AUDIT_BYTES", [])) == 1
        and isinstance(runner_assignments["PREREG_BYTES"][0].value, ast.Constant)
        and runner_assignments["PREREG_BYTES"][0].value.value == PREREG.stat().st_size
        and isinstance(runner_assignments["PREREG_AUDIT_BYTES"][0].value, ast.Constant)
        and runner_assignments["PREREG_AUDIT_BYTES"][0].value.value == PREREG_AUDIT.stat().st_size,
    )
    parent_verify = next(
        node for node in parent_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_frozen_inputs"
    )
    runner_verify = next(
        node for node in runner_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "verify_frozen_inputs"
    )
    parent_size_literals = [
        node.value for node in ast.walk(parent_verify)
        if isinstance(node, ast.Constant) and node.value in {21218, 9251}
    ]
    runner_size_names = [
        node.id for node in ast.walk(runner_verify)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        and node.id in {"PREREG_BYTES", "PREREG_AUDIT_BYTES"}
    ]
    check("parent_size_literals_exact", parent_size_literals == [21218, 9251], parent_size_literals)
    check("candidate_size_names_exact", runner_size_names == ["PREREG_BYTES", "PREREG_AUDIT_BYTES"], runner_size_names)
    parent_normal = ast.fix_missing_locations(RunnerNormalizer(False).visit(copy.deepcopy(parent_tree)))
    runner_normal = ast.fix_missing_locations(RunnerNormalizer(True).visit(copy.deepcopy(runner_tree)))
    normalized_runner_equal = (
        ast.dump(parent_normal, include_attributes=False)
        == ast.dump(runner_normal, include_attributes=False)
    )
    check("full_normalized_runner_ast_equal", normalized_runner_equal)
    normalized_parent_auditor = normalize_result_auditor(trees[PARENT_RESULT_AUDITOR])
    normalized_result_auditor = normalize_result_auditor(trees[RESULT_AUDITOR])
    normalized_auditor_equal = (
        ast.dump(normalized_parent_auditor, include_attributes=False)
        == ast.dump(normalized_result_auditor, include_attributes=False)
    )
    check("full_normalized_result_auditor_ast_equal", normalized_auditor_equal)
    runtime = forbidden_runtime(runner_tree)
    check("runtime_indirection_absent", not runtime["imports"] and not runtime["calls"] and not runtime["sys_modules_writes"], runtime)
    check(
        "legacy_protocol_labels_preserved",
        all(
            marker in RUNNER.read_text(encoding="utf-8")
            for marker in (
                "RS007_CONTRACT_PROBE_PASS",
                "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY",
                "PASS / RS007_DUAL_DOMAIN_QUALIFICATION_PASS",
            )
        ),
    )

    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    launcher_markers = (
        str(PYTHON), str(RUNNER), str(RESULT_AUDITOR), str(QUAL_ROOT),
        "$env:CUDA_VISIBLE_DEVICES = '0'",
        "$env:RS007_DEVICE_MODE = 'CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK'",
        "$env:PYTHONDONTWRITEBYTECODE = '1'",
        "$env:PYTHONHASHSEED = '0'",
        "$env:CUBLAS_WORKSPACE_CONFIG = ':4096:8'",
    )
    check(
        "launcher_absolute_contract_exact",
        all(marker in launcher_text for marker in launcher_markers),
        [marker for marker in launcher_markers if marker not in launcher_text],
    )
    escaped = str(LAUNCHER).replace("'", "''")
    parsed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            f"$t=$null;$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e;exit 1}}else{{'PASS'}}",
        ],
        capture_output=True, text=True, timeout=60,
    )
    check("launcher_powershell_parse_pass", parsed.returncode == 0 and "PASS" in parsed.stdout, {
        "stdout": parsed.stdout, "stderr": parsed.stderr,
    })
    check("future_outputs_fresh", not RESULT.exists() and not QUAL_ROOT.exists() and not QUICK_ROOT.exists())
    if not all(item["pass"] for item in checks):
        raise RuntimeError(f"implementation_static_failure:{[item['name'] for item in checks if not item['pass']]}")

    before = snapshot()
    probe = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER), "-Mode", "ContractProbe", "-Nonce", PROBE_NONCE,
        ],
        capture_output=True, text=True, timeout=300,
    )
    try:
        probe_payload = last_json(probe.stdout)
    except Exception as exc:
        probe_payload = {"parse_error": str(exc)}
    after = snapshot()
    check("exactly_one_final_launcher_probe", True, {"nonce": PROBE_NONCE})
    check("final_launcher_probe_exit0", probe.returncode == 0, {
        "stdout": probe.stdout[-4000:], "stderr": probe.stderr[-4000:],
    })
    check(
        "final_launcher_probe_contract_exact",
        probe_payload.get("classification") == "RS007_CONTRACT_PROBE_PASS"
        and probe_payload.get("identity_sha256") == IDENTITY
        and probe_payload.get("nonce") == PROBE_NONCE
        and probe_payload.get("device_mode") == "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK"
        and probe_payload.get("cuda_visible_devices") == "0"
        and probe_payload.get("torch_imported") is False
        and probe_payload.get("files_written") == 0,
        probe_payload,
    )
    check("probe_zero_file_diff", before == after, {"before": before, "after": after})
    check("checkpoint_unchanged", sha_file(CHECKPOINT) == EXPECTED[CHECKPOINT][1])
    passed = all(item["pass"] for item in checks)
    result = {
        "schema_version": "v5.rs009.implementation_audit.v1",
        "audited_at_epoch": time.time(),
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
            if passed else "FAIL_CLOSED / RS009_IMPLEMENTATION_AUDIT_FAILURE"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "normalized_ast": {
            "runner_equal": normalized_runner_equal,
            "result_auditor_equal": normalized_auditor_equal,
            "parent_size_literals": parent_size_literals,
            "candidate_size_names": runner_size_names,
            "runtime_indirection": runtime,
        },
        "bound_files": {
            str(path): {"bytes": path.stat().st_size, "sha256": sha_file(path)}
            for path in (
                PREREG, PREREG_AUDIT, PARENT_RUNNER, RUNNER,
                PARENT_RESULT_AUDITOR, RESULT_AUDITOR, LAUNCHER,
                THIS_FILE, PYTHON, CHECKPOINT, RS007C1_PASS,
            )
        },
        "inherited_deep_selftest": {
            "authority": "IMPLEMENTATION_EVIDENCE_ONLY_NO_RERUN_NO_STRENGTH",
            "source_sha256": EXPECTED[RS007C1_PASS][1],
        },
        "final_launcher_probe": {
            "nonce": PROBE_NONCE,
            "exit_code": probe.returncode,
            "payload": probe_payload,
            "stdout": probe.stdout[-4000:],
            "stderr": probe.stderr[-4000:],
        },
        "snapshot_before": before,
        "snapshot_after": after,
        "qualification_authority": "ONE_ATTEMPT" if passed else "NONE",
        "quick5k_authority": "NONE",
        "network_or_slumbot_hands": 0,
        "official_hands": 0,
    }
    with RESULT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
