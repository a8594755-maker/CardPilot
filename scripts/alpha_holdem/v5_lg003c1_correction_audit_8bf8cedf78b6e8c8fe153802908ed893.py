#!/usr/bin/env python3
"""Independent audit of the sole LG003C1 pre-output correction."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOKEN = "8bf8cedf78b6e8c8fe153802908ed893"
PARENT = ROOT / "scripts" / "alpha_holdem" / "v5_lg003_train_fbd630ab6a689913afc1cee8a63066dd.py"
TRAINER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003c1_train_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003c1_launcher_{TOKEN}.ps1"
REGISTRATION = ROOT / "reports" / f"v5_lg003c1_preoutput_correction_registration_{TOKEN}_20260723.json"
OUTPUT_ROOT = ROOT / "models" / "alpha_holdem_v5_hybrid" / f"v5_lg003c1_{TOKEN}_20260723"
OUT = ROOT / "reports" / f"v5_lg003c1_correction_audit_{TOKEN}_20260723.json"
EXPECTED = {
    PARENT: "a887ddae0e94065e5757ff88c650901fe88eee3a2cbc542b371ddf124f285615",
    TRAINER: "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452",
    LAUNCHER: "c20ebf0d3201b8fdb01a2a31945dbb2166defb646a2f1e410ca2e6d2e04b3d96",
    REGISTRATION: "69eebf15d02c179c7bcf6f2bf50af75bf13577453098800b264f19f5a1771fe4",
}


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"{label} count {source.count(old)}")
    return source.replace(old, new, 1)


def run_probe(mode: str) -> dict:
    completed = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(LAUNCHER), "-Mode", mode,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    rows = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if completed.returncode != 0 or not rows or OUTPUT_ROOT.exists():
        raise RuntimeError(f"{mode} failed: {completed.returncode} {completed.stderr[-1000:]}")
    return json.loads(rows[-1])


def main() -> None:
    if OUT.exists() or OUTPUT_ROOT.exists():
        raise SystemExit("LG003C1 audit path or output root collision")
    checks = {}
    for path, expected in EXPECTED.items():
        checks[f"identity:{path.name}"] = path.is_file() and sha256_path(path) == expected

    corrected = TRAINER.read_text(encoding="utf-8")
    compile(corrected, str(TRAINER), "exec")
    tree = ast.parse(corrected)
    main_fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    checkpoint_index = next(
        index for index, node in enumerate(main_fn.body)
        if isinstance(node, ast.FunctionDef) and node.name == "checkpoint_payload"
    )
    early_names = {
        target.id
        for node in main_fn.body[:checkpoint_index]
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    checks["provenance_vars_bound_before_checkpoint_payload"] = {
        "assignment_provenance_last_sha",
        "assignment_provenance_last_iteration",
    }.issubset(early_names)

    reverted = corrected
    reverted = replace_once(
        reverted,
        "v5_lg003c1_8bf8cedf78b6e8c8fe153802908ed893_20260723",
        "v5_lg003_fbd630ab6a689913afc1cee8a63066dd_20260723",
        "output root reverse",
    )
    reverted = replace_once(
        reverted,
        "    assignment_provenance_last_sha = None\n"
        "    assignment_provenance_last_iteration = None\n\n"
        "    def checkpoint_payload() -> dict:\n",
        "    def checkpoint_payload() -> dict:\n",
        "early init reverse",
    )
    reverted = replace_once(
        reverted,
        "    assignment_provenance_fh = None\n"
        "    if args.opponent_assignment_provenance_file:\n",
        "    assignment_provenance_fh = None\n"
        "    assignment_provenance_last_sha = None\n"
        "    assignment_provenance_last_iteration = None\n"
        "    if args.opponent_assignment_provenance_file:\n",
        "late init reverse",
    )
    checks["exact_three_change_reverse_to_terminal_parent"] = (
        hashlib.sha256(reverted.encode("utf-8")).hexdigest() == EXPECTED[PARENT]
    )

    parse = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-Command",
            "$e=$null;$t=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{LAUNCHER}',$([ref]$t),$([ref]$e))|Out-Null;"
            "if($e.Count -ne 0){exit 1}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    checks["launcher_ast_parse"] = parse.returncode == 0
    probe_control = run_probe("ProbeControl")
    probe_treatment = run_probe("ProbeTreatment")
    checks["control_probe"] = probe_control.get("status") == "PASS"
    checks["treatment_probe"] = probe_treatment.get("status") == "PASS"
    checks["same_probe_u64"] = [
        row["u64"] for row in probe_control["selector_samples"]
    ] == [
        row["u64"] for row in probe_treatment["selector_samples"]
    ]
    checks["output_root_absent"] = not OUTPUT_ROOT.exists()
    failed = [name for name, value in checks.items() if not value]
    if failed:
        raise RuntimeError(f"LG003C1 audit failures: {failed}")
    result = {
        "schema_version": "v5.lg003c1.correction_audit.v1",
        "checked_at": "2026-07-23T03:25:00-04:00",
        "token": TOKEN,
        "status": "PASS_SOLE_PREOUTPUT_CORRECTION",
        "checks": checks,
        "passed": len(checks),
        "failed": 0,
        "probe_control": probe_control,
        "probe_treatment": probe_treatment,
        "scientific_rows": 0,
        "next_authority": "ONE_STAGE_A_CONTROL_EXECUTION",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "passed": result["passed"], "out": str(OUT)}))


if __name__ == "__main__":
    main()
