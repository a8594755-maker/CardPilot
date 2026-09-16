"""Zero-hand recovery after the iteration-offset-only shared-auditor failure."""
from datetime import datetime, timezone
import importlib.util
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
ENDPOINT_SHA = "5a39b7df564d42a1dba3fe6890cf363e1c6218f9d7414715c97192f6658d527e"
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value): atomic_json(Path(path), value)
def update(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def record(command): update("--command", subprocess.list2cmdline(["python", *map(str, command)]))


def load_runner():
    spec = importlib.util.spec_from_file_location("original_weight_population_runner", BASE / "run_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def capture_code():
    target = BASE / "recovery_code"
    target.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py"]
    paths += [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, target, paths)
    for relative in paths:
        destination = target / "source_files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)


def main():
    if sys.argv[1:] or (BASE / "recovery_execution.json").exists() or (BASE / "matrix").exists():
        raise ValueError("one zero-hand recovery only")
    original = read(BASE / "execution.json")
    assert original["status"] == "NEEDS_REVIEW" and original["children"][0]["exit_code"] == 0
    assert "training metric iterations are not exactly contiguous" in (BASE / "production/train/audit_stdout.log").read_text()
    assert sha(BASE / "production/train/latest.pt") == ENDPOINT_SHA
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid != psutil.Process().pid and any(Path(arg).name == "train_v5.py" for arg in process.info["cmdline"] or []):
            raise RuntimeError("trainer still active")
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "children": [],
                 "new_training_hands": 65624, "evaluation_hands": 0, "slumbot_hands": 0, "trainer_launched": False}
    write(BASE / "recovery_execution.json", execution)
    try:
        capture_code()
        update("--artifact", BASE / "recovery_code/source_manifest.json", "--artifact", BASE / "recovery_code/code.patch")
        audit_command = [str(BASE / "audit_resumed_fixed_pool.py")]
        record(audit_command)
        with (BASE / "resume_audit_stdout.log").open("x", encoding="utf-8") as output:
            subprocess.run([sys.executable, *audit_command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
        audit = read(BASE / "production/train/resume_session_audit.json")
        assert audit["status"] == "PASS" and audit["checkpoint_sha256"] == ENDPOINT_SHA
        shutil.copy2(BASE / "production/train/latest.pt", BASE / "frozen/candidate.pt")
        assert sha(BASE / "frozen/candidate.pt") == ENDPOINT_SHA
        candidates = {"parent": {"path": str(BASE / "frozen/parent_raw.pt"), "sha256": "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"},
                      "candidate": {"path": str(BASE / "frozen/candidate.pt"), "sha256": ENDPOINT_SHA}}
        write(BASE / "candidate_manifest.json", candidates)
        update("--artifact", BASE / "production/train/resume_session_audit.json", "--artifact", BASE / "resume_audit_stdout.log",
               "--artifact", BASE / "frozen/candidate.pt", "--artifact", BASE / "candidate_manifest.json")
        runner = load_runner()
        population = read(BASE / "population_manifest.json")
        eval_members = [row for row in population["members"] if row["role"] == "eval"]
        contrasts, aggregate, matrix_hands = runner.evaluate(candidates, eval_members, execution)
        preserve = runner.preservation(BASE / "frozen/candidate.pt")
        evaluation_hands = matrix_hands + preserve["states"] * 2
        passed = bool(aggregate["ci95"][0] > 0 and sum(row["bb_per_100"] > 0 for row in contrasts) >= 4 and preserve["passed"])
        decision = "ADMIT_SEPARATE_GREEDY_FRESH5K" if passed else "WEIGHT_POPULATION_SMOKE_NOT_PROMISING"
        analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": decision,
                    "new_training_hands": 65624, "lineage_environment_hands": 198177,
                    "evaluation_hands": evaluation_hands, "slumbot_hands": 0,
                    "selected_scale": population["selected_scale"], "per_anchor_contrasts": contrasts,
                    "aggregate_contrast": aggregate, "preservation": preserve, "gate_passed": passed,
                    "candidate_sha256": ENDPOINT_SHA, "goal_achieved": False,
                    "recovery_scope": "zero-hand resume-aware evidence audit after iteration-offset-only shared-auditor failure"}
        write(BASE / "completed_analysis.json", analysis)
        execution.update({"status": "COMPLETED_PENDING_REVIEW", "evaluation_hands": evaluation_hands,
                          "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_seconds": time.monotonic() - started})
        write(BASE / "recovery_execution.json", execution)
        update("--count", "new_training_hands=65624", "--count", "lineage_training_hands=198177",
               "--count", f"evaluation_hands={evaluation_hands}", "--artifact", BASE / "parent_state_metrics.jsonl",
               "--artifact", BASE / "preservation.json", "--artifact", BASE / "completed_analysis.json",
               "--artifact", BASE / "recovery_execution.json", "--metric", f"wall_time_seconds={original['wall_time_seconds'] + execution['wall_time_seconds']}")
        reviewer = [str(BASE / "review_finish.py")]
        record(reviewer)
        subprocess.run([sys.executable, *reviewer], cwd=ROOT, check=True)
        print(json.dumps({"decision": decision, "aggregate": aggregate, "preservation": preserve}, sort_keys=True))
    except BaseException:
        execution.update({"status": "NEEDS_REVIEW", "error": traceback.format_exc(),
                          "finished_at": datetime.now(timezone.utc).isoformat(), "wall_time_seconds": time.monotonic() - started})
        write(BASE / "recovery_execution.json", execution)
        update("--artifact", BASE / "recovery_execution.json", "--note",
               "Zero-hand recovery failed and was preserved; no trainer launch, checkpoint mutation, or evidence overwrite occurred.")
        raise


if __name__ == "__main__": main()
