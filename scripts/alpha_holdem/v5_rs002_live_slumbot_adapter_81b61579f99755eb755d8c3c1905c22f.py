"""Thin live Slumbot adapter for the frozen RS002 resolver.

The adapter changes no resolver science.  It reconstructs the public information
set, verifies bit-exact observations and exact type+cent root-action identity at the
live boundary, and otherwise returns the precomputed H11 greedy baseline.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "81b61579f99755eb755d8c3c1905c22f"
FROZEN_RUNNER = ROOT / "scripts" / "alpha_holdem" / f"v5_rs002_paired_mc32_lcb95_resolver_{TOKEN}.py"
FROZEN_RUNNER_SHA256 = "44826e22405661b964a01827d051c825e04c28c194544f57ddb890dd34c4fdb6"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if sha256_file(FROZEN_RUNNER) != FROZEN_RUNNER_SHA256:
    raise RuntimeError("frozen_rs002_runner_hash_mismatch")

_spec = importlib.util.spec_from_file_location("v5_rs002_frozen_runner", FROZEN_RUNNER)
if _spec is None or _spec.loader is None:
    raise RuntimeError("frozen_rs002_runner_import_spec_failure")
rs002 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs002)

from alpha_holdem import play_slumbot as live  # noqa: E402


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def make_public_reconstruction_row(
    *,
    action_str: str,
    client_pos: int,
    hero_hole: list[str],
    board: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = live.parse_action(action_str)
    if "error" in state:
        raise RuntimeError("live_action_parse_failure")
    if int(state["pos"]) != int(client_pos):
        raise RuntimeError("live_current_player_mismatch")
    commitment = live.compute_commitments(state)
    safe_row = {
        "who": "hero",
        "street": int(state["st"]),
        "action_str_before": str(action_str),
        "client_pos": int(client_pos),
        "hero_hole": list(hero_hole),
        "board": list(board),
        "pot_before": int(commitment["pot"]),
        "to_call": int(commitment["to_call"]),
        "stack_remaining": int(commitment["stack"]),
    }
    return safe_row, state


def slumbot_action_identity(slot: int, incr: str | None, state: dict[str, Any], allin_incr: str | None) -> tuple[str, int] | None:
    if incr is None:
        return None
    if incr == "f":
        return "FOLD", 0
    if incr == "k":
        return "CHECK", 0
    if incr == "c":
        return "CALL", 0
    if not incr.startswith("b") or not incr[1:].isdigit():
        raise RuntimeError("live_increment_identity_invalid")
    amount = int(incr[1:])
    if slot == 8 and incr == allin_incr:
        action_type = "ALLIN"
    elif int(state["last_bet_size"]) > 0:
        action_type = "RAISE"
    else:
        action_type = "BET"
    return action_type, amount


def compare_live_boundary(
    *,
    action_str: str,
    client_pos: int,
    hero_hole: list[str],
    board: list[str],
) -> dict[str, Any]:
    safe_row, live_state = make_public_reconstruction_row(
        action_str=action_str,
        client_pos=client_pos,
        hero_hole=hero_hole,
        board=board,
    )
    if int(live_state["st"]) <= 0:
        return {
            "eligible_postflop": False,
            "exact": True,
            "reason": "PREFLOP_BIT_EXACT_PASSTHROUGH",
            "public_input_sha256": sha256_obj(safe_row),
        }
    info_state = rs002.reconstruct_witness(safe_row)
    hunl_mask, hunl_table, hunl_slots = rs002.legal_table_exact(info_state)
    live_mask, live_table = live.build_action_table(live_state)
    live_slots = [slot for slot in range(9) if float(live_mask[slot]) == 1.0]
    allin_incr = live_table[8]
    action_rows = []
    action_exact = hunl_slots == live_slots
    for slot in sorted(set(hunl_slots) | set(live_slots)):
        hunl_identity = rs002.action_identity(hunl_table[slot]) if slot in hunl_slots else None
        live_identity = slumbot_action_identity(slot, live_table[slot], live_state, allin_incr) if slot in live_slots else None
        equal = hunl_identity == live_identity
        action_exact = action_exact and equal
        action_rows.append({
            "slot": slot,
            "hunl_identity": list(hunl_identity) if hunl_identity is not None else None,
            "live_identity": list(live_identity) if live_identity is not None else None,
            "exact": equal,
        })
    live_card = live.encode_cards(hero_hole, board, int(live_state["st"]))
    live_history = live.encode_action_history(live_state, client_pos, int(live_state["pos"]), obs_version="v55")
    commitment = live.compute_commitments(live_state)
    live_extra = live.encode_extra([
        live.STACK_SIZE - commitment["hero_total"],
        live.STACK_SIZE - commitment["opp_total"],
    ])
    hunl_card = rs002.encode_cards(info_state, int(info_state.current_player))
    hunl_history = rs002.encode_action_history(info_state, int(info_state.current_player))
    hunl_extra = rs002.encode_extra(info_state, int(info_state.current_player))
    observation_exact = {
        "card": bool(np.array_equal(live_card, hunl_card)),
        "action_history": bool(np.array_equal(live_history, hunl_history)),
        "extra": bool(np.array_equal(live_extra, hunl_extra)),
        "legal_mask": bool(np.array_equal(live_mask, hunl_mask)),
    }
    exact = action_exact and all(observation_exact.values())
    return {
        "eligible_postflop": True,
        "exact": exact,
        "reason": "EXACT_LIVE_BOUNDARY" if exact else "ACTION_TABLE_OR_OBSERVATION_IDENTITY_MISMATCH",
        "public_input_sha256": sha256_obj(safe_row),
        "information_set_sha256": rs002.state_identity(info_state),
        "action_table_exact": action_exact,
        "observation_exact": observation_exact,
        "action_rows": action_rows,
        "hunl_legal_slots": hunl_slots,
        "live_legal_slots": live_slots,
    }


def choose_live_action(
    actor: Any,
    *,
    action_str: str,
    client_pos: int,
    hero_hole: list[str],
    board: list[str],
) -> tuple[int, dict[str, Any]]:
    safe_row, live_state = make_public_reconstruction_row(
        action_str=action_str,
        client_pos=client_pos,
        hero_hole=hero_hole,
        board=board,
    )
    baseline_slot = live.decide_action(
        actor.model,
        hero_hole,
        board,
        live_state,
        client_pos,
        "cuda:0",
        greedy=True,
        obs_version="v55",
        policy_mode="greedy",
    )
    if int(live_state["st"]) <= 0:
        return baseline_slot, {
            "resolver_attempted": False,
            "baseline_slot": baseline_slot,
            "selected_slot": baseline_slot,
            "reason": "PREFLOP_BIT_EXACT_PASSTHROUGH",
            "fallback": False,
            "public_input_sha256": sha256_obj(safe_row),
        }
    boundary = compare_live_boundary(
        action_str=action_str,
        client_pos=client_pos,
        hero_hole=hero_hole,
        board=board,
    )
    if not boundary["exact"]:
        return baseline_slot, {
            "resolver_attempted": True,
            "baseline_slot": baseline_slot,
            "selected_slot": baseline_slot,
            "reason": boundary["reason"],
            "fallback": True,
            "boundary": boundary,
        }
    info_state = rs002.reconstruct_witness(safe_row)
    resolution = rs002.resolve_information_set(actor, info_state, cohort="live_slumbot")
    selected_slot = int(resolution["selected_slot"])
    live_mask, live_table = live.build_action_table(live_state)
    if float(live_mask[selected_slot]) != 1.0 or live_table[selected_slot] is None:
        return baseline_slot, {
            "resolver_attempted": True,
            "baseline_slot": baseline_slot,
            "selected_slot": baseline_slot,
            "reason": "LIVE_SELECTED_SLOT_ILLEGAL",
            "fallback": True,
            "boundary": boundary,
        }
    return selected_slot, {
        "resolver_attempted": True,
        "baseline_slot": baseline_slot,
        "selected_slot": selected_slot,
        "reason": resolution["selection_reason"],
        "fallback": bool(resolution["error_fallback"]),
        "boundary": boundary,
        "resolution_trace_sha256": resolution.get("decision_trace_sha256"),
        "latency_seconds": resolution.get("latency_seconds"),
    }
