"""Matched entropy-penalty actor treatment with greedy reward/mechanism gates."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json, math, shutil, subprocess, sys, time, traceback
from pathlib import Path

import numpy as np
import psutil
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
LEGACY = ROOT / "models/baseline/standard10/latest.pt"
CONTROL = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
ANCHORS = ROOT / "research/experiments/v6-diverse-learned-league-pilot-20260831"
STATES = ROOT / "research/experiments/v6-actor-raw-fresh5k-slumbot-20260901"
LEGACY_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
CONTROL_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
TARGET, PAIRS = 131072, 2048
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file
from alpha_holdem.execution_v6 import load_policy
from alpha_holdem.policy_contract_v6 import from_external, observation


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def write(path, value):
    for attempt in range(20):
        try: atomic_json(Path(path), value); return
        except PermissionError:
            if attempt == 19: raise
            time.sleep(.05 * (attempt + 1))
def log(*args): subprocess.run([sys.executable, str(ROOT / "research/experiment_log.py"), "update", BASE.name, *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
def record(command): log("--command", subprocess.list2cmdline(["python", *map(str, command)]))
def line_count(path):
    try:
        with Path(path).open(encoding="utf-8") as handle: return sum(1 for _ in handle)
    except OSError: return 0
def estimate(values):
    values = [float(value) for value in values]; mean = math.fsum(values) / len(values)
    se = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) * (len(values) - 1)))
    return {"n": len(values), "mean": mean, "standard_error": se, "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


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


def train_command(frozen):
    run = BASE / "production/treatment"
    return ["-u", "scripts/alpha_holdem/train_v5.py", "--device", "cuda", "--workers", "12",
        "--hands-per-iter", "4096", "--total-hands", "99999999", "--total-environment-hands", str(TARGET),
        "--starting-stack", "200", "--env-version", "v6", "--v6-rebind-legacy-weights", "--norm-layer", "gn",
        "--lr", ".00003", "--ppo-epochs", "2", "--ppo-target-kl", ".01", "--policy-advantage-clip", "3",
        "--source-policy-kl-coef", ".01", "--source-policy-reference-checkpoint", str(frozen / "source_legacy.pt"),
        "--separate-preflop-head", "--all-policy-heads-only-training", "--actor-ema-decay", ".9",
        "--mini-batch-size", "1024", "--entropy-coef", "-.005", "--entropy-floor", "0",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints", *[str(frozen / f"anchor{i}.pt") for i in range(5)],
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25", "--opponent-assignment", "per-group",
        "--opponent-groups", "8", "--adaptive-opponent-league", "--adaptive-league-ema", ".9",
        "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "8", "--inference-min-batch-slots", "0",
        "--inference-batch-deadline-us", "700", "--worker-seed-base", "2026104200", "--fixed-training-deal-stream",
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200", "--h1-critic-init-seed", "2026071102",
        "--value-coef", "1", "--autonomous-critic-v2-continue", "--snapshot-every", "999999", "--save-interval", "1",
        "--archive-checkpoint-every", "8", "--run-id", "v6_entropy_penalty_actor_smoke_20260901",
        "--run-dir", str(run), "--out", str(run / "latest.pt"), "--seed", "20261042",
        "--max-runtime-seconds", "1800", "--resume", str(frozen / "source_legacy.pt"), "--allow-resume",
        "--reset-hand-counter", "--reset-optimizer", "--validate-stream"]


def health(source_state):
    run = BASE / "production/treatment"
    checkpoint = torch.load(run / "latest.pt", map_location="cpu", weights_only=False)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= TARGET and account["prefix_complete"] and account["unknown_prefix_training_marker_hands"] == 0
    rows = [json.loads(line) for line in (run / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert [row["iteration"] for row in rows] == list(range(1, checkpoint["iteration"] + 1))
    assert all(a < b for a, b in zip([0] + [row["environment_hand_accounting"]["completed_hands"] for row in rows[:-1]], [row["environment_hand_accounting"]["completed_hands"] for row in rows]))
    assert checkpoint["config"]["entropy_coef"] == -.005 and checkpoint["config"]["entropy_floor"] == 0
    assert checkpoint["actor_ema_updates"] == checkpoint["iteration"] and len(checkpoint["optimizer"]["state"]) == 10
    trainable = ("policy_head.", "preflop_policy_head.", "value_head.")
    assert all(torch.equal(checkpoint["model"][key], value) for key, value in source_state.items() if not key.startswith(trainable))
    audit = ["scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(run),
             "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(TARGET),
             "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "5",
             "--expected-archive-every", "8", "--expected-normalization", "global", "--out", str(run / "session_audit.json")]
    record(audit)
    with (run / "audit_stdout.log").open("x") as output: subprocess.run([sys.executable, *audit], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(run / "session_audit.json")["status"] == "PASS"
    return int(account["completed_hands"])


def state_mechanism(control_path, treatment_path):
    control, _, _ = load_policy(control_path, "cpu"); treatment, _, _ = load_policy(treatment_path, "cpu")
    obs = []
    for session in range(1, 9):
        for line in (STATES / "sessions" / f"s{session:02d}/hands.jsonl").read_text().splitlines():
            for decision in json.loads(line)["decisions"]:
                response = decision["response"]
                state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
                obs.append(observation(state, include_position=False)[0])
    def probabilities(model):
        result = []
        with torch.no_grad():
            for start in range(0, len(obs), 512):
                batch = obs[start:start + 512]
                tensors = [torch.as_tensor(np.stack([row[key] for row in batch]), dtype=torch.float32) for key in ("card_info", "action_info", "extra_info", "legal_mask")]
                logits, _ = model(*tensors); values = logits.numpy().astype(np.float64)
                for vector, row in zip(values, batch):
                    legal = np.flatnonzero(row["legal_mask"]); weights = np.exp(vector[legal] - np.max(vector[legal])); p = np.zeros(9); p[legal] = weights / weights.sum(); result.append(p)
        return result
    cp, tp = probabilities(control), probabilities(treatment)
    entropy = lambda p: float(-np.sum(p[p > 0] * np.log(p[p > 0])))
    return {"states": len(obs), "control_entropy": math.fsum(map(entropy, cp)) / len(cp),
            "treatment_entropy": math.fsum(map(entropy, tp)) / len(tp),
            "treatment_control_tv": math.fsum(.5 * float(np.sum(np.abs(a - b))) for a, b in zip(tp, cp)) / len(cp)}


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "production", "frozen", "matrix")): raise ValueError("No restart")
    assert torch.cuda.is_available() and sha(LEGACY) == LEGACY_SHA and sha(CONTROL) == CONTROL_SHA
    current = psutil.Process()
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid not in (current.pid, current.ppid()) and any(Path(arg).name in ("train_v5.py", "v6_mirror_eval.py", "run_smoke.py", "play_slumbot_v6_journaled.py") for arg in process.info["cmdline"] or []): raise RuntimeError("conflicting research process")
    started = time.monotonic(); execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(), "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0}; write(BASE / "execution.json", execution); success = False
    try:
        capture(); log("--artifact", BASE / "execution_code/source_manifest.json", "--artifact", BASE / "execution_code/code.patch", "--artifact", BASE / "execution_code/copy_manifest.json")
        test = ["-m", "pytest", str(BASE / "test_smoke.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]; record(test); subprocess.run([sys.executable, *test], cwd=ROOT, check=True); log("--artifact", BASE / "tests.xml")
        frozen = BASE / "frozen"; frozen.mkdir(); shutil.copy2(LEGACY, frozen / "source_legacy.pt"); shutil.copy2(CONTROL, frozen / "control.pt")
        anchors = read(ANCHORS / "anchor_manifest.json")[:5]
        for row in anchors: assert sha(row["path"]) == row["sha256"]; shutil.copy2(row["path"], frozen / f"anchor{row['index']}.pt")
        source_state = torch.load(LEGACY, map_location="cpu", weights_only=False)["model"]
        (BASE / "production/treatment").mkdir(parents=True); command = train_command(frozen); record(command)
        with (BASE / "treatment_stdout.log").open("x") as output:
            child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            while child.poll() is None:
                try: hands = int((read(BASE / "production/treatment/run_manifest.json").get("environment_hand_accounting") or {}).get("completed_hands", 0))
                except (OSError, json.JSONDecodeError): hands = 0
                if hands != execution["new_training_hands"]: execution["new_training_hands"] = hands; log("--count", f"new_training_hands={hands}"); write(BASE / "execution.json", execution)
                time.sleep(3)
        if child.wait(): raise RuntimeError("trainer failed; preserve")
        execution["new_training_hands"] = health(source_state); shutil.copy2(BASE / "production/treatment/latest.pt", frozen / "treatment.pt")
        candidates = {"source": frozen / "anchor0.pt", "control": frozen / "control.pt", "treatment": frozen / "treatment.pt"}
        write(BASE / "candidate_manifest.json", {name: {"path": str(path), "sha256": sha(path)} for name, path in candidates.items()}); log("--artifact", BASE / "candidate_manifest.json", "--artifact", frozen / "treatment.pt")
        evaluator = BASE / "execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py"; jobs = []
        for name, candidate in candidates.items():
            for index in range(5):
                output = BASE / "matrix" / f"{name}_anchor{index}"; command = [str(evaluator), "--candidate", str(candidate), "--anchor", str(frozen / f"anchor{index}.pt"), "--pairs", str(PAIRS), "--seed", "20261046", "--device", "cpu", "--policy-mode", "greedy", "--out-dir", str(output)]; record(command); jobs.append((name, index, output, command))
        def evaluate(job):
            name, index, _, command = job
            with (BASE / f"{name}_anchor{index}_stdout.log").open("x") as output: return subprocess.run([sys.executable, *command], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT).returncode
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            while not all(future.done() for future in futures): execution["evaluation_hands"] = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs); write(BASE / "execution.json", execution); time.sleep(10)
            assert all(future.result() == 0 for future in futures)
        matrix_hands = sum(line_count(output / "pairs.jsonl") * 2 for _, _, output, _ in jobs); assert matrix_hands == 61440
        values = {}; decks = None
        for name, index, output, _ in jobs:
            rows = [json.loads(line) for line in (output / "pairs.jsonl").read_text().splitlines()]; current_decks = [row["deck"] for row in rows]
            if decks is None: decks = current_decks
            assert len(rows) == PAIRS and current_decks == decks; values[name, index] = [math.fsum(row["rewards_bb"]) * 50 for row in rows]
        by_anchor = [estimate([t - c for t, c in zip(values["treatment", i], values["control", i])]) for i in range(5)]
        tc = estimate([math.fsum(values["treatment", i][p] - values["control", i][p] for i in range(5)) / 5 for p in range(PAIRS)])
        ts = estimate([math.fsum(values["treatment", i][p] - values["source", i][p] for i in range(5)) / 5 for p in range(PAIRS)])
        mechanism = state_mechanism(frozen / "control.pt", frozen / "treatment.pt"); execution["evaluation_hands"] = matrix_hands + 2 * mechanism["states"]
        positive = sum(row["mean"] > 0 for row in by_anchor); passed = tc["mean"] > 0 and ts["mean"] > 0 and positive >= 3 and mechanism["control_entropy"] - mechanism["treatment_entropy"] >= .03 and mechanism["treatment_control_tv"] < .10
        decision = "ADMIT_ENTROPY_PENALTY_PILOT" if passed else "ENTROPY_PENALTY_SMOKE_NOT_PROMISING"
        write(BASE / "analysis.json", {"status": "COMPLETED_PENDING_REVIEW", "decision": decision, "new_training_hands": execution["new_training_hands"], "evaluation_hands": execution["evaluation_hands"], "treatment_control": tc, "treatment_source": ts, "treatment_control_by_anchor": by_anchor, "positive_treatment_control_anchors": positive, "mechanism": mechanism, "candidate_sha256": {name: sha(path) for name, path in candidates.items()}, "slumbot_hands": 0, "goal_achieved": False}); success = True
    except BaseException:
        (BASE / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        execution["status"] = "COMPLETED_PENDING_REVIEW" if success else "FAILED_PRESERVED"; execution["finished_at"] = datetime.now(timezone.utc).isoformat(); execution["wall_time_seconds"] = time.monotonic() - started; write(BASE / "execution.json", execution)
        log("--count", f"new_training_hands={execution['new_training_hands']}", "--count", f"evaluation_hands={execution['evaluation_hands']}", "--count", "slumbot_hands=0", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}", "--artifact", BASE / "execution.json", "--artifact", BASE / ("analysis.json" if success else "failure.txt"))
    if not success: raise SystemExit(1)


if __name__ == "__main__": main()
