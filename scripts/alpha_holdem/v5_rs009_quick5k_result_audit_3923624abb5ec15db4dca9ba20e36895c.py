"""Independent hand-level evidence audit and exact RS009 quick5k judgment."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "3923624abb5ec15db4dca9ba20e36895c"
IDENTITY = "3923624abb5ec15db4dca9ba20e36895cc87e3b4db5089711c5734caa1155d70"
QUICK_ROOT = ROOT / "models" / "bench_v55_rs009_72e9bb6b8a4f4618aa6657710b66c5c9_greedy_quick5k_20260723"
OUTPUT = QUICK_ROOT / "result_audit.json"
PREREG = ROOT / "reports" / f"v5_rs009_quick5k_preregistration_{TOKEN}_20260723.json"
IMPLEMENTATION_AUDIT = ROOT / "reports" / f"v5_rs009_quick5k_implementation_audit_{TOKEN}_20260723.json"
CORRECTION_AUDIT = ROOT / "reports" / f"v5_rs009_quick5k_ps51_launcher_correction_audit_{TOKEN}_20260723.json"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
EXPECTED_CONTROL = {
    PREREG: "00f334383231d1ecb1655796498dd5e020e28d031b21a94ea9045c076e31672c",
    IMPLEMENTATION_AUDIT: "374e16348a27b251ae0fbe0ab8a7306d10e06a5563dc417a6bb8f41f9f8806ca",
    CORRECTION_AUDIT: "534605f07a43f17dd885c9abb5139ee51862ea750b31111495978d4add529bed",
    CHECKPOINT: "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13",
}
EXPECTED_DERIVED = {
    "launch_result_derived.json": "23b1694735f39e9590b63d6c9265b6b9d6122840d886e42687113aabbbdb01d1",
    "combined_ci.json": "359b31c261b80389e617804aac8bc9ef3e0c00425e3ff8eb032f924ca3aa4eae",
    "loss_report.json": "dd30d37865f2fb0d57803e93f5c2713bc1480410dbef4a44994d1dad2dd4ba98",
    "hand_review.json": "a3bca0404bf32b303ac68e7166b37e5e556e13a4a3c51b17d6c73d9e27585477",
    "result.json": "2d2b66974bcca005ee3153d457b8c629f05bfbe19733a168dd08558f8d2bfcf9",
}
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def action_increment(row: dict[str, Any]) -> str:
    return f"b{int(row['action_amount'])}" if row["action_move"] == "b" else str(row["action_move"])


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("result_audit_output_already_exists")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any = None) -> None:
        checks.append({"name": name, "pass": bool(passed), "evidence": evidence})

    for path, digest in EXPECTED_CONTROL.items():
        check(f"control_identity:{path.name}", path.is_file() and sha_file(path) == digest)
    for name, digest in EXPECTED_DERIVED.items():
        path = QUICK_ROOT / name
        check(f"derived_identity:{name}", path.is_file() and sha_file(path) == digest)

    invocation = json.loads((QUICK_ROOT / "invocation.json").read_text(encoding="utf-8-sig"))
    check(
        "invocation_exact",
        invocation.get("identity_sha256") == IDENTITY
        and invocation.get("parts") == 4
        and invocation.get("hands_per_part") == 1250
        and invocation.get("maximum_attempts_per_part") == 1500
        and invocation.get("policy_mode") == "greedy-direct"
        and invocation.get("nonces") == list(EXPECTED_NONCES.values()),
    )

    all_hands: list[dict[str, Any]] = []
    all_dump: list[dict[str, Any]] = []
    all_decisions: list[dict[str, Any]] = []
    raw_manifest: dict[str, Any] = {}
    join_failures: list[Any] = []
    for part in range(1, 5):
        paths = {
            "result": QUICK_ROOT / f"part{part}_result.json",
            "hands": QUICK_ROOT / f"part{part}_hands.jsonl",
            "dump": QUICK_ROOT / f"part{part}_dump.jsonl",
            "decisions": QUICK_ROOT / f"part{part}_resolver_decisions.jsonl",
            "errors": QUICK_ROOT / f"part{part}_errors.jsonl",
        }
        result = json.loads(paths["result"].read_text(encoding="utf-8"))
        hands = read_jsonl(paths["hands"])
        dump = read_jsonl(paths["dump"])
        decisions = read_jsonl(paths["decisions"])
        errors = read_jsonl(paths["errors"])
        for name, path in paths.items():
            raw_manifest[path.name] = {
                "bytes": path.stat().st_size,
                "sha256": sha_file(path),
            }
        check(
            f"part{part}_result_contract",
            result.get("identity_sha256") == IDENTITY
            and result.get("part") == part
            and result.get("nonce") == EXPECTED_NONCES[part]
            and result.get("requested_successful_hands") == 1250
            and result.get("successful_hands") == 1250
            and result.get("attempted_hands") == 1250
            and result.get("checkpoint_sha256") == EXPECTED_CONTROL[CHECKPOINT],
        )
        check(f"part{part}_hands_1250", len(hands) == 1250)
        check(f"part{part}_errors_zero", len(errors) == 0 and paths["errors"].stat().st_size == 0)
        check(
            f"part{part}_hand_sequence_exact",
            [int(row["hand_idx"]) for row in hands] == list(range(1250))
            and [int(row["successful_hand"]) for row in hands] == list(range(1, 1251))
            and [int(row["attempted_hand"]) for row in hands] == list(range(1, 1251)),
        )
        cumulative = 0
        cumulative_exact = True
        for row in hands:
            cumulative += int(row["winnings_chips"])
            cumulative_exact &= cumulative == int(row["cumulative_chips"])
        check(
            f"part{part}_cumulative_exact",
            cumulative_exact
            and cumulative == int(result["total_chips"])
            and abs(cumulative / 100 / 1250 * 100 - float(result["bb_per_100"])) < 1e-12,
        )

        dump_by_hand: dict[int, list[dict[str, Any]]] = defaultdict(list)
        decisions_by_hand: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in dump:
            dump_by_hand[int(row["hand_idx"])].append(row)
        for row in decisions:
            decisions_by_hand[int(row["hand_idx"])].append(row)
        dump_exact = set(dump_by_hand) == set(range(1250))
        for hand_idx in range(1250):
            rows = sorted(dump_by_hand[hand_idx], key=lambda row: int(row["move_idx"]))
            hero_rows = [row for row in rows if row["who"] == "hero"]
            decision_rows = sorted(decisions_by_hand[hand_idx], key=lambda row: int(row["decision_idx"]))
            if (
                [int(row["move_idx"]) for row in rows] != list(range(len(rows)))
                or any(int(row["winnings_hero"]) != int(hands[hand_idx]["winnings_chips"]) for row in rows)
                or len(hero_rows) != len(decision_rows)
            ):
                dump_exact = False
                join_failures.append([part, hand_idx, "count_or_sequence"])
                continue
            for hero_row, decision in zip(hero_rows, decision_rows, strict=True):
                exact = (
                    decision["action_str_before"] == hero_row["action_str_before"]
                    and int(decision["street"]) == int(hero_row["street"])
                    and decision["selected_increment"] == action_increment(hero_row)
                    and decision["contract"]["exact"] is True
                    and all(decision["contract"]["checks"].values())
                    and int(decision["contract_violations"]) == 0
                )
                if not exact:
                    dump_exact = False
                    join_failures.append([part, hand_idx, decision["decision_idx"]])
        check(f"part{part}_hand_dump_and_decision_join_exact", dump_exact, join_failures[-10:])

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

    check("raw_hands_exact_5000", len(all_hands) == 5000)
    check("raw_dump_nonempty", len(all_dump) == 31606)
    check("raw_resolver_decisions_exact", len(all_decisions) == 13246)
    check("all_hand_decision_joins_exact", not join_failures, join_failures[-20:])

    winnings = [float(row["winnings_bb"]) for row in all_hands]
    total_chips = sum(int(row["winnings_chips"]) for row in all_hands)
    mean = statistics.fmean(winnings)
    sd = statistics.stdev(winnings)
    half = 1.96 * sd / math.sqrt(5000) * 100.0
    bb100 = mean * 100.0
    postflop = [row for row in all_decisions if int(row["street"]) > 0]
    attempted = [row for row in postflop if row["resolver_attempted"] is True]
    fallback = [row for row in attempted if row["error_fallback"] is True]
    attempt_rate = len(attempted) / len(postflop)
    fallback_rate = len(fallback) / len(attempted)
    violations = sum(int(row["contract_violations"]) for row in all_decisions)
    played_aggression = sum(int(row["selected_slot"]) >= 2 for row in postflop) / len(postflop)
    greedy_aggression = sum(int(row["baseline_slot"]) >= 2 for row in postflop) / len(postflop)
    recomputed = {
        "hands": 5000,
        "total_chips": total_chips,
        "bb_per_100": bb100,
        "std_bb_per_hand": sd,
        "ci95_half_width_bb_per_100": half,
        "ci95_lower_bb_per_100": bb100 - half,
        "ci95_upper_bb_per_100": bb100 + half,
        "hero_decisions": len(all_decisions),
        "postflop_decisions": len(postflop),
        "resolver_attempt_rate": attempt_rate,
        "fallback_rate": fallback_rate,
        "contract_violations": violations,
        "played_postflop_raise_plus_allin_rate": played_aggression,
        "greedy_postflop_raise_plus_allin_rate": greedy_aggression,
    }
    derived_result = json.loads((QUICK_ROOT / "result.json").read_text(encoding="utf-8"))
    check(
        "metrics_recomputed_exact",
        all(derived_result["metrics"].get(key) == value for key, value in recomputed.items()),
        recomputed,
    )
    expected_gates = {
        "bb_per_100_directional": bb100 > -126.1726,
        "resolver_attempt_rate": attempt_rate >= 0.95,
        "fallback_rate": fallback_rate <= 0.02,
        "contract_violations": violations == 0,
        "played_aggression": played_aggression <= 0.8,
        "greedy_aggression": greedy_aggression <= 0.8,
    }
    check(
        "registered_scientific_gates_exact",
        all(derived_result["gates"].get(key) == value for key, value in expected_gates.items())
        and expected_gates
        == {
            "bb_per_100_directional": False,
            "resolver_attempt_rate": True,
            "fallback_rate": True,
            "contract_violations": True,
            "played_aggression": False,
            "greedy_aggression": False,
        },
        expected_gates,
    )
    check(
        "directional_nonpass_classification_exact",
        derived_result.get("classification")
        == "NONPASS / RS009_QUICK5K_DIRECTIONAL_OR_MECHANISM_GATE_NONPASS"
        and derived_result.get("strength_authority") == "NONE",
    )

    review = json.loads((QUICK_ROOT / "hand_review.json").read_text(encoding="utf-8"))
    worst_indices = [
        int(row["global_hand_idx"])
        for row in sorted(all_hands, key=lambda row: (float(row["winnings_bb"]), int(row["global_hand_idx"])))[:20]
    ]
    check(
        "hand_review_exact",
        [int(row["global_hand_idx"]) for row in review["reviewed_hands"]] == worst_indices,
    )
    loss = json.loads((QUICK_ROOT / "loss_report.json").read_text(encoding="utf-8"))
    check(
        "loss_report_exact",
        loss.get("hands") == 5000
        and loss.get("bb_per_100") == bb100
        and loss["resolver"]["resolver_attempt_rate"] == attempt_rate
        and loss["resolver"]["fallback_rate"] == fallback_rate,
    )

    passed = all(item["pass"] for item in checks)
    audit = {
        "schema_version": "v5.rs009.quick5k.result_audit.v1",
        "identity_sha256": IDENTITY,
        "classification": (
            "PASS / RS009_QUICK5K_INDEPENDENT_EVIDENCE_AUDIT_NONPASS_JUDGMENT_EXACT"
            if passed
            else "FAIL_CLOSED / RS009_QUICK5K_EVIDENCE_AUDIT_FAILURE"
        ),
        "scientific_judgment": (
            "RS009_QUICK5K_DIRECTIONAL_NONPASS_REJECT_RESOLVER_AND_SCIENTIFICALLY_RERANK"
            if passed
            else "NO_RESULT"
        ),
        "checks": checks,
        "pass_count": sum(item["pass"] for item in checks),
        "check_count": len(checks),
        "fail_count": sum(not item["pass"] for item in checks),
        "recomputed_metrics": recomputed,
        "raw_artifact_manifest": raw_manifest,
        "complete_hand_level_evidence": passed,
        "promotion_20k": False,
        "strength_authority": "NONE",
    }
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(audit, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
