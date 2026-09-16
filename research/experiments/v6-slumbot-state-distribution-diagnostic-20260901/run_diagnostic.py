"""Offline batched policy-distribution replay on audited Slumbot states."""
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901"
RAW = PARENT / "frozen/final.pt"
SOURCE = ROOT / "research/experiments/v6-diverse-learned-league-pilot-20260831/frozen/anchor0.pt"
RAW_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
SOURCE_SHA = "944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file
from alpha_holdem.execution_v6 import load_policy
from alpha_holdem.policy_contract_v6 import from_external, observation


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): atomic_json(Path(path), value)
def log(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def policy_probabilities(model, observations, batch_size=512):
    result = []
    with torch.no_grad():
        for start in range(0, len(observations), batch_size):
            batch = observations[start:start + batch_size]
            tensors = [torch.as_tensor(np.stack([row[key] for row in batch]), dtype=torch.float32)
                       for key in ("card_info", "action_info", "extra_info", "legal_mask")]
            logits, _ = model(*tensors)
            values = logits.detach().cpu().numpy().astype(np.float64)
            for vector, row in zip(values, batch):
                legal = np.flatnonzero(row["legal_mask"])
                weights = np.exp(vector[legal] - np.max(vector[legal]))
                probs = np.zeros(9, dtype=np.float64)
                probs[legal] = weights / weights.sum()
                result.append(probs)
    return result


def summarize(rows):
    n = len(rows)
    if not n: raise ValueError("empty partition")
    mean = lambda key: math.fsum(float(row[key]) for row in rows) / n
    raw_slots = [math.fsum(row["raw_probs"][slot] for row in rows) / n for slot in range(9)]
    source_slots = [math.fsum(row["source_probs"][slot] for row in rows) / n for slot in range(9)]
    raw_mix = [sum(row["raw_greedy"] == slot for row in rows) / n for slot in range(9)]
    source_mix = [sum(row["source_greedy"] == slot for row in rows) / n for slot in range(9)]
    return {
        "states": n,
        "greedy_disagreement_rate": mean("greedy_disagreement"),
        "raw_entropy": mean("raw_entropy"), "source_entropy": mean("source_entropy"),
        "kl_raw_source": mean("kl_raw_source"), "kl_source_raw": mean("kl_source_raw"),
        "total_variation": mean("total_variation"),
        "raw_greedy_probability": mean("raw_greedy_probability"),
        "source_greedy_probability": mean("source_greedy_probability"),
        "raw_slot_probabilities": raw_slots, "source_slot_probabilities": source_slots,
        "raw_minus_source_slot_probabilities": [a - b for a, b in zip(raw_slots, source_slots)],
        "raw_greedy_slot_mix": raw_mix, "source_greedy_slot_mix": source_mix,
    }


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "state_metrics.jsonl", "analysis.json")):
        raise ValueError("No restart")
    assert sha(RAW) == RAW_SHA and sha(SOURCE) == SOURCE_SHA
    assert read(PARENT / "experiment.json")["status"] == "COMPLETED"
    assert read(PARENT / "reviewed_analysis.json")["status"] == "PASS"
    assert read(PARENT / "combined_audit.json")["status"] == "PASS"
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
                 "network_calls": 0, "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0}
    write(BASE / "execution.json", execution)
    code = BASE / "execution_code"
    code.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += ["research/experiment_log.py"] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, code, paths)
    copies = []
    for relative in paths:
        target = code / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
    write(code / "copy_manifest.json", copies)
    log("--artifact", code / "source_manifest.json", "--artifact", code / "code.patch", "--artifact", code / "copy_manifest.json")
    raw_model, _, raw_hash = load_policy(RAW, "cpu")
    source_model, _, source_hash = load_policy(SOURCE, "cpu")
    assert raw_hash == RAW_SHA and source_hash == SOURCE_SHA
    responses, metadata = [], []
    input_hashes = []
    for session in range(1, 9):
        path = PARENT / "sessions" / f"s{session:02d}" / "hands.jsonl"
        input_hashes.append({"path": str(path), "sha256": sha(path)})
        for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hand = json.loads(line)
            assert hand["successful_hand"] == hand_line and hand["model_sha256"] == RAW_SHA
            for decision_index, decision in enumerate(hand["decisions"]):
                response = decision["response"]
                state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
                obs, _ = observation(state, include_position=False)
                assert decision["legal_mask"] == obs["legal_mask"].tolist()
                responses.append(obs)
                metadata.append({"session": session, "hand": hand_line, "decision": decision_index,
                                 "street": int(state.street), "seat": int(response["client_pos"]),
                                 "legal_mask": "".join(str(int(value)) for value in obs["legal_mask"])})
    write(BASE / "input_manifest.json", {"raw_checkpoint": {"path": str(RAW), "sha256": RAW_SHA},
          "source_checkpoint": {"path": str(SOURCE), "sha256": SOURCE_SHA}, "hands": input_hashes,
          "parent_audit_sha256": sha(PARENT / "combined_audit.json")})
    log("--artifact", BASE / "input_manifest.json")
    raw_probs = policy_probabilities(raw_model, responses)
    source_probs = policy_probabilities(source_model, responses)
    rows = []
    with (BASE / "state_metrics.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for meta, raw, source in zip(metadata, raw_probs, source_probs):
            raw_greedy, source_greedy = int(np.argmax(raw)), int(np.argmax(source))
            legal = raw > 0
            row = {**meta, "raw_probs": raw.tolist(), "source_probs": source.tolist(),
                   "raw_greedy": raw_greedy, "source_greedy": source_greedy,
                   "greedy_disagreement": int(raw_greedy != source_greedy),
                   "raw_entropy": float(-np.sum(raw[legal] * np.log(raw[legal]))),
                   "source_entropy": float(-np.sum(source[legal] * np.log(source[legal]))),
                   "kl_raw_source": float(np.sum(raw[legal] * np.log(raw[legal] / source[legal]))),
                   "kl_source_raw": float(np.sum(source[legal] * np.log(source[legal] / raw[legal]))),
                   "total_variation": float(0.5 * np.sum(np.abs(raw - source))),
                   "raw_greedy_probability": float(raw[raw_greedy]),
                   "source_greedy_probability": float(source[source_greedy])}
            rows.append(row)
            output.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    partitions = defaultdict(list)
    for row in rows:
        partitions[f"street{row['street']}_seat{row['seat']}"] .append(row)
    partition_summary = {key: summarize(value) for key, value in sorted(partitions.items())}
    supported = {key: value for key, value in partition_summary.items() if value["states"] >= 100}
    largest_key, largest = max(supported.items(), key=lambda item: item[1]["total_variation"])
    informative = any(value["greedy_disagreement_rate"] > 0.25 or value["total_variation"] > 0.10 for value in supported.values())
    decision = "CONCENTRATED_POLICY_DRIFT_IDENTIFIED" if informative else "NO_CONCENTRATED_POLICY_DRIFT"
    analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": decision,
                "states": len(rows), "hands": 5000, "overall": summarize(rows),
                "partitions": partition_summary, "largest_supported_tv_partition": largest_key,
                "largest_supported_tv": largest, "network_calls": 0, "new_training_hands": 0,
                "evaluation_hands": len(rows) * 2, "slumbot_hands": 0, "goal_achieved": False,
                "interpretation_limit": "raw-policy on-policy state corpus; no counterfactual source value inference"}
    write(BASE / "analysis.json", analysis)
    execution.update({"status": "COMPLETED_PENDING_REVIEW", "states": len(rows),
                      "evaluation_hands": len(rows) * 2, "finished_at": datetime.now(timezone.utc).isoformat(),
                      "wall_time_seconds": time.monotonic() - started})
    write(BASE / "execution.json", execution)
    log("--artifact", BASE / "state_metrics.jsonl", "--artifact", BASE / "analysis.json",
        "--count", "new_training_hands=0", "--count", f"evaluation_hands={len(rows) * 2}",
        "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    print(json.dumps({"decision": decision, "states": len(rows), "largest_partition": largest_key,
                      "largest_tv": largest["total_variation"]}, sort_keys=True))


if __name__ == "__main__": main()
