"""Independent raw-evidence review for the actor-EMA terminal smoke."""
import json
import math
from pathlib import Path
import sys

import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file

PAIRS = 2048


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def estimate(values):
    values = [float(value) for value in values]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def main():
    analysis = read(BASE / "analysis.json")
    execution = read(BASE / "execution.json")
    manifest = read(BASE / "candidate_manifest.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW"
    assert read(BASE / "production/train/session_audit.json")["status"] == "PASS"
    assert int(execution["new_training_hands"]) >= 131072
    assert int(execution["evaluation_hands"]) == 61440
    assert int(analysis["slumbot_hands"]) == 0 and not analysis["goal_achieved"]
    for name, row in manifest.items():
        assert sha256_file(Path(row["path"])) == row["sha256"] == analysis["candidate_sha256"][name]
    raw = torch.load(manifest["raw"]["path"], map_location="cpu", weights_only=False)
    ema = torch.load(manifest["ema"]["path"], map_location="cpu", weights_only=False)
    names = tuple(raw["actor_ema_parameter_names"])
    assert names == ("policy_head.weight", "policy_head.bias", "preflop_policy_head.weight", "preflop_policy_head.bias")
    assert raw["actor_ema_updates"] == raw["iteration"] > 0
    assert float(raw["actor_ema_decay"]) == 0.9
    assert any(not torch.equal(raw["model"][name], ema["model"][name]) for name in names)
    assert all(torch.equal(raw["model"][key], ema["model"][key]) for key in raw["model"] if key not in names)
    values = {}
    decks = None
    for candidate in ("source", "raw", "ema"):
        for anchor in range(5):
            path = BASE / "matrix" / f"{candidate}_anchor{anchor}/pairs.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            assert len(rows) == PAIRS
            assert [row["pair_index"] for row in rows] == list(range(PAIRS))
            current_decks = [row["deck"] for row in rows]
            if decks is None:
                decks = current_decks
            assert current_decks == decks
            values[candidate, anchor] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
    per_anchor = [estimate([left - right for left, right in zip(values["ema", index], values["raw", index])]) for index in range(5)]
    ema_raw = estimate([math.fsum(values["ema", index][pair] - values["raw", index][pair] for index in range(5)) / 5 for pair in range(PAIRS)])
    ema_source = estimate([math.fsum(values["ema", index][pair] - values["source", index][pair] for index in range(5)) / 5 for pair in range(PAIRS)])
    positive = sum(row["mean"] > 0 for row in per_anchor)
    passed = ema_raw["mean"] > 0 and ema_source["mean"] > 0 and positive >= 3
    decision = "ADMIT_INDEPENDENT_ACTOR_EMA_PILOT" if passed else "ACTOR_EMA_TERMINAL_SMOKE_NOT_PROMISING"
    assert analysis["decision"] == decision
    for expected, actual in ((ema_raw, analysis["ema_raw"]), (ema_source, analysis["ema_source"])):
        assert abs(expected["mean"] - actual["mean"]) < 1e-12
        assert all(abs(a - b) < 1e-12 for a, b in zip(expected["ci95"], actual["ci95"]))
    reviewed = {
        "status": "PASS", "decision": decision, "ema_raw": ema_raw,
        "ema_source": ema_source, "ema_raw_by_anchor": per_anchor,
        "positive_ema_raw_anchors": positive, "new_training_hands": execution["new_training_hands"],
        "evaluation_hands": execution["evaluation_hands"], "slumbot_hands": 0,
    }
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    summary = (
        "# Actor-head EMA terminal smoke result\n\n"
        f"Decision: `{decision}`. The run produced {execution['new_training_hands']:,} physical "
        f"training hands and {execution['evaluation_hands']:,} common-deck internal evaluation hands.\n\n"
        f"EMA minus raw: {ema_raw['mean']:+.6f} bb/100, 95% CI "
        f"[{ema_raw['ci95'][0]:+.6f}, {ema_raw['ci95'][1]:+.6f}]. "
        f"EMA minus source: {ema_source['mean']:+.6f} bb/100, 95% CI "
        f"[{ema_source['ci95'][0]:+.6f}, {ema_source['ci95'][1]:+.6f}]. "
        f"Positive EMA-minus-raw anchors: {positive}/5.\n\n"
        "The reviewer recomputed every estimate from pairs.jsonl, verified common decks, "
        "candidate hashes, checkpoint actor-only materialization, physical accounting, and "
        "the session audit. Slumbot hands: 0; Goal not achieved.\n"
    )
    (BASE / "result_summary.md").write_text(summary, encoding="utf-8")
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__":
    main()
