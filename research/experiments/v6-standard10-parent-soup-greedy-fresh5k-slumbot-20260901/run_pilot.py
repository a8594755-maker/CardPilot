"""Fixed fresh5k generic-greedy pilot for the conservative actor soup."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = ROOT / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901/run_pilot.py"
STATS_DIR = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
SOURCE = ROOT / "research/experiments/v6-standard10-parent-soup-preservation-20260901/frozen/candidate.pt"
SOURCE_SHA = "914c8d186d4cdb4f2139ff64d2b32b7558eb1c5761b553c09457bd756aaec8e5"
RUNTIME = BASE / "prepared_runtime/scripts"
sys.path.insert(0, str(STATS_DIR))
from pilot_stats import summarize


def session_id(index): return f"v6_standard10_parent_soup_greedy_fresh5k_20260901_s{index:02d}"
def session_seed(index): return 2026110500 + index


def prepare_runtime():
    if (BASE / "prepared_runtime").exists(): raise ValueError("No runtime overwrite")
    for package in ("alpha_holdem", "deep_cfr"):
        target = RUNTIME / package; target.mkdir(parents=True, exist_ok=False)
        for path in (ROOT / "scripts" / package).glob("*.py"): shutil.copy2(path, target / path.name)


def main():
    prepare_runtime()
    spec = importlib.util.spec_from_file_location("fixed_session_parent", PARENT_MODULE)
    impl = importlib.util.module_from_spec(spec); spec.loader.exec_module(impl)
    impl.BASE, impl.SOURCE, impl.SOURCE_SHA = BASE, SOURCE, SOURCE_SHA
    impl.CLIENT = RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"
    impl.AUDITOR = RUNTIME / "alpha_holdem/audit_slumbot_v6_session.py"
    impl.summarize = summarize
    original_log = impl.log

    def batched_log(*args):
        ordinary, artifacts, index = [], [], 0
        while index < len(args):
            option, value = args[index:index + 2]
            (artifacts if option == "--artifact" else ordinary).extend((option, value)); index += 2
        if ordinary: original_log(*ordinary)
        for start in range(0, len(artifacts), 60): original_log(*artifacts[start:start + 60])

    def command(index):
        return [str(impl.CLIENT), "--model", str(BASE / "frozen/final.pt"), "--hands", "625",
                "--seed", str(session_seed(index)), "--session-id", session_id(index),
                "--out-dir", str(BASE / "sessions" / f"s{index:02d}"), "--device", "cpu", "--policy-mode", "greedy"]

    def sessions():
        result = []
        for index in range(1, 9):
            rows = [json.loads(line) for line in (BASE / "sessions" / f"s{index:02d}/hands.jsonl").read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 625
            for hand_index, row in enumerate(rows, 1):
                assert row["successful_hand"] == row["attempted_hand"] == hand_index
                assert row["session_id"] == session_id(index) and row["policy_seed"] == session_seed(index)
                assert row["model_sha256"] == SOURCE_SHA and row["policy_mode"] == "greedy" and row["policy_temperature"] == 0
                assert row["terminal_validation"]["status"] == "PASS"
                assert all(decision["selected_action_slot"] == decision["greedy_action_slot"] and decision["behavior_action_probability"] == 1 for decision in row["decisions"])
            result.append([row["winnings_chips"] for row in rows])
        return result

    impl.log, impl.session_command, impl.raw_sessions = batched_log, command, sessions
    impl.main()


if __name__ == "__main__": main()
