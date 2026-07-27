"""Non-mutating coverage for v5_rearm_watchers.ps1 range resolution.

The production script's -ValidateOnly path returns before logging, PID inspection,
or watcher launch. These fixtures verify that a future re-arm starts at the live
next gate and rejects the old 12900..14000 continuation range.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "alpha_holdem" / "v5_rearm_watchers.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
RUN_ID = "rearm-range-fixture"


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_gate_status(
    root: Path,
    file_target: int,
    overall: str,
    *,
    reported_target: int | None = None,
    checkpoint_iteration: int | None = None,
    run_dir: str | None = None,
    run_id: str | None = RUN_ID,
) -> None:
    write_json(
        root / f"gate_{file_target}_status.json",
        {
            "target_iteration": file_target if reported_target is None else reported_target,
            "checkpoint_iteration": file_target if checkpoint_iteration is None else checkpoint_iteration,
            "overall": overall,
            "run_dir": str(root) if run_dir is None else run_dir,
            "run_id": run_id,
        },
    )


def make_fixture(
    root: Path,
    *,
    live_iteration: int,
    checkpoint_iteration: int,
    next_gate_iteration: int,
    passed_gate: int | None = None,
    run_id: str = RUN_ID,
    config: dict | None = None,
) -> None:
    write_json(root / "run_manifest.json", {"run_id": run_id, "config": config or {}})
    write_json(
        root / "v5_dashboard_watch_status.json",
        {
            "live_iteration": live_iteration,
            "checkpoint_iteration": checkpoint_iteration,
            "next_gate_target_iteration": next_gate_iteration,
        },
    )
    write_json(
        root / "progress_status.json",
        {
            "latest": {"iteration": live_iteration},
            "checkpoint": {"iteration": checkpoint_iteration},
        },
    )
    write_json(
        root / "v5_next_action_queue.json",
        {"queue": [{"key": f"gate_{next_gate_iteration}", "status": "WAITING"}]},
    )
    if passed_gate is not None:
        write_gate_status(root, passed_gate, "PASS")


def validate_only(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL, "PowerShell is required for the rearm watcher test"
    return subprocess.run(
        [
            POWERSHELL,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-RunDir",
            str(root),
            "-ValidateOnly",
            *extra,
        ],
        cwd=REPO,
        check=False,
        text=True,
        capture_output=True,
    )


def assert_no_rearm_artifacts(root: Path) -> None:
    assert not (root / "watcher_rearm.log").exists()
    assert not (root / "watcher_rearm_status.json").exists()


def test_ast_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "[int]$GateStartIteration = 0" in source
    assert "[int]$GateMaxIteration = 0" in source
    assert "[int]$InternalStartIteration = 0" in source
    assert "[int]$InternalMaxIteration = 0" in source
    assert "[switch]$ValidateOnly" in source
    assert "Refusing stale $Kind range" in source
    assert '"--expected-opponent-assignment", $script:expectedOpponentAssignment' in source
    assert '$script:isExp005EvidenceRun' in source
    assert "EXP-003 is terminally INCONCLUSIVE; EXP-005 evidence run must not reopen it" in source
    assert "EXPLORATORY_PILOT_NO_METHOD_JUDGMENT; promotion is forbidden" in source
    assert "v5_pilot_endpoint_stop_watch.py" in source
    assert '"--target-iteration", "32700"' in source
    assert '"--min-hands", "535989661"' in source
    assert '$script:isExp005CArm' in source
    assert '$script:isExpW1Arm' in source
    assert 'function Resolve-RepoPath' in source
    assert 'Launch-ExpW1EndpointFreeze' in source
    assert "'v5_hybrid_h1_endpoint_watch.py'" in source
    assert "'v5_hybrid_h2_endpoint_watch.py'" in source
    assert "'v5_hybrid_h2_protocol_watch.py'" in source
    assert "'v5_hybrid_h2_treatment_launch_watch.py'" in source
    assert "'v5_hybrid_h2_completion_watch.py'" in source
    assert "'v5_hybrid_h6_endpoint_watch.py'" in source
    assert "'v5_hybrid_h6_protocol_watch.py'" in source
    assert "'v5_hybrid_h6_completion_watch.py'" in source
    assert "'v5_hybrid_h7_endpoint_watch.py'" in source
    assert "'v5_hybrid_h7_protocol_watch.py'" in source
    assert "'v5_hybrid_h7_treatment_launch_watch.py'" in source
    assert "'v5_hybrid_h7_completion_watch.py'" in source
    assert "'v5_hybrid_h8_endpoint_watch.py'" in source
    assert "'v5_hybrid_h8_protocol_watch.py'" in source
    assert "'v5_hybrid_h8_treatment_launch_watch.py'" in source
    assert "'v5_hybrid_h8_completion_watch.py'" in source
    assert "v5_hybrid_h9_endpoint_watch.py" in source
    assert "v5_hybrid_h9_protocol_watch.py" in source
    assert "v5_hybrid_h9_treatment_launch_watch.py" in source
    assert "v5_hybrid_h9_completion_watch.py" in source
    assert (
        'if ($script:isHybridH1Arm -or $script:isHybridH2Arm -or '
        '$script:isHybridH6Arm -or $script:isHybridH7Arm -or '
        '$script:isHybridH8Arm -or $script:isHybridH9Arm) {'
    ) in source
    assert 'Launch-H2TreatmentLaunchWatch' in source
    assert 'Launch-H2CompletionWatch' in source
    assert '$protectedAncestorPids' in source
    assert 'preserving invoking ancestor watcher PID' in source
    assert "EXP-W1 arm blocks generic eval cadence" in source
    assert "EXP-W1 arm cannot launch promotion before both endpoints" in source
    assert "EXP-W1 arm cannot launch formal100k before primary PASS" in source
    assert "EXP005-C arm cannot launch promotion before both clean arms" in source


def test_exp_w1_validate_only_classifies_external_eval_block() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=31401,
            checkpoint_iteration=31400,
            next_gate_iteration=31500,
            run_id="v5_zero_l6_expw1_control_same31400_20m_r1_20260711",
            config={
                "opponent_assignment": "per-iteration",
                "exp_w1_design_lock": "reports/v5_exp_w1_design_lock_v2_20260711.json",
                "exp_w1_design_lock_sha256": "fixture",
            },
        )
        result = validate_only(root)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        classification = payload["run_classification"]
        assert classification["is_exp_w1_arm"] is True
        assert classification["block_generic_eval_and_slumbot"] is True
        assert_no_rearm_artifacts(root)


def test_completed_h1_without_watcher_artifacts_uses_exact_manifest_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(
            root / "run_manifest.json",
            {
                "run_id": "v5_hybrid_h1_treatment_criticv2_same31400_20m_r1_20260711",
                "iteration": 32617,
                "total_hands": 535996488,
                "status": "finished",
                "config": {"opponent_assignment": "per-iteration"},
            },
        )
        result = validate_only(root)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["resolution_version"] == "hybrid_h1_manifest_identity_v1"
        assert payload["safe_start_source"] == "hybrid-h1-exact-run-manifest"
        assert payload["high_water_iteration"] == 32617
        assert payload["gate"]["start_iteration"] == 0
        assert payload["internal"]["start_iteration"] == 0
        assert payload["run_classification"]["is_hybrid_h1_arm"] is True
        assert payload["run_classification"]["block_generic_eval_and_slumbot"] is True
        assert_no_rearm_artifacts(root)


def test_h6_validate_only_blocks_generic_and_slumbot_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(
            root / "run_manifest.json",
            {
                "run_id": "v5_hybrid_h6_treatment_kles003_same31400_20m_r1_20260713",
                "iteration": 31401,
                "total_hands": 516006089,
                "status": "running",
                "config": {"opponent_assignment": "per-iteration"},
            },
        )
        result = validate_only(root)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        classification = payload["run_classification"]
        assert classification["is_hybrid_h6_arm"] is True
        assert classification["block_generic_eval_and_slumbot"] is True
        assert payload["gate"]["start_iteration"] == 0
        assert payload["internal"]["start_iteration"] == 0
        assert_no_rearm_artifacts(root)


def test_h7_validate_only_blocks_generic_and_slumbot_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_json(root / "run_manifest.json", {"run_id": "v5_hybrid_h7_control_kl0_same31400_20m_r1_20260713", "iteration": 31401, "total_hands": 516006000, "status": "running", "config": {"opponent_assignment": "per-iteration"}})
        result = validate_only(root)
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["run_classification"]["is_hybrid_h7_arm"] is True
        assert payload["run_classification"]["block_generic_eval_and_slumbot"] is True
        assert payload["gate"]["start_iteration"] == 0
        assert_no_rearm_artifacts(root)

def test_current_next_gate_is_used_for_both_watchers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25522,
            checkpoint_iteration=25500,
            next_gate_iteration=25600,
            passed_gate=25500,
        )
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["high_water_iteration"] == 25522
        assert payload["safe_start_iteration"] == 25600
        assert payload["gate"]["start_iteration"] == 25600
        assert payload["gate"]["max_iteration"] == 26700
        assert payload["internal"]["start_iteration"] == 25600
        assert payload["internal"]["max_iteration"] == 26700
        assert_no_rearm_artifacts(root)


def test_passed_current_gate_advances_without_recreating_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25600,
            checkpoint_iteration=25600,
            next_gate_iteration=25600,
            passed_gate=25600,
        )
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["safe_start_iteration"] == 25700
        assert payload["gate"]["start_iteration"] == 25700
        assert payload["internal"]["start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_pending_current_saved_checkpoint_is_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25640,
            checkpoint_iteration=25600,
            next_gate_iteration=25700,
        )
        # Normal watcher behavior: the PENDING file was created while checkpoint
        # 25500 was current, so it must not be rejected for that prior checkpoint.
        write_gate_status(root, 25600, "PENDING", checkpoint_iteration=25500)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "CURRENT_SAVED_CHECKPOINT_PENDING"
        assert payload["safe_start_iteration"] == 25600
        assert payload["gate"]["start_iteration"] == 25600
        assert payload["internal"]["start_iteration"] == 25600
        assert_no_rearm_artifacts(root)


def test_anchored_pending_current_checkpoint_is_included() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25640,
            checkpoint_iteration=25600,
            next_gate_iteration=25700,
            passed_gate=25500,
        )
        write_gate_status(root, 25600, "PENDING", checkpoint_iteration=25500)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "CURRENT_SAVED_CHECKPOINT_PENDING"
        assert payload["safe_start_iteration"] == 25600
        assert payload["gate"]["start_iteration"] == 25600
        assert_no_rearm_artifacts(root)


def test_stale_prior_pending_is_not_replayed_after_saved_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25740,
            checkpoint_iteration=25700,
            next_gate_iteration=25800,
            passed_gate=25500,
        )
        write_gate_status(root, 25600, "PENDING")
        write_gate_status(root, 25700, "PASS")
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "PASS"
        assert payload["safe_start_iteration"] == 25800
        assert payload["gate"]["start_iteration"] == 25800
        assert payload["internal"]["start_iteration"] == 25800
        assert_no_rearm_artifacts(root)


def test_pending_latest_saved_checkpoint_is_included_after_prior_stale_pending() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25740,
            checkpoint_iteration=25700,
            next_gate_iteration=25800,
        )
        write_gate_status(root, 25600, "PENDING")
        write_gate_status(root, 25700, "PENDING", checkpoint_iteration=25600)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "CURRENT_SAVED_CHECKPOINT_PENDING"
        assert payload["safe_start_iteration"] == 25700
        assert payload["gate"]["start_iteration"] == 25700
        assert payload["internal"]["start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_mismatched_checkpoint_status_is_rejected_not_replayed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25640,
            checkpoint_iteration=25600,
            next_gate_iteration=25700,
            passed_gate=25500,
        )
        write_gate_status(root, 25600, "PENDING", reported_target=25500)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "MISMATCHED_TARGET"
        assert payload["safe_start_iteration"] == 25700
        assert payload["gate"]["start_iteration"] == 25700
        assert payload["internal"]["start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_pass_requires_target_checkpoint_identity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25600,
            checkpoint_iteration=25600,
            next_gate_iteration=25600,
        )
        write_gate_status(root, 25600, "PASS", checkpoint_iteration=25500)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "MISMATCHED_PASS_CHECKPOINT"
        assert payload["safe_start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_float_target_is_rejected_not_truncated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25640,
            checkpoint_iteration=25600,
            next_gate_iteration=25700,
            passed_gate=25500,
        )
        write_gate_status(root, 25600, "PENDING", reported_target=25600.4)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "MISMATCHED_TARGET"
        assert payload["safe_start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_float_pass_checkpoint_is_rejected_not_truncated() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25600,
            checkpoint_iteration=25600,
            next_gate_iteration=25600,
        )
        write_gate_status(root, 25600, "PASS", checkpoint_iteration=25600.4)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "MISMATCHED_PASS_CHECKPOINT"
        assert payload["safe_start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_pending_checkpoint_ahead_of_target_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25640,
            checkpoint_iteration=25600,
            next_gate_iteration=25700,
            passed_gate=25500,
        )
        write_gate_status(root, 25600, "PENDING", checkpoint_iteration=25700)
        result = validate_only(root)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["checkpoint_catchup"]["state"] == "PENDING_CHECKPOINT_AHEAD"
        assert payload["safe_start_iteration"] == 25700
        assert_no_rearm_artifacts(root)


def test_stale_range_override_is_refused_before_rearm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25522,
            checkpoint_iteration=25500,
            next_gate_iteration=25600,
        )
        result = validate_only(
            root,
            "-GateStartIteration",
            "12900",
            "-GateMaxIteration",
            "14000",
            "-InternalStartIteration",
            "12900",
            "-InternalMaxIteration",
            "14000",
        )
        assert result.returncode != 0
        assert "Refusing stale Gate range" in (result.stdout + result.stderr)
        assert_no_rearm_artifacts(root)


def test_stale_internal_range_override_is_refused_before_rearm() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_fixture(
            root,
            live_iteration=25522,
            checkpoint_iteration=25500,
            next_gate_iteration=25600,
        )
        result = validate_only(
            root,
            "-InternalStartIteration",
            "12900",
            "-InternalMaxIteration",
            "14000",
        )
        assert result.returncode != 0
        assert "Refusing stale Internal range" in (result.stdout + result.stderr)
        assert_no_rearm_artifacts(root)


if __name__ == "__main__":
    test_ast_contract()
    test_exp_w1_validate_only_classifies_external_eval_block()
    test_completed_h1_without_watcher_artifacts_uses_exact_manifest_identity()
    test_h6_validate_only_blocks_generic_and_slumbot_paths()
    test_h7_validate_only_blocks_generic_and_slumbot_paths()
    test_current_next_gate_is_used_for_both_watchers()
    test_passed_current_gate_advances_without_recreating_it()
    test_pending_current_saved_checkpoint_is_included()
    test_anchored_pending_current_checkpoint_is_included()
    test_stale_prior_pending_is_not_replayed_after_saved_checkpoint()
    test_pending_latest_saved_checkpoint_is_included_after_prior_stale_pending()
    test_mismatched_checkpoint_status_is_rejected_not_replayed()
    test_pass_requires_target_checkpoint_identity()
    test_float_target_is_rejected_not_truncated()
    test_float_pass_checkpoint_is_rejected_not_truncated()
    test_pending_checkpoint_ahead_of_target_is_rejected()
    test_stale_range_override_is_refused_before_rearm()
    test_stale_internal_range_override_is_refused_before_rearm()
    print("test_v5_rearm_watchers: PASS (18 checks)")
