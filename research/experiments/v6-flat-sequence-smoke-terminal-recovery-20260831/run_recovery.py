"""Read-only terminal audit and untouched evaluation of a preserved endpoint."""
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
PARENT = ROOT / "research/experiments/v6-flat-sequence-reward-smoke-20260831"
SNAPSHOT = PARENT / "execution_code/source_files/scripts"
ENDPOINT_SHA = "e0dea568045508705ce24e4b54e0514eee14051225b5de031b3d1d13d0083a9e"
SOURCE_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
TARGET = 32768
PAIRS = 4096
sys.path.insert(0, str(ROOT))
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
    forbidden = {"train_v5.py", "run_recovery.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (psutil.Process().pid, psutil.Process().ppid()):
            continue
        if any(Path(arg).name in forbidden for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def protect():
    assert read(PARENT / "experiment.json")["status"] == "FAILED"
    assert read(PARENT / "execution.json")["status"] == "FAILED_PRESERVED"
    assert read(PARENT / "execution.json")["children"][0]["exit_code"] == 0
    assert sha(PARENT / "production/latest.pt") == ENDPOINT_SHA
    manifest = read(PARENT / "input_manifest.json")
    for item in manifest["inputs"]:
        assert sha(item["source"]) == sha(item["path"]) == item["sha256"]
    for item in manifest["source_copies"]:
        assert sha(ROOT / item["original"]) == sha(ROOT / item["copy"]) == item["sha256"]
    return manifest


def capture():
    directory = BASE / "execution_code"
    directory.mkdir()
    paths = ["research/experiment_log.py"] + [
        path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")
    ]
    capture_code_provenance(ROOT, directory, paths)
    for relative in paths:
        target = directory / "source_files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "frozen", "evaluation")):
        raise ValueError("No restart")
    process_guard()
    protect()
    started = time.monotonic()
    execution = {"status": "RUNNING", "pid": psutil.Process().pid, "create_time": psutil.Process().create_time(), "started_at": datetime.now(timezone.utc).isoformat(), "new_training_hands": 0, "evaluation_hands": 0, "children": []}
    write(BASE / "execution.json", execution)
    success = False
    try:
        capture()
        endpoint = torch.load(PARENT / "production/latest.pt", map_location="cpu", weights_only=False)
        source = torch.load(PARENT / "frozen/source_legacy.pt", map_location="cpu", weights_only=False)
        account = endpoint["environment_hand_accounting"]
        assert account["completed_hands"] == 35546 and account["completed_hands"] >= TARGET
        assert account["prefix_complete"] and account["unknown_prefix_training_marker_hands"] == 0
        assert account["origin_run_id"] == "v6_flat_sequence_reward_smoke_20260831"
        assert endpoint["iteration"] == 7 and len(endpoint["model"]) == 100
        new_keys = [key for key in endpoint["model"] if key.startswith(("flat_sequence_encoder.", "flat_sequence_trunk_norm.", "flat_sequence_policy_adapters."))]
        assert len(new_keys) == 14 and all(torch.isfinite(endpoint["model"][key]).all() for key in new_keys)
        assert all(torch.equal(endpoint["model"][key], value) for key, value in source["model"].items() if not key.startswith("value_head."))
        assert len(endpoint["optimizer"]["state"]) == 20
        assert all(float(state["step"]) > 0 and all(torch.isfinite(value).all() for value in state.values() if isinstance(value, torch.Tensor)) for state in endpoint["optimizer"]["state"].values())
        metrics = [json.loads(line) for line in (PARENT / "production/h1_training_metrics.jsonl").read_text().splitlines()]
        assert [row["iteration"] for row in metrics] == list(range(1, 8))
        assert [row["environment_hand_accounting"]["completed_hands"] for row in metrics][-1] == 35546
        for row in metrics:
            assert_finite_tree(row)
            for key in ("approx_kl", "entropy", "reference_policy_kl", "reward_per_hand", "value_head_catchup_loss"):
                assert math.isfinite(float(row[key]))
        audit_command = [
            str(SNAPSHOT / "alpha_holdem/audit_train_v5_fixed_pool_session.py"),
            "--run-dir", str(PARENT / "production"), "--expected-target-hands", "99999999",
            "--expected-target-environment-hands", str(TARGET), "--expected-final-iteration", "7",
            "--expected-pool-size", "3", "--expected-archive-every", "4", "--expected-normalization", "global",
            "--out", str(BASE / "session_audit.json"),
        ]
        record(audit_command)
        with (BASE / "audit_stdout.log").open("x") as output:
            subprocess.run([sys.executable, *audit_command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        assert read(BASE / "session_audit.json")["status"] == "PASS"
        frozen = BASE / "frozen"
        frozen.mkdir()
        shutil.copy2(PARENT / "production/latest.pt", frozen / "treatment.pt")
        shutil.copy2(PARENT / "frozen/anchor0.pt", frozen / "anchor0.pt")
        assert sha(frozen / "treatment.pt") == ENDPOINT_SHA
        write(BASE / "input_manifest.json", {"endpoint": {"source": str(PARENT / "production/latest.pt"), "copy": str(frozen / "treatment.pt"), "sha256": ENDPOINT_SHA}, "anchor": {"source": str(PARENT / "frozen/anchor0.pt"), "copy": str(frozen / "anchor0.pt"), "sha256": sha(frozen / "anchor0.pt")}, "parent_input_manifest_sha256": sha(PARENT / "input_manifest.json"), "parent_copy_manifest_sha256": sha(PARENT / "execution_code/copy_manifest.json")})
        evaluation = BASE / "evaluation"
        eval_command = [
            str(SNAPSHOT / "alpha_holdem/v6_mirror_eval.py"), "--candidate", str(frozen / "treatment.pt"),
            "--anchor", str(frozen / "anchor0.pt"), "--pairs", str(PAIRS), "--seed", "20261032",
            "--device", "cpu", "--out-dir", str(evaluation),
        ]
        record(eval_command)
        with (BASE / "evaluation_stdout.log").open("x") as output:
            child = subprocess.Popen([sys.executable, *eval_command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            execution["children"].append({"role": "evaluation", "pid": child.pid, "command": [sys.executable, *eval_command], "exit_code": None})
            execution["children"][-1]["exit_code"] = child.wait()
        if execution["children"][-1]["exit_code"]:
            raise RuntimeError("untouched evaluation failed; preserve without retry")
        summary = read(evaluation / "summary.json")
        rows = [json.loads(line) for line in (evaluation / "pairs.jsonl").read_text().splitlines()]
        assert summary["status"] == "COMPLETED" and len(rows) == PAIRS
        values = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
        mean = math.fsum(values) / len(values)
        se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
        decision = "ADMIT_MATCHED_FLAT_SEQUENCE_REWARD_PILOT" if mean > -20 else "FLAT_SEQUENCE_REWARD_SMOKE_NOT_PROMISING"
        write(BASE / "analysis.json", {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "preserved_parent_status": "FAILED", "preserved_endpoint_sha256": ENDPOINT_SHA, "parent_training_hands": 35546, "new_training_hands": 0, "evaluation_hands": 2 * PAIRS, "source_contrast_bb_per_100": {"n": PAIRS, "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}, "session_audit_status": "PASS", "slumbot_hands": 0, "goal_achieved": False})
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
        log(*artifacts, "--count", "new_training_hands=0", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
    if not success:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
