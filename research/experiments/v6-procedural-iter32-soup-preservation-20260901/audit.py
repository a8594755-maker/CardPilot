from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
SOURCES = {
    "control": ROOT / (
        "research/experiments/v6-procedural-opponent-domain-randomization-pilot-20260901/"
        "control/checkpoints/checkpoint_iter000032_hands000000132038.pt"
    ),
    "treatment": ROOT / (
        "research/experiments/v6-procedural-opponent-domain-randomization-pilot-20260901/"
        "treatment/checkpoints/checkpoint_iter000032_hands000000131971.pt"
    ),
}
ACTOR_NAMES = (
    "policy_head.weight",
    "policy_head.bias",
    "preflop_policy_head.weight",
    "preflop_policy_head.bias",
)
ALPHA = 0.75
EXPECTED_SEEDS = list(range(2026111001, 2026111009))


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def main() -> None:
    checks: dict[str, bool] = {}
    manifest = read_json(BASE / "materialization.json")
    parent = torch.load(PARENT, map_location="cpu", weights_only=False)
    checks["fixed_alpha"] = manifest["alpha"] == ALPHA
    checks["actor_tensor_contract"] = tuple(manifest["actor_tensors"]) == ACTOR_NAMES
    checks["parent_input_hash"] = manifest["inputs"]["parent"]["sha256"] == sha(PARENT)
    candidates = {}
    for arm, source_path in SOURCES.items():
        source = torch.load(source_path, map_location="cpu", weights_only=False)
        candidate_path = BASE / "frozen" / f"{arm}.pt"
        candidate = torch.load(candidate_path, map_location="cpu", weights_only=False)
        candidates[arm] = candidate
        checks[f"{arm}_source_hash"] = manifest["inputs"][arm]["sha256"] == sha(source_path)
        checks[f"{arm}_candidate_hash"] = manifest["outputs"][arm]["sha256"] == sha(candidate_path)
        checks[f"{arm}_metadata"] = (
            candidate["actor_weight_soup"]["source_label"] == arm
            and candidate["actor_weight_soup"]["source_weight"] == ALPHA
            and candidate["actor_weight_soup"]["parent_weight"] == 1.0 - ALPHA
        )
        checks[f"{arm}_non_actor_parent_identical"] = all(
            torch.equal(value, parent["model"][name])
            for name, value in candidate["model"].items()
            if name not in ACTOR_NAMES
        )
        checks[f"{arm}_actor_exact"] = all(
            torch.equal(
                candidate["model"][name],
                torch.lerp(
                    parent["model"][name].detach().cpu(),
                    source["model"][name].detach().cpu(),
                    ALPHA,
                ).to(parent["model"][name].dtype),
            )
            for name in ACTOR_NAMES
        )

    preservation_dir = BASE / "preservation"
    preservation = read_json(preservation_dir / "summary.json")
    state_rows = rows(preservation_dir / "state_metrics.jsonl")
    treatment_tv = np.asarray(
        [row["treatment_total_variation"] for row in state_rows], dtype=np.float64
    )
    treatment_disagreement = np.asarray(
        [row["treatment_greedy_disagreement"] for row in state_rows], dtype=np.float64
    )
    checks["preservation_hash_and_count"] = (
        len(state_rows) == preservation["states"] == 14963
        and sha(preservation_dir / "state_metrics.jsonl")
        == preservation["state_metrics_sha256"]
    )
    checks["preservation_raw_recompute"] = (
        abs(float(treatment_tv.mean()) - preservation["treatment_mean_total_variation"])
        < 1e-12
        and abs(
            float(treatment_disagreement.mean())
            - preservation["treatment_greedy_disagreement_rate"]
        )
        < 1e-12
    )
    checks["preservation_gate_passed"] = (
        preservation["gate"]["passed"]
        and preservation["treatment_mean_total_variation"] <= 0.02
        and preservation["treatment_greedy_disagreement_rate"] <= 0.02
    )

    heldout_dir = BASE / "heldout_greedy_fresh32k"
    heldout = read_json(heldout_dir / "summary.json")
    pair_rows = rows(heldout_dir / "pairs.jsonl")
    deltas = np.asarray(
        [row["treatment_minus_control_bb_per_100"] for row in pair_rows],
        dtype=np.float64,
    )
    mean = float(deltas.mean())
    half = float(1.96 * deltas.std(ddof=1) / math.sqrt(len(deltas)))
    block_means = [
        float(
            np.mean(
                [
                    row["treatment_minus_control_bb_per_100"]
                    for row in pair_rows
                    if row["block_index"] == block
                ]
            )
        )
        for block in range(8)
    ]
    checks["fresh_seed_contract"] = heldout["block_seeds"] == EXPECTED_SEEDS
    checks["heldout_hash_and_count"] = (
        len(pair_rows) == heldout["pairs"] == 32768
        and sha(heldout_dir / "pairs.jsonl") == heldout["pairs_sha256"]
    )
    checks["heldout_checkpoint_hashes"] = (
        heldout["control_sha256"] == sha(BASE / "frozen/control.pt")
        and heldout["treatment_sha256"] == sha(BASE / "frozen/treatment.pt")
    )
    checks["heldout_raw_recompute"] = (
        abs(mean - heldout["treatment_minus_control_bb_per_100"]) < 1e-12
        and abs(mean - half - heldout["paired_delta_ci95"][0]) < 1e-12
        and abs(mean + half - heldout["paired_delta_ci95"][1]) < 1e-12
        and all(
            abs(value - heldout["blocks"][index]["treatment_minus_control_bb_per_100"])
            < 1e-12
            for index, value in enumerate(block_means)
        )
    )
    checks["heldout_gate_passed"] = (
        heldout["gate"]["passed"]
        and heldout["positive_blocks"] == 7
        and heldout["paired_delta_ci95"][0] > 0.0
    )

    report = {
        "schema": "cardpilot.procedural_iter32_soup_audit.v1",
        "passed": all(checks.values()),
        "checks": checks,
        "preservation": {
            "states": len(state_rows),
            "treatment_mean_total_variation": float(treatment_tv.mean()),
            "treatment_greedy_disagreement_rate": float(treatment_disagreement.mean()),
        },
        "heldout": {
            "pairs": len(pair_rows),
            "evaluation_hands": heldout["evaluation_hands"],
            "paired_delta_bb_per_100": mean,
            "paired_delta_ci95": [mean - half, mean + half],
            "positive_blocks": sum(value > 0 for value in block_means),
            "block_means": block_means,
        },
        "artifact_hashes": {
            str(path.relative_to(ROOT)): sha(path)
            for path in (
                BASE / "materialization.json",
                BASE / "frozen/control.pt",
                BASE / "frozen/treatment.pt",
                preservation_dir / "summary.json",
                preservation_dir / "state_metrics.jsonl",
                heldout_dir / "summary.json",
                heldout_dir / "pairs.jsonl",
            )
        },
        "decision": "ADMIT_SEPARATE_GENERIC_GREEDY_SLUMBOT_FRESH5K",
    }
    (BASE / "audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
