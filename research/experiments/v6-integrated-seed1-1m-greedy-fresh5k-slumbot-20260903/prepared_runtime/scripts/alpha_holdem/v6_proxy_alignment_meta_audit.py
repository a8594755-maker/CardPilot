"""Read-only audit of internal proxies and fresh5k-to-20k confirmation."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np


CONFIRMATION_PAIRS = [
    ("standard10", "v6-standard10-legacy-observation-bridge-greedy-fresh5k-slumbot-20260901", "v6-standard10-legacy-bridge-greedy-fresh20k-20260901"),
    ("legacy_iter16", "v6-legacy-iter16-greedy-fresh5k-20260901", "v6-legacy-iter16-greedy-fresh20k-20260901"),
    ("procedural_soup", "v6-procedural-iter32-soup-greedy-fresh5k-slumbot-20260901", "v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901"),
    ("actor_raw", "v6-actor-raw-greedy-fresh5k-slumbot-20260901", "v6-actor-raw-greedy-fresh20k-slumbot-20260901"),
    ("mgda_seed1_12k", "v6-mgda-seed1-12k-dual-greedy-fresh5k-multiseed-20260901", "v6-mgda-seed1-12k-dual-greedy-fresh20k-confirmation-20260901"),
]

INTERNAL_EXTERNAL_ROUTES = [
    ("physical_1m", "v6-physical1m-independent-confirmation-20260831", "physical-budget-1m-learning-curve-20260830", "v6-physical1m-fresh20k-slumbot-20260831", None),
    ("representation_full", "representation-scope-independent-confirmation-20260831", "matched-weak-kl-representation-curve-20260830", "representation-full-strict-sampled-slumbot20k-20260831", None),
    ("weak_source_kl", "weak-source-kl-independent-confirmation-20260830", "weak-source-kl-pilot-20260830", "weak-kl-strict-sampled-slumbot20k-20260830", None),
    ("procedural_soup", "v6-procedural-iter32-soup-preservation-20260901", "v6-procedural-opponent-domain-randomization-pilot-20260901", "v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901", None),
    ("legacy_iter16", "v6-legacy-contract-curve-independent-replication-20260901", "v6-legacy-contract-mixed-league-65k-pilot-20260901", "v6-legacy-iter16-greedy-fresh20k-20260901", None),
    ("mgda_seed1_12k", "v6-mgda-seed1-12k-continuation-replication-20260901", "v6-dual-contract-mgda-fresh-8k-two-seed-curve-20260901", "v6-mgda-seed1-12k-dual-greedy-fresh20k-confirmation-20260901", 12288),
]


def first_number(mapping: dict, names: tuple[str, ...]):
    for name in names:
        value = mapping.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def external_score(record: dict) -> tuple[float, float | None, float | None]:
    metrics = record.get("metrics", {})
    bb = first_number(metrics, ("bb_per_100", "raw_bb100", "candidate_bb100"))
    low = first_number(metrics, ("ci95_low_bb_per_100", "ci95_lower_bb_per_100", "ci95_lower", "raw_ci95_lower", "raw_ci95_low"))
    high = first_number(metrics, ("ci95_high_bb_per_100", "ci95_upper_bb_per_100", "ci95_upper", "raw_ci95_upper", "raw_ci95_high"))
    summary = str(record.get("result", {}).get("summary", ""))
    if bb is None:
        match = re.search(r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*bb/100", summary)
        if not match:
            raise ValueError(f"No external score in {record.get('id')}")
        bb = float(match.group(1))
    if low is None or high is None:
        match = re.search(
            r"(?:raw\s*)?95%\s*CI\s*\[\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*,\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*\]",
            summary,
            flags=re.IGNORECASE,
        )
        if match:
            low = float(match.group(1)) if low is None else low
            high = float(match.group(2)) if high is None else high
    return bb, low, high


def checkpoint_hashes(record: dict, repo: Path) -> set[str]:
    hashes = {
        value.get("sha256")
        for path, value in record.get("artifact_integrity", {}).items()
        if path.lower().endswith((".pt", ".pth")) and value.get("sha256")
    }
    source = record.get("source")
    if isinstance(source, str) and source.lower().endswith((".pt", ".pth")):
        path = repo / source
        if path.is_file():
            import hashlib
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            hashes.add(digest)
    return hashes


def internal_signal(record: dict) -> dict:
    metrics = record.get("metrics", {})
    preferred = [
        "final_sampled_standard10_delta_bb100", "final_sampled_slumbot_free_delta_bb100",
        "final_sampled_cfr96_delta_bb100", "fresh_procedural_delta_bb_per_100",
        "fresh_procedural_delta_ci95_lower", "iter16_delta_bb100",
        "iter16_bonferroni_lower", "pooled_delta_bb100", "combined_two_seed_slope_bb100",
        "combined_two_seed_ci95_low_bb100", "later_greedy_agreement", "disagreement_growth",
        "replication_passed", "final_sampled_confirmation_admission",
    ]
    return {key: metrics[key] for key in preferred if key in metrics}


def audit(experiments: Path) -> dict:
    repo = experiments.resolve().parents[1]
    records = {
        path.parent.name: json.loads(path.read_text(encoding="utf-8"))
        for path in experiments.glob("*/experiment.json")
    }
    confirmation_rows = []
    for label, pilot_id, confirm_id in CONFIRMATION_PAIRS:
        pilot, confirm = records[pilot_id], records[confirm_id]
        pilot_hashes, confirm_hashes = checkpoint_hashes(pilot, repo), checkpoint_hashes(confirm, repo)
        if not pilot_hashes.intersection(confirm_hashes):
            raise ValueError(f"No shared frozen checkpoint identity for {label}")
        pilot_bb, pilot_low, pilot_high = external_score(pilot)
        confirm_bb, confirm_low, confirm_high = external_score(confirm)
        confirmation_rows.append({
            "label": label, "pilot_id": pilot_id, "confirmation_id": confirm_id,
            "shared_checkpoint_sha256": sorted(pilot_hashes.intersection(confirm_hashes))[0],
            "pilot_hands": int(pilot["accounting"]["slumbot_hands"]),
            "pilot_bb100": pilot_bb, "pilot_ci95": [pilot_low, pilot_high],
            "confirmation_hands": int(confirm["accounting"]["slumbot_hands"]),
            "confirmation_bb100": confirm_bb, "confirmation_ci95": [confirm_low, confirm_high],
            "pilot_minus_confirmation_bb100": pilot_bb - confirm_bb,
            "pilot_positive": pilot_bb > 0, "confirmation_positive": confirm_bb > 0,
        })
    pilot_values = np.asarray([row["pilot_bb100"] for row in confirmation_rows])
    confirmation_values = np.asarray([row["confirmation_bb100"] for row in confirmation_rows])
    optimism = pilot_values - confirmation_values

    route_rows = []
    for label, internal_id, training_id, external_id, selected_lineage_hands in INTERNAL_EXTERNAL_ROUTES:
        internal, training, external = records[internal_id], records[training_id], records[external_id]
        bb, low, high = external_score(external)
        training_new_hands = int(training.get("accounting", {}).get("new_training_hands", 0) or 0)
        if training_new_hands <= 0:
            raise ValueError(f"No new training hands in route training record {training_id}")
        route_rows.append({
            "label": label, "internal_id": internal_id, "training_id": training_id, "external_id": external_id,
            "internal_decision": internal.get("result", {}).get("decision"),
            "internal_signal": internal_signal(internal),
            "training_record_total_new_hands": training_new_hands,
            "selected_policy_lineage_hands": selected_lineage_hands,
            "external_hands": int(external.get("accounting", {}).get("slumbot_hands", external.get("accounting", {}).get("evaluation_hands", 0)) or 0),
            "external_bb100": bb, "external_ci95": [low, high],
            "external_point_positive": bb > 0,
        })
    positive_pilots = [row for row in confirmation_rows if row["pilot_positive"]]
    checks = {
        "records_scanned": len(records),
        "same_policy_pairs": len(confirmation_rows),
        "all_same_policy_confirmations_negative": all(not row["confirmation_positive"] for row in confirmation_rows),
        "positive_5k_pilots": len(positive_pilots),
        "positive_5k_false_confirmations": sum(not row["confirmation_positive"] for row in positive_pilots),
        "mean_selected_pilot_optimism_bb100": float(optimism.mean()),
        "median_selected_pilot_optimism_bb100": float(np.median(optimism)),
        "pilot_confirmation_pearson": float(np.corrcoef(pilot_values, confirmation_values)[0, 1]),
        "internal_admission_routes": len(route_rows),
        "internal_admission_routes_with_negative_external_point": sum(not row["external_point_positive"] for row in route_rows),
    }
    protocol = {
        "training_curve_hands_per_seed": [65536, 262144, 1048576],
        "minimum_training_seeds_before_external": 3,
        "training_opponents": "at least six heterogeneous learned/procedural/solver anchors",
        "holdout_opponents": "at least three untouched anchors absent from gradient objectives",
        "internal_admission": [
            "positive geometric slope in at least two of three seeds",
            "nonnegative median delta across holdout opponents and both seats",
            "Standard10 greedy agreement at least 95% with no seat/street partition below 90%",
            "optimizer/common-descent and frozen-evidence contracts pass",
        ],
        "checkpoint_selection": "preregister robust median seed/checkpoint; never select the best fresh5k result",
        "external_first_gate_hands": 20000,
        "external_100k_admission": "same-policy 20k point > 0, both seats >= 0, and lower CI > -11.4275",
        "scale_interpretation": "failure at <=1M is undertraining unless mechanism/proxy or stability evidence is contradictory",
    }
    return {
        "schema": "cardpilot.proxy_alignment_meta_audit.v1",
        "confirmation_pairs": confirmation_rows,
        "internal_external_routes": route_rows,
        "checks": checks,
        "recommended_protocol": protocol,
        "decision": "REQUIRE_MULTI_SEED_BROAD_HOLDOUT_CURVES_AND_20K_FIRST_EXTERNAL_GATE",
        "caveat": "The promoted 5k pilots are selection-biased, so optimism estimates describe this research process rather than an unbiased 5k estimator.",
    }


def markdown(result: dict) -> str:
    lines = [
        "# Proxy alignment meta-audit", "",
        "## Same-policy 5k to 20k", "",
        "| Policy | 5k bb/100 | 20k bb/100 | 5k optimism |",
        "|---|---:|---:|---:|",
    ]
    for row in result["confirmation_pairs"]:
        lines.append(f"| {row['label']} | {row['pilot_bb100']:+.4f} | {row['confirmation_bb100']:+.4f} | {row['pilot_minus_confirmation_bb100']:+.4f} |")
    lines += ["", "## Internal-pass routes", "", "| Route | Internal decision | External bb/100 |", "|---|---|---:|"]
    for row in result["internal_external_routes"]:
        lines.append(f"| {row['label']} | `{row['internal_decision']}` | {row['external_bb100']:+.4f} |")
    lines += ["", "## Decision", "", f"`{result['decision']}`", "", result["caveat"], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiments", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    result = audit(args.experiments.resolve())
    (args.out_dir / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out_dir / "analysis.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result["checks"], sort_keys=True))
    print(result["decision"])


if __name__ == "__main__":
    main()
