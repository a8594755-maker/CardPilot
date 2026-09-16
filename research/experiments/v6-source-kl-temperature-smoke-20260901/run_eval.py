"""Evaluate only the new source-KL-temperature treatment on the audited panel."""

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
PRIOR = ROOT / "research/experiments/v6-greedy-advantage-margin-smoke-20260901"
CONTROL = PRIOR / "control/latest.pt"
TREATMENT = BASE / "treatment/latest.pt"
PAIRS = 1024
SEED = 20261115
EXPECTED_CONTROL_SHA = "d806394bc8f8068f8b72e19153d6f96c14f09e8c41c1418091e8441a977c8e29"
EXPECTED_TREATMENT_SHA = "d413f3fd2b980a9eeab47d11331b9db0c899ebbf350610306daa50493882ecfe"
ANCHORS = {
    "standard10": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor0.pt",
    "slumbot_free": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor1.pt",
    "corrected_cfr96": ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor2.pt",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_one(name):
    out = BASE / "eval" / f"treatment_{name}"
    command = [
        sys.executable, str(ROOT / "scripts/alpha_holdem/v6_mirror_eval.py"),
        "--candidate", str(TREATMENT), "--anchor", str(ANCHORS[name]),
        "--pairs", str(PAIRS), "--seed", str(SEED), "--device", "cpu",
        "--policy-mode", "greedy", "--out-dir", str(out),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (BASE / "eval").mkdir(exist_ok=True)
    (BASE / "eval" / f"treatment_{name}.stdout.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(result.stderr)


def load(path):
    decks, values = [], []
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        row = json.loads(line)
        assert row["pair_index"] == index
        decks.append(row["deck"])
        values.append(float(np.mean(row["rewards_bb"]) * 100.0))
    return decks, np.asarray(values, dtype=np.float64)


def stats(values):
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(values.size))
    return mean, [mean - half, mean + half]


def main():
    if (BASE / "eval").exists():
        raise ValueError("fixed one-shot evaluation already exists")
    assert sha256(CONTROL) == EXPECTED_CONTROL_SHA
    assert sha256(TREATMENT) == EXPECTED_TREATMENT_SHA
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run_one, ANCHORS))
    rows, pooled = [], []
    for name, anchor in ANCHORS.items():
        control_path = PRIOR / "eval" / f"control_{name}/pairs.jsonl"
        treatment_path = BASE / "eval" / f"treatment_{name}/pairs.jsonl"
        control_decks, control = load(control_path)
        treatment_decks, treatment = load(treatment_path)
        assert len(control) == len(treatment) == PAIRS and control_decks == treatment_decks
        delta = treatment - control
        mean, interval = stats(delta)
        pooled.extend(delta.tolist())
        rows.append({
            "anchor": name,
            "anchor_sha256": sha256(anchor),
            "control_bb100": float(control.mean()),
            "treatment_bb100": float(treatment.mean()),
            "treatment_minus_control_bb100": mean,
            "paired_ci95": interval,
            "prior_control_pairs_sha256": sha256(control_path),
            "treatment_pairs_sha256": sha256(treatment_path),
        })
    pooled = np.asarray(pooled, dtype=np.float64)
    mean, interval = stats(pooled)
    report = {
        "schema": "cardpilot.source_kl_temperature_smoke_delta.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "pairs_per_anchor": PAIRS,
        "policy_mode": "greedy",
        "control_sha256": EXPECTED_CONTROL_SHA,
        "treatment_sha256": EXPECTED_TREATMENT_SHA,
        "anchors": rows,
        "pooled": {
            "pairs": len(pooled),
            "treatment_minus_control_bb100": mean,
            "paired_ci95": interval,
            "positive_anchors": sum(row["treatment_minus_control_bb100"] > 0 for row in rows),
        },
        "new_evaluation_hands": 2 * PAIRS * len(ANCHORS),
        "reused_control_evaluation_hands": 2 * PAIRS * len(ANCHORS),
    }
    (BASE / "eval/paired_delta.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["pooled"], sort_keys=True))


if __name__ == "__main__":
    main()
