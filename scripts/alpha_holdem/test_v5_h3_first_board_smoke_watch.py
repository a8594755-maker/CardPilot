#!/usr/bin/env python3
"""Focused parser/content-determinism tests for the H3 first-board smoke watcher."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import os

import numpy as np

from alpha_holdem.v5_h3_first_board_smoke_watch import (
    EXPECTED_V55_BRIDGE_SHA,
    SMOKE_SCOPE,
    V55_BRIDGE,
    array_content_sha,
    compare_adapter_runs,
    qa_pass_board_ids,
    sha256,
    subprocess_env,
    verify_code_identity,
)


def write_adapter_fixture(root: Path, label: str, *, mutate: bool = False) -> Path:
    out = root / label
    out.mkdir()
    shard = out / "actor_rows_00000.npz"
    value = 2.0 if mutate else 1.0
    np.savez_compressed(shard, card_info=np.asarray([[value]], dtype=np.float32), actor_target=np.asarray([[1.0]], dtype=np.float32))
    provenance = out / "provenance.jsonl"
    provenance.write_text('{"row":1}\n', encoding="utf-8")
    manifest = {
        "overall": "PASS_CONVERTED",
        "bridge_scope": SMOKE_SCOPE,
        "training_eligible": False,
        "critic_rows": 0,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "projection_risk": {
            "unsupported_target_mass": 0.0,
            "sized_actions_mapped_to_allin": 0,
            "snapshot_roundtrip_mismatches": 0,
            "maximum_amount_error_over_source_pot": 0.1,
        },
        "rows": 1,
        "shards": [{"path": str(shard)}],
        "provenance": {"path": str(provenance)},
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def main() -> int:
    verify_code_identity()
    assert sha256(V55_BRIDGE) == EXPECTED_V55_BRIDGE_SHA
    child_env = subprocess_env()
    assert child_env["PYTHONPATH"].split(os.pathsep)[0] == str((Path(__file__).resolve().parents[1]).resolve())
    assert child_env["CUDA_VISIBLE_DEVICES"] == ""
    assert qa_pass_board_ids("board=6 QA_PASS x\nboard=5 QA_FAIL\nboard=2 QA_PASS") == [6, 2]
    assert qa_pass_board_ids("QA_PASS board=2") == []
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        a = write_adapter_fixture(root, "a")
        b = write_adapter_fixture(root, "b")
        result = compare_adapter_runs(a, b)
        assert result["rows"] == 1
        assert result["training_eligible"] is False
        assert result["critic_rows"] == 0
        assert result["projection_risk"]["unsupported_target_mass"] == 0.0
        assert len(result["array_content_sha256"]) == 64
        assert array_content_sha(json.loads(a.read_text())) == array_content_sha(json.loads(b.read_text()))
        c = write_adapter_fixture(root, "c", mutate=True)
        try:
            compare_adapter_runs(a, c)
            raise AssertionError("mutated adapter arrays passed")
        except ValueError as error:
            assert "array_content_not_deterministic" in str(error)
        bad = json.loads(b.read_text())
        bad["training_eligible"] = True
        b.write_text(json.dumps(bad), encoding="utf-8")
        try:
            compare_adapter_runs(a, b)
            raise AssertionError("smoke training authority passed")
        except ValueError as error:
            assert "scope_authority" in str(error)
        b = write_adapter_fixture(root, "d")
        bad_risk = json.loads(b.read_text())
        bad_risk["projection_risk"]["unsupported_target_mass"] = 0.1
        b.write_text(json.dumps(bad_risk), encoding="utf-8")
        try:
            compare_adapter_runs(a, b)
            raise AssertionError("unsupported projection risk passed")
        except ValueError as error:
            assert "projection_gate" in str(error)
    print("PASS 20/20 H3 first-board smoke watcher parser/content/scope/snapshot-risk/identity/env assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
