#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("v5_hybrid_h11_terminal_health_recovery.py")
SPEC = importlib.util.spec_from_file_location("h11_health_recovery", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_compatible_log_removes_only_vhcatch_token() -> None:
    source = "[1] klstop=1 vhcatch=3 clipfrac=0.2 vhcatch_extra=9\n"
    transformed, count = MODULE.compatible_log(source)
    assert count == 1
    assert transformed == "[1] klstop=1 clipfrac=0.2 vhcatch_extra=9\n"


def test_compatible_log_rejects_no_false_matches() -> None:
    source = "vhcatch=3 prefix_vhcatch=2 vhcatch=x\n"
    transformed, count = MODULE.compatible_log(source)
    assert count == 0
    assert transformed == source


def test_preserve_is_idempotent_and_hash_bound(tmp_path: Path) -> None:
    source = tmp_path / "status.json"
    source.write_text('{"overall":"FAIL"}\n', encoding="utf-8")
    destination = tmp_path / "preserved"
    first = MODULE.preserve([source], destination)
    second = MODULE.preserve([source], destination)
    assert first[0]["sha256"] == second[0]["snapshot_sha256"]
    assert (destination / source.name).read_bytes() == source.read_bytes()


def test_preserve_fails_closed_on_snapshot_conflict(tmp_path: Path) -> None:
    source = tmp_path / "status.json"
    source.write_text("one", encoding="utf-8")
    destination = tmp_path / "preserved"
    destination.mkdir()
    (destination / source.name).write_text("two", encoding="utf-8")
    try:
        MODULE.preserve([source], destination)
    except ValueError as exc:
        assert "conflict" in str(exc)
    else:
        raise AssertionError("snapshot conflict must fail closed")
