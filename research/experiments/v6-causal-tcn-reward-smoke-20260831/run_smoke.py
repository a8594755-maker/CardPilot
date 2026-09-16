"""Measured v6 production smoke for the causal-TCN sequence PPO architecture."""
from datetime import datetime, timezone
import json
import math
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
TARGET = 32768
PAIRS = 4096
PREFIXES = (
    "causal_sequence_token.",
    "causal_sequence_convs.",
    "causal_sequence_trunk_norm.",
    "causal_sequence_policy_adapters.",
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path):
    return sha256_file(Path(path))


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    atomic_json(Path(path), value)


def log(*args):
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "research/experiment_log.py"),
            "update",
            BASE.name,
            *map(str, args),
        ],
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


def assert_finite_tree(value):
    if isinstance(value, dict):
        for child in value.values():
            assert_finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            assert_finite_tree(child)
    elif isinstance(value, float):
        assert math.isfinite(value)


def process_guard():
    forbidden = {
        "train_v5.py",
        "run_smoke.py",
        "v6_mirror_eval.py",
        "play_slumbot_v6_journaled.py",
    }
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def capture():
    directory = BASE / "execution_code"
    directory.mkdir()
    paths = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))
    ]
    paths += [
        f"scripts/deep_cfr/{name}.py"
        for name in ("__init__", "game_state", "hand_eval")
    ]
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
        copies.append(
            {
                "original": relative,
                "copy": target.relative_to(ROOT).as_posix(),
                "sha256": sha(target),
            }
        )
    write(directory / "copy_manifest.json", copies)
    return copies


def training_command(frozen):
    run = BASE / "production"
    return [
        "-u", "scripts/alpha_holdem/train_v5.py",
        "--device", "cuda", "--workers", "12", "--hands-per-iter", "4096",
        "--total-hands", "99999999", "--total-environment-hands", str(TARGET),
        "--starting-stack", "200", "--env-version", "v6", "--v6-rebind-legacy-weights",
        "--norm-layer", "gn", "--lr", ".00003", "--ppo-epochs", "2",
        "--ppo-target-kl", ".01", "--policy-advantage-clip", "3",
        "--source-policy-kl-coef", ".01", "--source-policy-reference-checkpoint",
        str(frozen / "source_legacy.pt"), "--separate-preflop-head",
        "--causal-sequence-policy-adapter-hidden", "128",
        "--causal-sequence-adapter-only-training", "--mini-batch-size", "1024",
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
        "--worker-seed-base", "2026103500", "--fixed-training-deal-stream",
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200",
        "--h1-critic-init-seed", "2026071102", "--value-coef", "1",
        "--autonomous-critic-v2-continue", "--snapshot-every", "999999",
        "--save-interval", "1", "--archive-checkpoint-every", "4",
        "--run-id", "v6_causal_tcn_reward_smoke_20260831", "--run-dir", str(run),
        "--out", str(run / "latest.pt"), "--seed", "20261035",
        "--max-runtime-seconds", "900", "--resume", str(frozen / "source_legacy.pt"),
        "--allow-resume", "--reset-hand-counter", "--reset-optimizer", "--validate-stream",
    ]


def verify_health(source_state):
    from alpha_holdem.policy_contract_v6 import validate_metadata

    run = BASE / "production"
    checkpoint = torch.load(run / "latest.pt", map_location="cpu", weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= TARGET
    assert account["prefix_complete"] and account["unknown_prefix_training_marker_hands"] == 0
    assert account["origin_run_id"] == "v6_causal_tcn_reward_smoke_20260831"
    config = checkpoint["config"]
    assert config["causal_sequence_policy_adapter_hidden"] == 128
    assert config["causal_sequence_adapter_only_training"]
    assert config["source_policy_kl_coef"] == 0.01
    assert len(checkpoint["model"]) == len(source_state) + 18 == 104
    new_keys = [key for key in checkpoint["model"] if key.startswith(PREFIXES)]
    assert len(new_keys) == 18
    assert all(torch.isfinite(checkpoint["model"][key]).all() for key in new_keys)
    assert any(
        torch.count_nonzero(checkpoint["model"][key]).item()
        for key in new_keys
        if "policy_adapters" in key and key.endswith(("2.weight", "2.bias"))
    )
    assert all(
        torch.equal(checkpoint["model"][key], value)
        for key, value in source_state.items()
        if not key.startswith("value_head.")
    )
    assert len(checkpoint["optimizer"]["state"]) == 24
    assert all(
        float(state["step"]) > 0
        and all(
            torch.isfinite(value).all()
            for value in state.values()
            if isinstance(value, torch.Tensor)
        )
        for state in checkpoint["optimizer"]["state"].values()
    )
    metrics = [
        json.loads(line)
        for line in (run / "h1_training_metrics.jsonl").read_text().splitlines()
    ]
    assert [row["iteration"] for row in metrics] == list(range(1, checkpoint["iteration"] + 1))
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in metrics]
    assert all(left < right for left, right in zip([0] + counts[:-1], counts))
    assert counts[-1] >= TARGET
    for row in metrics:
        assert_finite_tree(row)
    audit = [
        "scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py",
        "--run-dir", str(run), "--expected-target-hands", "99999999",
        "--expected-target-environment-hands", str(TARGET),
        "--expected-final-iteration", str(checkpoint["iteration"]),
        "--expected-pool-size", "5", "--expected-archive-every", "4",
        "--expected-normalization", "global", "--out", str(run / "session_audit.json"),
    ]
    record(audit)
    with (run / "audit_stdout.log").open("x") as output:
        subprocess.run(
            [sys.executable, *audit], cwd=ROOT, stdout=output,
            stderr=subprocess.STDOUT, check=True,
        )
    assert read(run / "session_audit.json")["status"] == "PASS"
    return checkpoint, int(account["completed_hands"])


def main():
    forbidden = ("execution.json", "execution_code", "production", "frozen", "evaluation")
    if sys.argv[1:] or any((BASE / name).exists() for name in forbidden):
        raise ValueError("No restart")
    assert torch.cuda.is_available() and sha(SOURCE) == SOURCE_SHA
    process_guard()
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
        log(
            "--artifact", BASE / "execution_code/source_manifest.json",
            "--artifact", BASE / "execution_code/code.patch",
            "--artifact", BASE / "execution_code/copy_manifest.json",
        )
        test = [
            "-m", "pytest", str(BASE / "test_smoke.py"), "-q",
            f"--junitxml={BASE / 'tests.xml'}",
        ]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        log("--artifact", BASE / "tests.xml")
        frozen = BASE / "frozen"
        frozen.mkdir()
        shutil.copy2(SOURCE, frozen / "source_legacy.pt")
        inputs = [{
            "name": "source_legacy", "source": str(SOURCE),
            "path": str(frozen / "source_legacy.pt"), "sha256": SOURCE_SHA,
        }]
        for row in read(ANCHORS / "anchor_manifest.json")[:5]:
            source = Path(row["path"])
            assert sha(source) == row["sha256"]
            target = frozen / f"anchor{row['index']}.pt"
            shutil.copy2(source, target)
            inputs.append({
                "name": f"anchor{row['index']}", "source": str(source),
                "path": str(target), "sha256": sha(target),
            })
        write(BASE / "input_manifest.json", {"inputs": inputs, "source_copies": copies})
        log(
            "--artifact", BASE / "input_manifest.json",
            *[value for item in inputs for value in ("--artifact", item["path"])],
        )
        source_state = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
        command = training_command(frozen)
        record(command)
        (BASE / "production").mkdir()
        with (BASE / "training_stdout.log").open("x") as output:
            child = subprocess.Popen(
                [sys.executable, *command], cwd=ROOT, stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            info = {
                "role": "train", "pid": child.pid,
                "command": [sys.executable, *command], "exit_code": None,
            }
            execution["children"].append(info)
            write(BASE / "execution.json", execution)
            while child.poll() is None:
                try:
                    hands = int(
                        (read(BASE / "production/run_manifest.json").get(
                            "environment_hand_accounting"
                        ) or {}).get("completed_hands", 0)
                    )
                except (OSError, json.JSONDecodeError):
                    hands = 0
                if hands != execution["new_training_hands"]:
                    execution["new_training_hands"] = hands
                    log("--count", f"new_training_hands={hands}")
                    write(BASE / "execution.json", execution)
                time.sleep(3)
            info["exit_code"] = child.wait()
        if info["exit_code"]:
            raise RuntimeError("trainer failed; preserve without retry")
        checkpoint, hands = verify_health(source_state)
        execution["new_training_hands"] = hands
        shutil.copy2(BASE / "production/latest.pt", frozen / "treatment.pt")
        log("--count", f"new_training_hands={hands}", "--artifact", frozen / "treatment.pt")
        evaluation = BASE / "evaluation"
        snapshot = BASE / "execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py"
        eval_command = [
            str(snapshot), "--candidate", str(frozen / "treatment.pt"),
            "--anchor", str(frozen / "anchor0.pt"), "--pairs", str(PAIRS),
            "--seed", "20261036", "--device", "cpu", "--out-dir", str(evaluation),
        ]
        record(eval_command)
        with (BASE / "evaluation_stdout.log").open("x") as output:
            subprocess.run(
                [sys.executable, *eval_command], cwd=ROOT, stdout=output,
                stderr=subprocess.STDOUT, check=True,
            )
        summary = read(evaluation / "summary.json")
        rows = [
            json.loads(line)
            for line in (evaluation / "pairs.jsonl").read_text().splitlines()
        ]
        assert len(rows) == PAIRS and summary["status"] == "COMPLETED"
        assert [row["pair_index"] for row in rows] == list(range(PAIRS))
        contrast = estimate([math.fsum(row["rewards_bb"]) * 50 for row in rows])
        passed = contrast["mean"] > -20
        decision = (
            "ADMIT_MATCHED_CAUSAL_TCN_REWARD_PILOT"
            if passed else "CAUSAL_TCN_REWARD_SMOKE_NOT_PROMISING"
        )
        write(BASE / "analysis.json", {
            "status": "COMPLETED_PENDING_REVIEW", "decision": decision,
            "new_training_hands": hands, "target_environment_hands": TARGET,
            "training_iteration": checkpoint["iteration"], "evaluation_hands": 2 * PAIRS,
            "source_contrast_bb_per_100": contrast,
            "model_sha256": sha(frozen / "treatment.pt"), "source_sha256": SOURCE_SHA,
            "session_audit_status": read(BASE / "production/session_audit.json")["status"],
            "slumbot_hands": 0, "goal_achieved": False,
        })
        execution["evaluation_hands"] = 2 * PAIRS
        success = True
    except BaseException:
        execution["error"] = traceback.format_exc()
        (BASE / "failure.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(BASE / "execution.json", execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if (
                path.is_file() and "execution_code" not in path.parts
                and path.name not in ("experiment.json", "source_manifest.json", "code.patch")
            ):
                artifacts.extend(("--artifact", path))
        log(
            *artifacts, "--count", f"new_training_hands={execution['new_training_hands']}",
            "--count", f"evaluation_hands={execution['evaluation_hands']}",
            "--count", "slumbot_hands=0",
            "--metric", f"wall_time_seconds={execution['wall_time_seconds']}",
        )
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
