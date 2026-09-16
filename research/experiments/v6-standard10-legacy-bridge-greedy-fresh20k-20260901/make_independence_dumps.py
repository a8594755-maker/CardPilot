#!/usr/bin/env python3
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    output_dir = BASE / "independence_dumps"
    output_dir.mkdir(exist_ok=False)
    manifest = []
    for session in range(1, 9):
        source = BASE / "sessions" / f"s{session:02d}/hands.jsonl"
        target = output_dir / f"s{session:02d}_dump.jsonl"
        rows = []
        for index, line in enumerate(source.read_text(encoding="utf-8").splitlines()):
            hand = json.loads(line)
            terminal = hand["terminal_response"]
            rows.append({
                "hand_idx": index, "move_idx": 0,
                "client_pos": terminal["client_pos"],
                "hero_hole": terminal["hole_cards"],
                "opp_hole": terminal.get("bot_hole_cards"),
                "board": terminal.get("board", []),
                "action_move": terminal["action"], "action_amount": 0,
                "winnings_hero": hand["winnings_chips"],
            })
        if len(rows) != 2500:
            raise ValueError("Expected complete frozen session")
        target.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )
        manifest.append({"session": session, "source": str(source), "dump": str(target), "hands": len(rows)})
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
