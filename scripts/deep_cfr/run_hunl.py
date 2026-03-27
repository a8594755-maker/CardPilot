"""
Auto-resuming wrapper for HUNL Deep CFR training.
Runs training in chunks and auto-resumes from latest checkpoint.

Usage:
  python scripts/deep_cfr/run_hunl.py
"""
import glob
import os
import re
import subprocess
import sys
import time


CHECKPOINT_DIR = "checkpoints/sdcfr_hunl_srp50"
TARGET_ITERATIONS = 200
CHUNK_SIZE = 50  # iterations per chunk before checkpoint + restart
LOG_FILE = os.path.join(CHECKPOINT_DIR, "train_full.log")

TRAIN_ARGS = [
    sys.executable, "-u", "-m", "scripts.deep_cfr.train",
    "--game", "hunl",
    "--iterations", str(TARGET_ITERATIONS),
    "--traversals", "20000",
    "--game-config", "srp_50bb",
    "--train-mode", "aggregated",
    "--device", "cuda",
    "--checkpoint-dir", CHECKPOINT_DIR,
    "--buffer-size", "10000000",
    "--checkpoint-interval", "25",
    "--eval-interval", "25",
    "--eval-samples", "2000",
    "--lr", "0.001",
    "--hidden-dims", "256,256,256",
]


def find_latest_checkpoint():
    """Find the highest-iteration checkpoint file."""
    pattern = os.path.join(CHECKPOINT_DIR, "sdcfr_iter*.pt")
    files = glob.glob(pattern)
    if not files:
        return None, 0
    best_file = None
    best_iter = 0
    for f in files:
        m = re.search(r'sdcfr_iter(\d+)\.pt$', f)
        if m:
            it = int(m.group(1))
            if it > best_iter:
                best_iter = it
                best_file = f
    return best_file, best_iter


def main():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    while True:
        ckpt, last_iter = find_latest_checkpoint()
        if last_iter >= TARGET_ITERATIONS:
            print(f"Training complete! Reached {last_iter}/{TARGET_ITERATIONS} iterations.")
            break

        args = list(TRAIN_ARGS)
        if ckpt:
            args += ["--resume", ckpt]
            print(f"\n{'='*60}")
            print(f"Resuming from {ckpt} (iter {last_iter})")
            print(f"{'='*60}\n")
        else:
            print(f"\n{'='*60}")
            print(f"Starting fresh training")
            print(f"{'='*60}\n")

        with open(LOG_FILE, "a") as log:
            proc = subprocess.Popen(
                args,
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
            )
            proc.wait()
            exit_code = proc.returncode

        new_ckpt, new_iter = find_latest_checkpoint()
        print(f"Process exited with code {exit_code}. Latest checkpoint: iter {new_iter}")

        if new_iter <= last_iter:
            print("No progress made. Waiting 10s before retry...")
            time.sleep(10)

        if new_iter >= TARGET_ITERATIONS:
            print(f"Training complete! Reached {new_iter}/{TARGET_ITERATIONS} iterations.")
            break


if __name__ == "__main__":
    main()
