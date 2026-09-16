#!/usr/bin/env python3
"""Preregistered hand-level loss attribution with held-out teacher-proxy checks."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from alpha_holdem.legacy_observation_bridge_v6 import (  # noqa: E402
    legacy_observation_from_state,
    load_policy,
)
from alpha_holdem.policy_contract_v6 import action_table, from_external  # noqa: E402


CORPORA = {
    "seed1_1m_onpolicy": {
        "root": ROOT / "research/experiments/v6-integrated-seed1-1m-greedy-fresh20k-slumbot-20260903",
        "policy_sha256": "6fbbe021b140b91e448917ae3e2cbb9bcdca444865433074ac944cae79fa844a",
        "policy_pair": "standard10_vs_1m",
    },
    "seed1_2m_onpolicy": {
        "root": ROOT / "research/experiments/v6-integrated-seed1-2m-greedy-fresh20k-slumbot-20260903",
        "policy_sha256": "993fe99bd0a5ac0eaa0135e449315752d99efc25bedf220f93a1ad08884344c3",
        "policy_pair": "standard10_vs_2m",
    },
}
DRIFT_ROOT = ROOT / "research/experiments/v6-integrated-1m-2m-slumbot-state-drift-20260903/cpu_exact"
DRIFT_RAW = DRIFT_ROOT / "drift_raw.jsonl.gz"
DRIFT_ANALYSIS = DRIFT_ROOT / "analysis.json"
CFR4_PATH = ROOT / "research/experiments/v6-cfr4-full-e2-greedy-fresh20k-confirmation-20260901/frozen/final.pt"
CFR4_SHA256 = "571a9c413834247c80b63a797548689ea745878c060f265876d00bddcc3ff2db"
STANDARD10_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
BATCH_SIZE = 512
MIN_CLASS_HANDS = 200
MIN_PROXY_ROWS = 100
MIN_CONFIRM_DELTA_BB100 = -10.0
MIN_PROXY_UPLIFT = 0.02
MIN_TEACHER_MARGIN = 0.05
MAX_NOMINEES = 12


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bucket(value: float, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for cut, label in zip(cuts, labels):
        if value < cut:
            return label
    return labels[-1]


def street_name(street: int) -> str:
    return ("preflop", "flop", "turn", "river")[street]


def preflop_topology(action: str) -> str:
    preflop = action.split("/", 1)[0]
    raises = len(re.findall(r"b\d+", preflop))
    if raises == 0:
        return "unraised"
    if raises == 1:
        return "single_raised"
    if raises == 2:
        return "three_bet"
    return "four_bet_plus"


def selected_action_class(decision: dict) -> str:
    slot = int(decision["selected_action_slot"])
    if slot == 0:
        return "fold"
    if slot == 1:
        return "check_call"
    if slot == 8:
        return "all_in"
    return "raise"


def margin_bucket(value: float | None) -> str:
    if value is None:
        return "no_decision"
    return bucket(value, (0.05, 0.15, 0.35, float("inf")), ("lt05", "05to15", "15to35", "ge35"))


@torch.no_grad()
def infer(model, observations: list[dict]) -> np.ndarray:
    tensors = [
        torch.as_tensor(np.stack([obs[key] for obs in observations]), dtype=torch.float32)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    logits = logits.masked_fill(tensors[-1] <= 0, float("-inf"))
    return torch.softmax(logits, dim=-1).cpu().numpy()


def collapse_to_physical(raw: np.ndarray, legacy_table: list, state) -> np.ndarray:
    _, physical_table = action_table(state)
    result = np.zeros(9, dtype=np.float64)
    for slot, probability in enumerate(raw):
        if probability <= 0:
            continue
        action = legacy_table[slot]
        matches = [index for index, current in enumerate(physical_table) if current == action]
        if not matches:
            raise ValueError(f"legacy action {action!r} absent from physical table")
        result[matches[0]] += float(probability)
    if not math.isclose(float(result.sum()), 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("collapsed distribution is not normalized")
    return result


def probability_margin(probabilities: np.ndarray) -> float:
    legal = np.sort(probabilities[probabilities > 0])
    return float(legal[-1] - legal[-2]) if len(legal) > 1 else 1.0


def class_keys(row: dict) -> list[str]:
    singles = (
        "seat", "terminal_kind", "max_street", "preflop_topology",
        "max_exposure_bucket", "final_street", "final_action_class",
        "final_pot_bucket", "min_margin_bucket", "final_margin_bucket",
    )
    interactions = (
        ("seat", "max_street"),
        ("seat", "preflop_topology"),
        ("final_street", "final_action_class"),
        ("final_street", "max_exposure_bucket"),
        ("terminal_kind", "max_exposure_bucket"),
    )
    keys = [f"{field}={row[field]}" for field in singles]
    keys.extend("|".join(f"{field}={row[field]}" for field in fields) for fields in interactions)
    return keys


def outcome_metrics(rows: list[dict], key: str) -> dict:
    selected = [row for row in rows if key in row["class_keys"]]
    complement = [row for row in rows if key not in row["class_keys"]]
    if not selected or not complement:
        return {"hands": len(selected), "complement_hands": len(complement)}
    rewards = np.asarray([row["winnings_bb"] for row in selected], dtype=np.float64)
    other = np.asarray([row["winnings_bb"] for row in complement], dtype=np.float64)
    session_bb100 = {}
    for session in sorted({int(row["session"]) for row in rows}):
        values = [row["winnings_bb"] for row in selected if int(row["session"]) == session]
        session_bb100[str(session)] = float(np.mean(values) * 100.0) if values else None
    delta = float((rewards.mean() - other.mean()) * 100.0)
    return {
        "hands": len(selected),
        "complement_hands": len(complement),
        "net_bb": float(rewards.sum()),
        "bb100": float(rewards.mean() * 100.0),
        "complement_bb100": float(other.mean() * 100.0),
        "class_minus_complement_bb100": delta,
        "negative_excess_bb": float(max(0.0, -delta) * len(selected) / 100.0),
        "negative_sessions": sum(value is not None and value < 0 for value in session_bb100.values()),
        "session_bb100": session_bb100,
    }


def proxy_metrics(rows: list[dict], key: str) -> dict:
    selected = [row for row in rows if key in row["class_keys"] and row["teacher_admissible"]]
    complement = [row for row in rows if key not in row["class_keys"] and row["teacher_admissible"]]
    if not selected or not complement:
        return {"rows": len(selected), "complement_rows": len(complement)}
    selected_rate = float(np.mean([row["onpolicy_vs_teacher_consensus"] for row in selected]))
    complement_rate = float(np.mean([row["onpolicy_vs_teacher_consensus"] for row in complement]))
    return {
        "rows": len(selected),
        "complement_rows": len(complement),
        "disagreement_rate": selected_rate,
        "complement_disagreement_rate": complement_rate,
        "disagreement_uplift": selected_rate - complement_rate,
    }


def tail_summary(rows: list[dict]) -> dict:
    rewards = np.asarray([row["winnings_bb"] for row in rows], dtype=np.float64)
    result = {"hands": len(rows), "net_bb": float(rewards.sum()), "bb100": float(rewards.mean() * 100.0)}
    for percentile in (0.01, 0.05, 0.95, 0.99):
        result[f"q{int(percentile * 100):02d}_bb"] = float(np.quantile(rewards, percentile))
    for threshold in (-100.0, -50.0, 50.0, 100.0):
        if threshold < 0:
            mask = rewards <= threshold
            label = f"le_{abs(int(threshold))}bb"
        else:
            mask = rewards >= threshold
            label = f"ge_{int(threshold)}bb"
        result[label] = {"hands": int(mask.sum()), "net_bb": float(rewards[mask].sum())}
    return result


def main() -> None:
    if sys.argv[1:]:
        raise ValueError("this preregistered analysis takes no runtime arguments")
    raw_out = BASE / "hand_attribution_raw.jsonl.gz"
    analysis_out = BASE / "analysis.json"
    manifest_out = BASE / "input_manifest.json"
    if any(path.exists() for path in (raw_out, analysis_out, manifest_out)):
        raise FileExistsError("refusing to overwrite attribution evidence")
    started = time.time()

    drift_analysis = json.loads(DRIFT_ANALYSIS.read_text(encoding="utf-8"))
    if drift_analysis.get("status") != "PASS":
        raise RuntimeError("CPU-exact replay is not passing")
    if sha256_file(DRIFT_RAW) != drift_analysis["raw_sha256"]:
        raise RuntimeError("CPU-exact replay hash mismatch")

    drift_rows = {}
    with gzip.open(DRIFT_RAW, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["corpus"], int(row["session"]), int(row["hand"]), int(row["decision"]))
            if key in drift_rows:
                raise RuntimeError(f"duplicate replay key: {key}")
            drift_rows[key] = row

    input_hands = []
    rows = []
    teacher_items = []
    decision_rows_seen = 0
    for corpus, spec in CORPORA.items():
        record = json.loads((spec["root"] / "experiment.json").read_text(encoding="utf-8"))
        audit = json.loads((spec["root"] / "combined_audit.json").read_text(encoding="utf-8"))
        if record["status"] != "COMPLETED" or audit["status"] != "PASS":
            raise RuntimeError(f"unreviewed corpus: {corpus}")
        if audit["model_sha256"] != spec["policy_sha256"]:
            raise RuntimeError(f"corpus checkpoint mismatch: {corpus}")
        for session in range(1, 9):
            hand_path = spec["root"] / "sessions" / f"s{session:02d}" / "hands.jsonl"
            input_hands.append({"corpus": corpus, "session": session, "path": str(hand_path), "sha256": sha256_file(hand_path)})
            with hand_path.open("r", encoding="utf-8") as handle:
                for hand_index, line in enumerate(handle, 1):
                    hand = json.loads(line)
                    if hand["model_sha256"] != spec["policy_sha256"]:
                        raise RuntimeError("hand model SHA mismatch")
                    replay = [drift_rows[(corpus, session, hand_index, i)] for i in range(len(hand["decisions"]))]
                    decision_rows_seen += len(replay)
                    board_len = len(hand["terminal_response"].get("board", []))
                    fallback_street = {0: 0, 3: 1, 4: 2, 5: 3}[board_len]
                    final_replay = replay[-1] if replay else None
                    pair = spec["policy_pair"]
                    margins = [float(row[f"{pair}_right_margin"]) for row in replay]
                    max_exposure = max((float(row["exposure_bb"]) for row in replay), default=0.0)
                    feature = {
                        "corpus": corpus,
                        "session": session,
                        "hand": hand_index,
                        "split": "discovery" if session <= 4 else "confirmation",
                        "winnings_bb": float(hand["winnings_bb"]),
                        "seat": "bb" if int(hand["terminal_response"]["client_pos"]) == 0 else "sb",
                        "terminal_kind": hand["terminal_validation"]["terminal_kind"],
                        "max_street": street_name(max((int(row["street"]) for row in replay), default=fallback_street)),
                        "preflop_topology": preflop_topology(hand["terminal_response"]["action"]),
                        "max_exposure_bucket": bucket(max_exposure, (5, 20, 50, float("inf")), ("lt5", "5to20", "20to50", "ge50")),
                        "final_street": street_name(int(final_replay["street"])) if final_replay else "no_decision",
                        "final_action_class": selected_action_class(hand["decisions"][-1]) if replay else "no_decision",
                        "final_pot_bucket": final_replay["pot_bucket"] if final_replay else "no_decision",
                        "min_margin_bucket": margin_bucket(min(margins) if margins else None),
                        "final_margin_bucket": margin_bucket(margins[-1] if margins else None),
                        "teacher_admissible": False,
                        "onpolicy_vs_teacher_consensus": False,
                    }
                    feature["class_keys"] = class_keys(feature)
                    rows.append(feature)
                    if replay:
                        response = hand["decisions"][-1]["response"]
                        teacher_items.append({
                            "feature": feature,
                            "response": response,
                            "standard10_action": final_replay[f"{pair}_left_action"],
                            "standard10_margin": float(final_replay[f"{pair}_left_margin"]),
                            "onpolicy_action": final_replay[f"{pair}_right_action"],
                        })

    if len(rows) != 40_000 or decision_rows_seen != len(drift_rows):
        raise RuntimeError(f"input accounting mismatch: hands={len(rows)} decisions={decision_rows_seen}/{len(drift_rows)}")

    torch.set_num_threads(8)
    cfr4 = load_policy(CFR4_PATH, "cpu")
    if cfr4.sha256 != CFR4_SHA256:
        raise RuntimeError("CFR4 checkpoint hash mismatch")
    for start in range(0, len(teacher_items), BATCH_SIZE):
        batch = teacher_items[start : start + BATCH_SIZE]
        states = [from_external(item["response"]["action"], item["response"]["hole_cards"], item["response"].get("board", []), item["response"]["client_pos"]) for item in batch]
        observations = [legacy_observation_from_state(state, include_position=False, restrict_to_v6_action_table=True)[0] for state in states]
        probabilities = infer(cfr4.model, observations)
        for item, state, raw in zip(batch, states, probabilities):
            _, legacy_table = legacy_observation_from_state(state, include_position=False, restrict_to_v6_action_table=True)
            physical = collapse_to_physical(raw, legacy_table, state)
            action = legacy_table[int(np.argmax(raw))]
            cfr_margin = probability_margin(physical)
            consensus = item["standard10_action"] == action
            admissible = consensus and item["standard10_margin"] >= MIN_TEACHER_MARGIN and cfr_margin >= MIN_TEACHER_MARGIN
            item["feature"].update({
                "cfr4_action": action,
                "cfr4_margin": cfr_margin,
                "teacher_consensus": consensus,
                "teacher_admissible": admissible,
                "onpolicy_vs_teacher_consensus": admissible and item["onpolicy_action"] != action,
            })

    with gzip.open(raw_out, "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")

    by_corpus_split = defaultdict(list)
    for row in rows:
        by_corpus_split[(row["corpus"], row["split"])].append(row)
    all_keys = sorted({key for row in rows if row["split"] == "discovery" for key in row["class_keys"]})
    discovery = {}
    eligible = []
    for key in all_keys:
        per_corpus = {corpus: outcome_metrics(by_corpus_split[(corpus, "discovery")], key) for corpus in CORPORA}
        discovery[key] = per_corpus
        if all(metric.get("hands", 0) >= MIN_CLASS_HANDS and metric.get("class_minus_complement_bb100", 0) < 0 for metric in per_corpus.values()):
            score = sum(metric["negative_excess_bb"] for metric in per_corpus.values())
            eligible.append((score, key))
    nominees = [key for _, key in sorted(eligible, reverse=True)[:MAX_NOMINEES]]

    confirmation = {}
    confirmed = []
    for key in nominees:
        per_corpus = {corpus: outcome_metrics(by_corpus_split[(corpus, "confirmation")], key) for corpus in CORPORA}
        passed = all(
            metric.get("hands", 0) >= MIN_CLASS_HANDS
            and metric.get("class_minus_complement_bb100", 0) <= MIN_CONFIRM_DELTA_BB100
            and metric.get("negative_sessions", 0) >= 3
            for metric in per_corpus.values()
        )
        confirmation[key] = {"corpora": per_corpus, "passed": passed}
        if passed:
            confirmed.append(key)

    proxies = {}
    supported = []
    for key in confirmed:
        per_corpus = {corpus: proxy_metrics(by_corpus_split[(corpus, "confirmation")], key) for corpus in CORPORA}
        passed = all(
            metric.get("rows", 0) >= MIN_PROXY_ROWS
            and metric.get("complement_rows", 0) >= MIN_PROXY_ROWS
            and metric.get("disagreement_uplift", -1.0) >= MIN_PROXY_UPLIFT
            for metric in per_corpus.values()
        )
        proxies[key] = {"corpora": per_corpus, "passed": passed}
        if passed:
            supported.append(key)

    tails = {corpus: {split: tail_summary(by_corpus_split[(corpus, split)]) for split in ("discovery", "confirmation")} for corpus in CORPORA}
    manifest = {
        "schema": "cardpilot.integrated_slumbot_loss_attribution_inputs.v1",
        "outcome_labels_are_descriptive_not_action_targets": True,
        "drift_raw": {"path": str(DRIFT_RAW), "sha256": sha256_file(DRIFT_RAW)},
        "drift_analysis": {"path": str(DRIFT_ANALYSIS), "sha256": sha256_file(DRIFT_ANALYSIS)},
        "hands": input_hands,
        "models": {
            "standard10": {"sha256": STANDARD10_SHA256},
            "cfr4": {"path": str(CFR4_PATH), "sha256": CFR4_SHA256},
            **{corpus: {"sha256": spec["policy_sha256"]} for corpus, spec in CORPORA.items()},
        },
    }
    manifest_out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {
        "schema": "cardpilot.integrated_slumbot_loss_attribution.v1",
        "status": "COMPLETED",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "design": {
            "discovery_sessions": [1, 2, 3, 4],
            "confirmation_sessions": [5, 6, 7, 8],
            "min_class_hands": MIN_CLASS_HANDS,
            "min_confirm_delta_bb100": MIN_CONFIRM_DELTA_BB100,
            "min_negative_confirmation_sessions": 3,
            "min_proxy_rows": MIN_PROXY_ROWS,
            "min_proxy_uplift": MIN_PROXY_UPLIFT,
            "min_teacher_margin": MIN_TEACHER_MARGIN,
            "max_nominees": MAX_NOMINEES,
        },
        "accounting": {
            "slumbot_hands": 0,
            "reused_slumbot_hands": len(rows),
            "reused_decision_states": decision_rows_seen,
            "cfr4_final_state_queries": len(teacher_items),
        },
        "integrity": {
            "hand_count_exact": len(rows) == 40_000,
            "decision_replay_count_exact": decision_rows_seen == 124_121,
            "raw_attribution_rows_exact": len(rows) == 40_000,
            "frozen_input_hashes_verified": True,
            "discovery_confirmation_session_disjoint": True,
        },
        "tails_descriptive_only": tails,
        "discovery": discovery,
        "nominees": nominees,
        "confirmation": confirmation,
        "confirmed_classes": confirmed,
        "solver_teacher_proxies": proxies,
        "supported_classes": supported,
        "decision": "ADMIT_GENERAL_STATE_CLASS_INTERVENTION" if supported else "NO_REPLICATED_CAUSAL_PROXY",
        "interpretation": (
            "Supported classes may motivate only general resampling, value calibration, or solver supervision; "
            "the observational outcomes and teacher actions are not Slumbot action labels or causal Q estimates."
        ),
        "raw_sha256": sha256_file(raw_out),
        "input_manifest_sha256": sha256_file(manifest_out),
        "wall_time_seconds": time.time() - started,
    }
    if not all(analysis["integrity"].values()):
        raise RuntimeError("attribution integrity gate failed")
    analysis_out.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "decision": analysis["decision"],
        "nominees": len(nominees),
        "confirmed_classes": confirmed,
        "supported_classes": supported,
        "wall_time_seconds": analysis["wall_time_seconds"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
