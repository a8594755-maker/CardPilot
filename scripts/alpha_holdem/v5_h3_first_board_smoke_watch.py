#!/usr/bin/env python3
"""Wait for the first corrected Path-1 QA-PASS board and run locked H3 smoke twice."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = ROOT / "data" / "cfr" / "pipeline_v3_hu_srp_200bb_legalallin_v2"
PARALLEL_LOG = ASSET_DIR / "parallel-solver.log"
SELECTION_MANIFEST = ASSET_DIR / "path1-selection-manifest.json"
LOCK = ROOT / "reports" / "v5_h3_domain_adapter_design_lock_v3_20260713.json"
EXPORTER = ROOT / "packages" / "cfr-solver" / "src" / "scripts" / "path1-to-v55-bridge-source.ts"
ADAPTER = ROOT / "scripts" / "alpha_holdem" / "v5_h3_domain_adapter.py"
V55_BRIDGE = ROOT / "scripts" / "alpha_holdem" / "v5_h3_v55_bridge.py"
STATUS = ROOT / "reports" / "v5_h3_first_board_smoke_watch_status.json"
RESULT = ROOT / "reports" / "v5_h3_first_corrected_board_smoke_20260713.json"
OUTPUT_ROOT = ROOT / "reports" / "h3_first_board_smoke_20260713"

EXPECTED_LOCK_SHA = "fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e"
EXPECTED_EXPORTER_SHA = "a25de1e2c9c45e7e12a5eade5e20044903128c5d580aedb29e4747d1e54d22b4"
EXPECTED_ADAPTER_SHA = "d3258190a3da6161e9e1394c64ee838638c174f75cacba6659a3e34df376c5d8"
EXPECTED_V55_BRIDGE_SHA = "25ca5a85014bf201166eb0517118dc512e24c52701cbba1abbf9b4551c8044bf"
SMOKE_SCOPE = "SMOKE_PREFIX_ONLY_FORBIDDEN_TRAINING"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.{os.getpid()}.partial")
    partial.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(path)


def qa_pass_board_ids(log_text: str) -> list[int]:
    return [int(value) for value in re.findall(r"board=(\d+) QA_PASS\b", log_text)]


def selected_ids() -> list[int]:
    manifest = json.loads(SELECTION_MANIFEST.read_text(encoding="utf-8"))
    if (
        manifest.get("schema") != "path1_selection_v1"
        or manifest.get("selectionSeed") != 20260712
        or manifest.get("targetBoards") != 600
    ):
        raise ValueError("selection_manifest_identity_mismatch")
    return [int(value) for value in manifest["selectedBoardIds"]]


def first_ready_board() -> int | None:
    if not PARALLEL_LOG.exists():
        return None
    selected = set(selected_ids())
    # The first-board gate is chronological, not numeric. Preserve the append-only
    # solver log order when multiple boards finish between watcher polls.
    for board_id in qa_pass_board_ids(PARALLEL_LOG.read_text(encoding="utf-8")):
        if board_id not in selected:
            continue
        stem = ASSET_DIR / f"flop_{board_id:03d}"
        if Path(f"{stem}.jsonl.gz").exists() and Path(f"{stem}.meta.json").exists():
            return board_id
    return None


def creation_flags() -> int:
    if os.name != "nt":
        return 0
    return 0x08000000 | 0x00004000  # CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS


def subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    scripts_root = str((ROOT / "scripts").resolve())
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = scripts_root if not existing else scripts_root + os.pathsep + existing
    env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def run_logged(command: list[str], stdout_path: Path, stderr_path: Path) -> None:
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            check=False,
            creationflags=creation_flags(),
            env=subprocess_env(),
        )
    if completed.returncode != 0:
        raise RuntimeError(f"subprocess_failed:{completed.returncode}:{' '.join(command[:4])}")


def array_content_sha(manifest: dict) -> str:
    digest = hashlib.sha256()
    for shard in manifest["shards"]:
        with np.load(shard["path"], allow_pickle=False) as arrays:
            for key in sorted(arrays.files):
                array = arrays[key]
                digest.update(key.encode("utf-8"))
                digest.update(str(array.dtype).encode("ascii"))
                digest.update(json.dumps(array.shape).encode("ascii"))
                digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def compare_adapter_runs(a_manifest_path: Path, b_manifest_path: Path) -> dict:
    a = json.loads(a_manifest_path.read_text(encoding="utf-8"))
    b = json.loads(b_manifest_path.read_text(encoding="utf-8"))
    for label, manifest in (("a", a), ("b", b)):
        if manifest.get("overall") != "PASS_CONVERTED":
            raise ValueError(f"adapter_{label}_not_pass")
        if manifest.get("bridge_scope") != SMOKE_SCOPE or manifest.get("training_eligible") is not False:
            raise ValueError(f"adapter_{label}_scope_authority_violation")
        if manifest.get("critic_rows") != 0 or manifest.get("behavior_launch_authorized") is not False:
            raise ValueError(f"adapter_{label}_behavior_or_critic_authority_violation")
        if manifest.get("official_hands_authorized") != 0:
            raise ValueError(f"adapter_{label}_official_authority_violation")
        risk = manifest.get("projection_risk", {})
        if (
            risk.get("unsupported_target_mass") != 0.0
            or risk.get("sized_actions_mapped_to_allin") != 0
            or risk.get("snapshot_roundtrip_mismatches") != 0
            or float(risk.get("maximum_amount_error_over_source_pot", float("inf"))) > 0.5
        ):
            raise ValueError(f"adapter_{label}_snapshot_projection_gate_fail")
    if a["rows"] != b["rows"]:
        raise ValueError("adapter_row_count_mismatch")
    if a["projection_risk"] != b["projection_risk"]:
        raise ValueError("adapter_projection_risk_not_deterministic")
    a_provenance = Path(a["provenance"]["path"])
    b_provenance = Path(b["provenance"]["path"])
    if a_provenance.read_bytes() != b_provenance.read_bytes():
        raise ValueError("adapter_provenance_not_deterministic")
    a_content = array_content_sha(a)
    b_content = array_content_sha(b)
    if a_content != b_content:
        raise ValueError("adapter_array_content_not_deterministic")
    return {
        "rows": a["rows"],
        "provenance_sha256": sha256(a_provenance),
        "array_content_sha256": a_content,
        "training_eligible": False,
        "critic_rows": 0,
        "projection_risk": a["projection_risk"],
    }


def verify_code_identity() -> None:
    identities = {
        "lock": (LOCK, EXPECTED_LOCK_SHA),
        "exporter": (EXPORTER, EXPECTED_EXPORTER_SHA),
        "adapter": (ADAPTER, EXPECTED_ADAPTER_SHA),
        "v55_bridge": (V55_BRIDGE, EXPECTED_V55_BRIDGE_SHA),
    }
    for name, (path, expected) in identities.items():
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"{name}_sha256_mismatch:{actual}")


def preserve_interrupted_output() -> None:
    if not OUTPUT_ROOT.exists():
        return
    if RESULT.exists():
        existing = json.loads(RESULT.read_text(encoding="utf-8"))
        if existing.get("overall") == "PASS_FIRST_CORRECTED_BOARD_DETERMINISTIC_SMOKE":
            return
    destination = OUTPUT_ROOT.with_name(f"{OUTPUT_ROOT.name}.interrupted-{int(time.time())}")
    OUTPUT_ROOT.replace(destination)


def execute_smoke(board_id: int, smoke_rows: int) -> dict:
    verify_code_identity()
    preserve_interrupted_output()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node_not_found")
    stem = ASSET_DIR / f"flop_{board_id:03d}"
    gz = Path(f"{stem}.jsonl.gz").resolve()
    meta = Path(f"{stem}.meta.json").resolve()
    bridge_paths: list[Path] = []
    adapter_manifests: list[Path] = []
    for label in ("a", "b"):
        run_dir = OUTPUT_ROOT / label
        run_dir.mkdir()
        bridge = run_dir / "bridge.jsonl"
        bridge_manifest = run_dir / "bridge_manifest.json"
        run_logged(
            [
                node,
                "--max-old-space-size=8192",
                "--import",
                "tsx",
                str(EXPORTER.resolve()),
                "--board-gz",
                str(gz),
                "--board-meta",
                str(meta),
                "--output-jsonl",
                str(bridge.resolve()),
                "--manifest",
                str(bridge_manifest.resolve()),
                "--smoke-prefix-rows",
                str(smoke_rows),
            ],
            run_dir / "bridge_stdout.log",
            run_dir / "bridge_stderr.log",
        )
        bridge_result = json.loads(bridge_manifest.read_text(encoding="utf-8"))
        if (
            bridge_result.get("status") != "PASS_SMOKE_PREFIX_FORBIDDEN_TRAINING"
            or bridge_result.get("training_eligible") is not False
            or bridge_result.get("output_rows") != smoke_rows
        ):
            raise ValueError(f"bridge_{label}_scope_or_row_gate_fail")
        adapter_out = run_dir / "adapter"
        adapter_manifest = run_dir / "adapter_manifest.json"
        run_logged(
            [
                sys.executable,
                str(ADAPTER.resolve()),
                "--source-jsonl",
                str(bridge.resolve()),
                "--out-dir",
                str(adapter_out.resolve()),
                "--manifest",
                str(adapter_manifest.resolve()),
                "--shard-rows",
                str(smoke_rows),
            ],
            run_dir / "adapter_stdout.log",
            run_dir / "adapter_stderr.log",
        )
        bridge_paths.append(bridge)
        adapter_manifests.append(adapter_manifest)
    bridge_hashes = [sha256(path) for path in bridge_paths]
    if bridge_hashes[0] != bridge_hashes[1]:
        raise ValueError("bridge_jsonl_not_deterministic")
    adapter_comparison = compare_adapter_runs(*adapter_manifests)
    return {
        "schema_version": "v5.hybrid.h3.first_corrected_board_smoke.v1",
        "checked_at": now(),
        "overall": "PASS_FIRST_CORRECTED_BOARD_DETERMINISTIC_SMOKE",
        "board_id": board_id,
        "source_board_gz": str(gz),
        "source_board_sha256": sha256(gz),
        "source_board_meta": str(meta),
        "source_board_meta_sha256": sha256(meta),
        "design_lock_v3_sha256": EXPECTED_LOCK_SHA,
        "exporter_sha256": EXPECTED_EXPORTER_SHA,
        "adapter_sha256": EXPECTED_ADAPTER_SHA,
        "v55_bridge_sha256": EXPECTED_V55_BRIDGE_SHA,
        "smoke_rows": smoke_rows,
        "bridge_jsonl_sha256": bridge_hashes[0],
        "bridge_repeat_exact": True,
        "adapter_repeat": adapter_comparison,
        "required_provenance_label": "SYNTHETIC_PATH1_SRP_ENTRY_OOD_NOT_DEPLOYMENT_REACHABLE",
        "training_eligible": False,
        "h3_preregistration_authorized": False,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "next": "active handoff must append the PASS event; full 600-board validation remains required",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--smoke-rows", type=int, default=1000)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.smoke_rows <= 0 or args.smoke_rows > 10000:
        raise ValueError("smoke_rows_out_of_locked_range")
    if RESULT.exists():
        result = json.loads(RESULT.read_text(encoding="utf-8"))
        if result.get("overall") == "PASS_FIRST_CORRECTED_BOARD_DETERMINISTIC_SMOKE":
            atomic_json(STATUS, {"checked_at": now(), "overall": "PASS", "state": "ALREADY_COMPLETE", "result": str(RESULT)})
            return 0
    try:
        verify_code_identity()
        while True:
            board_id = first_ready_board()
            if board_id is None:
                atomic_json(
                    STATUS,
                    {
                        "schema_version": "v5.hybrid.h3.first_board_smoke_watch.v1",
                        "checked_at": now(),
                        "overall": "PENDING",
                        "state": "WAITING_FIRST_QA_PASS_BOARD",
                        "pid": os.getpid(),
                        "smoke_rows": args.smoke_rows,
                        "behavior_launch_authorized": False,
                        "official_hands_authorized": 0,
                    },
                )
                if args.once:
                    return 0
                time.sleep(max(1.0, args.poll_seconds))
                continue
            atomic_json(STATUS, {"checked_at": now(), "overall": "RUNNING", "state": "EXECUTING_LOCKED_SMOKE", "board_id": board_id, "pid": os.getpid()})
            result = execute_smoke(board_id, args.smoke_rows)
            atomic_json(RESULT, result)
            atomic_json(STATUS, {"checked_at": now(), "overall": "PASS", "state": "TERMINAL_PASS_HANDOFF_UPDATE_REQUIRED", "board_id": board_id, "pid": os.getpid(), "result": str(RESULT)})
            return 0
    except Exception as error:
        failure = {
            "schema_version": "v5.hybrid.h3.first_board_smoke_watch.v1",
            "checked_at": now(),
            "overall": "FAIL_CLOSED",
            "state": "TERMINAL_FAILURE_REQUIRES_CORRECTION",
            "error": str(error),
            "pid": os.getpid(),
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
        }
        atomic_json(STATUS, failure)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
