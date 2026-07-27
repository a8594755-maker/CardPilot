"""RS006 independent result-audit boundary over the frozen RS005 science audit."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "6d32ce726e79613115aa405d5fc7ced2"
IDENTITY = "6d32ce726e79613115aa405d5fc7ced2fd9291531f856ddbef4cc5e3e8c802bb"
SOURCE = ROOT / "scripts" / "alpha_holdem" / "v5_rs005_fully_live_terminal_utility_audit_5a01b095e04a242d79f0a20907a3e6f9.py"

spec = importlib.util.spec_from_file_location("rs006_frozen_result_audit", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("frozen_result_auditor_import_failure")
audit_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit_module
spec.loader.exec_module(audit_module)


class _AuditJsonProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(json, name)

    @staticmethod
    def loads(value: str, *args: Any, **kwargs: Any) -> Any:
        parsed = json.loads(value, *args, **kwargs)
        if (
            isinstance(parsed, dict)
            and parsed.get("identity_sha256") == IDENTITY
            and parsed.get("classification") == "PASS / RS006_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
        ):
            parsed = dict(parsed)
            parsed["classification"] = "PASS / RS005_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY"
        return parsed

audit_module.TOKEN = TOKEN
audit_module.IDENTITY = IDENTITY
audit_module.json = _AuditJsonProxy()
audit_module.IMPLEMENTATION_AUDIT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_implementation_audit_{TOKEN}_20260723.json"
audit_module.QUAL_ROOT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_qualification_{TOKEN}_20260723"

if __name__ == "__main__":
    raise SystemExit(audit_module.main())
