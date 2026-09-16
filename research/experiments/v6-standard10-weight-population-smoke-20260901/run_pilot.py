"""Frozen Standard10 weight-space population and conservative actor-tail smoke."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import sys
import time
import traceback

import numpy as np
import psutil
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
STANDARD10 = ROOT / "models/baseline/standard10/latest.pt"
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
CORPUS = ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901"
STANDARD10_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"
ACTOR_NAMES = (
    "policy_head.weight", "policy_head.bias",
    "preflop_policy_head.weight", "preflop_policy_head.bias",
)
SCALE_GRID = (0.25, 0.5, 1.0, 2.0)
CALIBRATION_SEEDS = tuple(range(2026110001, 2026110004))
TRAIN_SEEDS = tuple(range(2026110101, 2026110106))
EVAL_SEEDS = tuple(range(2026110201, 2026110206))
START_PHYSICAL = 132553
TARGET_PHYSICAL = 198089
PAIRS = 1024
EVAL_SEED = 20261104
RUN_ID = "v6_actor_ema_terminal_smoke_20260831"

sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from alpha_holdem.execution_v6 import load_policy
from alpha_holdem.policy_contract_v6 import METADATA, apply_incr, observation, from_external
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v5_mirror_eval import init_model
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


def perturb_actor_state(base_state, scale, seed):
    missing = set(ACTOR_NAMES) - set(base_state)
    if missing:
        raise KeyError(f"missing actor tensors: {sorted(missing)}")
    generator = torch.Generator(device="cpu")
    generator.manual_seed(int(seed))
    result = {name: value.detach().cpu().clone() for name, value in base_state.items()}
    for name in ACTOR_NAMES:
        source = result[name]
        sigma = float(source.float().std(unbiased=True))
        if not math.isfinite(sigma) or sigma <= 0:
            raise ValueError(f"invalid perturbation scale source for {name}: {sigma}")
        noise = torch.randn(source.shape, generator=generator, dtype=torch.float32)
        result[name] = (source.float() + noise * (sigma * float(scale))).to(source.dtype)
    return result


def select_scale(scale_tvs, target=0.12):
    return min(
        sorted(scale_tvs),
        key=lambda scale: (abs(statistics.median(scale_tvs[scale]) - target), scale),
    )


def estimate(values):
    values = [float(value) for value in values]
    if len(values) < 2 or not all(math.isfinite(value) for value in values):
        raise ValueError("invalid paired values")
    mean = statistics.mean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    return {"n": len(values), "bb_per_100": mean, "standard_error": se,
            "ci95": [mean - 1.96 * se, mean + 1.96 * se]}


def line_count(path):
    try:
        return Path(path).read_bytes().count(b"\n")
    except OSError:
        return 0


def guard():
    current = psutil.Process()
    names = {"train_v5.py", "run_pilot.py", "v6_mirror_eval.py", "play_slumbot_v6_journaled.py"}
    for process in psutil.process_iter(["pid", "cmdline"]):
        if process.pid in (current.pid, current.ppid()):
            continue
        if any(Path(arg).name in names for arg in process.info["cmdline"] or []):
            raise RuntimeError(f"conflicting research process {process.pid}")


def capture_code():
    target = BASE / "execution_code"
    target.mkdir()
    paths = [path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "scripts/alpha_holdem").glob("*.py"))]
    paths += [f"scripts/deep_cfr/{name}.py" for name in ("__init__", "game_state", "hand_eval")]
    paths += ["research/experiment_log.py"]
    paths += [path.relative_to(ROOT).as_posix() for path in sorted(BASE.iterdir()) if path.suffix in (".py", ".md")]
    capture_code_provenance(ROOT, target, paths)
    copies = []
    for relative in paths:
        destination = target / "source_files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        copies.append({"original": relative, "copy": destination.relative_to(ROOT).as_posix(), "sha256": sha(destination)})
    write(target / "copy_manifest.json", copies)
    return copies


def synthetic_observations(hands=256, seed=20261100):
    rng = random.Random(seed)
    rows = []
    for _ in range(hands):
        deck = list(range(52))
        rng.shuffle(deck)
        state = ChipState.new(deck)
        while not state.terminal:
            obs, table = observation(state, include_position=False)
            rows.append(obs)
            legal = [action for action in table if action is not None]
            state = apply_incr(state, rng.choice(legal))
    if len(rows) < 512:
        raise RuntimeError("synthetic cohort unexpectedly small")
    return rows


def policy_probabilities(model, observations, batch_size=512):
    result = []
    with torch.no_grad():
        for start in range(0, len(observations), batch_size):
            batch = observations[start:start + batch_size]
            tensors = [torch.as_tensor(np.stack([row[key] for row in batch]), dtype=torch.float32)
                       for key in ("card_info", "action_info", "extra_info", "legal_mask")]
            logits, _ = model(*tensors)
            values = logits.detach().cpu().numpy().astype(np.float64)
            for vector, row in zip(values, batch):
                legal = np.flatnonzero(row["legal_mask"])
                weights = np.exp(vector[legal] - np.max(vector[legal]))
                probs = np.zeros(9, dtype=np.float64)
                probs[legal] = weights / weights.sum()
                result.append(probs)
    return np.asarray(result)


def minimal_population_checkpoint(parent_checkpoint, standard_state, scale, seed, role):
    checkpoint = {
        key: copy.deepcopy(parent_checkpoint[key])
        for key in (
            "norm_layer", "separate_preflop_head", "critic_contract",
            "position_adapter_postflop_only", "position_adapter_min_street",
            "position_adapter_max_street", "starting_stack_bb",
        ) if key in parent_checkpoint
    }
    checkpoint.update(METADATA)
    checkpoint.update({
        "model": perturb_actor_state(standard_state, scale, seed),
        "legacy_weights_rebound_to_new_contract": True,
        "run_id": f"standard10_weight_population_{role}_{seed}",
        "iteration": int(parent_checkpoint.get("iteration", 0)),
        "total_hands": int(parent_checkpoint.get("total_hands", 0)),
        "weight_population": {
            "schema": "cardpilot.standard10_actor_perturbation.v1",
            "source_sha256": STANDARD10_SHA, "scale": float(scale),
            "seed": int(seed), "role": role, "actor_tensors": list(ACTOR_NAMES),
        },
    })
    return checkpoint


def materialize_population():
    standard = torch.load(STANDARD10, map_location="cpu", weights_only=False)
    parent = torch.load(PARENT, map_location="cpu", weights_only=False)
    standard_state = standard["model"]
    assert set(standard_state) == set(parent["model"])
    cohort = synthetic_observations()
    rebound = minimal_population_checkpoint(parent, standard_state, 0.0 + SCALE_GRID[0], 2026109999, "calibration_source")
    rebound["model"] = {name: tensor.detach().cpu().clone() for name, tensor in standard_state.items()}
    source_model = init_model(rebound, "cpu")
    source_probs = policy_probabilities(source_model, cohort)
    calibration = {}
    tv_by_scale = {}
    for scale in SCALE_GRID:
        tvs, disagreements = [], []
        for seed in CALIBRATION_SEEDS:
            checkpoint = minimal_population_checkpoint(parent, standard_state, scale, seed, "calibration")
            probs = policy_probabilities(init_model(checkpoint, "cpu"), cohort)
            tvs.append(float(np.mean(0.5 * np.abs(probs - source_probs).sum(axis=1))))
            disagreements.append(float(np.mean(np.argmax(probs, axis=1) != np.argmax(source_probs, axis=1))))
        tv_by_scale[scale] = tvs
        calibration[str(scale)] = {"mean_tvs": tvs, "greedy_disagreements": disagreements,
                                   "median_tv": statistics.median(tvs),
                                   "median_greedy_disagreement": statistics.median(disagreements)}
    selected = select_scale(tv_by_scale)
    population = BASE / "population"
    population.mkdir()
    rows = []
    for role, seeds in (("train", TRAIN_SEEDS), ("eval", EVAL_SEEDS)):
        for index, seed in enumerate(seeds):
            path = population / f"{role}{index}.pt"
            checkpoint = minimal_population_checkpoint(parent, standard_state, selected, seed, role)
            torch.save(checkpoint, path)
            loaded = torch.load(path, map_location="cpu", weights_only=False)
            assert all(torch.equal(loaded["model"][name], standard_state[name])
                       for name in standard_state if name not in ACTOR_NAMES)
            assert any(not torch.equal(loaded["model"][name], standard_state[name]) for name in ACTOR_NAMES)
            rows.append({"role": role, "index": index, "seed": seed, "scale": selected,
                         "path": str(path), "sha256": sha(path)})
    report = {"schema": "cardpilot.weight_population_manifest.v1", "standard10_sha256": STANDARD10_SHA,
              "parent_metadata_source_sha256": PARENT_SHA, "cohort_states": len(cohort),
              "scale_grid": list(SCALE_GRID), "target_tv": 0.12,
              "calibration": calibration, "selected_scale": selected, "members": rows}
    write(BASE / "population_manifest.json", report)
    return report


def training_command(train_paths):
    run = BASE / "production/train"
    return [
        "-u", "scripts/alpha_holdem/train_v5.py",
        "--device", "cuda", "--workers", "12", "--hands-per-iter", "4096",
        "--total-hands", "99999999", "--total-environment-hands", str(TARGET_PHYSICAL),
        "--starting-stack", "200", "--env-version", "v6", "--norm-layer", "gn",
        "--lr", ".00003", "--ppo-epochs", "2", "--ppo-target-kl", ".01",
        "--policy-advantage-clip", "3", "--source-policy-kl-coef", ".1",
        "--source-policy-reference-checkpoint", str(BASE / "frozen/parent_raw.pt"),
        "--separate-preflop-head", "--all-policy-heads-only-training",
        "--actor-ema-decay", ".9", "--mini-batch-size", "1024",
        "--entropy-coef", ".005", "--entropy-floor", ".05",
        "--pool-strategy", "latest", "--fixed-opponent-checkpoints", *map(str, train_paths),
        "--hero-policy-mode", "sample", "--self-play-fraction", ".25",
        "--opponent-assignment", "per-group", "--opponent-groups", "8",
        "--adaptive-opponent-league", "--adaptive-league-ema", ".9",
        "--adaptive-league-temperature-bb", "2", "--adaptive-league-min-probability", ".05",
        "--opponent-assignment-provenance-file", str(run / "opponent_assignments.jsonl"),
        "--rollout-mode", "multi", "--rollout-envs-per-worker", "8",
        "--inference-min-batch-slots", "0", "--inference-batch-deadline-us", "700",
        "--worker-seed-base", "2026110300", "--fixed-training-deal-stream",
        "--fixed-training-deal-start-index", str(START_PHYSICAL),
        "--critic-contract", "critic_v2", "--h1-effective-stack-divisor", "200",
        "--h1-critic-init-seed", "2026071102", "--value-coef", "1",
        "--autonomous-critic-v2-continue", "--snapshot-every", "999999",
        "--save-interval", "1", "--archive-checkpoint-every", "8",
        "--run-id", RUN_ID, "--run-dir", str(run), "--out", str(run / "latest.pt"),
        "--seed", "20261103", "--max-runtime-seconds", "1800",
        "--resume", str(BASE / "frozen/parent_raw.pt"), "--allow-resume",
        "--no-reset-optimizer", "--preserve-resumed-optimizer-lr", "--validate-stream",
    ]


def audit_training():
    run = BASE / "production/train"
    checkpoint = torch.load(run / "latest.pt", map_location="cpu", weights_only=False)
    account = checkpoint["environment_hand_accounting"]
    assert account["prefix_complete"] and account["completed_hands"] >= TARGET_PHYSICAL
    assert account["origin_run_id"] == RUN_ID and account["unknown_prefix_training_marker_hands"] == 0
    assert checkpoint["iteration"] > 27
    assert checkpoint["optimizer"]["param_groups"][0]["lr"] == pytest_approx(1e-5)
    rows = [json.loads(line) for line in (run / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert rows and rows[0]["iteration"] == 28 and rows[-1]["iteration"] == checkpoint["iteration"]
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in rows]
    assert all(left < right for left, right in zip([START_PHYSICAL] + counts[:-1], counts))
    audit = [
        "scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(run),
        "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(TARGET_PHYSICAL),
        "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "5",
        "--expected-archive-every", "8", "--expected-normalization", "global",
        "--out", str(run / "session_audit.json"),
    ]
    record(audit)
    with (run / "audit_stdout.log").open("x", encoding="utf-8") as output:
        subprocess.run([sys.executable, *audit], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(run / "session_audit.json")["status"] == "PASS"
    shutil.copy2(run / "latest.pt", BASE / "frozen/candidate.pt")
    return {"endpoint_environment_hands": int(account["completed_hands"]),
            "new_training_hands": int(account["completed_hands"]) - START_PHYSICAL,
            "iteration": int(checkpoint["iteration"]), "checkpoint_sha256": sha(BASE / "frozen/candidate.pt")}


def pytest_approx(value, tol=1e-12):
    class Approx:
        def __eq__(self, other):
            return abs(float(other) - value) <= tol
    return Approx()


def preservation(candidate_path):
    candidate_model, _, candidate_sha = load_policy(candidate_path, "cpu")
    parent_model, _, parent_sha = load_policy(BASE / "frozen/parent_raw.pt", "cpu")
    observations, metadata, inputs = [], [], []
    for session in range(1, 9):
        path = CORPUS / "sessions" / f"s{session:02d}/hands.jsonl"
        inputs.append({"path": str(path), "sha256": sha(path)})
        for hand_line, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hand = json.loads(line)
            assert hand["successful_hand"] == hand_line and hand["model_sha256"] == PARENT_SHA
            for decision_index, decision in enumerate(hand["decisions"]):
                response = decision["response"]
                state = from_external(response["action"], response["hole_cards"], response.get("board", []), response["client_pos"])
                obs, _ = observation(state, include_position=False)
                assert decision["legal_mask"] == obs["legal_mask"].tolist()
                observations.append(obs)
                metadata.append({"session": session, "hand": hand_line, "decision": decision_index,
                                 "street": int(state.street), "seat": int(response["client_pos"])})
    candidate_probs = policy_probabilities(candidate_model, observations)
    parent_probs = policy_probabilities(parent_model, observations)
    tvs = 0.5 * np.abs(candidate_probs - parent_probs).sum(axis=1)
    disagreements = np.argmax(candidate_probs, axis=1) != np.argmax(parent_probs, axis=1)
    with (BASE / "parent_state_metrics.jsonl").open("x", encoding="utf-8", newline="\n") as output:
        for meta, tv, disagree in zip(metadata, tvs, disagreements):
            output.write(json.dumps({**meta, "total_variation": float(tv),
                                     "greedy_disagreement": int(disagree)}, separators=(",", ":")) + "\n")
    result = {"states": len(observations), "candidate_sha256": candidate_sha,
              "parent_sha256": parent_sha, "mean_total_variation": float(np.mean(tvs)),
              "greedy_disagreement_rate": float(np.mean(disagreements)), "input_hands": inputs,
              "passed": bool(float(np.mean(tvs)) <= 0.02 and float(np.mean(disagreements)) <= 0.02)}
    write(BASE / "preservation.json", result)
    return result


def evaluate(candidate_manifest, eval_members, execution):
    jobs = []
    for label, candidate in candidate_manifest.items():
        for anchor in eval_members:
            out = BASE / "matrix" / f"{label}_anchor{anchor['index']}"
            command = ["scripts/alpha_holdem/v6_mirror_eval.py", "--candidate", candidate["path"],
                       "--anchor", anchor["path"], "--pairs", str(PAIRS), "--seed", str(EVAL_SEED),
                       "--device", "cpu", "--policy-mode", "greedy", "--out-dir", str(out)]
            record(command)
            jobs.append((label, anchor, out, command))

    def run(job):
        label, anchor, out, command = job
        log_path = BASE / f"{label}_anchor{anchor['index']}_stdout.log"
        with log_path.open("x", encoding="utf-8") as stream:
            process = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=stream,
                                       stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            info = {"role": f"eval_{label}_anchor{anchor['index']}", "pid": process.pid,
                    "command": [sys.executable, *command], "exit_code": None}
            execution["children"].append(info)
            info["exit_code"] = process.wait()
        return info

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        previous = -1
        while not all(future.done() for future in futures):
            count = sum(line_count(out / "pairs.jsonl") * 2 for _, _, out, _ in jobs)
            if count != previous:
                update("--count", f"evaluation_hands={count}")
                previous = count
            write(BASE / "execution.json", execution)
            time.sleep(5)
        outcomes = [future.result() for future in futures]
    assert all(row["exit_code"] == 0 for row in outcomes)
    values = {}
    decks = None
    for label, anchor, out, _ in jobs:
        summary = read(out / "summary.json")
        assert summary["status"] == "COMPLETED" and summary["policy_mode"] == "greedy"
        assert summary["pairs"] == PAIRS and summary["seed"] == EVAL_SEED
        assert summary["candidate_sha256"] == candidate_manifest[label]["sha256"]
        assert summary["anchor_sha256"] == anchor["sha256"]
        rows = [json.loads(line) for line in (out / "pairs.jsonl").read_text().splitlines()]
        current_decks = [row["deck"] for row in rows]
        if decks is None:
            decks = current_decks
        assert current_decks == decks
        values[label, anchor["index"]] = [sum(row["rewards_bb"]) * 50 for row in rows]
        update("--artifact", out / "summary.json", "--artifact", out / "pairs.jsonl",
               "--artifact", BASE / f"{label}_anchor{anchor['index']}_stdout.log")
    contrasts = []
    for index in range(5):
        contrasts.append({"anchor": index, **estimate([
            candidate - parent for candidate, parent in zip(values["candidate", index], values["parent", index])
        ])})
    aggregate = estimate([
        statistics.mean(values["candidate", index][pair] - values["parent", index][pair] for index in range(5))
        for pair in range(PAIRS)
    ])
    return contrasts, aggregate, len(jobs) * PAIRS * 2


def main():
    if sys.argv[1:] or any((BASE / name).exists() for name in ("execution.json", "execution_code", "production", "frozen", "population", "matrix")):
        raise ValueError("fixed experiment; preserve existing evidence")
    assert sha(STANDARD10) == STANDARD10_SHA and sha(PARENT) == PARENT_SHA
    assert read(CORPUS / "experiment.json")["status"] == "COMPLETED"
    assert read(CORPUS / "reviewed_analysis.json")["status"] == "PASS"
    assert read(CORPUS / "combined_audit.json")["status"] == "PASS"
    assert torch.cuda.is_available()
    guard()
    started = time.monotonic()
    execution = {"status": "RUNNING", "started_at": datetime.now(timezone.utc).isoformat(),
                 "children": [], "new_training_hands": 0, "evaluation_hands": 0, "slumbot_hands": 0}
    write(BASE / "execution.json", execution)
    update("--status", "RUNNING")
    try:
        copies = capture_code()
        update("--artifact", BASE / "execution_code/source_manifest.json",
               "--artifact", BASE / "execution_code/code.patch",
               "--artifact", BASE / "execution_code/copy_manifest.json")
        test = ["-m", "pytest", str(BASE / "test_pilot.py"), "-q", f"--junitxml={BASE / 'tests.xml'}"]
        record(test)
        subprocess.run([sys.executable, *test], cwd=ROOT, check=True)
        update("--artifact", BASE / "tests.xml")
        (BASE / "frozen").mkdir()
        shutil.copy2(PARENT, BASE / "frozen/parent_raw.pt")
        population = materialize_population()
        update("--artifact", BASE / "population_manifest.json", "--artifact", BASE / "frozen/parent_raw.pt",
               *[item for row in population["members"] for item in ("--artifact", row["path"])])
        train_paths = [row["path"] for row in population["members"] if row["role"] == "train"]
        command = training_command(train_paths)
        record(command)
        run = BASE / "production/train"
        run.mkdir(parents=True)
        with (BASE / "train_stdout.log").open("x", encoding="utf-8") as output:
            child = subprocess.Popen([sys.executable, *command], cwd=ROOT, stdout=output,
                                     stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            info = {"role": "training", "pid": child.pid, "command": [sys.executable, *command], "exit_code": None}
            execution["children"].append(info)
            previous = -1
            while child.poll() is None:
                try:
                    current = int(read(run / "run_manifest.json")["environment_hand_accounting"]["completed_hands"])
                except (OSError, KeyError, json.JSONDecodeError):
                    current = START_PHYSICAL
                added = max(0, current - START_PHYSICAL)
                if added != previous:
                    update("--count", f"new_training_hands={added}")
                    previous = added
                write(BASE / "execution.json", execution)
                time.sleep(5)
            info["exit_code"] = child.wait()
        if info["exit_code"]:
            raise RuntimeError("trainer failed; evidence preserved without retry")
        health = audit_training()
        execution["new_training_hands"] = health["new_training_hands"]
        update("--count", f"new_training_hands={health['new_training_hands']}",
               "--artifact", BASE / "train_stdout.log", "--artifact", run / "latest.pt",
               "--artifact", run / "run_manifest.json", "--artifact", run / "h1_training_metrics.jsonl",
               "--artifact", run / "opponent_assignments.jsonl", "--artifact", run / "session_audit.json",
               "--artifact", run / "audit_stdout.log", "--artifact", BASE / "frozen/candidate.pt")
        candidate_manifest = {
            "parent": {"path": str(BASE / "frozen/parent_raw.pt"), "sha256": PARENT_SHA},
            "candidate": {"path": str(BASE / "frozen/candidate.pt"), "sha256": health["checkpoint_sha256"]},
        }
        write(BASE / "candidate_manifest.json", candidate_manifest)
        update("--artifact", BASE / "candidate_manifest.json")
        eval_members = [row for row in population["members"] if row["role"] == "eval"]
        contrasts, aggregate, matrix_hands = evaluate(candidate_manifest, eval_members, execution)
        preserve = preservation(BASE / "frozen/candidate.pt")
        evaluation_hands = matrix_hands + preserve["states"] * 2
        passed = bool(aggregate["ci95"][0] > 0 and sum(row["bb_per_100"] > 0 for row in contrasts) >= 4 and preserve["passed"])
        decision = "ADMIT_SEPARATE_GREEDY_FRESH5K" if passed else "WEIGHT_POPULATION_SMOKE_NOT_PROMISING"
        analysis = {"status": "COMPLETED_PENDING_REVIEW", "decision": decision,
                    "new_training_hands": health["new_training_hands"], "lineage_environment_hands": health["endpoint_environment_hands"],
                    "evaluation_hands": evaluation_hands, "slumbot_hands": 0,
                    "selected_scale": population["selected_scale"], "per_anchor_contrasts": contrasts,
                    "aggregate_contrast": aggregate, "preservation": preserve, "gate_passed": passed,
                    "candidate_sha256": health["checkpoint_sha256"], "goal_achieved": False}
        write(BASE / "completed_analysis.json", analysis)
        execution.update({"status": "COMPLETED_PENDING_REVIEW", "evaluation_hands": evaluation_hands,
                          "finished_at": datetime.now(timezone.utc).isoformat(),
                          "wall_time_seconds": time.monotonic() - started})
        write(BASE / "execution.json", execution)
        update("--count", f"new_training_hands={health['new_training_hands']}",
               "--count", f"lineage_training_hands={health['endpoint_environment_hands']}",
               "--count", f"evaluation_hands={evaluation_hands}", "--artifact", BASE / "parent_state_metrics.jsonl",
               "--artifact", BASE / "preservation.json", "--artifact", BASE / "completed_analysis.json",
               "--artifact", BASE / "execution.json", "--metric", f"wall_time_seconds={execution['wall_time_seconds']}")
        reviewer = [str(BASE / "review_finish.py")]
        record(reviewer)
        subprocess.run([sys.executable, *reviewer], cwd=ROOT, check=True)
        print(json.dumps({"decision": decision, "training_hands": health["new_training_hands"],
                          "aggregate": aggregate, "preservation": preserve}, sort_keys=True), flush=True)
    except BaseException:
        execution["status"] = "NEEDS_REVIEW"
        execution["error"] = traceback.format_exc()
        execution["finished_at"] = datetime.now(timezone.utc).isoformat()
        execution["wall_time_seconds"] = time.monotonic() - started
        write(BASE / "execution.json", execution)
        try:
            update("--artifact", BASE / "execution.json", "--note",
                   "Execution error or interruption preserved; no retry, counter reset, or evidence overwrite was attempted.")
        finally:
            raise


if __name__ == "__main__":
    main()
