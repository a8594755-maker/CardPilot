"""One-trajectory actor-head EMA terminal-policy smoke."""
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
SOURCE = ROOT / "models/baseline/standard10/latest.pt"
ANCHORS = ROOT / "research/experiments/v6-diverse-learned-league-pilot-20260831"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
TARGET = 131072
PAIRS = 2048
DECAY = 0.9
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    for attempt in range(20):
        try:
            atomic_json(Path(path), value)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05 * (attempt + 1))


def log(*args):
    subprocess.run(
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def record(command):
    log("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def estimate(values):
    values = [float(value) for value in values]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(
        math.fsum((value - mean) ** 2 for value in values)
        / (len(values) * (len(values) - 1))
    )
    return {
        "n": len(values),
        "mean": mean,
        "standard_error": se,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
    }


def line_count(path):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def guard():
    names = {"train_v5.py", "run_smoke.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(Path(arg).name in names for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def capture():
    directory = BASE / "execution_code"
    directory.mkdir()
    paths = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))
    ]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py"]
    paths += [
        path.relative_to(ROOT).as_posix()
        for path in sorted(BASE.iterdir())
        if path.suffix in (".py", ".md")
    ]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        copies.append({
            "original": relative,
            "copy": target.relative_to(ROOT).as_posix(),
            "sha256": sha(target),
        })
    write(directory / "copy_manifest.json", copies)
    return copies


def training_command(frozen):
    run = BASE / "production/train"
    return [
        "-u", "scripts/alpha_holdem/train_v5.py",
        "--device", "cuda", "--workers", "12", "--hands-per-iter", "4096",
        "--total-hands", "99999999", "--total-environment-hands", str(TARGET),
        "--starting-stack", "200", "--env-version", "v6", "--v6-rebind-legacy-weights",
        "--norm-layer", "gn", "--lr", ".00003", "--ppo-epochs", "2",
        "--ppo-target-kl", ".01", "--policy-advantage-clip", "3",
        "--source-policy-kl-coef", ".01",
        "--source-policy-reference-checkpoint", str(frozen / "source_legacy.pt"),
        "--separate-preflop-head", "--all-policy-heads-only-training",
        "--actor-ema-decay", str(DECAY), "--mini-batch-size", "1024",
        "--entropy-coef", ".005", "--entropy-floor", ".05",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints",
        *[str(frozen / f"anchor{index}.pt") for index in range(5)],
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25",
        "--opponent-assignment", "per-group", "--opponent-groups", "8",
        "--adaptive-opponent-league", "--adaptive-league-ema", ".9",
        "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "8",
        "--inference-min-batch-slots", "0", "--inference-batch-deadline-us", "700",
        "--worker-seed-base", "2026104200", "--fixed-training-deal-stream",
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200",
        "--h1-critic-init-seed", "2026071102", "--value-coef", "1",
        "--autonomous-critic-v2-continue", "--snapshot-every", "999999",
        "--save-interval", "1", "--archive-checkpoint-every", "8",
        "--run-id", "v6_actor_ema_terminal_smoke_20260831", "--run-dir", str(run),
        "--out", str(run / "latest.pt"), "--seed", "20261042",
        "--max-runtime-seconds", "1800", "--resume", str(frozen / "source_legacy.pt"),
        "--allow-resume", "--reset-hand-counter", "--reset-optimizer", "--validate-stream",
    ]


def freeze_and_audit(source_state):
    directory = BASE / "production/train"
    checkpoint = torch.load(directory / "latest.pt", map_location="cpu", weights_only=False)
    from alpha_holdem.policy_contract_v6 import validate_metadata
    validate_metadata(checkpoint)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= TARGET
    assert account["prefix_complete"] and account["unknown_prefix_training_marker_hands"] == 0
    assert account["origin_run_id"] == "v6_actor_ema_terminal_smoke_20260831"
    rows = [json.loads(line) for line in (directory / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert [row["iteration"] for row in rows] == list(range(1, checkpoint["iteration"] + 1))
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in rows]
    assert all(left < right for left, right in zip([0] + counts[:-1], counts))
    assert counts[-1] >= TARGET
    assert all(float(row["actor_ema_decay"]) == DECAY for row in rows)
    assert [int(row["actor_ema_updates"]) for row in rows] == list(range(1, checkpoint["iteration"] + 1))
    names = (
        "policy_head.weight", "policy_head.bias",
        "preflop_policy_head.weight", "preflop_policy_head.bias",
    )
    assert tuple(checkpoint["actor_ema_parameter_names"]) == names
    assert set(checkpoint["actor_ema_state"]) == set(names)
    assert int(checkpoint["actor_ema_updates"]) == int(checkpoint["iteration"]) > 0
    assert float(checkpoint["actor_ema_decay"]) == DECAY
    assert len(checkpoint["optimizer"]["state"]) == 10
    trainable = ("policy_head.", "preflop_policy_head.", "value_head.")
    assert all(
        torch.equal(checkpoint["model"][key], value)
        for key, value in source_state.items()
        if not key.startswith(trainable)
    )
    frozen = BASE / "frozen"
    shutil.copy2(directory / "latest.pt", frozen / "raw.pt")
    ema = torch.load(frozen / "raw.pt", map_location="cpu", weights_only=False)
    for name in names:
        assert ema["actor_ema_state"][name].shape == ema["model"][name].shape
        assert torch.isfinite(ema["actor_ema_state"][name]).all()
        ema["model"][name] = ema["actor_ema_state"][name].clone()
    ema["run_id"] = "v6_actor_ema_terminal_smoke_ema_materialized_20260831"
    ema.setdefault("config", {})["deployed_actor_variant"] = "actor_ema"
    ema["deployed_actor_variant"] = "actor_ema"
    torch.save(ema, frozen / "ema.pt")
    raw = torch.load(frozen / "raw.pt", map_location="cpu", weights_only=False)
    materialized = torch.load(frozen / "ema.pt", map_location="cpu", weights_only=False)
    assert any(not torch.equal(raw["model"][name], materialized["model"][name]) for name in names)
    assert all(
        torch.equal(raw["model"][key], materialized["model"][key])
        for key in raw["model"] if key not in names
    )
    audit = [
        "scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py",
        "--run-dir", str(directory), "--expected-target-hands", "99999999",
        "--expected-target-environment-hands", str(TARGET),
        "--expected-final-iteration", str(checkpoint["iteration"]),
        "--expected-pool-size", "5", "--expected-archive-every", "8",
        "--expected-normalization", "global", "--out", str(directory / "session_audit.json"),
    ]
    record(audit)
    with (directory / "audit_stdout.log").open("x") as output:
        subprocess.run([sys.executable, *audit], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(directory / "session_audit.json")["status"] == "PASS"
    distances = {}
    for label, left, right in (
        ("raw_source", raw["model"], source_state),
        ("ema_source", materialized["model"], source_state),
        ("ema_raw", materialized["model"], raw["model"]),
    ):
        distances[label] = math.sqrt(math.fsum(
            float(torch.sum((left[name].double() - right[name].double()) ** 2))
            for name in names
        ))
    return int(account["completed_hands"]), distances


def main():
    forbidden = ("execution.json", "execution_code", "production", "frozen", "matrix")
    if sys.argv[1:] or any((BASE / name).exists() for name in forbidden):
        raise ValueError("No restart")
    assert torch.cuda.is_available() and sha(SOURCE) == SOURCE_SHA
    guard()
    started = time.monotonic()
    current = psutil.Process()
    execution = {
        "status": "RUNNING", "pid": current.pid, "create_time": current.create_time(),
        "started_at": datetime.now(timezone.utc).isoformat(), "children": [],
        "new_training_hands": 0, "evaluation_hands": 0,
    }
    write(BASE / "execution.json", execution)
    success = False
    try:
        copies = capture()
        log("--artifact", BASE / "execution_code/source_manifest.json", "--artifact", BASE / "execution_code/code.patch", "--artifact", BASE / "execution_code/copy_manifest.json")
        test = ["-m", "pytest", str(BASE / "test_smoke.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        log("--artifact", BASE / "tests.xml")
        frozen = BASE / "frozen"
        frozen.mkdir()
        shutil.copy2(SOURCE, frozen / "source_legacy.pt")
        inputs = [{"name": "source_legacy", "source": str(SOURCE), "path": str(frozen / "source_legacy.pt"), "sha256": SOURCE_SHA}]
        for row in read(ANCHORS / "anchor_manifest.json")[:5]:
            source = Path(row["path"])
            assert sha(source) == row["sha256"]
            target = frozen / f"anchor{row['index']}.pt"
            shutil.copy2(source, target)
            inputs.append({"name": f"anchor{row['index']}", "source": str(source), "path": str(target), "sha256": sha(target)})
        write(BASE / "input_manifest.json", {"inputs": inputs, "source_copies": copies})
        log("--artifact", BASE / "input_manifest.json", *[item for row in inputs for item in ("--artifact", row["path"])])
        source_state = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
        (BASE / "production/train").mkdir(parents=True)
        command = training_command(frozen)
        record(command)
        with (BASE / "train_stdout.log").open("x") as output:
            child = subprocess.Popen(
                [sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            child_info = {"role": "train", "pid": child.pid, "command": [sys.executable, *command], "exit_code": None}
            execution["children"].append(child_info)
            write(BASE / "execution.json", execution)
            while child.poll() is None:
                try:
                    hands = int((read(BASE / "production/train/run_manifest.json").get("environment_hand_accounting") or {}).get("completed_hands", 0))
                except (OSError, json.JSONDecodeError):
                    hands = 0
                if hands != execution["new_training_hands"]:
                    execution["new_training_hands"] = hands
                    log("--count", f"new_training_hands={hands}")
                    write(BASE / "execution.json", execution)
                time.sleep(3)
            child_info["exit_code"] = child.wait()
        if child_info["exit_code"]:
            raise RuntimeError("trainer failed; preserve without retry")
        hands, distances = freeze_and_audit(source_state)
        execution["new_training_hands"] = hands
        candidates = {"source": frozen / "anchor0.pt", "raw": frozen / "raw.pt", "ema": frozen / "ema.pt"}
        write(BASE / "candidate_manifest.json", {name: {"path": str(path), "sha256": sha(path)} for name, path in candidates.items()})
        log("--artifact", BASE / "candidate_manifest.json", "--artifact", frozen / "raw.pt", "--artifact", frozen / "ema.pt", "--count", f"new_training_hands={hands}")
        evaluator = BASE / "execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py"
        jobs = []
        for name, candidate in candidates.items():
            for index in range(5):
                output = BASE / "matrix" / f"{name}_anchor{index}"
                command = [str(evaluator), "--candidate", str(candidate), "--anchor", str(frozen / f"anchor{index}.pt"), "--pairs", str(PAIRS), "--seed", "20261043", "--device", "cpu", "--out-dir", str(output)]
                record(command)
                jobs.append((name, index, output, command))

        def evaluate(job):
            name, index, _, command = job
            with (BASE / f"{name}_anchor{index}_stdout.log").open("x") as stream:
                return subprocess.run([sys.executable, *command], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            while not all(future.done() for future in futures):
                execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs)
                write(BASE / "execution.json", execution)
                time.sleep(10)
            assert all(future.result() == 0 for future in futures)
        execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs)
        assert execution["evaluation_hands"] == 15 * PAIRS * 2
        values = {}
        decks = None
        for name, index, output, _ in jobs:
            rows = [json.loads(line) for line in (output / "pairs.jsonl").read_text().splitlines()]
            assert len(rows) == PAIRS and [row["pair_index"] for row in rows] == list(range(PAIRS))
            current_decks = [row["deck"] for row in rows]
            if decks is None:
                decks = current_decks
            assert current_decks == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
        per_anchor = [estimate([ema - raw for ema, raw in zip(values["ema", index], values["raw", index])]) for index in range(5)]
        ema_raw = estimate([
            math.fsum(values["ema", index][pair] - values["raw", index][pair] for index in range(5)) / 5
            for pair in range(PAIRS)
        ])
        ema_source = estimate([
            math.fsum(values["ema", index][pair] - values["source", index][pair] for index in range(5)) / 5
            for pair in range(PAIRS)
        ])
        positive = sum(row["mean"] > 0 for row in per_anchor)
        passed = ema_raw["mean"] > 0 and ema_source["mean"] > 0 and positive >= 3
        decision = "ADMIT_INDEPENDENT_ACTOR_EMA_PILOT" if passed else "ACTOR_EMA_TERMINAL_SMOKE_NOT_PROMISING"
        write(BASE / "analysis.json", {
            "status": "COMPLETED_PENDING_REVIEW", "decision": decision,
            "new_training_hands": hands, "evaluation_hands": execution["evaluation_hands"],
            "actor_ema_decay": DECAY, "actor_head_l2_distances": distances,
            "ema_raw": ema_raw, "ema_source": ema_source,
            "ema_raw_by_anchor": per_anchor, "positive_ema_raw_anchors": positive,
            "candidate_sha256": {name: sha(path) for name, path in candidates.items()},
            "slumbot_hands": 0, "goal_achieved": False,
        })
        success = True
    except BaseException:
        execution["error"] = traceback.format_exc()
        (BASE / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        print(traceback.format_exc(), flush=True)
    finally:
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(BASE / "execution.json", execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if path.is_file() and "execution_code" not in path.parts and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts += ["--artifact", path]
        log(*artifacts, "--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
