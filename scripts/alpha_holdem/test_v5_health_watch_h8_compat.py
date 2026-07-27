"""Reporting-only regression coverage for H8 health-log compatibility."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.alpha_holdem.v5_health_watch import prepare_monitor_run_dir, read_json_snapshot, run_monitor


LOG_LINE = (
    "[32618] hands=536,017,671 rew=+1.271 rew100=+1.271 ploss=-0.0015 "
    "vloss=1679.124219 vloss_bb2=1679.1242 ent=1.3490 kl=0.0225 ep=4/4 "
    "klstop=0 vhcatch=0 clipfrac=0.149 d1bite=0.003 aprior=2.3110 "
    "r50=1.00/r95=1.13/r99=1.29/rmax=7.48 eps=0.000 pool=5 mirror=0/0 "
    "aiev=490:76316 aiev_skip=0:0 trans=35105 terms=16385 "
    "mix=F0.175/C0.274/R0.530/A0.020 pmix=F0.197/C0.369/R0.422/A0.012 "
    "xmix=F0.156/C0.190/R0.625/A0.028 h/s=2062 tdec/s=4418 "
    "inf_bs=147.0 collect=7.9s ppo=5.1s\n"
)


def fixture(root: Path) -> None:
    (root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "v5_hybrid_h8_control_fixture",
                "iteration": 32618,
                "total_hands": 536017671,
                "config": {"h8_window_arm": "control", "env_version": "v55"},
            }
        ),
        encoding="utf-8",
    )
    (root / "latest_train.log").write_text(LOG_LINE, encoding="utf-8")
    (root / "console.err.log").write_bytes(b"")


def arguments() -> SimpleNamespace:
    return SimpleNamespace(
        preflop_call_warn_after_iter=200,
        preflop_call_warn=0.03,
        preflop_call_fail=0.005,
        preflop_dominance_warn=0.90,
        preflop_dominance_fail=0.97,
        preflop_allin_warn=0.12,
        preflop_allin_fail=0.25,
        stderr_recent_minutes=5.0,
    )


def test_adapter_removes_only_h8_reporting_token(tmp_path: Path) -> None:
    fixture(tmp_path)
    monitor_dir, provenance = prepare_monitor_run_dir(tmp_path)
    transformed = (monitor_dir / "latest_train.log").read_text(encoding="utf-8")
    assert "vhcatch=" not in transformed
    assert transformed == LOG_LINE.replace(" vhcatch=0", "")
    assert provenance is not None
    assert provenance["replacement_count"] == 1
    assert provenance["source_line_count"] == provenance["transformed_line_count"] == 1


def test_frozen_monitor_publishes_exact_h8_health(tmp_path: Path) -> None:
    fixture(tmp_path)
    code, output = run_monitor("python", tmp_path, arguments())
    assert code == 0, output
    health = json.loads((tmp_path / "health_status.json").read_text(encoding="utf-8"))
    assert health["overall"] == "PASS"
    assert health["latest"]["iteration"] == 32618
    assert health["latest"]["hands"] == 536017671
    assert health["reporting_adapter"]["replacement_count"] == 1
    assert health["reporting_adapter"]["frozen_monitor_sha256"]


def test_same_reporting_adapter_supports_h9_identity(tmp_path: Path) -> None:
    fixture(tmp_path)
    manifest_path = tmp_path / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = "v5_hybrid_h9_control_fixture"
    manifest["config"]["h8_window_arm"] = "none"
    manifest["config"]["h9_window_arm"] = "control"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    code, output = run_monitor("python", tmp_path, arguments())
    assert code == 0, output
    health = json.loads((tmp_path / "health_status.json").read_text(encoding="utf-8"))
    assert health["overall"] == "PASS"
    assert health["latest"]["iteration"] == 32618
    assert health["reporting_adapter"]["window"] == "H9"
    assert health["reporting_adapter"]["replacement_count"] == 1


def test_manifest_snapshot_retries_a_partial_producer_write(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "run_manifest.json"
    path.write_text('{"run_id":"exact"}', encoding="utf-8")
    original = Path.read_text
    reads = iter(["{\n", '{"run_id":"exact"}'])

    def controlled_read(self: Path, *args, **kwargs):
        if self == path:
            return next(reads)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", controlled_read)
    raw, value, attempts = read_json_snapshot(path, attempts=2, delay_seconds=0.0)
    assert raw == '{"run_id":"exact"}'
    assert value == {"run_id": "exact"}
    assert attempts == 2
