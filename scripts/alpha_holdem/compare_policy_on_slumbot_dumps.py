"""Compare two frozen policies on reconstructed observations from Slumbot dumps.

This measures the behavioral effect that policy-distribution KL can hide when
deployment is greedy argmax.  The comparison is descriptive: dump observations
come from the evaluated policy's state distribution and do not estimate EV.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(THIS_DIR))

from alpha_holdem.network import AlphaHoldemNet, CRITIC_V1, CRITIC_V2
from offline_slumbot_awr import (
    ACTION_SHAPE,
    CARD_SHAPE,
    NUM_ACTIONS,
    reservoir_rows,
    sha256_path,
)
from play_slumbot import (
    checkpoint_context_action_override,
    checkpoint_preflop_range_override,
    parse_action,
)


def load_model(path: Path, device: str) -> tuple[AlphaHoldemNet, dict[str, Any]]:
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    state = checkpoint["model"]
    norm_layer = str(checkpoint.get("norm_layer", "bn"))
    separate_preflop_head = bool(
        checkpoint.get("separate_preflop_head")
        or (checkpoint.get("config") or {}).get("separate_preflop_head")
        or (checkpoint.get("config") or {}).get("separate_preflop_head_only")
    )
    postflop_adapter_hidden = (
        int(state["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state
        else 0
    )
    position_adapter_hidden = (
        int(state["position_policy_adapters.0.0.weight"].shape[0])
        if "position_policy_adapters.0.0.weight" in state
        else 0
    )
    critic_contract = (
        CRITIC_V2 if "value_head.0.weight" in state else CRITIC_V1
    )
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=norm_layer,
        separate_preflop_head=separate_preflop_head,
        postflop_adapter_hidden=postflop_adapter_hidden,
        position_adapter_hidden=position_adapter_hidden,
        critic_contract=critic_contract,
    ).to(device)
    model.eval()
    with torch.no_grad():
        model(
            torch.zeros(2, *CARD_SHAPE, device=device),
            torch.zeros(2, *ACTION_SHAPE, device=device),
            torch.zeros(
                2,
                3 if position_adapter_hidden > 0 else 2,
                device=device,
            ),
        )
    model.load_state_dict(state)
    model.policy_range_override = checkpoint.get("policy_range_override")
    model.policy_context_override = checkpoint.get("policy_context_override")
    model.eval()
    return model, checkpoint


def risk_bucket(value: float) -> str:
    if value < 2.0:
        return "lt2"
    if value < 5.0:
        return "2to5"
    if value < 20.0:
        return "5to20"
    if value < 50.0:
        return "20to50"
    return "ge50"


def summarize(indices: list[int], metrics: dict[str, np.ndarray]) -> dict[str, Any]:
    if not indices:
        return {"rows": 0}
    selection = np.asarray(indices, dtype=np.int64)
    changed = metrics["changed"][selection]
    return {
        "rows": int(len(indices)),
        "argmax_disagreement_rate": float(changed.mean()),
        "source_to_candidate_kl_mean": float(metrics["kl"][selection].mean()),
        "total_variation_mean": float(metrics["tv"][selection].mean()),
        "source_matches_logged_rate": float(
            metrics["source_matches_logged"][selection].mean()
        ),
        "candidate_matches_logged_rate": float(
            metrics["candidate_matches_logged"][selection].mean()
        ),
        "source_margin_mean": float(metrics["source_margin"][selection].mean()),
        "candidate_margin_mean": float(
            metrics["candidate_margin"][selection].mean()
        ),
        "logged_return_bb_mean_per_decision": float(
            metrics["return_bb"][selection].mean()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkpoint", required=True)
    parser.add_argument("--candidate-checkpoint", required=True)
    parser.add_argument("--dumps", nargs="+", required=True)
    parser.add_argument("--actor", choices=("hero", "opp"), default="hero")
    parser.add_argument("--obs-version", choices=("v4", "v55"), default="v4")
    parser.add_argument(
        "--raise-action-mapping",
        choices=(
            "legacy_total_over_pot",
            "preflop_pot_fraction_v2",
            "pot_fraction_v2",
        ),
        default="legacy_total_over_pot",
    )
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    dump_paths = [Path(value).resolve() for value in args.dumps]
    missing = [str(path) for path in dump_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing dump files: {missing}")
    rows, ingest = reservoir_rows(
        files=dump_paths,
        max_rows=args.max_rows,
        seed=args.seed,
        obs_version=args.obs_version,
        street_min=0,
        street_max=3,
        actor=args.actor,
        raise_action_mapping=args.raise_action_mapping,
    )
    if not rows:
        raise RuntimeError("no reconstructable observations")

    source_path = Path(args.source_checkpoint).resolve()
    candidate_path = Path(args.candidate_checkpoint).resolve()
    source, source_checkpoint = load_model(source_path, args.device)
    candidate, candidate_checkpoint = load_model(candidate_path, args.device)

    arrays: dict[str, list[np.ndarray]] = defaultdict(list)
    with torch.no_grad():
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start : start + args.batch_size]
            cards = torch.from_numpy(
                np.stack([row["card"] for row in batch])
            ).to(args.device)
            actions = torch.from_numpy(
                np.stack([row["action"] for row in batch])
            ).to(args.device)
            extras = torch.from_numpy(
                np.stack([row["extra"] for row in batch])
            ).to(args.device)
            positions = torch.tensor(
                [int(row["position"]) for row in batch],
                dtype=extras.dtype,
                device=args.device,
            ).unsqueeze(1)
            legal = torch.from_numpy(
                np.stack([row["legal"] for row in batch])
            ).to(args.device)
            source_extras = (
                torch.cat([extras, positions], dim=1)
                if int(getattr(source, "position_adapter_hidden", 0)) > 0
                else extras
            )
            candidate_extras = (
                torch.cat([extras, positions], dim=1)
                if int(getattr(candidate, "position_adapter_hidden", 0)) > 0
                else extras
            )
            source_logits, _ = source(
                cards,
                actions,
                source_extras,
                legal,
            )
            candidate_logits, _ = candidate(
                cards,
                actions,
                candidate_extras,
                legal,
            )
            source_probs = F.softmax(source_logits, dim=-1)
            candidate_probs = F.softmax(candidate_logits, dim=-1)
            source_argmax = source_probs.argmax(dim=-1)
            candidate_argmax = candidate_probs.argmax(dim=-1)
            source_top2 = source_probs.topk(k=2, dim=-1).values
            candidate_top2 = candidate_probs.topk(k=2, dim=-1).values
            arrays["source_argmax"].append(source_argmax.cpu().numpy())
            arrays["candidate_argmax"].append(candidate_argmax.cpu().numpy())
            arrays["kl"].append(
                (
                    source_probs
                    * (
                        source_probs.clamp_min(1e-12).log()
                        - candidate_probs.clamp_min(1e-12).log()
                    )
                )
                .sum(dim=-1)
                .cpu()
                .numpy()
            )
            arrays["tv"].append(
                (0.5 * (source_probs - candidate_probs).abs().sum(dim=-1))
                .cpu()
                .numpy()
            )
            arrays["source_margin"].append(
                (source_top2[:, 0] - source_top2[:, 1]).cpu().numpy()
            )
            arrays["candidate_margin"].append(
                (candidate_top2[:, 0] - candidate_top2[:, 1]).cpu().numpy()
            )

    source_argmax = np.concatenate(arrays["source_argmax"])
    candidate_argmax = np.concatenate(arrays["candidate_argmax"])
    if (
        getattr(candidate, "policy_range_override", None)
        or getattr(candidate, "policy_context_override", None)
    ):
        for index, row in enumerate(rows):
            state = parse_action(str(row["action_str_before"]))
            if state.get("error"):
                continue
            legal_mask = torch.from_numpy(
                np.asarray(row["legal"], dtype=np.float32)
            ).unsqueeze(0)
            overridden = checkpoint_preflop_range_override(
                candidate,
                list(row["hole_cards"]),
                state,
                int(row["position"]),
                legal_mask,
                int(candidate_argmax[index]),
            )
            candidate_argmax[index] = checkpoint_context_action_override(
                candidate,
                list(row["hole_cards"]),
                list(row["board"]),
                state,
                int(row["position"]),
                legal_mask,
                int(overridden),
            )
    logged = np.asarray([row["selected"] for row in rows], dtype=np.int64)
    metrics = {
        "changed": source_argmax != candidate_argmax,
        "kl": np.concatenate(arrays["kl"]),
        "tv": np.concatenate(arrays["tv"]),
        "source_margin": np.concatenate(arrays["source_margin"]),
        "candidate_margin": np.concatenate(arrays["candidate_margin"]),
        "source_matches_logged": source_argmax == logged,
        "candidate_matches_logged": candidate_argmax == logged,
        "return_bb": np.asarray(
            [float(row["return_bb"]) for row in rows],
            dtype=np.float64,
        ),
    }

    group_indices: dict[str, list[int]] = defaultdict(list)
    switch_matrix = Counter()
    for index, row in enumerate(rows):
        group_indices[f"street_{int(row['street'])}"].append(index)
        group_indices[f"position_{int(row['position'])}"].append(index)
        group_indices[f"risk_{risk_bucket(float(row['decision_risk_bb']))}"].append(
            index
        )
        switch_matrix[
            f"{int(source_argmax[index])}->{int(candidate_argmax[index])}"
        ] += 1

    changed_indices = np.flatnonzero(metrics["changed"])
    changed_source_margin = metrics["source_margin"][changed_indices]
    hand_rows: dict[tuple[int, ...], dict[str, Any]] = {}
    switch_returns: dict[str, list[float]] = defaultdict(list)
    for index, row in enumerate(rows):
        hand_key = tuple(row["hand_key"])
        hand = hand_rows.setdefault(
            hand_key,
            {
                "return_bb": float(row["return_bb"]),
                "has_switch": False,
                "switches": 0,
            },
        )
        if bool(metrics["changed"][index]):
            hand["has_switch"] = True
            hand["switches"] += 1
        switch_key = f"{int(source_argmax[index])}->{int(candidate_argmax[index])}"
        switch_returns[switch_key].append(float(row["return_bb"]))

    switched_hands = [hand for hand in hand_rows.values() if hand["has_switch"]]
    unchanged_hands = [hand for hand in hand_rows.values() if not hand["has_switch"]]

    def hand_summary(hands: list[dict[str, Any]]) -> dict[str, Any]:
        returns = np.asarray(
            [float(hand["return_bb"]) for hand in hands],
            dtype=np.float64,
        )
        return {
            "hands": int(len(hands)),
            "total_bb": float(returns.sum()) if len(hands) else 0.0,
            "mean_bb_per_hand": float(returns.mean()) if len(hands) else None,
        }

    report = {
        "schema_version": "policy.slumbot_dump_comparison.v1",
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256_path(source_path),
        "source_iteration": source_checkpoint.get("iteration"),
        "source_total_hands": source_checkpoint.get("total_hands"),
        "candidate_checkpoint": str(candidate_path),
        "candidate_checkpoint_sha256": sha256_path(candidate_path),
        "candidate_iteration": candidate_checkpoint.get("iteration"),
        "candidate_total_hands": candidate_checkpoint.get("total_hands"),
        "actor": args.actor,
        "obs_version": args.obs_version,
        "raise_action_mapping": args.raise_action_mapping,
        "dump_files": [
            {"path": str(path), "sha256": sha256_path(path)}
            for path in dump_paths
        ],
        "ingest": ingest,
        "overall": summarize(list(range(len(rows))), metrics),
        "groups": {
            key: summarize(indices, metrics)
            for key, indices in sorted(group_indices.items())
        },
        "changed_rows": {
            "rows": int(changed_indices.size),
            "source_margin_mean": (
                float(changed_source_margin.mean())
                if changed_indices.size
                else None
            ),
            "source_margin_p50": (
                float(np.quantile(changed_source_margin, 0.50))
                if changed_indices.size
                else None
            ),
            "source_margin_p90": (
                float(np.quantile(changed_source_margin, 0.90))
                if changed_indices.size
                else None
            ),
        },
        "changed_row_details": [
            {
                "row_index": int(index),
                "hand_key": list(rows[int(index)]["hand_key"]),
                "street": int(rows[int(index)]["street"]),
                "position": int(rows[int(index)]["position"]),
                "decision_risk_bb": float(
                    rows[int(index)]["decision_risk_bb"]
                ),
                "logged_return_bb": float(rows[int(index)]["return_bb"]),
                "source_action": int(source_argmax[int(index)]),
                "candidate_action": int(candidate_argmax[int(index)]),
                "logged_action": int(logged[int(index)]),
                "source_margin": float(metrics["source_margin"][int(index)]),
                "candidate_margin": float(
                    metrics["candidate_margin"][int(index)]
                ),
                "bucket": list(rows[int(index)]["bucket"]),
            }
            for index in changed_indices
        ],
        "candidate_trajectory_hand_outcomes": {
            "note": (
                "Associational only: hands are grouped by whether at least one "
                "candidate-trajectory decision differs from the source greedy "
                "action."
            ),
            "all_reconstructed": hand_summary(list(hand_rows.values())),
            "with_policy_switch": hand_summary(switched_hands),
            "without_policy_switch": hand_summary(unchanged_hands),
        },
        "switch_matrix": dict(
            sorted(switch_matrix.items(), key=lambda item: (-item[1], item[0]))
        ),
        "switch_logged_return": {
            key: {
                "rows": len(values),
                "mean_return_bb": float(np.mean(values)),
                "total_return_bb_decision_weighted": float(np.sum(values)),
            }
            for key, values in sorted(
                switch_returns.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        },
        "note": (
            "Descriptive behavior comparison on candidate-encountered states; "
            "not an EV estimate."
        ),
    }
    output = Path(args.out_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["overall"], indent=2, sort_keys=True))
    print(json.dumps(report["groups"], indent=2, sort_keys=True))
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
