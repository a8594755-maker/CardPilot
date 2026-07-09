#!/usr/bin/env python3
"""Background Slumbot benchmark queue for V5.5 experiments."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from v55_supervisor import (
    BENCH_DONE_PATH,
    BENCH_QUEUE_PATH,
    CONFIRM_HANDS_PER_SESSION,
    CONFIRM_MIN_LCB_BB100,
    CONFIRM_SESSIONS,
    FULL_HANDS_PER_SESSION,
    FULL_SESSIONS,
    LAB,
    ROOT,
    SLUMBOT_DOMINATION_TARGET_BB100,
    benchmark,
    experiments,
    load_state,
    local_v4_baseline,
    promote,
    read_checkpoint_hands,
    save_state,
)


LOCK_PATH = LAB / "bench_queue_worker.lock"
MONITOR_LOCK_PATH = LAB / "bench_result_monitor.lock"
LOG_PATH = LAB / "bench_queue_worker.log"
PROCESSED_PATH = LAB / "bench_processed.jsonl"


def log(message: str) -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def pid_alive(pid: int) -> bool:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def acquire_lock(path: Path = LOCK_PATH) -> int | None:
    LAB.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            old_pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            old_pid = 0
        if old_pid and pid_alive(old_pid):
            return None
        try:
            path.unlink()
        except OSError:
            return None
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode("ascii"))
    return fd


def release_lock(fd: int, path: Path = LOCK_PATH) -> None:
    os.close(fd)
    try:
        path.unlink()
    except OSError:
        pass


def tag_set(path: Path) -> set[str]:
    return {str(row.get("tag")) for row in read_jsonl(path) if row.get("tag")}


def enqueue_task(task: dict) -> bool:
    tag = str(task.get("tag", ""))
    if not tag:
        return False
    if tag in tag_set(BENCH_DONE_PATH) or tag in tag_set(BENCH_QUEUE_PATH):
        return False
    append_jsonl(BENCH_QUEUE_PATH, task)
    return True


def enqueue(args: argparse.Namespace) -> int:
    task = {
        "tag": args.tag,
        "model": args.model,
        "sessions": args.sessions,
        "hands_per_session": args.hands_per_session,
        "sample": args.sample,
        "temperature": args.temperature,
        "kind": args.kind,
    }
    if not enqueue_task(task):
        log(f"ENQUEUE_SKIP tag={args.tag}")
        return 0
    log(f"ENQUEUE tag={args.tag} model={args.model}")
    return 0


def task_priority(task: dict) -> int:
    kind = str(task.get("kind", "")).lower()
    return {"confirm": 0, "full": 1, "smoke": 2}.get(kind, 3)


def infer_kind(tag: str, task: dict | None = None) -> str:
    if task and task.get("kind"):
        return str(task["kind"])
    for kind in ("confirm", "full", "smoke"):
        if tag.endswith(f"_{kind}"):
            return kind
    return "smoke"


def derived_tag(tag: str, from_kind: str, to_kind: str) -> str:
    suffix = f"_{from_kind}"
    if tag.endswith(suffix):
        return tag[: -len(suffix)] + f"_{to_kind}"
    return f"{tag}_{to_kind}"


def experiment_for_task(task: dict):
    explicit = str(task.get("experiment", ""))
    tag = str(task.get("tag", ""))
    model = str(task.get("model", ""))
    model_path = Path(model) if model else Path()
    for exp in experiments():
        if explicit == exp.name:
            return exp
        if tag.startswith(f"{exp.name}_"):
            return exp
        if model_path.name.startswith(f"{exp.name}_") or model_path.name == f"{exp.name}.pt":
            return exp
        if exp.name in model_path.parts:
            return exp
    return None


def infer_candidate_hands(task: dict) -> int:
    raw = task.get("candidate_hands")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    tag = str(task.get("tag", ""))
    match = re.search(r"_h(\d+)_i\d+", tag)
    if match:
        return int(match.group(1))
    model = Path(str(task.get("model", "")))
    return read_checkpoint_hands(model) if model.exists() else 0


def infer_round(task: dict) -> int | None:
    raw = task.get("round")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    match = re.search(r"_r(\d+)_h\d+_i\d+_c\d+", str(task.get("tag", "")))
    return int(match.group(1)) if match else None


def infer_candidate_idx(task: dict) -> int | None:
    raw = task.get("candidate_idx")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    match = re.search(r"_c(\d+)(?:_|$)", str(task.get("tag", "")))
    return int(match.group(1)) if match else None


def update_best(state: dict, model: Path, result: dict, label: str) -> None:
    if int(result.get("hands", 0)) <= 0:
        return
    bb100 = float(result.get("bb100", -9999.0))
    if bb100 <= float(state.get("best_bb100", -9999.0)):
        return
    state["best_bb100"] = bb100
    state["best_model"] = str(model)
    shutil.copy2(model, LAB / f"alpha_holdem_v55_best_{label}.pt")
    log(f"BEST_{label.upper()} bb100={bb100:+.2f} model={model}")


def process_completed_result(task: dict, done_row: dict) -> None:
    tag = str(done_row.get("tag") or task.get("tag") or "")
    if not tag:
        return
    if "error" in done_row:
        log(f"RESULT_SKIP tag={tag} error={done_row['error']}")
        return
    result = done_row.get("result")
    if not isinstance(result, dict):
        log(f"RESULT_SKIP tag={tag} missing result")
        return

    model = Path(str(done_row.get("model") or task.get("model") or ""))
    kind = infer_kind(tag, task)
    exp = experiment_for_task(task)
    exp_name = exp.name if exp else str(task.get("experiment", "unknown"))
    candidate_hands = infer_candidate_hands(task)
    round_idx = infer_round(task)
    candidate_idx = infer_candidate_idx(task)

    state = load_state()
    baseline = float(state.get("baseline_bb100", local_v4_baseline()))
    promote_threshold = float(
        state.get("promote_threshold_bb100", max(SLUMBOT_DOMINATION_TARGET_BB100, baseline))
    )
    require_positive_lcb = bool(state.get("require_positive_lcb", True))
    state.setdefault("history", []).append(
        {
            "async": True,
            "tag": tag,
            "kind": kind,
            "round": round_idx,
            "experiment": exp_name,
            "hands": candidate_hands,
            "model": str(model),
            kind: result,
            "config": asdict(exp) if exp else None,
        }
    )

    bb100 = float(result.get("bb100", -9999.0))
    if kind == "smoke":
        update_best(state, model, result, "smoke")
        # Smoke samples are intentionally small and noisy. Promote any candidate
        # close enough to the V4 baseline so the 20k run, not a 2k roll, decides.
        full_bench_floor = baseline - 25.0
        if bb100 >= full_bench_floor or bb100 > 0.0:
            full_tag = derived_tag(tag, "smoke", "full")
            full_task = {
                "tag": full_tag,
                "model": str(model),
                "sessions": FULL_SESSIONS,
                "hands_per_session": FULL_HANDS_PER_SESSION,
                "sample": bool(task.get("sample", False)),
                "temperature": float(task.get("temperature", 1.0)),
                "kind": "full",
                "experiment": exp_name,
                "round": round_idx,
                "candidate_idx": candidate_idx,
                "candidate_hands": candidate_hands,
                "parent_tag": tag,
            }
            if enqueue_task(full_task):
                log(f"ASYNC_FULL_ENQUEUE tag={full_tag} bb100={bb100:+.2f} model={model}")
            else:
                log(f"ASYNC_FULL_SKIP tag={full_tag}")

    elif kind == "full":
        update_best(state, model, result, "full")
        ci = float(result.get("ci_bb100") or 0.0)
        lcb = bb100 - ci
        target_hit = int(result.get("hands", 0)) > 0 and bb100 >= promote_threshold
        confidence_hit = (not require_positive_lcb) or lcb > 0.0
        log(
            f"ASYNC_PROMOTE_CHECK tag={tag} bb100={bb100:+.2f} lcb={lcb:+.2f} "
            f"target_hit={target_hit} confidence_hit={confidence_hit} model={model}"
        )
        if target_hit and confidence_hit:
            confirm_tag = derived_tag(tag, "full", "confirm")
            confirm_task = {
                "tag": confirm_tag,
                "model": str(model),
                "sessions": CONFIRM_SESSIONS,
                "hands_per_session": CONFIRM_HANDS_PER_SESSION,
                "sample": bool(task.get("sample", False)),
                "temperature": float(task.get("temperature", 1.0)),
                "kind": "confirm",
                "experiment": exp_name,
                "round": round_idx,
                "candidate_idx": candidate_idx,
                "candidate_hands": candidate_hands,
                "parent_tag": tag,
            }
            if enqueue_task(confirm_task):
                log(f"ASYNC_CONFIRM_ENQUEUE tag={confirm_tag} model={model}")
            else:
                log(f"ASYNC_CONFIRM_SKIP tag={confirm_tag}")

    elif kind == "confirm":
        ci = float(result.get("ci_bb100") or 0.0)
        lcb = bb100 - ci
        target_hit = int(result.get("hands", 0)) > 0 and bb100 >= promote_threshold
        confidence_hit = lcb >= CONFIRM_MIN_LCB_BB100
        log(
            f"ASYNC_CONFIRM_CHECK tag={tag} bb100={bb100:+.2f} lcb={lcb:+.2f} "
            f"target_hit={target_hit} confidence_hit={confidence_hit} model={model}"
        )
        if exp and target_hit and confidence_hit:
            promote(exp, model, result, baseline)
            state["promoted"] = True

    save_state(state)


def process_done_rows_once() -> int:
    done_rows = read_jsonl(BENCH_DONE_PATH)
    tasks = {str(row.get("tag")): row for row in read_jsonl(BENCH_QUEUE_PATH)}
    processed = tag_set(PROCESSED_PATH)
    count = 0
    for row in done_rows:
        tag = str(row.get("tag", ""))
        if not tag or tag in processed:
            continue
        task = tasks.get(tag, {"tag": tag, "model": row.get("model"), "kind": infer_kind(tag)})
        process_completed_result(task, row)
        append_jsonl(PROCESSED_PATH, {"tag": tag, "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")})
        processed.add(tag)
        count += 1
    return count


def watch_results(args: argparse.Namespace) -> int:
    fd = acquire_lock(MONITOR_LOCK_PATH)
    if fd is None:
        log("MONITOR_EXIT another monitor is active")
        return 0
    try:
        idle_since = time.time()
        while True:
            count = process_done_rows_once()
            if count:
                log(f"MONITOR_PROCESSED count={count}")
                idle_since = time.time()
            elif args.idle_exit_seconds > 0 and time.time() - idle_since >= args.idle_exit_seconds:
                log("MONITOR_EXIT idle")
                return 0
            time.sleep(args.poll_seconds)
    finally:
        release_lock(fd, MONITOR_LOCK_PATH)


def worker(args: argparse.Namespace) -> int:
    fd = acquire_lock()
    if fd is None:
        log("WORKER_EXIT another worker is active")
        return 0
    try:
        idle_since = time.time()
        while True:
            done_tags = {str(row.get("tag")) for row in read_jsonl(BENCH_DONE_PATH)}
            queue = read_jsonl(BENCH_QUEUE_PATH)
            pending = [
                (idx, row)
                for idx, row in enumerate(queue)
                if str(row.get("tag")) not in done_tags
            ]
            if not pending:
                if time.time() - idle_since >= args.idle_exit_seconds:
                    log("WORKER_EXIT idle")
                    return 0
                time.sleep(args.poll_seconds)
                continue

            idle_since = time.time()
            task = min(pending, key=lambda item: (task_priority(item[1]), item[0]))[1]
            tag = str(task["tag"])
            model = Path(str(task["model"]))
            log(f"BENCH_START tag={tag} model={model}")
            try:
                result = benchmark(
                    model,
                    tag,
                    int(task.get("sessions", 4)),
                    int(task.get("hands_per_session", 500)),
                    sample=bool(task.get("sample", False)),
                    temperature=float(task.get("temperature", 1.0)),
                )
                done_row = {
                    "tag": tag,
                    "model": str(model),
                    "result": result,
                    "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                append_jsonl(BENCH_DONE_PATH, done_row)
                log(f"BENCH_DONE tag={tag} bb100={float(result.get('bb100', 0.0)):+.2f}")
                process_done_rows_once()
            except Exception as exc:
                append_jsonl(
                    BENCH_DONE_PATH,
                    {
                        "tag": tag,
                        "model": str(model),
                        "error": repr(exc),
                        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    },
                )
                log(f"BENCH_ERROR tag={tag} error={exc!r}")
                process_done_rows_once()
    finally:
        release_lock(fd)


def main() -> int:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    enqueue_parser = sub.add_parser("enqueue")
    enqueue_parser.add_argument("--model", required=True)
    enqueue_parser.add_argument("--tag", required=True)
    enqueue_parser.add_argument("--sessions", type=int, default=4)
    enqueue_parser.add_argument("--hands-per-session", type=int, default=500)
    enqueue_parser.add_argument("--sample", action="store_true")
    enqueue_parser.add_argument("--temperature", type=float, default=1.0)
    enqueue_parser.add_argument("--kind", default="smoke")
    enqueue_parser.set_defaults(func=enqueue)

    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument("--poll-seconds", type=int, default=30)
    worker_parser.add_argument("--idle-exit-seconds", type=int, default=300)
    worker_parser.set_defaults(func=worker)

    monitor_parser = sub.add_parser("watch-results")
    monitor_parser.add_argument("--poll-seconds", type=int, default=30)
    monitor_parser.add_argument("--idle-exit-seconds", type=int, default=0)
    monitor_parser.set_defaults(func=watch_results)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
