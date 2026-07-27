#!/usr/bin/env python3
"""Independent exact evidence audit for an CT003 standard quick5k bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path


CHECKPOINT_SHA256 = {
    "ct003_mc_target": "76b85c5bd377533329424140d01352075e44b6a1aeb5796828fee60f34037f62",
}
CHECKPOINT_PATH = {
    "ct003_mc_target": (
        "C:\\Users\\a8594\\CardPilot\\models\\alpha_holdem_v5_hybrid\\"
        "v5_ct003_7296402ab1ddaadd86ebde1795d0f2ad_20260723\\"
        "mc_target_stagea\\latest.pt"
    ),
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def close(a: float, b: float, tolerance: float = 1e-9) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tolerance)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=sorted(CHECKPOINT_SHA256), required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--stdout-log", required=True)
    parser.add_argument("--stderr-log", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    stdout_log = Path(args.stdout_log).resolve()
    stderr_log = Path(args.stderr_log).resolve()
    output = Path(args.out).resolve()
    checkpoint = Path(CHECKPOINT_PATH[args.arm])
    prefix = root / f"bench_v55_{args.tag}"
    checks: dict[str, bool] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    check("checkpoint_exists", checkpoint.is_file())
    check("checkpoint_sha256", sha256_path(checkpoint) == CHECKPOINT_SHA256[args.arm])
    check("launcher_stderr_empty", stderr_log.is_file() and stderr_log.stat().st_size == 0)
    launcher_text = stdout_log.read_text(encoding="utf-8", errors="replace")
    check("launcher_complete_marker", "=== Bench complete ===" in launcher_text)

    all_hands: list[dict] = []
    all_dump_rows: list[dict] = []
    part_results: list[dict] = []
    artifacts: dict[str, dict] = {}
    for part in range(1, 5):
        base = Path(f"{prefix}_part{part}")
        paths = {
            "result": Path(str(base) + ".json"),
            "hands": Path(str(base) + "_hands.jsonl"),
            "dump": Path(str(base) + "_dump.jsonl"),
            "stdout": Path(str(base) + ".log"),
            "stderr": Path(str(base) + "_err.log"),
        }
        for role, path in paths.items():
            check(f"part{part}_{role}_exists", path.is_file())
        check(f"part{part}_stderr_empty", paths["stderr"].stat().st_size == 0)
        result = json.loads(paths["result"].read_text(encoding="utf-8"))
        hands = read_jsonl(paths["hands"])
        dumps = read_jsonl(paths["dump"])
        part_results.append(result)
        all_hands.extend(hands)
        all_dump_rows.extend(dumps)
        check(f"part{part}_requested_1250", int(result.get("requested_hands", -1)) == 1250)
        check(f"part{part}_successful_1250", int(result.get("successful_hands", -1)) == 1250)
        check(f"part{part}_policy_greedy", result.get("policy_mode") == "greedy")
        check(f"part{part}_strategy_model", result.get("strategy") == "model")
        check(f"part{part}_obs_v55", result.get("obs_version") == "v55")
        check(f"part{part}_device_cpu", result.get("device") == "cpu")
        check(f"part{part}_model_path", str(Path(result.get("model", "")).resolve()) == str(checkpoint.resolve()))
        check(f"part{part}_hand_count", len(hands) == 1250)
        check(
            f"part{part}_attempt_sequence",
            [int(row.get("attempted_hand", -1)) for row in hands] == list(range(1, 1251)),
        )
        check(
            f"part{part}_successful_sequence",
            [int(row.get("successful_hand", -1)) for row in hands] == list(range(1, 1251)),
        )
        chip_sum = sum(int(row["winnings_chips"]) for row in hands)
        check(f"part{part}_chip_sum", chip_sum == int(result.get("total_chips", 1)))
        check(f"part{part}_cumulative_final", int(hands[-1]["cumulative_chips"]) == chip_sum)
        check(f"part{part}_dump_nonempty", bool(dumps))
        check(
            f"part{part}_dump_hand_coverage",
            {int(row.get("hand_idx", -1)) for row in dumps} == set(range(1250)),
        )
        hand_winnings = {index: int(row["winnings_chips"]) for index, row in enumerate(hands)}
        check(
            f"part{part}_dump_winnings_match",
            all(int(row["winnings_hero"]) == hand_winnings[int(row["hand_idx"])] for row in dumps),
        )
        for role, path in paths.items():
            artifacts[str(path)] = {"bytes": path.stat().st_size, "sha256": sha256_path(path)}

    check("exact_total_hands", len(all_hands) == 5000)
    check("dump_rows_exact", len(all_dump_rows) > 0)
    total_chips = sum(int(row["winnings_chips"]) for row in all_hands)
    check("total_chips_part_results", total_chips == sum(int(row["total_chips"]) for row in part_results))
    values_bb = [float(row["winnings_bb"]) for row in all_hands]
    mean_bb = statistics.fmean(values_bb)
    std_bb = statistics.stdev(values_bb)
    ci95_bb100 = 1.96 * std_bb / math.sqrt(len(values_bb)) * 100.0
    bb100 = mean_bb * 100.0

    ci_path = Path(str(prefix) + "_ci_summary.json")
    loss_path = Path(str(prefix) + "_loss_report.json")
    promotion_path = Path(str(prefix) + "_promotion_gate.json")
    artifact_audit_path = root / "artifact_audit.json"
    hand_review_path = root / "hand_review.json"
    fixed = {
        "ci": ci_path,
        "loss": loss_path,
        "promotion": promotion_path,
        "artifact_audit": artifact_audit_path,
        "hand_review": hand_review_path,
    }
    for role, path in fixed.items():
        check(f"{role}_exists", path.is_file())
        artifacts[str(path)] = {"bytes": path.stat().st_size, "sha256": sha256_path(path)}

    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    loss = json.loads(loss_path.read_text(encoding="utf-8"))
    artifact_audit = json.loads(artifact_audit_path.read_text(encoding="utf-8"))
    hand_review = json.loads(hand_review_path.read_text(encoding="utf-8"))
    check("ci_hands", int(ci.get("hands", -1)) == 5000)
    check("ci_total_bb", close(ci.get("total_bb"), total_chips / 100.0))
    check("ci_bb100_recomputed", close(ci.get("bb_per_100"), bb100, 1e-10))
    check("ci_std_recomputed", close(ci.get("std_bb_per_hand"), std_bb, 1e-10))
    check("ci_half_width_recomputed", close(ci.get("ci95_bb_per_100"), ci95_bb100, 1e-10))
    check("ci_lower_recomputed", close(ci.get("lower_bound_bb_per_100"), bb100 - ci95_bb100, 1e-10))
    check("ci_upper_recomputed", close(ci.get("upper_bound_bb_per_100"), bb100 + ci95_bb100, 1e-10))
    check("ci_inputs_exact", [str(Path(value).resolve()) for value in ci.get("input_files", [])] == [
        str(Path(f"{prefix}_part{part}_hands.jsonl").resolve()) for part in range(1, 5)
    ])
    check("loss_hands", int(loss.get("hands", -1)) == 5000)
    check("loss_total_chips", int(loss.get("total_chips", 1)) == total_chips)
    check("loss_bb100", close(loss.get("bb_per_100"), bb100, 1e-10))
    check("artifact_audit_pass", artifact_audit.get("overall") == "PASS" and int(artifact_audit.get("fail_count", -1)) == 0)
    check("artifact_audit_counts", int(artifact_audit.get("total_hands", -1)) == 5000 and int(artifact_audit.get("total_decisions", -1)) == len(all_dump_rows))
    check("hand_review_pass", hand_review.get("overall") == "PASS")
    check("hand_review_diagnostic", hand_review.get("evidence_class") == "diagnostic")
    check("hand_review_policy", hand_review.get("policy_mode") == "greedy-direct")
    check("hand_review_score", close((hand_review.get("ci") or {}).get("bb_per_100"), round(bb100, 3), 1e-9))

    artifacts[str(checkpoint)] = {"bytes": checkpoint.stat().st_size, "sha256": sha256_path(checkpoint)}
    artifacts[str(stdout_log)] = {"bytes": stdout_log.stat().st_size, "sha256": sha256_path(stdout_log)}
    artifacts[str(stderr_log)] = {"bytes": stderr_log.stat().st_size, "sha256": sha256_path(stderr_log)}
    failed = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "schema_version": "v5.ct003.quick5k_result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "arm": args.arm,
        "tag": args.tag,
        "passed": sum(checks.values()),
        "failed": len(failed),
        "failed_checks": failed,
        "checks": checks,
        "result": {
            "hands": len(all_hands),
            "decision_rows": len(all_dump_rows),
            "total_chips": total_chips,
            "bb_per_100": bb100,
            "ci95_lower_bb_per_100": bb100 - ci95_bb100,
            "ci95_upper_bb_per_100": bb100 + ci95_bb100,
            "checkpoint_sha256": CHECKPOINT_SHA256[args.arm],
            "strength_authority": "DIRECTIONAL_ONLY",
        },
        "artifacts": artifacts,
        "next_authority": "REGISTERED_CT003_STAGE_A_GATE_JUDGMENT"
        if not failed
        else "STOP_INCOMPLETE_EXTERNAL_BUNDLE",
    }
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
