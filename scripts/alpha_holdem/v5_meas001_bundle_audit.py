#!/usr/bin/env python3
"""Independent artifact audit for a completed MEAS-001 evaluation bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from v5_meas001_common_deal_eval import (  # noqa: E402
    audit_completed_bundle,
    utc_now,
    write_json_exclusive,
    write_text_exclusive,
)


def write_markdown(audit: dict, path: Path) -> None:
    lines = [
        "# MEAS-001 Bundle Audit",
        "",
        f"- Checked at: `{audit['checked_at']}`",
        f"- Status: `{audit['status']}`",
        f"- Measurement status: `{audit.get('measurement_status')}`",
        f"- Pairs: `{audit.get('pairs')}`",
        "",
        "This audit validates method-measurement artifacts only. It does not support a Slumbot, V4, L5, or L6 claim.",
        "",
        "## Errors",
        "",
    ]
    if audit.get("errors"):
        lines.extend(f"- {error}" for error in audit["errors"])
    else:
        lines.append("- None")
    write_text_exclusive(path, "\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a terminal MEAS-001 artifact bundle")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-bundle", required=True)
    parser.add_argument("--pairs-jsonl", required=True)
    parser.add_argument("--execution", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    audit = audit_completed_bundle(
        summary_path=Path(args.summary),
        manifest_path=Path(args.manifest),
        source_bundle_path=Path(args.source_bundle),
        pairs_jsonl_path=Path(args.pairs_jsonl),
        execution_path=Path(args.execution),
    )
    audit.update(
        {
            "checked_at": utc_now(),
            "design_id": "MEAS-001",
            "claim_scope": "method_measurement_only_not_slumbot_not_v4_l5_l6",
        }
    )
    rendered = json.dumps(audit, indent=2, sort_keys=True)
    print(rendered)
    if args.out_json:
        write_json_exclusive(Path(args.out_json), audit)
    if args.out_md:
        write_markdown(audit, Path(args.out_md))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
