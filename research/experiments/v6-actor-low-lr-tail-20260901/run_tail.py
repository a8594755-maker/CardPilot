"""Exact optimizer-continuous low-LR actor convergence tail."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import psutil
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
START_PHYSICAL = 132553
TARGET_PHYSICAL = 262144
PAIRS = 2048
RUN_ID = "v6_actor_ema_terminal_smoke_20260831"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    atomic_json(Path(path), value)


def update(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )


def record(command):
    update("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def line_count(path):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def estimate(values):
    values = [float(value) for value in values]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def guard():
    current = psutil.Process()
    names = {"train_v5.py", "run_tail.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(Path(arg).name in names for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def capture_code(directory_name="execution_code"):
    target = BASE / directory_name
    target.mkdir()
    paths = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))
    ]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py", f"research/experiments/{BASE.name}/run_tail.py", f"research/experiments/{BASE.name}/test_tail.py", f"research/experiments/{BASE.name}/preregistration.md"]
    capture_code_provenance(ROOT, target, paths)
    copies = []
    for relative in paths:
        destination = target / "source_files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        copies.append({"original": relative, "copy": destination.relative_to(ROOT).as_posix(), "sha256": sha(destination)})
    write(target / "copy_manifest.json", copies)
    return copies


def training_command(frozen, run):
    return [
        "-u", "scripts/alpha_holdem/train_v5.py",
        "--device", "cuda", "--workers", "12", "--hands-per-iter", "4096",
        "--total-hands", "99999999", "--total-environment-hands", str(TARGET_PHYSICAL),
        "--starting-stack", "200", "--env-version", "v6", "--norm-layer", "gn",
        "--lr", ".00003", "--ppo-epochs", "2", "--ppo-target-kl", ".01",
        "--policy-advantage-clip", "3", "--source-policy-kl-coef", ".01",
        "--source-policy-reference-checkpoint", str(frozen / "source_legacy.pt"),
        "--separate-preflop-head", "--all-policy-heads-only-training",
        "--actor-ema-decay", ".9", "--mini-batch-size", "1024",
        "--entropy-coef", ".005", "--entropy-floor", ".05",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints",
        *[str(frozen / f"anchor{index}.pt") for index in range(5)],
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25",
        "--opponent-assignment", "per-group", "--opponent-groups", "8",
        "--adaptive-opponent-league", "--adaptive-league-ema", ".9",
        "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"),
        "--resume-assignment-state-from-provenance",
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "8",
        "--inference-min-batch-slots", "0", "--inference-batch-deadline-us", "700",
        "--worker-seed-base", "2026104200", "--fixed-training-deal-stream",
        "--fixed-training-deal-start-index", str(START_PHYSICAL),
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200",
        "--h1-critic-init-seed", "2026071102", "--value-coef", "1",
        "--autonomous-critic-v2-continue", "--snapshot-every", "999999",
        "--save-interval", "1", "--archive-checkpoint-every", "8",
        "--run-id", RUN_ID, "--run-dir", str(run), "--out", str(run / "latest.pt"),
        "--seed", "20261042", "--max-runtime-seconds", "1800",
        "--resume", str(frozen / "parent_raw.pt"), "--allow-resume", "--no-reset-optimizer",
        "--preserve-resumed-optimizer-lr", "--validate-stream",
    ]


def main():
    recovery = sys.argv[1:] == ["--recover-zero-hand-cli"]
    if (sys.argv[1:] and not recovery) or (
        not recovery
        and any((BASE / name).exists() for name in ("execution.json", "execution_code", "production", "frozen", "matrix"))
    ):
        raise ValueError("No restart")
    if recovery:
        failed = read(BASE / "execution.json")
        prefix = read(BASE / "prefix_manifest.json")
        run = BASE / "production/train"
        frozen = BASE / "frozen"
        assert failed["status"] == "FAILED_PRESERVED"
        assert failed["new_training_hands"] == failed["evaluation_hands"] == 0
        assert failed["children"][-1]["exit_code"] == 2
        assert "--no-reset-optimizer" not in failed["children"][-1]["command"]
        assert sha(run / "latest.pt") == PARENT_SHA == sha(frozen / "parent_raw.pt")
        assert sha(run / "h1_training_metrics.jsonl") == prefix["metrics_sha256"]
        assert sha(run / "opponent_assignments.jsonl") == prefix["assignments_sha256"]
    assert torch.cuda.is_available()
    guard()
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "children": [], "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0}
    execution_path = BASE / ("recovery_execution.json" if recovery else "execution.json")
    write(execution_path, execution)
    success = False
    try:
        code_directory = "recovery_code" if recovery else "execution_code"
        copies = capture_code(code_directory)
        update("--artifact", BASE / f"{code_directory}/source_manifest.json", "--artifact", BASE / f"{code_directory}/code.patch", "--artifact", BASE / f"{code_directory}/copy_manifest.json")
        test_output = BASE / ("recovery_tests.xml" if recovery else "tests.xml")
        test = ["-m", "pytest", str(BASE / "test_tail.py"), "-q", f"--junitxml={test_output}"]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        update("--artifact", test_output)

        if not recovery:
            frozen = BASE / "frozen"
            frozen.mkdir()
            parent_raw = PARENT / "frozen/raw.pt"
            assert sha(parent_raw) == PARENT_SHA
            shutil.copy2(parent_raw, frozen / "parent_raw.pt")
            shutil.copy2(PARENT / "frozen/source_legacy.pt", frozen / "source_legacy.pt")
            assert sha(frozen / "source_legacy.pt") == SOURCE_SHA
            inputs = []
            for name in ("parent_raw", "source_legacy"):
                inputs.append({"name": name, "path": str(frozen / f"{name}.pt"), "sha256": sha(frozen / f"{name}.pt")})
            for index in range(5):
                source = PARENT / f"frozen/anchor{index}.pt"
                shutil.copy2(source, frozen / f"anchor{index}.pt")
                inputs.append({"name": f"anchor{index}", "path": str(frozen / f"anchor{index}.pt"), "sha256": sha(frozen / f"anchor{index}.pt")})
            write(BASE / "input_manifest.json", {"inputs": inputs, "source_copies": copies})
            update("--artifact", BASE / "input_manifest.json", *[item for row in inputs for item in ("--artifact", row["path"])])

            run = BASE / "production/train"
            shutil.copytree(PARENT / "production/train", run)
            prefix = {
                "source_run_dir": str(PARENT / "production/train"),
                "source_checkpoint_sha256": PARENT_SHA,
                "metrics_sha256": sha(run / "h1_training_metrics.jsonl"),
                "assignments_sha256": sha(run / "opponent_assignments.jsonl"),
                "source_final_iteration": 27,
                "source_legacy_hands": 111390,
                "source_physical_hands": START_PHYSICAL,
            }
            write(BASE / "prefix_manifest.json", prefix)
            update("--artifact", BASE / "prefix_manifest.json")

        command = training_command(frozen, run)
        record(command)
        training_log = BASE / ("train_stdout_recovery.log" if recovery else "train_stdout.log")
        with training_log.open("x") as output:
            child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            child_info = {"role": "training", "pid": child.pid, "command": [sys.executable, *command], "exit_code": None}
            execution["children"].append(child_info)
            write(execution_path, execution)
            while child.poll() is None:
                try:
                    completed = int((read(run / "run_manifest.json").get("environment_hand_accounting") or {}).get("completed_hands", START_PHYSICAL))
                except (OSError, json.JSONDecodeError):
                    completed = START_PHYSICAL
                delta = max(0, completed - START_PHYSICAL)
                if delta != execution["new_training_hands"]:
                    execution["new_training_hands"] = delta
                    update("--count", f"new_training_hands={delta}")
                    write(execution_path, execution)
                time.sleep(3)
            child_info["exit_code"] = child.wait()
        if child_info["exit_code"]:
            raise RuntimeError("trainer failed; evidence preserved without retry")

        checkpoint = torch.load(run / "latest.pt", map_location="cpu", weights_only=False)
        account = checkpoint["environment_hand_accounting"]
        assert account["completed_hands"] >= TARGET_PHYSICAL and account["prefix_complete"]
        assert checkpoint["iteration"] > 27 and checkpoint["total_hands"] > 111390
        assert checkpoint["run_id"] == RUN_ID and checkpoint["actor_ema_updates"] == checkpoint["iteration"]
        assert len(checkpoint["optimizer"]["state"]) == 10
        assert len(checkpoint["optimizer"]["param_groups"]) == 1
        assert math.isclose(checkpoint["optimizer"]["param_groups"][0]["lr"], 1e-5, rel_tol=0, abs_tol=1e-15)
        rows = [json.loads(line) for line in (run / "h1_training_metrics.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert [row["iteration"] for row in rows] == list(range(1, checkpoint["iteration"] + 1))
        physical = [row["environment_hand_accounting"]["completed_hands"] for row in rows]
        assert all(a < b for a, b in zip(physical, physical[1:])) and physical[-1] >= TARGET_PHYSICAL
        shutil.copy2(run / "latest.pt", frozen / "tail_raw.pt")

        audit = ["scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(run), "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(TARGET_PHYSICAL), "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "5", "--expected-archive-every", "8", "--expected-normalization", "global", "--out", str(run / "session_audit.json")]
        record(audit)
        with (run / "tail_audit_stdout.log").open("x") as output:
            subprocess.run([sys.executable, *audit], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        assert read(run / "session_audit.json")["status"] == "PASS"
        delta_hands = int(account["completed_hands"]) - START_PHYSICAL
        execution["new_training_hands"] = delta_hands
        candidates = {"source": frozen / "anchor0.pt", "parent": frozen / "parent_raw.pt", "tail": frozen / "tail_raw.pt"}
        write(BASE / "candidate_manifest.json", {name: {"path": str(path), "sha256": sha(path)} for name, path in candidates.items()})
        update("--artifact", BASE / "candidate_manifest.json", "--artifact", frozen / "tail_raw.pt", "--count", f"new_training_hands={delta_hands}")

        evaluator = BASE / "execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py"
        jobs = []
        for name, candidate in candidates.items():
            for index in range(5):
                output = BASE / "matrix" / f"{name}_anchor{index}"
                eval_command = [str(evaluator), "--candidate", str(candidate), "--anchor", str(frozen / f"anchor{index}.pt"), "--pairs", str(PAIRS), "--seed", "20261101", "--device", "cpu", "--policy-mode", "greedy", "--out-dir", str(output)]
                record(eval_command)
                jobs.append((name, index, output, eval_command))

        def evaluate(job):
            name, index, _, eval_command = job
            with (BASE / f"{name}_anchor{index}_stdout.log").open("x") as stream:
                return subprocess.run([sys.executable, *eval_command], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            while not all(f.done() for f in futures):
                execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs)
                write(execution_path, execution)
                time.sleep(8)
            assert all(f.result() == 0 for f in futures)
        execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs)
        assert execution["evaluation_hands"] == 15 * PAIRS * 2

        values = {}
        decks = None
        for name, index, output, _ in jobs:
            pairs = [json.loads(line) for line in (output / "pairs.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            assert len(pairs) == PAIRS
            current = [row["deck"] for row in pairs]
            if decks is None:
                decks = current
            assert current == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in pairs]
        per_anchor = [estimate([tail - parent for tail, parent in zip(values["tail", index], values["parent", index])]) for index in range(5)]
        tail_parent = estimate([math.fsum(values["tail", index][pair] - values["parent", index][pair] for index in range(5)) / 5 for pair in range(PAIRS)])
        tail_source = estimate([math.fsum(values["tail", index][pair] - values["source", index][pair] for index in range(5)) / 5 for pair in range(PAIRS)])
        positive = sum(row["mean"] > 0 for row in per_anchor)
        passed = tail_parent["mean"] > 0 and tail_parent["ci95"][0] > 0 and tail_source["mean"] > 0 and positive >= 3
        decision = "ADMIT_INDEPENDENT_GREEDY_FRESH5K" if passed else "LOW_LR_TAIL_NOT_PROMISING"
        write(BASE / "analysis.json", {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "new_training_hands": delta_hands, "lineage_physical_hands": int(account["completed_hands"]), "evaluation_hands": execution["evaluation_hands"], "slumbot_hands": 0, "tail_parent": tail_parent, "tail_source": tail_source, "tail_parent_by_anchor": per_anchor, "positive_tail_parent_anchors": positive, "candidate_sha256": {name: sha(path) for name, path in candidates.items()}, "training_matrix_is_generalization_evidence": False, "goal_achieved": False})
        success = True
    except BaseException:
        execution["error"] = traceback.format_exc()
        failure_path = BASE / ("recovery_failure.txt" if recovery else "failure.txt")
        failure_path.write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), flush=True)
    finally:
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(execution_path, execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if path.is_file() and "execution_code" not in path.parts and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts += ["--artifact", path]
                if len(artifacts) >= 120:
                    update(*artifacts)
                    artifacts = []
        if artifacts:
            update(*artifacts)
        update("--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
