#!/usr/bin/env python3
"""Launch the fixed EXP-003 post-cutover mirror roles, without touching training.

The watcher waits for ``v5_exp003_freeze_watch.py`` to freeze the registered
first eligible checkpoint, verifies every immutable input, and then runs the
two remaining CPU mirror roles sequentially.  It is deliberately not a
judgment runner: its only successful terminal state is ``REVIEW_READY`` from
the canonical next-action-queue validator.

Existing artifacts are immutable.  A usable role is reused; any partial,
failed, or otherwise unusable artifact set is preserved and causes a terminal
failure instead of being overwritten or hidden by a retry.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR))

from v5_next_action_queue import (
    EXP003_CUTOVER_HANDS,
    EXP003_CUTOVER_ITERATION,
    EXP003_CI_PRECISION_FAILED,
    EXP003_EVALUATOR_SHA256,
    EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION,
    EXP003_LEGACY_PRE_RESULT_NAME,
    EXP003_LEGACY_PRE_RUN_ID,
    EXP003_LEGACY_PRE_SCHEMA_VERSION,
    EXP003_MIRROR_OOD_MAX,
    EXP003_MIRROR_PAIRS,
    EXP003_MIRROR_POLICY_MODE,
    EXP003_MIRROR_SEED,
    EXP003_NATIVE_MIRROR_TARGET_HANDS,
    EXP003_NATIVE_ANCHOR_HANDS,
    EXP003_NATIVE_SHA256,
    EXP003_PRE_SHA256,
    _exp003_mirror_record,
    exp003_mirror_bundle_status,
)
from v5_checkpoint_archive_watch import checkpoint_summary
from v5_ops_log_watch import append_event_row


SCHEMA_VERSION = "v5.exp003.bundle_watch.v1"
CONTENTION_REAUDIT_SCHEMA_VERSION = "v5.exp003.contention_reaudit.v1"
LEGACY_PREFLIGHT_CONTRACT_SCHEMA_VERSION = "v5.exp003.pre_vs_native.legacy_preflight_contract.v1"
# This is a one-off forensic allowlist for the historical false positive at
# gate24900.  It is intentionally *not* a general PowerShell exception: all
# four observer identities must match the saved raw event exactly.
CAPTURED_FALSE_POSITIVE_OBSERVER = {
    "command_line_sha256": "44c3ed8b57ec746601e187d31dded536e9a623d532128050779f216deb423b0c",
    "script_sha256": "a7ba0c5f2fd8e44c0200472e5b3a2f00fb442a275e66d41709e160d43e155cba",
    "pid": 24724,
    "creation_date": "/Date(1783638953136)/",
    "checked_at": "2026-07-09T23:15:53.851103+00:00",
    "snapshot_sha256": "c9a31754090c9ad844e5d2ea452c7f6d11e9ea1d21d1b819bac01bd646fbf231",
    "launcher_sha256": "2b13d4f25c9a7eb179f4909b01548c47dba4eaa86cc157768b458dd49b03b9f7",
    "quarantine_sha256": "70ab1895b4fe42896ab48f564ac52dec37014428908025ef365e8b167db0a848",
}
CAPTURED_FALSE_POSITIVE_FREEZE = {
    "gate_iteration": 24900,
    "gate_hands": 409_058_520,
    "archive_sha256": "060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020",
}
EVALUATOR_PATH = THIS_DIR / "v5_mirror_eval.py"
PRE_CHECKPOINT_PATH = (
    REPO_ROOT
    / "models"
    / "bench_v55_v5_v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709_iter21800_358M_promotion20k_checkpoint.pt"
)
NATIVE_CHECKPOINT_PATH = (
    REPO_ROOT
    / "models"
    / "bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_iter4600_75M_quick5k_checkpoint.pt"
)
STARTING_STACK = 200.0
DEVICE = "cpu"
PRIORITY = "below-normal"
TORCH_THREADS = 1
TORCH_INTEROP_THREADS = 1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"_missing": True, "path": str(path)}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # status payloads must fail closed
        return {"_load_error": f"{type(exc).__name__}: {exc}", "path": str(path)}
    if not isinstance(value, dict):
        return {"_load_error": "JSON root is not an object", "path": str(path)}
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _same_path(left: Any, right: Path) -> bool:
    try:
        return Path(str(left)).resolve() == right.resolve()
    except (OSError, ValueError):
        return False


class SingleInstanceLock:
    """Small PID-file lock with stale-owner recovery and exclusive creation."""

    def __init__(
        self,
        path: Path,
        identity_lookup: Callable[[int], dict[str, Any] | None] | None = None,
    ):
        self.path = Path(path)
        self.owned = False
        self.identity_lookup = identity_lookup or process_identity
        self.owner_token = uuid.uuid4().hex

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                previous = load_json(self.path)
                if previous.get("_missing") or previous.get("_load_error"):
                    raise RuntimeError(
                        "bundle watcher lock exists but is partial/unreadable; fail-closed until a complete owner can be audited"
                    )
                owner = _int(previous.get("pid"))
                complete_owner = bool(
                    owner is not None
                    and previous.get("owner_token")
                    and previous.get("creation_date")
                    and previous.get("command_line")
                )
                if not complete_owner:
                    raise RuntimeError(
                        "bundle watcher lock has incomplete owner identity; fail-closed instead of deleting a possible creation race"
                    )
                try:
                    live = self.identity_lookup(owner)
                except Exception as exc:
                    raise RuntimeError(
                        f"bundle watcher lock owner lookup failed; fail-closed: {type(exc).__name__}: {exc}"
                    ) from exc
                same_creation = bool(
                    live
                    and previous.get("creation_date")
                    and str(previous.get("creation_date")) == str(live.get("creation_date"))
                )
                same_command = bool(
                    live
                    and previous.get("command_line")
                    and str(previous.get("command_line")) == str(live.get("command_line"))
                )
                if live and (same_creation and same_command):
                    raise RuntimeError(
                        f"bundle watcher lock is held by exact live process PID {owner} "
                        f"CreationDate={live.get('creation_date')}"
                    )
                if live and same_creation:
                    raise RuntimeError(
                        f"bundle watcher lock PID {owner} is live but identity differs; fail-closed against PID/metadata races"
                    )
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            try:
                identity = self.identity_lookup(os.getpid())
            except Exception:
                os.close(descriptor)
                self.path.unlink(missing_ok=True)
                raise
            if not identity or not identity.get("creation_date") or not identity.get("command_line"):
                os.close(descriptor)
                self.path.unlink(missing_ok=True)
                raise RuntimeError("cannot create exact lock owner identity; no lock was claimed")
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(
                    {
                        "pid": os.getpid(),
                        "owner_token": self.owner_token,
                        "creation_date": identity.get("creation_date"),
                        "command_line": identity.get("command_line"),
                        "acquired_at": now_iso(),
                    },
                    handle,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.owned = True
            return
        raise RuntimeError("could not acquire bundle watcher lock")

    def release(self) -> None:
        if self.owned:
            current = load_json(self.path)
            if (
                not current.get("_missing")
                and not current.get("_load_error")
                and str(current.get("owner_token") or "") == self.owner_token
            ):
                self.path.unlink(missing_ok=True)
            self.owned = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


def process_rows() -> list[dict[str, Any]]:
    """Return process identity rows, including Windows CreationDate."""

    rows: list[dict[str, Any]] = []
    if os.name == "nt":
        command = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,Name,CreationDate,CommandLine | ConvertTo-Json -Compress"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"process scan failed: {completed.stderr.strip()}")
        text = completed.stdout.strip()
        if text:
            decoded = json.loads(text)
            rows = decoded if isinstance(decoded, list) else [decoded]
    else:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"process scan failed: {completed.stderr.strip()}")
        for line in completed.stdout.splitlines():
            fields = line.strip().split(maxsplit=1)
            if not fields:
                continue
            rows.append(
                {
                    "ProcessId": _int(fields[0]),
                    "Name": "",
                    "CreationDate": None,
                    "CommandLine": fields[1] if len(fields) > 1 else "",
                }
            )
    return rows


def process_identity(pid: int) -> dict[str, Any] | None:
    for row in process_rows():
        row_pid = _int(row.get("ProcessId") or row.get("pid"))
        if row_pid != int(pid):
            continue
        return {
            "pid": row_pid,
            "name": str(row.get("Name") or row.get("name") or ""),
            "creation_date": str(row.get("CreationDate") or row.get("creation_date") or ""),
            "command_line": str(row.get("CommandLine") or row.get("args") or ""),
        }
    return None


def active_eval_processes(exclude_pids: set[int] | None = None) -> list[dict[str, Any]]:
    """Return active Slumbot/mirror processes; parse uncertainty blocks launch."""

    exclude_pids = set(exclude_pids or set())
    conflicts: list[dict[str, Any]] = []
    for row in process_rows():
        pid = _int(row.get("ProcessId") or row.get("pid"))
        command_line = str(row.get("CommandLine") or row.get("args") or "")
        if pid == os.getpid() or (pid is not None and pid in exclude_pids):
            continue
        try:
            matched = _classify_eval_invocation(command_line)
        except Exception as exc:
            # A malformed/unparseable command line cannot safely be declared
            # non-conflicting while a fixed causal measurement is running.
            conflicts.append(
                {
                    "pid": pid,
                    "name": str(row.get("Name") or row.get("name") or ""),
                    "creation_date": str(row.get("CreationDate") or row.get("creation_date") or ""),
                    "command_line": command_line,
                    "matched_tokens": ["command_line_parse_error"],
                    "parse_error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if matched:
            conflicts.append(
                {
                    "pid": pid,
                    "name": str(row.get("Name") or row.get("name") or ""),
                    "creation_date": str(row.get("CreationDate") or row.get("creation_date") or ""),
                    "command_line": command_line,
                    "matched_tokens": matched,
                }
            )
    return conflicts


def eval_contention(run_dir: Path, exclude_pids: set[int] | None = None) -> dict[str, Any]:
    """Require both process state and Slumbot launch state to be idle."""

    processes = active_eval_processes(exclude_pids)
    blocking_states = {
        "RUNNING",
        "FREEZING",
        "PREFLIGHT",
        "SELECTOR_REPLAY",
        "READY",
        "READY_WITH_WARNINGS",
        "FREEZE_RETRY",
    }
    status_paths: set[Path] = set()
    for pattern in (
        "slumbot_*_launch_status.json",
        "slumbot_cadence*_status.json",
        "v5_slumbot_cadence*_status.json",
    ):
        status_paths.update(run_dir.glob(pattern))
    running_statuses: list[dict[str, Any]] = []
    for path in sorted(status_paths):
        status = load_json(path)
        state = str(status.get("state") or status.get("overall") or "").upper()
        blocks = any(state == item or state.startswith(item + "_") for item in blocking_states)
        if blocks:
            running_statuses.append(
                {
                    "path": str(path),
                    "state": state,
                    "pid": _int(status.get("pid") or status.get("launcher_pid")),
                }
            )
    return {
        "busy": bool(processes or running_statuses),
        "processes": processes,
        "slumbot_running_statuses": running_statuses,
    }


@dataclass(frozen=True)
class StageSpec:
    role: str
    stem: Path
    candidate_label: str
    candidate_path: Path
    candidate_sha256: str
    anchor_label: str
    anchor_path: Path
    anchor_sha256: str

    @property
    def result_path(self) -> Path:
        return Path(str(self.stem) + ".json")

    @property
    def markdown_path(self) -> Path:
        return Path(str(self.stem) + ".md")

    @property
    def stdout_path(self) -> Path:
        return Path(str(self.stem) + ".stdout.log")

    @property
    def stderr_path(self) -> Path:
        return Path(str(self.stem) + ".stderr.log")

    @property
    def execution_path(self) -> Path:
        return Path(str(self.stem) + ".execution.json")

    @property
    def launcher_path(self) -> Path:
        return Path(str(self.stem) + ".launcher.json")

    @property
    def contention_reaudit_path(self) -> Path:
        """Immutable forensic companion; deliberately not a mirror result."""

        return Path(str(self.stem) + ".contention_reaudit.json")

    def artifacts(self) -> list[Path]:
        return [
            self.result_path,
            self.markdown_path,
            self.stdout_path,
            self.stderr_path,
            self.execution_path,
            self.launcher_path,
        ]


def _stage_specs(run_dir: Path, freeze: dict[str, Any]) -> list[StageSpec]:
    iteration = int(freeze["gate_iteration"])
    archive_path = Path(str(freeze["archive_path"])).resolve()
    archive_sha = str(freeze["archive_sha256"]).lower()
    return [
        StageSpec(
            role="post_vs_native",
            stem=run_dir / f"v5_mirror_eval_exp003_post_vs_native_gate{iteration}_25kp",
            candidate_label=f"exp003_post_gate{iteration}",
            candidate_path=archive_path,
            candidate_sha256=archive_sha,
            anchor_label="v55_native75M",
            anchor_path=NATIVE_CHECKPOINT_PATH.resolve(),
            anchor_sha256=EXP003_NATIVE_SHA256,
        ),
        StageSpec(
            role="post_vs_pre_direct",
            stem=run_dir / f"v5_mirror_eval_exp003_post_vs_pre_gate21800_gate{iteration}_25kp",
            candidate_label=f"exp003_post_gate{iteration}",
            candidate_path=archive_path,
            candidate_sha256=archive_sha,
            anchor_label="exp003_pre_gate21800",
            anchor_path=PRE_CHECKPOINT_PATH.resolve(),
            anchor_sha256=EXP003_PRE_SHA256,
        ),
    ]


def _command(spec: StageSpec, python: str) -> list[str]:
    return [
        python,
        str(EVALUATOR_PATH.resolve()),
        "--candidate",
        str(spec.candidate_path),
        "--candidate-label",
        spec.candidate_label,
        "--anchor",
        f"{spec.anchor_label}={spec.anchor_path}",
        "--pairs",
        str(EXP003_MIRROR_PAIRS),
        "--seed",
        str(EXP003_MIRROR_SEED),
        "--starting-stack",
        str(int(STARTING_STACK)),
        "--device",
        DEVICE,
        "--priority",
        PRIORITY,
        "--torch-threads",
        str(TORCH_THREADS),
        "--torch-interop-threads",
        str(TORCH_INTEROP_THREADS),
        "--anchor-ood-valid-threshold",
        str(EXP003_MIRROR_OOD_MAX),
        "--out-json",
        str(spec.result_path),
        "--out-md",
        str(spec.markdown_path),
        "--execution-json",
        str(spec.execution_path),
    ]


def _input_hashes(spec: StageSpec) -> dict[str, str]:
    return {
        "evaluator": sha256_file(EVALUATOR_PATH) if EVALUATOR_PATH.is_file() else "",
        "candidate": sha256_file(spec.candidate_path) if spec.candidate_path.is_file() else "",
        "anchor": sha256_file(spec.anchor_path) if spec.anchor_path.is_file() else "",
    }


def _staging_spec(run_dir: Path, spec: StageSpec) -> StageSpec:
    stage_dir = run_dir / "exp003_bundle_staging" / f"{spec.role}_attempt1"
    return replace(spec, stem=stage_dir / "payload")


def _wait_process_identity(pid: int, timeout_seconds: float = 5.0) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        identity = process_identity(pid)
        if identity and identity.get("creation_date") and identity.get("command_line"):
            return identity
        time.sleep(0.1)
    return None


def _launcher_payload(
    spec: StageSpec,
    canonical_spec: StageSpec,
    pid: int,
    command: list[str],
    identity: dict[str, Any],
    input_hashes: dict[str, str],
    prelaunch_hashed_at: str,
) -> dict[str, Any]:
    protocol = {
        "pairs": EXP003_MIRROR_PAIRS,
        "seed": EXP003_MIRROR_SEED,
        "starting_stack": STARTING_STACK,
        "policy_mode": EXP003_MIRROR_POLICY_MODE,
        "device": DEVICE,
        "priority": PRIORITY,
        "torch_threads": TORCH_THREADS,
        "torch_interop_threads": TORCH_INTEROP_THREADS,
        "anchor_ood_valid_threshold": EXP003_MIRROR_OOD_MAX,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "role": spec.role,
        "attempt": 1,
        "pid": int(pid),
        "process_creation_date": identity.get("creation_date"),
        "process_command_line": identity.get("command_line"),
        "started_at": now_iso(),
        "working_directory": str(REPO_ROOT),
        "command": command,
        "evaluator_path": str(EVALUATOR_PATH.resolve()),
        "evaluator_sha256": EXP003_EVALUATOR_SHA256,
        "candidate_path": str(spec.candidate_path),
        "candidate_sha256": spec.candidate_sha256,
        "anchor_path": str(spec.anchor_path),
        "anchor_sha256": spec.anchor_sha256,
        "model_sha256": {
            "candidate": spec.candidate_sha256,
            "anchor": spec.anchor_sha256,
        },
        "input_sha256_pre": input_hashes,
        "prelaunch_hashed_at": prelaunch_hashed_at,
        "publish_target": {
            "result": str(canonical_spec.result_path),
            "markdown": str(canonical_spec.markdown_path),
            "stdout": str(canonical_spec.stdout_path),
            "stderr": str(canonical_spec.stderr_path),
            "execution": str(canonical_spec.execution_path),
            "launcher": str(canonical_spec.launcher_path),
        },
        "protocol": protocol,
        # Canonical queue validator consumes these top-level protocol aliases.
        "pairs": EXP003_MIRROR_PAIRS,
        "seed": EXP003_MIRROR_SEED,
        "starting_stack": STARTING_STACK,
        "device": DEVICE,
        "priority": PRIORITY,
        "torch_threads": TORCH_THREADS,
        "torch_interop_threads": TORCH_INTEROP_THREADS,
        "anchor_ood_valid_threshold": EXP003_MIRROR_OOD_MAX,
        "state": "RUNNING",
    }


def launch_stage(
    spec: StageSpec,
    python: str,
    on_started: Callable[[dict[str, Any]], None] | None = None,
    contention_scan: Callable[[set[int]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Launch into a non-ingested staging directory and wait exactly once."""

    existing = [str(path) for path in spec.artifacts() if path.exists()]
    if existing:
        return {
            "status": "REFUSED_EXISTING_ARTIFACTS",
            "role": spec.role,
            "existing_artifacts": existing,
        }

    run_dir = spec.stem.parent
    staged = _staging_spec(run_dir, spec)
    if staged.stem.parent.exists():
        return {
            "status": "STAGING_EXISTS",
            "role": spec.role,
            "staging_dir": str(staged.stem.parent),
        }
    staged.stem.parent.mkdir(parents=True, exist_ok=False)
    command = _command(staged, python)
    expected_hashes = _expected_hashes(spec)
    prelaunch_hashed_at = now_iso()
    try:
        hashes_pre = _input_hashes(spec)
    except Exception as exc:
        hashes_pre = {}
        prehash_error = f"{type(exc).__name__}: {exc}"
    else:
        prehash_error = None
    if hashes_pre != expected_hashes:
        failure = {
            "schema_version": SCHEMA_VERSION,
            "role": spec.role,
            "attempt": 1,
            "pid": None,
            "state": "PRELAUNCH_HASH_FAIL",
            "started_at": now_iso(),
            "prelaunch_hashed_at": prelaunch_hashed_at,
            "input_sha256_pre": hashes_pre,
            "expected_input_sha256": expected_hashes,
            "error": prehash_error or "prelaunch hashes differ from fixed protocol",
            "command": command,
            "evaluator_sha256": hashes_pre.get("evaluator"),
            "candidate_sha256": hashes_pre.get("candidate"),
            "anchor_sha256": hashes_pre.get("anchor"),
        }
        atomic_write_json(staged.launcher_path, failure)
        return {
            "status": "FAILED",
            "role": spec.role,
            "launcher": failure,
            "staging_dir": str(staged.stem.parent),
        }
    environment = os.environ.copy()
    environment.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    started = time.monotonic()
    stdout_handle = staged.stdout_path.open("xb")
    stderr_handle = staged.stderr_path.open("xb")
    process: subprocess.Popen[bytes] | None = None
    launcher: dict[str, Any] | None = None
    try:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=stdout_handle,
                stderr=stderr_handle,
                env=environment,
                creationflags=creationflags,
            )
        except Exception as exc:
            failure = {
                "schema_version": SCHEMA_VERSION,
                "role": spec.role,
                "pid": None,
                "started_at": now_iso(),
                "state": "LAUNCH_FAILED",
                "error": f"{type(exc).__name__}: {exc}",
                "command": command,
                "evaluator_sha256": EXP003_EVALUATOR_SHA256,
                "candidate_sha256": spec.candidate_sha256,
                "anchor_sha256": spec.anchor_sha256,
            }
            atomic_write_json(staged.launcher_path, failure)
            return {
                "status": "FAILED",
                "role": spec.role,
                "launcher": failure,
                "staging_dir": str(staged.stem.parent),
            }

        try:
            identity = _wait_process_identity(process.pid)
        except Exception as exc:
            identity = None
            identity_error = f"{type(exc).__name__}: {exc}"
        else:
            identity_error = "process identity did not become observable"
        if identity is None:
            process.terminate()
            process.wait(timeout=30)
            failure = {
                "schema_version": SCHEMA_VERSION,
                "role": spec.role,
                "attempt": 1,
                "pid": process.pid,
                "state": "PROCESS_IDENTITY_FAIL",
                "error": identity_error,
                "started_at": now_iso(),
                "command": command,
                "evaluator_sha256": EXP003_EVALUATOR_SHA256,
            }
            atomic_write_json(staged.launcher_path, failure)
            return {
                "status": "FAILED",
                "role": spec.role,
                "launcher": failure,
                "staging_dir": str(staged.stem.parent),
            }
        launcher = _launcher_payload(
            staged,
            spec,
            process.pid,
            command,
            identity,
            hashes_pre,
            prelaunch_hashed_at,
        )
        try:
            atomic_write_json(staged.launcher_path, launcher)
        except Exception:
            process.terminate()
            process.wait(timeout=30)
            raise
        monitor_errors: list[dict[str, str]] = []
        if on_started is not None:
            try:
                on_started(dict(launcher))
            except Exception as exc:
                monitor_errors.append(
                    {"checked_at": now_iso(), "error": f"status callback: {type(exc).__name__}: {exc}"}
                )
        contention_snapshots: list[dict[str, Any]] = []
        contention_scan = contention_scan or (lambda excluded: eval_contention(run_dir, excluded))
        while process.poll() is None:
            try:
                contention = contention_scan({process.pid})
            except Exception as exc:
                monitor_errors.append(
                    {"checked_at": now_iso(), "error": f"{type(exc).__name__}: {exc}"}
                )
            else:
                if contention.get("busy"):
                    contention_snapshots.append({"checked_at": now_iso(), **contention})
            try:
                process.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                pass
        return_code = int(process.returncode or 0)
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except Exception:
                process.kill()
                process.wait(timeout=30)
        raise
    finally:
        stdout_handle.close()
        stderr_handle.close()

    assert process is not None and launcher is not None
    try:
        hashes_post = _input_hashes(spec)
        posthash_error = None
    except Exception as exc:
        hashes_post = {}
        posthash_error = f"{type(exc).__name__}: {exc}"
    launcher.update(
        {
            "state": "COMPLETED" if return_code == 0 and posthash_error is None else "FAILED",
            "return_code": int(return_code),
            "finished_at": now_iso(),
            "elapsed_seconds": time.monotonic() - started,
            "input_sha256_post": hashes_post,
            "posthash_error": posthash_error,
            "contention_detected": bool(contention_snapshots or monitor_errors),
            "contention_snapshots": contention_snapshots,
            "contention_monitor_errors": monitor_errors,
        }
    )
    atomic_write_json(staged.launcher_path, launcher)
    return {
        "status": "STAGED_COMPLETED" if return_code == 0 and posthash_error is None else "FAILED",
        "role": spec.role,
        "pid": process.pid,
        "return_code": int(return_code),
        "launcher": launcher,
        "canonical_spec": spec,
        "staged_spec": staged,
        "staging_dir": str(staged.stem.parent),
        "artifacts": [str(path) for path in staged.artifacts()],
    }


def _expected_hashes(spec: StageSpec) -> dict[str, str]:
    return {
        "evaluator": EXP003_EVALUATOR_SHA256,
        "candidate": spec.candidate_sha256,
        "anchor": spec.anchor_sha256,
    }


def _parse_process_command_line(command_line: str) -> list[str]:
    if not command_line:
        return []
    if os.name != "nt":
        return shlex.split(command_line)
    argc = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    argv = command_line_to_argv(command_line, ctypes.byref(argc))
    if not argv:
        return []
    try:
        return [argv[index] for index in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def _command_basename(value: str) -> str:
    """Return a case-normalized basename for either Windows or POSIX argv text."""

    return str(value).replace("/", "\\").rsplit("\\", 1)[-1].lower()


def _is_python_executable(value: str) -> bool:
    name = _command_basename(value)
    if name.endswith(".exe"):
        name = name[:-4]
    if name in {"python", "pythonw", "py"}:
        return True
    return name.startswith("python") and name[6:].replace(".", "").isdigit()


def _is_powershell_executable(value: str) -> bool:
    return _command_basename(value) in {
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
    }


def _python_script_argument(argv: list[str]) -> str | None:
    """Return Python's script positional argument, never code/module text."""

    index = 1
    # Keep this deliberately narrow but include Python's common option/value
    # pairs used by the benchmark launchers.  Case matters here: ``-X`` takes
    # a value, whereas lowercase ``-x`` is flag-only.
    options_with_value = {"-W", "-X", "--check-hash-based-pycs"}
    while index < len(argv):
        argument = argv[index]
        lowered = argument.lower()
        if lowered in {"-c", "-m"}:
            # The next argument is code/module text, not an executable script.
            return None
        if argument == "-":
            return None
        if argument == "--":
            return argv[index + 1] if index + 1 < len(argv) else None
        if argument.startswith("-"):
            index += 2 if argument in options_with_value else 1
            continue
        return argument
    return None


def _powershell_file_argument(argv: list[str]) -> str | None:
    """Return a direct PowerShell ``-File`` target, never ``-Command`` text."""

    index = 1
    while index < len(argv):
        argument = argv[index]
        lowered = argument.lower()
        if lowered in {"-command", "-c", "-encodedcommand", "-e"}:
            return None
        if lowered in {"-file", "-f"}:
            if index + 1 >= len(argv):
                raise ValueError("PowerShell -File is missing its target")
            return argv[index + 1]
        if lowered.startswith("-file:"):
            target = argument.split(":", 1)[1]
            if not target:
                raise ValueError("PowerShell -File is missing its target")
            return target
        index += 1
    return None


def _is_eval_python_script(value: str) -> bool:
    script = _command_basename(value)
    return (
        script.startswith("play_slumbot") and script.endswith(".py")
    ) or script in {
        "v5_slumbot_selector_replay.py",
        "v5_slumbot_pipeline_preflight.py",
        "slumbot_pipeline_preflight.py",
        "v5_mirror_eval.py",
    }


def _classify_eval_invocation(command_line: str) -> list[str]:
    """Classify only an actual evaluator invocation, not incidental command text."""

    argv = _parse_process_command_line(command_line)
    if not argv:
        return []
    if _is_python_executable(argv[0]):
        target = _python_script_argument(argv)
        if target and _is_eval_python_script(target):
            return [_command_basename(target)]
        return []
    if _is_powershell_executable(argv[0]):
        target = _powershell_file_argument(argv)
        if target and _command_basename(target) == "bench_v55_slumbot.ps1":
            return ["bench_v55_slumbot.ps1"]
    return []


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    """Stable bytes for immutable forensic evidence and equality checks."""

    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _json_fingerprint(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _immutable_write_json(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Create an immutable JSON artifact, or prove an exact prior copy exists.

    A forensic re-audit may be resumed after a watcher crash.  Replacing an
    existing explanation would defeat that purpose, so a different byte stream
    is an error rather than a reason to overwrite it.
    """

    encoded = _canonical_json_bytes(payload)
    expected = hashlib.sha256(encoded).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        if not path.is_file():
            raise RuntimeError(f"immutable forensic path exists but is not a file: {path}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"immutable forensic artifact already exists with different SHA256: {path}")
        return {"status": "MATCHED_EXISTING", "path": str(path), "sha256": actual}
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"immutable forensic artifact hash mismatch after write: {path}")
    return {"status": "CREATED", "path": str(path), "sha256": actual}


def _powershell_command_argument(argv: list[str]) -> tuple[str | None, str | None]:
    """Return a direct ``-Command`` payload under a deliberately tiny grammar.

    Recovery is not a general PowerShell safety oracle.  It accepts only the
    no-profile, direct command shape used by the captured read-only operator
    diagnostic.  Anything less explicit remains quarantined.
    """

    if not argv or not _is_powershell_executable(argv[0]):
        return None, "not a PowerShell executable"
    no_value_options = {"-noprofile", "-noninteractive", "-nologo"}
    index = 1
    while index < len(argv):
        argument = str(argv[index])
        lowered = argument.lower()
        if lowered == "-command":
            if index + 1 >= len(argv):
                return None, "PowerShell -Command is missing its script text"
            if index + 2 != len(argv):
                return None, "PowerShell -Command has unexpected trailing arguments"
            return str(argv[index + 1]), None
        if lowered in {"-file", "-f", "-encodedcommand", "-e", "-c"} or lowered.startswith("-file:"):
            return None, f"PowerShell option {argument!r} is not a direct read-only -Command"
        if lowered not in no_value_options:
            return None, f"PowerShell option {argument!r} is not allowed for forensic recovery"
        index += 1
    return None, "PowerShell -Command was not present"


def _classify_readonly_powershell_diagnostic(command_line: str) -> dict[str, Any]:
    """Reclassify exactly the captured observer, never generic PowerShell text."""

    evidence: dict[str, Any] = {
        "command_line_sha256": _sha256_text(command_line),
        "corrected_eval_invocation": None,
        "kind": "NOT_READONLY_DIAGNOSTIC",
        "status": "FAIL",
    }
    try:
        argv = _parse_process_command_line(command_line)
        evidence["argv_sha256"] = _json_fingerprint(argv)
        corrected = _classify_eval_invocation(command_line)
        evidence["corrected_eval_invocation"] = corrected
        if corrected:
            evidence["reason"] = f"corrected classifier still sees evaluator invocation: {corrected}"
            return evidence
        script, command_error = _powershell_command_argument(argv)
        if command_error or script is None:
            evidence["reason"] = command_error or "PowerShell script text is absent"
            return evidence
        evidence["script_sha256"] = _sha256_text(script)
    except Exception as exc:
        evidence["reason"] = f"{type(exc).__name__}: {exc}"
        return evidence
    evidence["historical_allowlist"] = {
        "command_line_sha256": CAPTURED_FALSE_POSITIVE_OBSERVER["command_line_sha256"],
        "script_sha256": CAPTURED_FALSE_POSITIVE_OBSERVER["script_sha256"],
    }
    if (
        evidence["command_line_sha256"] != CAPTURED_FALSE_POSITIVE_OBSERVER["command_line_sha256"]
        or evidence["script_sha256"] != CAPTURED_FALSE_POSITIVE_OBSERVER["script_sha256"]
    ):
        evidence["reason"] = "PowerShell -Command does not match the captured false-positive observer bytes"
        return evidence
    evidence.update(
        {
            "kind": "POWERSHELL_READONLY_DIAGNOSTIC",
            "status": "PASS",
            "reason": "parsed direct PowerShell command exactly matches the captured read-only observer",
        }
    )
    return evidence


def _staged_raw_artifact_paths(staged: StageSpec) -> dict[str, Path]:
    return {
        "result": staged.result_path,
        "markdown": staged.markdown_path,
        "stdout": staged.stdout_path,
        "stderr": staged.stderr_path,
        "execution": staged.execution_path,
        "launcher": staged.launcher_path,
    }


def _fingerprint_paths(paths: dict[str, Path]) -> dict[str, dict[str, Any]]:
    fingerprints: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"required forensic source is missing: {name}={path}")
        fingerprints[name] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    return fingerprints


def _fingerprints_match(expected: Any, paths: dict[str, Path]) -> tuple[bool, dict[str, dict[str, Any]]]:
    """Re-prove a re-audit's raw source bytes before publishing any result."""

    try:
        actual = _fingerprint_paths(paths)
    except Exception:
        return False, {}
    if not isinstance(expected, dict) or set(expected) != set(paths):
        return False, actual
    for name, current in actual.items():
        saved = expected.get(name)
        if not isinstance(saved, dict):
            return False, actual
        if str(saved.get("path") or "") != current["path"]:
            return False, actual
        if str(saved.get("sha256") or "") != current["sha256"]:
            return False, actual
        if _int(saved.get("bytes")) != _int(current["bytes"]):
            return False, actual
    return True, actual


def _same_executable(left: str, right: str) -> bool:
    left_resolved = shutil.which(left) or left
    right_resolved = shutil.which(right) or right
    try:
        return Path(left_resolved).resolve() == Path(right_resolved).resolve()
    except (OSError, ValueError):
        return left_resolved.lower() == right_resolved.lower()


def _audit_staged(
    spec: StageSpec,
    staged: StageSpec,
    *,
    allow_reaudited_contention: bool = False,
) -> dict[str, Any]:
    missing = [str(path) for path in staged.artifacts() if not path.is_file()]
    if missing:
        return {"status": "FAIL", "reason": "missing staged companions", "missing": missing}
    mirror = load_json(staged.result_path)
    if mirror.get("_missing") or mirror.get("_load_error"):
        return {"status": "FAIL", "reason": "staged result is unreadable", "result": mirror}
    record = _exp003_mirror_record(staged.result_path, mirror)
    expected = _expected_hashes(spec)
    actual = _input_hashes(spec)
    launcher = load_json(staged.launcher_path)
    execution = load_json(staged.execution_path)
    launcher_command = launcher.get("command") if isinstance(launcher.get("command"), list) else []
    execution_command = execution.get("command") if isinstance(execution.get("command"), list) else []
    process_command = _parse_process_command_line(str(launcher.get("process_command_line") or ""))
    expected_command = _command(staged, str(launcher_command[0])) if launcher_command else []
    expected_publish_target = {
        "result": str(spec.result_path),
        "markdown": str(spec.markdown_path),
        "stdout": str(spec.stdout_path),
        "stderr": str(spec.stderr_path),
        "execution": str(spec.execution_path),
        "launcher": str(spec.launcher_path),
    }
    exact_command = bool(
        launcher_command
        and launcher_command == expected_command
        and execution_command
        and launcher_command[1:] == execution_command[1:]
        and _same_executable(str(launcher_command[0]), str(execution_command[0]))
        and process_command
        and launcher_command[1:] == process_command[1:]
        and _same_executable(str(launcher_command[0]), str(process_command[0]))
    )
    raw_contention_clean = bool(
        launcher.get("contention_detected") is False
        and not launcher.get("contention_snapshots")
        and not launcher.get("contention_monitor_errors")
    )
    structural_checks = {
        "execution": record.get("execution_ok") is True,
        "companions": record.get("companions_ok") is True,
        "stderr_empty": record.get("stderr_empty") is True,
        "protocol": (
            record.get("pairs") == EXP003_MIRROR_PAIRS
            and record.get("seed") == EXP003_MIRROR_SEED
            and record.get("policy_mode") == EXP003_MIRROR_POLICY_MODE
            and record.get("starting_stack") == STARTING_STACK
            and str(record.get("device") or "").lower() == DEVICE
            and record.get("ood_threshold") == EXP003_MIRROR_OOD_MAX
        ),
        "candidate_identity": (
            record.get("candidate_sha256") == spec.candidate_sha256
            and _same_path(record.get("candidate_path"), spec.candidate_path)
        ),
        "anchor_identity": (
            record.get("anchor_sha256") == spec.anchor_sha256
            and _same_path(record.get("anchor_path"), spec.anchor_path)
        ),
        "numeric_measurement_present": (
            record.get("candidate_bb100") is not None
            and record.get("candidate_ci95_bb100") is not None
            and record.get("ood_rate") is not None
        ),
        "launcher_complete": (
            str(launcher.get("state") or "").upper() == "COMPLETED"
            and _int(launcher.get("return_code")) == 0
            and launcher.get("input_sha256_pre") == expected
            and launcher.get("input_sha256_post") == expected
            and (raw_contention_clean or allow_reaudited_contention)
        ),
        "launcher_identity": (
            launcher.get("role") == spec.role
            and _int(launcher.get("attempt")) == 1
            and _int(launcher.get("pid")) is not None
            and _int(launcher.get("pid")) == _int(execution.get("pid"))
            and bool(launcher.get("process_creation_date"))
            and bool(launcher.get("process_command_line"))
            and str(launcher.get("working_directory") or "") == str(REPO_ROOT)
            and str(execution.get("working_directory") or "") == str(REPO_ROOT)
        ),
        "launcher_command": exact_command,
        "launcher_paths": (
            _same_path(launcher.get("evaluator_path"), EVALUATOR_PATH)
            and _same_path(launcher.get("candidate_path"), spec.candidate_path)
            and _same_path(launcher.get("anchor_path"), spec.anchor_path)
            and launcher.get("publish_target") == expected_publish_target
        ),
        "launcher_model_hashes": (
            launcher.get("evaluator_sha256") == EXP003_EVALUATOR_SHA256
            and launcher.get("candidate_sha256") == spec.candidate_sha256
            and launcher.get("anchor_sha256") == spec.anchor_sha256
            and launcher.get("model_sha256")
            == {"candidate": spec.candidate_sha256, "anchor": spec.anchor_sha256}
        ),
        "current_input_hashes": actual == expected,
    }
    status = "PASS" if all(structural_checks.values()) else "FAIL"
    return {
        "status": status,
        "reason": "staged role is structurally complete" if status == "PASS" else "staged role failed structural validation",
        "structural_checks": structural_checks,
        "measurement_usable": record.get("usable") is True,
        "ci_ok": record.get("ci_ok"),
        "ood_ok": record.get("ood_ok"),
        "record": record,
        "input_sha256_actual": actual,
        "raw_contention_clean": raw_contention_clean,
        "reaudited_contention_exception_used": bool(allow_reaudited_contention and not raw_contention_clean),
    }


def _atomic_copy_verified(source: Path, destination: Path, expected_sha256: str) -> str:
    if destination.exists():
        actual = sha256_file(destination)
        if actual != expected_sha256:
            raise RuntimeError(f"publish target exists with different SHA256: {destination}")
        return "MATCHED_EXISTING"
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".publish.tmp", dir=str(destination.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if sha256_file(temporary) != expected_sha256:
            raise RuntimeError(f"staged artifact changed during publish copy: {source}")
        try:
            # Hard-link creation is atomic and fails if another publisher won
            # the destination race; unlike Path.replace it never clobbers.
            os.link(temporary, destination)
        except FileExistsError:
            actual = sha256_file(destination)
            if actual != expected_sha256:
                raise RuntimeError(
                    f"publish destination won a race with different SHA256: {destination}"
                )
            return "MATCHED_RACE"
    finally:
        temporary.unlink(missing_ok=True)
    return "PUBLISHED"


def _build_publish_manifest(spec: StageSpec, staged: StageSpec, audit: dict[str, Any]) -> dict[str, Any]:
    keys = ["markdown", "stdout", "stderr", "execution", "launcher", "result"]
    staged_paths = {
        "result": staged.result_path,
        "markdown": staged.markdown_path,
        "stdout": staged.stdout_path,
        "stderr": staged.stderr_path,
        "execution": staged.execution_path,
        "launcher": staged.launcher_path,
    }
    canonical_paths = {
        "result": spec.result_path,
        "markdown": spec.markdown_path,
        "stdout": spec.stdout_path,
        "stderr": spec.stderr_path,
        "execution": spec.execution_path,
        "launcher": spec.launcher_path,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "state": "VALIDATED_FOR_PUBLISH",
        "checked_at": now_iso(),
        "role": spec.role,
        "measurement_usable": audit.get("measurement_usable"),
        "publish_order": keys,
        "main_json_last": True,
        "artifacts": {
            key: {
                "staged": str(staged_paths[key]),
                "canonical": str(canonical_paths[key]),
                "sha256": sha256_file(staged_paths[key]),
            }
            for key in keys
        },
    }


def _publish_manifest_matches_spec(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    """Accept a crash-recovery manifest only when it is this exact publish plan."""

    if existing.get("schema_version") != expected.get("schema_version"):
        return False
    if existing.get("role") != expected.get("role"):
        return False
    if existing.get("measurement_usable") != expected.get("measurement_usable"):
        return False
    if existing.get("publish_order") != expected.get("publish_order"):
        return False
    if existing.get("main_json_last") is not True:
        return False
    if str(existing.get("state") or "") not in {"VALIDATED_FOR_PUBLISH", "PUBLISHED"}:
        return False
    existing_artifacts = existing.get("artifacts") if isinstance(existing.get("artifacts"), dict) else {}
    expected_artifacts = expected.get("artifacts") if isinstance(expected.get("artifacts"), dict) else {}
    if set(existing_artifacts) != set(expected_artifacts):
        return False
    for key, expected_row in expected_artifacts.items():
        if not isinstance(expected_row, dict) or existing_artifacts.get(key) != expected_row:
            return False
    return True


def _exclusive_create_json(path: Path, payload: dict[str, Any]) -> bool:
    """Create a mutable-status plan with O_EXCL; never replace a competing plan."""

    encoded = _canonical_json_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return True


def _publish_from_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    if manifest.get("_missing") or manifest.get("_load_error"):
        return {"status": "FAIL", "reason": "publish manifest is unreadable", "manifest": manifest}
    if manifest.get("main_json_last") is not True:
        return {"status": "FAIL", "reason": "publish manifest does not require main JSON last"}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    order = ["markdown", "stdout", "stderr", "execution", "launcher", "result"]
    if set(artifacts) != set(order):
        return {"status": "FAIL", "reason": "publish manifest artifact set mismatch"}
    outcomes: dict[str, str] = {}
    try:
        for key in order:
            row = artifacts[key]
            source = Path(str(row["staged"]))
            destination = Path(str(row["canonical"]))
            expected = str(row["sha256"])
            if not source.is_file() or sha256_file(source) != expected:
                raise RuntimeError(f"staged {key} is missing or changed")
            outcomes[key] = _atomic_copy_verified(source, destination, expected)
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": f"{type(exc).__name__}: {exc}",
            "outcomes": outcomes,
        }
    manifest.update({"state": "PUBLISHED", "published_at": now_iso(), "outcomes": outcomes})
    atomic_write_json(manifest_path, manifest)
    return {"status": "PUBLISHED", "manifest": manifest, "outcomes": outcomes}


def finalize_staged(
    spec: StageSpec,
    staged: StageSpec,
    *,
    audit: dict[str, Any] | None = None,
    expected_raw_artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Publish a structurally audited stage without replacing any artifact.

    A forensic contention recovery passes its immutable source fingerprints in
    ``expected_raw_artifacts``.  This binds the later publish manifest to the
    exact bytes certified by the re-audit, not merely to a newly valid-looking
    payload at resume time.
    """

    audit = audit or _audit_staged(spec, staged)
    if audit.get("status") != "PASS":
        return {"status": "FAIL", "reason": "staged audit failed", "audit": audit}
    if expected_raw_artifacts is not None:
        fingerprints_ok, actual_fingerprints = _fingerprints_match(
            expected_raw_artifacts,
            _staged_raw_artifact_paths(staged),
        )
        if not fingerprints_ok:
            return {
                "status": "FAIL",
                "reason": "staged raw artifacts no longer match immutable forensic re-audit",
                "audit": audit,
                "actual_raw_artifacts": actual_fingerprints,
            }
    manifest_path = staged.stem.parent / "publish_manifest.json"
    expected_manifest = _build_publish_manifest(spec, staged, audit)
    if manifest_path.exists():
        existing = load_json(manifest_path)
        if existing.get("_load_error") or existing.get("_missing"):
            return {"status": "FAIL", "reason": "existing publish manifest is corrupt"}
        if not _publish_manifest_matches_spec(existing, expected_manifest):
            return {
                "status": "FAIL",
                "reason": "existing publish manifest is not the exact spec-bound staged publish plan",
            }
    else:
        created = _exclusive_create_json(manifest_path, expected_manifest)
        if not created:
            existing = load_json(manifest_path)
            if existing.get("_load_error") or existing.get("_missing") or not _publish_manifest_matches_spec(
                existing,
                expected_manifest,
            ):
                return {
                    "status": "FAIL",
                    "reason": "concurrent publish manifest is not the exact spec-bound staged publish plan",
                }
        else:
            existing = expected_manifest
        existing = load_json(manifest_path)
    if expected_raw_artifacts is not None:
        manifest_artifacts = existing.get("artifacts") if isinstance(existing.get("artifacts"), dict) else {}
        manifest_hashes = {
            name: str(row.get("sha256") or "")
            for name, row in manifest_artifacts.items()
            if isinstance(row, dict)
        }
        expected_hashes = {
            name: str(row.get("sha256") or "")
            for name, row in expected_raw_artifacts.items()
            if isinstance(row, dict)
        }
        if manifest_hashes != expected_hashes:
            return {
                "status": "FAIL",
                "reason": "publish manifest hashes do not match immutable forensic re-audit",
                "audit": audit,
                "manifest_hashes": manifest_hashes,
                "expected_hashes": expected_hashes,
            }
    published = _publish_from_manifest(manifest_path)
    published["audit"] = audit
    published["manifest_path"] = str(manifest_path)
    return published


def quarantine_staged(staged: StageSpec, reason: str, evidence: Any) -> dict[str, Any]:
    marker = staged.stem.parent / "quarantine.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "state": "QUARANTINED",
        "checked_at": now_iso(),
        "role": staged.role,
        "reason": reason,
        "evidence": evidence,
        "published": False,
    }
    if not marker.exists():
        atomic_write_json(marker, payload)
    return payload


def _contention_snapshot_classifier_evidence(
    launcher: dict[str, Any],
    quarantine: dict[str, Any],
) -> dict[str, Any]:
    """Prove every persisted contention row is the exact read-only observer.

    Both the launcher's snapshots and quarantine evidence are source records.
    They must agree byte-for-byte; that lets one set of parsed evidence cover
    every saved snapshot without silently selecting a convenient subset.
    """

    snapshots = launcher.get("contention_snapshots")
    quarantine_evidence = quarantine.get("evidence")
    problems: list[str] = []
    if launcher.get("contention_detected") is not True:
        problems.append("launcher does not explicitly record contention_detected=true")
    if launcher.get("contention_monitor_errors") != []:
        problems.append("launcher has monitor errors or an unprovable monitor-error shape")
    if not isinstance(snapshots, list) or not snapshots:
        problems.append("launcher contention snapshots are missing/empty")
    if not isinstance(quarantine_evidence, list) or not quarantine_evidence:
        problems.append("quarantine evidence snapshots are missing/empty")
    if not problems and _canonical_json_bytes(snapshots) != _canonical_json_bytes(quarantine_evidence):
        problems.append("launcher and quarantine contention snapshots differ")

    classified_snapshots: list[dict[str, Any]] = []
    if isinstance(snapshots, list):
        for snapshot_index, snapshot in enumerate(snapshots):
            snapshot_sha = _json_fingerprint(snapshot)
            row: dict[str, Any] = {
                "snapshot_index": snapshot_index,
                "snapshot_sha256": snapshot_sha,
                "historical_allowlist": {
                    "pid": CAPTURED_FALSE_POSITIVE_OBSERVER["pid"],
                    "creation_date": CAPTURED_FALSE_POSITIVE_OBSERVER["creation_date"],
                    "checked_at": CAPTURED_FALSE_POSITIVE_OBSERVER["checked_at"],
                    "snapshot_sha256": CAPTURED_FALSE_POSITIVE_OBSERVER["snapshot_sha256"],
                },
                "status": "FAIL",
                "processes": [],
            }
            if not isinstance(snapshot, dict):
                row["reason"] = "contention snapshot is not an object"
                classified_snapshots.append(row)
                continue
            row["busy"] = snapshot.get("busy")
            row["slumbot_running_statuses"] = snapshot.get("slumbot_running_statuses")
            snapshot_problems: list[str] = []
            if snapshot.get("busy") is not True:
                snapshot_problems.append("saved contention snapshot is not explicitly busy")
            if snapshot.get("slumbot_running_statuses") != []:
                snapshot_problems.append("saved contention snapshot contains Slumbot blocking status(es)")
            if snapshot_index != 0 or len(snapshots) != 1:
                snapshot_problems.append("recovery permits exactly one captured contention snapshot")
            if snapshot_sha != CAPTURED_FALSE_POSITIVE_OBSERVER["snapshot_sha256"]:
                snapshot_problems.append("saved snapshot SHA256 does not match the captured false positive")
            if str(snapshot.get("checked_at") or "") != CAPTURED_FALSE_POSITIVE_OBSERVER["checked_at"]:
                snapshot_problems.append("saved snapshot timestamp does not match the captured false positive")
            processes = snapshot.get("processes")
            if not isinstance(processes, list) or not processes:
                snapshot_problems.append("saved contention snapshot has no process evidence")
                processes = []
            elif len(processes) != 1:
                snapshot_problems.append("recovery permits exactly one captured observer process")
            for process_index, process in enumerate(processes):
                process_row: dict[str, Any] = {
                    "process_index": process_index,
                    "status": "FAIL",
                }
                if not isinstance(process, dict):
                    process_row["reason"] = "saved process row is not an object"
                    snapshot_problems.append("saved process row is not an object")
                    row["processes"].append(process_row)
                    continue
                command_line = str(process.get("command_line") or "")
                process_row.update(
                    {
                        "pid": _int(process.get("pid")),
                        "name": str(process.get("name") or ""),
                        "creation_date": str(process.get("creation_date") or ""),
                        "original_matched_tokens": process.get("matched_tokens"),
                        "classification": _classify_readonly_powershell_diagnostic(command_line),
                    }
                )
                if process_row["pid"] != CAPTURED_FALSE_POSITIVE_OBSERVER["pid"]:
                    snapshot_problems.append("observer PID does not match the captured false positive")
                if process_row["creation_date"] != CAPTURED_FALSE_POSITIVE_OBSERVER["creation_date"]:
                    snapshot_problems.append("observer CreationDate does not match the captured false positive")
                if process_row["classification"].get("status") == "PASS":
                    process_row["status"] = "PASS"
                else:
                    snapshot_problems.append(
                        f"process[{process_index}] is not a parsed read-only PowerShell observer"
                    )
                row["processes"].append(process_row)
            if not snapshot_problems:
                row.update(
                    {
                        "status": "PASS",
                        "kind": "POWERSHELL_READONLY_DIAGNOSTIC",
                        "reason": "all saved process rows are parsed exact read-only observers",
                    }
                )
            else:
                row["reason"] = "; ".join(snapshot_problems)
            classified_snapshots.append(row)

    if not classified_snapshots or any(row.get("status") != "PASS" for row in classified_snapshots):
        problems.append("not every saved contention snapshot reclassifies as a read-only diagnostic")
    return {
        "status": "PASS" if not problems else "FAIL",
        "reason": "all persisted contention evidence is an exact parsed read-only observer" if not problems else "; ".join(problems),
        "launcher_snapshot_count": len(snapshots) if isinstance(snapshots, list) else None,
        "quarantine_snapshot_count": len(quarantine_evidence) if isinstance(quarantine_evidence, list) else None,
        "launcher_quarantine_snapshots_exact_match": bool(
            isinstance(snapshots, list)
            and isinstance(quarantine_evidence, list)
            and _canonical_json_bytes(snapshots) == _canonical_json_bytes(quarantine_evidence)
        ),
        "all_saved_snapshots_covered": bool(
            isinstance(snapshots, list)
            and isinstance(quarantine_evidence, list)
            and _canonical_json_bytes(snapshots) == _canonical_json_bytes(quarantine_evidence)
        ),
        "snapshots": classified_snapshots,
    }


def _forensic_audit_view(audit: dict[str, Any]) -> dict[str, Any]:
    """Keep the certificate compact but include every structural audit outcome."""

    return {
        "status": audit.get("status"),
        "reason": audit.get("reason"),
        "structural_checks": audit.get("structural_checks"),
        "measurement_usable": audit.get("measurement_usable"),
        "ci_ok": audit.get("ci_ok"),
        "ood_ok": audit.get("ood_ok"),
        "input_sha256_actual": audit.get("input_sha256_actual"),
        "raw_contention_clean": audit.get("raw_contention_clean"),
        "reaudited_contention_exception_used": audit.get("reaudited_contention_exception_used"),
    }


def _build_contention_reaudit(
    spec: StageSpec,
    staged: StageSpec,
    quarantine: dict[str, Any],
    original_terminal_status: dict[str, Any] | None,
    original_terminal_status_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
    """Build (without writing) an immutable false-positive contention certificate."""

    launcher = load_json(staged.launcher_path)
    if launcher.get("_missing") or launcher.get("_load_error"):
        return None, None, "original staged launcher is missing or unreadable"
    if quarantine.get("_missing") or quarantine.get("_load_error"):
        return None, None, "original quarantine is missing or unreadable"
    if str(quarantine.get("state") or "").upper() != "QUARANTINED":
        return None, None, "quarantine state is not QUARANTINED"
    if quarantine.get("published") is not False:
        return None, None, "quarantine does not prove the original staged role stayed unpublished"
    if str(quarantine.get("role") or "") != spec.role:
        return None, None, "quarantine role does not match the staged role"
    expected_status_path = (spec.stem.parent / "v5_exp003_bundle_watch_status.json").resolve()
    if original_terminal_status is None or original_terminal_status_path is None:
        return None, None, "canonical original terminal bundle status was not supplied for forensic preservation"
    status_path = Path(original_terminal_status_path).resolve()
    if status_path != expected_status_path:
        return None, None, "forensic recovery accepts only the canonical bundle watcher status path"
    current_terminal_status = load_json(status_path)
    if current_terminal_status != original_terminal_status:
        return None, None, "canonical terminal bundle status changed before forensic certification"
    if not _is_recoverable_false_positive_terminal(current_terminal_status, spec.stem.parent, status_path):
        return None, None, "canonical terminal bundle status is not the one allowlisted false-positive state"
    try:
        source_before = {
            "launcher": _fingerprint_paths({"launcher": staged.launcher_path})["launcher"],
            "quarantine": _fingerprint_paths({"quarantine": staged.stem.parent / "quarantine.json"})["quarantine"],
            "terminal_status": _fingerprint_paths({"terminal_status": status_path})["terminal_status"],
            "raw_artifacts": _fingerprint_paths(_staged_raw_artifact_paths(staged)),
        }
    except Exception as exc:
        return None, None, f"could not fingerprint original forensic sources: {type(exc).__name__}: {exc}"
    if source_before["launcher"]["sha256"] != CAPTURED_FALSE_POSITIVE_OBSERVER["launcher_sha256"]:
        return None, None, "original launcher SHA256 is not the captured false-positive launcher"
    if source_before["quarantine"]["sha256"] != CAPTURED_FALSE_POSITIVE_OBSERVER["quarantine_sha256"]:
        return None, None, "original quarantine SHA256 is not the captured false-positive quarantine"
    terminal_snapshot_sha256 = _json_fingerprint(original_terminal_status)
    if source_before["terminal_status"]["sha256"] != terminal_snapshot_sha256:
        return None, None, "canonical terminal status bytes do not exactly match the preserved terminal status snapshot"
    classifier = _contention_snapshot_classifier_evidence(launcher, quarantine)
    if classifier.get("status") != "PASS":
        return None, None, f"contention evidence cannot be safely reclassified: {classifier.get('reason')}"
    audit = _audit_staged(spec, staged, allow_reaudited_contention=True)
    if audit.get("status") != "PASS":
        return None, None, "original raw artifacts failed identity/protocol/structural audit"
    if audit.get("raw_contention_clean") is not False or audit.get("reaudited_contention_exception_used") is not True:
        return None, None, "re-audit is not using exactly the preserved contention exception"
    try:
        source_after = {
            "launcher": _fingerprint_paths({"launcher": staged.launcher_path})["launcher"],
            "quarantine": _fingerprint_paths({"quarantine": staged.stem.parent / "quarantine.json"})["quarantine"],
            "terminal_status": _fingerprint_paths({"terminal_status": status_path})["terminal_status"],
            "raw_artifacts": _fingerprint_paths(_staged_raw_artifact_paths(staged)),
        }
    except Exception as exc:
        return None, None, f"could not re-fingerprint original forensic sources: {type(exc).__name__}: {exc}"
    if source_before != source_after:
        return None, None, "original forensic sources changed while the re-audit was running"
    payload = {
        "schema_version": CONTENTION_REAUDIT_SCHEMA_VERSION,
        "state": "FALSE_POSITIVE_CONTENTION_REAUDIT_PASS",
        "reaudited_at": now_iso(),
        "role": spec.role,
        "attempt": 1,
        "staged_companion_path": str(staged.contention_reaudit_path),
        "canonical_companion_path": str(spec.contention_reaudit_path),
        "source": source_after,
        "terminal_status_snapshot": original_terminal_status,
        "terminal_status_snapshot_sha256": terminal_snapshot_sha256,
        "classifier": classifier,
        "raw_audit": _forensic_audit_view(audit),
        "forensic_verdict": "PASS",
        "all_saved_contention_snapshots_reclassified": True,
        "no_slumbot_blocking_state": True,
        "no_monitor_errors": True,
        "raw_identity_protocol_audit_pass": True,
        "recovery_eligible": True,
        "recovery_scope": "publish_exact_existing_staged_role_only_no_new_pairs_then_continue_remaining_fixed_role",
        "original_launcher_and_quarantine_preserved": True,
    }
    return payload, audit, None


def _matching_reaudit_payload(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    required_keys = {
        "schema_version",
        "state",
        "role",
        "attempt",
        "staged_companion_path",
        "canonical_companion_path",
        "source",
        "terminal_status_snapshot",
        "terminal_status_snapshot_sha256",
        "classifier",
        "raw_audit",
        "forensic_verdict",
        "all_saved_contention_snapshots_reclassified",
        "no_slumbot_blocking_state",
        "no_monitor_errors",
        "raw_identity_protocol_audit_pass",
        "recovery_eligible",
        "recovery_scope",
        "original_launcher_and_quarantine_preserved",
    }
    return all(existing.get(key) == expected.get(key) for key in required_keys)


def _recover_false_positive_contention(
    spec: StageSpec,
    staged: StageSpec,
    quarantine: dict[str, Any],
    original_terminal_status: dict[str, Any] | None,
    original_terminal_status_path: Path | None,
) -> dict[str, Any]:
    """Publish exactly one quarantined stage only after immutable re-audit proof."""

    payload, audit, error = _build_contention_reaudit(
        spec,
        staged,
        quarantine,
        original_terminal_status,
        original_terminal_status_path,
    )
    if payload is None or audit is None:
        return {
            "status": "QUARANTINED",
            "reason": error or "forensic re-audit could not be constructed",
            "staged_spec": staged,
            "quarantine": quarantine,
        }
    staged_certificate = staged.contention_reaudit_path
    existing_staged = load_json(staged_certificate)
    try:
        if existing_staged.get("_missing"):
            staged_write = _immutable_write_json(staged_certificate, payload)
            certificate = load_json(staged_certificate)
        elif existing_staged.get("_load_error"):
            raise RuntimeError("existing staged contention re-audit is unreadable")
        else:
            if not _matching_reaudit_payload(existing_staged, payload):
                raise RuntimeError("existing staged contention re-audit does not bind current raw forensic sources")
            staged_write = {
                "status": "MATCHED_EXISTING",
                "path": str(staged_certificate),
                "sha256": sha256_file(staged_certificate),
            }
            certificate = existing_staged
        certificate_sha = sha256_file(staged_certificate)
        canonical_outcome = _atomic_copy_verified(
            staged_certificate,
            spec.contention_reaudit_path,
            certificate_sha,
        )
    except Exception as exc:
        return {
            "status": "QUARANTINED",
            "reason": f"immutable contention re-audit publication failed: {type(exc).__name__}: {exc}",
            "staged_spec": staged,
            "quarantine": quarantine,
        }
    if not _matching_reaudit_payload(certificate, payload):
        return {
            "status": "QUARANTINED",
            "reason": "staged contention re-audit changed after immutable write",
            "staged_spec": staged,
            "quarantine": quarantine,
        }
    finalized = finalize_staged(
        spec,
        staged,
        audit=audit,
        expected_raw_artifacts=payload["source"]["raw_artifacts"],
    )
    finalized.update(
        {
            "staged_spec": staged,
            "contention_reaudit": {
                "status": "PUBLISHED" if finalized.get("status") == "PUBLISHED" else "PUBLISH_FAILED",
                "schema_version": CONTENTION_REAUDIT_SCHEMA_VERSION,
                "staged_path": str(staged_certificate),
                "canonical_path": str(spec.contention_reaudit_path),
                "sha256": certificate_sha,
                "staged_write": staged_write,
                "canonical_outcome": canonical_outcome,
                "source": payload["source"],
                "classifier": payload["classifier"],
            },
        }
    )
    return finalized


def recover_staging(
    spec: StageSpec,
    *,
    allow_contention_recovery: bool = False,
    original_terminal_status: dict[str, Any] | None = None,
    original_terminal_status_path: Path | None = None,
) -> dict[str, Any]:
    staged = _staging_spec(spec.stem.parent, spec)
    stage_dir = staged.stem.parent
    if not stage_dir.exists():
        return {"status": "NONE", "staged_spec": staged}
    quarantine = stage_dir / "quarantine.json"
    if quarantine.exists():
        saved_quarantine = load_json(quarantine)
        if not allow_contention_recovery:
            return {"status": "QUARANTINED", "staged_spec": staged, "quarantine": saved_quarantine}
        return _recover_false_positive_contention(
            spec,
            staged,
            saved_quarantine,
            original_terminal_status,
            original_terminal_status_path,
        )
    manifest = stage_dir / "publish_manifest.json"
    if manifest.exists():
        result = _publish_from_manifest(manifest)
        result["staged_spec"] = staged
        return result
    launcher = load_json(staged.launcher_path)
    if launcher.get("_missing") or launcher.get("_load_error"):
        return {
            "status": "FAIL",
            "reason": "staging directory exists without a readable launcher",
            "staged_spec": staged,
        }
    if str(launcher.get("state") or "").upper() == "RUNNING":
        pid = _int(launcher.get("pid"))
        identity = process_identity(pid) if pid is not None else None
        exact_live_child = bool(
            identity
            and str(identity.get("creation_date")) == str(launcher.get("process_creation_date"))
            and str(identity.get("command_line")) == str(launcher.get("process_command_line"))
        )
        if exact_live_child:
            return {
                "status": "ORPHAN_RUNNING",
                "reason": "exact staged evaluator child is still running; refusing duplicate launch",
                "child": identity,
                "staged_spec": staged,
            }
        quarantined = quarantine_staged(
            staged,
            "orphan evaluator monitoring ended before a finalized launcher; contention history is unprovable",
            {"launcher": launcher, "live_identity": identity},
        )
        return {"status": "QUARANTINED", "staged_spec": staged, "quarantine": quarantined}
    if str(launcher.get("state") or "").upper() == "COMPLETED":
        if (
            launcher.get("contention_detected") is not False
            or launcher.get("contention_snapshots")
            or launcher.get("contention_monitor_errors")
        ):
            quarantined = quarantine_staged(
                staged,
                "completed staging attempt contains contention or monitoring uncertainty",
                {
                    "contention_detected": launcher.get("contention_detected"),
                    "contention_snapshots": launcher.get("contention_snapshots"),
                    "contention_monitor_errors": launcher.get("contention_monitor_errors"),
                },
            )
            return {"status": "QUARANTINED", "staged_spec": staged, "quarantine": quarantined}
        result = finalize_staged(spec, staged)
        result["staged_spec"] = staged
        return result
    return {
        "status": "FAIL",
        "reason": f"staging launcher state={launcher.get('state')!r} is not recoverable",
        "staged_spec": staged,
    }


def _result(
    run_dir: Path,
    overall: str,
    state: str,
    reason: str,
    *,
    terminal: bool,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "overall": overall,
        "state": state,
        "reason": reason,
        "terminal": terminal,
        "claim_scope": "internal_method_measurement_only_not_slumbot_not_l5_l6",
    }
    payload.update(extra)
    return payload


def _ops_event_id(run_dir: Path, freeze: dict[str, Any], suffix: str) -> str:
    run_id = str(freeze.get("run_id") or run_dir.name)
    gate = _int(freeze.get("gate_iteration")) or 0
    return f"exp003_bundle_{run_id}_gate{gate}_{suffix}"


def append_ops_event(
    run_dir: Path,
    freeze: dict[str, Any],
    suffix: str,
    title: str,
    detail: str,
) -> dict[str, Any]:
    canonical_root = (REPO_ROOT / "models" / "alpha_holdem_v5_from_zero").resolve()
    try:
        run_dir.resolve().relative_to(canonical_root)
    except (OSError, ValueError):
        return {
            "appended": False,
            "reason": "noncanonical_run_dir_guard",
            "event_id": _ops_event_id(run_dir, freeze, suffix),
            "row": None,
        }
    return append_event_row(
        REPO_ROOT / "reports" / "v5_experiment_ledger.md",
        event_id=_ops_event_id(run_dir, freeze, suffix),
        title=title,
        detail=detail,
        dry_run=False,
    )


def persist_status(status_path: Path, payload: dict[str, Any]) -> None:
    if payload.get("terminal"):
        run_dir = Path(str(payload.get("run_dir") or status_path.parent))
        freeze = payload.get("freeze") if isinstance(payload.get("freeze"), dict) else {}
        event = append_ops_event(
            run_dir,
            freeze,
            "terminal",
            "EXP-003 fixed bundle terminal",
            (
                f"state={payload.get('state')} overall={payload.get('overall')} "
                f"reason={payload.get('reason')} claim_scope=method_measurement_only"
            ),
        )
        payload = {**payload, "ops_terminal_event": event}
    atomic_write_json(status_path, payload)


def _validate_freeze(
    run_dir: Path,
    freeze_status: dict[str, Any],
    bundle: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    selected = freeze_status.get("selected_gate") if isinstance(freeze_status.get("selected_gate"), dict) else {}
    archive = freeze_status.get("archive") if isinstance(freeze_status.get("archive"), dict) else {}
    checkpoint = archive.get("checkpoint") if isinstance(archive.get("checkpoint"), dict) else {}
    first_gate = bundle.get("first_eligible_gate") if isinstance(bundle.get("first_eligible_gate"), dict) else {}
    gate_path = Path(str(selected.get("path") or ""))
    if not gate_path.is_absolute():
        gate_path = (REPO_ROOT / gate_path).resolve()
    gate = load_json(gate_path)
    archive_path = Path(str(archive.get("path") or ""))
    if not archive_path.is_absolute():
        archive_path = (REPO_ROOT / archive_path).resolve()

    iteration = _int(selected.get("iteration"))
    target_iteration = _int(selected.get("target_iteration"))
    hands = _int(selected.get("checkpoint_hands"))
    archive_iteration = _int(checkpoint.get("iteration"))
    archive_hands = _int(checkpoint.get("total_hands"))
    expected_sha = str(archive.get("sha256") or "").lower()
    problems: list[str] = []
    manifest = load_json(run_dir / "run_manifest.json")
    manifest_run_id = str(manifest.get("run_id") or "")
    expected_gate_path = (run_dir / f"gate_{iteration}_status.json").resolve() if iteration is not None else None
    if _int(freeze_status.get("target_hands")) != EXP003_NATIVE_MIRROR_TARGET_HANDS:
        problems.append("freeze target_hands mismatch")
    if not _same_path(freeze_status.get("run_dir"), run_dir):
        problems.append("freeze run_dir does not match active run")
    if iteration is None or target_iteration != iteration or hands is None:
        problems.append("selected gate identity is incomplete or inconsistent")
    elif hands < EXP003_NATIVE_MIRROR_TARGET_HANDS:
        problems.append("selected gate is below the registered hand target")
    if str(selected.get("overall") or "").upper() != "PASS":
        problems.append("selected gate is not PASS")
    if expected_gate_path is None or gate_path.resolve() != expected_gate_path:
        problems.append("selected gate path is not the exact active-run gate artifact")
    if gate.get("_missing") or gate.get("_load_error"):
        problems.append("selected gate artifact is missing or unreadable")
    elif not (
        _int(gate.get("target_iteration")) == iteration
        and _int(gate.get("checkpoint_iteration")) == iteration
        and _int(gate.get("checkpoint_hands")) == hands
        and str(gate.get("overall") or "").upper() == "PASS"
    ):
        problems.append("selected gate artifact does not exactly match freeze status")
    if not (
        _int(first_gate.get("iteration")) == iteration
        and _int(first_gate.get("hands")) == hands
        and _same_path(first_gate.get("path"), gate_path)
    ):
        problems.append("freeze is not the queue validator's first eligible PASS gate")
    try:
        archive_path.resolve().relative_to((run_dir / "exp003_judgment_archives").resolve())
    except (OSError, ValueError):
        problems.append("frozen archive path is outside the registered active-run archive directory")
    if not archive_path.is_file() or not expected_sha:
        problems.append("frozen archive path or SHA256 is missing")
        actual_sha = ""
        actual_checkpoint: dict[str, Any] = {}
    else:
        actual_sha = sha256_file(archive_path)
        if actual_sha.lower() != expected_sha:
            problems.append("frozen archive SHA256 mismatch")
        actual_checkpoint = checkpoint_summary(archive_path)
        if actual_checkpoint.get("_missing") or actual_checkpoint.get("_load_error"):
            problems.append("frozen archive could not be loaded for checkpoint metadata verification")
        elif not (
            _int(actual_checkpoint.get("iteration")) == iteration
            and _int(actual_checkpoint.get("total_hands")) == hands
            and str(actual_checkpoint.get("run_id") or "") == manifest_run_id
        ):
            problems.append("torch-loaded frozen archive iteration/hands/run_id does not match the selected gate")
    if archive_iteration != iteration or archive_hands != hands:
        problems.append("frozen archive checkpoint metadata does not match selected gate")
    gate_run_id = str(gate.get("run_id") or "")
    archive_run_id = str(checkpoint.get("run_id") or "")
    if gate_run_id and archive_run_id and gate_run_id != archive_run_id:
        problems.append("frozen archive run_id does not match selected gate")
    if not manifest_run_id or gate_run_id != manifest_run_id or archive_run_id != manifest_run_id:
        problems.append("freeze gate/archive run_id does not exactly match run_manifest")
    if problems:
        return None, "; ".join(problems)
    return {
        "gate_iteration": int(iteration),
        "gate_hands": int(hands),
        "gate_path": str(gate_path),
        "archive_path": str(archive_path),
        "archive_sha256": expected_sha,
        "archive_actual_sha256": actual_sha.lower(),
        "archive_loaded_checkpoint": actual_checkpoint,
        "run_id": archive_run_id or gate_run_id,
    }, None


def _legacy_role1_inconclusive_preflight_allowance(
    run_dir: Path,
    bundle: dict[str, Any],
    freeze: dict[str, Any],
    role1: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate the sole queue-authorized legacy role1 continuation contract.

    This is intentionally a role3-launch exception, not a role1 success path.
    It is available only after the exact recovered post-vs-native role exists,
    has independently failed the fixed CI precision gate, and the queue says
    role3 is the only missing causal measurement.  It cannot produce normal
    REVIEW_READY/ADOPT evidence.
    """

    def fail(reason: str) -> dict[str, Any]:
        return {"status": "FAIL", "reason": reason}

    roles = bundle.get("roles") if isinstance(bundle.get("roles"), dict) else {}
    contract = bundle.get("legacy_preflight_contract")
    if not isinstance(contract, dict):
        return fail("queue did not expose an exact legacy preflight contract")
    if not isinstance(role1, dict):
        return fail("role1 is not an object")
    post = roles.get("post_vs_native") if isinstance(roles.get("post_vs_native"), dict) else None
    direct = roles.get("post_vs_pre_direct")
    expected_role1_path = (run_dir / EXP003_LEGACY_PRE_RESULT_NAME).resolve()
    expected_provenance_path = Path(str(expected_role1_path)[:-5] + ".legacy_provenance.json")
    expected_audit_path = Path(str(expected_role1_path)[:-5] + ".legacy_provenance_audit.json")
    try:
        post_spec = _stage_specs(run_dir, freeze)[0]
    except Exception as exc:
        return fail(f"could not derive the frozen post-vs-native role: {type(exc).__name__}: {exc}")
    expected_reaudit_path = post_spec.contention_reaudit_path.resolve()
    required_contract = {
        "schema_version": LEGACY_PREFLIGHT_CONTRACT_SCHEMA_VERSION,
        "role": "pre_vs_native",
        "run_id": EXP003_LEGACY_PRE_RUN_ID,
        "result_path": str(expected_role1_path),
        "candidate_iteration": EXP003_CUTOVER_ITERATION,
        "candidate_hands": EXP003_CUTOVER_HANDS,
        "candidate_sha256": EXP003_PRE_SHA256,
        "anchor_iteration": 4600,
        "anchor_hands": EXP003_NATIVE_ANCHOR_HANDS,
        "anchor_sha256": EXP003_NATIVE_SHA256,
        "provenance_path": str(expected_provenance_path),
        "audit_path": str(expected_audit_path),
        "post_vs_native_result_path": str(post_spec.result_path),
        "post_vs_native_candidate_iteration": freeze.get("gate_iteration"),
        "post_vs_native_candidate_hands": freeze.get("gate_hands"),
        "post_vs_native_candidate_sha256": post_spec.candidate_sha256,
        "post_vs_native_contention_reaudit_path": str(expected_reaudit_path),
        "required_ci_precision_failed_roles": ["post_vs_native"],
        "inconclusive_only": True,
        "requires_post_vs_native_ci_failure": True,
        "forbids_review_ready": True,
        "forbids_additional_pairs": True,
        "normal_launcher_evidence": False,
    }
    for key, expected in required_contract.items():
        if contract.get(key) != expected:
            return fail(f"legacy preflight contract field {key!r} is not the registered exact value")
    if not (
        str(bundle.get("status") or "").upper() == "INCOMPLETE"
        and direct is None
        and bundle.get("legacy_inconclusive_roles") == ["pre_vs_native"]
        and bundle.get("ci_precision_failed_roles") == ["post_vs_native"]
        and bundle.get("candidate_checkpoint_hands") == freeze.get("gate_hands")
    ):
        return fail("queue state is not exactly role3-missing with role2-only fixed CI failure")
    if not (
        role1.get("legacy_inconclusive_only") is True
        and role1.get("launcher_evidence_ok") is False
        and role1.get("judgmentable") is False
        and role1.get("usable") is False
        and role1.get("base_judgmentable") is True
        and role1.get("candidate_iteration") == EXP003_CUTOVER_ITERATION
        and role1.get("candidate_hands") == EXP003_CUTOVER_HANDS
        and role1.get("anchor_iteration") == 4600
        and role1.get("anchor_hands") == EXP003_NATIVE_ANCHOR_HANDS
        and role1.get("candidate_sha256") == EXP003_PRE_SHA256
        and role1.get("anchor_sha256") == EXP003_NATIVE_SHA256
        and _same_path(role1.get("path"), expected_role1_path)
        and _same_path(role1.get("candidate_path"), PRE_CHECKPOINT_PATH)
        and _same_path(role1.get("anchor_path"), NATIVE_CHECKPOINT_PATH)
    ):
        return fail("role1 does not exactly match the registered legacy pre-vs-native provenance identity")
    if not isinstance(post, dict) or not _published_role_structural(post, post_spec, freeze):
        return fail("post-vs-native is not a structurally complete frozen role")
    if not (
        post.get("base_judgmentable") is True
        and post.get("launcher_evidence_ok") is True
        and post.get("judgmentable") is True
        and post.get("usable") is False
        and post.get("ci_precision_failed") is True
        and post.get("ci_ok") is False
        and post.get("legacy_inconclusive_only") is False
        and _same_path(post.get("path"), post_spec.result_path)
    ):
        return fail("post-vs-native does not independently prove the registered CI precision failure")
    provenance = role1.get("legacy_provenance") if isinstance(role1.get("legacy_provenance"), dict) else {}
    companions = role1.get("companion_paths") if isinstance(role1.get("companion_paths"), dict) else {}
    post_companions = post.get("companion_paths") if isinstance(post.get("companion_paths"), dict) else {}
    if not (
        provenance.get("status") == "PASS"
        and _same_path(provenance.get("path"), expected_provenance_path)
        and _same_path(provenance.get("audit_path"), expected_audit_path)
        and _same_path(companions.get("legacy_provenance"), expected_provenance_path)
        and _same_path(companions.get("legacy_provenance_audit"), expected_audit_path)
        and _same_path(post_companions.get("contention_reaudit"), expected_reaudit_path)
    ):
        return fail("role companion provenance paths do not exactly match the legacy/recovered contract")
    if not (expected_provenance_path.is_file() and expected_audit_path.is_file() and expected_reaudit_path.is_file()):
        return fail("required legacy or recovered provenance companion is missing")
    try:
        provenance_sha = sha256_file(expected_provenance_path)
        audit_sha = sha256_file(expected_audit_path)
        reaudit_sha = sha256_file(expected_reaudit_path)
    except Exception as exc:
        return fail(f"could not hash legacy/recovered provenance companion: {type(exc).__name__}: {exc}")
    if not (
        contract.get("provenance_sha256") == provenance_sha
        and provenance.get("sha256") == provenance_sha
        and contract.get("audit_sha256") == audit_sha
        and provenance.get("audit_sha256") == audit_sha
        and contract.get("post_vs_native_contention_reaudit_sha256") == reaudit_sha
    ):
        return fail("legacy/recovered provenance companion SHA256 mismatch")
    provenance_json = load_json(expected_provenance_path)
    audit_json = load_json(expected_audit_path)
    reaudit_json = load_json(expected_reaudit_path)
    if (
        provenance_json.get("_missing")
        or provenance_json.get("_load_error")
        or audit_json.get("_missing")
        or audit_json.get("_load_error")
        or reaudit_json.get("_missing")
        or reaudit_json.get("_load_error")
    ):
        return fail("legacy/recovered provenance companion JSON is unreadable")
    if not (
        provenance_json.get("schema_version") == EXP003_LEGACY_PRE_SCHEMA_VERSION
        and provenance_json.get("state") == "LEGACY_PROVENANCE_INCONCLUSIVE_ONLY_PASS"
        and provenance_json.get("role") == "pre_vs_native"
        and provenance_json.get("run_id") == EXP003_LEGACY_PRE_RUN_ID
        and _same_path(provenance_json.get("result_path"), expected_role1_path)
        and provenance_json.get("candidate_sha256") == EXP003_PRE_SHA256
        and provenance_json.get("anchor_sha256") == EXP003_NATIVE_SHA256
        and provenance_json.get("decision_capability") == "INCONCLUSIVE_ONLY"
        and provenance_json.get("generic_fallback") is False
        and audit_json.get("schema_version") == EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION
        and audit_json.get("overall") == "PASS"
        and audit_json.get("role") == "pre_vs_native"
        and audit_json.get("run_id") == EXP003_LEGACY_PRE_RUN_ID
        and reaudit_json.get("schema_version") == CONTENTION_REAUDIT_SCHEMA_VERSION
        and reaudit_json.get("state") == "FALSE_POSITIVE_CONTENTION_REAUDIT_PASS"
        and reaudit_json.get("role") == "post_vs_native"
        and reaudit_json.get("recovery_eligible") is True
        and reaudit_json.get("forensic_verdict") == "PASS"
    ):
        return fail("legacy/recovered provenance companion content is not the exact INCONCLUSIVE-only contract")
    return {
        "status": "PASS",
        "reason": "exact role1 legacy provenance plus recovered role2-only CI failure permits the one remaining role3 measurement",
        "contract": contract,
    }


def preflight(
    run_dir: Path,
    validator: Callable[[Path, int], dict[str, Any]] | None = None,
    process_scan: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    validator = validator or exp003_mirror_bundle_status
    process_scan = process_scan or (lambda: eval_contention(run_dir))
    freeze_path = run_dir / "exp003_judgment_freeze_status.json"
    freeze_status = load_json(freeze_path)
    if freeze_status.get("_load_error"):
        return _result(
            run_dir,
            "FAIL",
            "FREEZE_STATUS_CORRUPT",
            str(freeze_status["_load_error"]),
            terminal=True,
            freeze_status_path=str(freeze_path),
        )
    freeze_overall = str(freeze_status.get("overall") or "MISSING").upper()
    if freeze_overall == "FAIL":
        return _result(
            run_dir,
            "FAIL",
            "FREEZE_TERMINAL_FAIL",
            str(freeze_status.get("reason") or "EXP-003 freeze failed"),
            terminal=True,
            freeze_status_path=str(freeze_path),
            freeze_status=freeze_status,
        )
    if freeze_overall != "PASS":
        return _result(
            run_dir,
            "WAITING",
            "WAITING_FOR_FREEZE_PASS",
            f"freeze overall={freeze_overall}; PASS required",
            terminal=False,
            freeze_status_path=str(freeze_path),
        )
    if str(freeze_status.get("state") or "") != "FROZEN_FIRST_ELIGIBLE_PASS":
        return _result(
            run_dir,
            "FAIL",
            "FREEZE_STATE_INVALID",
            "freeze PASS is accepted only with state=FROZEN_FIRST_ELIGIBLE_PASS",
            terminal=True,
            freeze_status_path=str(freeze_path),
            freeze_status=freeze_status,
        )

    bundle = validator(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
    freeze, freeze_error = _validate_freeze(run_dir, freeze_status, bundle)
    if freeze_error:
        return _result(
            run_dir,
            "FAIL",
            "FREEZE_INTEGRITY_FAIL",
            freeze_error,
            terminal=True,
            freeze_status_path=str(freeze_path),
            queue_bundle_status=bundle.get("status"),
        )

    role1 = (bundle.get("roles") or {}).get("pre_vs_native")
    role1_valid = bool(
        isinstance(role1, dict)
        and role1.get("usable") is True
        and str(role1.get("candidate_sha256") or "").lower() == EXP003_PRE_SHA256
        and str(role1.get("anchor_sha256") or "").lower() == EXP003_NATIVE_SHA256
        and _same_path(role1.get("candidate_path"), PRE_CHECKPOINT_PATH)
        and _same_path(role1.get("anchor_path"), NATIVE_CHECKPOINT_PATH)
    )
    legacy_role1_allowance = (
        {"status": "NOT_NEEDED", "reason": "role1 has ordinary usable launcher evidence"}
        if role1_valid
        else _legacy_role1_inconclusive_preflight_allowance(run_dir, bundle, freeze, role1)
    )
    role1_continuity_mode = (
        "NORMAL_USABLE"
        if role1_valid
        else "LEGACY_INCONCLUSIVE_ONLY_ROLE3_CONTINUATION"
        if legacy_role1_allowance.get("status") == "PASS"
        else "NONE"
    )
    if role1_continuity_mode == "NONE":
        return _result(
            run_dir,
            "FAIL",
            "ROLE1_NOT_USABLE",
            (
                "pre-cutover gate21800 vs native75M role is missing/unusable or the exact "
                "legacy-INCONCLUSIVE-only role3 continuation contract did not validate"
            ),
            terminal=True,
            freeze=freeze,
            role1=role1,
            legacy_role1_allowance=legacy_role1_allowance,
        )

    fixed_inputs = [
        ("evaluator", EVALUATOR_PATH, EXP003_EVALUATOR_SHA256),
        ("pre_checkpoint", PRE_CHECKPOINT_PATH, EXP003_PRE_SHA256),
        ("native_checkpoint", NATIVE_CHECKPOINT_PATH, EXP003_NATIVE_SHA256),
    ]
    input_audit: dict[str, Any] = {}
    for name, path, expected in fixed_inputs:
        actual = sha256_file(path) if path.is_file() else ""
        input_audit[name] = {
            "path": str(path.resolve()),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "status": "PASS" if actual.lower() == expected else "FAIL",
        }
    if any(row["status"] != "PASS" for row in input_audit.values()):
        return _result(
            run_dir,
            "FAIL",
            "FIXED_INPUT_INTEGRITY_FAIL",
            "evaluator or fixed model SHA256 does not match the registered protocol",
            terminal=True,
            freeze=freeze,
            input_audit=input_audit,
        )

    health_path = run_dir / "health_status.json"
    health = load_json(health_path)
    if str(health.get("overall") or "").upper() != "PASS":
        return _result(
            run_dir,
            "WAITING",
            "WAITING_FOR_HEALTH_PASS",
            f"health overall={health.get('overall')!r}; PASS required before mirror launch",
            terminal=False,
            freeze=freeze,
            health_status_path=str(health_path),
        )
    trainer_stderr = run_dir / "console.err.log"
    if not trainer_stderr.is_file() or trainer_stderr.stat().st_size != 0:
        return _result(
            run_dir,
            "WAITING",
            "WAITING_FOR_EMPTY_TRAINER_STDERR",
            "trainer console.err.log must exist and be empty before mirror launch",
            terminal=False,
            freeze=freeze,
            trainer_stderr_path=str(trainer_stderr),
            trainer_stderr_bytes=(trainer_stderr.stat().st_size if trainer_stderr.exists() else None),
        )
    try:
        contention_raw = process_scan()
    except Exception as exc:
        return _result(
            run_dir,
            "WAITING",
            "WAITING_FOR_PROCESS_SCAN",
            f"{type(exc).__name__}: {exc}",
            terminal=False,
            freeze=freeze,
        )
    if isinstance(contention_raw, dict):
        contention = contention_raw
    else:
        contention = {
            "busy": bool(contention_raw),
            "processes": list(contention_raw or []),
            "slumbot_running_statuses": [],
        }
    if contention.get("busy"):
        return _result(
            run_dir,
            "WAITING",
            "WAITING_FOR_EVAL_SLOT",
            "active play_slumbot/v5_mirror process prevents launch",
            terminal=False,
            freeze=freeze,
            contention=contention,
        )
    return _result(
        run_dir,
        "PASS",
        (
            "READY_TO_LAUNCH"
            if role1_continuity_mode == "NORMAL_USABLE"
            else "LEGACY_INCONCLUSIVE_ONLY_ROLE3_CONTINUATION"
        ),
        (
            "freeze, ordinary usable role1, fixed inputs, trainer health, stderr, and eval slot all verified"
            if role1_continuity_mode == "NORMAL_USABLE"
            else (
                "exact legacy role1 provenance plus recovered post-vs-native-only CI failure verified; "
                "launching only the remaining direct role cannot support REVIEW_READY/ADOPT"
            )
        ),
        terminal=False,
        freeze=freeze,
        role1=role1,
        role1_continuity_mode=role1_continuity_mode,
        legacy_role1_allowance=legacy_role1_allowance,
        input_audit=input_audit,
        health_status_path=str(health_path),
        queue_bundle_status=bundle.get("status"),
        bundle=bundle,
    )


def _role(bundle: dict[str, Any], name: str) -> dict[str, Any] | None:
    roles = bundle.get("roles") if isinstance(bundle.get("roles"), dict) else {}
    value = roles.get(name)
    return value if isinstance(value, dict) else None


def _published_role_structural(role: dict[str, Any], spec: StageSpec, freeze: dict[str, Any]) -> bool:
    expected_anchor_hands = 75_479_020 if spec.role == "post_vs_native" else 358_064_575
    return bool(
        role.get("execution_ok") is True
        and role.get("companions_ok") is True
        and role.get("stderr_empty") is True
        and role.get("pairs") == EXP003_MIRROR_PAIRS
        and role.get("seed") == EXP003_MIRROR_SEED
        and role.get("policy_mode") == EXP003_MIRROR_POLICY_MODE
        and role.get("starting_stack") == STARTING_STACK
        and str(role.get("device") or "").lower() == DEVICE
        and role.get("ood_threshold") == EXP003_MIRROR_OOD_MAX
        and role.get("candidate_hands") == freeze.get("gate_hands")
        and role.get("anchor_hands") == expected_anchor_hands
        and role.get("candidate_sha256") == spec.candidate_sha256
        and role.get("anchor_sha256") == spec.anchor_sha256
        and _same_path(role.get("candidate_path"), spec.candidate_path)
        and _same_path(role.get("anchor_path"), spec.anchor_path)
        and role.get("candidate_bb100") is not None
        and role.get("candidate_ci95_bb100") is not None
        and role.get("ood_rate") is not None
    )


def scan_published_role_artifacts(
    run_dir: Path,
    spec: StageSpec,
    freeze: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed on partial or duplicate artifacts hidden by queue selection."""

    prefix = (
        "v5_mirror_eval_exp003_post_vs_native_"
        if spec.role == "post_vs_native"
        else "v5_mirror_eval_exp003_post_vs_pre_"
    )
    suffixes = (
        ".execution.json",
        ".launcher.json",
        ".stdout.log",
        ".stderr.log",
        ".json",
        ".md",
    )
    groups: dict[str, set[str]] = {}
    for path in run_dir.glob(prefix + "*"):
        if not path.is_file():
            continue
        name = path.name
        if name.endswith(".contention_reaudit.json"):
            continue
        stem = None
        suffix_used = None
        for suffix in suffixes:
            if name.endswith(suffix):
                stem = name[: -len(suffix)]
                suffix_used = suffix
                break
        if stem is not None and suffix_used is not None:
            groups.setdefault(stem, set()).add(suffix_used)
    partial_groups = [
        {"stem": stem, "suffixes": sorted(found)}
        for stem, found in sorted(groups.items())
        if ".json" not in found
    ]

    expected_anchor_hands = 75_479_020 if spec.role == "post_vs_native" else 358_064_575
    matching: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob(prefix + "*.json")):
        # Companion JSON files are excluded by their longer suffixes.
        if path.name.endswith((".execution.json", ".launcher.json", ".contention_reaudit.json")):
            continue
        mirror = load_json(path)
        if mirror.get("_missing") or mirror.get("_load_error"):
            matching.append({"path": str(path), "load_error": mirror})
            continue
        record = _exp003_mirror_record(path, mirror)
        same_role = bool(
            record.get("candidate_hands") == freeze.get("gate_hands")
            and record.get("anchor_hands") == expected_anchor_hands
        )
        if same_role or path.resolve() == spec.result_path.resolve():
            matching.append(record)
    structural = [
        row
        for row in matching
        if isinstance(row, dict) and _published_role_structural(row, spec, freeze)
    ]
    invalid = [row for row in matching if row not in structural]
    problems: list[str] = []
    if partial_groups:
        problems.append("partial canonical role artifact group(s)")
    if invalid:
        problems.append("matching role artifact(s) are structurally invalid")
    if len(structural) > 1:
        problems.append("duplicate structurally complete role artifacts create selection conflict")
    return {
        "status": "PASS" if not problems else "FAIL",
        "problems": problems,
        "partial_groups": partial_groups,
        "matching_records": matching,
        "structural_records": structural,
        "selected": structural[0] if len(structural) == 1 else None,
    }


def _is_recoverable_false_positive_terminal(
    previous: dict[str, Any],
    run_dir: Path,
    status_path: Path,
) -> bool:
    """Recognize only the single captured gate24900 false-positive terminal.

    This predicate runs *before* a resumed watcher writes a status.  It therefore
    repeats the canonical rearm identity checks and hashes the preserved staged
    launcher/quarantine itself.  A merely similar FAIL state remains sticky and
    cannot be converted into a different terminal result by a direct invocation.
    """

    run_dir = Path(run_dir).resolve()
    status_path = Path(status_path).resolve()
    canonical_status_path = (run_dir / "v5_exp003_bundle_watch_status.json").resolve()
    freeze = previous.get("freeze") if isinstance(previous.get("freeze"), dict) else {}
    quarantine = previous.get("quarantine") if isinstance(previous.get("quarantine"), dict) else {}
    if not (
        status_path == canonical_status_path
        and _same_path(previous.get("run_dir"), run_dir)
        and str(previous.get("overall") or "").upper() == "FAIL"
        and previous.get("terminal") is True
        and str(previous.get("state") or "") == "MEASUREMENT_CONTENTION_QUARANTINED"
        and str(quarantine.get("state") or "").upper() == "QUARANTINED"
        and quarantine.get("published") is False
        and str(quarantine.get("role") or "") == "post_vs_native"
        and _int(freeze.get("gate_iteration")) == CAPTURED_FALSE_POSITIVE_FREEZE["gate_iteration"]
        and _int(freeze.get("gate_hands")) == CAPTURED_FALSE_POSITIVE_FREEZE["gate_hands"]
        and str(freeze.get("archive_sha256") or "").lower()
        == CAPTURED_FALSE_POSITIVE_FREEZE["archive_sha256"]
        and str(freeze.get("archive_actual_sha256") or "").lower()
        == CAPTURED_FALSE_POSITIVE_FREEZE["archive_sha256"]
    ):
        return False
    try:
        spec = _stage_specs(run_dir, freeze)[0]
        staged = _staging_spec(run_dir, spec)
        launcher_path = staged.launcher_path
        quarantine_path = staged.stem.parent / "quarantine.json"
        return bool(
            launcher_path.is_file()
            and quarantine_path.is_file()
            and sha256_file(launcher_path) == CAPTURED_FALSE_POSITIVE_OBSERVER["launcher_sha256"]
            and sha256_file(quarantine_path) == CAPTURED_FALSE_POSITIVE_OBSERVER["quarantine_sha256"]
        )
    except Exception:
        return False


def run_once(
    run_dir: Path,
    *,
    python: str = sys.executable,
    status_path: Path | None = None,
    validator: Callable[[Path, int], dict[str, Any]] | None = None,
    process_scan: Callable[[], Any] | None = None,
    launcher: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    status_path = Path(status_path) if status_path else run_dir / "v5_exp003_bundle_watch_status.json"
    validator = validator or exp003_mirror_bundle_status
    process_scan = process_scan or (lambda: eval_contention(run_dir))
    launcher = launcher or launch_stage

    previous = load_json(status_path)
    resume_false_positive_contention = _is_recoverable_false_positive_terminal(previous, run_dir, status_path)
    if (
        str(previous.get("overall") or "").upper()
        in {"FAIL", "REVIEW_READY", "INCONCLUSIVE_JUDGMENT_REQUIRED"}
        and not resume_false_positive_contention
    ):
        return previous

    recovered_roles: list[dict[str, Any]] = []
    pre_recovered_roles: set[str] = set()
    if resume_false_positive_contention:
        # The terminal predicate has already bound this to the one captured
        # completed role2.  Recover it *before* normal preflight so the queue
        # can see its canonical fixed-CI result.  Never infer precision from
        # staging and never launch any new evaluator on this path.
        try:
            recovery_freeze = previous["freeze"]
            recovery_spec = _stage_specs(run_dir, recovery_freeze)[0]
        except Exception:
            return previous
        recovery = recover_staging(
            recovery_spec,
            allow_contention_recovery=True,
            original_terminal_status=previous,
            original_terminal_status_path=status_path,
        )
        contention_reaudit = recovery.get("contention_reaudit")
        if not (
            recovery.get("status") == "PUBLISHED"
            and isinstance(contention_reaudit, dict)
            and contention_reaudit.get("status") == "PUBLISHED"
        ):
            # Preserve the original terminal status byte-for-byte on any
            # failed forensic recovery; no preflight, retry, or new pairs.
            return previous
        recovery_event = append_ops_event(
            run_dir,
            recovery_freeze,
            f"{recovery_spec.role}_false_positive_contention_recovery",
            f"EXP-003 {recovery_spec.role} false-positive contention recovery",
            (
                f"role={recovery_spec.role} no_new_pairs=true cert={contention_reaudit.get('canonical_path')} "
                f"cert_sha256={contention_reaudit.get('sha256')} "
                "original_launcher_quarantine_preserved=true"
            ),
        )
        recovered_roles.append(
            {
                "role": recovery_spec.role,
                "contention_reaudit": contention_reaudit,
                "ops_event": recovery_event,
            }
        )
        pre_recovered_roles.add(recovery_spec.role)
        # This is the first authorized replacement of the historic terminal
        # status: exact canonical role2 and its immutable certificate exist.
        persist_status(
            status_path,
            _result(
                run_dir,
                "PASS",
                f"CONTENTION_REAUDIT_PUBLISHED_{recovery_spec.role.upper()}",
                f"{recovery_spec.role} exact staged artifacts recovered from the single allowlisted false positive; no pairs rerun",
                terminal=False,
                freeze=recovery_freeze,
                recovered_roles=recovered_roles,
                next_action="re-run normal preflight; only an exact legacy-INCONCLUSIVE contract may permit role3",
            ),
        )

    # After the exact role2 recovery (if any), validate immutable inputs and
    # the queue state normally.  This is where the narrow role1 legacy
    # INCONCLUSIVE-only continuation contract is checked.
    first = preflight(
        run_dir,
        validator=validator,
        process_scan=lambda: {"busy": False, "processes": [], "slumbot_running_statuses": []},
    )
    persist_status(status_path, first)
    if first["overall"] != "PASS":
        return first
    freeze = first["freeze"]
    legacy_inconclusive_role3_continuation = (
        first.get("role1_continuity_mode") == "LEGACY_INCONCLUSIVE_ONLY_ROLE3_CONTINUATION"
    )
    legacy_preflight_contract = (
        first.get("legacy_role1_allowance", {}).get("contract")
        if isinstance(first.get("legacy_role1_allowance"), dict)
        else None
    )
    completed_roles: list[str] = []
    measurement_failures: list[dict[str, Any]] = []

    for spec in _stage_specs(run_dir, freeze):
        if spec.role in pre_recovered_roles:
            recovery = {"status": "NONE", "staged_spec": _staging_spec(run_dir, spec)}
        else:
            recovery = recover_staging(
                spec,
                allow_contention_recovery=False,
            )
        if recovery.get("status") == "ORPHAN_RUNNING":
            waiting = _result(
                run_dir,
                "WAITING",
                "WAITING_FOR_EXACT_ORPHAN_CHILD",
                "exact staged evaluator child is still running; duplicate launch is forbidden",
                terminal=False,
                freeze=freeze,
                active_role=spec.role,
                recovery={key: value for key, value in recovery.items() if key != "staged_spec"},
            )
            persist_status(status_path, waiting)
            return waiting
        if recovery.get("status") in {"FAIL", "QUARANTINED"}:
            failed = _result(
                run_dir,
                "FAIL",
                "STAGING_RECOVERY_FAIL",
                f"{spec.role} fixed attempt cannot be safely recovered or retried",
                terminal=True,
                freeze=freeze,
                recovery={key: value for key, value in recovery.items() if key != "staged_spec"},
            )
            persist_status(status_path, failed)
            return failed

        contention_reaudit = recovery.get("contention_reaudit")
        if recovery.get("status") == "PUBLISHED" and isinstance(contention_reaudit, dict):
            if contention_reaudit.get("status") != "PUBLISHED":
                failed = _result(
                    run_dir,
                    "FAIL",
                    "CONTENTION_REAUDIT_PUBLISH_INCONSISTENT",
                    f"{spec.role} recovery reported publication without a published immutable forensic companion",
                    terminal=True,
                    freeze=freeze,
                    recovery={key: value for key, value in recovery.items() if key != "staged_spec"},
                )
                persist_status(status_path, failed)
                return failed
            recovery_event = append_ops_event(
                run_dir,
                freeze,
                f"{spec.role}_false_positive_contention_recovery",
                f"EXP-003 {spec.role} false-positive contention recovery",
                (
                    f"role={spec.role} no_new_pairs=true cert={contention_reaudit.get('canonical_path')} "
                    f"cert_sha256={contention_reaudit.get('sha256')} "
                    "original_launcher_quarantine_preserved=true"
                ),
            )
            recovered_roles.append(
                {
                    "role": spec.role,
                    "contention_reaudit": contention_reaudit,
                    "ops_event": recovery_event,
                }
            )
            # This is the first authorized replacement of the prior terminal
            # status: it occurs only after exact canonical artifacts and their
            # immutable certificate exist.
            recovered_status = _result(
                run_dir,
                "PASS",
                f"CONTENTION_REAUDIT_PUBLISHED_{spec.role.upper()}",
                f"{spec.role} exact staged artifacts recovered from the single allowlisted false positive; no pairs rerun",
                terminal=False,
                freeze=freeze,
                recovered_roles=recovered_roles,
                next_action="reuse recovered role and continue the remaining fixed causal role",
            )
            persist_status(status_path, recovered_status)

        published_scan = scan_published_role_artifacts(run_dir, spec, freeze)
        if published_scan.get("status") != "PASS":
            failed = _result(
                run_dir,
                "FAIL",
                "PUBLISHED_ROLE_ARTIFACT_CONFLICT",
                f"{spec.role} has partial, invalid, or duplicate canonical artifacts; no retry/selection is allowed",
                terminal=True,
                freeze=freeze,
                published_scan=published_scan,
            )
            persist_status(status_path, failed)
            return failed

        current = preflight(run_dir, validator=validator, process_scan=process_scan)
        persist_status(status_path, current)
        if current["overall"] != "PASS":
            return current
        bundle = current["bundle"]
        existing_role = _role(bundle, spec.role)
        scanned_role = published_scan.get("selected")
        if (existing_role is None) != (scanned_role is None) or (
            existing_role is not None
            and scanned_role is not None
            and str(existing_role.get("path")) != str(scanned_role.get("path"))
        ):
            failed = _result(
                run_dir,
                "FAIL",
                "QUEUE_ROLE_SELECTION_MISMATCH",
                f"queue-selected {spec.role} disagrees with exhaustive canonical artifact scan",
                terminal=True,
                freeze=freeze,
                queue_role=existing_role,
                published_scan=published_scan,
            )
            persist_status(status_path, failed)
            return failed
        if existing_role is not None:
            if not _published_role_structural(existing_role, spec, freeze):
                failed = _result(
                    run_dir,
                    "FAIL",
                    "EXISTING_ROLE_NOT_STRUCTURAL",
                    f"existing {spec.role} artifacts are structurally invalid; preserving and refusing retry",
                    terminal=True,
                    freeze=freeze,
                    role=existing_role,
                )
                persist_status(status_path, failed)
                return failed
            append_ops_event(
                run_dir,
                freeze,
                f"{spec.role}_start",
                f"EXP-003 {spec.role} fixed measurement start",
                (
                    f"role={spec.role} pairs={EXP003_MIRROR_PAIRS} seed={EXP003_MIRROR_SEED} "
                    f"candidate_sha256={spec.candidate_sha256} reused_existing=true"
                ),
            )
            append_ops_event(
                run_dir,
                freeze,
                f"{spec.role}_done",
                f"EXP-003 {spec.role} fixed measurement done",
                (
                    f"role={spec.role} usable={existing_role.get('usable')} "
                    f"ci_ok={existing_role.get('ci_ok')} ood_ok={existing_role.get('ood_ok')} "
                    f"path={existing_role.get('path')}"
                ),
            )
            completed_roles.append(spec.role)
            if existing_role.get("usable") is not True:
                measurement_failures.append(
                    {
                        "role": spec.role,
                        "ci_ok": existing_role.get("ci_ok"),
                        "ood_ok": existing_role.get("ood_ok"),
                        "path": existing_role.get("path"),
                    }
                )
            continue
        existing_artifacts = [str(path) for path in spec.artifacts() if path.exists()]
        if existing_artifacts:
            failed = _result(
                run_dir,
                "FAIL",
                "EXISTING_ARTIFACTS_NOT_USABLE",
                f"partial/failed {spec.role} artifacts exist; preserving them and refusing overwrite",
                terminal=True,
                freeze=freeze,
                existing_artifacts=existing_artifacts,
            )
            persist_status(status_path, failed)
            return failed

        running = _result(
            run_dir,
            "RUNNING",
            f"RUNNING_{spec.role.upper()}",
            f"launching fixed {spec.role} mirror role sequentially",
            terminal=False,
            freeze=freeze,
            completed_roles=completed_roles,
            active_role=spec.role,
            expected_artifacts=[str(path) for path in spec.artifacts()],
            watcher_identity=process_identity(os.getpid()),
            staging_dir=str(_staging_spec(run_dir, spec).stem.parent),
        )
        append_ops_event(
            run_dir,
            freeze,
            f"{spec.role}_start",
            f"EXP-003 {spec.role} fixed measurement start",
            (
                f"role={spec.role} pairs={EXP003_MIRROR_PAIRS} seed={EXP003_MIRROR_SEED} "
                f"candidate_sha256={spec.candidate_sha256} anchor_sha256={spec.anchor_sha256}"
            ),
        )
        persist_status(status_path, running)

        def on_started(launcher_payload: dict[str, Any]) -> None:
            started_status = dict(running)
            started_status.update(
                {
                    "checked_at": now_iso(),
                    "launcher_pid": launcher_payload.get("pid"),
                    "launcher_creation_date": launcher_payload.get("process_creation_date"),
                    "launcher_command_line": launcher_payload.get("process_command_line"),
                    "launcher_path": str(_staging_spec(run_dir, spec).launcher_path),
                }
            )
            persist_status(status_path, started_status)

        launched = launcher(
            spec,
            python,
            on_started,
            contention_scan=lambda excluded: eval_contention(run_dir, excluded),
        )
        if str(launched.get("status") or "").upper() != "STAGED_COMPLETED":
            failed = _result(
                run_dir,
                "FAIL",
                "MIRROR_EXECUTION_FAIL",
                f"{spec.role} launcher returned {launched.get('status')}",
                terminal=True,
                freeze=freeze,
                launch=launched,
            )
            persist_status(status_path, failed)
            return failed

        staged_spec = launched.get("staged_spec")
        if not isinstance(staged_spec, StageSpec):
            failed = _result(
                run_dir,
                "FAIL",
                "MIRROR_STAGING_SCHEMA_FAIL",
                f"{spec.role} launcher did not return its staged artifact schema",
                terminal=True,
                freeze=freeze,
                launch={key: value for key, value in launched.items() if key not in {"canonical_spec", "staged_spec"}},
            )
            persist_status(status_path, failed)
            return failed
        if launched.get("launcher", {}).get("contention_detected"):
            quarantine = quarantine_staged(
                staged_spec,
                "Slumbot/mirror contention was observed during the fixed measurement",
                launched.get("launcher", {}).get("contention_snapshots"),
            )
            failed = _result(
                run_dir,
                "FAIL",
                "MEASUREMENT_CONTENTION_QUARANTINED",
                f"{spec.role} stayed out of the canonical glob because eval contention was detected",
                terminal=True,
                freeze=freeze,
                quarantine=quarantine,
            )
            persist_status(status_path, failed)
            return failed

        # Re-prove the exact first gate, run_id, paths, model hashes, trainer
        # health, and empty eval slot after the long-running measurement.
        after = preflight(run_dir, validator=validator, process_scan=process_scan)
        if after.get("overall") != "PASS":
            quarantine = quarantine_staged(
                staged_spec,
                "post-measurement immutable-input/health verification failed",
                after,
            )
            failed = _result(
                run_dir,
                "FAIL",
                "POST_MEASUREMENT_VERIFY_QUARANTINED",
                f"{spec.role} was not published because post-measurement verification failed",
                terminal=True,
                freeze=freeze,
                quarantine=quarantine,
            )
            persist_status(status_path, failed)
            return failed

        finalized = finalize_staged(spec, staged_spec)
        if finalized.get("status") != "PUBLISHED":
            failed = _result(
                run_dir,
                "FAIL",
                "STAGED_ARTIFACT_PUBLISH_FAIL",
                f"{spec.role} companions failed staged validation/publication",
                terminal=True,
                freeze=freeze,
                finalized=finalized,
            )
            persist_status(status_path, failed)
            return failed

        post_publish_scan = scan_published_role_artifacts(run_dir, spec, freeze)
        if post_publish_scan.get("status") != "PASS":
            failed = _result(
                run_dir,
                "FAIL",
                "POST_PUBLISH_ROLE_CONFLICT",
                f"{spec.role} publication exposed a partial/duplicate role conflict",
                terminal=True,
                freeze=freeze,
                finalized=finalized,
                published_scan=post_publish_scan,
            )
            persist_status(status_path, failed)
            return failed

        refreshed = validator(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
        refreshed_role = _role(refreshed, spec.role)
        if not refreshed_role or not _published_role_structural(refreshed_role, spec, freeze):
            failed = _result(
                run_dir,
                "FAIL",
                "QUEUE_VALIDATION_FAIL",
                f"canonical queue validator rejected completed {spec.role} artifacts",
                terminal=True,
                freeze=freeze,
                launch=launched,
                queue_bundle=refreshed,
            )
            persist_status(status_path, failed)
            return failed
        completed_roles.append(spec.role)
        if refreshed_role.get("usable") is not True:
            # A fixed 25k CI/OOD failure is evidence, not permission to add
            # pairs.  Preserve it and still run the other causal role.
            measurement_failures.append(
                {
                    "role": spec.role,
                    "ci_ok": refreshed_role.get("ci_ok"),
                    "ood_ok": refreshed_role.get("ood_ok"),
                    "path": refreshed_role.get("path"),
                }
            )
        append_ops_event(
            run_dir,
            freeze,
            f"{spec.role}_done",
            f"EXP-003 {spec.role} fixed measurement done",
            (
                f"role={spec.role} usable={refreshed_role.get('usable')} "
                f"ci_ok={refreshed_role.get('ci_ok')} ood_ok={refreshed_role.get('ood_ok')} "
                f"path={refreshed_role.get('path')} no_extra_pairs=true"
            ),
        )
        stage_done = _result(
            run_dir,
            "PASS",
            f"COMPLETED_{spec.role.upper()}",
            (
                f"canonical queue validator accepted {spec.role}"
                if refreshed_role.get("usable") is True
                else f"{spec.role} fixed measurement failed CI/OOD usability; role preserved and no pairs added"
            ),
            terminal=False,
            freeze=freeze,
            completed_roles=completed_roles,
            role=refreshed_role,
            queue_bundle_status=refreshed.get("status"),
            measurement_failures=measurement_failures,
        )
        persist_status(status_path, stage_done)

    final_bundle = validator(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
    if legacy_inconclusive_role3_continuation:
        legacy_final_ok = bool(
            final_bundle.get("status") == EXP003_CI_PRECISION_FAILED
            and final_bundle.get("measurement_status") == EXP003_CI_PRECISION_FAILED
            and final_bundle.get("ci_precision_failed_roles") == ["post_vs_native"]
            and final_bundle.get("legacy_inconclusive_roles") == ["pre_vs_native"]
            and final_bundle.get("legacy_preflight_contract") == legacy_preflight_contract
        )
        if not legacy_final_ok:
            failed = _result(
                run_dir,
                "FAIL",
                "LEGACY_INCONCLUSIVE_ONLY_FINAL_STATE_VIOLATION",
                (
                    "legacy role1 continuation may terminate only in the queue's exact "
                    "post-vs-native CI_PRECISION_FAILED / explicit-INCONCLUSIVE path; "
                    "REVIEW_READY/ADOPT and any contract drift are forbidden"
                ),
                terminal=True,
                freeze=freeze,
                completed_roles=completed_roles,
                recovered_roles=recovered_roles,
                measurement_failures=measurement_failures,
                legacy_preflight_contract=legacy_preflight_contract,
                queue_bundle=final_bundle,
            )
            persist_status(status_path, failed)
            return failed
    if final_bundle.get("status") == EXP003_CI_PRECISION_FAILED:
        ci_precision_event = append_ops_event(
            run_dir,
            freeze,
            "ci_precision_failed_ready",
            "EXP-003 fixed CI precision failure ready for explicit INCONCLUSIVE judgment",
            (
                "measurement_status=CI_PRECISION_FAILED no_retry=true no_extra_pairs=true "
                "next_action=explicit_INCONCLUSIVE_judgment_only"
            ),
        )
        inconclusive_ready = _result(
            run_dir,
            "INCONCLUSIVE_JUDGMENT_REQUIRED",
            "CI_PRECISION_FAILED_READY_FOR_EXPLICIT_INCONCLUSIVE_JUDGMENT",
            (
                "all three fixed causal roles are structurally preserved, but the registered fixed CI precision "
                "gate failed; only an explicit INCONCLUSIVE EXP-003 judgment may close this window"
            ),
            terminal=True,
            freeze=freeze,
            completed_roles=completed_roles,
            recovered_roles=recovered_roles,
            measurement_failures=measurement_failures,
            queue_bundle=final_bundle,
            ops_ci_precision_ready_event=ci_precision_event,
            next_action=(
                "run v5_exp003_judgment.py to write an explicit INCONCLUSIVE judgment; "
                "do not retry, add pairs, or substitute a later checkpoint"
            ),
        )
        persist_status(status_path, inconclusive_ready)
        return inconclusive_ready
    if final_bundle.get("status") != "REVIEW_READY":
        failed = _result(
            run_dir,
            "FAIL",
            "FINAL_BUNDLE_NOT_REVIEW_READY",
            f"canonical queue validator returned {final_bundle.get('status')}; REVIEW_READY required",
            terminal=True,
            freeze=freeze,
            completed_roles=completed_roles,
            recovered_roles=recovered_roles,
            measurement_failures=measurement_failures,
            queue_bundle=final_bundle,
        )
        persist_status(status_path, failed)
        return failed
    ready = _result(
        run_dir,
        "REVIEW_READY",
        "REVIEW_READY",
        "fixed three-role bundle is valid; separate EXP-003 judgment is still required",
        terminal=True,
        freeze=freeze,
        completed_roles=completed_roles,
        recovered_roles=recovered_roles,
        measurement_failures=measurement_failures,
        queue_bundle=final_bundle,
        next_action="run v5_exp003_judgment.py; do not infer ADOPT/ROLLBACK from measurement validity",
    )
    persist_status(status_path, ready)
    return ready


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch EXP-003's two frozen post-cutover mirror roles.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--status-json", default="")
    parser.add_argument("--lock-file", default="")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    status_path = Path(args.status_json).resolve() if args.status_json else run_dir / "v5_exp003_bundle_watch_status.json"
    lock_path = Path(args.lock_file).resolve() if args.lock_file else run_dir / "v5_exp003_bundle_watch.lock"
    try:
        with SingleInstanceLock(lock_path):
            while True:
                result = run_once(run_dir, python=args.python, status_path=status_path)
                print(
                    json.dumps(
                        {
                            "checked_at": result.get("checked_at"),
                            "overall": result.get("overall"),
                            "state": result.get("state"),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                if args.once or result.get("terminal"):
                    return 0 if result.get("overall") != "FAIL" else 2
                time.sleep(max(1.0, args.poll_seconds))
    except RuntimeError as exc:
        print(f"v5_exp003_bundle_watch: {exc}", file=sys.stderr, flush=True)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
