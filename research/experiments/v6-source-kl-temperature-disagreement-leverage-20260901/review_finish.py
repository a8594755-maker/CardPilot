"""Independent review of outcome-blind disagreement leverage rows."""

from collections import Counter
import json
import math
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, sha256_file  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    analysis = read(BASE / "analysis.json")
    inputs = read(BASE / "input_manifest.json")
    execution = read(BASE / "execution.json")
    assert execution["status"] == "COMPLETED_PENDING_REVIEW"
    assert sha256_file(Path(inputs["drift_rows"])) == inputs["drift_rows_sha256"]
    assert sha256_file(Path(inputs["parent_audit"])) == inputs["parent_audit_sha256"]
    rows = [json.loads(line) for line in (BASE / "leverage_rows.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == analysis["states"] == 15078
    assert all(set(row).isdisjoint({"winnings_chips", "winnings_bb", "outcome", "reward"}) for row in rows)
    disagreements = [row for row in rows if row["greedy_disagreement"]]
    assert len(disagreements) == analysis["overall"]["disagreements"]
    assert len({(row["session"], row["hand"], row["decision"]) for row in rows}) == len(rows)
    rate = len(disagreements) / len(rows)
    weighted = math.fsum(row["pot_bb"] for row in disagreements) / math.fsum(row["pot_bb"] for row in rows)
    assert math.isclose(rate, analysis["overall"]["greedy_disagreement_rate"], abs_tol=1e-15)
    assert math.isclose(weighted, analysis["overall"]["pot_weighted_disagreement_rate"], abs_tol=1e-15)
    transitions = Counter(f"{row['source_greedy']}->{row['raw_greedy']}" for row in disagreements)
    assert dict(transitions.most_common()) == analysis["slot_transitions"]
    fold_involved = sum(row["raw_greedy"] == 0 or row["source_greedy"] == 0 for row in disagreements)
    all_in_involved = sum(row["raw_greedy"] == 8 or row["source_greedy"] == 8 for row in disagreements)
    assert fold_involved == analysis["overall"]["fold_involved"]
    assert all_in_involved == analysis["overall"]["all_in_involved"]
    decision = "HIGH_LEVERAGE_FLIPS_IDENTIFIED" if (
        weighted >= 2 * rate or fold_involved + all_in_involved >= len(disagreements) / 2
    ) else "NO_HIGH_LEVERAGE_FLIP_CONCENTRATION"
    assert decision == analysis["decision"]
    reviewed = {
        "status": "PASS",
        "decision": decision,
        "states": len(rows),
        "disagreements": len(disagreements),
        "greedy_disagreement_rate": rate,
        "pot_weighted_disagreement_rate": weighted,
        "mean_pot_bb_all": analysis["overall"]["mean_pot_bb_all"],
        "mean_pot_bb_disagreements": analysis["overall"]["mean_pot_bb_disagreements"],
        "fold_involved": fold_involved,
        "all_in_involved": all_in_involved,
        "top_slot_transitions": transitions.most_common(8),
        "outcomes_used": False,
        "network_calls": 0,
        "slumbot_hands": 0,
        "goal_achieved": False,
    }
    atomic_json(BASE / "reviewed_analysis.json", reviewed)
    (BASE / "result_summary.md").write_text(
        "# Source-KL-temperature disagreement leverage diagnostic\n\n"
        f"Decision: `{decision}`. Across {len(rows):,} outcome-blind states, "
        f"{len(disagreements)} greedy flips ({rate:.3%}) account for {weighted:.3%} of "
        f"pot-weighted decision mass. Mean pot is {reviewed['mean_pot_bb_all']:.3f} bb overall "
        f"and {reviewed['mean_pot_bb_disagreements']:.3f} bb on flips; fold involved "
        f"{fold_involved}, all-in involved {all_in_involved}. No outcomes, network calls, "
        "training hands, or new Slumbot hands were used. Goal not achieved.\n",
        encoding="utf-8",
    )
    print(json.dumps(reviewed, sort_keys=True))


if __name__ == "__main__":
    main()
