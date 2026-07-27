from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h12_health_watch.py"
SPEC = importlib.util.spec_from_file_location("h12_health", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_transform_accepts_every_nonnegative_catchup_epoch() -> None:
    source = "a vhcatch=0 b\na vhcatch=1 b\na vhcatch=2 b\na vhcatch=17 b\n"
    transformed, replacements = MODULE.transform_log(source)
    assert replacements == 4
    assert "vhcatch=" not in transformed


def test_prepare_view_is_exact_and_does_not_modify_source(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    manifest = {"run_id": "h12", "iteration": 2, "total_hands": 3, "config": {"h12_window_arm": "control"}}
    raw = json.dumps(manifest)
    (run_dir / "run_manifest.json").write_text(raw, encoding="utf-8")
    source = "x vhcatch=0 y\nx vhcatch=3 y\n"
    (run_dir / "latest_train.log").write_text(source, encoding="utf-8")
    (run_dir / "console.err.log").write_bytes(b"")
    (run_dir / "h1_training_metrics.jsonl").write_text("{}\n{}\n", encoding="utf-8")
    view, provenance = MODULE.prepare_view(run_dir, raw, manifest)
    assert (run_dir / "latest_train.log").read_text(encoding="utf-8") == source
    assert "vhcatch=" not in (view / "latest_train.log").read_text(encoding="utf-8")
    assert provenance["replacement_count"] == 2
    assert provenance["source_changed"] is False


def test_missing_startup_log_is_pending_until_frozen_deadline(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert MODULE.startup_log_gate(run_dir, 100.0, 101.0, 180.0) == "PENDING"
    assert MODULE.startup_log_gate(run_dir, 100.0, 280.0, 180.0) == "TIMEOUT"
    (run_dir / "latest_train.log").write_text("ready\n", encoding="utf-8")
    assert MODULE.startup_log_gate(run_dir, 100.0, 999.0, 180.0) == "READY"
