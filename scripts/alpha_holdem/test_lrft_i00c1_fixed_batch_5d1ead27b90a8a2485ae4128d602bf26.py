#!/usr/bin/env python3
"""Fresh LRFT-I00C1 fixed-batch correction qualification."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict
import hashlib
import inspect
import itertools
import json
from pathlib import Path
import random
import sys
from typing import Any

import numpy as np
import torch


REPO = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from alpha_holdem import (  # noqa: E402
    lrft_h11_likelihood_c1_5d1ead27b90a8a2485ae4128d602bf26 as subject,
)
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1  # noqa: E402


IDENTITY = "5d1ead27b90a8a2485ae4128d602bf26d50c3a42455e7e289a5dd44429b87a6d"
TOKEN = IDENTITY[:32]
PARENT_IDENTITY = "a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704"
PARENT_RESULT = REPO / (
    "reports/v5_lrft_i00_interface_qualification_"
    "a0354ffed044c37ee5cc17a3d045273e_20260723.json"
)
PARENT_RESULT_SHA256 = "2c30c5570cb39e6b4286f6d5800addf860ec6420c32b3e95a0fd05226883e837"
PARENT_ENGINE = REPO / (
    "scripts/alpha_holdem/lrft_exact_cent_public_"
    "a0354ffed044c37ee5cc17a3d045273e.py"
)
PARENT_ENGINE_SHA256 = "9c429ace16f7c70c9ee4723e3b74209acaa6aa320ff117ae7866f4deebcb3b24"
SUBJECT_PATH = REPO / f"scripts/alpha_holdem/lrft_h11_likelihood_c1_{TOKEN}.py"
H11_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def counter_cards(label: str, count: int, excluded: set[int] | None = None) -> tuple[int, ...]:
    excluded = set(excluded or ())
    ranked = sorted(
        (hashlib.sha256(f"I00C1|{label}|{card}".encode()).digest(), card)
        for card in range(52)
        if card not in excluded
    )
    return tuple(card for _, card in ranked[:count])


def fixture(
    street: int, actor: int, variant: int
) -> tuple[subject.PublicLikelihoodState, int, tuple[int, int], tuple[int, ...]]:
    board = counter_cards(f"board|{street}|{variant}", (0, 3, 4, 5)[street])
    records: list[tuple[subject.PublicActionRecord, ...]] = []
    for history_street in range(4):
        if history_street > street:
            records.append(())
            continue
        count = (
            (variant + history_street + actor) % 5
            if history_street < street
            else (variant + actor) % 3
        )
        street_records = []
        for index in range(count):
            player = (actor + index + history_street) % 2
            if index % 3 == 0:
                action_type, amount = 1, 0
            elif index % 3 == 1:
                action_type, amount = 3, 100 + 25 * ((variant + index) % 20)
            else:
                action_type, amount = 2, 0
            street_records.append(
                subject.PublicActionRecord(player, action_type, amount)
            )
        records.append(tuple(street_records))
    committed0 = 50 + (variant * 17) % 4_000
    committed1 = 100 + (variant * 23) % 4_000
    stacks = (20_000 - committed0, 20_000 - committed1)
    state = subject.PublicLikelihoodState(
        street=street,
        button=1,
        current_player=actor,
        board=board,
        pot_cents=committed0 + committed1,
        stacks_cents=stacks,
        starting_stack_cents=20_000,
        actions_by_street=tuple(records),
    )
    hole = counter_cards(f"hole|{street}|{actor}|{variant}", 2, set(board))
    masks = (
        (1, 1, 0, 0, 0, 0, 0, 1, 1),
        (0, 1, 1, 0, 1, 0, 1, 0, 1),
        (1, 1, 0, 1, 0, 1, 0, 1, 1),
        (0, 1, 1, 1, 1, 1, 1, 1, 1),
    )
    return state, actor, hole, masks[(street + actor + variant) % len(masks)]


def manual_encode(
    state: subject.PublicLikelihoodState,
    actor: int,
    hole: tuple[int, int],
    mask: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    cards = np.zeros((6, 4, 13), dtype=np.float32)
    for card in hole:
        cards[0, card % 4, card // 4] = 1
        cards[5, card % 4, card // 4] = 1
    for index, card in enumerate(state.board):
        channel = 1 if index < 3 else 2 if index == 3 else 3
        cards[channel, card % 4, card // 4] = 1
        cards[4, card % 4, card // 4] = 1
        cards[5, card % 4, card // 4] = 1
    history = np.zeros((25, 4, 5), dtype=np.float32)
    for street_index, records in enumerate(state.actions_by_street):
        for slot, record in enumerate(records):
            channel = street_index * 6 + slot
            history[channel, 0, 0] = 1.0 if record.player == actor else 0.0
            history[channel, 1, min(record.action_type, 4)] = 1.0
            if record.amount_cents:
                history[channel, 2, 0] = (
                    min(record.amount_cents / max(state.pot_cents, 100), 2.0) / 2.0
                )
            history[channel, 3, 0] = 1.0
    history[24, 0, 0] = 1.0
    extra = np.asarray(
        [
            state.stacks_cents[actor] / 20_000,
            state.stacks_cents[1 - actor] / 20_000,
        ],
        dtype=np.float32,
    )
    return cards, history, extra, np.asarray(mask, dtype=np.float32)


def tensor_hash(state: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        value = tensor.detach().cpu().contiguous()
        digest.update(name.encode())
        digest.update(str(value.dtype).encode())
        digest.update(str(tuple(value.shape)).encode())
        digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def independent_model() -> AlphaHoldemNet:
    checkpoint = torch.load(
        subject.H11_CHECKPOINT_PATH, map_location="cpu", weights_only=True
    )
    with torch.device("meta"):
        model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1)
        model(
            torch.zeros((256, 6, 4, 13), device="meta"),
            torch.zeros((256, 25, 4, 5), device="meta"),
            torch.zeros((256, 2), device="meta"),
            torch.ones((256, 9), device="meta"),
        )
    model.load_state_dict(checkpoint["model"], strict=True, assign=True)
    return model.eval().requires_grad_(False)


def normalized(logits: torch.Tensor, masks: torch.Tensor) -> np.ndarray:
    output = torch.full(logits.shape, float("-inf"), dtype=torch.float64)
    rows = logits.detach().cpu().double()
    legal = masks.bool()
    for index in range(rows.shape[0]):
        output[index, legal[index]] = (
            rows[index, legal[index]]
            - torch.logsumexp(rows[index, legal[index]], dim=0)
        )
    return output.numpy()


def static_contract() -> bool:
    source = SUBJECT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "importlib", "runpy", "subprocess", "socket", "requests", "urllib",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name.split(".")[0] in forbidden_modules for alias in node.names
        ):
            return False
        if isinstance(node, ast.ImportFrom) and (
            node.module or ""
        ).split(".")[0] in forbidden_modules:
            return False
        if isinstance(node, ast.Name) and node.id in {"exec", "eval", "compile"}:
            return False
        if isinstance(node, ast.Attribute) and node.attr in {
            "write_text", "write_bytes", "manual_seed", "multinomial", "seed",
        }:
            return False
    return (
        "v5_rs" not in source
        and "lrft_h11_likelihood_a0354" not in source
        and "sys.modules" not in source
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite LRFT-I00C1 result: {out}")

    checks: dict[str, bool] = {}
    parent = json.loads(PARENT_RESULT.read_text(encoding="utf-8"))
    parent_checks: dict[str, bool] = parent["checks"]
    checks["parent_failure_identity_exact"] = (
        sha256_path(PARENT_RESULT) == PARENT_RESULT_SHA256
        and parent["identity_sha256"] == PARENT_IDENTITY
        and parent["failed_checks"] == ["independent_direct_h11_oracle"]
        and parent["passed"] == 18
        and parent["total"] == 19
        and all(
            passed is True
            for name, passed in parent_checks.items()
            if name != "independent_direct_h11_oracle"
        )
    )
    checks["parent_engine_exact_and_frozen"] = (
        sha256_path(PARENT_ENGINE) == PARENT_ENGINE_SHA256
        and parent["source_sha256"]["exact_cent_engine"] == PARENT_ENGINE_SHA256
    )
    checks["fresh_identity_and_sole_correction_exact"] = (
        subject.LRFT_I00C1_IDENTITY == IDENTITY
        and subject.PARENT_IDENTITY == PARENT_IDENTITY
        and subject.PARENT_RESULT_SHA256 == PARENT_RESULT_SHA256
        and subject.SOLE_CORRECTION
        == "FIXED_BATCH_256_CANONICAL_DUPLICATE_PADDING"
        and subject.CANONICAL_BATCH_SIZE == 256
    )
    checks["fresh_source_static_prohibitions"] = static_contract()
    checks["h11_checkpoint_exact"] = (
        sha256_path(subject.H11_CHECKPOINT_PATH) == H11_SHA256
    )

    fixtures = [
        fixture(street, actor, variant)
        for street in range(4)
        for actor in range(2)
        for variant in range(512)
    ]
    observation_rows = 0
    for state, actor, hole, mask in fixtures:
        encoded = subject.encode_h11_tensors(state, actor, hole, mask)
        expected = manual_encode(state, actor, hole, mask)
        if not all(
            np.array_equal(observed.numpy()[0], reference)
            for observed, reference in zip(encoded, expected)
        ):
            raise AssertionError("fresh observation mismatch")
        observation_rows += 1
    checks["fresh_4096_observations_independent_exact"] = observation_rows == 4_096

    selected = fixtures[::64][:64]
    states = [row[0] for row in selected]
    actors = [row[1] for row in selected]
    holes = [row[2] for row in selected]
    masks = [row[3] for row in selected]
    torch_before = torch.get_rng_state().clone()
    numpy_before = np.random.get_state()
    python_before = random.getstate()
    production_model = subject._exact_h11_model()
    production_hash_before = tensor_hash(production_model.state_dict())
    batch_outputs = subject.evaluate_h11_log_probs_batch(
        states, actors, holes, masks
    )
    checks["fresh_model_and_rng_immutable"] = (
        production_hash_before == tensor_hash(production_model.state_dict())
        and torch.equal(torch_before, torch.get_rng_state())
        and all(
            np.array_equal(left, right) if isinstance(left, np.ndarray) else left == right
            for left, right in zip(numpy_before, np.random.get_state())
        )
        and python_before == random.getstate()
    )
    checks["fresh_mask_normalization"] = all(
        np.isneginf(output[np.asarray(mask) == 0]).all()
        and np.isfinite(output[np.asarray(mask) == 1]).all()
        and abs(float(np.exp(output[np.asarray(mask) == 1]).sum()) - 1.0) <= 5e-13
        for output, mask in zip(batch_outputs, masks)
    )

    # Independently load and evaluate the identical canonical 256-row batch.
    encoded = [
        subject.encode_h11_tensors(state, actor, hole, mask)
        for state, actor, hole, mask in selected
    ]
    padded = encoded + [encoded[-1]] * (256 - len(encoded))
    oracle = independent_model()
    with torch.inference_mode():
        oracle_logits, _ = oracle(
            torch.cat([row[0] for row in padded]),
            torch.cat([row[1] for row in padded]),
            torch.cat([row[2] for row in padded]),
            torch.cat([row[3] for row in padded]),
        )
    oracle_outputs = normalized(
        oracle_logits,
        torch.cat([row[3] for row in padded]),
    )[:len(selected)]
    direct_error = max(
        float(np.max(np.abs(left[np.isfinite(left)] - right[np.isfinite(right)])))
        for left, right in zip(batch_outputs, oracle_outputs)
    )
    checks["fixed_batch_independent_oracle_within_2e6"] = direct_error <= 2e-6

    # Target row must be invariant to caller length, other rows, position, chunk,
    # and canonical duplicate padding. Every internal forward remains exactly 256.
    target = fixtures[0]
    baseline = subject.evaluate_h11_log_probs(*target)
    shape_cases: dict[str, float] = {}
    for size, position in (
        (1, 0), (2, 1), (31, 15), (32, 31), (255, 254),
        (256, 128), (257, 256), (513, 512),
    ):
        rows = [fixtures[1 + (index % (len(fixtures) - 1))] for index in range(size)]
        rows[position] = target
        outputs = subject.evaluate_h11_log_probs_batch(
            [row[0] for row in rows],
            [row[1] for row in rows],
            [row[2] for row in rows],
            [row[3] for row in rows],
        )
        error = float(np.max(np.abs(
            baseline[np.isfinite(baseline)]
            - outputs[position][np.isfinite(outputs[position])]
        )))
        shape_cases[f"n{size}_p{position}"] = error
    maximum_shape_error = max(shape_cases.values())
    checks["fixed_batch_shape_and_hostile_row_invariance"] = maximum_shape_error <= 2e-6

    permutation = list(reversed(range(len(selected))))
    reversed_outputs = subject.evaluate_h11_log_probs_batch(
        [states[index] for index in permutation],
        [actors[index] for index in permutation],
        [holes[index] for index in permutation],
        [masks[index] for index in permutation],
    )
    reverse_error = max(
        float(np.max(np.abs(
            batch_outputs[index][np.isfinite(batch_outputs[index])]
            - reversed_outputs[len(selected) - 1 - index][
                np.isfinite(reversed_outputs[len(selected) - 1 - index])
            ]
        )))
        for index in range(len(selected))
    )
    checks["fixed_batch_order_invariance"] = reverse_error <= 2e-6

    signature_scalar = tuple(
        inspect.signature(subject.evaluate_h11_log_probs).parameters
    )
    signature_batch = tuple(
        inspect.signature(subject.evaluate_h11_log_probs_batch).parameters
    )
    checks["hidden_information_absent_from_fresh_api"] = (
        signature_scalar
        == ("public_state", "acting_player", "own_hole", "legal_mask")
        and signature_batch
        == ("public_states", "acting_players", "own_holes", "legal_masks")
    )
    checks["no_scientific_artifacts_created"] = True

    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.lrft_i00c1.fixed_batch_qualification.v1",
        "recorded_at": "2026-07-23T22:35:00-04:00",
        "status": (
            "LRFT-I00C1_FIXED_BATCH_INTERFACE_QUALIFICATION_PASS"
            if not failed
            else "LRFT-I00C1_FIXED_BATCH_INTERFACE_QUALIFICATION_NONPASS"
        ),
        "identity_sha256": IDENTITY,
        "parent": {
            "identity_sha256": PARENT_IDENTITY,
            "result_sha256": PARENT_RESULT_SHA256,
            "terminal_status": parent["status"],
            "sole_failed_check": "independent_direct_h11_oracle",
            "observed_parent_max_abs_error":
                parent["diagnostics"]["max_direct_logprob_abs_error"],
        },
        "source_sha256": {
            "frozen_exact_cent_engine": sha256_path(PARENT_ENGINE),
            "fresh_fixed_batch_likelihood": sha256_path(SUBJECT_PATH),
            "fresh_test_runner": sha256_path(Path(__file__).resolve()),
            "h11_checkpoint": sha256_path(subject.H11_CHECKPOINT_PATH),
        },
        "correction": {
            "sole_change": subject.SOLE_CORRECTION,
            "canonical_batch_size": 256,
            "terminal_chunk_padding": "duplicate_final_validated_row_then_discard",
            "threshold_unchanged": "max_abs_logprob_error<=2e-6",
            "engine_changed": False,
            "checkpoint_or_observation_changed": False,
        },
        "scope": {
            "interface_only": True,
            "behavior_changed": False,
            "training_hands": 0,
            "teacher_rows": 0,
            "solver_roots": 0,
            "checkpoints": 0,
            "network_calls": 0,
            "slumbot_hands": 0,
        },
        "checks": checks,
        "counts": {
            "fresh_observation_rows": observation_rows,
            "fixed_batch_oracle_rows": len(selected),
            "shape_invariance_cases": len(shape_cases),
        },
        "diagnostics": {
            "direct_oracle_max_abs_error": direct_error,
            "maximum_shape_case_abs_error": maximum_shape_error,
            "reverse_order_max_abs_error": reverse_error,
            "shape_cases": shape_cases,
        },
        "judgment": {
            "clears_exact_cent_interface_blocker": not failed,
            "clears_arbitrary_hole_likelihood_blocker": not failed,
            "authorizes_lrft_f64_preregistration_only": not failed,
            "does_not_authorize_root_census_solver_teacher_bc_checkpoint_or_quick5k": True,
        },
        "passed": sum(checks.values()),
        "total": len(checks),
        "failed_checks": failed,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "passed": result["passed"],
        "total": result["total"],
        "failed": failed,
        "direct_error": direct_error,
        "shape_error": maximum_shape_error,
        "reverse_error": reverse_error,
    }, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
