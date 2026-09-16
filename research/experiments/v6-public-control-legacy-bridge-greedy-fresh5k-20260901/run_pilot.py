"""Eight fixed fresh625 matched-control legacy-bridge greedy sessions."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = ROOT / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901/run_pilot.py"
SOURCE = ROOT / "research/experiments/v6-public-opponent-matched-hero-smoke-20260901/control/latest.pt"
SOURCE_SHA = "6cdc7c46738f9330037bbc8f5f8c9cfbed5ec10599969ef29d2a54f36aa8d20a"
RUNTIME = BASE / "prepared_runtime/scripts"

sys.path.insert(0, str(BASE))
from pilot_stats import summarize


def prepare_runtime():
    if (BASE / "prepared_runtime").exists():
        raise ValueError("No runtime overwrite")
    for package in ("alpha_holdem", "deep_cfr"):
        source = ROOT / "scripts" / package
        target = RUNTIME / package
        target.mkdir(parents=True, exist_ok=False)
        for path in source.glob("*.py"):
            shutil.copy2(path, target / path.name)


def load_parent():
    spec = importlib.util.spec_from_file_location("bridge_fixed_session_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def session_id(index):
    return f"v6_public_control_legacy_bridge_greedy_fresh5k_20260901_s{index:02d}"


def session_seed(index):
    return 2026137200 + index


def session_command(index):
    return [
        str(RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"),
        "--model", str(BASE / "frozen/final.pt"),
        "--hands", "625", "--seed", str(session_seed(index)),
        "--session-id", session_id(index),
        "--out-dir", str(BASE / "sessions" / f"s{index:02d}"),
        "--device", "cpu", "--policy-mode", "greedy",
        "--observation-bridge", "legacy-v4",
    ]


def raw_sessions():
    result = []
    for index in range(1, 9):
        chips = []
        path = BASE / "sessions" / f"s{index:02d}" / "hands.jsonl"
        for hand_index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            assert row["successful_hand"] == row["attempted_hand"] == hand_index
            assert row["session_id"] == session_id(index)
            assert row["policy_seed"] == session_seed(index)
            assert row["model_sha256"] == SOURCE_SHA and row["strict_policy_execution"]
            assert row["policy_mode"] == "greedy" and row["policy_temperature"] == 0
            assert row["terminal_validation"]["status"] == "PASS"
            assert row["winnings_bb"] == row["winnings_chips"] / 100
            for decision in row["decisions"]:
                assert decision["observation_bridge_contract"] == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_action_probability"] == 1
                assert decision["direct_increment"] in decision["v6_action_table"]
            chips.append(row["winnings_chips"])
        if len(chips) != 625:
            raise ValueError("Incomplete fixed bridge session")
        result.append(chips)
    return result


def main():
    prepare_runtime()
    impl = load_parent()
    impl.BASE = BASE
    impl.SOURCE = SOURCE
    impl.SOURCE_SHA = SOURCE_SHA
    impl.CLIENT = RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"
    impl.AUDITOR = BASE / "audit_bridge_cli.py"
    impl.summarize = summarize
    impl.session_id = session_id
    impl.session_seed = session_seed
    impl.session_command = session_command
    impl.raw_sessions = raw_sessions
    impl.main()


if __name__ == "__main__":
    main()
