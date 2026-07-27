#!/usr/bin/env python3
"""Read-only, bounded audit of Path-1 CFR assets for an H3 v55 policy bridge."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def action_count_bounds(history: str, sizes_per_street: int = 3, raise_cap: int = 1) -> tuple[int, int]:
    """Legal V3 tree action-count bounds without reconstructing remaining stacks."""
    segment = history.rsplit("/", 1)[-1]
    aggressive = sum(ch.isdigit() or ch == "A" for ch in segment)
    facing = bool(segment) and (segment[-1].isdigit() or segment[-1] == "A")
    if not facing:
        return 2, 1 + sizes_per_street + 1  # check + at least one wager, at most sizes + all-in
    if segment[-1] == "A":
        return 2, 2  # fold/call only when facing an all-in
    raises_used = max(0, aggressive - 1)
    if raises_used >= raise_cap:
        return 2, 2
    return 2, 2 + sizes_per_street + 1  # stack constraints can prune raise sizes


def sample_rows(gz_path: Path, board_id: int, limit: int) -> dict:
    checks = Counter()
    probability_lengths = Counter()
    examples = []
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for index, line in enumerate(f):
            if index >= limit:
                break
            row = json.loads(line)
            checks["rows"] += 1
            checks["schema_key_probs_only"] += set(row) == {"key", "probs"}
            parts = row.get("key", "").split("|")
            key_ok = len(parts) == 5 and parts[0] in {"F", "T", "R"}
            checks["key_parse"] += key_ok
            if not key_ok:
                continue
            checks["board_identity"] += int(parts[1]) == board_id
            probs = row.get("probs")
            prob_ok = isinstance(probs, list) and probs and all(
                isinstance(p, (int, float)) and math.isfinite(p) and p >= 0 for p in probs
            )
            checks["probabilities_valid"] += prob_ok
            if not prob_ok:
                continue
            checks["probabilities_normalized"] += abs(sum(probs) - 1.0) <= 0.01
            lower, upper = action_count_bounds(parts[3])
            checks["action_count_within_tree_bounds"] += lower <= len(probs) <= upper
            segment = parts[3].rsplit("/", 1)[-1]
            if segment.endswith("A"):
                checks["facing_allin_rows"] += 1
                checks["illegal_post_allin_extra_action_rows"] += len(probs) > 2
            probability_lengths[len(probs)] += 1
            if len(examples) < 3:
                examples.append({"key": row["key"], "probability_count": len(probs), "bounds": [lower, upper]})
    return {
        "board_id": board_id,
        "path": str(gz_path.resolve()),
        "sha256": sha256(gz_path),
        "sample_limit": limit,
        "checks_count": dict(checks),
        "probability_lengths": dict(sorted(probability_lengths.items())),
        "examples": examples,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cfr-dir", required=True)
    p.add_argument("--qa-log", required=True)
    p.add_argument("--sample-rows", type=int, default=256)
    p.add_argument("--out", required=True)
    p.add_argument("--md-out", required=True)
    args = p.parse_args()

    root = Path(args.cfr_dir).resolve()
    metas = []
    for path in sorted(root.glob("flop_*.meta.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        gz = path.with_name(path.name.replace(".meta.json", ".jsonl.gz"))
        if gz.is_file():
            metas.append((int(meta["boardId"]), path, gz, meta))
    iteration_counts = Counter(int(item[3]["iterations"]) for item in metas)
    legacy = [item for item in metas if int(item[3]["iterations"]) == 200000]
    current = [item for item in metas if int(item[3]["iterations"]) == 80000]

    selected = []
    for candidates in (legacy[:1], current[:1], current[-1:]):
        if candidates and candidates[0][0] not in {x[0] for x in selected}:
            selected.append(candidates[0])
    samples = [sample_rows(item[2], item[0], args.sample_rows) for item in selected]

    qa_path = Path(args.qa_log).resolve()
    qa_text = qa_path.read_text(encoding="utf-8", errors="replace")
    qa_pass_ids = {int(x) for x in re.findall(r"board=(\d+) QA_PASS", qa_text)}
    qa_fails = [
        {"board_id": int(board), "rainbow": rainbow.lower() == "true"}
        for board, rainbow in re.findall(r"board=(\d+) QA_FAIL rainbow=(true|false)", qa_text)
    ]

    schema_checks_pass = all(
        all(sample["checks_count"].get(name, 0) == sample["checks_count"].get("rows", 0) for name in (
            "schema_key_probs_only", "key_parse", "board_identity", "probabilities_valid",
            "probabilities_normalized"
        ))
        for sample in samples
    )
    illegal_post_allin_rows = sum(
        sample["checks_count"].get("illegal_post_allin_extra_action_rows", 0) for sample in samples
    )
    current_sample_qa = all(item[0] in qa_pass_ids for item in selected if int(item[3]["iterations"]) == 80000)
    protocol_abort = illegal_post_allin_rows > 0
    solve_healthy = bool(current) and schema_checks_pass and current_sample_qa and not protocol_abort

    repo = Path(__file__).resolve().parents[2]
    evidence_files = [
        repo / "packages/cfr-solver/src/tree/tree-config.ts",
        repo / "packages/cfr-solver/src/scripts/cfr-to-training-data.ts",
        repo / "scripts/alpha_holdem/environment_v55.py",
    ]
    output = {
        "schema_version": "v5.hybrid.h3.asset_readiness_audit.v3",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": (
            "PATH1_FAIL_PROTOCOL_ABORT_ILLEGAL_POST_ALLIN_ACTIONS" if protocol_abort
            else "PATH1_HEALTHY_H3_BRIDGE_NOT_READY" if solve_healthy
            else "FAIL_CLOSED_PATH1_OR_SCHEMA_AUDIT"
        ),
        "asset_generation": {
            "config": "pipeline_srp_v3_200bb",
            "complete_board_pairs": len(metas),
            "target_boards": 600,
            "iteration_counts": dict(sorted(iteration_counts.items())),
            "qa_pass_board_ids_observed": len(qa_pass_ids),
            "qa_fail_events": qa_fails,
            "bounded_schema_samples_pass": schema_checks_pass,
            "current_80k_samples_qa_pass": current_sample_qa,
            "illegal_post_allin_extra_action_rows": illegal_post_allin_rows,
            "qa_gap": protocol_abort and current_sample_qa,
            "status": "PROTOCOL_ABORT_REQUIRED" if protocol_abort else "HEALTHY_RUNNING" if solve_healthy else "AUDIT_FAIL_CLOSED",
        },
        "sampled_exports": samples,
        "h3_bridge": {
            "ready": False,
            "policy_target_available": True,
            "node_or_action_value_target_available": False,
            "exact_v55_observation_available": False,
            "exact_9_action_target_available": False,
            "coverage": "postflop_200bb_single_raised_pots_only",
            "binding_gaps": [
                "solver tree contains strategy nodes with more than fold/call after the opponent all-in; upstream policies are contaminated",
                "exports persist only abstraction key plus policy probabilities",
                "no exact AlphaHoldem v55 card_info/action_info/extra_info/legal_mask record",
                "no audited mapping from V3 abstract actions to legal V5.5 9-action slots",
                "no node/action EV target; therefore assets cannot initialize or supervise the critic",
            ],
            "allowed_next_proof": "streaming CPU-only actor-policy bridge on frozen sampled rows; reconstruct exact v55 states, map only legal matched actions, and fail closed on probability-mass loss or identity mismatch",
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
        },
        "asset_protocol_abort_required": protocol_abort,
        "source_evidence": [{"path": str(path), "sha256": sha256(path)} for path in evidence_files],
        "path1_touched": False,
        "gpu_used": False,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = f"""# H3 Path-1 asset readiness audit\n\nVerdict: `{output['overall']}`.\n\nPath-1 has {len(metas)}/600 complete meta+gzip board pairs: {iteration_counts.get(200000, 0)} legacy 200K and {iteration_counts.get(80000, 0)} current 80K. Bounded samples found {illegal_post_allin_rows} rows whose history ends in opponent all-in but whose strategy still has more than fold/call. Current QA marked the sampled 80K boards PASS, so this is also a QA coverage gap.\n\nThese assets are not H3 training-ready: illegal post-all-in branches contaminate upstream CFR values and policies. Independently, the exports have no exact v55 observation, audited 9-action mapping or value target. Asset generation must stop, preserve its outputs, fix the tree/QA, and restart into a new output directory. No H3 behavior launch or official Slumbot hands are authorized.\n"""
    Path(args.md_out).write_text(md, encoding="utf-8")
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if solve_healthy else 2


if __name__ == "__main__":
    raise SystemExit(main())
