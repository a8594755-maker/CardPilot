#!/usr/bin/env python3
"""Non-network preflight for the V5 Slumbot benchmark pipeline.

This script intentionally does not call Slumbot. It verifies that the same
components used by bench_v55_slumbot.ps1 can load a V5 checkpoint, encode a few
representative Slumbot action strings, run a forward pass, map policy slots to
Slumbot increments, compute CI from per-hand JSONL, and run the promotion-gate
auditor over those artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(THIS_DIR))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment_v55 import NUM_ACTIONS
from alpha_holdem.play_slumbot import (
    action_idx_to_incr,
    compute_legal_mask,
    decide_action,
    parse_action,
    resolve_obs_version,
)
from alpha_holdem.slumbot_ci_from_hands import DEFAULT_BASELINE_BB100
from alpha_holdem.slumbot_ci_from_hands import DEFAULT_BASELINE_HANDS_MIN
from alpha_holdem.slumbot_ci_from_hands import load_rewards, summarize as summarize_ci
from v5_slumbot_promotion_gate import evaluate as evaluate_promotion_gate
from v5_slumbot_promotion_gate import write_markdown as write_promotion_markdown


EXPECTED_METADATA = {
    "version": "v5.zero",
    "env_version": "v55",
    "obs_version": "v55",
    "action_space_version": "9slot_v5",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_checkpoint(path: Path, device: str) -> dict[str, Any]:
    obj = torch.load(path, map_location=device, weights_only=False)
    if not isinstance(obj, dict):
        raise TypeError(f"checkpoint is {type(obj).__name__}, not dict")
    return obj


def init_model(checkpoint: dict[str, Any], device: str) -> AlphaHoldemNet:
    norm_layer = str(checkpoint.get("norm_layer", "bn"))
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm_layer).to(device)
    model.eval()
    with torch.no_grad():
        model(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(2, 2, device=device),
        )
    model.load_state_dict(checkpoint["model"])
    model.eval()
    return model


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def board_for_street(street: int) -> list[str]:
    if street <= 0:
        return []
    if street == 1:
        return ["2c", "7d", "Jh"]
    if street == 2:
        return ["2c", "7d", "Jh", "9s"]
    return ["2c", "7d", "Jh", "9s", "Ad"]


def inference_cases(model: AlphaHoldemNet, checkpoint: dict[str, Any], device: str) -> list[dict[str, Any]]:
    obs_version = resolve_obs_version(checkpoint, "auto")
    examples = [
        "",
        "c",
        "b300",
        "cb300",
        "b300c/k",
        "b300c/kb600",
    ]
    rows: list[dict[str, Any]] = []
    for action_str in examples:
        state = parse_action(action_str)
        if state.get("error") or state.get("pos") not in (0, 1):
            rows.append({"action": action_str, "status": "SKIP", "detail": state.get("error") or "terminal state"})
            continue
        hole = ["As", "Kh"] if state["pos"] == 1 else ["Qs", "Qh"]
        board = board_for_street(int(state["st"]))
        mask = compute_legal_mask(state)
        action_idx = decide_action(
            model,
            hole,
            board,
            state,
            int(state["pos"]),
            device,
            greedy=True,
            obs_version=obs_version,
        )
        incr = action_idx_to_incr(action_idx, state)
        rows.append(
            {
                "action": action_str,
                "status": "PASS",
                "street": state["st"],
                "client_pos": state["pos"],
                "legal_slots": [idx for idx, value in enumerate(mask.tolist()) if value > 0],
                "chosen_slot": int(action_idx),
                "slumbot_incr": incr,
                "hole": hole,
                "board": board,
            }
        )
    return rows


def write_synthetic_hands(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rewards_bb = [1.5, -1.0, 0.5, 2.0, -2.5, 0.0, 1.0, -0.5, 3.0, -1.5]
    total = 0.0
    with path.open("w", encoding="utf-8") as fp:
        for idx, reward in enumerate(rewards_bb, start=1):
            total += reward
            fp.write(
                json.dumps(
                    {
                        "attempted_hand": idx,
                        "successful_hand": idx,
                        "winnings_bb": reward,
                        "winnings_chips": int(reward * 100),
                        "cumulative_bb": total,
                        "cumulative_chips": int(total * 100),
                    }
                )
                + "\n"
            )


def build_preflight(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else run_dir / "latest.pt"
    out_dir = Path(args.out_dir) if args.out_dir else run_dir
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    checks: list[dict[str, str]] = []
    checkpoint = load_checkpoint(checkpoint_path, device)
    add_check(checks, "checkpoint_load", "PASS", f"loaded {checkpoint_path}")

    for key, expected in EXPECTED_METADATA.items():
        actual = checkpoint.get(key)
        add_check(checks, key, "PASS" if actual == expected else "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if "model" in checkpoint:
        add_check(checks, "model_state", "PASS", "checkpoint contains model state_dict")
    else:
        add_check(checks, "model_state", "FAIL", "checkpoint missing model state_dict")

    model = init_model(checkpoint, device)
    add_check(checks, "model_load", "PASS", f"loaded AlphaHoldemNet params={count_parameters(model):,}")

    cases = inference_cases(model, checkpoint, device)
    failed_cases = [case for case in cases if case.get("status") != "PASS"]
    if failed_cases:
        add_check(checks, "inference_cases", "FAIL", f"{len(failed_cases)} cases failed/skipped")
    else:
        add_check(checks, "inference_cases", "PASS", f"{len(cases)} representative states passed")

    synthetic_hands = out_dir / "slumbot_preflight_hands.jsonl"
    ci_json = out_dir / "slumbot_preflight_ci_summary.json"
    promotion_json = out_dir / "slumbot_preflight_promotion_gate.json"
    promotion_md = out_dir / "slumbot_preflight_promotion_gate.md"
    write_synthetic_hands(synthetic_hands)
    rewards = load_rewards([synthetic_hands])
    ci = summarize_ci(
        rewards,
        l6_target_bb100=11.1,
        l6_tolerance_bb100=2.0,
        baseline_bb100=DEFAULT_BASELINE_BB100,
        baseline_hands_min=DEFAULT_BASELINE_HANDS_MIN,
    )
    ci["input_files"] = [str(synthetic_hands)]
    ci_json.write_text(json.dumps(ci, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    add_check(checks, "ci_pipeline", "PASS", f"wrote synthetic CI {ci_json}")

    promotion = evaluate_promotion_gate(
        checkpoint_path=checkpoint_path,
        ci_json_path=ci_json,
        run_dir=run_dir,
        min_promotion_hands=20_000,
        expected_stack_bb=200.0,
    )
    promotion_json.write_text(json.dumps(promotion, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_promotion_markdown(promotion_md, promotion)

    promotion_checks = {item["name"]: item["status"] for item in promotion.get("checks") or []}
    required_promotion_statuses = {
        "checkpoint_load": {"PASS"},
        "version": {"PASS"},
        "env_version": {"PASS"},
        "obs_version": {"PASS"},
        "action_space_version": {"PASS"},
        "starting_stack_bb": {"PASS"},
        "actual_hand_accounting": {"PASS"},
        "fresh_from_zero_lineage": {"PASS"},
        "health_status": {"PASS", "WARN"},
        "ci_json": {"PASS"},
        "hand_artifacts": {"PASS"},
    }
    bad = [
        name
        for name, accepted in required_promotion_statuses.items()
        if promotion_checks.get(name) not in accepted
    ]
    if bad:
        add_check(checks, "promotion_gate_pipeline", "FAIL", f"unexpected failed checks: {bad}")
    else:
        add_check(checks, "promotion_gate_pipeline", "PASS", "metadata/artifact promotion checks passed; hand-count block expected")

    expected_block = promotion_checks.get("promotion_hands") == "FAIL"
    add_check(
        checks,
        "promotion_hands_block",
        "PASS" if expected_block else "FAIL",
        "synthetic 10-hand preflight is correctly blocked from promotion",
    )

    hard_fail = any(item["status"] == "FAIL" for item in checks)
    return {
        "checked_at": now_iso(),
        "overall": "FAIL" if hard_fail else "PASS",
        "run_dir": str(run_dir),
        "checkpoint_path": str(checkpoint_path),
        "device": device,
        "checkpoint": {
            "iteration": checkpoint.get("iteration"),
            "total_hands": checkpoint.get("total_hands"),
            "version": checkpoint.get("version"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": checkpoint.get("obs_version"),
            "action_space_version": checkpoint.get("action_space_version"),
            "norm_layer": checkpoint.get("norm_layer", "bn"),
            "run_id": checkpoint.get("run_id"),
        },
        "obs_version": resolve_obs_version(checkpoint, "auto"),
        "checks": checks,
        "inference_cases": cases,
        "artifacts": {
            "synthetic_hands": str(synthetic_hands),
            "ci_json": str(ci_json),
            "promotion_json": str(promotion_json),
            "promotion_md": str(promotion_md),
        },
        "promotion_gate_overall": promotion.get("overall"),
        "notes": [
            "No Slumbot API calls were made.",
            "The synthetic promotion gate is expected to fail promotion_hands.",
            "A PASS here only proves local benchmark plumbing, not model strength.",
        ],
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Slumbot Pipeline Preflight",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- Checkpoint iteration: `{summary['checkpoint'].get('iteration')}`",
        f"- Checkpoint hands: `{summary['checkpoint'].get('total_hands'):,}`",
        f"- Obs version: `{summary.get('obs_version')}`",
        f"- Device: `{summary.get('device')}`",
        "",
        "## Checks",
        "",
    ]
    for check in summary.get("checks") or []:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")

    lines.extend(["", "## Inference Cases", "", "| action string | street | legal slots | chosen | incr |", "|---|---:|---|---:|---|"])
    for case in summary.get("inference_cases") or []:
        lines.append(
            "| {action} | {street} | {legal} | {chosen} | {incr} |".format(
                action=case.get("action"),
                street=case.get("street"),
                legal=case.get("legal_slots"),
                chosen=case.get("chosen_slot"),
                incr=case.get("slumbot_incr"),
            )
        )

    lines.extend(["", "## Artifacts", ""])
    for key, value in (summary.get("artifacts") or {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Notes", ""])
    for note in summary.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight the local V5 Slumbot benchmark pipeline without API calls.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_preflight(args)
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
