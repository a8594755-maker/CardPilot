"""Nonbehavioral RS007C1 authority-path bridge."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(r"C:\Users\a8594\CardPilot")
RUNNER = ROOT / "scripts" / "alpha_holdem" / "v5_rs007_dual_domain_fully_live_resolver_bf43f304c4709f356af131d60ef6e35a.py"
AUDITOR = ROOT / "scripts" / "alpha_holdem" / "v5_rs007_dual_domain_fully_live_resolver_audit_bf43f304c4709f356af131d60ef6e35a.py"
ENVELOPE = ROOT / "reports" / "v5_rs007c1_qualification_authority_envelope_ac09e2283fc6459f887b83e1d1e22b6d_20260723.json"
QUAL_ROOT = ROOT / "reports" / "v5_rs007_dual_domain_fully_live_resolver_qualification_bf43f304c4709f356af131d60ef6e35a_20260723"
EXPECTED = {
    RUNNER: "049d779556fd89fc0e93f5bbb32f5e1a1a9594372cece2dcfa0c526ba46a5e94",
    AUDITOR: "bce42611096975a958ac4bcd131b2fcca355a771f9fd26749d285d7685e9d4ba",
    ENVELOPE: "20216b353a5dfb893500b791916374d69374c37087c1999730a220c553a65a0a",
}
QUALIFICATION_NONCE = "RS007_QUALIFICATION_2036972299"


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_exact(name: str, path: Path) -> ModuleType:
    if not path.is_file() or sha_file(path) != EXPECTED[path]:
        raise RuntimeError(f"immutable_target_failure:{path.name}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module_spec_failure:{path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_envelope() -> str:
    if not ENVELOPE.is_file() or sha_file(ENVELOPE) != EXPECTED[ENVELOPE]:
        raise RuntimeError("authority_envelope_identity_failure")
    value = json.loads(ENVELOPE.read_text(encoding="utf-8"))
    if value.get("classification") != "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY":
        raise RuntimeError("authority_envelope_classification_failure")
    return EXPECTED[ENVELOPE]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("Qualification", "Audit"))
    parser.add_argument("--nonce")
    args = parser.parse_args()
    envelope_sha = verify_envelope()
    if args.mode == "Qualification":
        if args.nonce != QUALIFICATION_NONCE:
            raise RuntimeError("qualification_nonce_failure")
        if QUAL_ROOT.exists():
            raise RuntimeError("qualification_root_not_fresh")
        runner = load_exact("rs007_parent_runner", RUNNER)
        runner.IMPL_AUDIT = ENVELOPE
        if runner.QUAL_ROOT.resolve(strict=False) != QUAL_ROOT.resolve(strict=False):
            raise RuntimeError("parent_qualification_root_nonidentity")
        runner.verify_child_boundary(args.nonce)
        return int(runner.qualification(QUAL_ROOT, envelope_sha, args.nonce))
    if QUAL_ROOT.resolve(strict=False) != QUAL_ROOT.resolve(strict=False):
        raise RuntimeError("qualification_root_nonidentity")
    auditor = load_exact("rs007_parent_result_auditor", AUDITOR)
    auditor.IMPL_AUDIT = ENVELOPE
    if auditor.QUAL_ROOT.resolve(strict=False) != QUAL_ROOT.resolve(strict=False):
        raise RuntimeError("parent_audit_root_nonidentity")
    return int(auditor.audit(QUAL_ROOT, envelope_sha))


if __name__ == "__main__":
    raise SystemExit(main())
