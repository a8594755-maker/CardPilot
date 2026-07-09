#!/usr/bin/env python3
"""
Archive and bench overwritten train_mp3 checkpoints while training continues.

train_mp3 writes one rolling --out checkpoint. That is fast, but it loses
non-monotonic peaks inside a segment. This watcher copies each new saved
checkpoint by total_hands/iteration and optionally enqueues a Slumbot smoke.
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "models" / "v55_lab"
STATE_PATH = LAB / "mp3_checkpoint_watcher_state.json"
LOG_PATH = LAB / "mp3_checkpoint_watcher.log"


def log(msg: str) -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"seen": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def expand_models(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        raw = str((ROOT / pattern) if not Path(pattern).is_absolute() else Path(pattern))
        matches = glob.glob(raw)
        if matches:
            paths.extend(Path(m) for m in matches)
        else:
            paths.append(Path(raw))
    return sorted({p.resolve() for p in paths if p.exists()})


def read_checkpoint_meta(path: Path) -> tuple[int, int] | None:
    try:
        ckpt = torch.load(path, map_location="cpu")
    except Exception as exc:
        log(f"READ_SKIP path={path} error={exc!r}")
        return None
    hands = int(ckpt.get("total_hands", 0) or 0)
    iteration = int(ckpt.get("iteration", 0) or 0)
    if hands <= 0:
        return None
    return hands, iteration


def enqueue_smoke(model: Path, exp_name: str, hands: int, iteration: int, args: argparse.Namespace) -> bool:
    sys.path.insert(0, str(ROOT))
    from scripts.alpha_holdem.v55_bench_queue import enqueue_task
    from scripts.alpha_holdem.v55_supervisor import ensure_bench_worker

    tag = f"{exp_name}_watch_h{hands}_i{iteration}_c1_smoke"
    task = {
        "tag": tag,
        "model": str(model),
        "sessions": args.sessions,
        "hands_per_session": args.hands_per_session,
        "sample": args.sample,
        "temperature": args.temperature,
        "kind": "smoke",
        "experiment": exp_name,
        "candidate_hands": hands,
    }
    queued = enqueue_task(task)
    if queued:
        ensure_bench_worker()
        log(f"ENQUEUE_SMOKE tag={tag} model={model}")
    else:
        log(f"ENQUEUE_SKIP tag={tag}")
    return queued


def archive_once(path: Path, state: dict, args: argparse.Namespace) -> bool:
    meta = read_checkpoint_meta(path)
    if meta is None:
        return False
    hands, iteration = meta
    exp_name = path.stem
    seen_key = str(path)
    seen_hands = int(state.setdefault("seen", {}).get(seen_key, 0) or 0)
    if hands <= seen_hands:
        return False

    archive_dir = LAB / "archives" / exp_name
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / f"{exp_name}_iter{iteration}_hands{hands}_watch.pt"
    if not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(path, tmp)
        tmp.replace(dest)
        log(f"ARCHIVE path={dest} hands={hands:,} iteration={iteration}")
    else:
        log(f"ARCHIVE_EXISTS path={dest}")

    state["seen"][seen_key] = hands
    save_state(state)
    if args.enqueue_smoke:
        enqueue_smoke(dest, exp_name, hands, iteration, args)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        default=["models/v55_lab/v4mp3_*.pt"],
        help="Checkpoint files or glob patterns to watch.",
    )
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--idle-exit-seconds", type=int, default=0)
    parser.add_argument("--enqueue-smoke", action="store_true")
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--hands-per-session", type=int, default=500)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--temperature", type=float, default=1.0)
    args = parser.parse_args()

    state = load_state()
    idle_started: float | None = None
    log(
        "START models="
        + ",".join(args.models)
        + f" enqueue_smoke={args.enqueue_smoke} poll={args.poll_seconds}s"
    )
    while True:
        did_work = False
        for path in expand_models(args.models):
            did_work = archive_once(path, state, args) or did_work
        if did_work:
            idle_started = None
        else:
            if idle_started is None:
                idle_started = time.time()
            if args.idle_exit_seconds and time.time() - idle_started >= args.idle_exit_seconds:
                log("EXIT idle")
                return 0
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
