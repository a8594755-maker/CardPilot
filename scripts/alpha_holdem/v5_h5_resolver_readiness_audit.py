#!/usr/bin/env python3
"""Reporting-only H5 play-time resolver readiness audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def typecheck(repo: Path, package: str) -> dict[str, Any]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return {"package": package, "returncode": -1, "pass": False, "stdout": "", "stderr": "npm executable not found"}
    completed = subprocess.run(
        [npm, "--prefix", package, "run", "typecheck"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        shell=False,
    )
    return {"package": package, "returncode": completed.returncode, "pass": completed.returncode == 0, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}


def analyze_sources(resolver_text: str, slumbot_text: str, tree_text: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    realtime_scenarios = [name for name in ("srp_50bb", "srp_100bb", "3bet_50bb", "3bet_100bb") if name in resolver_text]
    exact_200bb_realtime = "srp_200bb" in resolver_text or "3bet_200bb" in resolver_text
    full_spot_coverage = all(token in resolver_text.lower() for token in ("limp", "4bet"))
    slumbot_integrated = "resolver" in slumbot_text.lower() or "resolveSubgame" in slumbot_text
    pipeline_200bb_exists = "PIPELINE_SRP_V3_200BB_CONFIG" in tree_text
    typechecks_pass = all(row.get("pass") is True for row in checks)
    gates = {
        "typescript_typechecks_pass": typechecks_pass,
        "exact_200bb_realtime_scenario": exact_200bb_realtime,
        "complete_hunl_spot_coverage": full_spot_coverage,
        "v55_9slot_legality_bridge_proven": False,
        "slumbot_harness_integration": slumbot_integrated,
        "deterministic_greedy_direct_contract_proven": False,
        "registered_latency_bundle_pass": False,
        "pipeline_200bb_config_exists_but_is_not_realtime_authority": pipeline_200bb_exists,
    }
    ready = all(gates[key] for key in (
        "typescript_typechecks_pass",
        "exact_200bb_realtime_scenario",
        "complete_hunl_spot_coverage",
        "v55_9slot_legality_bridge_proven",
        "slumbot_harness_integration",
        "deterministic_greedy_direct_contract_proven",
        "registered_latency_bundle_pass",
    ))
    return {
        "overall": "PASS_H5_RESOLVER_PREREQUISITES_READY" if ready else "FAIL_CLOSED_H5_PREREQUISITES_INCOMPLETE",
        "gates": gates,
        "realtime_scenarios_observed": realtime_scenarios,
        "missing": [key for key, value in gates.items() if value is False],
    }


def build(repo: Path) -> dict[str, Any]:
    resolver = repo / "apps/bot-client/src/realtime-resolver.ts"
    subgame = repo / "packages/cfr-solver/src/vectorized/subgame-resolver.ts"
    tree = repo / "packages/cfr-solver/src/tree/tree-config.ts"
    slumbot = repo / "scripts/alpha_holdem/play_slumbot.py"
    checks = [typecheck(repo, "apps/bot-client"), typecheck(repo, "packages/cfr-solver")]
    analysis = analyze_sources(
        resolver.read_text(encoding="utf-8-sig"),
        slumbot.read_text(encoding="utf-8-sig"),
        tree.read_text(encoding="utf-8-sig"),
        checks,
    )
    return {
        "schema_version": "v5.hybrid.h5.resolver_readiness_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **analysis,
        "typechecks": checks,
        "source_identity": [
            {"path": str(path.resolve()), "sha256": sha256(path)}
            for path in (resolver, subgame, tree, slumbot)
        ],
        "inference": "Existing resolver code is an engineering starting point only. A separately frozen 200bb full-HUNL legality/latency/integration design is required before H5 preregistration.",
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
        "strength_claim": "FORBIDDEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(f"one-shot output exists: {args.out}")
    result = build(args.repo.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "missing": result["missing"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
