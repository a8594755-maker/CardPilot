#!/usr/bin/env python3
"""Offline preflop policy probe for V5 Slumbot evaluation.

This does not call Slumbot. It enumerates all 1,326 two-card private hands for
representative preflop action strings, then compares the model's mean action
probabilities against greedy argmax choices. The goal is to catch cases where a
mixed poker policy has reasonable call/limp probability mass but greedy eval
turns it into a fold/raise-only policy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from alpha_holdem.environment_v55 import NUM_ACTIONS
from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.play_slumbot import (
    action_idx_to_incr,
    build_action_table,
    compute_commitments,
    encode_action_history,
    encode_cards,
    encode_extra,
    guarded_action_probs,
    is_unopened_preflop_start,
    parse_action,
    resolve_obs_version,
)


RANKS = "23456789TJQKA"
SUITS = "cdhs"

CASES = [
    {
        "name": "sb_open_start",
        "action_str": "",
        "client_pos": 1,
        "description": "SB first action preflop, facing the posted BB.",
    },
    {
        "name": "bb_vs_min_open_b200",
        "action_str": "b200",
        "client_pos": 0,
        "description": "BB facing a min-open to 2bb.",
    },
    {
        "name": "bb_vs_open_b300",
        "action_str": "b300",
        "client_pos": 0,
        "description": "BB facing a 3bb open.",
    },
    {
        "name": "sb_vs_3bet_b200_b800",
        "action_str": "b200b800",
        "client_pos": 1,
        "description": "SB facing a BB 3-bet to 8bb after opening to 2bb.",
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def all_hole_combos() -> list[list[str]]:
    cards = [rank + suit for rank in RANKS for suit in SUITS]
    combos: list[list[str]] = []
    for i, first in enumerate(cards):
        for second in cards[i + 1 :]:
            combos.append([first, second])
    return combos


def load_model(checkpoint_path: Path, device: str) -> tuple[AlphaHoldemNet, dict[str, Any]]:
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if not isinstance(checkpoint, dict):
        raise TypeError(f"checkpoint is {type(checkpoint).__name__}, not dict")
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=str(checkpoint.get("norm_layer", "bn"))).to(device)
    model.eval()
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(2, 2, device=device),
        )
    model.load_state_dict(checkpoint["model"])
    model.eval()
    return model, checkpoint


def classify_slot(slot: int) -> str:
    if slot == 0:
        return "fold"
    if slot == 1:
        return "call"
    if slot == 8:
        return "allin"
    return "raise"


def entropy(probs: np.ndarray) -> float:
    clipped = np.clip(probs, 1e-12, 1.0)
    return float(-(clipped * np.log(clipped)).sum())


def evaluate_case(
    model: AlphaHoldemNet,
    obs_version: str,
    device: str,
    case: dict[str, Any],
    holes: list[list[str]],
    batch_size: int,
    guarded_temperature: float,
    guarded_allin_max_spr: float,
    guarded_allin_min_prob: float,
    callguard_min_prob: float,
    callguard_ratio: float,
    callguard_include_open: bool,
) -> dict[str, Any]:
    state = parse_action(str(case["action_str"]))
    if state.get("error"):
        raise ValueError(f"{case['name']} parse failed: {state['error']}")
    if int(state.get("pos", -1)) != int(case["client_pos"]):
        raise ValueError(
            f"{case['name']} is not hero turn: state pos={state.get('pos')} client_pos={case['client_pos']}"
        )

    mask, table = build_action_table(state)
    c = compute_commitments(state)
    stacks = [20_000 - c["hero_total"], 20_000 - c["opp_total"]]
    action_info = encode_action_history(state, int(case["client_pos"]), int(state["pos"]), obs_version=obs_version)
    extra = encode_extra(stacks)

    sum_probs = np.zeros(NUM_ACTIONS, dtype=np.float64)
    sum_guarded_probs = np.zeros(NUM_ACTIONS, dtype=np.float64)
    sum_entropy = 0.0
    greedy_counts = np.zeros(NUM_ACTIONS, dtype=np.int64)
    callguard_counts = np.zeros(NUM_ACTIONS, dtype=np.int64)
    examples: dict[str, list[str]] = {str(i): [] for i in range(NUM_ACTIONS)}
    callguard_examples: dict[str, list[str]] = {str(i): [] for i in range(NUM_ACTIONS)}
    legal_slots = np.where(mask > 0)[0]
    callguard_enabled = (
        int(state.get("st", 0)) == 0
        and bool(mask[1] > 0)
        and (c.get("to_call", 0) > 0 or bool(callguard_include_open))
        and (not is_unopened_preflop_start(state) or bool(callguard_include_open))
    )

    with torch.no_grad():
        for start in range(0, len(holes), batch_size):
            batch_holes = holes[start : start + batch_size]
            cards = np.stack([encode_cards(hole, [], int(state["st"])) for hole in batch_holes]).astype(np.float32)
            actions = np.repeat(action_info[None, ...], len(batch_holes), axis=0).astype(np.float32)
            extras = np.repeat(extra[None, ...], len(batch_holes), axis=0).astype(np.float32)
            masks = np.repeat(mask[None, ...], len(batch_holes), axis=0).astype(np.float32)

            mask_tensor = torch.from_numpy(masks).to(device)
            logits, _ = model(
                torch.from_numpy(cards).to(device),
                torch.from_numpy(actions).to(device),
                torch.from_numpy(extras).to(device),
                mask_tensor,
            )
            probs = F.softmax(logits, dim=-1).cpu().numpy()
            guarded_probs_t = guarded_action_probs(
                F.softmax(logits / max(float(guarded_temperature), 1e-6), dim=-1),
                mask_tensor,
                state,
                allin_max_spr=guarded_allin_max_spr,
                allin_min_prob=guarded_allin_min_prob,
            )
            guarded_probs = guarded_probs_t.cpu().numpy()
            choices = probs.argmax(axis=1)
            callguard_base = probs if (is_unopened_preflop_start(state) and not callguard_include_open) else guarded_probs
            callguard_choices = callguard_base[:, legal_slots].argmax(axis=1)
            callguard_choices = legal_slots[callguard_choices].astype(np.int64)
            if callguard_enabled:
                top_probs = callguard_base[:, legal_slots].max(axis=1)
                choose_call = (
                    (callguard_base[:, 1] >= float(callguard_min_prob))
                    & (callguard_base[:, 1] >= float(callguard_ratio) * top_probs)
                )
                callguard_choices[choose_call] = 1
            sum_probs += probs.sum(axis=0)
            sum_guarded_probs += guarded_probs.sum(axis=0)
            sum_entropy += sum(entropy(row) for row in probs)
            for hole, choice in zip(batch_holes, choices):
                greedy_counts[int(choice)] += 1
                key = str(int(choice))
                if len(examples[key]) < 5:
                    examples[key].append("".join(hole))
            for hole, choice in zip(batch_holes, callguard_choices):
                callguard_counts[int(choice)] += 1
                key = str(int(choice))
                if len(callguard_examples[key]) < 5:
                    callguard_examples[key].append("".join(hole))

    n = len(holes)
    mean_probs = sum_probs / max(n, 1)
    mean_guarded_probs = sum_guarded_probs / max(n, 1)
    greedy_rates = greedy_counts / max(n, 1)
    class_counts: dict[str, int] = {"fold": 0, "call": 0, "raise": 0, "allin": 0}
    callguard_class_counts: dict[str, int] = {"fold": 0, "call": 0, "raise": 0, "allin": 0}
    class_prob_mass: dict[str, float] = {"fold": 0.0, "call": 0.0, "raise": 0.0, "allin": 0.0}
    guarded_class_prob_mass: dict[str, float] = {"fold": 0.0, "call": 0.0, "raise": 0.0, "allin": 0.0}
    for slot in range(NUM_ACTIONS):
        cls = classify_slot(slot)
        class_counts[cls] += int(greedy_counts[slot])
        callguard_class_counts[cls] += int(callguard_counts[slot])
        class_prob_mass[cls] += float(mean_probs[slot])
        guarded_class_prob_mass[cls] += float(mean_guarded_probs[slot])

    statuses: list[dict[str, str]] = []
    if mask[1] <= 0:
        statuses.append({"status": "FAIL", "name": "call_mask", "detail": "slot 1 is not legal"})
    else:
        statuses.append({"status": "PASS", "name": "call_mask", "detail": "slot 1 is legal"})

    if float(mean_probs[1]) >= 0.10 and float(greedy_rates[1]) <= 0.01:
        statuses.append(
            {
                "status": "WARN",
                "name": "argmax_suppresses_call",
                "detail": f"mean call prob={mean_probs[1]:.3f}, greedy call rate={greedy_rates[1]:.3f}",
            }
        )

    if case["name"] == "sb_open_start" and float(greedy_rates[0]) > 0.40:
        statuses.append(
            {
                "status": "WARN",
                "name": "sb_open_overfold_greedy",
                "detail": f"greedy SB fold rate={greedy_rates[0]:.3f}",
            }
        )
    if case["name"] == "sb_open_start" and float(greedy_rates[1]) > 0.50:
        statuses.append(
            {
                "status": "WARN",
                "name": "sb_open_overlimp_greedy",
                "detail": f"greedy SB limp/call rate={greedy_rates[1]:.3f}",
            }
        )
    if case["name"] == "sb_open_start" and float(greedy_rates[2:8].sum()) < 0.20:
        statuses.append(
            {
                "status": "WARN",
                "name": "sb_open_underraise_greedy",
                "detail": f"greedy SB raise rate={greedy_rates[2:8].sum():.3f}",
            }
        )
    if case["name"] == "sb_open_start" and float(greedy_rates[8]) > 0.02:
        statuses.append(
            {
                "status": "WARN",
                "name": "sb_open_jam_rate_greedy",
                "detail": f"greedy SB open-jam rate={greedy_rates[8]:.3f}",
            }
        )
    if case["name"].startswith("bb_vs_") and float(greedy_rates[0]) > 0.60:
        statuses.append(
            {
                "status": "WARN",
                "name": "bb_defense_overfold_greedy",
                "detail": f"greedy BB fold rate={greedy_rates[0]:.3f}",
            }
        )
    if case["name"].startswith("bb_vs_") and float(greedy_rates[1]) > 0.70:
        statuses.append(
            {
                "status": "WARN",
                "name": "bb_defense_overcall_greedy",
                "detail": f"greedy BB call rate={greedy_rates[1]:.3f}",
            }
        )
    if case["name"].startswith("bb_vs_") and float(greedy_rates[2:8].sum()) < 0.05:
        statuses.append(
            {
                "status": "WARN",
                "name": "bb_defense_underraise_greedy",
                "detail": f"greedy BB raise rate={greedy_rates[2:8].sum():.3f}",
            }
        )
    if case["name"].startswith("bb_vs_") and float(greedy_rates[8]) > 0.05:
        statuses.append(
            {
                "status": "WARN",
                "name": "bb_defense_jam_rate_greedy",
                "detail": f"greedy BB jam rate={greedy_rates[8]:.3f}",
            }
        )
    if case["name"] == "sb_vs_3bet_b200_b800" and float(greedy_rates[8]) > 0.10:
        statuses.append(
            {
                "status": "WARN",
                "name": "sb_vs_3bet_jam_rate_greedy",
                "detail": f"greedy SB vs 3bet jam rate={greedy_rates[8]:.3f}",
            }
        )

    return {
        "name": case["name"],
        "description": case["description"],
        "action_str": case["action_str"],
        "client_pos": case["client_pos"],
        "state": {
            "street": state.get("st"),
            "pos": state.get("pos"),
            "last_bet_size": state.get("last_bet_size"),
            "street_last_bet_to": state.get("street_last_bet_to"),
            "total_last_bet_to": state.get("total_last_bet_to"),
            "to_call": c.get("to_call"),
            "pot": c.get("pot"),
        },
        "legal_slots": [
            {"slot": idx, "incr": table[idx], "class": classify_slot(idx)}
            for idx, value in enumerate(mask.tolist())
            if value > 0
        ],
        "hands": n,
        "mean_probs": {str(i): round(float(mean_probs[i]), 6) for i in range(NUM_ACTIONS)},
        "mean_class_prob_mass": {key: round(value, 6) for key, value in class_prob_mass.items()},
        "guarded": {
            "temperature": guarded_temperature,
            "allin_max_spr": guarded_allin_max_spr,
            "allin_min_prob": guarded_allin_min_prob,
            "mean_probs": {str(i): round(float(mean_guarded_probs[i]), 6) for i in range(NUM_ACTIONS)},
            "mean_class_prob_mass": {key: round(value, 6) for key, value in guarded_class_prob_mass.items()},
        },
        "avg_entropy": round(sum_entropy / max(n, 1), 6),
        "greedy_counts": {str(i): int(greedy_counts[i]) for i in range(NUM_ACTIONS)},
        "greedy_rates": {str(i): round(float(greedy_rates[i]), 6) for i in range(NUM_ACTIONS)},
        "greedy_class_counts": class_counts,
        "greedy_class_rates": {key: round(value / max(n, 1), 6) for key, value in class_counts.items()},
        "callguard": {
            "enabled": callguard_enabled,
            "min_prob": callguard_min_prob,
            "ratio": callguard_ratio,
            "include_open": callguard_include_open,
            "counts": {str(i): int(callguard_counts[i]) for i in range(NUM_ACTIONS)},
            "rates": {str(i): round(float(callguard_counts[i] / max(n, 1)), 6) for i in range(NUM_ACTIONS)},
            "class_counts": callguard_class_counts,
            "class_rates": {key: round(value / max(n, 1), 6) for key, value in callguard_class_counts.items()},
            "examples_by_slot": {key: value for key, value in callguard_examples.items() if value},
        },
        "examples_by_slot": {key: value for key, value in examples.items() if value},
        "checks": statuses,
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    checkpoint_path = Path(args.checkpoint)
    model, checkpoint = load_model(checkpoint_path, args.device)
    obs_version = resolve_obs_version(checkpoint, "auto")
    holes = all_hole_combos()
    cases = [
        evaluate_case(
            model,
            obs_version,
            args.device,
            case,
            holes,
            args.batch_size,
            args.guarded_temperature,
            args.guarded_allin_max_spr,
            args.guarded_allin_min_prob,
            args.callguard_min_prob,
            args.callguard_ratio,
            args.callguard_include_open,
        )
        for case in CASES
    ]

    warnings = [
        {"case": case["name"], **check}
        for case in cases
        for check in case.get("checks", [])
        if check.get("status") == "WARN"
    ]
    failures = [
        {"case": case["name"], **check}
        for case in cases
        for check in case.get("checks", [])
        if check.get("status") == "FAIL"
    ]
    if failures:
        overall = "FAIL"
    elif warnings:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "checked_at": now_iso(),
        "overall": overall,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_iteration": checkpoint.get("iteration"),
        "checkpoint_hands": checkpoint.get("total_hands"),
        "warning_count": len(warnings),
        "failure_count": len(failures),
        "checkpoint": {
            "iteration": checkpoint.get("iteration"),
            "total_hands": checkpoint.get("total_hands"),
            "version": checkpoint.get("version"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": checkpoint.get("obs_version"),
            "action_space_version": checkpoint.get("action_space_version"),
            "run_id": checkpoint.get("run_id"),
        },
        "obs_version_used": obs_version,
        "hole_combos": len(holes),
        "guarded_config": {
            "temperature": args.guarded_temperature,
            "allin_max_spr": args.guarded_allin_max_spr,
            "allin_min_prob": args.guarded_allin_min_prob,
        },
        "callguard_config": {
            "min_prob": args.callguard_min_prob,
            "ratio": args.callguard_ratio,
            "include_open": args.callguard_include_open,
            "scope": "preflop facing bet only unless include_open is true",
        },
        "cases": cases,
        "warnings": warnings,
        "failures": failures,
        "interpretation": (
            "WARN means legal masks are intact but greedy argmax/action mix may suppress mixed preflop actions."
            if overall == "WARN"
            else "No preflop probe warnings."
        ),
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Preflop Policy Probe",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- Iteration: `{summary['checkpoint'].get('iteration')}`",
        f"- Hands: `{summary['checkpoint'].get('total_hands')}`",
        f"- Warning count: `{summary.get('warning_count')}`",
        f"- Failure count: `{summary.get('failure_count')}`",
        f"- Hole combos per case: `{summary['hole_combos']}`",
        f"- Observation encoder: `{summary['obs_version_used']}`",
        "",
        "## Cases",
        "",
    ]
    for case in summary["cases"]:
        rates = case["greedy_class_rates"]
        mass = case["mean_class_prob_mass"]
        guarded_mass = (case.get("guarded") or {}).get("mean_class_prob_mass") or {}
        callguard_rates = ((case.get("callguard") or {}).get("class_rates") or {})
        lines.extend(
            [
                f"### {case['name']}",
                "",
                f"- Description: {case['description']}",
                f"- Action string: `{case['action_str']}`",
                f"- Legal slots: `{case['legal_slots']}`",
                f"- Mean prob mass: fold `{mass['fold']:.3f}`, call `{mass['call']:.3f}`, raise `{mass['raise']:.3f}`, allin `{mass['allin']:.3f}`",
                f"- Greedy rates: fold `{rates['fold']:.3f}`, call `{rates['call']:.3f}`, raise `{rates['raise']:.3f}`, allin `{rates['allin']:.3f}`",
                f"- Guarded expected mass: fold `{guarded_mass.get('fold', 0.0):.3f}`, call `{guarded_mass.get('call', 0.0):.3f}`, raise `{guarded_mass.get('raise', 0.0):.3f}`, allin `{guarded_mass.get('allin', 0.0):.3f}`",
                f"- Callguard rates: fold `{callguard_rates.get('fold', 0.0):.3f}`, call `{callguard_rates.get('call', 0.0):.3f}`, raise `{callguard_rates.get('raise', 0.0):.3f}`, allin `{callguard_rates.get('allin', 0.0):.3f}`",
                f"- Avg entropy: `{case['avg_entropy']:.3f}`",
            ]
        )
        for check in case.get("checks") or []:
            lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
        lines.append("")
    if summary.get("warnings"):
        lines.extend(["## Warnings", ""])
        for item in summary["warnings"]:
            lines.append(f"- `{item['case']}` `{item['name']}`: {item['detail']}")
        lines.append("")
    lines.extend(["## Interpretation", "", summary.get("interpretation", ""), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe V5 preflop policy over all hole-card combos.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--guarded-temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--callguard-include-open", action="store_true")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_summary(args)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0 if summary["overall"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
