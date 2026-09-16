"""Materialize and outcome-free audit one fixed conservative actor model soup."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
SOURCE = ROOT / "models/baseline/standard10/latest.pt"
CORPUS = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
PARENT_WEIGHT, SOURCE_WEIGHT = 0.75, 0.25
ACTOR_NAMES = ("policy_head.weight", "policy_head.bias", "preflop_policy_head.weight", "preflop_policy_head.bias")
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from alpha_holdem.execution_v6 import load_policy
from alpha_holdem.policy_contract_v6 import from_external, observation
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): atomic_json(Path(path), value)
def update(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def record(command): update("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def interpolate(parent, source, actor_names=ACTOR_NAMES):
    if set(parent) != set(source): raise ValueError("state keys differ")
    result = {name: tensor.detach().cpu().clone() for name, tensor in parent.items()}
    for name in actor_names:
        result[name] = (parent[name].detach().cpu() * PARENT_WEIGHT + source[name].detach().cpu() * SOURCE_WEIGHT).to(parent[name].dtype)
    return result


def probabilities(model, observations, batch_size=512):
    output = []
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
                probs = np.zeros(9, dtype=np.float64); probs[legal] = weights / weights.sum(); output.append(probs)
    return np.asarray(output)


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "frozen", "state_metrics.jsonl")):
        raise ValueError("fixed one-shot gate")
    assert sha(PARENT) == PARENT_SHA and sha(SOURCE) == SOURCE_SHA
    assert read(CORPUS / "experiment.json")["status"] == "COMPLETED"
    assert read(CORPUS / "reviewed_analysis.json")["status"] == "PASS"
    assert read(CORPUS / "combined_audit.json")["status"] == "PASS"
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
                 "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0, "network_calls": 0}
    write(BASE / "execution.json", execution); update("--status", "RUNNING")
    try:
        code = BASE / "execution_code"; code.mkdir()
        paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
        paths += ["research/experiment_log.py"] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
        capture_code_provenance(ROOT, code, paths)
        for relative in paths:
            target = code / "source_files" / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / relative, target)
        update("--artifact", code / "source_manifest.json", "--artifact", code / "code.patch")
        test = ["-m", "pytest", str(BASE / "test_gate.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test); subprocess.run([sys.executable, *test], cwd=ROOT, check=True); update("--artifact", BASE / "tests.xml")
        parent_checkpoint = torch.load(PARENT, map_location="cpu", weights_only=False)
        source_checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
        candidate = {key: value for key, value in parent_checkpoint.items()}
        candidate["model"] = interpolate(parent_checkpoint["model"], source_checkpoint["model"])
        candidate["run_id"] = "v6_standard10_parent_actor_soup_075_025_20260901"
        candidate["deployed_actor_variant"] = "standard10_parent_actor_weight_soup"
        candidate["weight_soup"] = {"schema": "cardpilot.actor_weight_soup.v1", "parent_sha256": PARENT_SHA,
                                    "source_sha256": SOURCE_SHA, "parent_weight": PARENT_WEIGHT,
                                    "source_weight": SOURCE_WEIGHT, "actor_tensors": list(ACTOR_NAMES)}
        candidate.setdefault("config", {})["deployed_actor_variant"] = candidate["deployed_actor_variant"]
        (BASE / "frozen").mkdir(); torch.save(candidate, BASE / "frozen/candidate.pt")
        frozen = torch.load(BASE / "frozen/candidate.pt", map_location="cpu", weights_only=False)
        assert all(torch.equal(frozen["model"][name], parent_checkpoint["model"][name]) for name in frozen["model"] if name not in ACTOR_NAMES)
        for name in ACTOR_NAMES:
            expected = (parent_checkpoint["model"][name] * PARENT_WEIGHT + source_checkpoint["model"][name] * SOURCE_WEIGHT).to(parent_checkpoint["model"][name].dtype)
            assert torch.equal(frozen["model"][name], expected)
        candidate_sha = sha(BASE / "frozen/candidate.pt")
        inputs, observations, metadata = [], [], []
        for session in range(1, 9):
            path = CORPUS / "sessions" / f"s{session:02d}/hands.jsonl"; inputs.append({"path": str(path), "sha256": sha(path)})
            for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                hand = json.loads(line); assert hand["successful_hand"] == hand_line and hand["model_sha256"] == PARENT_SHA
                for decision_index, decision in enumerate(hand["decisions"]):
                    response = decision["response"]
                    state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
                    obs, _ = observation(state, include_position=False); assert decision["legal_mask"] == obs["legal_mask"].tolist()
                    observations.append(obs); metadata.append({"session": session, "hand": hand_line, "decision": decision_index,
                                                               "street": int(state.street), "seat": int(response["client_pos"])})
        candidate_model, _, loaded_candidate_sha = load_policy(BASE / "frozen/candidate.pt", "cpu")
        parent_model, _, loaded_parent_sha = load_policy(PARENT, "cpu")
        assert loaded_candidate_sha == candidate_sha and loaded_parent_sha == PARENT_SHA
        candidate_probs, parent_probs = probabilities(candidate_model, observations), probabilities(parent_model, observations)
        tvs = 0.5 * np.abs(candidate_probs - parent_probs).sum(axis=1)
        disagreements = np.argmax(candidate_probs, axis=1) != np.argmax(parent_probs, axis=1)
        with (BASE / "state_metrics.jsonl").open("x", encoding="utf-8", newline="\n") as output:
            for meta, tv, disagreement in zip(metadata, tvs, disagreements):
                output.write(json.dumps({**meta, "total_variation": float(tv), "greedy_disagreement": int(disagreement)}, separators=(",", ":")) + "\n")
        mean_tv, disagreement_rate = float(np.mean(tvs)), float(np.mean(disagreements))
        passed = mean_tv <= 0.02 and disagreement_rate <= 0.02
        analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": "ADMIT_SEPARATE_GREEDY_FRESH5K" if passed else "CONSERVATIVE_SOUP_PRESERVATION_NOT_PASSED",
                    "candidate_sha256": candidate_sha, "parent_sha256": PARENT_SHA, "source_sha256": SOURCE_SHA,
                    "states": len(observations), "mean_total_variation": mean_tv, "greedy_disagreement_rate": disagreement_rate,
                    "gate_passed": passed, "input_hands": inputs, "new_training_hands": 0,
                    "evaluation_hands": 2 * len(observations), "slumbot_hands": 0, "network_calls": 0, "goal_achieved": False}
        write(BASE / "analysis.json", analysis)
        execution.update({"status": "COMPLETED_PENDING_REVIEW", "evaluation_hands": analysis["evaluation_hands"],
                          "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_seconds": time.monotonic() - started})
        write(BASE / "execution.json", execution)
        update("--artifact", BASE / "frozen/candidate.pt", "--artifact", BASE / "state_metrics.jsonl", "--artifact", BASE / "analysis.json",
               "--artifact", BASE / "execution.json", "--count", f"evaluation_hands={analysis['evaluation_hands']}",
               "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
        reviewer = [str(BASE / "review_finish.py")]; record(reviewer); subprocess.run([sys.executable, *reviewer], cwd=ROOT, check=True)
        print(json.dumps(analysis, sort_keys=True))
    except BaseException:
        execution.update({"status": "NEEDS_REVIEW", "error": traceback.format_exc(), "finished_at": datetime.now(timezone.utc).isoformat(),
                          "wall_time_seconds": time.monotonic() - started}); write(BASE / "execution.json", execution); update("--artifact", BASE / "execution.json"); raise


if __name__ == "__main__": main()
