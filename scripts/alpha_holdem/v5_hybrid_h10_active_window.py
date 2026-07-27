#!/usr/bin/env python3
"""Atomic fail-closed active-window sentinel for the registered H10 lifecycle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


CONTROL = "v5_hybrid_h10_control_catchmse_same33834_20m_r1_20260715"
TREATMENT = "v5_hybrid_h10_treatment_catchsmoothl1b1_same33834_20m_r1_20260715"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: Path) -> dict:
    if not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_write(path: Path, value: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activate", "terminal", "validate"))
    parser.add_argument("--sentinel", type=Path, required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--arm", choices=("control", "treatment"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--verdict", choices=("PASS", "FAIL", "INCONCLUSIVE"))
    parser.add_argument("--judgment", type=Path)
    args = parser.parse_args()

    lock = load(args.design_lock)
    if (
        sha(args.design_lock) != args.expected_lock_sha256.lower()
        or lock.get("design_id") != "H10"
        or lock.get("status") != "LOCKED"
    ):
        raise SystemExit("H10 design-lock identity/hash mismatch")
    current = load(args.sentinel)

    if args.action == "validate":
        valid = not current or (
            current.get("schema_version") == "v5.active_window.v1"
            and current.get("design_id") == "H10"
            and current.get("design_lock_sha256") == args.expected_lock_sha256.lower()
            and isinstance(current.get("history"), list)
        )
        print(json.dumps({"overall": "PASS" if valid else "FAIL_CLOSED", "sentinel": current}, indent=2))
        return 0 if valid else 2

    now = datetime.now(timezone.utc).isoformat()
    if args.action == "activate":
        expected_run = CONTROL if args.arm == "control" else TREATMENT
        if args.run_id != expected_run:
            raise SystemExit("H10 arm/run identity mismatch")
        if args.arm == "control":
            if current and not current.get("terminal"):
                raise SystemExit("another nonterminal active window already exists")
            history: list[dict] = []
        else:
            if not (
                current.get("design_id") == "H10"
                and current.get("active") is True
                and current.get("terminal") is False
                and current.get("arm") == "control"
            ):
                raise SystemExit("H10 treatment requires the same active control window")
            history = list(current.get("history") or [])
        history.append({"at": now, "event": f"{args.arm.upper()}_ACTIVATED", "run_id": args.run_id})
        value = {
            "schema_version": "v5.active_window.v1",
            "design_id": "H10",
            "design_lock_path": str(args.design_lock.resolve()),
            "design_lock_sha256": args.expected_lock_sha256.lower(),
            "active": True,
            "terminal": False,
            "state": f"H10_{args.arm.upper()}_ACTIVE",
            "arm": args.arm,
            "run_id": args.run_id,
            "official_hands_authorized": 0,
            "generic_planner_command_emission": "FORBIDDEN",
            "history": history,
            "updated_at": now,
        }
    else:
        if current.get("terminal") is True:
            same = (
                args.judgment is not None
                and args.judgment.is_file()
                and current.get("verdict") == args.verdict
                and current.get("judgment_sha256") == sha(args.judgment)
            )
            if not same:
                raise SystemExit("conflicting H10 terminal sentinel")
            print(json.dumps(current, indent=2, sort_keys=True))
            return 0
        if not (
            current.get("design_id") == "H10"
            and current.get("active") is True
            and current.get("terminal") is False
            and current.get("arm") == "treatment"
        ):
            raise SystemExit("H10 terminal transition requires an active treatment window")
        if not args.judgment or not args.judgment.is_file() or not args.verdict:
            raise SystemExit("terminal transition requires verdict and judgment")
        judgment = load(args.judgment)
        if judgment.get("overall") != args.verdict or judgment.get("design_id") != "H10":
            raise SystemExit("H10 judgment identity/verdict mismatch")
        history = list(current.get("history") or [])
        history.append({
            "at": now,
            "event": "H10_TERMINAL",
            "verdict": args.verdict,
            "judgment_path": str(args.judgment.resolve()),
            "judgment_sha256": sha(args.judgment),
        })
        value = dict(current)
        value.update({
            "active": False,
            "terminal": True,
            "state": f"H10_TERMINAL_{args.verdict}",
            "verdict": args.verdict,
            "judgment_path": str(args.judgment.resolve()),
            "judgment_sha256": sha(args.judgment),
            "history": history,
            "updated_at": now,
        })
    atomic_write(args.sentinel, value)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
