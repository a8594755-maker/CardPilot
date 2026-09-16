"""Measured v6 production smoke for the flat-sequence PPO architecture."""
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
        [sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)],
        cwd=ROOT, check=True, stdout=subprocess.DEVNULL,
    )


def record(command):
    log("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def process_guard():
    forbidden = {"train_v5.py", "run_smoke.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (psutil.Process().pid, psutil.Process().ppid()):
            continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def capture():
    directory = BASE / "execution_code"
    directory.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py"]
    paths += [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
    write(directory / "copy_manifest.json", copies)
    return copies


def training_command(frozen):
    run = BASE / "production"
    return [
        "-u", "scripts/alpha_holdem/train_v5.py", "--device", "cuda", "--workers", "12",
        "--hands-per-iter", "4096", "--total-hands", "99999999",
        "--total-environment-hands", str(TARGET), "--starting-stack", "200", "--env-version", "v6",
        "--v6-rebind-legacy-weights", "--norm-layer", "gn", "--lr", ".00003", "--ppo-epochs", "2",
        "--ppo-target-kl", ".01", "--policy-advantage-clip", "3", "--source-policy-kl-coef", ".01",
        "--source-policy-reference-checkpoint", str(frozen / "source_legacy.pt"), "--separate-preflop-head",
        "--flat-sequence-policy-adapter-hidden", "128", "--flat-sequence-adapter-only-training",
        "--mini-batch-size", "1024", "--entropy-coef", ".005", "--entropy-floor", ".05",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints",
        str(frozen / "anchor0.pt"), str(frozen / "anchor1.pt"), str(frozen / "anchor2.pt"),
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25", "--opponent-assignment", "per-group",
        "--opponent-groups", "8", "--adaptive-opponent-league", "--adaptive-league-ema", ".9",
        "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "8", "--inference-min-batch-slots", "0",
        "--inference-batch-deadline-us", "700", "--worker-seed-base", "2026103100",
        "--fixed-training-deal-stream", "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200",
        "--h1-critic-init-seed", "2026071102", "--value-coef", "1", "--autonomous-critic-v2-continue",
        "--snapshot-every", "999999", "--save-interval", "1", "--archive-checkpoint-every", "4",
        "--run-id", "v6_flat_sequence_reward_smoke_20260831", "--run-dir", str(run), "--out", str(run / "latest.pt"),
        "--seed", "20261031", "--max-runtime-seconds", "900", "--resume", str(frozen / "source_legacy.pt"),
        "--allow-resume", "--reset-hand-counter", "--reset-optimizer", "--validate-stream",
    ]


def verify_health(source_state):
    from alpha_holdem.policy_contract_v6 import validate_metadata
    run = BASE / "production"
    checkpoint = torch.load(run / "latest.pt", map_location="cpu", weights_only=False)
    validate_metadata(checkpoint)
    accounting = checkpoint["environment_hand_accounting"]
    assert accounting["completed_hands"] >= TARGET and accounting["prefix_complete"]
    assert accounting["unknown_prefix_training_marker_hands"] == 0
    assert accounting["origin_run_id"] == "v6_flat_sequence_reward_smoke_20260831"
    config = checkpoint["config"]
    assert config["flat_sequence_policy_adapter_hidden"] == 128
    assert config["flat_sequence_adapter_only_training"] and config["source_policy_kl_coef"] == .01
    assert len(checkpoint["model"]) == len(source_state) + 14 == 100
    new_keys = [key for key in checkpoint["model"] if key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters."))]
    assert len(new_keys) == 14 and all(torch.isfinite(checkpoint["model"][key]).all() for key in new_keys)
    assert any(torch.count_nonzero(checkpoint["model"][key]).item() for key in new_keys if key.endswith(("2.weight", "2.bias")))
    frozen_source_keys = [key for key in source_state if not key.startswith("value_head.")]
    assert all(torch.equal(checkpoint["model"][key], source_state[key]) for key in frozen_source_keys)
    assert len(checkpoint["optimizer"]["state"]) == 20
    assert all(float(state["step"]) > 0 and all(torch.isfinite(value).all() for value in state.values() if isinstance(value, torch.Tensor)) for state in checkpoint["optimizer"]["state"].values())
    metrics = [json.loads(line) for line in (run / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert [row["iteration"] for row in metrics] == list(range(1, checkpoint["iteration"] + 1))
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in metrics]
    assert all(left < right for left, right in zip([0] + counts[:-1], counts)) and counts[-1] >= TARGET
    for row in metrics:
        for key in ("policy_loss", "value_loss", "approx_kl", "entropy"):
            assert math.isfinite(float(row[key]))
    audit_command = [
        "scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(run),
        "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(TARGET),
        "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "3",
        "--expected-archive-every", "4", "--expected-normalization", "global",
        "--out", str(run / "session_audit.json"),
    ]
    record(audit_command)
    with (run / "audit_stdout.log").open("x") as output:
        subprocess.run([sys.executable, *audit_command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(run / "session_audit.json")["status"] == "PASS"
    return checkpoint, accounting["completed_hands"]


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "production", "frozen", "evaluation")):
        raise ValueError("No restart")
    assert torch.cuda.is_available() and sha(SOURCE) == SOURCE_SHA
    process_guard()
    started = time.monotonic()
    execution = {"status": "RUNNING", "pid": psutil.Process().pid, "create_time": psutil.Process().create_time(), "started_at": datetime.now(timezone.utc).isoformat(), "children": [], "new_training_hands": 0, "evaluation_hands": 0}
    write(BASE / "execution.json", execution)
    success = False
    try:
        copies = capture()
        log("--artifact", BASE / "execution_code/source_manifest.json", "--artifact", BASE / "execution_code/code.patch", "--artifact", BASE / "execution_code/copy_manifest.json")
        test_command = ["-m", "pytest", str(BASE / "test_smoke.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test_command)
        subprocess.run([sys.executable, *test_command], cwd=ROOT, check=True)
        log("--artifact", BASE / "tests.xml")
        frozen = BASE / "frozen"
        frozen.mkdir()
        shutil.copy2(SOURCE, frozen / "source_legacy.pt")
        anchor_rows = read(ANCHORS / "anchor_manifest.json")[:3]
        inputs = [{"name": "source_legacy", "source": str(SOURCE), "path": str(frozen / "source_legacy.pt"), "sha256": SOURCE_SHA}]
        for row in anchor_rows:
            source = Path(row["path"])
            assert sha(source) == row["sha256"]
            target = frozen / f"anchor{row['index']}.pt"
            shutil.copy2(source, target)
            inputs.append({"name": f"anchor{row['index']}", "source": str(source), "path": str(target), "sha256": sha(target)})
        write(BASE / "input_manifest.json", {"inputs": inputs, "source_copies": copies})
        log("--artifact", BASE / "input_manifest.json", *[value for item in inputs for value in ("--artifact", item["path"])])
        source_checkpoint = torch.load(SOURCE, map_location="cpu", weights_only=False)
        command = training_command(frozen)
        record(command)
        (BASE / "production").mkdir()
        with (BASE / "training_stdout.log").open("x") as output:
            child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            execution["children"].append({"role": "train", "pid": child.pid, "command": [sys.executable, *command], "exit_code": None})
            while child.poll() is None:
                try:
                    manifest = read(BASE / "production/run_manifest.json")
                    hands = int((manifest.get("environment_hand_accounting") or {}).get("completed_hands", 0))
                except (OSError, json.JSONDecodeError):
                    hands = 0
                if hands != execution["new_training_hands"]:
                    execution["new_training_hands"] = hands
                    log("--count", f"new_training_hands={hands}")
                    write(BASE / "execution.json", execution)
                time.sleep(3)
            execution["children"][-1]["exit_code"] = child.wait()
        if execution["children"][-1]["exit_code"]:
            raise RuntimeError("trainer failed; preserve without retry")
        checkpoint, hands = verify_health(source_checkpoint["model"])
        execution["new_training_hands"] = hands
        shutil.copy2(BASE / "production/latest.pt", frozen / "treatment.pt")
        log("--count", f"new_training_hands={hands}", "--artifact", frozen / "treatment.pt")
        evaluation = BASE / "evaluation"
        eval_command = [
            "scripts/alpha_holdem/v6_mirror_eval.py", "--candidate", str(frozen / "treatment.pt"),
            "--anchor", str(frozen / "anchor0.pt"), "--pairs", str(PAIRS), "--seed", "20261032",
            "--device", "cpu", "--out-dir", str(evaluation),
        ]
        record(eval_command)
        with (BASE / "evaluation_stdout.log").open("x") as output:
            subprocess.run([sys.executable, *eval_command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        summary = read(evaluation / "summary.json")
        rows = [json.loads(line) for line in (evaluation / "pairs.jsonl").read_text().splitlines()]
        assert len(rows) == PAIRS and summary["status"] == "COMPLETED"
        values = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
        mean = math.fsum(values) / len(values)
        se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
        passed = mean > -20
        analysis = {
            "status": "COMPLETED_PENDING_REVIEW", "decision": "ADMIT_MATCHED_FLAT_SEQUENCE_REWARD_PILOT" if passed else "FLAT_SEQUENCE_REWARD_SMOKE_NOT_PROMISING",
            "new_training_hands": hands, "target_environment_hands": TARGET, "training_iteration": checkpoint["iteration"],
            "evaluation_hands": 2 * PAIRS, "source_contrast_bb_per_100": {"n": PAIRS, "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]},
            "model_sha256": sha(frozen / "treatment.pt"), "source_sha256": SOURCE_SHA,
            "session_audit_status": read(BASE / "production/session_audit.json")["status"], "slumbot_hands": 0, "goal_achieved": False,
        }
        write(BASE / "analysis.json", analysis)
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
            if path.is_file() and "execution_code" not in path.parts and path.name not in ("experiment.json", "source_manifest.json", "code.patch"):
                artifacts.extend(("--artifact", path))
        log(*artifacts, "--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
