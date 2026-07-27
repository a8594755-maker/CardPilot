#!/usr/bin/env python3
"""Hold the RR032-C1 Windows session mutex until an explicit release signal exists."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
import time


ERROR_ALREADY_EXISTS = 183
WAIT_TIMEOUT = 258


def write_exclusive(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--mutex-name", required=True)
    parser.add_argument("--lock-path", required=True)
    parser.add_argument("--metadata-path", required=True)
    parser.add_argument("--release-path", required=True)
    return parser.parse_args()


def main() -> int:
    if os.name != "nt":
        raise RuntimeError("windows_required")
    args = parse_args()
    lock_path = Path(args.lock_path).resolve(strict=False)
    metadata_path = Path(args.metadata_path).resolve(strict=False)
    release_path = Path(args.release_path).resolve(strict=False)
    if lock_path.exists() or metadata_path.exists() or release_path.exists():
        raise RuntimeError("fresh_lock_namespace_required")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    mutex = kernel32.CreateMutexW(None, True, args.mutex_name)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(mutex)
        raise RuntimeError("mutex_already_exists")

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("x", encoding="ascii", newline="\n") as handle:
            handle.write(f"nonce={args.nonce}\nmutex={args.mutex_name}\n")
            handle.flush()
            os.fsync(handle.fileno())
        write_exclusive(
            metadata_path,
            {
                "schema_version": "v5.rr032.c1.session_lock_metadata.v1",
                "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "holder_pid": os.getpid(),
                "python_executable": str(Path(sys.executable).resolve()),
                "nonce": args.nonce,
                "mutex_name": args.mutex_name,
                "lock_path": str(lock_path),
                "metadata_path": str(metadata_path),
                "release_path": str(release_path),
                "exclusive_create": True,
                "mutex_initial_owner": True,
                "release_semantics": "CREATE_RELEASE_PATH_ONLY_AFTER_TERMINAL_RESULT_AUDIT_AND_CONTROL_REFRESH",
            },
        )
        while not release_path.exists():
            time.sleep(1.0)
        return 0
    finally:
        kernel32.ReleaseMutex(mutex)
        kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
