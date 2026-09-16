"""Zero-hand provenance-path recovery; preserves the preregistered cohort exactly."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import psutil

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path[:0] = [str(BASE), str(ROOT)]
import run_pilot as pilot  # noqa: E402
from pilot_stats import summarize  # noqa: E402
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file  # noqa: E402


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    atomic_json(Path(path), value)


def log(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )


def record(command):
    log("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def raw_count(path):
    path = Path(path)
    return path.read_bytes().count(b"\n") if path.exists() else 0


def total_raw():
    return sum(raw_count(BASE / "sessions" / f"s{i:02d}" / "hands.jsonl") for i in range(1, 9))


def prior_token_hashes():
    hashes, inputs = set(), []
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


def runtime_manifest():
    files = []
    for path in sorted((BASE / "prepared_runtime/scripts").rglob("*.py")):
        relative = path.relative_to(BASE).as_posix()
        source_relative = Path(*Path(relative).parts[2:])
        source = ROOT / "scripts" / source_relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if sha(path) != sha(source):
            raise ValueError(f"Prepared runtime differs from source: {relative}")
        files.append({"path": relative, "sha256": sha(path)})
    if not files:
        raise ValueError("Prepared runtime is empty")
    return files


def main():
    if sys.argv[1:]:
        raise ValueError("Recovery has no mutable arguments")
    initial = read(BASE / "execution.json")
    if initial != {
        "status": "PREPARING",
        "pid": initial.get("pid"),
        "create_time": initial.get("create_time"),
        "started_at": initial.get("started_at"),
        "children": [],
        "evaluation_hands": 0,
        "slumbot_hands": 0,
    }:
        raise ValueError(f"Unexpected interrupted state: {initial}")
    if any((BASE / name).exists() for name in ("frozen", "sessions", "combined_audit.json")):
        raise ValueError("Recovery requires the proven zero-hand pre-session state")
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(
            Path(arg).name in ("train_v5.py", "play_slumbot_v6_journaled.py", "v6_mirror_eval.py", "run_pilot.py", "run_recovery.py")
            for arg in process.info["cmdline"] or []
        ):
            raise RuntimeError(f"conflicting research process {process.pid}")
    if sha(pilot.SOURCE) != pilot.SOURCE_SHA:
        raise ValueError("Frozen source identity changed")
    runtime_files = runtime_manifest()
    started = time.monotonic()
    interruption = {
        "schema": "cardpilot.preflight_recovery.v1",
        "status": "SAFE_ZERO_HAND_RECOVERY",
        "failed_command": "python research/experiments/v6-standard10-legacy-observation-bridge-greedy-fresh5k-slumbot-20260901/run_pilot.py",
        "failure_phase": "execution_code/source_files provenance copy",
        "cause": "Windows legacy path-length limit while nesting the long experiment id",
        "policy_or_network_loaded": False,
        "children_started": 0,
        "evaluation_hands": 0,
        "slumbot_hands": 0,
        "preserved_checkpoint_sha256": pilot.SOURCE_SHA,
        "preserved_session_ids": [pilot.session_id(i) for i in range(1, 9)],
        "preserved_session_seeds": [pilot.session_seed(i) for i in range(1, 9)],
        "recovery_change": "Use short ec/files provenance copies; prepared runtime and preregistered cohort unchanged",
    }
    write(BASE / "interruption_report.json", interruption)
    write(BASE / "prepared_runtime_manifest.json", {"files": runtime_files})
    execution = {
        **initial,
        "status": "RECOVERING_PREPARATION",
        "recovery_pid": current.pid,
        "recovery_create_time": current.create_time(),
        "recovery_started_at": datetime.now(timezone.utc).isoformat(),
        "children": [],
    }
    write(BASE / "execution.json", execution)

    code = BASE / "ec"
    code.mkdir(exist_ok=False)
    paths = ["research/experiment_log.py"] + [
        path.relative_to(ROOT).as_posix()
        for path in sorted(BASE.iterdir())
        if path.suffix in (".py", ".md")
    ]
    capture_code_provenance(ROOT, code, paths)
    copies = []
    copy_dir = code / "files"
    copy_dir.mkdir()
    for index, relative in enumerate(paths):
        source = ROOT / relative
        target = copy_dir / f"{index:02d}_{source.name}"
        shutil.copy2(source, target)
        copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
    write(code / "copy_manifest.json", copies)
    old_tokens, prior_audits = prior_token_hashes()
    write(BASE / "runtime_origin.json", {
        "client": str(pilot.RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"),
        "client_sha256": sha(pilot.RUNTIME / "alpha_holdem/play_slumbot_v6_journaled.py"),
        "auditor": str(BASE / "audit_bridge_cli.py"),
        "auditor_sha256": sha(BASE / "audit_bridge_cli.py"),
        "prior_audits": prior_audits,
        "prior_token_hashes": len(old_tokens),
        "recovery": str(BASE / "interruption_report.json"),
    })
    log(
        "--artifact", BASE / "interruption_report.json",
        "--artifact", BASE / "prepared_runtime_manifest.json",
        "--artifact", code / "source_manifest.json",
        "--artifact", code / "code.patch",
        "--artifact", code / "copy_manifest.json",
        "--artifact", BASE / "runtime_origin.json",
        "--note", "Zero-hand preflight recovery after Windows path-length failure; checkpoint, runtime, commands, seeds, sessions, and evidence contract unchanged.",
    )
    (BASE / "frozen").mkdir()
    shutil.copy2(pilot.SOURCE, BASE / "frozen/final.pt")
    log("--artifact", BASE / "frozen/final.pt")

    children, handles, success = [], [], False
    try:
        test = ["-m", "pytest", str(BASE / "test_pilot.py"), str(BASE / "test_bridge_client.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        log("--artifact", BASE / "tests.xml")
        execution["status"] = "RUNNING"
        commands = [pilot.session_command(index) for index in range(1, 9)]
        for command in commands:
            record(command)
        write(BASE / "session_commands.json", [
            {"session": index, "command": [sys.executable, *command]}
            for index, command in enumerate(commands, 1)
        ])
        log("--artifact", BASE / "session_commands.json")
        for index, command in enumerate(commands, 1):
            handle = (BASE / f"s{index:02d}_stdout.log").open("x")
            handles.append(handle)
            child = subprocess.Popen(
                [sys.executable, *command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            info = {
                "role": f"session{index}", "pid": child.pid,
                "create_time": psutil.Process(child.pid).create_time(),
                "command": [sys.executable, *command], "exit_code": None,
            }
            execution["children"].append(info)
            children.append((child, info))
            write(BASE / "execution.json", execution)
        previous = -1
        while any(child.poll() is None for child, _ in children):
            for child, info in children:
                info["exit_code"] = child.poll()
            count = total_raw()
            if count != previous:
                log("--count", f"evaluation_hands={count}", "--count", f"slumbot_hands={count}")
                previous = count
            execution["evaluation_hands"] = execution["slumbot_hands"] = count
            write(BASE / "execution.json", execution)
            time.sleep(5)
        for child, info in children:
            info["exit_code"] = child.wait()
        for handle in handles:
            handle.close()
        count = total_raw()
        execution["evaluation_hands"] = execution["slumbot_hands"] = count
        if count != 5000 or any(info["exit_code"] != 0 for _, info in children):
            raise RuntimeError("Incomplete fixed cohort; preserve without replacement")
        execution["status"] = "AUDITING"
        command = [str(BASE / "audit_bridge_cli.py"), "--model", str(BASE / "frozen/final.pt")]
        for index in range(1, 9):
            command += ["--session-dir", str(BASE / "sessions" / f"s{index:02d}")]
        record(command)
        with (BASE / "combined_audit.json").open("x") as output:
            audit = subprocess.run([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        if audit.returncode:
            raise RuntimeError("Combined bridge-aware evidence audit failed")
        report = read(BASE / "combined_audit.json")
        if not (
            report["status"] == "PASS" and report["sessions"] == 8
            and report["successful_hands"] == 5000 and report["model_sha256"] == pilot.SOURCE_SHA
            and report["token_chains_disjoint"]
        ):
            raise RuntimeError("Combined audit summary mismatch")
        new_tokens = {token for row in report["results"] for token in row["token_sha256"]}
        if new_tokens.intersection(old_tokens):
            raise RuntimeError("Fresh token chain overlaps prior audited evidence")
        statistics = summarize(pilot.raw_sessions())
        decision = "ADMIT_SEPARATE_FRESH20K" if statistics["supports_separate_fresh20k"] else "FRESH5K_TRANSFER_GATE_NOT_PASSED"
        write(BASE / "completed_analysis.json", {
            "status": "COMPLETED_PENDING_REVIEW", "decision": decision,
            "model_sha256": pilot.SOURCE_SHA, "statistics": statistics,
            "prior_token_hashes_checked": len(old_tokens), "new_training_hands": 0,
            "evaluation_hands": 5000, "slumbot_hands": 5000, "goal_achieved": False,
        })
        log("--artifact", BASE / "combined_audit.json", "--artifact", BASE / "completed_analysis.json")
        success = True
    except BaseException:
        (BASE / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        log("--artifact", BASE / "failure.txt")
    finally:
        for child, info in children:
            if child.poll() is None:
                info["exit_code"] = child.wait()
        for handle in handles:
            if not handle.closed:
                handle.close()
        count = total_raw()
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"
        execution["evaluation_hands"] = execution["slumbot_hands"] = count
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(BASE / "execution.json", execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if path.is_file() and not any(part in ("execution_code", "ec") for part in path.parts) and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts += ["--artifact", path]
        log(
            "--count", "new_training_hands=0",
            "--count", f"evaluation_hands={count}",
            "--count", f"slumbot_hands={count}",
            "--metric", f"wall_time_seconds={execution['wall_time_seconds']}",
            *artifacts,
        )
    print(json.dumps({"status": execution["status"], "durable_raw_hands": total_raw()}), flush=True)
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
