#!/usr/bin/env python3
"""Focused identity and tamper tests for the H3 adapter v2 lock audit."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from alpha_holdem.v5_h3_domain_adapter_design_lock_v2_audit import LOCK, audit


def main() -> int:
    passed = audit()
    assert passed["overall"] == "PASS_IMMUTABLE_OFFLINE_CORRECTION_LOCK"
    assert passed["assertions_passed"] == passed["assertions_total"] == 20
    with tempfile.TemporaryDirectory() as temp:
        tampered_path = Path(temp) / "lock.json"
        tampered = json.loads(LOCK.read_text(encoding="utf-8"))
        tampered["behavior_launch_authorized"] = True
        tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
        failed = audit(tampered_path)
        assert failed["overall"] == "FAIL_CLOSED"
        assert failed["checks"]["lock_sha"] is False
        assert failed["checks"]["no_behavior_authority"] is False
    print("PASS 23/23 H3 domain-adapter v2 lock identity/tamper assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
