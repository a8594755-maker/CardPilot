"""Build deterministic RS009 quick5k reporting from immutable raw part evidence."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "3923624abb5ec15db4dca9ba20e36895c"
IDENTITY = "3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70"
QUICK_ROOT = ROOT / "models" / "bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723"
OUTPUTS = {
    "launcher": QUICK_ROOT / "launch_result_derived.json",
    "ci": QUICK_ROOT / "combined_ci.json",
    "loss": QUICK_ROOT / "loss_report.json",
    "review": QUICK_ROOT / "hand_review.json",
    "result": QUICK_ROOT / "result.json",
}


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def main() -> int:
    if any(path.exists() for path in OUTPUTS.values()):
        raise RuntimeError("derived_output_collision")

    all_hands: list[dict[str, Any]] = []
    all_dump: list[dict[str, Any]] = []
    all_decisions: list[dict[str, Any]] = []
    part_results = []
    raw_manifest: dict[str, Any] = {}
    for part in range(1, 5):
        result_path = QUICK_ROOT / f"part{part}_result.json"
        hands_path = QUICK_ROOT / f"part{part}_hands.jsonl"
        dump_path = QUICK_ROOT / f"part{part}_dump.jsonl"
        decisions_path = QUICK_ROOT / f"part{part}_resolver_decisions.jsonl"
        errors_path = QUICK_ROOT / f"part{part}_errors.jsonl"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        hands = read_jsonl(hands_path)
        dump = read_jsonl(dump_path)
        decisions = read_jsonl(decisions_path)
        errors = read_jsonl(errors_path)
        if (
            result["identity_sha256"] != IDENTITY
            or result["part"] != part
            or result["successful_hands"] != 1250
            or result["attempted_hands"] != 1250
            or len(hands) != 1250
            or errors
        ):
            raise RuntimeError(f"part_raw_contract_failure:{part}")
        for row in hands:
            row["global_hand_idx"] = (part - 1) * 1250 + int(row["hand_idx"])
        for row in dump:
            row["part"] = part
            row["global_hand_idx"] = (part - 1) * 1250 + int(row["hand_idx"])
        for row in decisions:
            row["global_hand_idx"] = (part - 1) * 1250 + int(row["hand_idx"])
        all_hands.extend(hands)
        all_dump.extend(dump)
        all_decisions.extend(decisions)
        part_results.append(result)
        for path in (result_path, hands_path, dump_path, decisions_path, errors_path):
            raw_manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha_file(path),
            }

    winnings_bb = [float(row["winnings_bb"]) for row in all_hands]
    total_chips = sum(int(row["winnings_chips"]) for row in all_hands)
    mean = statistics.fmean(winnings_bb)
    sd = statistics.stdev(winnings_bb)
    half = 1.96 * sd / math.sqrt(len(winnings_bb)) * 100.0
    bb100 = mean * 100.0
    ci = {
        "schema_version": "v5.rs009.quick5k.combined_ci.v1",
        "identity_sha256": IDENTITY,
        "hands": len(winnings_bb),
        "total_chips": total_chips,
        "bb_per_100": bb100,
        "std_bb_per_hand": sd,
        "ci95_half_width_bb_per_100": half,
        "ci95_lower_bb_per_100": bb100 - half,
        "ci95_upper_bb_per_100": bb100 + half,
    }

    decisions_by_hand: dict[int, list[dict[str, Any]]] = defaultdict(list)
    dump_by_hand: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in all_decisions:
        decisions_by_hand[int(row["global_hand_idx"])].append(row)
    for row in all_dump:
        dump_by_hand[int(row["global_hand_idx"])].append(row)

    postflop = [row for row in all_decisions if int(row["street"]) > 0]
    attempted = [row for row in postflop if row["resolver_attempted"] is True]
    fallback = [row for row in attempted if row["error_fallback"] is True]
    contract_violations = sum(int(row["contract_violations"]) for row in all_decisions)
    selected_aggressive = sum(int(row["selected_slot"]) >= 2 for row in postflop)
    baseline_aggressive = sum(int(row["baseline_slot"]) >= 2 for row in postflop)
    resolver_attempt_rate = len(attempted) / len(postflop) if postflop else 0.0
    fallback_rate = len(fallback) / len(attempted) if attempted else 0.0
    played_aggression_rate = selected_aggressive / len(postflop) if postflop else 0.0
    greedy_aggression_rate = baseline_aggressive / len(postflop) if postflop else 0.0

    by_position: dict[str, list[float]] = defaultdict(list)
    for row in all_hands:
        hand_dump = dump_by_hand[int(row["global_hand_idx"])]
        position = f"client_pos_{int(hand_dump[0]['client_pos'])}"
        by_position[position].append(float(row["winnings_bb"]))
    loss_report = {
        "schema_version": "v5.rs009.quick5k.loss_report.v1",
        "identity_sha256": IDENTITY,
        "hands": len(all_hands),
        "bb_per_100": bb100,
        "position": {
            key: {
                "hands": len(values),
                "bb_per_100": statistics.fmean(values) * 100.0,
                "total_bb": sum(values),
            }
            for key, values in sorted(by_position.items())
        },
        "resolver": {
            "hero_decisions": len(all_decisions),
            "postflop_decisions": len(postflop),
            "attempted": len(attempted),
            "resolver_attempt_rate": resolver_attempt_rate,
            "fallback": len(fallback),
            "fallback_rate": fallback_rate,
            "contract_violations": contract_violations,
            "selected_postflop_raise_plus_allin_rate": played_aggression_rate,
            "baseline_postflop_raise_plus_allin_rate": greedy_aggression_rate,
            "selection_reasons": dict(Counter(row["selection_reason"] for row in all_decisions)),
        },
    }

    worst = sorted(all_hands, key=lambda row: (float(row["winnings_bb"]), int(row["global_hand_idx"])))[:20]
    reviewed = []
    for hand in worst:
        global_idx = int(hand["global_hand_idx"])
        rows = sorted(dump_by_hand[global_idx], key=lambda row: int(row["move_idx"]))
        reviewed.append(
            {
                "global_hand_idx": global_idx,
                "part": int(hand["part"]),
                "hand_idx": int(hand["hand_idx"]),
                "winnings_bb": float(hand["winnings_bb"]),
                "client_pos": int(rows[0]["client_pos"]),
                "hero_hole": rows[0]["hero_hole"],
                "board": rows[-1]["board"],
                "action_sequence": [
                    f"b{int(row['action_amount'])}" if row["action_move"] == "b" else row["action_move"]
                    for row in rows
                ],
                "hero_decisions": len(decisions_by_hand[global_idx]),
            }
        )
    hand_review = {
        "schema_version": "v5.rs009.quick5k.hand_review.v1",
        "identity_sha256": IDENTITY,
        "method": "DETERMINISTIC_WORST20_BY_WINNINGS_THEN_GLOBAL_INDEX",
        "reviewed_hands": reviewed,
    }

    gates = {
        "complete_hands_exact": len(all_hands) == 5000,
        "parts_exact": len(part_results) == 4,
        "hands_per_part_exact": all(result["successful_hands"] == 1250 for result in part_results),
        "bb_per_100_directional": bb100 > -126.1726,
        "resolver_attempt_rate": resolver_attempt_rate >= 0.95,
        "fallback_rate": fallback_rate <= 0.02,
        "contract_violations": contract_violations == 0,
        "played_aggression": played_aggression_rate <= 0.8,
        "greedy_aggression": greedy_aggression_rate <= 0.8,
        "hand_jsonl_complete": len(all_hands) == 5000,
        "decision_dump_present": len(all_dump) > 0,
        "resolver_decisions_present": len(all_decisions) > 0,
        "ci_complete": True,
        "loss_report_complete": True,
        "hand_review_complete": len(reviewed) == 20,
    }
    result = {
        "schema_version": "v5.rs009.quick5k.result.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS009_QUICK5K_RAW_AND_DERIVED_GATES_PASS_PENDING_INDEPENDENT_AUDIT"
            if all(gates.values())
            else "NONPASS / RS009_QUICK5K_DIRECTIONAL_OR_MECHANISM_GATE_NONPASS"
        ),
        "gates": gates,
        "pass_count": sum(gates.values()),
        "check_count": len(gates),
        "metrics": {
            **ci,
            "resolver_attempt_rate": resolver_attempt_rate,
            "fallback_rate": fallback_rate,
            "contract_violations": contract_violations,
            "played_postflop_raise_plus_allin_rate": played_aggression_rate,
            "greedy_postflop_raise_plus_allin_rate": greedy_aggression_rate,
            "hero_decisions": len(all_decisions),
            "postflop_decisions": len(postflop),
            "dump_rows": len(all_dump),
        },
        "raw_manifest": raw_manifest,
        "strength_authority": "NONE",
    }
    launcher = {
        "schema_version": "v5.rs009.quick5k.launch_result_derived.v1",
        "identity_sha256": IDENTITY,
        "classification": "PASS / RS009_QUICK5K_ALL_PARTS_COMPLETE_DERIVED_FROM_PART_RESULTS",
        "foreground_launcher_result": "ABSENT_AFTER_MONITOR_TIMEOUT",
        "part_result_sha256": {
            f"part{part}_result.json": sha_file(QUICK_ROOT / f"part{part}_result.json")
            for part in range(1, 5)
        },
    }
    write_json(OUTPUTS["launcher"], launcher)
    write_json(OUTPUTS["ci"], ci)
    write_json(OUTPUTS["loss"], loss_report)
    write_json(OUTPUTS["review"], hand_review)
    write_json(OUTPUTS["result"], result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
