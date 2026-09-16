"""Empirical shared-stream audit for journaled Slumbot raw-hand evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def load_session(directory: Path) -> dict:
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (directory / "hands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if summary.get("status") != "COMPLETED" or len(rows) != summary.get("successful_hands"):
        raise ValueError(f"Incomplete session evidence: {directory}")
    expected = list(range(1, len(rows) + 1))
    if [row.get("successful_hand") for row in rows] != expected:
        raise ValueError(f"Non-contiguous raw hands: {directory}")
    if len({row.get("session_id") for row in rows}) != 1 or rows[0]["session_id"] != summary.get("session_id"):
        raise ValueError(f"Session identity mismatch: {directory}")
    visible_deals = []
    for row in rows:
        response = row["terminal_response"]
        visible_deals.append({
            "client_pos": response["client_pos"],
            "hero_hole": sorted(response["hole_cards"]),
            "board": response.get("board", []),
            "bot_hole": sorted(response.get("bot_hole_cards", [])),
        })
    prefix = visible_deals[: min(64, len(visible_deals))]
    return {
        "directory": str(directory),
        "session_id": summary["session_id"],
        "policy_seed": summary["policy_seed"],
        "model_sha256": summary["model_sha256"],
        "initial_token_sha256": rows[0]["session_token_sha256"],
        "hands": len(rows),
        "visible_deals": visible_deals,
        "first64_visible_sequence_sha256": hashlib.sha256(canonical(prefix)).hexdigest(),
    }


def audit(directories: list[str | Path]) -> dict:
    if len(directories) < 2:
        raise ValueError("At least two sessions are required")
    sessions = [load_session(Path(path)) for path in directories]
    for key in ("directory", "session_id", "policy_seed", "initial_token_sha256"):
        if len({session[key] for session in sessions}) != len(sessions):
            raise ValueError(f"Repeated session evidence field: {key}")
    if len({session["model_sha256"] for session in sessions}) != 1:
        raise ValueError("Mixed frozen checkpoints")
    if len({session["first64_visible_sequence_sha256"] for session in sessions}) != len(sessions):
        raise ValueError("Repeated visible deal prefix indicates a shared/replayed stream")
    pairwise = []
    worst_rate = 0.0
    for left_index, left in enumerate(sessions):
        for right in sessions[left_index + 1:]:
            compared = min(left["hands"], right["hands"])
            matches = sum(
                left["visible_deals"][index] == right["visible_deals"][index]
                for index in range(compared)
            )
            rate = matches / compared if compared else 1.0
            worst_rate = max(worst_rate, rate)
            pairwise.append({
                "left": left["session_id"],
                "right": right["session_id"],
                "positions_compared": compared,
                "same_position_visible_deal_matches": matches,
                "match_rate": rate,
            })
    # A shared/replayed stream is expected to match nearly every position.  The
    # five-percent ceiling remains conservative when folds hide most cards.
    status = "PASS" if worst_rate < 0.05 else "FAIL"
    return {
        "schema": "cardpilot.journaled_slumbot_independence.v1",
        "status": status,
        "sessions": len(sessions),
        "hands": sum(session["hands"] for session in sessions),
        "model_sha256": sessions[0]["model_sha256"],
        "unique_session_ids": True,
        "unique_policy_seeds": True,
        "unique_token_chains": True,
        "unique_first64_visible_sequences": True,
        "worst_same_position_visible_deal_match_rate": worst_rate,
        "server_rng_independence_proven": False,
        "pairwise": pairwise,
        "session_summaries": [
            {key: value for key, value in session.items() if key != "visible_deals"}
            for session in sessions
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", action="append", required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.session_dir)
    args.out_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
