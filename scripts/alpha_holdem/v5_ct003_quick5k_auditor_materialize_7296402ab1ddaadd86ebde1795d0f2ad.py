"""Materialize CT003's exact quick5k auditor from the frozen LG004 auditor."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/alpha_holdem/v5_lg004_quick5k_result_audit_8ef9c64242a75f99bfe04d44de5b643b.py"
OUTPUT = ROOT / "scripts/alpha_holdem/v5_ct003_quick5k_result_audit_7296402ab1ddaadd86ebde1795d0f2ad.py"
PARENT_SHA = "e435924923447395fbfcf1916728c2501bea62f8c601143f5c78e029585820b4"


def main() -> int:
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("parent_hash_mismatch")
    if OUTPUT.exists():
        raise RuntimeError("output_exists")
    text = PARENT.read_text(encoding="utf-8").replace("LG004", "CT003").replace("lg004", "ct003")
    start = text.index("CHECKPOINT_SHA256 = {")
    end = text.index("\n\n\ndef sha256_path", start)
    replacement = """CHECKPOINT_SHA256 = {
    "ct003_mc_target": "76b85c5bd377533329424140d01352075e44b6a1aeb5796828fee60f34037f62",
}
CHECKPOINT_PATH = {
    "ct003_mc_target": (
        "C:\\\\Users\\\\a8594\\\\CardPilot\\\\models\\\\alpha_holdem_v5_hybrid\\\\"
        "v5_ct003_7296402ab1ddaadd86ebde1795d0f2ad_20260723\\\\"
        "mc_target_stagea\\\\latest.pt"
    ),
}"""
    text = text[:start] + replacement + text[end:]
    text = text.replace(
        '"REGISTERED_STAGE_A_TREATMENT_FROM_EXACT_H11_START"',
        '"REGISTERED_CT003_STAGE_A_GATE_JUDGMENT"',
    )
    if "treatment_membership" in text or "v5_lg004" in text or "LG004" in text:
        raise RuntimeError("obsolete_parent_identity_remains")
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
