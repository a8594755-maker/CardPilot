"""Outcome-free candidate-parent distribution replay on parent on-policy states."""
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = ROOT / "research/experiments/v6-slumbot-state-distribution-diagnostic-20260901/run_diagnostic.py"
CORPUS = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
CANDIDATE = ROOT / "research/experiments/v6-parent-kl-conservative-tail-recovery-20260901/frozen/tail_raw.pt"
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
CANDIDATE_SHA = "1c050edb088eaaf4bdc653a7b7b4708191854a7ca216f913ca2b7c1c6cd412c4"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file
from alpha_holdem.execution_v6 import load_policy
from alpha_holdem.policy_contract_v6 import from_external, observation


def load_engine():
    spec = importlib.util.spec_from_file_location("distribution_helpers", ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): atomic_json(Path(path), value)
def update(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "state_metrics.jsonl", "analysis.json")):
        raise ValueError("No restart")
    assert sha(CANDIDATE) == CANDIDATE_SHA and sha(PARENT) == PARENT_SHA
    assert read(CORPUS / "experiment.json")["status"] == "COMPLETED"
    assert read(CORPUS / "reviewed_analysis.json")["status"] == "PASS"
    assert read(CORPUS / "combined_audit.json")["status"] == "PASS"
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "network_calls": 0, "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0}
    write(BASE / "execution.json", execution)
    code = BASE / "execution_code"
    code.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += ["research/experiment_log.py"] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, code, paths)
    for relative in paths:
        target = code / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    update("--artifact", code / "source_manifest.json", "--artifact", code / "code.patch")

    helpers = load_engine()
    candidate_model, _, candidate_hash = load_policy(CANDIDATE, "cpu")
    parent_model, _, parent_hash = load_policy(PARENT, "cpu")
    assert candidate_hash == CANDIDATE_SHA and parent_hash == PARENT_SHA
    observations, metadata, input_hashes = [], [], []
    for session in range(1, 9):
        path = CORPUS / "sessions" / f"s{session:02d}" / "hands.jsonl"
        input_hashes.append({"path": str(path), "sha256": sha(path)})
        for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hand = json.loads(line)
            assert hand["successful_hand"] == hand_line and hand["model_sha256"] == PARENT_SHA
            for decision_index, decision in enumerate(hand["decisions"]):
                response = decision["response"]
                state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
                obs, _ = observation(state, include_position=False)
                assert decision["legal_mask"] == obs["legal_mask"].tolist()
                observations.append(obs)
                metadata.append({"session": session, "hand": hand_line, "decision": decision_index, "street": int(state.street), "seat": int(response["client_pos"]), "legal_mask": "".join(str(int(value)) for value in obs["legal_mask"])})
    write(BASE / "input_manifest.json", {"candidate_checkpoint": {"path": str(CANDIDATE), "sha256": CANDIDATE_SHA}, "parent_checkpoint": {"path": str(PARENT), "sha256": PARENT_SHA}, "hands": input_hashes, "corpus_audit_sha256": sha(CORPUS / "combined_audit.json")})
    update("--artifact", BASE / "input_manifest.json")
    candidate_probs = helpers.policy_probabilities(candidate_model, observations)
    parent_probs = helpers.policy_probabilities(parent_model, observations)
    rows = []
    with (BASE / "state_metrics.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for meta, candidate, parent in zip(metadata, candidate_probs, parent_probs):
            candidate_greedy, parent_greedy = int(np.argmax(candidate)), int(np.argmax(parent))
            legal = candidate > 0
            row = {**meta, "raw_probs": candidate.tolist(), "source_probs": parent.tolist(), "raw_greedy": candidate_greedy, "source_greedy": parent_greedy, "greedy_disagreement": int(candidate_greedy != parent_greedy), "raw_entropy": float(-np.sum(candidate[legal] * np.log(candidate[legal]))), "source_entropy": float(-np.sum(parent[legal] * np.log(parent[legal]))), "kl_raw_source": float(np.sum(candidate[legal] * np.log(candidate[legal] / parent[legal]))), "kl_source_raw": float(np.sum(parent[legal] * np.log(parent[legal] / candidate[legal]))), "total_variation": float(0.5 * np.sum(np.abs(candidate - parent))), "raw_greedy_probability": float(candidate[candidate_greedy]), "source_greedy_probability": float(parent[parent_greedy])}
            rows.append(row)
            output.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    partitions = defaultdict(list)
    for row in rows: partitions[f"street{row['street']}_seat{row['seat']}"] .append(row)
    summary = {key: helpers.summarize(value) for key, value in sorted(partitions.items())}
    supported = {key: value for key, value in summary.items() if value["states"] >= 100}
    overall = helpers.summarize(rows)
    passed = overall["total_variation"] <= 0.01 and overall["greedy_disagreement_rate"] <= 0.01 and all(value["total_variation"] <= 0.025 and value["greedy_disagreement_rate"] <= 0.05 for value in supported.values())
    decision = "ADMIT_INDEPENDENT_GREEDY_FRESH5K" if passed else "PARENT_STATE_PRESERVATION_GATE_NOT_PASSED"
    analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "states": len(rows), "overall": overall, "partitions": summary, "network_calls": 0, "new_training_hands": 0, "evaluation_hands": len(rows) * 2, "slumbot_hands": 0, "goal_achieved": False, "outcomes_used": False}
    write(BASE / "analysis.json", analysis)
    execution.update({"status": "COMPLETED_PENDING_REVIEW", "evaluation_hands": len(rows) * 2, "states": len(rows), "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_seconds": time.monotonic() - started})
    write(BASE / "execution.json", execution)
    update("--artifact", BASE / "state_metrics.jsonl", "--artifact", BASE / "analysis.json", "--count", "new_training_hands=0", "--count", f"evaluation_hands={len(rows) * 2}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    print(json.dumps({"decision": decision, "states": len(rows), "overall_tv": overall["total_variation"], "greedy_disagreement": overall["greedy_disagreement_rate"], "max_partition_tv": max(value["total_variation"] for value in supported.values())}, sort_keys=True))


if __name__ == "__main__": main()

