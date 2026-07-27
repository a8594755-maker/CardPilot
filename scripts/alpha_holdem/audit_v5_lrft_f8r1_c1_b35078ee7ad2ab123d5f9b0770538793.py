"""Fresh C1 correction for the LRFT-F8R1 implementation auditor.

The frozen parent auditor's first process terminated before emitting a probe result
because its isolated child could not resolve the repository import graph.  It wrote
no audit report and created no F8R1 output.  The final runner now establishes the
repository root in the fresh child itself and binds this C1 auditor/report path.

This wrapper preserves the parent's independent checks and exactly-two-probe main,
changing only its frozen runner SHA/byte binding, exclusive C1 report path, and
append-only correction lineage.
"""

from __future__ import annotations

import hashlib
import json as standard_json
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
PARENT = (
    ROOT
    / "scripts"
    / "alpha_holdem"
    / f"audit_v5_lrft_f8r1_{TOKEN}.py"
)
PARENT_SHA256 = (
    "f12a8d0e47ee0501ce9181d5fe19eb495127476a4e30b3f2496be6fec6c57a6e"
)
FINAL_RUNNER_SHA256 = (
    "579a0d0ecc4c85a9e8a5600b6128717e2752caccbed3daba1779cd254d18fc95"
)
FINAL_RUNNER_BYTES = 76_276
FAILED_PARENT_REPORT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_implementation_audit_{TOKEN}_20260723.json"
)
FAILED_PARENT_OUTPUT_ROOT = ROOT / "reports" / f"lrft_f8r1_{TOKEN}"
C1_REPORT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_implementation_audit_c1_{TOKEN}_20260723.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class JsonProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(standard_json, name)

    def dump(self, value: Any, stream: Any, **kwargs: Any) -> None:
        if (
            isinstance(value, dict)
            and value.get("schema_version")
            == "v5.lrft_f8r1.implementation_audit.v1"
        ):
            value = dict(value)
            value["correction_lineage"] = {
                "parent_auditor": {
                    "path": str(PARENT),
                    "sha256": PARENT_SHA256,
                },
                "parent_failure": (
                    "PREOUTPUT_ISOLATED_IMPORT_PATH_FAILURE_NO_REPORT_"
                    "NO_MODEL_NO_RESOURCE_NO_SCIENCE"
                ),
                "parent_report_absent_before_c1": True,
                "parent_output_root_absent_before_c1": True,
                "scientific_design_changed": False,
                "runner_final_sha256": FINAL_RUNNER_SHA256,
                "runner_final_bytes": FINAL_RUNNER_BYTES,
            }
        standard_json.dump(value, stream, **kwargs)


def corrected_source() -> str:
    raw = PARENT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PARENT_SHA256:
        raise RuntimeError("frozen parent auditor mismatch")
    if FAILED_PARENT_REPORT.exists():
        raise RuntimeError("failed parent unexpectedly has an audit report")
    if FAILED_PARENT_OUTPUT_ROOT.exists():
        raise RuntimeError("F8R1 output root exists before C1")
    if C1_REPORT.exists():
        raise RuntimeError(f"refusing to overwrite {C1_REPORT}")
    source = raw.decode("utf-8")
    replacements = (
        (
            'f"v5_lrft_f8r1_implementation_audit_{TOKEN}_20260723.json"',
            'f"v5_lrft_f8r1_implementation_audit_c1_{TOKEN}_20260723.json"',
        ),
        (
            "98d451266c228f264a3b4de0efa46efce26348538c807bf38b1153a4557d328c",
            FINAL_RUNNER_SHA256,
        ),
        ("len(runner_raw) == 74_757", "len(runner_raw) == 76_276"),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise RuntimeError(f"parent correction anchor count is not one: {old}")
        source = source.replace(old, new, 1)
    return source


def main() -> int:
    runner = ROOT / "scripts" / "alpha_holdem" / f"v5_lrft_f8r1_{TOKEN}.py"
    if sha256(runner) != FINAL_RUNNER_SHA256 or runner.stat().st_size != FINAL_RUNNER_BYTES:
        raise RuntimeError("final runner identity mismatch")
    namespace: dict[str, Any] = {
        "__file__": str(Path(__file__).resolve()),
        "__name__": "lrft_f8r1_c1_auditor_body",
        "__package__": None,
    }
    source = corrected_source()
    exec(compile(source, str(Path(__file__).resolve()), "exec"), namespace)
    namespace["json"] = JsonProxy()
    return int(namespace["main"]())


if __name__ == "__main__":
    raise SystemExit(main())
