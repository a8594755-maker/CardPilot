#!/usr/bin/env python3
"""Replay Slumbot decision dumps through alternate V5 selectors.

This is an offline diagnostic: it does not request new Slumbot hands. It reads
the JSONL decision dumps emitted by play_slumbot.py, filters hero decision
contexts, and re-runs the frozen checkpoint with deterministic selector modes.
Use it after quick/promotion/formal runs to decide whether a bad score is a
policy-learning problem or a greedy-realization problem.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from play_slumbot import (  # noqa: E402
    AlphaHoldemNet,
    NUM_ACTIONS,
    STACK_SIZE,
    action_idx_to_incr,
    compute_commitments,
    compute_legal_mask,
    encode_action_history,
    encode_cards,
    encode_extra,
    guarded_action_probs,
    is_unopened_preflop_start,
    parse_action,
    preflop_callguard_action,
    resolve_obs_version,
)


POLICY_CONFIGS: dict[str, dict[str, Any]] = {
    "greedy": {"policy_mode": "greedy", "greedy": True, "callguard_include_open": False},
    "greedy-guarded": {"policy_mode": "greedy-guarded", "greedy": True, "callguard_include_open": False},
    "preflop-callguard": {
        "policy_mode": "preflop-callguard",
        "greedy": True,
        "callguard_include_open": False,
    },
    "preflop-callguard-open": {
        "policy_mode": "preflop-callguard",
        "greedy": True,
        "callguard_include_open": True,
    },
}

STREET_NAMES = ("preflop", "flop", "turn", "river")


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


def action_class_from_slot(slot: int) -> str:
    if slot == 0:
        return "fold"
    if slot == 1:
        return "call"
    if slot == 8:
        return "allin"
    return "raise"


def actual_incr(row: dict[str, Any]) -> str:
    move = str(row.get("action_move") or "")
    if move == "b":
        return f"b{int(row.get('action_amount') or 0)}"
    return move


def actual_class(row: dict[str, Any]) -> str:
    move = str(row.get("action_move") or "")
    if move == "f":
        return "fold"
    if move in {"k", "c"}:
        return "call"
    if move == "b":
        amount = int(row.get("action_amount") or 0)
        return "allin" if amount >= STACK_SIZE else "raise"
    return "unknown"


def situation_name(state: dict[str, Any]) -> str:
    street = int(state.get("st", 0))
    if street == 0:
        c = compute_commitments(state)
        if is_unopened_preflop_start(state):
            return "preflop_open"
        if int(c.get("to_call", 0)) > 0:
            return "preflop_facing_bet"
        return "preflop_other"
    street_name = STREET_NAMES[street] if 0 <= street < len(STREET_NAMES) else f"street_{street}"
    c = compute_commitments(state)
    suffix = "facing_bet" if int(c.get("to_call", 0)) > 0 else "no_bet"
    return f"{street_name}_{suffix}"


def expand_dump_paths(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(Path(pattern))
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def add_class_rate(counter: Counter[str]) -> dict[str, Any]:
    total = sum(counter.values())
    rates = {
        key: (float(counter.get(key, 0)) / total if total else 0.0)
        for key in ("fold", "call", "raise", "allin", "unknown")
    }
    return {"count": total, "counts": dict(counter), "rates": rates}


def add_probability_mass(counter: Counter[str], probs: torch.Tensor) -> None:
    values = probs.detach().cpu().numpy().reshape(-1)
    for slot, prob in enumerate(values):
        counter[action_class_from_slot(slot)] += float(prob)


def probability_mass_summary(counter: Counter[str], total_decisions: int) -> dict[str, Any]:
    rates = {
        key: (float(counter.get(key, 0.0)) / total_decisions if total_decisions else 0.0)
        for key in ("fold", "call", "raise", "allin", "unknown")
    }
    return {"count": total_decisions, "mass": dict(counter), "rates": rates}


def nested_probability_mass_summary(
    nested: dict[str, Counter[str]],
    totals: Counter[str],
) -> dict[str, Any]:
    return {
        key: probability_mass_summary(counter, int(totals.get(key, 0)))
        for key, counter in sorted(nested.items())
    }


def nested_counter_to_summary(nested: dict[str, Counter[str]]) -> dict[str, Any]:
    return {key: add_class_rate(counter) for key, counter in sorted(nested.items())}


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


@torch.no_grad()
def forward_probs(
    model: AlphaHoldemNet,
    *,
    hero_hole: list[str],
    board: list[str],
    state: dict[str, Any],
    client_pos: int,
    device: str,
    obs_version: str,
) -> tuple[torch.Tensor, torch.Tensor]:
    street = int(state.get("st", 0))
    card_t = torch.tensor(encode_cards(hero_hole, board, street), device=device).unsqueeze(0)
    action_t = torch.tensor(
        encode_action_history(state, client_pos, int(state.get("pos", -1)), obs_version=obs_version),
        device=device,
    ).unsqueeze(0)
    c = compute_commitments(state)
    stacks = [STACK_SIZE - c["hero_total"], STACK_SIZE - c["opp_total"]]
    extra_t = torch.tensor(encode_extra(stacks), device=device).unsqueeze(0)
    mask_t = torch.tensor(compute_legal_mask(state), device=device).unsqueeze(0)
    logits, _ = model(card_t, action_t, extra_t, mask_t)
    return F.softmax(logits, dim=-1), mask_t


def select_from_probs(
    name: str,
    probs: torch.Tensor,
    mask_t: torch.Tensor,
    state: dict[str, Any],
    args: argparse.Namespace,
) -> int:
    cfg = POLICY_CONFIGS[name]
    policy_mode = str(cfg["policy_mode"])
    include_open = bool(cfg["callguard_include_open"])
    if policy_mode == "greedy":
        return int(torch.argmax(probs, dim=-1).item())

    guarded = guarded_action_probs(
        probs,
        mask_t,
        state,
        allin_max_spr=args.guarded_allin_max_spr,
        allin_min_prob=args.guarded_allin_min_prob,
    )
    if policy_mode == "greedy-guarded":
        return int(torch.argmax(guarded, dim=-1).item())
    if policy_mode == "preflop-callguard":
        if is_unopened_preflop_start(state) and not include_open:
            return int(torch.argmax(probs, dim=-1).item())
        callguard_action = preflop_callguard_action(
            guarded,
            mask_t,
            state,
            call_min_prob=args.callguard_min_prob,
            call_ratio=args.callguard_ratio,
            include_open=include_open,
        )
        if callguard_action is not None:
            return int(callguard_action)
        return int(torch.argmax(guarded, dim=-1).item())
    raise ValueError(f"unsupported deterministic policy: {name}")


def replay(args: argparse.Namespace) -> dict[str, Any]:
    device = args.device
    model, checkpoint = load_model(Path(args.checkpoint), device)
    obs_version = resolve_obs_version(checkpoint, args.obs_version)
    policy_names = [name.strip() for name in args.policies.split(",") if name.strip()]
    unknown = [name for name in policy_names if name not in POLICY_CONFIGS]
    if unknown:
        raise ValueError(f"unknown policies: {', '.join(unknown)}")

    dump_paths = expand_dump_paths(args.dump)
    missing = [str(path) for path in dump_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing dump files: {missing}")

    total_rows = 0
    hero_rows = 0
    skipped_rows = Counter()
    actual_by_situation: dict[str, Counter[str]] = defaultdict(Counter)
    actual_by_street: dict[str, Counter[str]] = defaultdict(Counter)
    probability_mass: dict[str, dict[str, Any]] = {
        "raw": {"classes": Counter(), "situations": defaultdict(Counter), "streets": defaultdict(Counter)},
        "guarded": {"classes": Counter(), "situations": defaultdict(Counter), "streets": defaultdict(Counter)},
    }
    probability_totals: dict[str, dict[str, Counter[str] | int]] = {
        "raw": {"total": 0, "situations": Counter(), "streets": Counter()},
        "guarded": {"total": 0, "situations": Counter(), "streets": Counter()},
    }
    policy_stats: dict[str, dict[str, Any]] = {}
    for name in policy_names:
        policy_stats[name] = {
            "classes": Counter(),
            "situations": defaultdict(Counter),
            "streets": defaultdict(Counter),
            "exact_match": 0,
            "class_match": 0,
            "total": 0,
        }

    changes: dict[str, dict[str, Any]] = {
        name: {
            "changed": 0,
            "changed_preflop": 0,
            "changed_preflop_facing_bet": 0,
            "changed_losing_hands": 0,
            "changed_winning_hands": 0,
            "to_call": 0,
            "from_to": Counter(),
            "examples": [],
        }
        for name in policy_names
        if name != "greedy"
    }

    for path in dump_paths:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                if args.limit and hero_rows >= args.limit:
                    break
                line = line.strip()
                if not line:
                    continue
                total_rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    skipped_rows["bad_json"] += 1
                    continue
                if row.get("who") != "hero":
                    continue
                state = parse_action(str(row.get("action_str_before") or ""))
                if state.get("error"):
                    skipped_rows["parse_error"] += 1
                    continue
                client_pos = int(row.get("client_pos", -999))
                if int(state.get("pos", -1)) != client_pos:
                    skipped_rows["not_hero_turn"] += 1
                    continue
                hero_hole = list(row.get("hero_hole") or [])
                if len(hero_hole) != 2:
                    skipped_rows["missing_hero_hole"] += 1
                    continue
                board = list(row.get("board") or [])
                hero_rows += 1

                actual_cls = actual_class(row)
                actual = actual_incr(row)
                situation = situation_name(state)
                street = STREET_NAMES[int(state.get("st", 0))] if int(state.get("st", 0)) < 4 else "unknown"
                actual_by_situation[situation][actual_cls] += 1
                actual_by_street[street][actual_cls] += 1

                probs, mask_t = forward_probs(
                    model,
                    hero_hole=hero_hole,
                    board=board,
                    state=state,
                    client_pos=client_pos,
                    device=device,
                    obs_version=obs_version,
                )
                guarded_probs = guarded_action_probs(
                    probs,
                    mask_t,
                    state,
                    allin_max_spr=args.guarded_allin_max_spr,
                    allin_min_prob=args.guarded_allin_min_prob,
                )
                for mass_name, mass_probs in (("raw", probs), ("guarded", guarded_probs)):
                    add_probability_mass(probability_mass[mass_name]["classes"], mass_probs)
                    add_probability_mass(probability_mass[mass_name]["situations"][situation], mass_probs)
                    add_probability_mass(probability_mass[mass_name]["streets"][street], mass_probs)
                    probability_totals[mass_name]["total"] = int(probability_totals[mass_name]["total"]) + 1
                    situation_totals = probability_totals[mass_name]["situations"]
                    street_totals = probability_totals[mass_name]["streets"]
                    assert isinstance(situation_totals, Counter)
                    assert isinstance(street_totals, Counter)
                    situation_totals[situation] += 1
                    street_totals[street] += 1

                decisions: dict[str, dict[str, Any]] = {}
                for name in policy_names:
                    slot = select_from_probs(name, probs, mask_t, state, args)
                    incr = action_idx_to_incr(slot, state)
                    cls = action_class_from_slot(slot)
                    decisions[name] = {"slot": slot, "incr": incr, "class": cls}

                    stats = policy_stats[name]
                    stats["total"] += 1
                    stats["classes"][cls] += 1
                    stats["situations"][situation][cls] += 1
                    stats["streets"][street][cls] += 1
                    if incr == actual:
                        stats["exact_match"] += 1
                    if cls == actual_cls:
                        stats["class_match"] += 1

                greedy_decision = decisions.get("greedy")
                if greedy_decision:
                    for name, decision in decisions.items():
                        if name == "greedy":
                            continue
                        if decision["slot"] == greedy_decision["slot"]:
                            continue
                        change = changes[name]
                        change["changed"] += 1
                        if int(state.get("st", 0)) == 0:
                            change["changed_preflop"] += 1
                        if situation == "preflop_facing_bet":
                            change["changed_preflop_facing_bet"] += 1
                        winnings_bb = safe_float(row.get("winnings_hero")) / 100.0
                        if winnings_bb < 0:
                            change["changed_losing_hands"] += 1
                        elif winnings_bb > 0:
                            change["changed_winning_hands"] += 1
                        if decision["class"] == "call":
                            change["to_call"] += 1
                        change["from_to"][f"{greedy_decision['class']}->{decision['class']}"] += 1
                        if len(change["examples"]) < args.max_examples:
                            change["examples"].append(
                                {
                                    "hand_idx": row.get("hand_idx"),
                                    "street": street,
                                    "situation": situation,
                                    "action_str_before": row.get("action_str_before"),
                                    "hero_hole": hero_hole,
                                    "board": board,
                                    "actual": {"incr": actual, "class": actual_cls},
                                    "greedy": greedy_decision,
                                    name: decision,
                                    "winnings_bb": winnings_bb,
                                }
                            )

        if args.limit and hero_rows >= args.limit:
            break

    policy_summaries: dict[str, Any] = {}
    for name, stats in policy_stats.items():
        total = int(stats["total"])
        policy_summaries[name] = {
            "total": total,
            "classes": add_class_rate(stats["classes"]),
            "situations": nested_counter_to_summary(stats["situations"]),
            "streets": nested_counter_to_summary(stats["streets"]),
            "exact_match_rate_vs_dump": float(stats["exact_match"]) / total if total else 0.0,
            "class_match_rate_vs_dump": float(stats["class_match"]) / total if total else 0.0,
        }

    change_summaries: dict[str, Any] = {}
    for name, change in changes.items():
        changed = int(change["changed"])
        change_summaries[name] = {
            "changed": changed,
            "changed_rate": float(changed) / hero_rows if hero_rows else 0.0,
            "changed_preflop": int(change["changed_preflop"]),
            "changed_preflop_facing_bet": int(change["changed_preflop_facing_bet"]),
            "changed_losing_hands": int(change["changed_losing_hands"]),
            "changed_winning_hands": int(change["changed_winning_hands"]),
            "to_call": int(change["to_call"]),
            "from_to": dict(change["from_to"]),
            "examples": change["examples"],
        }

    mass_summaries: dict[str, Any] = {}
    for name, mass in probability_mass.items():
        totals = probability_totals[name]
        situation_totals = totals["situations"]
        street_totals = totals["streets"]
        assert isinstance(situation_totals, Counter)
        assert isinstance(street_totals, Counter)
        mass_summaries[name] = {
            "classes": probability_mass_summary(mass["classes"], int(totals["total"])),
            "situations": nested_probability_mass_summary(mass["situations"], situation_totals),
            "streets": nested_probability_mass_summary(mass["streets"], street_totals),
        }

    return {
        "checkpoint": {
            "path": str(Path(args.checkpoint)),
            "iteration": checkpoint.get("iteration"),
            "total_hands": checkpoint.get("total_hands"),
            "version": checkpoint.get("version"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": obs_version,
            "action_space_version": checkpoint.get("action_space_version"),
        },
        "dump_files": [str(path) for path in dump_paths],
        "total_rows": total_rows,
        "hero_decisions": hero_rows,
        "skipped_rows": dict(skipped_rows),
        "actual": {
            "situations": nested_counter_to_summary(actual_by_situation),
            "streets": nested_counter_to_summary(actual_by_street),
        },
        "probability_mass": mass_summaries,
        "policies": policy_summaries,
        "changes_vs_greedy": change_summaries,
        "config": {
            "temperature": args.temperature,
            "guarded_allin_max_spr": args.guarded_allin_max_spr,
            "guarded_allin_min_prob": args.guarded_allin_min_prob,
            "callguard_min_prob": args.callguard_min_prob,
            "callguard_ratio": args.callguard_ratio,
            "policies": policy_names,
            "limit": args.limit,
        },
    }


def fmt_pct(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def class_rates_line(summary: dict[str, Any]) -> str:
    rates = (summary.get("classes") or {}).get("rates") or {}
    return (
        f"fold {fmt_pct(float(rates.get('fold', 0.0)))}, "
        f"call/check {fmt_pct(float(rates.get('call', 0.0)))}, "
        f"raise {fmt_pct(float(rates.get('raise', 0.0)))}, "
        f"all-in {fmt_pct(float(rates.get('allin', 0.0)))}"
    )


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    checkpoint = summary.get("checkpoint") or {}
    lines = [
        "# V5 Slumbot Selector Replay",
        "",
        f"- Checkpoint: `{checkpoint.get('path')}`",
        f"- Iteration: `{checkpoint.get('iteration')}`",
        f"- Training hands: `{checkpoint.get('total_hands')}`",
        f"- Env/obs/action: `{checkpoint.get('env_version')}` / `{checkpoint.get('obs_version')}` / `{checkpoint.get('action_space_version')}`",
        f"- Dump files: `{len(summary.get('dump_files') or [])}`",
        f"- Hero decisions replayed: `{summary.get('hero_decisions')}`",
        "",
        "## Policy Mix",
        "",
        "| Policy | Overall mix | Exact match vs dump | Class match vs dump |",
        "| --- | --- | ---: | ---: |",
    ]
    for name, policy in (summary.get("policies") or {}).items():
        lines.append(
            f"| `{name}` | {class_rates_line(policy)} | "
            f"{fmt_pct(float(policy.get('exact_match_rate_vs_dump') or 0.0))} | "
            f"{fmt_pct(float(policy.get('class_match_rate_vs_dump') or 0.0))} |"
        )

    lines.extend(
        [
            "",
            "## Policy Probability Mass",
            "",
            "| Distribution | Overall mass |",
            "| --- | --- |",
        ]
    )
    for name, mass in (summary.get("probability_mass") or {}).items():
        lines.append(f"| `{name}` | {class_rates_line({'classes': mass.get('classes') or {}})} |")

    lines.extend(["", "## Preflop Facing Bet", "", "| Policy | Count | Fold | Call | Raise | All-in |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for name, policy in (summary.get("policies") or {}).items():
        pf = ((policy.get("situations") or {}).get("preflop_facing_bet") or {})
        rates = pf.get("rates") or {}
        lines.append(
            f"| `{name}` | {int(pf.get('count') or 0)} | "
            f"{fmt_pct(float(rates.get('fold', 0.0)))} | {fmt_pct(float(rates.get('call', 0.0)))} | "
            f"{fmt_pct(float(rates.get('raise', 0.0)))} | {fmt_pct(float(rates.get('allin', 0.0)))} |"
        )

    lines.extend(["", "## Probability Mass By Street", "", "| Distribution | Street | Fold | Call | Raise | All-in |", "| --- | --- | ---: | ---: | ---: | ---: |"])
    for name, mass in (summary.get("probability_mass") or {}).items():
        for street, street_summary in (mass.get("streets") or {}).items():
            rates = street_summary.get("rates") or {}
            lines.append(
                f"| `{name}` | `{street}` | "
                f"{fmt_pct(float(rates.get('fold', 0.0)))} | {fmt_pct(float(rates.get('call', 0.0)))} | "
                f"{fmt_pct(float(rates.get('raise', 0.0)))} | {fmt_pct(float(rates.get('allin', 0.0)))} |"
            )

    lines.extend(["", "## Changes Vs Greedy", ""])
    for name, change in (summary.get("changes_vs_greedy") or {}).items():
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Changed decisions: `{change.get('changed')}` ({fmt_pct(float(change.get('changed_rate') or 0.0))})",
                f"- Changed preflop decisions: `{change.get('changed_preflop')}`",
                f"- Changed preflop facing-bet decisions: `{change.get('changed_preflop_facing_bet')}`",
                f"- Changed to call/check: `{change.get('to_call')}`",
                f"- Changed on losing hands: `{change.get('changed_losing_hands')}`",
                f"- Changed on winning hands: `{change.get('changed_winning_hands')}`",
                f"- From/to classes: `{change.get('from_to')}`",
                "",
            ]
        )
        examples = change.get("examples") or []
        if examples:
            lines.extend(["Examples:", ""])
            for ex in examples[:5]:
                lines.append(
                    "- "
                    f"hand `{ex.get('hand_idx')}` {ex.get('situation')} action=`{ex.get('action_str_before')}` "
                    f"hole=`{''.join(ex.get('hero_hole') or [])}` "
                    f"greedy=`{(ex.get('greedy') or {}).get('incr')}` "
                    f"{name}=`{(ex.get(name) or {}).get('incr')}` "
                    f"actual=`{(ex.get('actual') or {}).get('incr')}` "
                    f"winnings_bb=`{ex.get('winnings_bb')}`"
                )
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Slumbot dump decisions through deterministic V5 selectors.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--dump", nargs="+", required=True, help="Dump JSONL paths or glob patterns.")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--obs-version", default="auto", choices=["auto", "v4", "v55"])
    parser.add_argument(
        "--policies",
        default="greedy,greedy-guarded,preflop-callguard,preflop-callguard-open",
        help="Comma-separated policy names.",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--limit", type=int, default=0, help="Optional max hero decisions for fast probes.")
    parser.add_argument("--max-examples", type=int, default=12)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = replay(args)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
