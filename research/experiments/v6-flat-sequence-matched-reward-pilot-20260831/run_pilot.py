"""Matched final-only flat-sequence reward pilot and common-deck matrix."""
from concurrent.futures import ThreadPoolExecutor
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
TARGET = 262144
PAIRS = 4096
ARMS = ("control", "treatment")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)
def log(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def record(command): log("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def estimate(values):
    values = [float(value) for value in values]
    mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def gate(treatment_control, treatment_source, anchor_points):
    return treatment_control["ci95"][0] > 0 and treatment_source["ci95"][0] > 0 and sum(value > 0 for value in anchor_points) >= 3


def assert_finite_tree(value):
    if isinstance(value, dict):
        for child in value.values(): assert_finite_tree(child)
    elif isinstance(value, list):
        for child in value: assert_finite_tree(child)
    elif isinstance(value, float):
        assert math.isfinite(value)


def process_guard():
    forbidden = {"train_v5.py", "run_pilot.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()): continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []): raise RuntimeError(f"conflicting research process {process.pid}")


def capture():
    directory = BASE / "execution_code"; directory.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py"] + [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory / "source_files" / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT / relative, target)
        copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": sha(target)})
    write(directory / "copy_manifest.json", copies)
    return copies


def training_command(arm, frozen):
    assert arm in ARMS
    run = BASE / "production" / arm
    command = [
        "-u", "scripts/alpha_holdem/train_v5.py", "--device", "cuda", "--workers", "12", "--hands-per-iter", "4096",
        "--total-hands", "99999999", "--total-environment-hands", str(TARGET), "--starting-stack", "200", "--env-version", "v6",
        "--v6-rebind-legacy-weights", "--norm-layer", "gn", "--lr", ".00003", "--ppo-epochs", "2", "--ppo-target-kl", ".01",
        "--policy-advantage-clip", "3", "--source-policy-kl-coef", ".01", "--source-policy-reference-checkpoint", str(frozen / "source_legacy.pt"),
        "--separate-preflop-head", "--mini-batch-size", "1024", "--entropy-coef", ".005", "--entropy-floor", ".05",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints", *[str(frozen / f"anchor{index}.pt") for index in range(5)],
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25", "--opponent-assignment", "per-group", "--opponent-groups", "8",
        "--adaptive-opponent-league", "--adaptive-league-ema", ".9", "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"), "--rollout-mode", "multi", "--rollout-envs-per-worker", "8",
        "--inference-min-batch-slots", "0", "--inference-batch-deadline-us", "700", "--worker-seed-base", "2026103300", "--fixed-training-deal-stream",
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200", "--h1-critic-init-seed", "2026071102", "--value-coef", "1",
        "--autonomous-critic-v2-continue", "--snapshot-every", "999999", "--save-interval", "1", "--archive-checkpoint-every", "4",
        "--run-id", f"v6_flat_sequence_matched_{arm}_20260831", "--run-dir", str(run), "--out", str(run / "latest.pt"),
        "--seed", "20261033", "--max-runtime-seconds", "1800", "--resume", str(frozen / "source_legacy.pt"), "--allow-resume",
        "--reset-hand-counter", "--reset-optimizer", "--validate-stream",
    ]
    if arm == "control": command.append("--all-policy-heads-only-training")
    else: command.extend(("--flat-sequence-policy-adapter-hidden", "128", "--flat-sequence-adapter-only-training"))
    return command


def health(arm, source_state):
    from alpha_holdem.policy_contract_v6 import validate_metadata
    directory = BASE / "production" / arm
    checkpoint = torch.load(directory / "latest.pt", map_location="cpu", weights_only=False); validate_metadata(checkpoint)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= TARGET and account["prefix_complete"] and account["unknown_prefix_training_marker_hands"] == 0
    assert account["origin_run_id"] == f"v6_flat_sequence_matched_{arm}_20260831"
    metrics = [json.loads(line) for line in (directory / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert [row["iteration"] for row in metrics] == list(range(1, checkpoint["iteration"] + 1))
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in metrics]
    assert all(left < right for left, right in zip([0] + counts[:-1], counts)) and counts[-1] >= TARGET
    for row in metrics: assert_finite_tree(row)
    if arm == "control":
        assert len(checkpoint["model"]) == 86 and len(checkpoint["optimizer"]["state"]) == 10
        trainable = ("policy_head.", "preflop_policy_head.", "value_head.")
        assert all(torch.equal(checkpoint["model"][key], value) for key, value in source_state.items() if not key.startswith(trainable))
    else:
        assert len(checkpoint["model"]) == 100 and len(checkpoint["optimizer"]["state"]) == 20
        assert all(torch.equal(checkpoint["model"][key], value) for key, value in source_state.items() if not key.startswith("value_head."))
        new = [key for key in checkpoint["model"] if key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters."))]
        assert len(new) == 14 and all(torch.isfinite(checkpoint["model"][key]).all() for key in new)
    assert all(float(state["step"]) > 0 and all(torch.isfinite(value).all() for value in state.values() if isinstance(value, torch.Tensor)) for state in checkpoint["optimizer"]["state"].values())
    audit = ["scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(directory), "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(TARGET), "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "5", "--expected-archive-every", "4", "--expected-normalization", "global", "--out", str(directory / "session_audit.json")]
    record(audit)
    with (directory / "audit_stdout.log").open("x") as output: subprocess.run([sys.executable, *audit], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(directory / "session_audit.json")["status"] == "PASS"
    return checkpoint, int(account["completed_hands"])


def line_count(path):
    try:
        with Path(path).open() as handle: return sum(1 for _ in handle)
    except OSError: return 0


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "production", "frozen", "matrix")): raise ValueError("No restart")
    assert torch.cuda.is_available() and sha(SOURCE) == SOURCE_SHA; process_guard()
    started = time.monotonic(); execution = {"status": "RUNNING", "pid": psutil.Process().pid, "create_time": psutil.Process().create_time(), "started_at": datetime.now(timezone.utc).isoformat(), "children": [], "arm_training_hands": {}, "new_training_hands": 0, "evaluation_hands": 0}; write(BASE / "execution.json", execution); success = False
    try:
        copies = capture(); log("--artifact", BASE / "execution_code/source_manifest.json", "--artifact", BASE / "execution_code/code.patch", "--artifact", BASE / "execution_code/copy_manifest.json")
        test = ["-m", "pytest", str(BASE / "test_pilot.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]; record(test); subprocess.run([sys.executable, *test], cwd=ROOT, check=True); log("--artifact", BASE / "tests.xml")
        frozen = BASE / "frozen"; frozen.mkdir(); shutil.copy2(SOURCE, frozen / "source_legacy.pt")
        inputs = [{"name": "source_legacy", "source": str(SOURCE), "path": str(frozen / "source_legacy.pt"), "sha256": SOURCE_SHA}]
        anchors = read(ANCHORS / "anchor_manifest.json")[:5]
        for row in anchors:
            source = Path(row["path"]); assert sha(source) == row["sha256"]; target = frozen / f"anchor{row['index']}.pt"; shutil.copy2(source, target); inputs.append({"name": f"anchor{row['index']}", "source": str(source), "path": str(target), "sha256": sha(target)})
        write(BASE / "input_manifest.json", {"inputs": inputs, "source_copies": copies}); log("--artifact", BASE / "input_manifest.json", *[value for item in inputs for value in ("--artifact", item["path"])])
        source_state = torch.load(SOURCE, map_location="cpu", weights_only=False)["model"]
        (BASE / "production").mkdir()
        for arm in ARMS:
            command = training_command(arm, frozen); record(command); directory = BASE / "production" / arm; directory.mkdir()
            with (BASE / f"{arm}_stdout.log").open("x") as output:
                child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                info = {"role": f"train_{arm}", "pid": child.pid, "command": [sys.executable, *command], "exit_code": None}; execution["children"].append(info); write(BASE / "execution.json", execution)
                while child.poll() is None:
                    try: hands = int((read(directory / "run_manifest.json").get("environment_hand_accounting") or {}).get("completed_hands", 0))
                    except (OSError, json.JSONDecodeError): hands = 0
                    if hands != execution["arm_training_hands"].get(arm, 0): execution["arm_training_hands"][arm] = hands; execution["new_training_hands"] = sum(execution["arm_training_hands"].values()); log("--count", f"new_training_hands={execution['new_training_hands']}", "--metric", f"active_arm={arm}"); write(BASE / "execution.json", execution)
                    time.sleep(5)
                info["exit_code"] = child.wait()
            if info["exit_code"]: raise RuntimeError(f"{arm} trainer failed; preserve without retry")
            checkpoint, hands = health(arm, source_state); execution["arm_training_hands"][arm] = hands; execution["new_training_hands"] = sum(execution["arm_training_hands"].values()); shutil.copy2(directory / "latest.pt", frozen / f"{arm}.pt"); log("--count", f"new_training_hands={execution['new_training_hands']}", "--artifact", frozen / f"{arm}.pt", "--note", f"{arm} final frozen after terminal health/session audit PASS")
        candidates = {"source": frozen / "anchor0.pt", "control": frozen / "control.pt", "treatment": frozen / "treatment.pt"}; write(BASE / "candidate_manifest.json", {name: {"path": str(path), "sha256": sha(path)} for name, path in candidates.items()}); log("--artifact", BASE / "candidate_manifest.json")
        snapshot = BASE / "execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py"; jobs = []
        for name, candidate in candidates.items():
            for index in range(5):
                output = BASE / "matrix" / f"{name}_anchor{index}"; command = [str(snapshot), "--candidate", str(candidate), "--anchor", str(frozen / f"anchor{index}.pt"), "--pairs", str(PAIRS), "--seed", "20261034", "--device", "cpu", "--out-dir", str(output)]; record(command); jobs.append((name, index, output, command))
        def evaluate(job):
            name, index, output, command = job
            with (BASE / f"{name}_anchor{index}_stdout.log").open("x") as stream:
                child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0); child.wait()
            return child.returncode
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            while not all(future.done() for future in futures):
                hands = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs)
                if hands != execution["evaluation_hands"]: execution["evaluation_hands"] = hands; log("--count", f"evaluation_hands={hands}"); write(BASE / "execution.json", execution)
                time.sleep(10)
            assert all(future.result() == 0 for future in futures)
        execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs); assert execution["evaluation_hands"] == 15 * PAIRS * 2
        values = {}; decks = None
        for name, index, output, _ in jobs:
            rows = [json.loads(line) for line in (output / "pairs.jsonl").read_text().splitlines()]; assert len(rows) == PAIRS
            current = [row["deck"] for row in rows]
            if decks is None: decks = current
            assert current == decks
            values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
        assert all(value == 0 for value in values["source", 0])
        per_anchor = [estimate([t - c for t, c in zip(values["treatment", index], values["control", index])]) for index in range(5)]
        tc = estimate([math.fsum(values["treatment", index][row] - values["control", index][row] for index in range(5)) / 5 for row in range(PAIRS)])
        ts = estimate([math.fsum(values["treatment", index][row] - values["source", index][row] for index in range(5)) / 5 for row in range(PAIRS)])
        points = [item["mean"] for item in per_anchor]; passed = gate(tc, ts, points); decision = "ADMIT_FLAT_SEQUENCE_TRAINING_SEED_CONFIRMATION" if passed else "FLAT_SEQUENCE_MATCHED_REWARD_GATE_NOT_PASSED"
        write(BASE / "analysis.json", {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "arm_training_hands": execution["arm_training_hands"], "new_training_hands": execution["new_training_hands"], "evaluation_hands": execution["evaluation_hands"], "treatment_control": tc, "treatment_source": ts, "treatment_control_by_anchor": per_anchor, "positive_treatment_control_anchors": sum(value > 0 for value in points), "candidate_sha256": {name: sha(path) for name, path in candidates.items()}, "slumbot_hands": 0, "goal_achieved": False}); success = True
    except BaseException:
        execution["error"] = traceback.format_exc(); (BASE / "failure.txt").write_text(traceback.format_exc()); print(traceback.format_exc(), flush=True)
    finally:
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"; execution["finished_at"] = datetime.now(timezone.utc).isoformat(); execution["wall_time_seconds"] = time.monotonic() - started; write(BASE / "execution.json", execution)
        artifacts = []
        for path in BASE.rglob("*"):
            if path.is_file() and "execution_code" not in path.parts and path.name not in ("experiment.json", "source_manifest.json", "code.patch"): artifacts.extend(("--artifact", path))
        log(*artifacts, "--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    if not success: raise SystemExit(1)


if __name__ == "__main__": main()
