import json

import pytest

from scripts.alpha_holdem.audit_journaled_slumbot_independence import audit


def write_session(root, name, seed, token, deals):
    directory = root / name
    directory.mkdir()
    summary = {
        "status": "COMPLETED", "successful_hands": len(deals),
        "session_id": name, "policy_seed": seed, "model_sha256": "a" * 64,
    }
    (directory / "summary.json").write_text(json.dumps(summary))
    rows = []
    for index, deal in enumerate(deals, 1):
        rows.append({
            "successful_hand": index, "session_id": name,
            "session_token_sha256": token,
            "terminal_response": {
                "client_pos": index % 2, "hole_cards": deal,
                "board": [], "action": "f",
            },
        })
    (directory / "hands.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    return directory


def test_independent_visible_sequences_pass(tmp_path):
    left = write_session(tmp_path, "left", 1, "1" * 64, [["As", "Ah"], ["Ks", "Kh"]])
    right = write_session(tmp_path, "right", 2, "2" * 64, [["2s", "2h"], ["3s", "3h"]])
    result = audit([left, right])
    assert result["status"] == "PASS"
    assert result["unique_token_chains"] is True


def test_replayed_visible_sequence_is_rejected(tmp_path):
    deals = [["As", "Ah"], ["Ks", "Kh"]]
    left = write_session(tmp_path, "left", 1, "1" * 64, deals)
    right = write_session(tmp_path, "right", 2, "2" * 64, deals)
    with pytest.raises(ValueError, match="shared/replayed"):
        audit([left, right])
