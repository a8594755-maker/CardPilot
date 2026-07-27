"""Materialize LG004's exact quick5k auditor from the frozen LG003C1 auditor."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/alpha_holdem/v5_lg003c1_quick5k_result_audit_8bf8cedf78b6e8c8fe153802908ed893.py"
OUTPUT = ROOT / "scripts/alpha_holdem/v5_lg004_quick5k_result_audit_8ef9c64242a75f99bfe04d44de5b643b.py"
PARENT_SHA = "d365b11eb29798193c91ce6ea31c5a95759266c491f64f21bec2aed717d84beb"


def main() -> int:
    if hashlib.sha256(PARENT.read_bytes()).hexdigest() != PARENT_SHA:
        raise RuntimeError("parent_hash_mismatch")
    if OUTPUT.exists():
        raise RuntimeError("output_exists")
    text = PARENT.read_text(encoding="utf-8").replace("LG003C1", "LG004").replace("lg003c1", "lg004")
    start = text.index("CHECKPOINT_SHA256 = {")
    end = text.index("\n\n\ndef sha256_path", start)
    replacement = """CHECKPOINT_SHA256 = {
    "treatment_membership": "e1e9ac642c1f042ffb54a8c5593fead584e170959e5a48997ca1abd4006b1a8b",
}
CHECKPOINT_PATH = {
    "treatment_membership": (
        "C:\\\\Users\\\\a8594\\\\CardPilot\\\\models\\\\alpha_holdem_v5_hybrid\\\\"
        "v5_lg004_8ef9c64242a75f99bfe04d44de5b643b_20260723\\\\"
        "treatment_membership_stagea\\\\latest.pt"
    ),
}"""
    text = text[:start] + replacement + text[end:]
    if "control_uniform" in text or "treatment_diversity" in text:
        text = text.replace(
            'len(all_dump_rows) == 32117 if args.arm == "control_uniform" else len(all_dump_rows) > 0',
            "len(all_dump_rows) > 0",
        )
    if "control_uniform" in text or "treatment_diversity" in text:
        raise RuntimeError("obsolete_arm_remains")
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
