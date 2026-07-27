#!/usr/bin/env python3
"""Deterministic reporting-only VR002C1 resource-throughput admission."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date
from decimal import Decimal, getcontext
from fractions import Fraction
from pathlib import Path
from typing import Any


IDENTITY = "8d3cb2f1a897d1b9228b14ee7043db496c7a319c4af7318aae4e0103ac534a4d"
METRICS_SHA256 = "549c807b2b63f4b25b91ebd6908f9c31f8ccdd286ef95e7ea2468b4c540f6171"
T0_TEXT = "2026-07-23T11:59:06.7131337-04:00"
TICKS = 10_000_000
WARMUP_TICKS = 1_800 * TICKS
BLOCK_TICKS = 900 * TICKS
BOOTSTRAP_REPLICATES = 200_000
SOURCE_HANDS = 576_021_901
SOURCE_ITERATION = 35_051
TARGET_MAX_HANDS = 5_050_000
INFLATED_HANDS = 6_312_500
PER_ARM_CAP_SECONDS = 57_600
ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d{1,7}))?(Z|[+-]\d{2}:\d{2})$"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(row: dict[str, Any]) -> str:
    payload = dict(row)
    payload.pop("record_sha256", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def iso100ns(text: str) -> int:
    match = ISO_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid explicit-offset ISO timestamp: {text!r}")
    year, month, day, hour, minute, second = map(int, match.groups()[:6])
    fraction = (match.group(7) or "").ljust(7, "0")
    offset = match.group(8)
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError(f"invalid time fields: {text!r}")
    ordinal_seconds = (
        (date(year, month, day).toordinal() - date(1970, 1, 1).toordinal()) * 86_400
        + hour * 3_600
        + minute * 60
        + second
    )
    if offset != "Z":
        sign = 1 if offset[0] == "+" else -1
        offset_hour, offset_minute = map(int, offset[1:].split(":"))
        if offset_hour > 23 or offset_minute > 59:
            raise ValueError(f"invalid UTC offset: {text!r}")
        ordinal_seconds -= sign * (offset_hour * 3_600 + offset_minute * 60)
    return ordinal_seconds * TICKS + int(fraction)


def rate(blocks: list[dict[str, int]]) -> Fraction:
    return Fraction(
        sum(block["admitted"] for block in blocks) * TICKS,
        sum(block["ticks"] for block in blocks),
    )


def decimal_text(value: Fraction) -> str:
    getcontext().prec = 50
    return format(Decimal(value.numerator) / Decimal(value.denominator), "f")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    metrics_path = Path(args.metrics).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite admission result: {out}")
    if sha256_path(metrics_path) != METRICS_SHA256:
        raise RuntimeError("frozen metrics identity mismatch")

    raw = metrics_path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    timestamps = [iso100ns(row["recorded_at"]) for row in rows]
    admitted = [int(row["admitted_hands"]) for row in rows]
    excluded = [int(row["mixed_or_stale_hands"]) for row in rows]
    complete = [int(row["complete_hands"]) for row in rows]
    integrity = {
        "exact_161_rows_final_newline_no_blank":
            len(rows) == 161 and raw.endswith(b"\n") and all(line.strip() for line in lines),
        "identity_exact": all(row.get("identity") == IDENTITY for row in rows),
        "record_hashes_exact": all(
            row.get("record_sha256") == canonical_hash(row) for row in rows
        ),
        "iterations_contiguous":
            [int(row["iteration"]) for row in rows]
            == list(range(SOURCE_ITERATION + 1, SOURCE_ITERATION + 1 + len(rows))),
        "timestamps_strictly_monotone":
            all(left < right for left, right in zip(timestamps, timestamps[1:])),
        "counters_monotone": all(
            all(left <= right for left, right in zip(series, series[1:]))
            for series in (admitted, excluded, complete)
        ),
        "counter_identities_exact": all(
            int(row["new_hands"]) == int(row["complete_hands"])
            and int(row["total_hands"]) == SOURCE_HANDS + int(row["new_hands"])
            and int(row["admitted_hands"]) + int(row["mixed_or_stale_hands"])
            == int(row["complete_hands"])
            and int(row["stale_assignment_hands"])
            <= int(row["mixed_or_stale_hands"])
            for row in rows
        ),
        "terminal_counts_exact":
            complete[-1] == 3_064_100
            and admitted[-1] == 2_649_478
            and excluded[-1] == 414_622
            and int(rows[-1]["stale_assignment_hands"]) == 148_897,
    }
    if not all(integrity.values()):
        raise RuntimeError(
            "frozen metrics integrity nonpass: "
            + ",".join(name for name, passed in integrity.items() if not passed)
        )

    t0 = iso100ns(T0_TEXT)
    start_index = min(
        index for index, value in enumerate(timestamps)
        if value >= t0 + WARMUP_TICKS
    )
    blocks: list[dict[str, int]] = []
    start = start_index
    while True:
        endpoints = [
            index for index in range(start + 1, len(rows))
            if timestamps[index] - timestamps[start] >= BLOCK_TICKS
        ]
        if not endpoints:
            break
        end = min(endpoints)
        blocks.append(
            {
                "start_row_zero_based": start,
                "end_row_zero_based": end,
                "admitted": admitted[end] - admitted[start],
                "excluded": excluded[end] - excluded[start],
                "complete": complete[end] - complete[start],
                "ticks": timestamps[end] - timestamps[start],
            }
        )
        start = end
    tail = blocks[len(blocks) - len(blocks) // 2:]

    bounds: dict[str, Fraction] = {}
    selected_samples: dict[str, dict[str, int]] = {}
    for segment_name, segment in (("all", blocks), ("tail", tail)):
        count = len(segment)
        for length in (2, 4, 8):
            rates: list[tuple[Fraction, int, int, int]] = []
            draws = math.ceil(count / length)
            for replicate in range(BOOTSTRAP_REPLICATES):
                indices: list[int] = []
                for draw in range(draws):
                    message = (
                        f"VRP-P01-HPS-v1|{segment_name}|{length}|{replicate}|{draw}"
                    ).encode("ascii")
                    start_at = int.from_bytes(
                        hashlib.sha256(message).digest()[:8], "big"
                    ) % count
                    indices.extend((start_at + offset) % count for offset in range(length))
                sample = [segment[index] for index in indices[:count]]
                hands = sum(block["admitted"] for block in sample)
                ticks = sum(block["ticks"] for block in sample)
                rates.append((Fraction(hands * TICKS, ticks), replicate, hands, ticks))
            rates.sort(key=lambda item: item[0])
            selected = rates[333]
            key = f"{segment_name}_ell{length}"
            bounds[key] = selected[0]
            selected_samples[key] = {
                "order_statistic_one_based": 334,
                "representative_replicate": selected[1],
                "admitted": selected[2],
                "ticks": selected[3],
            }

    drift: list[tuple[str, Fraction, int, int]] = []
    for index in range(0, len(blocks) - 4 + 1):
        sample = blocks[index:index + 4]
        drift.append(
            (
                f"rolling4_{index + 1}_{index + 4}",
                rate(sample),
                sum(block["admitted"] for block in sample),
                sum(block["ticks"] for block in sample),
            )
        )
    for length in (4, 8, 12):
        if len(blocks) >= length:
            sample = blocks[-length:]
            drift.append(
                (
                    f"trailing{length}",
                    rate(sample),
                    sum(block["admitted"] for block in sample),
                    sum(block["ticks"] for block in sample),
                )
            )
    drift_name, drift_floor, drift_hands, drift_ticks = min(
        drift, key=lambda item: item[1]
    )
    bootstrap_floor = min(bounds.values())
    hps_lcb = min(bootstrap_floor, drift_floor)

    postwarmup_gaps = [
        timestamps[index] - timestamps[index - 1]
        for index in range(start_index + 1, len(rows))
    ]
    d99_rank = math.ceil(0.99 * len(postwarmup_gaps))
    d99_ticks = sorted(postwarmup_gaps)[d99_rank - 1]
    finalization_seconds = max(Fraction(600), Fraction(2 * d99_ticks, TICKS))
    warmup_seconds = Fraction(timestamps[start_index] - t0, TICKS)
    pure_bound_seconds = Fraction(TARGET_MAX_HANDS, 1) / hps_lcb
    inflated_bound_seconds = Fraction(INFLATED_HANDS, 1) / hps_lcb
    overhead_allowance_seconds = pure_bound_seconds / 4
    direct_bound_seconds = warmup_seconds + pure_bound_seconds + finalization_seconds
    rate_gate = (
        hps_lcb.numerator * PER_ARM_CAP_SECONDS
        >= INFLATED_HANDS * hps_lcb.denominator
    )
    overhead_gate = (
        warmup_seconds + finalization_seconds <= overhead_allowance_seconds
    )
    per_arm_cap_gate = inflated_bound_seconds <= PER_ARM_CAP_SECONDS
    pair_cap_gate = 2 * inflated_bound_seconds <= PER_ARM_CAP_SECONDS

    result = {
        "schema_version": "v5.vr002c1.reporting_only_throughput_admission.v1",
        "recorded_at": "2026-07-23T21:30:00-04:00",
        "status": "VRP-P01_RESOURCE_ADMISSION_NONPASS",
        "identity_sha256": IDENTITY,
        "authority": {
            "metrics_sha256": METRICS_SHA256,
            "resource_evidence_only": True,
            "mechanism_authority": False,
            "checkpoint_authority": False,
            "strength_authority": False,
            "process_exit_cause": "UNPROVEN",
        },
        "method": {
            "integer_time_unit": "100ns_UTC_ticks",
            "warmup_seconds": 1800,
            "block_minimum_seconds": 900,
            "block_endpoint": "first_observed_row_at_or_after_start_plus_900s",
            "block_inclusion": "(start_row,end_row]_cumulative_difference",
            "terminal_short_fragment": "discard_zero_credit",
            "eligible_numerator": "admitted_generation_and_assignment_pure_hands",
            "bootstrap": {
                "replicates": BOOTSTRAP_REPLICATES,
                "segments": ["all", "tail_last_floor_B_over_2"],
                "circular_block_lengths": [2, 4, 8],
                "counter_message":
                    "VRP-P01-HPS-v1|segment|ell|replicate_zero_based|draw_zero_based",
                "counter_value": "sha256_first8_big_endian_mod_segment_length",
                "familywise_one_sided_alpha": "0.01",
                "order_statistic_one_based": 334,
                "exact_fraction_ordering": True,
            },
            "drift_set": "all_contiguous_rolling4_plus_trailing4_8_12",
            "gate_arithmetic": "exact_integer_cross_product",
        },
        "integrity": integrity,
        "blocking": {
            "start_row_zero_based": start_index,
            "anchor_recorded_at": rows[start_index]["recorded_at"],
            "warmup_actual_ticks": timestamps[start_index] - t0,
            "warmup_actual_seconds": decimal_text(warmup_seconds),
            "warmup_zero_credit": {
                "admitted": admitted[start_index],
                "complete": complete[start_index],
            },
            "full_block_count": len(blocks),
            "tail_block_count": len(tail),
            "terminal_fragment_ticks": timestamps[-1] - timestamps[start],
            "terminal_fragment_seconds":
                decimal_text(Fraction(timestamps[-1] - timestamps[start], TICKS)),
            "terminal_fragment_zero_credit_admitted": admitted[-1] - admitted[start],
            "blocks": blocks,
        },
        "ratio_of_sums": {
            "all": {
                "admitted": sum(block["admitted"] for block in blocks),
                "excluded": sum(block["excluded"] for block in blocks),
                "complete": sum(block["complete"] for block in blocks),
                "ticks": sum(block["ticks"] for block in blocks),
                "hps": decimal_text(rate(blocks)),
            },
            "tail": {
                "admitted": sum(block["admitted"] for block in tail),
                "excluded": sum(block["excluded"] for block in tail),
                "complete": sum(block["complete"] for block in tail),
                "ticks": sum(block["ticks"] for block in tail),
                "hps": decimal_text(rate(tail)),
            },
        },
        "bootstrap_bounds": {
            key: {
                **selected_samples[key],
                "fraction_numerator": value.numerator,
                "fraction_denominator": value.denominator,
                "hps": decimal_text(value),
            }
            for key, value in bounds.items()
        },
        "drift_floor": {
            "name": drift_name,
            "admitted": drift_hands,
            "ticks": drift_ticks,
            "fraction_numerator": drift_floor.numerator,
            "fraction_denominator": drift_floor.denominator,
            "hps": decimal_text(drift_floor),
        },
        "final_hps_lcb": {
            "fraction_numerator": hps_lcb.numerator,
            "fraction_denominator": hps_lcb.denominator,
            "hps": decimal_text(hps_lcb),
        },
        "overhead": {
            "postwarmup_adjacent_gap_count": len(postwarmup_gaps),
            "d99_nearest_rank_one_based": d99_rank,
            "d99_ticks": d99_ticks,
            "d99_seconds": decimal_text(Fraction(d99_ticks, TICKS)),
            "finalization_seconds": decimal_text(finalization_seconds),
            "warmup_plus_finalization_seconds":
                decimal_text(warmup_seconds + finalization_seconds),
            "overhead_allowance_seconds": decimal_text(overhead_allowance_seconds),
        },
        "gates": {
            "minimum_blocks_20": len(blocks) >= 20,
            "minimum_tail_blocks_10": len(tail) >= 10,
            "rate_threshold_hps":
                decimal_text(Fraction(INFLATED_HANDS, PER_ARM_CAP_SECONDS)),
            "rate_gate": rate_gate,
            "pure_5_05m_bound_seconds": decimal_text(pure_bound_seconds),
            "inflated_1_25_bound_seconds": decimal_text(inflated_bound_seconds),
            "per_arm_cap_seconds": PER_ARM_CAP_SECONDS,
            "per_arm_cap_gate": per_arm_cap_gate,
            "overhead_gate": overhead_gate,
            "direct_w_plus_pure_plus_f_seconds": decimal_text(direct_bound_seconds),
            "sequential_two_arm_inflated_bound_seconds":
                decimal_text(2 * inflated_bound_seconds),
            "whole_pair_57600_cap_gate": pair_cap_gate,
        },
        "judgment": {
            "launch_vrp_p01": False,
            "launch_short_performance_probe": False,
            "resume_or_use_vr002c1": False,
            "next_route": "LRFT-F64",
            "reason":
                "exact conservative HPS lower bound fails the frozen per-arm rate and cap gates",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "blocks": len(blocks),
        "tail": len(tail),
        "hps_lcb": decimal_text(hps_lcb),
        "rate_gate": rate_gate,
        "per_arm_cap_gate": per_arm_cap_gate,
        "overhead_gate": overhead_gate,
        "whole_pair_cap_gate": pair_cap_gate,
    }, sort_keys=True))
    return 0 if result["status"] == "VRP-P01_RESOURCE_ADMISSION_NONPASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
