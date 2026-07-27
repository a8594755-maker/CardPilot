"""Independent no-model implementation audit for LRFT-F8R1C1.

The corrected runner is never imported.  This audit proves normalized full-AST
equality to the frozen parent, verifies exact fail-closed authority comparisons,
and invokes exactly two direct zero-file contract-probe subprocesses.  Child
detailed evidence must be bit-identical to frozen parent evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "80f4f9d2e7e6c7f4bc9f6dc82e7f2e89"
IDENTITY = TOKEN + "6bd0c3ff56dd542eec58b239d1422619"
PARENT_TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
PARENT_IDENTITY = PARENT_TOKEN + "d14e7b9dfbdbb51cc7897df93e2d3198"
RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1c1_{TOKEN}.py"
PARENT_RUNNER = (
    ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1_{PARENT_TOKEN}.py"
)
PREREG = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_runtime_metadata_correction_preregistration_{TOKEN}_20260723.json"
)
PREAUDIT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_preregistration_audit_{TOKEN}_20260723.json"
)
PARENT_AUDIT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_implementation_audit_c2_{PARENT_TOKEN}_20260723.json"
)
PARENT_FAILURE = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_resource_admission_preoutput_runtime_metadata_failure_{PARENT_TOKEN}_20260723.json"
)
OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1c1_implementation_audit_{TOKEN}_20260723.json"
)
OUTPUT_ROOT = ROOT / "reports" / f"lrft_f8r1c1_{TOKEN}"
EXPECTED_RUNNER_SHA = "0697f5d127f484f9ad01023d751c87500d527ca3c76a2286e392a04ad1ff0711"
EXPECTED_RUNNER_BYTES = 88_050
EXPECTED_HASHES = {
    PREREG: "53b0bbfd1aceb511b7e027fc42e2e100cf6d680f989bf8e292ffd59bf1dccb08",
    PREAUDIT: "5857daa842330c7aa5448adce3c57d067b78c9c53ed6f91b0d875e7937a29eab",
    PARENT_RUNNER: "2922d9dc18566b361883da6a384a9349a4bddbf5e3f743f0952ba09bbcdd8506",
    PARENT_AUDIT: "0fd7c8103b60a4db2795dcfb1bf3eb8f7d04dae575fa25df2d74e6f97e69beec",
    PARENT_FAILURE: "99a0f9a65b4c32883cd1967d7c59a0f49380c5cb28ecec4e4298ee5e5726f324",
}
TOP_LEVEL_SENTINELS = {
    "IDENTITY",
    "PREREG",
    "PREREG_SHA256",
    "PREAUDIT",
    "PREAUDIT_SHA256",
    "IMPLEMENTATION_AUDITOR",
    "IMPLEMENTATION_AUDIT",
    "IMPLEMENTATION_AUDIT_SCHEMA",
    "IMPLEMENTATION_AUDIT_PASS",
    "OUTPUT_ROOT",
    "RESOURCE_PATH",
}
SCIENCE = {
    "model_or_network_calls": 0,
    "resource_rows": 0,
    "census_hands": 0,
    "selected_roots": 0,
    "belief_rows": 0,
    "solver_traversals": 0,
    "leaf_outcomes": 0,
    "E0_tapes": 0,
    "E1_tapes": 0,
    "teacher_rows": 0,
    "checkpoints": 0,
    "slumbot_hands": 0,
    "official_hands": 0,
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate(name: str, predicates: dict[str, bool], evidence: Any) -> dict[str, Any]:
    native = {key: bool(value) for key, value in predicates.items()}
    return {
        "name": name,
        "pass": all(native.values()),
        "predicates": native,
        "evidence": evidence,
    }


class NormalizeAuthority(ast.NodeTransformer):
    """Normalize only the authority changes explicitly registered by F8R1C1."""

    def visit_Module(self, node: ast.Module) -> ast.Module:
        body: list[ast.stmt] = []
        for item in node.body:
            if isinstance(item, ast.Assign):
                names = [
                    target.id
                    for target in item.targets
                    if isinstance(target, ast.Name)
                ]
                if any(
                    name in {"SCIENCE_MASTER_IDENTITY", "PARENT_RUNNER_SHA256"}
                    for name in names
                ):
                    continue
                if len(names) == 1 and names[0] in TOP_LEVEL_SENTINELS:
                    item.value = ast.Constant(value=f"__AUTH_{names[0]}__")
                    body.append(item)
                    continue
            body.append(self.visit(item))
        node.body = body
        return node

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id == "SCIENCE_MASTER_IDENTITY":
            node.id = "IDENTITY"
        return node

    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        self.generic_visit(node)
        left = ast.dump(node.left, include_attributes=False)
        is_torch_metadata = (
            "metadata" in left
            and "version" in left
            and any(
                isinstance(child, ast.Constant) and child.value == "torch"
                for child in ast.walk(node.left)
            )
        )
        if is_torch_metadata:
            for comparator in node.comparators:
                if (
                    isinstance(comparator, ast.Constant)
                    and comparator.value == "2.6.0+cu124"
                ):
                    comparator.value = "2.6.0"
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if not isinstance(node.value, str):
            return node
        value = node.value
        value = value.replace(IDENTITY, PARENT_IDENTITY)
        value = value.replace(TOKEN, PARENT_TOKEN)
        value = value.replace("F8R1C1", "F8R1").replace("f8r1c1", "f8r1")
        value = value.replace(
            "LRFT_F8R1_REGISTERED_PREIMPLEMENTATION_AUDIT_"
            "PASS_IMPLEMENTATION_AUTHORIZED_ONLY",
            "LRFT_F8R1_REGISTERED_INSTANTIATED_PREIMPLEMENTATION_AUDIT_PASS",
        )
        node.value = value
        return node


def normalized_ast(source: str) -> tuple[str, int]:
    tree = NormalizeAuthority().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ast.dump(tree, include_attributes=False), sum(1 for _ in ast.walk(tree))


def top_constant(tree: ast.Module, name: str) -> Any:
    for item in tree.body:
        if not isinstance(item, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in item.targets):
            if isinstance(item.value, ast.Constant):
                return item.value.value
    raise RuntimeError(f"missing top-level constant {name}")


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef:
    for item in tree.body:
        if isinstance(item, ast.FunctionDef) and item.name == name:
            return item
    raise RuntimeError(f"missing function {name}")


def exact_gate_static(tree: ast.Module, source: str) -> dict[str, bool]:
    verifier = function_node(tree, "_verify_implementation_audit")
    resource = function_node(tree, "resource_admission")
    main = function_node(tree, "main")
    verifier_dump = ast.dump(verifier, include_attributes=False)
    resource_dump = ast.dump(resource, include_attributes=False)
    main_dump = ast.dump(main, include_attributes=False)
    return {
        "audit_status_exact": 'audit.get("status") == IMPLEMENTATION_AUDIT_PASS'
        in source,
        "audit_path_exact": (
            "resolved != IMPLEMENTATION_AUDIT.resolve(strict=False)"
            in source
        ),
        "auditor_path_exact": (
            "== IMPLEMENTATION_AUDITOR.resolve(strict=False)" in source
        ),
        "runner_sha_exact": 'runner_binding.get("sha256") == runner_sha' in source,
        "gates_all_true": "all(item.get(\"pass\") is True" in source,
        "no_pass_substring": '"PASS" in' not in verifier_dump
        and "'PASS' in" not in verifier_dump,
        "resource_pass_exact": (
            'result["status"]\n        == '
            '"LRFT_F8R1C1_RESOURCE_ADMISSION_PASS_SCIENCE_SEPARATELY_AUTHORIZED"'
            in source
        ),
        "verifier_present": "_verify_implementation_audit" in resource_dump,
        "main_exact_exit_compare": "LRFT_F8R1C1_RESOURCE_ADMISSION_PASS" in main_dump,
    }


def run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lrft_f8r1c1_audit_probe_") as directory:
        root = Path(directory)
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(RUNNER),
                "--mode",
                "contract-probe",
                "--probe-root",
                str(root),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        files = [path for path in root.rglob("*") if path.is_file()]
        if completed.returncode != 0:
            raise RuntimeError(
                f"contract probe exit {completed.returncode}: {completed.stderr[-4000:]}"
            )
        return {
            "payload": json.loads(completed.stdout.strip()),
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "files": len(files),
            "bytes": sum(path.stat().st_size for path in files),
        }


def parent_probe_evidence(parent: dict[str, Any]) -> tuple[Any, Any]:
    found: dict[str, Any] = {}
    for item in parent.get("gates", []):
        if item.get("name") in {
            "G2_FRESH_ZERO_FILE_CLI_PROBE_1",
            "G3_FRESH_ZERO_FILE_CLI_PROBE_2",
        }:
            found[item["name"]] = item["evidence"]["payload"]["evidence"]
    if set(found) != {
        "G2_FRESH_ZERO_FILE_CLI_PROBE_1",
        "G3_FRESH_ZERO_FILE_CLI_PROBE_2",
    }:
        raise RuntimeError("frozen parent probe evidence missing")
    return (
        found["G2_FRESH_ZERO_FILE_CLI_PROBE_1"],
        found["G3_FRESH_ZERO_FILE_CLI_PROBE_2"],
    )


def main() -> int:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite {OUT}")
    if OUTPUT_ROOT.exists():
        raise RuntimeError("F8R1C1 output root exists before implementation audit")
    observed_hashes = {str(path): sha(path) for path in EXPECTED_HASHES}
    if any(observed_hashes[str(path)] != expected for path, expected in EXPECTED_HASHES.items()):
        raise RuntimeError("frozen input identity mismatch")
    if sha(RUNNER) != EXPECTED_RUNNER_SHA or RUNNER.stat().st_size != EXPECTED_RUNNER_BYTES:
        raise RuntimeError("corrected runner identity mismatch")

    child_source = RUNNER.read_text(encoding="utf-8")
    parent_source = PARENT_RUNNER.read_text(encoding="utf-8")
    child_tree = ast.parse(child_source)
    child_normalized, child_nodes = normalized_ast(child_source)
    parent_normalized, parent_nodes = normalized_ast(parent_source)
    parent_report = json.loads(PARENT_AUDIT.read_text(encoding="utf-8"))
    expected_probe0, expected_probe1 = parent_probe_evidence(parent_report)
    if expected_probe0 != expected_probe1:
        raise RuntimeError("frozen parent detailed evidence is not repeat-identical")

    probes = [run_probe(), run_probe()]  # Exactly two direct zero-file probes.
    gates: list[dict[str, Any]] = []
    gates.append(
        gate(
            "G1_FROZEN_IDENTITIES_AND_CONTROL_SCIENCE_SPLIT",
            {
                "runner_sha": sha(RUNNER) == EXPECTED_RUNNER_SHA,
                "runner_bytes": RUNNER.stat().st_size == EXPECTED_RUNNER_BYTES,
                "all_inputs": all(
                    observed_hashes[str(path)] == expected
                    for path, expected in EXPECTED_HASHES.items()
                ),
                "control_identity": top_constant(child_tree, "IDENTITY") == IDENTITY,
                "science_identity": top_constant(
                    child_tree, "SCIENCE_MASTER_IDENTITY"
                )
                == PARENT_IDENTITY,
                "parent_runner_binding": top_constant(
                    child_tree, "PARENT_RUNNER_SHA256"
                )
                == EXPECTED_HASHES[PARENT_RUNNER],
            },
            {
                "runner_sha256": sha(RUNNER),
                "frozen_inputs": observed_hashes,
                "control_identity": IDENTITY,
                "science_master_identity": PARENT_IDENTITY,
            },
        )
    )
    gates.append(
        gate(
            "G2_NORMALIZED_COMPLETE_AST_EQUALITY",
            {
                "full_dump_equal": child_normalized == parent_normalized,
                "node_count_equal": child_nodes == parent_nodes,
                "science_default_name": (
                    "master: str = SCIENCE_MASTER_IDENTITY" in child_source
                ),
                "sole_metadata_literal": (
                    'importlib.metadata.version("torch") != "2.6.0+cu124"'
                    in child_source
                    and 'torch.__version__ != "2.6.0+cu124"'
                    in child_source
                ),
            },
            {
                "child_normalized_sha256": hashlib.sha256(
                    child_normalized.encode("utf-8")
                ).hexdigest(),
                "parent_normalized_sha256": hashlib.sha256(
                    parent_normalized.encode("utf-8")
                ).hexdigest(),
                "child_nodes": child_nodes,
                "parent_nodes": parent_nodes,
            },
        )
    )
    static = exact_gate_static(child_tree, child_source)
    gates.append(gate("G3_EXACT_FAIL_CLOSED_PATHS_AND_STATUSES", static, static))

    for index, probe in enumerate(probes, start=1):
        payload = probe["payload"]
        gates.append(
            gate(
                f"G{index + 3}_DIRECT_ZERO_FILE_PROBE_{index}",
                {
                    "exit0": probe["returncode"] == 0,
                    "status": payload.get("status")
                    == "LRFT_F8R1C1_CONTRACT_PROBE_PASS",
                    "identity": payload.get("identity") == IDENTITY,
                    "pass39": payload.get("passed") == payload.get("total") == 39,
                    "checks": len(payload.get("checks", {})) == 39
                    and all(payload["checks"].values()),
                    "zero_root": payload.get("before") == payload.get("after")
                    == {"files": 0, "bytes": 0},
                    "zero_process": probe["files"] == probe["bytes"] == 0,
                    "torch_absent": payload.get("torch_loaded") is False,
                    "model0": payload.get("model_calls") == 0,
                    "created0": payload.get("files_created")
                    == payload.get("bytes_created")
                    == 0,
                    "stderr_empty": probe["stderr"] == "",
                },
                probe,
            )
        )

    evidence0 = probes[0]["payload"]["evidence"]
    evidence1 = probes[1]["payload"]["evidence"]
    gates.append(
        gate(
            "G6_DETAILED_EVIDENCE_PARENT_BIT_EQUIVALENCE",
            {
                "child_repeat": evidence0 == evidence1,
                "probe1_parent": evidence0 == expected_probe0,
                "probe2_parent": evidence1 == expected_probe1,
                "parent_repeat": expected_probe0 == expected_probe1,
            },
            {
                "child_evidence_sha256": hashlib.sha256(
                    json.dumps(evidence0, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "parent_evidence_sha256": hashlib.sha256(
                    json.dumps(
                        expected_probe0, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest(),
            },
        )
    )
    gates.append(
        gate(
            "G7_NO_MODEL_RESOURCE_OR_SCIENCE",
            {
                "output_absent": not OUTPUT_ROOT.exists(),
                "model0": all(
                    probe["payload"].get("model_calls") == 0 for probe in probes
                ),
                "torch_absent": all(
                    probe["payload"].get("torch_loaded") is False for probe in probes
                ),
                "resource_not_run": True,
                "science0": all(value == 0 for value in SCIENCE.values()),
            },
            {
                "model_instantiated": 0,
                "checkpoint_loads": 0,
                "network_calls": 0,
                "resource_admission_runs": 0,
                "scientific_output": SCIENCE,
            },
        )
    )

    passed = sum(item["pass"] for item in gates)
    status = (
        "LRFT_F8R1C1_IMPLEMENTATION_AUDIT_PASS_RESOURCE_ADMISSION_AUTHORIZED_ONLY"
        if passed == len(gates)
        else "LRFT_F8R1C1_IMPLEMENTATION_AUDIT_NONPASS"
    )
    result = {
        "schema_version": "v5.lrft_f8r1c1.implementation_audit.v1",
        "identity": IDENTITY,
        "status": status,
        "runner": {
            "path": str(RUNNER.resolve()),
            "sha256": sha(RUNNER),
            "bytes": RUNNER.stat().st_size,
        },
        "audit_source": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha(Path(__file__).resolve()),
        },
        "parent": {
            "runner_sha256": EXPECTED_HASHES[PARENT_RUNNER],
            "implementation_audit_sha256": EXPECTED_HASHES[PARENT_AUDIT],
            "preoutput_failure_sha256": EXPECTED_HASHES[PARENT_FAILURE],
        },
        "gates_passed": passed,
        "gates_total": len(gates),
        "gates": gates,
        "model_instantiated": 0,
        "checkpoint_loads": 0,
        "network_calls": 0,
        "resource_admission_runs": 0,
        "scientific_output": SCIENCE,
        "authority": (
            "PASS authorizes exactly one registered F8R1C1 zero-science resource "
            "admission only. It is not scientific evidence."
        ),
    }
    descriptor = os.open(OUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({"status": status, "passed": passed, "total": len(gates)}))
    return 0 if passed == len(gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
