#!/usr/bin/env python3
"""Independent pre-output audit for the registered LG003 implementation."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[2]
TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
PREREG = ROOT / "reports" / f"v5_lg003_cleanroom_diversity_league_preregistration_{TOKEN}_20260723.json"
CLEAN = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_h11_clean_base_{TOKEN}.py"
TRAINER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_train_{TOKEN}.py"
MATERIALIZER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_materialize_{TOKEN}.py"
LAUNCHER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_launcher_{TOKEN}.ps1"
CHECKPOINT = (
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715"
    / "h11_control_endpoint.pt"
)
OUTPUT_ROOT = (
    ROOT
    / "models"
    / "alpha_holdem_v5_hybrid"
    / f"v5_lg003_{TOKEN}_20260723"
)
OUT = ROOT / "reports" / f"v5_lg003_implementation_audit_{TOKEN}_20260723.json"

EXPECTED = {
    PREREG: "525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d",
    CLEAN: "7cacc211065ab8494b9bb12c7d8b4ad30abbb303bb29875f9d70b756a52f8ca7",
    TRAINER: "a887ddae0e94065e5757ff88c650901fe88eee3a2cbc542b371ddf124f285615",
    MATERIALIZER: "a805fd604391c3c52acd2a5daf163fbf34937086981b7c3960ccceb71b2f8b4f",
    LAUNCHER: "55b8891210513ccb35316b6c284cbe7745961edf5d6dc63b3246bdc679ac3d97",
    CHECKPOINT: "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13",
}
MEMBER_HASHES = {
    103: "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
    109: "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    115: "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    120: "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    129: "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def state_dict_sha256(state_dict: dict) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        digest.update(len(metadata).to_bytes(8, "big"))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def is_name_target(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def is_lg003_active(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "lg003_active"


class NormalizeLG003(ast.NodeTransformer):
    """Remove exactly the registered LG003 opt-in surface from trainer AST."""

    def visit_Module(self, node: ast.Module):
        body = []
        for item in node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else [item.target]
                if any(isinstance(target, ast.Name) and target.id.startswith("LG003_") for target in targets):
                    continue
            if isinstance(item, ast.FunctionDef) and item.name.startswith("lg003_"):
                continue
            visited = self.visit(item)
            if visited is not None:
                body.append(visited)
        node.body = body
        return node

    def visit_Expr(self, node: ast.Expr):
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "parser"
            and call.func.attr == "add_argument"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
            and call.args[0].value.startswith("--lg003")
        ):
            return None
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if any(
            isinstance(target, ast.Name)
            and target.id in {"lg003_active", "lg003_contract", "lg003_assignment"}
            for target in node.targets
        ):
            return None
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        node = self.generic_visit(node)
        node.values = [
            value
            for value in node.values
            if not (
                isinstance(value, ast.UnaryOp)
                and isinstance(value.op, ast.Not)
                and is_lg003_active(value.operand)
            )
        ]
        if len(node.values) == 1:
            return node.values[0]
        return node

    def visit_Dict(self, node: ast.Dict):
        node = self.generic_visit(node)
        pairs = [
            (key, value)
            for key, value in zip(node.keys, node.values)
            if not (
                isinstance(key, ast.Constant)
                and key.value == "lg003"
            )
        ]
        node.keys = [pair[0] for pair in pairs]
        node.values = [pair[1] for pair in pairs]
        return node

    def visit_If(self, node: ast.If):
        if is_lg003_active(node.test):
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                return self.visit(node.orelse[0])
            return None
        if (
            isinstance(node.test, ast.BoolOp)
            and any(
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "args"
                and value.attr == "lg003_contract_probe"
                for value in node.test.values
            )
        ):
            return None
        return self.generic_visit(node)


def normalized_ast_equal() -> tuple[bool, str, str]:
    clean_tree = ast.parse(CLEAN.read_text(encoding="utf-8"), filename=str(CLEAN))
    trainer_tree = ast.parse(TRAINER.read_text(encoding="utf-8"), filename=str(TRAINER))
    normalized = NormalizeLG003().visit(trainer_tree)
    ast.fix_missing_locations(normalized)
    clean_dump = ast.dump(clean_tree, annotate_fields=True, include_attributes=False)
    normalized_dump = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return (
        clean_dump == normalized_dump,
        hashlib.sha256(clean_dump.encode()).hexdigest(),
        hashlib.sha256(normalized_dump.encode()).hexdigest(),
    )


def load_trainer_module():
    previous = os.environ.get("PYTHONDONTWRITEBYTECODE")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        spec = importlib.util.spec_from_file_location("v5_lg003_audit_module", TRAINER)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot create trainer import spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous


def run_probe(mode: str) -> dict:
    before = OUTPUT_ROOT.exists()
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(LAUNCHER),
            "-Mode",
            mode,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    after = OUTPUT_ROOT.exists()
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    payload = json.loads(lines[-1]) if lines else None
    if completed.returncode != 0 or before or after or not payload:
        raise RuntimeError(
            f"{mode} failed rc={completed.returncode} before={before} after={after} "
            f"stdout={completed.stdout[-1000:]} stderr={completed.stderr[-1000:]}"
        )
    return payload


def check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise RuntimeError(label)


def main() -> None:
    if OUT.exists():
        raise SystemExit("refusing to overwrite LG003 implementation audit")
    checks: dict[str, bool] = {}
    for path, expected in EXPECTED.items():
        check(path.is_file() and sha256_path(path) == expected, f"identity:{path.name}", checks)
    check(not OUTPUT_ROOT.exists(), "output_root_absent_before_audit", checks)
    check(compile(CLEAN.read_text(encoding="utf-8"), str(CLEAN), "exec") is not None, "clean_compile", checks)
    check(compile(TRAINER.read_text(encoding="utf-8"), str(TRAINER), "exec") is not None, "trainer_compile", checks)
    clean_lower = CLEAN.read_text(encoding="utf-8").lower()
    check(
        not any(name.lower() in clean_lower for name in ("LG001", "LG002", "H12", "H13", "H14", "H15", "H16", "H17", "H18")),
        "clean_base_forbidden_symbols_zero",
        checks,
    )
    equal, clean_ast_sha, normalized_ast_sha = normalized_ast_equal()
    check(equal, "full_normalized_ast_equal", checks)

    launcher_text = LAUNCHER.read_text(encoding="utf-8-sig")
    check("train_v5.py" not in launcher_text, "launcher_never_uses_censured_trainer", checks)
    check(
        f"$Token = '{TOKEN}'" in launcher_text
        and 'v5_lg003_train_${Token}.py' in launcher_text,
        "launcher_uses_exact_fresh_trainer",
        checks,
    )
    parse = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$e=$null;$t=$null;"
                f"[System.Management.Automation.Language.Parser]::ParseFile('{LAUNCHER}',$([ref]$t),$([ref]$e))|Out-Null;"
                "if($e.Count -ne 0){exit 1}"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    check(parse.returncode == 0, "launcher_powershell_ast_parse", checks)

    checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    check(int(checkpoint.get("iteration", -1)) == 35051, "checkpoint_iteration", checks)
    check(int(checkpoint.get("total_hands", -1)) == 576021901, "checkpoint_hands", checks)
    snapshots = checkpoint.get("pool_snapshots") or []
    check(tuple(int(row["id"]) for row in snapshots) == (109, 115, 120, 129, 103), "pool_order", checks)
    observed_member_hashes = {
        int(row["id"]): state_dict_sha256(row["state_dict"])
        for row in snapshots
    }
    check(observed_member_hashes == MEMBER_HASHES, "pool_member_state_hashes", checks)

    module = load_trainer_module()
    state_before = random.getstate()
    replay_rows = []
    for iteration in range(35052, 39148):
        control = module.lg003_select_opponent("control_uniform", iteration, snapshots)[1]
        treatment = module.lg003_select_opponent("treatment_diversity", iteration, snapshots)[1]
        check(control["u64"] == treatment["u64"], f"same_u64:{iteration}", checks)
        independent = int.from_bytes(
            hashlib.sha256(
                f"LG003_ASSIGNMENT_V1|{TOKEN}|2026072301|{iteration}".encode("utf-8")
            ).digest()[:8],
            "big",
        )
        check(control["u64"] == independent, f"independent_u64:{iteration}", checks)
        replay_rows.append((control, treatment))
    check(random.getstate() == state_before, "selector_global_rng_unchanged", checks)
    self_rows = sum(row[0]["selected_kind"] == "self_play" for row in replay_rows)
    check(0.17 <= self_rows / len(replay_rows) <= 0.23, "selector_self_fraction_sanity", checks)

    probe_control = run_probe("ProbeControl")
    probe_treatment = run_probe("ProbeTreatment")
    check(probe_control["status"] == "PASS", "probe_control_pass", checks)
    check(probe_treatment["status"] == "PASS", "probe_treatment_pass", checks)
    check(
        [row["u64"] for row in probe_control["selector_samples"]]
        == [row["u64"] for row in probe_treatment["selector_samples"]],
        "probe_same_u64",
        checks,
    )
    check(not OUTPUT_ROOT.exists(), "output_root_absent_after_audit", checks)

    result = {
        "schema_version": "v5.lg003.implementation_audit.v1",
        "checked_at": "2026-07-23T03:20:00-04:00",
        "registration_token": TOKEN,
        "status": "PASS_IMPLEMENTATION_AND_TWO_ZERO_OUTPUT_PROBES",
        "checks": checks,
        "passed": sum(checks.values()),
        "failed": sum(not value for value in checks.values()),
        "source_sha256": {str(path): value for path, value in EXPECTED.items()},
        "normalized_ast": {
            "clean_sha256": clean_ast_sha,
            "trainer_after_lg003_removal_sha256": normalized_ast_sha,
            "equal": equal,
        },
        "pool_member_state_sha256": {str(key): value for key, value in observed_member_hashes.items()},
        "selector_replay_rows": len(replay_rows),
        "probe_control": probe_control,
        "probe_treatment": probe_treatment,
        "scientific_rows": 0,
        "training_authorized_next": "STAGE_A_CONTROL_THEN_AUDIT_THEN_QUICK5K_THEN_STAGE_A_TREATMENT",
        "strength_claim": "FORBIDDEN",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": result["status"], "passed": result["passed"], "failed": result["failed"], "out": str(OUT)}))


if __name__ == "__main__":
    main()
