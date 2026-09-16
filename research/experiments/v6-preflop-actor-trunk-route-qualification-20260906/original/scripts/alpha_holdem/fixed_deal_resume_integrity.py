"""Evidence-only accounting for deterministic single-environment deal streams.

This module does not claim bitwise process resumption. Completed-hand counters
do not include unknown, uncheckpointed work after an abrupt interruption. A
preflight based on these counters alone cannot certify that unknown suffix.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def single_env_intervals(config: dict, accounting: dict) -> list[dict]:
    """Return half-open intervals for evidenced completed deals, fail closed."""
    if not config.get("fixed_training_deal_stream"):
        raise ValueError("fixed deal stream required")
    if config.get("rollout_mode", "single") != "single":
        raise ValueError("multi-env cursors require per-env evidence")
    if config.get("mirror_self_play_deals") or config.get("paired_seat_average_returns"):
        raise ValueError("mirrored hands are not one completed hand per deal index")
    seed = config.get("worker_seed_base")
    if seed is None:
        raise ValueError("worker seed required")
    start = int(config.get("fixed_training_deal_start_index", 0))
    workers = int(config["workers"])
    rows = accounting.get("session_worker_counts") or []
    if len(rows) != workers or {int(r["worker_id"]) for r in rows} != set(range(workers)):
        raise ValueError("complete unique per-worker counters required")
    if start < 0 or any(int(r["completed_hands"]) < 0 for r in rows):
        raise ValueError("negative cursor or count")
    total = sum(int(r["completed_hands"]) for r in rows)
    if total != int(accounting["session_completed_hands"]):
        raise ValueError("worker sum disagrees with session physical count")
    return [
        {"worker_seed": int(seed) + int(r["worker_id"]), "env_index": 0,
         "start": start, "end": start + int(r["completed_hands"])}
        for r in sorted(rows, key=lambda r: int(r["worker_id"]))
    ]


def summarize_overlap(attempts: list[dict]) -> dict:
    """Count repeated deterministic deal identities, not duplicated trajectories."""
    streams: dict[tuple[int, int], list[tuple[int, int]]] = {}
    executed = 0
    by_attempt = []
    for attempt in attempts:
        intervals = single_env_intervals(attempt["config"], attempt["accounting"])
        count = sum(r["end"] - r["start"] for r in intervals)
        by_attempt.append({"label": attempt["label"], "executed_hands": count,
                           "intervals": intervals})
        executed += count
        for row in intervals:
            key = (row["worker_seed"], row["env_index"])
            streams.setdefault(key, []).append((row["start"], row["end"]))
    unique = 0
    for intervals in streams.values():
        end = -1
        for start, stop in sorted(intervals):
            unique += max(0, stop - max(start, end))
            end = max(end, stop)
    return {"executed_hands": executed, "unique_evidenced_deal_identities": unique,
            "repeated_deal_exposures": executed - unique, "attempts": by_attempt,
            "scope": "saved completed single-env deal identities only",
            "unknown_uncheckpointed_suffix_excluded": True,
            "identical_trajectory_claim": False,
            "physical_counter_correction_required": False}


def validate_resume_start(attempts: list[dict], proposed: dict,
                          *, abrupt_suffix_resolved: bool = False) -> dict:
    """Reject known overlap. Unknown crash suffix also fails until resolved.

    The caller must supply ALL earlier attempts in the same seed namespace.
    Reuse of optimizer/replay is unrelated to this validation.
    """
    if not abrupt_suffix_resolved:
        raise ValueError("unknown crash/in-flight suffix requires explicit resolution")
    workers = int(proposed["workers"])
    dummy = {"session_completed_hands": 0, "session_worker_counts": [
        {"worker_id": w, "completed_hands": 0} for w in range(workers)]}
    new = single_env_intervals(proposed, dummy)
    bounds: dict[tuple[int, int], int] = {}
    for attempt in attempts:
        for row in single_env_intervals(attempt["config"], attempt["accounting"]):
            key = (row["worker_seed"], row["env_index"])
            bounds[key] = max(bounds.get(key, 0), row["end"])
    for row in new:
        key = (row["worker_seed"], row["env_index"])
        # One extra index conservatively excludes an in-flight deal at a saved boundary.
        if key in bounds and row["start"] <= bounds[key]:
            raise ValueError(f"resume start {row['start']} overlaps or touches prior bound {bounds[key]}")
    return {"passed": True, "semantics": "nonoverlapping statistical continuation",
            "bitwise_uninterrupted_equivalence": False}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", action="append", help="LABEL=PATH")
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify-report", type=Path,
                        help="Replay an immutable report, never the moving live tail")
    args = parser.parse_args()
    if args.verify_report:
        if args.checkpoint or args.metrics or args.out:
            parser.error("--verify-report is exclusive")
        saved = json.loads(args.verify_report.read_text(encoding="utf-8"))
        import torch
        attempts = []
        for item, summary in zip(saved["inputs"], saved["attempts"][:-1], strict=True):
            path = Path(item["path"])
            if _sha(path) != item["sha256"]:
                raise RuntimeError("immutable checkpoint SHA mismatch")
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
            attempts.append({"label": summary["label"], "config": ckpt["config"],
                             "accounting": ckpt["environment_hand_accounting"]})
        prefix_info = saved["metrics_prefix"]
        with Path(prefix_info["path"]).open("rb") as handle:
            prefix = handle.read(prefix_info["bytes"])
        if hashlib.sha256(prefix).hexdigest() != prefix_info["sha256"]:
            raise RuntimeError("original append-only metric prefix changed")
        if json.loads(prefix.splitlines()[-1]) != saved["observed_metric"]:
            raise RuntimeError("embedded metric differs from original prefix")
        attempts.append({"label": saved["attempts"][-1]["label"],
                         "config": attempts[-1]["config"],
                         "accounting": saved["observed_metric"]["environment_hand_accounting"]})
        result = summarize_overlap(attempts)
        if any(result[key] != saved[key] for key in result):
            raise RuntimeError("frozen overlap report does not reconstruct exactly")
        print(json.dumps({"verified": True, "report_sha256": _sha(args.verify_report),
                          "executed_hands": result["executed_hands"],
                          "repeated_deal_exposures": result["repeated_deal_exposures"]}))
        return
    if not args.checkpoint or not args.metrics or not args.out:
        parser.error("supply --checkpoint, --metrics, --out or --verify-report")
    if args.out.exists():
        raise FileExistsError(args.out)
    import torch

    attempts = []
    inputs = []
    for item in args.checkpoint:
        label, raw = item.split("=", 1)
        path = Path(raw)
        before = _sha(path)
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        after = _sha(path)
        if before != after:
            raise RuntimeError("checkpoint changed during audit; use immutable source")
        attempts.append({"label": label, "config": ckpt["config"],
                         "accounting": ckpt["environment_hand_accounting"]})
        inputs.append({"path": str(path), "sha256": before,
                       "iteration": int(ckpt["iteration"]), "hands": int(ckpt["total_hands"])})
    raw_metrics = args.metrics.read_bytes()
    # Snapshot only the complete append-only prefix; ignore an in-progress final line.
    prefix = raw_metrics[:raw_metrics.rfind(b"\n") + 1]
    rows = [json.loads(line) for line in prefix.splitlines() if line.strip()]
    latest = rows[-1]
    attempts.append({"label": "recovery2_observed_prefix", "config": attempts[-1]["config"],
                     "accounting": latest["environment_hand_accounting"]})
    result = summarize_overlap(attempts)
    result.update({"schema": "cardpilot.fixed_deal_resume_audit.v1", "inputs": inputs,
                   "metrics_prefix": {"path": str(args.metrics), "bytes": len(prefix),
                                      "sha256": hashlib.sha256(prefix).hexdigest()},
                   "observed_metric": latest,
                   "live_config_assumption": "recovery2 uses same seed/start as frozen recovery1 source; independently verified against launcher and OS command"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("attempts", "observed_metric")}))


if __name__ == "__main__":
    main()
