#!/usr/bin/env python3
"""Atomic fail-closed active-window sentinel for H17, including either-arm aborts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


CONTROL = "v5_hybrid_h17_control_catchmse_same35051_20m_r1_20260719"
TREATMENT = "v5_hybrid_h17_treatment_catchsmoothl1b1_same35051_20m_r1_20260719"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: Path) -> dict:
    if not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def lock_is_exact(path: Path, expected: str) -> tuple[bool, dict]:
    if not path.is_file() or sha(path) != expected.lower():
        return False, {}
    value = load(path)
    return value.get("design_id") == "H17" and value.get("status") == "LOCKED", value


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
    exact, _ = lock_is_exact(args.design_lock, args.expected_lock_sha256)
    if not exact:
        raise SystemExit("H17 design-lock identity/hash mismatch")
    current = load(args.sentinel)
    if args.action == "validate":
        valid_prior = not current or current.get("terminal") is True
        valid_h17 = (
            current.get("schema_version") == "v5.active_window.v1"
            and current.get("design_id") == "H17"
            and current.get("design_lock_sha256") == args.expected_lock_sha256.lower()
            and isinstance(current.get("history"), list)
        )
        print(json.dumps({"overall": "PASS" if valid_prior or valid_h17 else "FAIL_CLOSED", "sentinel": current}, indent=2))
        return 0 if valid_prior or valid_h17 else 2
    now = datetime.now(timezone.utc).isoformat()
    if args.action == "activate":
        expected_run = CONTROL if args.arm == "control" else TREATMENT
        if args.run_id != expected_run:
            raise SystemExit("H17 arm/run identity mismatch")
        if args.arm == "control":
            if current and current.get("terminal") is not True:
                raise SystemExit("another nonterminal active window already exists")
            history: list[dict] = []
        else:
            if not (
                current.get("design_id") == "H17"
                and current.get("active") is True
                and current.get("terminal") is False
                and current.get("arm") == "control"
            ):
                raise SystemExit("H17 treatment requires the same active control window")
            history = list(current.get("history") or [])
        history.append({"at": now, "event": f"{args.arm.upper()}_ACTIVATED", "run_id": args.run_id})
        value = {
            "schema_version": "v5.active_window.v1",
            "design_id": "H17",
            "design_lock_path": str(args.design_lock.resolve()),
            "design_lock_sha256": args.expected_lock_sha256.lower(),
            "active": True,
            "terminal": False,
            "state": f"H17_{args.arm.upper()}_ACTIVE",
            "arm": args.arm,
            "run_id": args.run_id,
            "official_hands_authorized": 0,
            "generic_planner_command_emission": "FORBIDDEN",
            "parent_or_delegated_observer_commands": "FORBIDDEN",
            "history": history,
            "updated_at": now,
        }
    else:
        if not args.judgment or not args.judgment.is_file() or not args.verdict:
            raise SystemExit("terminal transition requires verdict and judgment")
        judgment = load(args.judgment)
        judgment_hash = sha(args.judgment)
        if judgment.get("overall") != args.verdict or judgment.get("design_id") != "H17":
            raise SystemExit("H17 judgment identity/verdict mismatch")
        if current.get("terminal") is True:
            same = current.get("verdict") == args.verdict and current.get("judgment_sha256") == judgment_hash
            if not same:
                raise SystemExit("conflicting H17 terminal sentinel")
            print(json.dumps(current, indent=2, sort_keys=True))
            return 0
        if not (
            current.get("design_id") == "H17"
            and current.get("active") is True
            and current.get("terminal") is False
            and current.get("arm") in {"control", "treatment"}
        ):
            raise SystemExit("H17 terminal transition requires an active control or treatment window")
        history = list(current.get("history") or [])
        history.append({
            "at": now,
            "event": "H17_TERMINAL",
            "terminal_from_arm": current.get("arm"),
            "verdict": args.verdict,
            "judgment_path": str(args.judgment.resolve()),
            "judgment_sha256": judgment_hash,
        })
        value = dict(current)
        value.update({
            "active": False,
            "terminal": True,
            "state": f"H17_TERMINAL_{args.verdict}",
            "verdict": args.verdict,
            "judgment_path": str(args.judgment.resolve()),
            "judgment_sha256": judgment_hash,
            "history": history,
            "updated_at": now,
        })
    atomic_write(args.sentinel, value)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
