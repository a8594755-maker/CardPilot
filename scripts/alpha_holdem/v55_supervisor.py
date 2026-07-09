#!/usr/bin/env python3
"""
Long-running V5.5 experiment supervisor.

Goal: search for a V5.5 configuration that beats the local V4 Slumbot baseline,
without relying on paper replication assumptions. The supervisor runs one GPU
training branch at a time, then benchmarks the produced checkpoint on CPU.

Outputs live under models/v55_lab/ so the existing alpha_holdem_v55.pt line is
left intact.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
LAB = MODELS / "v55_lab"
STATE_PATH = LAB / "supervisor_state.json"
LOG_PATH = LAB / "supervisor.log"
BENCH_QUEUE_PATH = LAB / "bench_queue.jsonl"
BENCH_DONE_PATH = LAB / "bench_done.jsonl"
BENCH_WORKER_OUT = LAB / "bench_queue_worker_stdout.log"
BENCH_WORKER_ERR = LAB / "bench_queue_worker_stderr.log"

BB_CHIPS = 100.0
DEFAULT_V4_BASELINE_BB100 = -49.73
SLUMBOT_DOMINATION_TARGET_BB100 = 30.0
SMOKE_SESSIONS = 4
SMOKE_HANDS_PER_SESSION = 500
FULL_SESSIONS = 12
FULL_HANDS_PER_SESSION = 1700
CONFIRM_SESSIONS = 12
CONFIRM_HANDS_PER_SESSION = 5000
CONFIRM_MIN_LCB_BB100 = 10.0
SEGMENT_HANDS = 1_000_000


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    LAB.mkdir(parents=True, exist_ok=True)
    line = f"[{now()}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd: list[str], *, stdout: Path | None = None, stderr: Path | None = None) -> int:
    log("RUN " + " ".join(str(x) for x in cmd))
    out_f = stdout.open("ab") if stdout else None
    err_f = stderr.open("ab") if stderr else None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=out_f if out_f else None,
            stderr=err_f if err_f else None,
            text=False,
        )
        return proc.wait()
    finally:
        if out_f:
            out_f.close()
        if err_f:
            err_f.close()


def read_checkpoint_hands(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        import torch

        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        return int(ckpt.get("total_hands", 0))
    except Exception as exc:
        log(f"WARN failed to read checkpoint hands from {path}: {exc}")
        return 0


def read_checkpoint_iteration(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        import torch

        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        return int(ckpt.get("iteration", 0))
    except Exception as exc:
        log(f"WARN failed to read checkpoint iteration from {path}: {exc}")
        return 0


def parse_slumbot_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    m_total = re.search(r"Total:\s+([+-]?\d+) chips", text)
    m_hands = re.search(r"Slumbot \((\d+,?\d*) hands\)", text)
    m_avg = re.search(r"Avg:\s+([+-]?\d+\.\d+) BB/hand", text)
    if not (m_total and m_hands and m_avg):
        return None
    return {
        "log": str(path),
        "hands": int(m_hands.group(1).replace(",", "")),
        "total_chips": int(m_total.group(1)),
        "avg_bb": float(m_avg.group(1)),
    }


def combine_logs(logs: list[Path]) -> dict:
    parsed = [p for p in (parse_slumbot_log(path) for path in logs) if p]
    total_hands = sum(int(p["hands"]) for p in parsed)
    total_chips = sum(int(p["total_chips"]) for p in parsed)
    avg_bb = (total_chips / total_hands / BB_CHIPS) if total_hands else 0.0
    bb100 = avg_bb * 100.0
    ci_bb100 = None
    if total_hands >= 1000:
        # Same rough scale used by combine_slumbot_logs.py.
        ci_mbb = 700.0 * math.sqrt(2000.0 / total_hands)
        ci_bb100 = ci_mbb / 10.0
    return {
        "sessions": len(parsed),
        "hands": total_hands,
        "total_chips": total_chips,
        "avg_bb": avg_bb,
        "bb100": bb100,
        "ci_bb100": ci_bb100,
        "logs": [p["log"] for p in parsed],
    }


def local_v4_baseline() -> float:
    logs = sorted(MODELS.glob("slumbot_v4_987M_20k_part*.log"))
    if not logs:
        return DEFAULT_V4_BASELINE_BB100
    result = combine_logs(logs)
    if result["hands"] == 0:
        return DEFAULT_V4_BASELINE_BB100
    return float(result["bb100"])


def write_summary(tag: str, result: dict) -> Path:
    path = LAB / f"bench_{tag}_summary.txt"
    with path.open("w", encoding="utf-8") as f:
        f.write(f"tag={tag}\n")
        f.write(f"sessions={result['sessions']}\n")
        f.write(f"hands={result['hands']}\n")
        f.write(f"avg_bb={result['avg_bb']:+.4f}\n")
        f.write(f"bb100={result['bb100']:+.2f}\n")
        if result["ci_bb100"] is not None:
            f.write(f"ci_bb100_rough=+/-{result['ci_bb100']:.1f}\n")
        f.write(f"total_chips={result['total_chips']:+d}\n")
        for log_path in result["logs"]:
            f.write(f"log={log_path}\n")
    return path


def benchmark(
    model: Path,
    tag: str,
    sessions: int,
    hands_per_session: int,
    *,
    sample: bool = False,
    temperature: float = 1.0,
    policy_mode: str = "greedy",
    guarded_allin_max_spr: float = 2.0,
    guarded_allin_min_prob: float = 0.65,
    callguard_min_prob: float = 0.20,
    callguard_ratio: float = 0.65,
    callguard_include_open: bool = False,
) -> dict:
    bench_dir = LAB / "bench"
    bench_dir.mkdir(parents=True, exist_ok=True)
    slumbot_data_dir = LAB / "slumbot_data"
    slumbot_data_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[subprocess.Popen, Path]] = []
    effective_policy_mode = "sample" if sample else policy_mode
    mode = f"{effective_policy_mode}/temp={temperature:g}"
    log(
        f"BENCH tag={tag} model={model} sessions={sessions} "
        f"hands={hands_per_session} mode={mode}"
    )

    for idx in range(1, sessions + 1):
        out = bench_dir / f"{tag}_part{idx}.log"
        err = bench_dir / f"{tag}_part{idx}_err.log"
        dump = slumbot_data_dir / f"{tag}_part{idx}.jsonl"
        cmd = [
            sys.executable,
            "-X",
            "utf8",
            "-u",
            "scripts/alpha_holdem/play_slumbot.py",
            "--model",
            str(model),
            "--hands",
            str(hands_per_session),
            "--device",
            "cpu",
            "--dump-slumbot",
            str(dump),
            "--policy-mode",
            effective_policy_mode,
            "--temperature",
            str(temperature),
            "--guarded-allin-max-spr",
            str(guarded_allin_max_spr),
            "--guarded-allin-min-prob",
            str(guarded_allin_min_prob),
            "--callguard-min-prob",
            str(callguard_min_prob),
            "--callguard-ratio",
            str(callguard_ratio),
        ]
        if callguard_include_open:
            cmd.append("--callguard-include-open")
        out_f = out.open("wb")
        err_f = err.open("wb")
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=out_f, stderr=err_f)
        proc._out_f = out_f  # type: ignore[attr-defined]
        proc._err_f = err_f  # type: ignore[attr-defined]
        jobs.append((proc, out))

    for proc, _ in jobs:
        proc.wait()
        proc._out_f.close()  # type: ignore[attr-defined]
        proc._err_f.close()  # type: ignore[attr-defined]

    logs = [path for _, path in jobs]
    result = combine_logs(logs)
    summary = write_summary(tag, result)
    log(
        f"BENCH_DONE tag={tag} hands={result['hands']} "
        f"bb100={result['bb100']:+.2f} summary={summary}"
    )
    return result


def train_segment(exp: "Experiment", resume: Path, target_hands: int) -> int:
    stdout = LAB / f"{exp.name}_train_stdout.log"
    stderr = LAB / f"{exp.name}_train_stderr.log"
    if exp.trainer == "mp3":
        cmd = [
            sys.executable,
            "-X",
            "utf8",
            "-u",
            "scripts/alpha_holdem/train_mp3.py",
            "--resume",
            str(resume),
            "--out",
            str(exp.out),
            "--device",
            "cuda",
            "--workers",
            str(exp.workers),
            "--hands-per-iter",
            str(exp.hands_per_iter),
            "--total-hands",
            str(target_hands),
            "--starting-stack",
            "200.0",
            "--lr",
            str(exp.lr),
            "--epsilon",
            str(exp.epsilon),
            "--gamma",
            "0.999",
            "--entropy-coef",
            str(exp.entropy_coef),
            "--k-best",
            "5",
            "--snapshot-every",
            str(exp.snapshot_every),
            "--save-interval",
            str(exp.save_interval),
            "--self-play-fraction",
            str(exp.self_play_fraction),
            "--opponent-temperature",
            str(exp.opponent_temperature),
        ]
        if exp.slumbot_mimic_path:
            cmd.extend(["--slumbot-mimic-path", str(exp.slumbot_mimic_path)])
        return run(cmd, stdout=stdout, stderr=stderr)

    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-u",
        "scripts/alpha_holdem/train_v55.py",
        "--resume",
        str(resume),
        "--out",
        str(exp.out),
        "--device",
        "cuda",
        "--workers",
        str(exp.workers),
        "--hands-per-iter",
        str(exp.hands_per_iter),
        "--total-hands",
        str(target_hands),
        "--starting-stack",
        "200.0",
        "--lr",
        str(exp.lr),
        "--epsilon",
        str(exp.epsilon),
        "--epsilon-min",
        str(exp.epsilon_min),
        "--gamma",
        "0.999",
        "--entropy-coef",
        str(exp.entropy_coef),
        "--entropy-floor",
        str(exp.entropy_floor),
        "--save-interval",
        str(exp.save_interval),
        "--archive-dir",
        str(exp.archive_dir),
        "--archive-interval",
        str(exp.archive_interval),
        "--archive-max",
        str(exp.archive_max),
        "--snapshot-every",
        str(exp.snapshot_every),
        "--pool-update-mode",
        exp.pool_update_mode,
        "--opponent-mode",
        exp.opponent_mode,
        "--env-version",
        exp.env_version,
        "--self-play-fraction",
        str(exp.self_play_fraction),
        "--ema-fraction",
        str(exp.ema_fraction),
        "--ema-alpha",
        str(exp.ema_alpha),
        "--ema-only-fraction",
        str(exp.ema_only_fraction),
        "--mmd-lambda",
        str(exp.mmd_lambda),
        "--mmd-anchor",
        exp.mmd_anchor,
        "--min-runtime-entropy",
        str(exp.min_runtime_entropy),
        "--max-runtime-rew100",
        str(exp.max_runtime_rew100),
        "--max-runtime-positive-rew100",
        str(exp.max_runtime_positive_rew100),
        "--min-safety-stop-iters",
        str(exp.min_safety_stop_iters),
    ]
    if exp.collect_self_play_both:
        cmd.append("--collect-self-play-both")
    try:
        if (not exp.reset_optimizer) or resume.resolve() == exp.out.resolve():
            cmd.append("--no-reset-optimizer")
    except OSError:
        pass
    if exp.light_archive:
        cmd.append("--light-archive")
    return run(cmd, stdout=stdout, stderr=stderr)


@dataclass
class Experiment:
    name: str
    opponent_mode: str
    lr: float
    entropy_coef: float
    entropy_floor: float
    trainer: str = "v55"
    mmd_lambda: float = 0.0
    mmd_anchor: str = "ema"
    env_version: str = "v55"
    epsilon: float = 0.0
    epsilon_min: float = 0.0
    eval_sample: bool = False
    eval_temperature: float = 1.0
    ema_alpha: float = 0.999
    ema_only_fraction: float = 0.5
    self_play_fraction: float = 0.2
    ema_fraction: float = 0.3
    pool_update_mode: str = "latest"
    collect_self_play_both: bool = False
    reset_optimizer: bool = True
    workers: int = 28
    hands_per_iter: int = 16384
    save_interval: int = 50
    snapshot_every: int = 100
    archive_interval: int = 25
    archive_max: int = 16
    min_runtime_entropy: float = 0.05
    max_runtime_rew100: float = 12.0
    max_runtime_positive_rew100: float = 6.0
    min_safety_stop_iters: int = 10
    segment_hands: int | None = None
    target_total_hands: int | None = None
    repeat_until_target: bool = False
    light_archive: bool = False
    max_eval_candidates: int | None = None
    slumbot_mimic_path: str | None = None
    opponent_temperature: float = 1.0

    @property
    def out(self) -> Path:
        return LAB / f"{self.name}.pt"

    @property
    def archive_dir(self) -> Path:
        return LAB / "archives" / self.name


def experiments() -> list[Experiment]:
    return [
        Experiment(
            name="pool_fast_entropy05",
            opponent_mode="pool",
            lr=5e-5,
            entropy_coef=0.02,
            entropy_floor=0.5,
            mmd_lambda=0.02,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=2.5,
        ),
        Experiment(
            name="hybrid_mmd005_entropy05",
            opponent_mode="hybrid",
            lr=5e-5,
            entropy_coef=0.02,
            entropy_floor=0.5,
            mmd_lambda=0.05,
            ema_fraction=0.3,
            self_play_fraction=0.2,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=2.5,
        ),
        Experiment(
            name="hybrid_mmd003_entropy06_rew20",
            opponent_mode="hybrid",
            lr=4e-5,
            entropy_coef=0.025,
            entropy_floor=0.6,
            mmd_lambda=0.03,
            ema_fraction=0.25,
            self_play_fraction=0.15,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=2.0,
        ),
        Experiment(
            name="pool_mmd003_entropy07_rew20",
            opponent_mode="pool",
            lr=4e-5,
            entropy_coef=0.03,
            entropy_floor=0.7,
            mmd_lambda=0.03,
            self_play_fraction=0.15,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=2.0,
        ),
        Experiment(
            name="hybrid_fixed_mmd010_entropy08_rew08",
            opponent_mode="hybrid",
            lr=2e-5,
            entropy_coef=0.035,
            entropy_floor=0.8,
            mmd_lambda=0.10,
            mmd_anchor="fixed",
            ema_fraction=0.20,
            self_play_fraction=0.10,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=0.8,
        ),
        Experiment(
            name="pool_fixed_mmd010_entropy08_rew08",
            opponent_mode="pool",
            lr=2e-5,
            entropy_coef=0.035,
            entropy_floor=0.8,
            mmd_lambda=0.10,
            mmd_anchor="fixed",
            self_play_fraction=0.10,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=0.8,
        ),
        Experiment(
            name="legacy_micro_pool_fixed_mmd020_lr5e6",
            opponent_mode="pool",
            env_version="v4",
            lr=5e-6,
            entropy_coef=0.018,
            entropy_floor=0.45,
            mmd_lambda=0.20,
            mmd_anchor="fixed",
            self_play_fraction=0.10,
            save_interval=1,
            archive_interval=1,
            archive_max=8,
            snapshot_every=25,
            max_runtime_positive_rew100=0.25,
        ),
        Experiment(
            name="v4mp3_continue_fast_lr105e6_eps05",
            trainer="mp3",
            opponent_mode="pool",
            env_version="v4",
            lr=1.05e-4,
            entropy_coef=0.01,
            entropy_floor=0.3,
            epsilon=0.05,
            epsilon_min=0.05,
            self_play_fraction=0.20,
            pool_update_mode="frozen",
            reset_optimizer=False,
            segment_hands=5_000_000,
            target_total_hands=1_004_222_193,
            save_interval=100,
            archive_interval=0,
            archive_max=0,
            max_eval_candidates=1,
            snapshot_every=200,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="v4mp3_w36_fast_lr105e6_eps05",
            trainer="mp3",
            opponent_mode="pool",
            env_version="v4",
            lr=1.05e-4,
            entropy_coef=0.01,
            entropy_floor=0.3,
            epsilon=0.05,
            epsilon_min=0.05,
            self_play_fraction=0.20,
            pool_update_mode="frozen",
            reset_optimizer=False,
            workers=36,
            segment_hands=5_000_000,
            target_total_hands=1_004_222_193,
            save_interval=100,
            archive_interval=0,
            archive_max=0,
            max_eval_candidates=1,
            snapshot_every=200,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="v4mp3_w40_fast_lr105e6_eps05",
            trainer="mp3",
            opponent_mode="pool",
            env_version="v4",
            lr=1.05e-4,
            entropy_coef=0.01,
            entropy_floor=0.3,
            epsilon=0.05,
            epsilon_min=0.05,
            self_play_fraction=0.20,
            pool_update_mode="frozen",
            reset_optimizer=False,
            workers=40,
            segment_hands=5_000_000,
            target_total_hands=1_004_222_193,
            save_interval=100,
            archive_interval=0,
            archive_max=0,
            max_eval_candidates=1,
            snapshot_every=200,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="v4mp3_w36_entropy015_lr105e6_eps05",
            trainer="mp3",
            opponent_mode="pool",
            env_version="v4",
            lr=1.05e-4,
            entropy_coef=0.015,
            entropy_floor=0.3,
            epsilon=0.05,
            epsilon_min=0.05,
            self_play_fraction=0.20,
            pool_update_mode="frozen",
            reset_optimizer=False,
            workers=36,
            segment_hands=5_000_000,
            target_total_hands=1_004_222_193,
            save_interval=100,
            archive_interval=0,
            archive_max=0,
            max_eval_candidates=1,
            snapshot_every=200,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="v4faithful_pool_frozen_nommd_lr105e6_eps05",
            opponent_mode="pool",
            env_version="v4",
            lr=1.05e-4,
            entropy_coef=0.01,
            entropy_floor=0.3,
            mmd_lambda=0.0,
            epsilon=0.05,
            epsilon_min=0.05,
            self_play_fraction=0.20,
            pool_update_mode="frozen",
            collect_self_play_both=False,
            reset_optimizer=False,
            segment_hands=5_000_000,
            target_total_hands=1_500_000_000,
            repeat_until_target=True,
            light_archive=True,
            save_interval=100,
            archive_interval=100,
            archive_max=24,
            max_eval_candidates=5,
            snapshot_every=200,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="bridge_cap1_v4obs_pool_fixed_mmd020_lr5e6",
            opponent_mode="pool",
            env_version="v55cap1v4obs",
            lr=5e-6,
            entropy_coef=0.018,
            entropy_floor=0.45,
            mmd_lambda=0.20,
            mmd_anchor="fixed",
            self_play_fraction=0.10,
            segment_hands=10_000_000,
            target_total_hands=1_500_000_000,
            repeat_until_target=True,
            light_archive=True,
            save_interval=100,
            archive_interval=100,
            archive_max=24,
            max_eval_candidates=5,
            snapshot_every=25,
            max_runtime_rew100=99.0,
            max_runtime_positive_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="bridge_cap1_ema_fixed_mmd050_lr1e5",
            opponent_mode="ema",
            env_version="v55cap1",
            lr=1e-5,
            entropy_coef=0.025,
            entropy_floor=0.65,
            mmd_lambda=0.50,
            mmd_anchor="fixed",
            ema_only_fraction=0.75,
            self_play_fraction=0.10,
            segment_hands=25_000_000,
            target_total_hands=1_500_000_000,
            repeat_until_target=True,
            light_archive=True,
            save_interval=100,
            archive_interval=100,
            archive_max=24,
            max_eval_candidates=5,
            snapshot_every=50,
            max_runtime_positive_rew100=2.0,
            min_safety_stop_iters=20,
        ),
        Experiment(
            name="bridge_cap1_hybrid_fixed_mmd030_lr8e6",
            opponent_mode="hybrid",
            env_version="v55cap1",
            lr=8e-6,
            entropy_coef=0.025,
            entropy_floor=0.65,
            mmd_lambda=0.30,
            mmd_anchor="fixed",
            ema_fraction=0.30,
            self_play_fraction=0.08,
            segment_hands=1_500_000,
            save_interval=10,
            archive_interval=10,
            archive_max=12,
            snapshot_every=50,
            max_runtime_positive_rew100=2.0,
            min_safety_stop_iters=20,
        ),
        Experiment(
            name="bridge_cap1_ema_long_mmd080_lr3e6",
            opponent_mode="ema",
            env_version="v55cap1",
            lr=3e-6,
            entropy_coef=0.03,
            entropy_floor=0.75,
            mmd_lambda=0.80,
            mmd_anchor="fixed",
            ema_only_fraction=0.80,
            self_play_fraction=0.05,
            segment_hands=5_000_000,
            save_interval=25,
            archive_interval=25,
            archive_max=12,
            snapshot_every=50,
            max_runtime_positive_rew100=99.0,
            max_runtime_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="legacy_micro_hybrid_fixed_mmd030_lr5e6_sample07",
            opponent_mode="hybrid",
            env_version="v4",
            eval_sample=True,
            eval_temperature=0.7,
            lr=5e-6,
            entropy_coef=0.02,
            entropy_floor=0.50,
            mmd_lambda=0.30,
            mmd_anchor="fixed",
            ema_fraction=0.20,
            self_play_fraction=0.10,
            save_interval=1,
            archive_interval=1,
            archive_max=8,
            snapshot_every=25,
            max_runtime_positive_rew100=0.25,
        ),
        Experiment(
            name="v55_micro_fixed_mmd050_lr3e6_sample08",
            opponent_mode="hybrid",
            env_version="v55",
            eval_sample=True,
            eval_temperature=0.8,
            lr=3e-6,
            entropy_coef=0.04,
            entropy_floor=0.9,
            mmd_lambda=0.50,
            mmd_anchor="fixed",
            ema_fraction=0.15,
            self_play_fraction=0.05,
            save_interval=1,
            archive_interval=1,
            archive_max=8,
            snapshot_every=25,
            max_runtime_positive_rew100=0.20,
        ),
        Experiment(
            name="v55_long_adapt_fixed_mmd100_lr1e6",
            opponent_mode="hybrid",
            env_version="v55",
            lr=1e-6,
            entropy_coef=0.05,
            entropy_floor=1.0,
            mmd_lambda=1.00,
            mmd_anchor="fixed",
            ema_fraction=0.15,
            self_play_fraction=0.05,
            segment_hands=5_000_000,
            save_interval=25,
            archive_interval=25,
            archive_max=12,
            snapshot_every=50,
            max_runtime_positive_rew100=99.0,
            max_runtime_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="legacy_long_adapt_fixed_mmd050_lr1e6",
            opponent_mode="hybrid",
            env_version="v4",
            lr=1e-6,
            entropy_coef=0.02,
            entropy_floor=0.5,
            mmd_lambda=0.50,
            mmd_anchor="fixed",
            ema_fraction=0.15,
            self_play_fraction=0.05,
            segment_hands=5_000_000,
            save_interval=25,
            archive_interval=25,
            archive_max=12,
            snapshot_every=50,
            max_runtime_positive_rew100=99.0,
            max_runtime_rew100=99.0,
            min_safety_stop_iters=100,
        ),
        Experiment(
            name="ema_tempered_mmd010_entropy07",
            opponent_mode="ema",
            lr=3e-5,
            entropy_coef=0.03,
            entropy_floor=0.7,
            mmd_lambda=0.10,
            ema_only_fraction=0.6,
            min_runtime_entropy=0.08,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=1.8,
        ),
        Experiment(
            name="hybrid_mmd010_entropy07",
            opponent_mode="hybrid",
            lr=3e-5,
            entropy_coef=0.03,
            entropy_floor=0.7,
            mmd_lambda=0.10,
            ema_fraction=0.25,
            self_play_fraction=0.25,
            min_runtime_entropy=0.08,
            save_interval=25,
            snapshot_every=50,
            max_runtime_positive_rew100=1.8,
        ),
        # Slumbot-mimic exploitation: hero trains exclusively against a
        # behavior-cloned proxy of Slumbot. No self-play, no EMA, no pool drift.
        # Skipped automatically when mimic checkpoint is missing.
        Experiment(
            name="slumbot_mimic_exploit_lr3e5",
            opponent_mode="pool",
            trainer="mp3",
            lr=3e-5,
            entropy_coef=0.015,
            entropy_floor=0.40,
            self_play_fraction=0.0,
            workers=28,
            hands_per_iter=16384,
            save_interval=25,
            snapshot_every=50,
            slumbot_mimic_path="models/v55_lab/slumbot_mimic.pt",
        ),
        Experiment(
            name="slumbot_mimic_exploit_lr1e5_selfplay10",
            opponent_mode="pool",
            trainer="mp3",
            lr=1e-5,
            entropy_coef=0.02,
            entropy_floor=0.50,
            self_play_fraction=0.10,
            workers=28,
            hands_per_iter=16384,
            save_interval=25,
            snapshot_every=50,
            slumbot_mimic_path="models/v55_lab/slumbot_mimic.pt",
        ),
        # Path A iterations: flatten mimic's peaked softmax via temperature.
        # Mimic at T=1 has 47% of decisions with >95% confidence (near-argmax).
        # T=2 roughly halves the peak, restoring more of Slumbot's strategic mixing.
        Experiment(
            name="slumbot_mimic_exploit_temp2_lr1e5",
            opponent_mode="pool",
            trainer="mp3",
            lr=1e-5,
            entropy_coef=0.02,
            entropy_floor=0.50,
            self_play_fraction=0.0,
            workers=28,
            hands_per_iter=16384,
            save_interval=25,
            snapshot_every=50,
            slumbot_mimic_path="models/v55_lab/slumbot_mimic.pt",
            opponent_temperature=2.0,
        ),
        Experiment(
            name="slumbot_mimic_exploit_temp3_lr1e5_selfplay10",
            opponent_mode="pool",
            trainer="mp3",
            lr=1e-5,
            entropy_coef=0.02,
            entropy_floor=0.50,
            self_play_fraction=0.10,
            workers=28,
            hands_per_iter=16384,
            save_interval=25,
            snapshot_every=50,
            slumbot_mimic_path="models/v55_lab/slumbot_mimic.pt",
            opponent_temperature=3.0,
        ),
    ]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    return {
        "round": 0,
        "best_bb100": -9999.0,
        "best_model": None,
        "promoted": False,
        "history": [],
    }


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def promote(exp: Experiment, model_path: Path, result: dict, baseline: float) -> None:
    best = LAB / "alpha_holdem_v55_best.pt"
    promoted = MODELS / "alpha_holdem_v55_promoted.pt"
    shutil.copy2(model_path, best)
    shutil.copy2(model_path, promoted)
    meta = {
        "experiment": exp.name,
        "model": str(model_path),
        "baseline_bb100": baseline,
        "slumbot_target_bb100": SLUMBOT_DOMINATION_TARGET_BB100,
        "result": result,
        "promoted_at": now(),
        "config": asdict(exp),
    }
    (LAB / "alpha_holdem_v55_promoted.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    log(f"PROMOTED {exp.name}: bb100={result['bb100']:+.2f} baseline={baseline:+.2f}")


def candidate_checkpoints(exp: Experiment, min_hands: int) -> list[Path]:
    candidates: dict[str, Path] = {}
    if exp.out.exists() and read_checkpoint_hands(exp.out) > min_hands:
        candidates[str(exp.out.resolve())] = exp.out
    if exp.archive_dir.exists():
        for path in exp.archive_dir.glob("*.pt"):
            if read_checkpoint_hands(path) > min_hands:
                candidates[str(path.resolve())] = path
    ordered = sorted(
        candidates.values(),
        key=lambda path: (read_checkpoint_hands(path), read_checkpoint_iteration(path), str(path)),
    )
    deduped: dict[tuple[int, int], Path] = {}
    for path in ordered:
        key = (read_checkpoint_hands(path), read_checkpoint_iteration(path))
        # Prefer immutable archives over the mutable experiment output when
        # both contain the same training point.
        if key not in deduped or "archives" in path.parts:
            deduped[key] = path
    return list(deduped.values())


def limit_candidates(candidates: list[Path], max_candidates: int | None) -> list[Path]:
    if max_candidates is None or max_candidates <= 0 or len(candidates) <= max_candidates:
        return list(reversed(candidates))
    if max_candidates == 1:
        return [candidates[-1]]
    last_index = len(candidates) - 1
    selected_indices = {
        round(i * last_index / (max_candidates - 1))
        for i in range(max_candidates)
    }
    return [candidates[i] for i in sorted(selected_indices, reverse=True)]


def candidate_bench_tag(exp_name: str, round_idx: int, candidate_idx: int, candidate: Path) -> str:
    candidate_hands = read_checkpoint_hands(candidate)
    candidate_iter = read_checkpoint_iteration(candidate)
    return f"{exp_name}_r{round_idx}_h{candidate_hands}_i{candidate_iter}_c{candidate_idx}"


def jsonl_tags(path: Path) -> set[str]:
    if not path.exists():
        return set()
    tags: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        tag = data.get("tag")
        if isinstance(tag, str):
            tags.add(tag)
    return tags


def enqueue_bench_task(task: dict) -> bool:
    LAB.mkdir(parents=True, exist_ok=True)
    tag = str(task["tag"])
    if tag in jsonl_tags(BENCH_QUEUE_PATH) or tag in jsonl_tags(BENCH_DONE_PATH):
        return False
    with BENCH_QUEUE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(task, sort_keys=True) + "\n")
    return True


def ensure_bench_worker() -> None:
    out_f = BENCH_WORKER_OUT.open("ab")
    err_f = BENCH_WORKER_ERR.open("ab")
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "-u",
                "scripts/alpha_holdem/v55_bench_queue.py",
                "worker",
            ],
            cwd=ROOT,
            stdout=out_f,
            stderr=err_f,
            text=False,
        )
    finally:
        out_f.close()
        err_f.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rounds", type=int, default=10_000)
    parser.add_argument("--segment-hands", type=int, default=SEGMENT_HANDS)
    parser.add_argument("--baseline-bb100", type=float, default=None)
    parser.add_argument("--target-bb100", type=float, default=SLUMBOT_DOMINATION_TARGET_BB100)
    parser.add_argument("--require-positive-lcb", action="store_true", default=True)
    parser.add_argument("--allow-negative-lcb", dest="require_positive_lcb", action="store_false")
    parser.add_argument(
        "--sync-bench",
        action="store_true",
        help="Block training while running Slumbot benchmarks. Default is async queue.",
    )
    parser.add_argument("--start", default=str(MODELS / "alpha_holdem_v4_final.pt"))
    args = parser.parse_args()

    os.chdir(ROOT)
    LAB.mkdir(parents=True, exist_ok=True)
    baseline = args.baseline_bb100 if args.baseline_bb100 is not None else local_v4_baseline()
    promote_threshold = max(float(args.target_bb100), baseline)
    state = load_state()
    state["baseline_bb100"] = baseline
    state["promote_threshold_bb100"] = promote_threshold
    state["require_positive_lcb"] = bool(args.require_positive_lcb)
    save_state(state)

    log(
        f"START baseline_bb100={baseline:+.2f} "
        f"slumbot_target_bb100={float(args.target_bb100):+.2f} "
        f"promote_threshold={promote_threshold:+.2f} "
        f"require_positive_lcb={bool(args.require_positive_lcb)}"
    )
    start_ckpt = Path(args.start)
    if not start_ckpt.exists():
        log(f"ERROR start checkpoint missing: {start_ckpt}")
        return 2

    exps = experiments()
    while not state.get("promoted") and int(state["round"]) < args.max_rounds:
        round_idx = int(state["round"])
        exp = exps[round_idx % len(exps)]
        if exp.slumbot_mimic_path and not Path(exp.slumbot_mimic_path).exists():
            log(
                f"SKIP_NO_MIMIC exp={exp.name} mimic_path={exp.slumbot_mimic_path} "
                f"does not exist; train it via scripts/alpha_holdem/train_slumbot_mimic.py"
            )
            state["round"] = round_idx + 1
            save_state(state)
            continue
        resume = exp.out if exp.out.exists() else start_ckpt
        current_hands = read_checkpoint_hands(resume)
        segment_hands = int(exp.segment_hands or args.segment_hands)
        if exp.target_total_hands is not None and current_hands >= exp.target_total_hands:
            log(
                f"TARGET_REACHED exp={exp.name} current_hands={current_hands:,} "
                f"target_total={exp.target_total_hands:,}; advancing"
            )
            state["round"] = round_idx + 1
            save_state(state)
            continue
        target_hands = current_hands + segment_hands
        if exp.target_total_hands is not None:
            target_hands = min(target_hands, exp.target_total_hands)
        log(
            f"ROUND {round_idx} exp={exp.name} resume={resume} "
            f"current_hands={current_hands:,} target={target_hands:,} "
            f"segment={segment_hands:,}"
        )

        rc = train_segment(exp, resume, target_hands)
        new_hands = read_checkpoint_hands(exp.out)
        log(f"TRAIN_DONE exp={exp.name} rc={rc} hands={new_hands:,}")

        if not exp.out.exists() or new_hands <= current_hands:
            log(f"SKIP_BENCH exp={exp.name} no progress")
            state["round"] = round_idx + 1
            save_state(state)
            continue

        candidates_all = candidate_checkpoints(exp, current_hands)
        candidates = limit_candidates(candidates_all, exp.max_eval_candidates)
        log(
            f"CANDIDATES exp={exp.name} count={len(candidates)} "
            f"available={len(candidates_all)}"
        )
        # Smoke samples are intentionally small and noisy. Promote any candidate
        # close enough to the V4 baseline so the 20k run, not a 2k roll, decides.
        full_bench_floor = baseline - 25.0

        if not args.sync_bench:
            enqueued = 0
            for candidate_idx, candidate in enumerate(candidates, start=1):
                candidate_hands = read_checkpoint_hands(candidate)
                smoke_tag = f"{candidate_bench_tag(exp.name, round_idx, candidate_idx, candidate)}_smoke"
                task = {
                    "tag": smoke_tag,
                    "model": str(candidate),
                    "sessions": SMOKE_SESSIONS,
                    "hands_per_session": SMOKE_HANDS_PER_SESSION,
                    "sample": exp.eval_sample,
                    "temperature": exp.eval_temperature,
                    "experiment": exp.name,
                    "round": round_idx,
                    "candidate_idx": candidate_idx,
                    "candidate_hands": candidate_hands,
                    "kind": "smoke",
                }
                if enqueue_bench_task(task):
                    enqueued += 1
                    log(
                        f"ASYNC_BENCH_ENQUEUE exp={exp.name} idx={candidate_idx}/{len(candidates)} "
                        f"hands={candidate_hands:,} tag={smoke_tag} model={candidate}"
                    )
            if enqueued:
                ensure_bench_worker()
                log(f"ASYNC_BENCH_WORKER ensured enqueued={enqueued}")
            candidates = []

        for candidate_idx, candidate in enumerate(candidates, start=1):
            candidate_hands = read_checkpoint_hands(candidate)
            candidate_tag = candidate_bench_tag(exp.name, round_idx, candidate_idx, candidate)
            smoke_tag = f"{candidate_tag}_smoke"
            log(
                f"CANDIDATE_SMOKE exp={exp.name} idx={candidate_idx}/{len(candidates)} "
                f"hands={candidate_hands:,} model={candidate}"
            )
            smoke = benchmark(
                candidate,
                smoke_tag,
                SMOKE_SESSIONS,
                SMOKE_HANDS_PER_SESSION,
                sample=exp.eval_sample,
                temperature=exp.eval_temperature,
            )
            state["history"].append({
                "round": round_idx,
                "experiment": exp.name,
                "hands": candidate_hands,
                "model": str(candidate),
                "smoke": smoke,
                "config": asdict(exp),
            })

            if smoke["bb100"] > float(state["best_bb100"]):
                state["best_bb100"] = smoke["bb100"]
                state["best_model"] = str(candidate)
                shutil.copy2(candidate, LAB / "alpha_holdem_v55_best_smoke.pt")
                log(f"BEST_SMOKE exp={exp.name} bb100={smoke['bb100']:+.2f} model={candidate}")

            # Full bench when smoke is plausibly V4-level or better. The full
            # run is the real gate for "quality above V4".
            if smoke["bb100"] >= full_bench_floor or smoke["bb100"] > 0.0:
                full_tag = f"{candidate_tag}_full"
                full = benchmark(
                    candidate,
                    full_tag,
                    FULL_SESSIONS,
                    FULL_HANDS_PER_SESSION,
                    sample=exp.eval_sample,
                    temperature=exp.eval_temperature,
                )
                state["history"][-1]["full"] = full
                if full["hands"] > 0 and full["bb100"] > float(state["best_bb100"]):
                    state["best_bb100"] = full["bb100"]
                    state["best_model"] = str(candidate)
                    shutil.copy2(candidate, LAB / "alpha_holdem_v55_best_full.pt")
                    log(f"BEST_FULL exp={exp.name} bb100={full['bb100']:+.2f} model={candidate}")
                ci = float(full["ci_bb100"] or 0.0)
                lcb = float(full["bb100"]) - ci
                target_hit = full["hands"] > 0 and float(full["bb100"]) >= promote_threshold
                confidence_hit = (not args.require_positive_lcb) or lcb > 0.0
                log(
                    f"PROMOTE_CHECK exp={exp.name} bb100={full['bb100']:+.2f} "
                    f"lcb={lcb:+.2f} target_hit={target_hit} confidence_hit={confidence_hit} "
                    f"model={candidate}"
                )
                if target_hit and confidence_hit:
                    confirm_tag = f"{candidate_tag}_confirm"
                    confirm = benchmark(
                        candidate,
                        confirm_tag,
                        CONFIRM_SESSIONS,
                        CONFIRM_HANDS_PER_SESSION,
                        sample=exp.eval_sample,
                        temperature=exp.eval_temperature,
                    )
                    state["history"][-1]["confirm"] = confirm
                    confirm_ci = float(confirm["ci_bb100"] or 0.0)
                    confirm_lcb = float(confirm["bb100"]) - confirm_ci
                    confirm_target_hit = (
                        confirm["hands"] > 0 and float(confirm["bb100"]) >= promote_threshold
                    )
                    confirm_confidence_hit = confirm_lcb >= CONFIRM_MIN_LCB_BB100
                    log(
                        f"CONFIRM_CHECK exp={exp.name} bb100={confirm['bb100']:+.2f} "
                        f"lcb={confirm_lcb:+.2f} target_hit={confirm_target_hit} "
                        f"confidence_hit={confirm_confidence_hit} model={candidate}"
                    )
                    save_state(state)
                    if confirm_target_hit and confirm_confidence_hit:
                        promote(exp, candidate, confirm, baseline)
                        state["promoted"] = True
                        break

            save_state(state)

        if state.get("promoted"):
            save_state(state)
            break

        if (
            exp.repeat_until_target
            and exp.target_total_hands is not None
            and new_hands < exp.target_total_hands
        ):
            log(
                f"REPEAT_UNTIL_TARGET exp={exp.name} hands={new_hands:,} "
                f"target_total={exp.target_total_hands:,}"
            )
            state["round"] = round_idx
        else:
            state["round"] = round_idx + 1
        save_state(state)

    log("STOP promoted=" + str(state.get("promoted")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
