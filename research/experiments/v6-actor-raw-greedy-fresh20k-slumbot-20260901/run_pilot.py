"""Eight fixed fresh2500 generic-greedy Slumbot sessions; never retry."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import psutil

from pilot_stats import summarize

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
SOURCE_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
READY = ROOT / "research/experiments/v6-source-live-readiness-20260831"
RUNTIME = BASE / "prepared_runtime/scripts"
CLIENT = RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"
AUDITOR = RUNTIME / "alpha_holdem/audit_slumbot_v6_session.py"
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): atomic_json(Path(path), value)
def log(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def record(command): log("--command", subprocess.list2cmdline(["python", *map(str, command)]))
def raw_count(path): return Path(path).read_bytes().count(b"\n") if Path(path).exists() else 0
def total_raw(): return sum(raw_count(BASE / "sessions" / f"s{i:02d}" / "hands.jsonl") for i in range(1, 9))


def prepare_runtime():
    if (BASE / "prepared_runtime").exists():
        raise ValueError("No runtime overwrite")
    for package in ("alpha_holdem", "deep_cfr"):
        source = ROOT / "scripts" / package
        target = RUNTIME / package
        target.mkdir(parents=True, exist_ok=False)
        for path in source.glob("*.py"):
            shutil.copy2(path, target / path.name)


def session_id(index): return f"v6_actor_raw_greedy_fresh20k_20260901_s{index:02d}"
def session_seed(index): return 2026111300 + index
def session_command(index):
    return [str(CLIENT), "--model", str(BASE / "frozen/final.pt"), "--hands", "2500",
            "--seed", str(session_seed(index)), "--session-id", session_id(index),
            "--out-dir", str(BASE / "sessions" / f"s{index:02d}"), "--device", "cpu",
            "--policy-mode", "greedy"]


def prior_token_hashes():
    hashes = set()
    inputs = []
    for path in sorted((ROOT / "research/experiments").glob("*/*combined_audit.json")):
        if BASE in path.parents:
            continue
        try:
            report = read(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if report.get("status") != "PASS":
            continue
        tokens = {token for row in report.get("results", []) for token in row.get("token_sha256", [])}
        hashes.update(tokens)
        inputs.append({"path": str(path), "sha256": sha(path), "tokens": len(tokens)})
    return hashes, inputs


def raw_sessions():
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
            assert row["winnings_bb"] == row["winnings_chips"] / 100
            for decision in row["decisions"]:
                assert decision["selected_action_slot"] == decision["greedy_action_slot"]
                assert decision["behavior_action_probability"] == 1
            chips.append(row["winnings_chips"])
        if len(chips) != 2500:
            raise ValueError("Incomplete fixed session")
        result.append(chips)
    return result


def main():
    forbidden = ("execution.json", "execution_code", "frozen", "sessions", "prepared_runtime")
    if sys.argv[1:] or any((BASE / name).exists() for name in forbidden):
        raise ValueError("No restart, resume, overwrite, or replacement")
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(Path(arg).name in ("train_v5.py", "play_slumbot_v6_journaled.py", "v6_mirror_eval.py", "run_pilot.py") for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")
    prepare_runtime()
    assert sha(SOURCE) == SOURCE_SHA and CLIENT.is_file() and AUDITOR.is_file()
    assert read(READY / "reviewed_analysis.json")["status"] == "PASS"
    started = time.monotonic()
    execution = {"status": "PREPARING", "pid": current.pid, "create_time": current.create_time(),
                 "started_at": datetime.now(timezone.utc).isoformat(), "children": [],
                 "evaluation_hands": 0, "slumbot_hands": 0}
    write(BASE / "execution.json", execution)
    code = BASE / "execution_code"
    code.mkdir()
    paths = ["research/experiment_log.py"] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, code, paths)
    copies = []
    for relative in paths:
        target = code / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
    write(code / "copy_manifest.json", copies)
    old_tokens, prior_audits = prior_token_hashes()
    write(BASE / "runtime_origin.json", {"client": str(CLIENT), "client_sha256": sha(CLIENT),
          "auditor": str(AUDITOR), "auditor_sha256": sha(AUDITOR), "readiness_review": str(READY / "reviewed_analysis.json"),
          "readiness_review_sha256": sha(READY / "reviewed_analysis.json"), "prior_audits": prior_audits,
          "prior_token_hashes": len(old_tokens)})
    log("--artifact", code / "source_manifest.json", "--artifact", code / "code.patch", "--artifact", code / "copy_manifest.json", "--artifact", BASE / "runtime_origin.json")
    (BASE / "frozen").mkdir()
    shutil.copy2(SOURCE, BASE / "frozen/final.pt")
    log("--artifact", BASE / "frozen/final.pt")
    children, handles = [], []
    success = False
    try:
        test = ["-m", "pytest", str(BASE / "test_pilot.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        log("--artifact", BASE / "tests.xml")
        execution["status"] = "RUNNING"
        commands = [session_command(index) for index in range(1, 9)]
        for command in commands: record(command)
        write(BASE / "session_commands.json", [{"session": index, "command": [sys.executable, *command]} for index, command in enumerate(commands, 1)])
        log("--artifact", BASE / "session_commands.json")
        for index, command in enumerate(commands, 1):
            handle = (BASE / f"s{index:02d}_stdout.log").open("x")
            handles.append(handle)
            child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            info = {"role": f"session{index}", "pid": child.pid, "create_time": psutil.Process(child.pid).create_time(),
                    "command": [sys.executable, *command], "exit_code": None}
            execution["children"].append(info)
            children.append((child, info))
            write(BASE / "execution.json", execution)
        previous = -1
        while any(child.poll() is None for child, _ in children):
            for child, info in children: info["exit_code"] = child.poll()
            count = total_raw()
            if count != previous:
                log("--count", f"evaluation_hands={count}", "--count", f"slumbot_hands={count}")
                previous = count
            execution["evaluation_hands"] = execution["slumbot_hands"] = count
            write(BASE / "execution.json", execution)
            time.sleep(5)
        for child, info in children: info["exit_code"] = child.wait()
        for handle in handles: handle.close()
        count = total_raw()
        execution["evaluation_hands"] = execution["slumbot_hands"] = count
        if count != 20000 or any(info["exit_code"] != 0 for _, info in children):
            raise RuntimeError("Incomplete fixed cohort; preserve without replacement")
        execution["status"] = "AUDITING"
        command = [str(AUDITOR), "--model", str(BASE / "frozen/final.pt")]
        for index in range(1, 9): command += ["--session-dir", str(BASE / "sessions" / f"s{index:02d}")]
        record(command)
        with (BASE / "combined_audit.json").open("x") as output:
            audit = subprocess.run([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        if audit.returncode:
            raise RuntimeError("Combined evidence audit failed")
        report = read(BASE / "combined_audit.json")
        assert report["status"] == "PASS" and report["sessions"] == 8 and report["successful_hands"] == 20000
        assert report["model_sha256"] == SOURCE_SHA and report["token_chains_disjoint"]
        new_tokens = {token for row in report["results"] for token in row["token_sha256"]}
        assert not new_tokens.intersection(old_tokens)
        statistics = summarize(raw_sessions())
        decision = "ADMIT_SEPARATE_FRESH100K" if statistics["supports_separate_fresh100k"] else "FRESH20K_CONFIRMATION_GATE_NOT_PASSED"
        write(BASE / "completed_analysis.json", {"status": "COMPLETED_PENDING_REVIEW", "decision": decision,
              "model_sha256": SOURCE_SHA, "statistics": statistics, "prior_token_hashes_checked": len(old_tokens),
              "new_training_hands": 0, "evaluation_hands": 20000, "slumbot_hands": 20000, "goal_achieved": False})
        log("--artifact", BASE / "combined_audit.json", "--artifact", BASE / "completed_analysis.json")
        success = True
    except BaseException:
        (BASE / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        log("--artifact", BASE / "failure.txt")
    finally:
        for child, info in children:
            if child.poll() is None: info["exit_code"] = child.wait()
        for handle in handles:
            if not handle.closed: handle.close()
        count = total_raw()
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"
        execution["evaluation_hands"] = execution["slumbot_hands"] = count
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(BASE / "execution.json", execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if path.is_file() and "execution_code" not in path.parts and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts += ["--artifact", path]
        log("--count", "new_training_hands=0", "--count", f"evaluation_hands={count}", "--count", f"slumbot_hands={count}",
            "--metric", f"wall_time_seconds={execution['wall_time_seconds']}", *artifacts)
    print(json.dumps({"status": execution["status"], "durable_raw_hands": total_raw()}), flush=True)
    if not success: raise SystemExit(1)


if __name__ == "__main__": main()
