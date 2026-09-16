"""Greedy specialization of the proven fixed-session orchestration."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = ROOT / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901/run_pilot.py"
SOURCE = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
SOURCE_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
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
    spec = importlib.util.spec_from_file_location("sampled_fixed_session_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def session_id(index): return f"v6_actor_raw_greedy_fresh5k_20260901_s{index:02d}"
def session_seed(index): return 2026104500 + index


def main():
    prepare_runtime()
    impl = load_parent()
    impl.BASE = BASE
    impl.SOURCE = SOURCE
    impl.SOURCE_SHA = SOURCE_SHA
    impl.CLIENT = RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"
    impl.AUDITOR = RUNTIME / "alpha_holdem/audit_slumbot_v6_session.py"
    impl.summarize = summarize

    def command(index):
        return [str(impl.CLIENT), "--model", str(BASE / "frozen/final.pt"),
                "--hands", "625", "--seed", str(session_seed(index)),
                "--session-id", session_id(index),
                "--out-dir", str(BASE / "sessions" / f"s{index:02d}"),
                "--device", "cpu", "--policy-mode", "greedy"]

    def sessions():
        result = []
        for index in range(1, 9):
            chips = []
            path = BASE / "sessions" / f"s{index:02d}" / "hands.jsonl"
            for hand_index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                row = json.loads(line)
                assert row["successful_hand"] == row["attempted_hand"] == hand_index
                assert row["session_id"] == session_id(index) and row["policy_seed"] == session_seed(index)
                assert row["model_sha256"] == SOURCE_SHA and row["strict_policy_execution"]
                assert row["policy_mode"] == "greedy" and row["policy_temperature"] == 0
                assert row["terminal_validation"]["status"] == "PASS"
                for decision in row["decisions"]:
                    assert decision["policy_mode"] == "greedy" and decision["temperature"] == 0
                    assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                    assert decision["behavior_action_probability"] == 1
                chips.append(row["winnings_chips"])
            if len(chips) != 625:
                raise ValueError("Incomplete fixed greedy session")
            result.append(chips)
        return result

    impl.session_command = command
    impl.raw_sessions = sessions
    impl.main()


if __name__ == "__main__": main()
