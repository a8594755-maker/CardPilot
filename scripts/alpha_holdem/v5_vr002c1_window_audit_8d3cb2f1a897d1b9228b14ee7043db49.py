#!/usr/bin/env python3
"""Independent auditor for the sole registered VR002C1 first-crossing Stage-A endpoint."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch


REPO = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "8d3cb2f1a897d1b9228b14ee7043db49"
IDENTITY = "8d3cb2f1a897d1b9228b14ee7043db496c7a319c4af7318aae4e0103ac534a4d"
PREREG_SHA256 = "a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e"
SOURCE = REPO / (
    "models/alpha_holdem_v5_hybrid/"
    "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715/"
    "h11_control_endpoint.pt"
)
SOURCE_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_HANDS = 576_021_901
SOURCE_ITERATION = 35_051
TARGET_HANDS = 581_021_901
MIN_NEW_HANDS = 5_000_000
MAX_NEW_HANDS = 5_050_000
MAX_RUNTIME_SECONDS = 21_600.0
POOL_IDS = [109, 115, 120, 129, 103]
POOL_HASHES = {
    "109": "aee38c625bf0faada6b163f23aeb4cc539d67f7cbe46dc234aa4f46b18960953",
    "115": "ed92c7724486e446c13e5d4c623327d4288c68652964b7b4f35c0d2a7630d0c1",
    "120": "86c3d7bacce72dd5749c21deaad3865c7313c9f118860cbc7e9b8b378070494e",
    "129": "9d008780ac3cd259579131532df9775b53b4e3c95c7b0f12f2aac70bc915b255",
    "103": "cdec36f3deb27470a61c586b6491cd5de44aa3a99194b026a6e491a3121335a1",
}
Q_INIT_SEED = 2_026_072_302
Q_MINIBATCH_SEED = 2_026_072_303
CORE = REPO / f"scripts/alpha_holdem/v5_vr002c1_qboost_core_{TOKEN}.py"
TRAINER = REPO / f"scripts/alpha_holdem/v5_vr002c1_train_{TOKEN}.py"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def finite_tree(value: Any) -> bool:
    if torch.is_tensor(value):
        return bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tree(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(item) for item in value)
    return not isinstance(value, float) or math.isfinite(value)


def canonical_record_hash(row: dict[str, Any]) -> str:
    payload = dict(row)
    payload.pop("record_sha256", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def valid_hash_chain(rows: list[dict[str, Any]]) -> bool:
    previous = "0" * 64
    for row in rows:
        if row.get("previous_record_sha256") != previous:
            return False
        if row.get("record_sha256") != canonical_record_hash(row):
            return False
        previous = row["record_sha256"]
    return True


def valid_records(rows: list[dict[str, Any]]) -> bool:
    return all(row.get("record_sha256") == canonical_record_hash(row) for row in rows)


def valid_trace_chain(rows: list[dict[str, Any]]) -> bool:
    previous = "0" * 64
    for row in rows:
        if row.get("previous_record_sha256") != previous:
            return False
        if row.get("record_sha256") != canonical_record_hash(row):
            return False
        previous = row["record_sha256"]
    return True


def median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def tensor_tree_hash(value: Any) -> str:
    digest = hashlib.sha256()

    def update(item: Any, name: str) -> None:
        digest.update(name.encode("utf-8"))
        if torch.is_tensor(item):
            tensor = item.detach().cpu().contiguous()
            digest.update(str(tensor.dtype).encode("ascii"))
            digest.update(json.dumps(list(tensor.shape)).encode("ascii"))
            # numpy().tobytes() is deterministic for contiguous CPU tensors and,
            # unlike view(torch.uint8), is valid for scalar BN/Adam state tensors.
            digest.update(tensor.numpy().tobytes(order="C"))
        elif isinstance(item, dict):
            for key in sorted(item, key=lambda key: str(key)):
                update(item[key], f"{name}/{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                update(child, f"{name}/{index}")
        else:
            digest.update(repr(item).encode("utf-8"))

    update(value, "root")
    return digest.hexdigest()


def tensor_tree_hash_scalar_contract() -> bool:
    original = {
        "float_step": torch.tensor(7.0, dtype=torch.float32),
        "nested": [
            torch.tensor(11, dtype=torch.int64),
            {"vector": torch.tensor([1.0, 2.0], dtype=torch.float64)},
        ],
    }
    identical = {
        "float_step": original["float_step"].clone(),
        "nested": [
            original["nested"][0].clone(),
            {"vector": original["nested"][1]["vector"].clone()},
        ],
    }
    changed = {
        "float_step": torch.tensor(8.0, dtype=torch.float32),
        "nested": identical["nested"],
    }
    baseline = tensor_tree_hash(original)
    return baseline == tensor_tree_hash(identical) and baseline != tensor_tree_hash(changed)


def value_head_optimizer_state(checkpoint: dict[str, Any]) -> dict[str, Any]:
    model = checkpoint["model"]
    optimizer = checkpoint["optimizer"]
    parameter_names = list(model.keys())
    # State-dict order follows model.parameters(); buffers are filtered by optimizer count.
    parameter_names = [
        name
        for name in parameter_names
        if not any(part in name for part in ("running_mean", "running_var", "num_batches_tracked"))
    ]
    optimizer_ids = [
        item for group in optimizer["param_groups"] for item in group["params"]
    ]
    if len(parameter_names) != len(optimizer_ids):
        raise RuntimeError("cannot independently map actor optimizer IDs to model parameters")
    name_to_id = dict(zip(parameter_names, optimizer_ids, strict=True))
    return {
        name: optimizer["state"].get(name_to_id[name], {})
        for name in parameter_names
        if name.startswith("value_head.")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_dir = Path(args.run_dir).resolve()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite audit: {out}")

    paths = {
        "checkpoint": run_dir / "latest.pt",
        "metrics": run_dir / "vr002_metrics.jsonl",
        "trace_manifest": run_dir / "vr002_trace_manifest.jsonl",
        "provenance": run_dir / "opponent_assignment_provenance.jsonl",
        "run_manifest": run_dir / "run_manifest.json",
    }
    checks: dict[str, bool] = {
        f"{name}_exists": path.is_file() for name, path in paths.items()
    }
    checks["tensor_tree_hash_nested_scalar_contract"] = tensor_tree_hash_scalar_contract()
    if not all(checks.values()):
        missing = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"incomplete VR002C1 endpoint bundle: {missing}")

    stable_hashes: dict[str, str] = {}
    for name, path in paths.items():
        first = sha256_path(path)
        second = sha256_path(path)
        checks[f"{name}_stable_read"] = first == second
        stable_hashes[name] = first

    checkpoint = torch.load(paths["checkpoint"], map_location="cpu", weights_only=False)
    source = torch.load(SOURCE, map_location="cpu", weights_only=False)
    metrics = jsonl(paths["metrics"])
    traces = jsonl(paths["trace_manifest"])
    provenance = jsonl(paths["provenance"])
    manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    contract = checkpoint.get("vr002") or {}

    checks["identity_exact"] = (
        contract.get("identity_sha256") == IDENTITY
        and contract.get("identity") == IDENTITY
        and contract.get("token") == TOKEN
        and contract.get("preregistration_sha256") == PREREG_SHA256
    )
    checks["source_exact"] = (
        sha256_path(SOURCE) == SOURCE_SHA256
        and contract.get("source_checkpoint_sha256") == SOURCE_SHA256
        and int(contract.get("source_total_hands", -1)) == SOURCE_HANDS
    )
    checks["q_contract_exact"] = (
        int(contract.get("central_serialized_floats", -1)) == 895
        and int(contract.get("central_learned_floats", -1)) == 886
        and int(contract.get("legal_sidecar_floats", -1)) == 9
        and int(contract.get("focal_views_per_action", -1)) == 2
        and int(contract.get("q_init_seed", -1)) == Q_INIT_SEED
        and int(contract.get("q_minibatch_seed", -1)) == Q_MINIBATCH_SEED
        and float(contract.get("gamma", -1.0)) == 0.999
        and float(contract.get("lambda", -1.0)) == 0.95
        and int(contract.get("q_epochs", -1)) == 4
        and int(contract.get("q_physical_rows_per_minibatch", -1)) == 512
        and contract.get("historical_replay") is False
        and contract.get("reward_contract")
        == "EXACT_INHERITED_ALLIN_EV_ADJUSTED_ZERO_SUM_TERMINAL_VECTOR"
        and contract.get("actor_before_critic") is True
    )
    checks["pool_contract_exact"] = (
        contract.get("pool_member_ids") == POOL_IDS
        and contract.get("opponent_assignment") == "LG003_ASSIGNMENT_V1_control_uniform"
        and contract.get("pool_member_state_dict_sha256") == POOL_HASHES
        and contract.get("assignment_rule") == "LG003_ASSIGNMENT_V1"
        and contract.get("assignment_token") == "fbd630ab6a689913afc1cee8a63066dd"
        and int(contract.get("assignment_seed", -1)) == 2_026_072_301
    )
    checks["separate_q_namespaces_present"] = all(
        key in checkpoint
        for key in (
            "vr002_q_model",
            "vr002_q_optimizer",
            "vr002_q_minibatch_generator_state",
        )
    ) and all(
        key not in checkpoint
        for key in ("q_model", "q_optimizer", "q_minibatch_generator_state")
    )
    checks["all_checkpoint_tensors_finite"] = (
        finite_tree(checkpoint.get("model"))
        and finite_tree(checkpoint.get("optimizer"))
        and finite_tree(checkpoint.get("vr002_q_model"))
        and finite_tree(checkpoint.get("vr002_q_optimizer"))
    )
    checks["candidate_source_hashes_bound"] = (
        contract.get("core_sha256") == sha256_path(CORE)
        and contract.get("trainer_sha256") == sha256_path(TRAINER)
    )
    endpoint_snapshots = checkpoint.get("pool_snapshots") or []
    source_snapshots = source.get("pool_snapshots") or []
    checks["pool_order_and_state_bit_identical"] = (
        [int(row.get("id", -1)) for row in endpoint_snapshots] == POOL_IDS
        and [int(row.get("id", -1)) for row in source_snapshots] == POOL_IDS
        and tensor_tree_hash(endpoint_snapshots) == tensor_tree_hash(source_snapshots)
    )
    source_value = {
        name: tensor
        for name, tensor in source["model"].items()
        if name.startswith("value_head.")
    }
    endpoint_value = {
        name: tensor
        for name, tensor in checkpoint["model"].items()
        if name.startswith("value_head.")
    }
    checks["value_head_parameters_bit_identical"] = (
        tensor_tree_hash(source_value) == tensor_tree_hash(endpoint_value)
    )
    checks["value_head_optimizer_slots_bit_identical"] = (
        tensor_tree_hash(value_head_optimizer_state(source))
        == tensor_tree_hash(value_head_optimizer_state(checkpoint))
    )

    sys.path.insert(0, str(REPO / "scripts" / "alpha_holdem"))
    from network_hybrid_h1 import AlphaHoldemNet  # pylint: disable=import-outside-toplevel

    official_actor = AlphaHoldemNet(critic_contract="critic_v1")
    with torch.no_grad():
        official_actor(
            torch.zeros(1, 6, 4, 13),
            torch.zeros(1, 25, 4, 5),
            torch.zeros(1, 2),
        )
    strict_result = official_actor.load_state_dict(checkpoint["model"], strict=True)
    checks["official_actor_strict_load"] = (
        not strict_result.missing_keys and not strict_result.unexpected_keys
    )
    sys.path.insert(0, str(REPO / "scripts"))
    qcore = importlib.import_module(
        f"alpha_holdem.v5_vr002c1_qboost_core_{TOKEN}"
    )
    endpoint_q = qcore.make_q_critic_isolated(seed=Q_INIT_SEED)
    q_load = endpoint_q.load_state_dict(checkpoint["vr002_q_model"], strict=True)
    endpoint_q_optimizer = qcore.initialize_q_optimizer(endpoint_q)
    endpoint_q_optimizer.load_state_dict(checkpoint["vr002_q_optimizer"])
    endpoint_q_generator = qcore.make_q_minibatch_generator(
        checkpoint["vr002_q_minibatch_generator_state"]
    )
    qcore.assert_models_storage_disjoint(official_actor, endpoint_q)
    checks["q_model_optimizer_generator_strict_load"] = (
        not q_load.missing_keys
        and not q_load.unexpected_keys
        and finite_tree(endpoint_q.state_dict())
        and finite_tree(endpoint_q_optimizer.state_dict())
        and torch.equal(
            endpoint_q_generator.get_state(),
            checkpoint["vr002_q_minibatch_generator_state"].detach().cpu(),
        )
    )

    checks["metrics_nonempty"] = bool(metrics)
    checks["trace_manifest_nonempty"] = bool(traces)
    checks["raw_json_evidence_finite"] = finite_tree(metrics) and finite_tree(traces)
    checks["metrics_iterations_contiguous"] = [
        int(row.get("iteration", -1)) for row in metrics
    ] == list(range(SOURCE_ITERATION + 1, int(checkpoint.get("iteration", -1)) + 1))
    totals = [int(row.get("total_hands", -1)) for row in metrics]
    crossing = [index for index, total in enumerate(totals) if total >= TARGET_HANDS]
    checks["sole_first_crossing_is_endpoint"] = crossing == [len(totals) - 1]
    endpoint_hands = int(checkpoint.get("total_hands", -1))
    new_hands = endpoint_hands - SOURCE_HANDS
    checks["checkpoint_matches_first_crossing"] = (
        endpoint_hands == totals[-1]
        and MIN_NEW_HANDS <= new_hands <= MAX_NEW_HANDS
    )
    checks["metric_record_hashes"] = valid_records(metrics)
    checks["metric_identity_exact"] = all(
        row.get("identity") == IDENTITY for row in metrics
    )
    checks["actor_generation_exact"] = all(
        int(row.get("actor_generation", -1)) == SOURCE_ITERATION + index + 1
        and int(row.get("actor_generation_reference", -1)) == SOURCE_ITERATION + index
        and int(row.get("actor_generation_after", -1)) == SOURCE_ITERATION + index + 1
        and int(row.get("assignment_version", -1)) == index + 1
        for index, row in enumerate(metrics)
    )
    required_metric_bools = (
        "bijection_pass",
        "chronology_coverage_pass",
        "math_contract_pass",
        "reward_contract_pass",
        "legal_policy_contract_pass",
        "actor_q_isolation_pass",
        "leakage_contract_pass",
        "finite_pass",
        "value_head_frozen_pass",
        "q_dispersion_actor_rows_only",
    )
    checks["all_per_update_validity_gates"] = all(
        all(row.get(name) is True for name in required_metric_bools)
        and int(row.get("q_focal_rows", -1)) == 2 * int(row.get("physical_rows", -2))
        and 1 <= int(row.get("actor_epochs_completed", -1)) <= 4
        and float(row.get("q_parameter_delta", 0.0)) > 0.0
        for row in metrics
    )
    checks["paired_mechanism_evidence_exact"] = all(
        int(row.get("paired_actor_row_count", -1)) == int(row.get("actor_rows", -2))
        and int(row.get("paired_actor_row_count", 0)) > 0
        and int(row.get("q_dispersion_eligible_actor_row_count", 0)) > 0
        and float(row.get("legacy_gae_population_variance", 0.0)) > 1e-12
        and math.isclose(
            float(row.get("paired_variance_ratio", float("nan"))),
            float(row.get("qboost_advantage_population_variance", float("nan")))
            / float(row.get("legacy_gae_population_variance", float("nan"))),
            rel_tol=1e-12,
            abs_tol=1e-15,
        )
        and math.isclose(
            float(row.get("qboost_advantage_raw_std", float("nan"))) ** 2,
            float(row.get("qboost_advantage_population_variance", float("nan"))),
            rel_tol=1e-10,
            abs_tol=1e-12,
        )
        and math.isclose(
            float(row.get("legacy_gae_raw_std", float("nan"))) ** 2,
            float(row.get("legacy_gae_population_variance", float("nan"))),
            rel_tol=1e-10,
            abs_tol=1e-12,
        )
        and -1.0 <= float(row.get("paired_raw_correlation", float("nan"))) <= 1.0
        and all(
            math.isfinite(float(row.get(name, float("nan"))))
            for name in (
                "qboost_advantage_raw_mean",
                "qboost_advantage_raw_std",
                "legacy_gae_raw_mean",
                "legacy_gae_raw_std",
                "paired_raw_correlation",
                "q_dispersion",
            )
        )
        and isinstance(row.get("paired_actor_uid_sha256"), str)
        and len(row["paired_actor_uid_sha256"]) == 64
        and all(char in "0123456789abcdef" for char in row["paired_actor_uid_sha256"])
        for row in metrics
    )
    checks["inherited_absolute_progress_lr_exact"] = all(
        math.isclose(
            float(row.get("actor_learning_rate", float("nan"))),
            0.0003
            * (
                1.0
                if float(row["total_hands"]) / TARGET_HANDS < 0.5
                else 1.0
                - ((float(row["total_hands"]) / TARGET_HANDS - 0.5) / 0.5)
                * (1.0 - 1.0 / 3.0)
            ),
            rel_tol=0.0,
            abs_tol=1e-15,
        )
        for row in metrics
    )

    checks["trace_hash_chain"] = valid_trace_chain(traces)
    checks["trace_iterations_match_metrics"] = [
        int(row.get("iteration", -1)) for row in traces
    ] == [int(row.get("iteration", -1)) for row in metrics]
    checks["trace_schema_and_summary_flags"] = all(
        row.get("schema_version") == "v5.vr002.trace_aggregate.v1"
        and row.get("step_contiguous_all") is True
        and row.get("successor_links_all") is True
        and row.get("two_focal_views_per_row") is True
        and row.get("terminal_reward_zero_sum_all") is True
        and row.get("actor_bijection_all") is True
        for row in traces
    )
    checks["trace_count_identities"] = all(
        int(row.get("q_focal_rows", -1)) == 2 * int(row.get("physical_rows", -2))
        and int(row.get("terminal_rows", -1)) == int(row.get("complete_hands", -2))
        and int(row.get("complete_hands", -1))
        == int(row.get("admitted_hands", -2)) + int(row.get("mixed_or_stale_hands", -3))
        and len(row.get("rejected_hand_uids", []))
        == int(row.get("mixed_or_stale_hands", -1))
        for row in traces
    )
    checks["trace_metric_cumulative_counts"] = (
        sum(int(row["complete_hands"]) for row in traces) == int(metrics[-1]["complete_hands"])
        and sum(int(row["admitted_hands"]) for row in traces) == int(metrics[-1]["admitted_hands"])
        and sum(int(row["mixed_or_stale_hands"]) for row in traces)
        == int(metrics[-1]["mixed_or_stale_hands"])
        and all(
            int(trace["complete_hands"]) == int(metric["rollout_complete_hands"])
            and int(trace["admitted_hands"]) == int(metric["rollout_admitted_hands"])
            and int(trace["mixed_or_stale_hands"])
            == int(metric["rollout_mixed_or_stale_hands"])
            and trace.get("cumulative_hand_sha256") == metric.get("trace_hand_chain_sha256")
            and int(trace.get("assignment_version_collected", -1))
            == int(metric.get("assignment_version", -2))
            and int(trace.get("stale_assignment_hands", -1))
            == int(metric.get("rollout_stale_assignment_hands", -2))
            for trace, metric in zip(traces, metrics)
        )
    )
    exp003_keys = set().union(
        *(set(row.get("exp003_metrics", {})) for row in metrics)
    )
    cumulative_exp003 = {
        key: sum(int(row.get("exp003_metrics", {}).get(key, 0)) for row in metrics)
        for key in exp003_keys
    }
    checks["inherited_allin_ev_evidence_exact"] = (
        all(
            metric.get("exp003_metrics") == trace.get("exp003_metrics")
            for metric, trace in zip(metrics, traces)
        )
        and cumulative_exp003 == manifest.get("exp003_metrics")
    )

    def sample_ok(
        hand: dict[str, Any],
        admitted: bool,
        reference_generation: int,
        reference_assignment_version: int,
    ) -> bool:
        rows = hand.get("rows") or []
        if not rows or hand.get("admitted") is not admitted:
            return False
        if (
            not isinstance(hand.get("hand_uid"), str)
            or not isinstance(hand.get("hand_digest"), str)
            or len(hand["hand_digest"]) != 64
            or not all(char in "0123456789abcdef" for char in hand["hand_digest"])
        ):
            return False
        if [int(row.get("step_index", -1)) for row in rows] != list(range(len(rows))):
            return False
        if len({row.get("uid") for row in rows}) != len(rows):
            return False
        hero_generations: list[int] = []
        for index, row in enumerate(rows):
            if row.get("uid") != f"{hand['hand_uid']}|{index}":
                return False
            payload = dict(row)
            record_hash = payload.pop("row_payload_sha256", None)
            if hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest() != record_hash:
                return False
            if not all(
                isinstance(row.get(name), str)
                and len(row[name]) == 64
                and all(char in "0123456789abcdef" for char in row[name])
                for name in (
                    "state_payload_sha256",
                    "card6_sha256",
                    "action25_sha256",
                    "extra2_sha256",
                    "other_hole_public_sha256",
                )
            ):
                return False
            legal = np.asarray(row.get("legal9"), dtype=np.float64)
            pi = np.asarray(row.get("pi_ref9"), dtype=np.float64)
            action = int(row.get("selected_action", -1))
            if (
                legal.shape != (9,)
                or pi.shape != (9,)
                or not np.isin(legal, (0.0, 1.0)).all()
                or action < 0
                or action >= 9
                or legal[action] != 1.0
                or not np.isfinite(pi).all()
                or (pi < 0).any()
                or not np.all(pi[legal == 0] == 0)
                or not math.isclose(float(pi.sum()), 1.0, rel_tol=0.0, abs_tol=2e-6)
                or pi[action] <= 0
                or not math.isclose(
                    math.log(float(pi[action])),
                    float(row.get("old_log_probability", float("nan"))),
                    rel_tol=0.0,
                    abs_tol=2e-6,
                )
            ):
                return False
            if int(row.get("active_absolute_seat", -1)) not in (0, 1):
                return False
            model_id = int(row.get("request_model_id", -999))
            local_index = int(row.get("request_model_local_index", -999))
            if model_id == -1:
                if local_index != -1:
                    return False
                hero_generations.append(int(row.get("actor_generation", -1)))
            else:
                if (
                    model_id not in POOL_IDS
                    or local_index < 0
                    or local_index >= len(POOL_IDS)
                    or POOL_IDS[local_index] != model_id
                    or int(row.get("actor_generation", 0)) != -1
                ):
                    return False
            if not isinstance(row.get("assignment_version"), int):
                return False
            expected_next = None if index == len(rows) - 1 else rows[index + 1].get("uid")
            if row.get("next_uid") != expected_next or bool(row.get("done")) != (index == len(rows) - 1):
                return False
            reward = np.asarray(row.get("training_reward"), dtype=np.float64)
            if reward.shape != (2,) or not np.isfinite(reward).all():
                return False
            if index < len(rows) - 1 and not np.array_equal(reward, np.zeros(2)):
                return False
            if index == len(rows) - 1 and not math.isclose(float(reward.sum()), 0.0, abs_tol=1e-9):
                return False
        generation_pure = bool(hero_generations) and set(hero_generations) == {reference_generation}
        assignment_pure = {
            int(row["assignment_version"]) for row in rows
        } == {reference_assignment_version}
        pure = generation_pure and assignment_pure
        return pure if admitted else not pure

    checks["sampled_raw_hand_evidence"] = all(
        len(row.get("sampled_raw_admitted_hands", [])) == min(4, int(row["admitted_hands"]))
        and len(row.get("sampled_raw_rejected_hands", []))
        == min(4, int(row["mixed_or_stale_hands"]))
        and all(
            sample_ok(
                hand,
                True,
                int(row["actor_generation_collected"]),
                int(row["assignment_version_collected"]),
            )
            for hand in row.get("sampled_raw_admitted_hands", [])
        )
        and all(
            sample_ok(
                hand,
                False,
                int(row["actor_generation_collected"]),
                int(row["assignment_version_collected"]),
            )
            for hand in row.get("sampled_raw_rejected_hands", [])
        )
        and len(set(row.get("rejected_hand_uids", [])))
        == len(row.get("rejected_hand_uids", []))
        and {
            hand["hand_uid"] for hand in row.get("sampled_raw_rejected_hands", [])
        }.issubset(set(row.get("rejected_hand_uids", [])))
        for row in traces
    )

    checks["provenance_hash_chain"] = valid_hash_chain(provenance)
    checks["provenance_iterations_match"] = [
        int(row.get("applies_to_iteration", -1)) for row in provenance
    ] == [int(row.get("iteration", -1)) for row in metrics]
    def assignment_ok(row: dict[str, Any]) -> bool:
        absolute_iteration = int(row.get("applies_to_iteration", -1))
        payload = (
            "LG003_ASSIGNMENT_V1|fbd630ab6a689913afc1cee8a63066dd|"
            f"2026072301|{absolute_iteration}"
        )
        expected_u64 = int.from_bytes(
            hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big"
        )
        unit = expected_u64 / float(1 << 64)
        expected_member = None
        expected_local = -1
        if unit >= 0.2:
            conditional = (unit - 0.2) / 0.8
            ordered_ids = [103, 109, 115, 120, 129]
            expected_member = ordered_ids[min(int(conditional / 0.2), 4)]
            expected_local = POOL_IDS.index(expected_member)
        assignment = row.get("assignment", {})
        return (
            assignment.get("assignment_rule") == "LG003_ASSIGNMENT_V1"
            and int(assignment.get("assignment_seed", -1)) == 2_026_072_301
            and assignment.get("arm") == "control_uniform"
            and assignment.get("conditional_weights_by_member_id")
            == {"103": 0.2, "109": 0.2, "115": 0.2, "120": 0.2, "129": 0.2}
            and int(assignment.get("u64", -1)) == expected_u64
            and assignment.get("selected_member_id") == expected_member
            and int(assignment.get("selected_local_index", -2)) == expected_local
            and int(row.get("generation", -1)) == absolute_iteration - 1
            and int(row.get("assignment_version", -1))
            == absolute_iteration - SOURCE_ITERATION
        )

    checks["provenance_uniform_exact"] = all(assignment_ok(row) for row in provenance)

    ratios = [
        float(row["paired_variance_ratio"]) for row in metrics
    ]
    dispersions = [
        float(row["q_dispersion"]) for row in metrics
    ]
    half = len(ratios) // 2
    dispersion_half = len(dispersions) // 2
    paired_median = median(ratios[half:])
    dispersion_median = median(dispersions[dispersion_half:])
    checks["mechanism_minimum_valid_updates"] = len(ratios) >= 20 and len(dispersions) == len(ratios)
    checks["paired_advantage_variance_gate"] = math.isfinite(paired_median) and paired_median < 1.0
    checks["nondegenerate_q_gate"] = (
        math.isfinite(dispersion_median) and dispersion_median > 0.000001
    )

    checks["manifest_finished_first_crossing"] = (
        manifest.get("status") == "finished"
        and manifest.get("termination_reason") == "first_crossing_target"
        and manifest.get("first_crossing") is True
        and manifest.get("no_unused_provenance_after_first_crossing") is True
        and manifest.get("identity") == IDENTITY
        and int(manifest.get("total_hands", -1)) == endpoint_hands
        and float(manifest.get("runtime_seconds", float("inf"))) <= MAX_RUNTIME_SECONDS
        and manifest.get("trainer_sha256") == sha256_path(TRAINER)
        and manifest.get("core_sha256") == sha256_path(CORE)
    )
    bound_artifacts = manifest.get("immutable_artifacts") or {}
    checks["manifest_binds_raw_artifacts"] = all(
        bound_artifacts.get(manifest_name, {}).get("sha256") == stable_hashes[path_name]
        for manifest_name, path_name in (
            ("checkpoint", "checkpoint"),
            ("metrics", "metrics"),
            ("trace", "trace_manifest"),
            ("provenance", "provenance"),
        )
    )
    manifest_payload = dict(manifest)
    manifest_record_hash = manifest_payload.pop("manifest_payload_sha256", None)
    checks["manifest_payload_hash"] = hashlib.sha256(
        json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == manifest_record_hash

    mechanism_pass = (
        checks["mechanism_minimum_valid_updates"]
        and checks["paired_advantage_variance_gate"]
        and checks["nondegenerate_q_gate"]
    )
    validity_names = [
        name
        for name in checks
        if name not in {"paired_advantage_variance_gate", "nondegenerate_q_gate"}
    ]
    validity_pass = all(checks[name] for name in validity_names)
    failed = [name for name, passed in checks.items() if not passed]
    status = (
        "VR002C1_VALID_ENDPOINT_MECHANISM_PASS_QUICK5K_MANDATORY"
        if validity_pass and mechanism_pass
        else "VR002C1_VALID_ENDPOINT_MECHANISM_FAIL_QUICK5K_MANDATORY"
        if validity_pass
        else "VR002C1_INVALID_ENDPOINT_ABORT_PRESERVE_NO_QUICK5K"
    )
    result = {
        "schema_version": "v5.vr002c1.stage_a.window_audit.v1",
        "status": status,
        "identity_sha256": IDENTITY,
        "preregistration_sha256": PREREG_SHA256,
        "validity_pass": validity_pass,
        "mechanism_pass": mechanism_pass,
        "checks": checks,
        "passed": len(checks) - len(failed),
        "total": len(checks),
        "failed_checks": failed,
        "measurements": {
            "iteration": int(checkpoint.get("iteration", -1)),
            "total_hands": endpoint_hands,
            "new_hands": new_hands,
            "updates": len(metrics),
            "valid_paired_updates": len(ratios),
            "final_half_paired_variance_ratio_median": paired_median,
            "final_half_q_dispersion_median": dispersion_median,
            "runtime_seconds": manifest.get("runtime_seconds"),
        },
        "artifacts": {
            name: {
                "path": str(path),
                "sha256": stable_hashes[name],
                "bytes": path.stat().st_size,
            }
            for name, path in paths.items()
        },
        "authority": {
            "quick5k_mandatory": validity_pass,
            "quick5k_authorized": validity_pass,
            "promotion_authority": "NONE_UNTIL_COMPLETE_AUDITED_QUICK5K",
            "strength_authority": "NONE",
        },
    }
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if validity_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
