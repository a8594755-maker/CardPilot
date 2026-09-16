"""Real shared-memory worker smoke for the public opponent path."""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from multiprocessing import shared_memory
from pathlib import Path
import sys
import time
import traceback

import numpy as np

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.train_v5 import (
    ACTION_SIZE,
    CARD_SIZE,
    EXTRA_SIZE,
    HERO_MODEL_ID,
    IDLE,
    OBS_SIZE,
    PUBLIC_OPPONENT_COUNTER_STRIDE,
    READY,
    RESULT_SIZE,
    WAITING,
    public_opponent_accounting_snapshot,
    public_opponent_hand_seed,
    worker_process_v5,
)


def _worker_entry(*worker_args):
    try:
        worker_process_v5(*worker_args)
    except Exception:
        try:
            worker_args[6].send({"type": "worker_error", "traceback": traceback.format_exc()})
        finally:
            raise


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    obs_shm = shared_memory.SharedMemory(create=True, size=OBS_SIZE * 4)
    result_shm = shared_memory.SharedMemory(create=True, size=RESULT_SIZE * 4)
    status_shm = shared_memory.SharedMemory(create=True, size=4)
    assigned_shm = shared_memory.SharedMemory(create=True, size=4)
    request_shm = shared_memory.SharedMemory(create=True, size=4)
    parent, child = mp.Pipe()
    stop = mp.Event()
    epsilon = mp.Value("d", 0.0)
    environment_counters = mp.Array("q", 2, lock=True)
    public_counters = mp.Array("q", PUBLIC_OPPONENT_COUNTER_STRIDE, lock=True)
    obs = np.ndarray((OBS_SIZE,), np.float32, buffer=obs_shm.buf)
    result = np.ndarray((RESULT_SIZE,), np.float32, buffer=result_shm.buf)
    status = np.ndarray((1,), np.int32, buffer=status_shm.buf)
    assigned = np.ndarray((1,), np.int32, buffer=assigned_shm.buf)
    request = np.ndarray((1,), np.int32, buffer=request_shm.buf)
    obs[:] = 0
    result[:] = 0
    status[:] = IDLE
    assigned[:] = 0
    request[:] = HERO_MODEL_ID
    process = mp.Process(
        target=_worker_entry,
        args=(
            0, obs_shm.name, result_shm.name, status_shm.name,
            assigned_shm.name, request_shm.name, child, stop, epsilon,
            200.0, "v6", args.seed, False, False, False, 200,
            True, 0, False, 200, 2026082801, "model", False,
            environment_counters, 0.0, None, str(args.opponent_model),
            1.0, public_counters,
        ),
    )
    process.start()
    child.close()
    inference_requests = []
    transition_rows = 0
    worker_error = None
    deadline = time.time() + 120.0
    try:
        while time.time() < deadline:
            if status[0] == WAITING:
                inference_requests.append(int(request[0]))
                legal_mask = obs[CARD_SIZE + ACTION_SIZE + EXTRA_SIZE :]
                legal = np.flatnonzero(legal_mask > 0)
                if not len(legal):
                    raise RuntimeError("worker requested inference with no legal action")
                action = 1 if legal_mask[1] > 0 else int(legal[0])
                result[:] = (float(action), 0.0, 0.0)
                status[0] = READY
            try:
                while parent.poll():
                    message = parent.recv()
                    if isinstance(message, list):
                        transition_rows += len(message)
                    elif isinstance(message, dict) and message.get("type") == "worker_error":
                        worker_error = message["traceback"]
            except (EOFError, BrokenPipeError):
                if not process.is_alive():
                    break
                raise
            accounting = public_opponent_accounting_snapshot(public_counters)
            if accounting["session_hands"] >= args.hands:
                break
            time.sleep(0.0001)
        else:
            raise TimeoutError("public opponent worker smoke timed out")
    finally:
        stop.set()
        shutdown_deadline = time.time() + 20.0
        while process.is_alive() and time.time() < shutdown_deadline:
            try:
                while parent.poll():
                    message = parent.recv()
                    if isinstance(message, list):
                        transition_rows += len(message)
                    elif isinstance(message, dict) and message.get("type") == "worker_error":
                        worker_error = message["traceback"]
            except (EOFError, BrokenPipeError):
                pass
            process.join(timeout=0.05)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5.0)
        try:
            while parent.poll():
                message = parent.recv()
                if isinstance(message, list):
                    transition_rows += len(message)
                elif isinstance(message, dict) and message.get("type") == "worker_error":
                    worker_error = message["traceback"]
        except (EOFError, BrokenPipeError):
            pass
        parent.close()
        for segment in (obs_shm, result_shm, status_shm, assigned_shm, request_shm):
            segment.close()
            segment.unlink()
    accounting = public_opponent_accounting_snapshot(public_counters)
    with environment_counters.get_lock():
        environment_hands = int(environment_counters[0])
    gates = {
        "process_exit_zero": process.exitcode == 0,
        "target_hands_complete": accounting["session_hands"] >= args.hands,
        "environment_accounting_matches": environment_hands == accounting["session_hands"],
        "public_decisions_nonzero": accounting["session_decisions"] > 0,
        "opponent_inference_fully_bypassed": (
            accounting["inference_bypasses"] == accounting["session_decisions"]
        ),
        "only_hero_inference_requested": bool(inference_requests) and set(inference_requests) == {HERO_MODEL_ID},
        "hero_transitions_emitted": transition_rows > 0,
        "seed_replay_identity": (
            public_opponent_hand_seed(args.seed, 17)
            == public_opponent_hand_seed(args.seed, 17)
            != public_opponent_hand_seed(args.seed, 18)
        ),
    }
    summary = {
        "schema_version": 1,
        "config": {"target_hands": args.hands, "seed": args.seed},
        "accounting": {
            "environment_training_hands": 0,
            "evaluation_hands": environment_hands,
            "hero_transition_rows": transition_rows,
            "hero_inference_requests": len(inference_requests),
            "public_opponent": accounting,
        },
        "gates": gates,
        "worker_error": worker_error,
    }
    summary["admit_matched_hero_smoke"] = all(gates.values())
    summary["decision"] = (
        "ADMIT_MATCHED_PUBLIC_OPPONENT_HERO_SMOKE"
        if summary["admit_matched_hero_smoke"]
        else "REJECT_PUBLIC_OPPONENT_WORKER_INTEGRATION"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--opponent-model", type=Path, required=True)
    parser.add_argument("--hands", type=int, default=256)
    parser.add_argument("--seed", type=int, default=60916)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
