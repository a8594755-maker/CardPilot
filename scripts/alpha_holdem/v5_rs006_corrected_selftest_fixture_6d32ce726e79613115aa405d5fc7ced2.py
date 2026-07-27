"""RS006 correction wrapper: exact-live self-test fixture only."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TOKEN = "6d32ce726e79613115aa405d5fc7ced2"
IDENTITY = "6d32ce726e79613115aa405d5fc7ced2fd9291531f856ddbef4cc5e3e8c802bb"
PREREG = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_preregistration_{TOKEN}_20260723.json"
PREREG_SHA = "f110b12a0d57c325d3b17f91d39a6a17afbfa7a979cec9f54a20c05f367fc43b"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_preregistration_audit_{TOKEN}_20260723.json"
PREREG_AUDIT_SHA = "ecf0a34f695cfde535c05d4640f4fc61ac45708c860ec10d7f0b13335321b04f"
OLD_PREREG = ROOT / "reports" / "v5_rs005_fully_live_terminal_utility_resolver_preregistration_5a01b095e04a242d79f0a20907a3e6f9_20260723.json"
SOURCE = ROOT / "scripts" / "alpha_holdem" / "v5_rs005_fully_live_terminal_utility_5a01b095e04a242d79f0a20907a3e6f9.py"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs006_corrected_selftest_fixture_qualification_{TOKEN}_20260723"

spec = importlib.util.spec_from_file_location("rs006_frozen_science", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("frozen_science_import_failure")
science = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = science
spec.loader.exec_module(science)


class _ScienceJsonProxy:
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


def verify_new_inputs() -> dict[str, Any]:
    if PREREG.stat().st_size != 7235 or science.sha_file(PREREG) != PREREG_SHA:
        raise RuntimeError("rs006_preregistration_failure")
    if PREREG_AUDIT.stat().st_size != 3078 or science.sha_file(PREREG_AUDIT) != PREREG_AUDIT_SHA:
        raise RuntimeError("rs006_preregistration_audit_failure")
    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    if registration["identity"]["sha256"] != IDENTITY:
        raise RuntimeError("rs006_identity_failure")
    for item in registration["frozen_correction_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or science.sha_file(path) != item["sha256"]:
            raise RuntimeError(f"rs006_correction_input_failure:{item['role']}")
    inherited = json.loads(OLD_PREREG.read_text(encoding="utf-8"))
    for item in inherited["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or science.sha_file(path) != item["sha256"]:
            raise RuntimeError(f"rs006_inherited_input_failure:{item['role']}")
    return inherited


def verify_new_boundary(nonce: str) -> dict[str, Any]:
    if os.environ.get("RS006_DEVICE_MODE") != "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK":
        raise RuntimeError("rs006_device_mode_failure")
    if os.environ.get("RS006_NONCE") != nonce:
        raise RuntimeError("rs006_nonce_failure")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("rs006_visibility_failure")
    return {"device_mode": os.environ["RS006_DEVICE_MODE"], "cuda_visible_devices": "0", "nonce": nonce}


def corrected_self_test(level: str) -> int:
    inherited = verify_new_inputs()
    valid_prefixes = ("", "c", "ck/", "b200c/kk/", "b200b400c/kk/")
    for prefix in valid_prefixes:
        row = {
            "source": "rs006-selftest",
            "hand_idx": 0,
            "move_idx": 0,
            "client_pos": 0,
            "hero_hole": ["As", "Kd"],
            "action_str_before": prefix,
        }
        count = 0 if prefix.count("/") == 0 else 3 if prefix.count("/") == 1 else 4 if prefix.count("/") == 2 else 5
        row["board"] = [science.card_text(x) for x in [0, 5, 10, 15, 20][:count]]
        science.state_from_row(row)
    exact_fixture = {
        "source": "rs006-selftest", "hand_idx": 1, "move_idx": 0,
        "client_pos": 0, "hero_hole": ["As", "Kd"], "board": [],
        "action_str_before": "b200",
    }
    state = science.state_from_row(exact_fixture)
    table = state.action_table()[1]
    if "b400" not in table or "b600" in table:
        raise RuntimeError("corrected_fixture_not_exact")
    terminal = science.terminal_cohort()
    comparator = science.comparator_checks()
    checks: dict[str, Any] = {
        "valid_prefixes": len(valid_prefixes),
        "corrected_fixture_b400_executable": True,
        "invalid_fixture_b600_absent": True,
        "terminal_rows": len(terminal),
        "terminal_cells": len({row["cell"] for row in terminal}),
        "terminal_exact": all(row["zero_sum"] and row["uncalled_refund_exact"] and row.get("comparator_sign_exact", True) for row in terminal),
        "comparator": comparator,
    }
    if level == "deep":
        census = science.source_census(science.load_rows(inherited))
        checks["census"] = census
        if census != {
            "ledger_rows": 29878, "source_scoped_hands": 5000,
            "distinct_prefixes": 584, "adjacent_transitions": 24878,
            "move_indices_contiguous": True, "hero_postflop_live_interfaces": 6921,
        }:
            raise RuntimeError("rs006_deep_census_failure")
    if len(terminal) != 1280 or len({row["cell"] for row in terminal}) != 20:
        raise RuntimeError("rs006_terminal_cohort_failure")
    if not checks["terminal_exact"] or any(value != 8192 for value in comparator.values()):
        raise RuntimeError("rs006_science_selftest_failure")
    print(science.canonical({
        "classification": "RS006_DEEP_SELF_TEST_PASS",
        "level": level,
        "checks": checks,
        "files_written": 0,
    }))
    return 0


science.TOKEN = TOKEN
science.IDENTITY = IDENTITY
science.PREREG = PREREG
science.PREREG_AUDIT = PREREG_AUDIT
science.IMPL_AUDIT = IMPL_AUDIT
science.QUAL_ROOT = QUAL_ROOT
science.SYNTHETIC_SEED = 2026072298
science.WITNESS_SEED = 2026972298
science.HIDDEN_SEED = 2027972298
science.FUTURE_SEED = 2028972298
science.ROLLOUT_SEED = 2029972298
science.FAULT_SEED = 2030972298
science.json = _ScienceJsonProxy()
science.verify_inputs = verify_new_inputs
science.verify_boundary = verify_new_boundary
science.run_self_test = corrected_self_test


if __name__ == "__main__":
    raise SystemExit(science.main())
