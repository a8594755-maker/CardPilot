"""Frozen RS009 greedy-direct Slumbot quick5k session runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from alpha_holdem import play_slumbot as live  # noqa: E402
from alpha_holdem import v5_rs009_direct_materialized_resolver_72e9bb6b8a4f4618aa6657710b66c5c9 as rs009  # noqa: E402


TOKEN = "3923624abb5ec15db4dca9ba20e36895c"
IDENTITY = "3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70"
RS009_IDENTITY = "72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4"
PREREG = ROOT / "reports" / f"v5_rs009_quick5k_preregistration_{TOKEN}_20260723.json"
PREREG_BYTES = 7387
PREREG_SHA256 = "00f334383231d1ecb1655796498dd5e020e28d031b21a94ea9045c076e31672c"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs009_quick5k_implementation_audit_{TOKEN}_20260723.json"
QUICK_ROOT = ROOT / "models" / "bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723"
EXPECTED_NONCES = {
    1: "RS009_QUICK5K_PART1_2036972301",
    2: "RS009_QUICK5K_PART2_2036972301",
    3: "RS009_QUICK5K_PART3_2036972301",
    4: "RS009_QUICK5K_PART4_2036972301",
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def write_line(handle: Any, value: Any) -> None:
    handle.write(canonical(value) + "\n")
    handle.flush()


def verify_static_authority() -> dict[str, Any]:
    if PREREG.stat().st_size != PREREG_BYTES or sha_file(PREREG) != PREREG_SHA256:
        raise RuntimeError("quick5k_preregistration_identity_failure")
    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    if registration["identity"]["sha256"] != IDENTITY:
        raise RuntimeError("quick5k_identity_failure")
    failures = []
    for item in registration["frozen_inputs"]:
        path = Path(item["path"])
        if (
            not path.is_file()
            or path.stat().st_size != int(item["bytes"])
            or sha_file(path) != item["sha256"]
        ):
            failures.append(item["role"])
    if failures:
        raise RuntimeError(f"quick5k_frozen_input_failure:{failures}")
    rs009.verify_frozen_inputs()
    return registration


def serialize_action_state(state: dict[str, Any]) -> str:
    street = int(state["st"])
    segments: list[str] = []
    actions = state["street_actions"]
    for street_index in range(street + 1):
        text = ""
        for action, _actor, amount in actions[street_index]:
            text += f"b{int(amount)}" if action == "b" else str(action)
        segments.append(text)
    return "/".join(segments)


def live_row(
    *,
    source: str,
    hand_idx: int,
    decision_idx: int,
    action_str: str,
    state: dict[str, Any],
    client_pos: int,
    hole_cards: list[str],
    board: list[str],
) -> dict[str, Any]:
    commitments = live.compute_commitments(state)
    return {
        "hand_idx": int(hand_idx),
        "move_idx": int(decision_idx),
        "who": "hero",
        "client_pos": int(client_pos),
        "mover_pos": int(state["pos"]),
        "action_str_before": str(action_str),
        "street": int(state["st"]),
        "hero_hole": list(hole_cards),
        "board": list(board),
        "pot_before": int(commitments["pot"]),
        "to_call": int(commitments["to_call"]),
        "stack_remaining": int(commitments["stack"]),
        "last_bet_size": int(state["last_bet_size"]),
        "street_last_bet_to": int(state["street_last_bet_to"]),
        "total_last_bet_to": int(state["total_last_bet_to"]),
        "action_move": "k",
        "action_amount": 0,
        "source": source,
    }


def boundary_contract(
    *,
    row: dict[str, Any],
    state: dict[str, Any],
    client_pos: int,
    hole_cards: list[str],
    board: list[str],
    live_mask: np.ndarray,
) -> tuple[rs009.DualDomainState, dict[str, Any]]:
    root = rs009.state_from_row(row)
    witness = rs009.assert_witness(row, root)
    rs_mask, rs_table = root.policy_table()
    expected_mask, expected_table = live.build_action_table(state)
    rs_cards, rs_history, rs_extra, _, _ = rs009.observation(root)
    commitments = live.compute_commitments(state)
    live_cards = live.encode_cards(hole_cards, board, int(state["st"]))
    live_history = live.encode_action_history(state, client_pos, int(state["pos"]), obs_version="v55")
    live_extra = live.encode_extra(
        [
            live.STACK_SIZE - int(commitments["hero_total"]),
            live.STACK_SIZE - int(commitments["opp_total"]),
        ]
    )
    checks = {
        "action_string_roundtrip": serialize_action_state(state) == row["action_str_before"],
        "actor_exact": int(state["pos"]) == int(client_pos) == int(root.actor),
        "mask_exact": bool(np.array_equal(rs_mask, expected_mask) and np.array_equal(rs_mask, live_mask)),
        "table_exact": rs_table == expected_table,
        "cards_exact": bool(np.array_equal(rs_cards, live_cards)),
        "history_exact": bool(np.array_equal(rs_history, live_history)),
        "extra_exact": bool(np.array_equal(rs_extra, live_extra)),
    }
    return root, {
        "exact": all(checks.values()),
        "checks": checks,
        "witness": witness,
        "policy_table9": rs_table,
    }


class ResolverPolicy:
    def __init__(self, *, part: int, nonce: str):
        self.part = int(part)
        self.source = f"RS009_QUICK5K_PART{part}"
        self.policy = rs009.H11Policy(nonce)
        self.hand_idx = 0
        self.decision_idx = 0
        self.pending: list[dict[str, Any]] = []

    def begin_hand(self, hand_idx: int) -> None:
        self.hand_idx = int(hand_idx)
        self.decision_idx = 0
        self.pending = []

    def decide(
        self,
        hole_cards: list[str],
        board: list[str],
        state: dict[str, Any],
        client_pos: int,
        live_mask: np.ndarray,
    ) -> int:
        action_str = serialize_action_state(state)
        row = live_row(
            source=self.source,
            hand_idx=self.hand_idx,
            decision_idx=self.decision_idx,
            action_str=action_str,
            state=state,
            client_pos=client_pos,
            hole_cards=hole_cards,
            board=board,
        )
        root, contract = boundary_contract(
            row=row,
            state=state,
            client_pos=client_pos,
            hole_cards=hole_cards,
            board=board,
            live_mask=live_mask,
        )
        baseline_slots, baseline_logits = self.policy.infer([root])
        baseline = int(baseline_slots[0])
        _, table = root.policy_table()
        postflop = int(state["st"]) > 0
        if not contract["exact"]:
            selected = int(
                live.decide_action(
                    self.policy.model,
                    hole_cards,
                    board,
                    state,
                    client_pos,
                    "cuda:0",
                    greedy=True,
                    obs_version="v55",
                    policy_mode="greedy",
                )
            )
            resolution = {
                "resolver_attempted": postflop,
                "selected_slot": selected,
                "selection_reason": "LIVE_CONTRACT_FALLBACK",
                "error_fallback": True,
                "latency_seconds": 0.0,
            }
        elif postflop:
            resolution = rs009.resolve(self.policy, row)
            selected = int(resolution["selected_slot"])
        else:
            selected = baseline
            resolution = {
                "resolver_attempted": False,
                "selected_slot": selected,
                "selection_reason": "PREFLOP_GREEDY_DIRECT",
                "error_fallback": False,
                "latency_seconds": 0.0,
            }
        if selected < 0 or selected >= 9 or table[selected] is None:
            raise RuntimeError("selected_slot_not_live_legal")
        record = {
            "part": self.part,
            "hand_idx": self.hand_idx,
            "decision_idx": self.decision_idx,
            "action_str_before": action_str,
            "street": int(state["st"]),
            "client_pos": int(client_pos),
            "hero_hole": list(hole_cards),
            "board": list(board),
            "baseline_slot": baseline,
            "baseline_increment": table[baseline],
            "baseline_logits_sha256": rs009.sha_obj(baseline_logits[0]),
            "selected_slot": selected,
            "selected_increment": table[selected],
            "resolver_attempted": bool(resolution["resolver_attempted"]),
            "selection_reason": resolution["selection_reason"],
            "error_fallback": bool(resolution["error_fallback"]),
            "latency_seconds": float(resolution["latency_seconds"]),
            "contract": contract,
            "contract_violations": 0 if contract["exact"] else 1,
            "state_identity_sha256": rs009.row_identity(row),
            "decision_trace_sha256": resolution.get("decision_trace_sha256"),
            "rollout_trace_sha256": resolution.get("rollout_trace_sha256"),
            "determinizations": resolution.get("determinizations"),
            "paired_statistics_by_slot": resolution.get("paired_statistics_by_slot"),
            "max_rollout_actions": resolution.get("max_rollout_actions"),
        }
        self.pending.append(record)
        self.decision_idx += 1
        return selected


def contract_test() -> dict[str, Any]:
    registration = verify_static_authority()
    total = 0
    hero = 0
    roundtrip = 0
    witness = 0
    tables = 0
    observations = 0
    for item in registration["frozen_inputs"]:
        if item["role"] != "rs009_runner":
            continue
    rs_registration = json.loads(rs009.PREREG.read_text(encoding="utf-8"))
    for item in rs_registration["frozen_authority_inputs"]:
        if not item["role"].startswith("h11_dump_part"):
            continue
        source = str(Path(item["path"]).resolve())
        with Path(item["path"]).open(encoding="utf-8") as handle:
            for line in handle:
                raw = json.loads(line)
                row = rs009.safe_row(raw, source)
                state = live.parse_action(row["action_str_before"])
                if "error" in state:
                    raise RuntimeError("historical_prefix_parse_failure")
                total += 1
                if serialize_action_state(state) != row["action_str_before"]:
                    raise RuntimeError("historical_prefix_roundtrip_failure")
                roundtrip += 1
                root = rs009.state_from_row(row)
                rs009.assert_witness(row, root)
                witness += 1
                if row["who"] == "hero":
                    hero += 1
                    rs_mask, rs_table = root.policy_table()
                    live_mask, live_table = live.build_action_table(state)
                    if not np.array_equal(rs_mask, live_mask) or rs_table != live_table:
                        raise RuntimeError("historical_live_table_failure")
                    tables += 1
                    rs_cards, rs_history, rs_extra, _, _ = rs009.observation(root)
                    commitments = live.compute_commitments(state)
                    live_cards = live.encode_cards(row["hero_hole"], row["board"], int(state["st"]))
                    live_history = live.encode_action_history(
                        state,
                        int(row["client_pos"]),
                        int(state["pos"]),
                        obs_version="v55",
                    )
                    live_extra = live.encode_extra(
                        [
                            live.STACK_SIZE - int(commitments["hero_total"]),
                            live.STACK_SIZE - int(commitments["opp_total"]),
                        ]
                    )
                    if not (
                        np.array_equal(rs_cards, live_cards)
                        and np.array_equal(rs_history, live_history)
                        and np.array_equal(rs_extra, live_extra)
                    ):
                        raise RuntimeError("historical_live_observation_failure")
                    observations += 1
    result = {
        "classification": "PASS / RS009_QUICK5K_NO_NETWORK_CONTRACT_TEST",
        "identity_sha256": IDENTITY,
        "source_rows": total,
        "hero_rows": hero,
        "roundtrip_exact": roundtrip,
        "witness_exact": witness,
        "live_table_exact": tables,
        "live_observation_exact": observations,
        "network_calls": 0,
        "files_written": 0,
    }
    if result != {
        "classification": "PASS / RS009_QUICK5K_NO_NETWORK_CONTRACT_TEST",
        "identity_sha256": IDENTITY,
        "source_rows": 29878,
        "hero_rows": 12564,
        "roundtrip_exact": 29878,
        "witness_exact": 29878,
        "live_table_exact": 12564,
        "live_observation_exact": 12564,
        "network_calls": 0,
        "files_written": 0,
    }:
        raise RuntimeError(f"contract_test_count_failure:{result}")
    return result


def run_session(
    *,
    part: int,
    hands: int,
    max_attempts: int,
    nonce: str,
    implementation_audit_sha256: str,
) -> int:
    verify_static_authority()
    if part not in EXPECTED_NONCES or nonce != EXPECTED_NONCES[part]:
        raise RuntimeError("part_nonce_failure")
    if hands != 1250 or max_attempts != 1500:
        raise RuntimeError("part_budget_failure")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("cuda_visibility_failure")
    if os.environ.get("RS007_DEVICE_MODE") != "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK":
        raise RuntimeError("device_mode_failure")
    if os.environ.get("RS007_NONCE") != nonce:
        raise RuntimeError("environment_nonce_failure")
    if not QUICK_ROOT.is_dir():
        raise RuntimeError("quick5k_root_missing")
    if not IMPL_AUDIT.is_file() or sha_file(IMPL_AUDIT) != implementation_audit_sha256:
        raise RuntimeError("implementation_audit_identity_failure")
    audit = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    if audit.get("classification") != "PASS / RS009_QUICK5K_IMPLEMENTATION_AUDIT_PASS_NETWORK_READY":
        raise RuntimeError("implementation_audit_nonpass")

    paths = {
        "result": QUICK_ROOT / f"part{part}_result.json",
        "hands": QUICK_ROOT / f"part{part}_hands.jsonl",
        "dump": QUICK_ROOT / f"part{part}_dump.jsonl",
        "decisions": QUICK_ROOT / f"part{part}_resolver_decisions.jsonl",
        "errors": QUICK_ROOT / f"part{part}_errors.jsonl",
    }
    if any(path.exists() for path in paths.values()):
        raise RuntimeError("part_output_collision")

    policy = ResolverPolicy(part=part, nonce=nonce)
    started = time.time()
    token: str | None = None
    successful = 0
    attempts = 0
    total_chips = 0
    winnings: list[int] = []
    with (
        paths["hands"].open("x", encoding="utf-8", newline="\n") as hands_fp,
        paths["dump"].open("x", encoding="utf-8", newline="\n") as dump_fp,
        paths["decisions"].open("x", encoding="utf-8", newline="\n") as decisions_fp,
        paths["errors"].open("x", encoding="utf-8", newline="\n") as errors_fp,
    ):
        while successful < hands and attempts < max_attempts:
            attempts += 1
            policy.begin_hand(successful)
            dump_before = dump_fp.tell()
            try:
                token, won = live.play_hand(
                    policy,
                    token,
                    "cuda:0",
                    verbose=False,
                    greedy=True,
                    obs_version="v55",
                    policy_mode="greedy",
                    dump_fp=dump_fp,
                    hand_idx=successful,
                )
                dump_fp.flush()
                if dump_fp.tell() <= dump_before:
                    write_line(
                        errors_fp,
                        {
                            "attempt": attempts,
                            "successful_before": successful,
                            "classification": "INCOMPLETE_HAND_NO_DUMP",
                        },
                    )
                    continue
            except Exception as error:
                write_line(
                    errors_fp,
                    {
                        "attempt": attempts,
                        "successful_before": successful,
                        "classification": "SESSION_EXCEPTION",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                )
                continue

            successful += 1
            total_chips += int(won)
            winnings.append(int(won))
            for record in policy.pending:
                write_line(decisions_fp, record)
            write_line(
                hands_fp,
                {
                    "part": part,
                    "attempted_hand": attempts,
                    "successful_hand": successful,
                    "hand_idx": successful - 1,
                    "winnings_chips": int(won),
                    "winnings_bb": float(won / live.BIG_BLIND),
                    "cumulative_chips": total_chips,
                    "cumulative_bb": float(total_chips / live.BIG_BLIND),
                    "hero_decisions": len(policy.pending),
                },
            )
            if successful % 100 == 0:
                print(
                    f"part={part} successful={successful} attempts={attempts} "
                    f"bb100={total_chips / live.BIG_BLIND / successful * 100:+.4f}",
                    flush=True,
                )

    if successful != hands:
        raise RuntimeError(f"part_incomplete:{successful}:{attempts}")
    bb_values = [value / live.BIG_BLIND for value in winnings]
    mean = statistics.fmean(bb_values)
    sd = statistics.stdev(bb_values) if len(bb_values) > 1 else 0.0
    half = 1.96 * sd / math.sqrt(len(bb_values)) * 100.0
    result = {
        "schema_version": "v5.rs009.quick5k.part_result.v1",
        "identity_sha256": IDENTITY,
        "rs009_identity_sha256": RS009_IDENTITY,
        "part": part,
        "nonce": nonce,
        "requested_successful_hands": hands,
        "successful_hands": successful,
        "attempted_hands": attempts,
        "total_chips": total_chips,
        "bb_per_100": mean * 100.0,
        "std_bb_per_hand": sd,
        "ci95_half_width_bb_per_100": half,
        "ci95_lower_bb_per_100": mean * 100.0 - half,
        "ci95_upper_bb_per_100": mean * 100.0 + half,
        "elapsed_seconds": time.time() - started,
        "checkpoint_sha256": rs009.sha_file(rs009.CHECKPOINT),
        "implementation_audit_sha256": implementation_audit_sha256,
        "artifacts": {
            name: {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha_file(path),
            }
            for name, path in paths.items()
            if name != "result"
        },
    }
    with paths["result"].open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("ContractTest", "Session"), required=True)
    parser.add_argument("--part", type=int)
    parser.add_argument("--hands", type=int)
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--nonce")
    parser.add_argument("--implementation-audit-sha256")
    args = parser.parse_args()
    if args.mode == "ContractTest":
        print(canonical(contract_test()))
        return 0
    if None in (args.part, args.hands, args.max_attempts) or not args.nonce or not args.implementation_audit_sha256:
        raise RuntimeError("session_arguments_missing")
    return run_session(
        part=args.part,
        hands=args.hands,
        max_attempts=args.max_attempts,
        nonce=args.nonce,
        implementation_audit_sha256=args.implementation_audit_sha256,
    )


if __name__ == "__main__":
    raise SystemExit(main())
