"""Common-deck greedy endpoint evaluation for the matched margin smoke."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PAIRS = 1024
SEED = 20261115
ARMS = {
    "control": BASE / "control/latest.pt",
    "treatment": BASE / "treatment/latest.pt",
}
ANCHORS = {
    "standard10": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor0.pt",
    "slumbot_free": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor1.pt",
    "corrected_cfr96": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor2.pt",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_one(item: tuple[str, str]) -> dict:
    arm, anchor_name = item
    out_dir = BASE / "eval" / f"{arm}_{anchor_name}"
    command = [
        sys.executable,
        str(ROOT / "scripts/alpha_holdem/v6_mirror_eval.py"),
        "--candidate", str(ARMS[arm]),
        "--anchor", str(ANCHORS[anchor_name]),
        "--pairs", str(PAIRS),
        "--seed", str(SEED),
        "--device", "cpu",
        "--policy-mode", "greedy",
        "--out-dir", str(out_dir),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (BASE / "eval").mkdir(exist_ok=True)
    (BASE / "eval" / f"{arm}_{anchor_name}.stdout.log").write_text(
        completed.stdout + completed.stderr, encoding="utf-8"
    )
    if completed.returncode:
        raise RuntimeError(f"evaluation failed for {arm}/{anchor_name}: {completed.stderr}")
    return json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))


def load_values(path: Path) -> tuple[list[list[int]], np.ndarray]:
    decks, values = [], []
    for expected_index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        if row["pair_index"] != expected_index:
            raise ValueError(f"non-contiguous pair index in {path}")
        decks.append(row["deck"])
        values.append(np.mean(row["rewards_bb"]) * 100.0)
    return decks, np.asarray(values, dtype=np.float64)


def ci(values: np.ndarray) -> tuple[float, float, float]:
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, mean - half, mean + half


def main() -> None:
    eval_dir = BASE / "eval"
    if eval_dir.exists():
        raise ValueError("fixed one-shot evaluation directory already exists")
    for path in [*ARMS.values(), *ANCHORS.values()]:
        if not path.is_file():
            raise FileNotFoundError(path)
    items = [(arm, anchor) for anchor in ANCHORS for arm in ARMS]
    with ThreadPoolExecutor(max_workers=3) as pool:
        summaries = list(pool.map(run_one, items))
    rows, pooled = [], []
    for anchor_name, anchor_path in ANCHORS.items():
        control_path = eval_dir / f"control_{anchor_name}/pairs.jsonl"
        treatment_path = eval_dir / f"treatment_{anchor_name}/pairs.jsonl"
        control_decks, control = load_values(control_path)
        treatment_decks, treatment = load_values(treatment_path)
        if control_decks != treatment_decks:
            raise ValueError(f"deck mismatch for {anchor_name}")
        delta = treatment - control
        mean, lower, upper = ci(delta)
        pooled.extend(delta.tolist())
        rows.append({
            "anchor": anchor_name,
            "anchor_path": str(anchor_path),
            "anchor_sha256": sha256(anchor_path),
            "pairs": PAIRS,
            "control_bb100": float(control.mean()),
            "treatment_bb100": float(treatment.mean()),
            "treatment_minus_control_bb100": mean,
            "paired_ci95": [lower, upper],
            "control_pairs_sha256": sha256(control_path),
            "treatment_pairs_sha256": sha256(treatment_path),
        })
    pooled_array = np.asarray(pooled, dtype=np.float64)
    mean, lower, upper = ci(pooled_array)
    output = {
        "schema": "cardpilot.greedy_margin_smoke_paired_delta.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "pairs_per_anchor": PAIRS,
        "policy_mode": "greedy",
        "control_sha256": sha256(ARMS["control"]),
        "treatment_sha256": sha256(ARMS["treatment"]),
        "anchors": rows,
        "pooled": {
            "pairs": int(pooled_array.size),
            "treatment_minus_control_bb100": mean,
            "paired_ci95": [lower, upper],
            "positive_anchors": sum(row["treatment_minus_control_bb100"] > 0 for row in rows),
        },
        "evaluation_hands": 2 * PAIRS * len(ARMS) * len(ANCHORS),
        "raw_summaries": summaries,
    }
    (eval_dir / "paired_delta.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output["pooled"], sort_keys=True))


if __name__ == "__main__":
    main()
