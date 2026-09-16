from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.execution_v6 import load_policy, sha256_file  # noqa: E402
from alpha_holdem.policy_contract_v6 import from_external, observation  # noqa: E402
from alpha_holdem.train_mp3_hybrid_h1 import preflop_context_masks  # noqa: E402


ENGINE = (
    ROOT
    / "research/experiments/v6-contextual-preflop-prior-mechanism-smoke-20260901/evaluate_mechanism.py"
)
PILOT = ROOT / "research/experiments/v6-preflop-head-only-context-prior-65k-pilot-20260901"
CORPUS = ROOT / "research/experiments/v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901"
PARENT = ROOT / "research/experiments/v6-procedural-iter32-soup-preservation-20260901/frozen/treatment.pt"
PARENT_SHA256 = "66c2254d96e36710c1b326d17026099e6ccabdec70d8e2333cfbef26a63c4a6c"
ITERATIONS = tuple(range(2, 17, 2))


def checkpoint(arm: str, iteration: int) -> Path:
    matches = list((PILOT / arm / "checkpoints").glob(f"checkpoint_iter{iteration:06d}_hands*.pt"))
    if len(matches) != 1:
        raise ValueError(f"expected one {arm} checkpoint at iteration {iteration}, got {matches}")
    return matches[0]


def load_observations():
    record = json.loads((CORPUS / "experiment.json").read_text(encoding="utf-8-sig"))
    review = json.loads((CORPUS / "reviewed_analysis.json").read_text(encoding="utf-8-sig"))
    audit = json.loads((CORPUS / "combined_audit.json").read_text(encoding="utf-8-sig"))
    if record["status"] != "COMPLETED" or review["status"] != "PASS" or audit["status"] != "PASS":
        raise ValueError("source corpus is not complete and audited")
    observations, input_hands = [], []
    for session in range(1, 9):
        path = CORPUS / "sessions" / f"s{session:02d}" / "hands.jsonl"
        input_hands.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)})
        for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hand = json.loads(line)
            if hand["successful_hand"] != hand_line or hand["model_sha256"] != PARENT_SHA256:
                raise ValueError("source corpus identity or contiguity mismatch")
            for decision in hand["decisions"]:
                response = decision["response"]
                state = from_external(
                    response["action"], response["hole_cards"], response.get("board", []), response["client_pos"]
                )
                obs, _ = observation(state, include_position=False)
                if decision["legal_mask"] != obs["legal_mask"].tolist():
                    raise ValueError("source legal-mask replay mismatch")
                observations.append(obs)
    return observations, input_hands


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    started = time.time()
    spec = importlib.util.spec_from_file_location("mechanism_engine", ENGINE)
    engine = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(engine)

    observations, input_hands = load_observations()
    cards = np.stack([row["card_info"] for row in observations])
    actions = np.stack([row["action_info"] for row in observations])
    postflop, sb_open, bb_vs_open = preflop_context_masks(cards, actions)
    masks = {
        "all": np.ones(len(observations), dtype=bool),
        "postflop": postflop,
        "sb_open": sb_open,
        "bb_vs_open": bb_vs_open,
    }
    parent_model, _, parent_sha = load_policy(PARENT, args.device)
    if parent_sha != PARENT_SHA256:
        raise ValueError("parent SHA256 mismatch")
    parent_probs = engine.probabilities(parent_model, observations, args.device)
    del parent_model

    arrays = {
        "parent": parent_probs,
        "postflop_mask": postflop.astype(np.uint8),
        "sb_open_mask": sb_open.astype(np.uint8),
        "bb_vs_open_mask": bb_vs_open.astype(np.uint8),
    }
    curve = []
    for iteration in ITERATIONS:
        paths = {arm: checkpoint(arm, iteration) for arm in ("control", "treatment")}
        loaded = {}
        hashes = {}
        for arm, path in paths.items():
            model, _, hashes[arm] = load_policy(path, args.device)
            loaded[arm] = engine.probabilities(model, observations, args.device)
            del model
        control_probs = loaded["control"]
        treatment_probs = loaded["treatment"]
        arrays[f"control_iter{iteration:02d}"] = control_probs
        arrays[f"treatment_iter{iteration:02d}"] = treatment_probs
        contexts = {
            name: engine.context_summary(mask, parent_probs, control_probs, treatment_probs)
            for name, mask in masks.items()
        }
        postflop_exact = (
            np.array_equal(control_probs[postflop], parent_probs[postflop])
            and np.array_equal(treatment_probs[postflop], parent_probs[postflop])
        )
        target_distance_improved = all(
            abs(contexts[context]["treatment"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            < abs(contexts[context]["control"]["mean_class_mass_fold_call_raise_allin"][2] - target)
            for context, target in (("sb_open", 0.63), ("bb_vs_open", 0.18))
        )
        drift = contexts["all"]["treatment_vs_parent"]
        eligible = (
            postflop_exact
            and target_distance_improved
            and drift["mean_total_variation"] <= 0.05
            and drift["greedy_disagreement"] <= 0.05
        )
        curve.append(
            {
                "iteration": iteration,
                "checkpoint_paths": {arm: str(path.relative_to(ROOT)) for arm, path in paths.items()},
                "checkpoint_sha256": hashes,
                "contexts": contexts,
                "postflop_exact": bool(postflop_exact),
                "contextual_target_distance_improved": bool(target_distance_improved),
                "eligible": bool(eligible),
            }
        )
        torch.cuda.empty_cache()

    eligible = [row for row in curve if row["eligible"]]
    selected = eligible[-1] if eligible else None
    raw_path = BASE / "state_probabilities.npz"
    np.savez_compressed(raw_path, **arrays)
    summary = {
        "schema": "cardpilot.contextual_preflop_prior_dose_curve.v1",
        "status": "COMPLETED",
        "iterations": list(ITERATIONS),
        "selection_rule": "latest even iteration with postflop exact, contextual target distance improved, overall parent TV<=0.05 and greedy disagreement<=0.05",
        "selected_iteration": selected["iteration"] if selected else None,
        "selected_control_checkpoint": selected["checkpoint_paths"]["control"] if selected else None,
        "selected_treatment_checkpoint": selected["checkpoint_paths"]["treatment"] if selected else None,
        "selected_checkpoint_sha256": selected["checkpoint_sha256"] if selected else None,
        "states": len(observations),
        "endpoint_state_comparisons": len(observations) * len(ITERATIONS),
        "policy_queries": len(observations) * (1 + 2 * len(ITERATIONS)),
        "parent_sha256": parent_sha,
        "curve": curve,
        "input_hands": input_hands,
        "state_probabilities_sha256": sha256_file(raw_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (BASE / "dose_curve.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "selected_iteration": summary["selected_iteration"],
        "curve": [
            {
                "iteration": row["iteration"],
                "tv": row["contexts"]["all"]["treatment_vs_parent"]["mean_total_variation"],
                "disagreement": row["contexts"]["all"]["treatment_vs_parent"]["greedy_disagreement"],
                "eligible": row["eligible"],
            }
            for row in curve
        ],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
