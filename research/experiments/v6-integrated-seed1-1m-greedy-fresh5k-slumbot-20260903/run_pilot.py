"""Eight fixed fresh625 integrated-policy legacy-bridge Slumbot sessions."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = (
    ROOT
    / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901/run_pilot.py"
)
SOURCE = (
    ROOT
    / "research/experiments/v6-integrated-alphaholdem-seed1-1m-deep-control-20260902/seed1/latest.pt"
)
SOURCE_SHA = "6fbbe021b140b91e448917ae3e2cbb9bcdca444865433074ac944cae79fa844a"
RUNTIME = BASE / "prepared_runtime/scripts"

sys.path.insert(0, str(BASE))
from pilot_stats import summarize  # noqa: E402


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
    spec = importlib.util.spec_from_file_location("integrated_fresh5k_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def session_id(index):
    return f"v6_integrated_seed1_1m_greedy_fresh5k_20260903_s{index:02d}"


def session_seed(index):
    return 2026263000 + index


def session_command(index):
    return [
        str(RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"),
        "--model", str(BASE / "frozen/final.pt"),
        "--hands", "625",
        "--seed", str(session_seed(index)),
        "--session-id", session_id(index),
        "--out-dir", str(BASE / "sessions" / f"s{index:02d}"),
        "--device", "cpu",
        "--policy-mode", "greedy",
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
                assert decision["policy_mode"] == "greedy" and decision["temperature"] == 0
                assert decision["observation_bridge_contract"] == (
                    "hunl_v6_physical_legacy_v4_observation_bridge_v1"
                )
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
