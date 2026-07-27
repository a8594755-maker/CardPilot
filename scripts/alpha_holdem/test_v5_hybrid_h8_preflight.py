"""Regression tests for H8 preflight Path-1 worker identity."""

from scripts.alpha_holdem.v5_hybrid_h8_preflight import is_path1_worker_command


def test_counts_exact_solver_worker_command() -> None:
    command = (
        '"C:\\Program Files\\nodejs\\node.exe" --import tsx '
        'C:\\Users\\a8594\\CardPilot\\packages\\cfr-solver\\src\\orchestration\\solve-worker.ts'
    )
    assert is_path1_worker_command(command)


def test_excludes_coordinator_console_host() -> None:
    assert not is_path1_worker_command(r"\\??\\C:\\WINDOWS\\system32\\conhost.exe 0x4")


def test_excludes_unrelated_node_process() -> None:
    assert not is_path1_worker_command(
        r'"C:\\Program Files\\nodejs\\node.exe" mcp-server.js'
    )
