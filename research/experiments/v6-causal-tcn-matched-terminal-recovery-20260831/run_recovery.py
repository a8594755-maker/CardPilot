"""Read-only recovery of complete causal-TCN matched evidence."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import psutil
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-causal-tcn-matched-reward-pilot-20260831"
PAIRS = 4096
TARGET = 262144
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)
def log(*args):
    subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def gone(execution):
    try: return abs(psutil.Process(execution["pid"]).create_time() - execution["create_time"]) > 0.001
    except psutil.NoSuchProcess: return True


def estimate(values):
    values = [float(value) for value in values]; mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def gate(tc, ts, points): return tc["ci95"][0] > 0 and ts["ci95"][0] > 0 and sum(value > 0 for value in points) >= 3


def compute():
    values = {}; decks = None; evidence = []
    for name in ("source", "control", "treatment"):
        for index in range(5):
            path = PARENT / f"matrix/{name}_anchor{index}/pairs.jsonl"
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            assert len(rows) == PAIRS and [row["pair_index"] for row in rows] == list(range(PAIRS))
            current = [row["deck"] for row in rows]
            if decks is None: decks = current
            assert current == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
            summary = PARENT / f"matrix/{name}_anchor{index}/summary.json"
            assert read(summary)["status"] == "COMPLETED"
            evidence.extend(({"path": str(path), "sha256": sha(path)}, {"path": str(summary), "sha256": sha(summary)}))
    assert all(value == 0 for value in values["source", 0])
    per_anchor = [estimate([t - c for t, c in zip(values["treatment", index], values["control", index])]) for index in range(5)]
    tc = estimate([math.fsum(values["treatment", index][row] - values["control", index][row] for index in range(5)) / 5 for row in range(PAIRS)])
    ts = estimate([math.fsum(values["treatment", index][row] - values["source", index][row] for index in range(5)) / 5 for row in range(PAIRS)])
    return tc, ts, per_anchor, evidence


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "analysis.json", "input_manifest.json")): raise ValueError("No repeat")
    started = time.monotonic(); current = psutil.Process()
    write(BASE / "execution.json", {"status": "RUNNING", "pid": current.pid, "create_time": current.create_time(), "started_at": datetime.now(timezone.utc).isoformat(), "new_training_hands": 0, "evaluation_hands": 0, "source_evaluation_hands": 122880})
    parent_record = read(PARENT / "experiment.json"); parent_execution = read(PARENT / "execution.json")
    assert parent_record["status"] == "FAILED" and parent_record["result"]["decision"] == "TERMINAL_AGGREGATION_FAILED_EVIDENCE_PRESERVED"
    assert parent_execution["status"] == "FAILED_PRESERVED" and gone(parent_execution)
    for path, expected in parent_record["artifact_integrity"].items(): assert sha(path) == expected["sha256"]
    checkpoints = []
    for arm, expected_hands in (("control", 266229), ("treatment", 266071)):
        path = PARENT / f"frozen/{arm}.pt"; checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        assert checkpoint["environment_hand_accounting"]["completed_hands"] == expected_hands >= TARGET
        assert read(PARENT / f"production/{arm}/session_audit.json")["status"] == "PASS"
        checkpoints.append({"arm": arm, "path": str(path), "sha256": sha(path), "hands": expected_hands})
    tc, ts, per_anchor, evidence = compute(); points = [item["mean"] for item in per_anchor]
    decision = "ADMIT_CAUSAL_TCN_TRAINING_SEED_CONFIRMATION" if gate(tc, ts, points) else "CAUSAL_TCN_MATCHED_REWARD_GATE_NOT_PASSED"
    write(BASE / "input_manifest.json", {"parent_record": {"path": str(PARENT / "experiment.json"), "sha256": sha(PARENT / "experiment.json")}, "checkpoints": checkpoints, "raw_evidence": evidence})
    analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "preserved_parent_status": "FAILED", "parent_training_hands": 532300, "new_training_hands": 0, "source_evaluation_hands": 122880, "evaluation_hands": 0, "treatment_control": tc, "treatment_source": ts, "treatment_control_by_anchor": per_anchor, "positive_treatment_control_anchors": sum(value > 0 for value in points), "candidate_sha256": {item["arm"]: item["sha256"] for item in checkpoints}, "slumbot_hands": 0, "goal_achieved": False}
    write(BASE / "analysis.json", analysis)
    execution = read(BASE / "execution.json"); execution.update({"status": "COMPLETED_PENDING_REVIEW", "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_seconds": time.monotonic() - started}); write(BASE / "execution.json", execution)
    log("--artifact", BASE / "execution.json", "--artifact", BASE / "input_manifest.json", "--artifact", BASE / "analysis.json", "--count", "new_training_hands=0", "--count", "evaluation_hands=0", "--count", "slumbot_hands=0", "--metric", "source_evaluation_hands=122880", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    print(json.dumps(analysis), flush=True)


if __name__ == "__main__": main()
