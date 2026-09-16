"""Corrected new-seed CTDE smoke using the frozen parent orchestration module."""
import importlib.util
import json
from pathlib import Path
import shutil
import statistics

import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE_MODULE = ROOT / "research/experiments/v6-centralized-critic-matched-smoke-20260831/run_smoke.py"
spec = importlib.util.spec_from_file_location("ctde_smoke_parent_module", SOURCE_MODULE)
impl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impl)
impl.BASE = BASE

_original_command = impl.command
_original_capture = impl.capture


def command(arm, frozen):
    result = _original_command(arm, frozen)
    replacements = {
        "--seed": "20261041",
        "--worker-seed-base": "2026104100",
        "--run-id": f"v6_ctde_corrected_{arm}_20260831",
    }
    for flag, value in replacements.items():
        result[result.index(flag) + 1] = value
    return result


def capture():
    copies = _original_capture()
    relative = SOURCE_MODULE.relative_to(ROOT).as_posix()
    target = BASE / "execution_code/source_files" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_MODULE, target)
    copies.append({"original": relative, "copy": target.relative_to(ROOT).as_posix(), "sha256": impl.sha(target)})
    impl.write(BASE / "execution_code/copy_manifest.json", copies)
    return copies


def health(arm, source_state):
    from alpha_holdem.policy_contract_v6 import validate_metadata
    directory = BASE / "production" / arm
    checkpoint = torch.load(directory / "latest.pt", map_location="cpu", weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint["environment_hand_accounting"]
    assert account["completed_hands"] >= impl.TARGET and account["prefix_complete"]
    assert account["unknown_prefix_training_marker_hands"] == 0
    assert account["origin_run_id"] == f"v6_ctde_corrected_{arm}_20260831"
    rows = [json.loads(line) for line in (directory / "h1_training_metrics.jsonl").read_text().splitlines()]
    assert [row["iteration"] for row in rows] == list(range(1, checkpoint["iteration"] + 1))
    counts = [row["environment_hand_accounting"]["completed_hands"] for row in rows]
    assert all(left < right for left, right in zip([0] + counts[:-1], counts)) and counts[-1] >= impl.TARGET
    for row in rows:
        impl.finite(row)
        assert bool(row["centralized_critic"]) == (arm == "treatment")
        assert float(row["preupdate_critic_mse"]) >= 0.0
    median_mse = statistics.median(float(row["preupdate_critic_mse"]) for row in rows[len(rows) // 2:])
    if arm == "control":
        assert len(checkpoint["model"]) == 86 and len(checkpoint["optimizer"]["state"]) == 10
        trainable = ("policy_head.", "preflop_policy_head.", "value_head.")
        assert all(torch.equal(checkpoint["model"][key], value) for key, value in source_state.items() if not key.startswith(trainable))
    else:
        assert len(checkpoint["model"]) == 92 and len(checkpoint["optimizer"]["state"]) == 10
        assert len([key for key in checkpoint["model"] if key.startswith("centralized_value_head.")]) == 6
        assert all(torch.equal(checkpoint["model"][key], value) for key, value in source_state.items() if not key.startswith(("policy_head.", "preflop_policy_head.")))
    audit = ["scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py", "--run-dir", str(directory), "--expected-target-hands", "99999999", "--expected-target-environment-hands", str(impl.TARGET), "--expected-final-iteration", str(checkpoint["iteration"]), "--expected-pool-size", "5", "--expected-archive-every", "4", "--expected-normalization", "global", "--out", str(directory / "session_audit.json")]
    impl.record(audit)
    with (directory / "audit_stdout.log").open("x") as output:
        impl.subprocess.run([impl.sys.executable, *audit], cwd=impl.ROOT, stdout=output, stderr=impl.subprocess.STDOUT, check=True)
    assert impl.read(directory / "session_audit.json")["status"] == "PASS"
    return int(account["completed_hands"]), median_mse


impl.command = command
impl.capture = capture
impl.health = health

ROOT, TARGET, PAIRS, ARMS = impl.ROOT, impl.TARGET, impl.PAIRS, impl.ARMS
sha, read, write, log, estimate, gate = impl.sha, impl.read, impl.write, impl.log, impl.estimate, impl.gate


def main():
    impl.main()


if __name__ == "__main__":
    main()
