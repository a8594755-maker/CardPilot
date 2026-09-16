from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
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


CORPUS = (
    ROOT
    / "research/experiments/v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901"
)
EXPECTED_PARENT_SHA256 = (
    "66c2254d96e36710c1b326d17026099e6ccabdec70d8e2333cfbef26a63c4a6c"
)


def probabilities(model, observations, device: str, batch_size: int = 512):
    output = []
    with torch.no_grad():
        for start in range(0, len(observations), batch_size):
            batch = observations[start : start + batch_size]
            tensors = [
                torch.as_tensor(
                    np.stack([row[key] for row in batch]),
                    dtype=torch.float32,
                    device=device,
                )
                for key in ("card_info", "action_info", "extra_info", "legal_mask")
            ]
            logits, _ = model(*tensors)
            vectors = logits.detach().cpu().numpy().astype(np.float64)
            for vector, row in zip(vectors, batch):
                legal = np.flatnonzero(row["legal_mask"])
                if not np.isfinite(vector[legal]).all():
                    raise ValueError("non-finite legal policy logit")
                weights = np.exp(vector[legal] - np.max(vector[legal]))
                result = np.zeros(9, dtype=np.float64)
                result[legal] = weights / weights.sum()
                output.append(result)
    return np.asarray(output)


def class_mass(probs):
    return np.stack(
        (probs[:, 0], probs[:, 1], probs[:, 2:8].sum(axis=1), probs[:, 8]),
        axis=1,
    )


def greedy_class(probs):
    action = np.argmax(probs, axis=1)
    return np.where(action == 0, 0, np.where(action == 1, 1, np.where(action == 8, 3, 2)))


def context_summary(mask, parent_probs, control_probs, treatment_probs):
    if not np.any(mask):
        raise ValueError("empty evaluation context")
    result = {"states": int(mask.sum())}
    for name, probs in (
        ("parent", parent_probs),
        ("control", control_probs),
        ("treatment", treatment_probs),
    ):
        mass = class_mass(probs[mask])
        greedy = greedy_class(probs[mask])
        result[name] = {
            "mean_class_mass_fold_call_raise_allin": mass.mean(axis=0).tolist(),
            "greedy_class_frequency_fold_call_raise_allin": [
                float(np.mean(greedy == index)) for index in range(4)
            ],
        }
    parent = parent_probs[mask]
    control = control_probs[mask]
    treatment = treatment_probs[mask]
    result["control_vs_parent"] = {
        "mean_total_variation": float(0.5 * np.abs(control - parent).sum(axis=1).mean()),
        "greedy_disagreement": float(np.mean(np.argmax(control, axis=1) != np.argmax(parent, axis=1))),
    }
    result["treatment_vs_parent"] = {
        "mean_total_variation": float(0.5 * np.abs(treatment - parent).sum(axis=1).mean()),
        "greedy_disagreement": float(np.mean(np.argmax(treatment, axis=1) != np.argmax(parent, axis=1))),
    }
    result["treatment_vs_control"] = {
        "mean_total_variation": float(0.5 * np.abs(treatment - control).sum(axis=1).mean()),
        "greedy_disagreement": float(np.mean(np.argmax(treatment, axis=1) != np.argmax(control, axis=1))),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--treatment", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()

    record = json.loads((CORPUS / "experiment.json").read_text(encoding="utf-8-sig"))
    review = json.loads((CORPUS / "reviewed_analysis.json").read_text(encoding="utf-8-sig"))
    audit = json.loads((CORPUS / "combined_audit.json").read_text(encoding="utf-8-sig"))
    if record["status"] != "COMPLETED" or review["status"] != "PASS" or audit["status"] != "PASS":
        raise ValueError("source corpus evidence is not complete and audited")

    observations = []
    metadata = []
    input_hands = []
    for session in range(1, 9):
        path = CORPUS / "sessions" / f"s{session:02d}" / "hands.jsonl"
        input_hands.append({"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path)})
        for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hand = json.loads(line)
            if hand["successful_hand"] != hand_line or hand["model_sha256"] != EXPECTED_PARENT_SHA256:
                raise ValueError("source corpus identity or contiguity mismatch")
            for decision_index, decision in enumerate(hand["decisions"]):
                response = decision["response"]
                state = from_external(
                    response["action"], response["hole_cards"], response.get("board", []), response["client_pos"]
                )
                obs, _ = observation(state, include_position=False)
                if decision["legal_mask"] != obs["legal_mask"].tolist():
                    raise ValueError("source corpus legal-mask replay mismatch")
                observations.append(obs)
                metadata.append(
                    {"session": session, "hand": hand_line, "decision": decision_index, "street": int(state.street)}
                )

    cards = np.stack([row["card_info"] for row in observations])
    actions = np.stack([row["action_info"] for row in observations])
    postflop, sb_open, bb_vs_open = preflop_context_masks(cards, actions)
    masks = {
        "all": np.ones(len(observations), dtype=bool),
        "postflop": postflop,
        "sb_open": sb_open,
        "bb_vs_open": bb_vs_open,
    }

    parent, _, parent_sha = load_policy(args.parent, args.device)
    control, _, control_sha = load_policy(args.control, args.device)
    treatment, _, treatment_sha = load_policy(args.treatment, args.device)
    if parent_sha != EXPECTED_PARENT_SHA256:
        raise ValueError("unexpected frozen parent SHA256")
    parent_probs = probabilities(parent, observations, args.device)
    control_probs = probabilities(control, observations, args.device)
    treatment_probs = probabilities(treatment, observations, args.device)

    contexts = {
        name: context_summary(mask, parent_probs, control_probs, treatment_probs)
        for name, mask in masks.items()
    }
    raw_path = output / "state_metrics.jsonl"
    with raw_path.open("x", encoding="utf-8", newline="\n") as handle:
        parent_mass = class_mass(parent_probs)
        control_mass = class_mass(control_probs)
        treatment_mass = class_mass(treatment_probs)
        for index, meta in enumerate(metadata):
            context = (
                "postflop" if postflop[index] else "sb_open" if sb_open[index] else "bb_vs_open" if bb_vs_open[index] else "other_preflop"
            )
            row = {
                **meta,
                "context": context,
                "parent_class_mass": parent_mass[index].tolist(),
                "control_class_mass": control_mass[index].tolist(),
                "treatment_class_mass": treatment_mass[index].tolist(),
                "parent_greedy_class": int(greedy_class(parent_probs[index : index + 1])[0]),
                "control_greedy_class": int(greedy_class(control_probs[index : index + 1])[0]),
                "treatment_greedy_class": int(greedy_class(treatment_probs[index : index + 1])[0]),
                "control_parent_tv": float(0.5 * np.abs(control_probs[index] - parent_probs[index]).sum()),
                "treatment_parent_tv": float(0.5 * np.abs(treatment_probs[index] - parent_probs[index]).sum()),
                "treatment_control_tv": float(0.5 * np.abs(treatment_probs[index] - control_probs[index]).sum()),
            }
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")

    sb = contexts["sb_open"]
    bb = contexts["bb_vs_open"]
    overall = contexts["all"]["treatment_vs_parent"]
    post = contexts["postflop"]["treatment_vs_control"]
    gate = {
        "sb_raise_mass_reduced": sb["treatment"]["mean_class_mass_fold_call_raise_allin"][2] < sb["control"]["mean_class_mass_fold_call_raise_allin"][2],
        "sb_greedy_raise_frequency_not_increased": sb["treatment"]["greedy_class_frequency_fold_call_raise_allin"][2] <= sb["control"]["greedy_class_frequency_fold_call_raise_allin"][2],
        "bb_vs_open_raise_mass_reduced": bb["treatment"]["mean_class_mass_fold_call_raise_allin"][2] < bb["control"]["mean_class_mass_fold_call_raise_allin"][2],
        "bb_vs_open_greedy_raise_frequency_not_increased": bb["treatment"]["greedy_class_frequency_fold_call_raise_allin"][2] <= bb["control"]["greedy_class_frequency_fold_call_raise_allin"][2],
        "postflop_treatment_control_tv_at_most_0_005": post["mean_total_variation"] <= 0.005,
        "overall_treatment_parent_tv_at_most_0_02": overall["mean_total_variation"] <= 0.02,
        "overall_treatment_parent_disagreement_at_most_0_02": overall["greedy_disagreement"] <= 0.02,
    }
    gate["passed"] = all(gate.values())
    summary = {
        "schema": "cardpilot.contextual_preflop_prior_mechanism.v1",
        "status": "COMPLETED",
        "states": len(observations),
        "policy_queries": 3 * len(observations),
        "checkpoint_sha256": {"parent": parent_sha, "control": control_sha, "treatment": treatment_sha},
        "contexts": contexts,
        "gate": gate,
        "input_hands": input_hands,
        "state_metrics_sha256": sha256_file(raw_path),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
