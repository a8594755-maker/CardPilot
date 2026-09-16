"""Recover the complete fresh20k cohort after the inherited 5k count guard."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
AUDITOR = BASE / "prepared_runtime/scripts/alpha_holdem/audit_slumbot_v6_session.py"
MODEL = BASE / "frozen/final.pt"
MODEL_SHA = "66c2254d96e36710c1b326d17026099e6ccabdec70d8e2333cfbef26a63c4a6c"
sys.path[:0] = [str(BASE), str(ROOT)]
from pilot_stats import summarize  # noqa: E402
from research.experiment_log import atomic_json, sha256_file  # noqa: E402


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def session_id(index):
    return f"v6_procedural_iter32_soup_greedy_fresh20k_20260901_s{index:02d}"


def main():
    if (BASE / "combined_audit.json").exists() or (BASE / "completed_analysis.json").exists():
        raise FileExistsError("recovery is fixed and one-shot")
    execution = read(BASE / "execution.json")
    failure = (BASE / "failure.txt").read_text(encoding="utf-8")
    assert execution["status"] == "FAILED_PRESERVED"
    assert "Incomplete fixed cohort; preserve without replacement" in failure
    assert execution["evaluation_hands"] == execution["slumbot_hands"] == 20000
    assert len(execution["children"]) == 8
    assert all(child["exit_code"] == 0 for child in execution["children"])
    assert sha256_file(MODEL) == MODEL_SHA
    sessions = []
    for index in range(1, 9):
        path = BASE / "sessions" / f"s{index:02d}/hands.jsonl"
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2500
        assert [row["successful_hand"] for row in rows] == list(range(1, 2501))
        assert all(
            row["model_sha256"] == MODEL_SHA
            and row["session_id"] == session_id(index)
            and row["policy_seed"] == 2026111200 + index
            and row["policy_mode"] == "greedy"
            and row["policy_temperature"] == 0
            and row["strict_policy_execution"]
            and row["terminal_validation"]["status"] == "PASS"
            for row in rows
        )
        sessions.append([row["winnings_chips"] for row in rows])
    command = [sys.executable, str(AUDITOR), "--model", str(MODEL)]
    for index in range(1, 9):
        command += ["--session-dir", str(BASE / "sessions" / f"s{index:02d}")]
    with (BASE / "combined_audit.json").open("x", encoding="utf-8") as output:
        result = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError("recovery combined evidence audit failed")
    audit = read(BASE / "combined_audit.json")
    assert audit["status"] == "PASS" and audit["sessions"] == 8
    assert audit["successful_hands"] == 20000 and audit["model_sha256"] == MODEL_SHA
    assert audit["token_chains_disjoint"]
    new_tokens = {token for row in audit["results"] for token in row["token_sha256"]}
    old_tokens = set()
    prior_inputs = []
    for path in sorted((ROOT / "research/experiments").glob("*/*combined_audit.json")):
        if BASE in path.parents:
            continue
        try:
            prior = read(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if prior.get("status") != "PASS":
            continue
        tokens = {
            token
            for row in prior.get("results", [])
            for token in row.get("token_sha256", [])
        }
        old_tokens.update(tokens)
        prior_inputs.append(
            {"path": str(path.relative_to(ROOT)), "sha256": sha256_file(path), "tokens": len(tokens)}
        )
    assert not new_tokens.intersection(old_tokens)
    statistics = summarize(sessions)
    decision = (
        "ADMIT_SEPARATE_FRESH100K"
        if statistics["supports_separate_fresh100k"]
        else "FRESH20K_CONFIRMATION_GATE_NOT_PASSED"
    )
    analysis = {
        "status": "COMPLETED_PENDING_REVIEW",
        "decision": decision,
        "model_sha256": MODEL_SHA,
        "statistics": statistics,
        "prior_token_hashes_checked": len(old_tokens),
        "new_training_hands": 0,
        "evaluation_hands": 20000,
        "slumbot_hands": 20000,
        "goal_achieved": False,
        "recovery": "post-cohort inherited_5000_count_guard_only",
    }
    atomic_json(BASE / "completed_analysis.json", analysis)
    atomic_json(
        BASE / "recovery.json",
        {
            "status": "PASS",
            "reason": "All eight2500-hand children exited0; inherited orchestration expected5000 total hands.",
            "original_failure_sha256": sha256_file(BASE / "failure.txt"),
            "combined_audit_sha256": sha256_file(BASE / "combined_audit.json"),
            "prior_audits": prior_inputs,
            "prior_token_hashes_checked": len(old_tokens),
            "new_token_hashes": len(new_tokens),
            "decision": decision,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    execution["status"] = "COMPLETED_PENDING_REVIEW"
    execution["recovery"] = {
        "reason": "inherited_5000_count_guard_after_complete_20000_cohort",
        "failure_preserved": True,
        "recovery_file": str(BASE / "recovery.json"),
    }
    atomic_json(BASE / "execution.json", execution)
    print(json.dumps(analysis, sort_keys=True))


if __name__ == "__main__":
    main()
