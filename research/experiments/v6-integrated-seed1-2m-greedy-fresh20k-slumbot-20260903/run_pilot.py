"""Eight fixed fresh2500 Seed1-2M legacy-bridge Slumbot sessions."""
import importlib.util
import json
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = ROOT / "research/experiments/v6-actor-raw-greedy-fresh20k-slumbot-20260901/run_pilot.py"
SOURCE = ROOT / "research/experiments/v6-integrated-seed1-2m-greedy-fresh5k-slumbot-20260903/frozen/final.pt"
SOURCE_SHA = "993fe99bd0a5ac0eaa0135e449315752d99efc25bedf220f93a1ad08884344c3"
RUNTIME = BASE / "prepared_runtime/scripts"

sys.path.insert(0, str(BASE))
from pilot_stats import summarize  # noqa: E402


def load_parent():
    spec = importlib.util.spec_from_file_location("integrated_seed1_2m_fresh20k_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def batched_log(original, *args, max_chars=24000, artifact_batch=16):
    if sum(len(str(value)) + 1 for value in args) <= max_chars:
        return original(*args)
    common = []
    artifacts = []
    index = 0
    while index < len(args):
        if index + 1 >= len(args):
            raise ValueError("Logger arguments must be option/value pairs")
        option, value = args[index], args[index + 1]
        if option == "--artifact":
            artifacts.append(value)
        else:
            common.extend((option, value))
        index += 2
    if common:
        original(*common)
    for start in range(0, len(artifacts), artifact_batch):
        batch = []
        for artifact in artifacts[start:start + artifact_batch]:
            batch.extend(("--artifact", artifact))
        original(*batch)


def session_id(index):
    return f"v6_integrated_seed1_2m_greedy_fresh20k_20260903_s{index:02d}"


def session_seed(index):
    return 2026263300 + index


def session_command(index):
    return [
        str(RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"),
        "--model", str(BASE / "frozen/final.pt"),
        "--hands", "2500",
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
                assert decision["observation_bridge_contract"] == "hunl_v6_physical_legacy_v4_observation_bridge_v1"
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_action_probability"] == 1
                assert decision["direct_increment"] in decision["v6_action_table"]
            chips.append(row["winnings_chips"])
        if len(chips) != 2500:
            raise ValueError("Incomplete fixed bridge session")
        result.append(chips)
    return result


def main():
    impl = load_parent()
    original_log = impl.log
    impl.log = lambda *args: batched_log(original_log, *args)
    impl.BASE = BASE
    impl.SOURCE = SOURCE
    impl.SOURCE_SHA = SOURCE_SHA
    impl.RUNTIME = RUNTIME
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
