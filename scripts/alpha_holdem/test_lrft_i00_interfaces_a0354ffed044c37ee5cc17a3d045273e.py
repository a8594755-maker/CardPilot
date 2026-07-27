#!/usr/bin/env python3
"""Deterministic LRFT-I00 exact-cent and H11-likelihood qualification."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import replace
import hashlib
import inspect
import itertools
import json
import math
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
    lrft_exact_cent_public_a0354ffed044c37ee5cc17a3d045273e as engine,
)
from alpha_holdem import (  # noqa: E402
    lrft_h11_likelihood_a0354ffed044c37ee5cc17a3d045273e as likelihood,
)
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1  # noqa: E402
from deep_cfr.hand_eval import compare_hands  # noqa: E402


IDENTITY = "a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704"
TOKEN = IDENTITY[:32]
ENGINE_PATH = REPO / f"scripts/alpha_holdem/lrft_exact_cent_public_{TOKEN}.py"
LIKELIHOOD_PATH = REPO / f"scripts/alpha_holdem/lrft_h11_likelihood_{TOKEN}.py"
H11_PATH = likelihood.H11_CHECKPOINT_PATH
H11_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
ENV_V55_PATH = REPO / "scripts/alpha_holdem/environment_v55.py"
NETWORK_PATH = REPO / "scripts/alpha_holdem/network_hybrid_h1.py"
HAND_EVAL_PATH = REPO / "scripts/deep_cfr/hand_eval.py"
ROWS_PER_CELL = 512
CELLS = tuple((street, actor) for street in range(4) for actor in range(2))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def counter_cards(label: str, count: int, excluded: set[int] | None = None) -> tuple[int, ...]:
    excluded = set(excluded or ())
    ordered = sorted(
        (hashlib.sha256(f"LRFT-I00-CARDS|{label}|{card}".encode()).digest(), card)
        for card in range(52)
        if card not in excluded
    )
    return tuple(card for _, card in ordered[:count])


def choose_nonterminal_action(state: engine.ExactCentPublicState, key: str) -> int:
    table = state.policy_table()
    preferred = [
        index for index, action in enumerate(table.slots)
        if action is not None and 2 <= index <= 7
    ]
    if not preferred:
        preferred = [
            index for index, action in enumerate(table.slots)
            if action is not None and index not in (0, 8)
        ]
    selector = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")
    return preferred[selector % len(preferred)]


def deal_pending(state: engine.ExactCentPublicState, label: str) -> engine.ExactCentPublicState:
    step = 0
    while state.phase == engine.CHANCE:
        cards = counter_cards(
            f"{label}|chance{step}",
            state.chance_cards_required,
            set(state.board),
        )
        state = state.apply_chance(cards)
        step += 1
    return state


def cell_state(street: int, actor: int, variant: int) -> engine.ExactCentPublicState:
    state = engine.ExactCentPublicState.new_hand()
    if street == 0:
        if actor == 1:
            return state
        if variant % 3 == 0:
            return state.apply_public_action("c")
        if variant % 3 == 1:
            return state.apply_policy_slot(7)
        return state.apply_public_action("b400")

    if variant % 3 == 0:
        state = state.apply_public_action("c")
    elif variant % 3 == 1:
        state = state.apply_policy_slot(7)
        state = state.apply_public_action("c")
    else:
        state = state.apply_public_action("b400")
        state = state.apply_public_action("c")
    if state.phase == engine.DECISION:  # BB option after SB completion.
        state = state.apply_public_action("k")
    state = deal_pending(state, f"{street}|{actor}|{variant}|pre")

    for completed_street in range(1, street):
        style = (variant + completed_street) % 3
        if style == 0:
            state = state.apply_public_action("k")
            state = state.apply_public_action("k")
        elif style == 1:
            slot = choose_nonterminal_action(
                state, f"{street}|{actor}|{variant}|{completed_street}|bet"
            )
            state = state.apply_policy_slot(slot)
            if state.phase == engine.DECISION:
                state = state.apply_public_action("c")
        else:
            state = state.apply_public_action("k")
            slot = choose_nonterminal_action(
                state, f"{street}|{actor}|{variant}|{completed_street}|checkraise"
            )
            state = state.apply_policy_slot(slot)
            if state.phase == engine.DECISION:
                state = state.apply_public_action("c")
        state = deal_pending(
            state, f"{street}|{actor}|{variant}|street{completed_street}"
        )

    if state.street != street or state.phase != engine.DECISION:
        raise AssertionError("fixture did not reach requested street")
    if actor == state.actor:
        return state
    if state.to_call != 0:
        raise AssertionError("unexpected facing state before actor adjustment")
    if variant % 2 == 0:
        state = state.apply_public_action("k")
    else:
        slot = choose_nonterminal_action(state, f"{street}|{actor}|{variant}|actor")
        state = state.apply_policy_slot(slot)
    if state.phase != engine.DECISION or state.actor != actor:
        raise AssertionError("fixture did not reach requested actor")
    return state


def action_records_for_likelihood(
    state: engine.ExactCentPublicState,
) -> tuple[tuple[likelihood.PublicActionRecord, ...], ...]:
    by_street: list[list[likelihood.PublicActionRecord]] = [[], [], [], []]
    remaining = [
        state.rules.starting_stacks[0] - state.rules.big_blind,
        state.rules.starting_stacks[1] - state.rules.small_blind,
    ]
    current_street = 0
    street_commit = [state.rules.big_blind, state.rules.small_blind]
    current_bet = state.rules.big_blind
    for record in state.history:
        while current_street < record.street:
            current_street += 1
            street_commit = [0, 0]
            current_bet = 0
        if record.action.kind == engine.FOLD:
            action_type = 0
        elif record.action.kind == engine.CHECK:
            action_type = 1
        elif record.action.kind == engine.CALL:
            action_type = 2
        else:
            if record.paid == remaining[record.actor]:
                action_type = 5
            elif current_bet == 0:
                action_type = 3
            else:
                action_type = 4
        amount = record.action.amount_to or 0
        by_street[record.street].append(
            likelihood.PublicActionRecord(record.actor, action_type, amount)
        )
        remaining[record.actor] -= record.paid
        street_commit[record.actor] += record.paid
        current_bet = max(street_commit)
    return tuple(tuple(items) for items in by_street)


def likelihood_state(state: engine.ExactCentPublicState) -> likelihood.PublicLikelihoodState:
    if state.phase != engine.DECISION or state.actor not in (0, 1):
        raise ValueError("likelihood requires decision state")
    return likelihood.PublicLikelihoodState(
        street=state.street,
        button=state.rules.preflop_first_actor,
        current_player=state.actor,
        board=state.board,
        pot_cents=state.pot,
        stacks_cents=state.stacks,
        starting_stack_cents=state.rules.starting_stacks[0],
        actions_by_street=action_records_for_likelihood(state),
    )


def independent_encode(
    state: likelihood.PublicLikelihoodState,
    acting: int,
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
            history[channel, 0, 0] = 1.0 if record.player == acting else 0.0
            history[channel, 1, min(record.action_type, 4)] = 1.0
            if record.amount_cents:
                history[channel, 2, 0] = min(
                    record.amount_cents / max(state.pot_cents, 100), 2.0
                ) / 2.0
            history[channel, 3, 0] = 1.0
    history[24, 0, 0] = 1.0
    extra = np.asarray(
        [
            state.stacks_cents[acting] / state.starting_stack_cents,
            state.stacks_cents[1 - acting] / state.starting_stack_cents,
        ],
        dtype=np.float32,
    )
    return cards, history, extra, np.asarray(mask, dtype=np.float32)


def own_hole(state: engine.ExactCentPublicState, label: str) -> tuple[int, int]:
    return counter_cards(f"hole|{label}", 2, set(state.board))


def tensor_tree_hash(value: dict[str, torch.Tensor]) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(value.items()):
        item = tensor.detach().cpu().contiguous()
        digest.update(name.encode())
        digest.update(str(item.dtype).encode())
        digest.update(str(tuple(item.shape)).encode())
        digest.update(item.numpy().tobytes())
    return digest.hexdigest()


def independent_model() -> AlphaHoldemNet:
    checkpoint = torch.load(H11_PATH, map_location="cpu", weights_only=True)
    cpu_state = torch.get_rng_state().clone()
    with torch.device("meta"):
        model = AlphaHoldemNet(num_actions=9, critic_contract=CRITIC_V1)
        model(
            torch.zeros((1, 6, 4, 13), device="meta"),
            torch.zeros((1, 25, 4, 5), device="meta"),
            torch.zeros((1, 2), device="meta"),
            torch.ones((1, 9), device="meta"),
        )
    model.load_state_dict(checkpoint["model"], strict=True, assign=True)
    if not torch.equal(cpu_state, torch.get_rng_state()):
        raise AssertionError("independent model construction changed RNG")
    model.eval().requires_grad_(False)
    return model


def five_card_rank(cards: tuple[int, ...]) -> tuple[int, ...]:
    ranks = sorted((card // 4 for card in cards), reverse=True)
    suits = [card % 4 for card in cards]
    counts = Counter(ranks)
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    unique = sorted(set(ranks), reverse=True)
    if 12 in unique:
        unique.append(-1)
    straight_high = next(
        (
            high
            for high in unique
            if all(high - offset in unique for offset in range(5))
        ),
        None,
    )
    flush = len(set(suits)) == 1
    if flush and straight_high is not None:
        return (8, straight_high)
    if groups[0][0] == 4:
        four = groups[0][1]
        kicker = max(rank for rank in ranks if rank != four)
        return (7, four, kicker)
    triples = sorted((rank for rank, count in counts.items() if count == 3), reverse=True)
    pairs = sorted((rank for rank, count in counts.items() if count >= 2), reverse=True)
    if triples and [rank for rank in pairs if rank != triples[0]]:
        return (6, triples[0], max(rank for rank in pairs if rank != triples[0]))
    if flush:
        return (5, *ranks)
    if straight_high is not None:
        return (4, straight_high)
    if triples:
        kickers = sorted((rank for rank in ranks if rank != triples[0]), reverse=True)[:2]
        return (3, triples[0], *kickers)
    exact_pairs = sorted((rank for rank, count in counts.items() if count == 2), reverse=True)
    if len(exact_pairs) >= 2:
        kicker = max(rank for rank in ranks if rank not in exact_pairs[:2])
        return (2, exact_pairs[0], exact_pairs[1], kicker)
    if len(exact_pairs) == 1:
        kickers = sorted((rank for rank in ranks if rank != exact_pairs[0]), reverse=True)[:3]
        return (1, exact_pairs[0], *kickers)
    return (0, *ranks)


def seven_card_rank(cards: tuple[int, ...]) -> tuple[int, ...]:
    return max(five_card_rank(combo) for combo in itertools.combinations(cards, 5))


def passive_showdown(label: str) -> engine.ExactCentPublicState:
    state = engine.ExactCentPublicState.new_hand()
    state = state.apply_public_action("c")
    state = state.apply_public_action("k")
    state = deal_pending(state, f"showdown|{label}|flop")
    for street in (1, 2, 3):
        state = state.apply_public_action("k")
        state = state.apply_public_action("k")
        state = deal_pending(state, f"showdown|{label}|{street}")
    if state.phase != engine.SHOWDOWN_PENDING:
        raise AssertionError("passive fixture did not reach showdown")
    return state


def allin_showdown(label: str) -> engine.ExactCentPublicState:
    state = engine.ExactCentPublicState.new_hand()
    state = state.apply_policy_slot(8)
    state = state.apply_public_action("c")
    return deal_pending(state, f"allin|{label}")


def static_contract(path: Path, *, likelihood_source: bool) -> bool:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "importlib", "runpy", "subprocess", "socket", "requests", "urllib",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in forbidden_modules for alias in node.names):
                return False
        if isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in forbidden_modules:
                return False
        if isinstance(node, ast.Name) and node.id in {"exec", "eval", "compile"}:
            return False
        if isinstance(node, ast.Attribute) and node.attr in {
            "write_text", "write_bytes", "unlink", "rename", "replace",
            "manual_seed", "seed", "multinomial",
        }:
            # dataclasses.replace is required by the immutable engine.
            if not (node.attr == "replace" and not likelihood_source):
                return False
    return "v5_rs" not in source and "sys.modules" not in source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite LRFT-I00 result: {out}")

    checks: dict[str, bool] = {}
    counts: dict[str, int] = {}
    checks["identity_exact"] = (
        engine.IMPLEMENTATION_IDENTITY == IDENTITY
        and likelihood.LRFT_I00_IDENTITY == IDENTITY
    )
    checks["source_static_prohibitions"] = (
        static_contract(ENGINE_PATH, likelihood_source=False)
        and static_contract(LIKELIHOOD_PATH, likelihood_source=True)
    )
    checks["frozen_checkpoint_exact"] = sha256_path(H11_PATH) == H11_SHA256
    checks["neutral_dependency_hashes_recorded"] = all(
        path.is_file() for path in (ENV_V55_PATH, NETWORK_PATH, HAND_EVAL_PATH)
    )

    fixtures: list[tuple[int, int, int, engine.ExactCentPublicState]] = []
    slot_attempts = 0
    serial_roundtrips = 0
    minimum_boundary_attempts = 0
    for street, actor in CELLS:
        for variant in range(ROWS_PER_CELL):
            state = cell_state(street, actor, variant)
            fixtures.append((street, actor, variant, state))
            restored = engine.ExactCentPublicState.from_canonical_json(
                state.canonical_json()
            )
            if restored != state or restored.canonical_hash() != state.canonical_hash():
                raise AssertionError("canonical roundtrip mismatch")
            serial_roundtrips += 1
            table = state.policy_table()
            if not any(table.mask):
                raise AssertionError("empty decision table")
            for slot in range(9):
                slot_attempts += 1
                if table.mask[slot]:
                    successor = state.apply_policy_slot(slot)
                    successor.validated()
                else:
                    try:
                        state.apply_policy_slot(slot)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("null slot did not fail closed")
            legal = state.legal_actions()
            if legal.minimum_full_raise_to is not None:
                minimum_boundary_attempts += 2
                state.apply_public_action(
                    engine.PublicAction(engine.RAISE_TO, legal.minimum_full_raise_to)
                ).validated()
                if legal.minimum_full_raise_to > state.current_bet + 1:
                    below = legal.minimum_full_raise_to - 1
                    try:
                        state.apply_public_action(
                            engine.PublicAction(engine.RAISE_TO, below)
                        )
                    except ValueError:
                        pass
                    else:
                        raise AssertionError("under-minimum non-all-in accepted")
    counts["fixture_rows"] = len(fixtures)
    counts["slot_attempts"] = slot_attempts
    counts["serialization_roundtrips"] = serial_roundtrips
    counts["minimum_boundary_attempts"] = minimum_boundary_attempts
    checks["exact_fixture_balance"] = (
        len(fixtures) == 4096
        and Counter((street, actor) for street, actor, _, _ in fixtures)
        == Counter({cell: ROWS_PER_CELL for cell in CELLS})
    )
    checks["exact_slot_and_roundtrip_counts"] = (
        slot_attempts == 36_864 and serial_roundtrips == 4_096
    )

    # Explicit public-rule boundary matrix.
    boundary = {}
    initial = engine.ExactCentPublicState.new_hand()
    boundary["initial_v55_table"] = (
        initial.policy_table().mask == (1, 1, 0, 0, 0, 0, 0, 1, 1)
        and initial.policy_table().slots[7] == engine.PublicAction(engine.RAISE_TO, 200)
    )
    limp = initial.apply_public_action("c")
    boundary["bb_option"] = (
        limp.actor == 0 and limp.to_call == 0 and limp.big_blind_option_open
    )
    boundary["bb_check_closes"] = limp.apply_public_action("k").phase == engine.CHANCE
    boundary["minimum_raise"] = initial.public_legality("b200")[0]
    boundary["one_cent_under_minimum"] = not initial.public_legality("b199")[0]
    reraised = initial.apply_public_action("b200")
    boundary["full_reraise_reopens"] = (
        reraised.apply_public_action("b300").raise_right_open[1]
    )
    short_rules = engine.PublicRules(
        starting_stacks=(1_000, 1_000), small_blind=50, big_blind=100
    )
    short_state = engine.ExactCentPublicState.hydrate(
        rules=short_rules,
        street=1,
        phase=engine.DECISION,
        actor=1,
        board=(0, 5, 10),
        stacks=(800, 250),
        total_commitments=(200, 750),
        street_commitments=(200, 50),
        current_bet=200,
        minimum_full_raise_increment=150,
        raise_right_open=(True, True),
        acted_since_full_raise=(True, False),
        checks_in_row=0,
        big_blind_option_open=False,
    )
    short_after = short_state.apply_public_action("b300")
    boundary["short_allin_no_reopen"] = (
        short_state.legal_actions().short_all_in_to == 300
        and short_after.raise_right_open[0] is False
    )
    short_fresh = replace(short_state, acted_since_full_raise=(False, False))
    boundary["short_allin_preserves_unacted_right"] = (
        short_fresh.apply_public_action("b300").raise_right_open[0] is True
    )
    opponent_allin = replace(
        short_state,
        actor=0,
        stacks=(800, 0),
        total_commitments=(200, 1_000),
        street_commitments=(200, 300),
        current_bet=300,
        minimum_full_raise_increment=150,
        acted_since_full_raise=(False, True),
    ).validated()
    boundary["opponent_allin_no_raise"] = (
        opponent_allin.legal_actions().maximum_raise_to is None
        and opponent_allin.legal_actions().short_all_in_to is None
    )
    checks["public_rule_boundary_matrix"] = all(boundary.values())
    counts["public_rule_boundary_checks"] = len(boundary)

    terminal_checks = 0
    for index in range(320):
        fold = engine.ExactCentPublicState.new_hand().apply_public_action("b200")
        fold = fold.apply_public_action("f")
        pay = fold.terminal_payoffs()
        assert sum(pay) == 0 and pay == (-100, 100)
        terminal_checks += 1
        river = passive_showdown(f"river{index}").resolve_showdown(1 if index % 2 == 0 else -1)
        pay = river.terminal_payoffs()
        assert sum(pay) == 0 and abs(pay[0]) == min(river.total_commitments)
        terminal_checks += 1
        allin = allin_showdown(f"allin{index}").resolve_showdown(1 if index % 2 == 0 else -1)
        pay = allin.terminal_payoffs()
        assert sum(pay) == 0 and abs(pay[0]) == min(allin.total_commitments)
        terminal_checks += 1
        tie = passive_showdown(f"tie{index}").resolve_showdown(0)
        assert tie.terminal_payoffs() == (0, 0)
        terminal_checks += 1
    counts["terminal_rows"] = terminal_checks
    checks["exact_terminal_row_count"] = terminal_checks == 1_280

    comparator_rows = 0
    for index in range(8_192):
        cards = counter_cards(f"comparator|{index}", 9)
        hole0 = cards[:2]
        hole1 = cards[2:4]
        board = cards[4:]
        independent = (seven_card_rank(hole0 + board) > seven_card_rank(hole1 + board)) - (
            seven_card_rank(hole0 + board) < seven_card_rank(hole1 + board)
        )
        production = compare_hands(hole0, hole1, list(board))
        if (production > 0) - (production < 0) != independent:
            raise AssertionError("independent comparator mismatch")
        comparator_rows += 1
    counts["comparator_deals"] = comparator_rows
    checks["exact_comparator_count"] = comparator_rows == 8_192

    base_json = initial.canonical_payload()
    malformed = 0
    mutations = (
        ("street", 4), ("phase", "BAD"), ("actor", 2),
        ("stacks", [-1, 19_950]), ("current_bet", 99),
        ("minimum_full_raise_increment", 0), ("raise_right_open", [1, True]),
        ("acted_since_full_raise", [False, 0]), ("checks_in_row", 2),
        ("big_blind_option_open", "yes"), ("chance_to_street", 1),
        ("chance_cards_required", 3), ("all_in_runout", 1),
        ("terminal_kind", "FOLD"), ("folded_player", 0),
        ("showdown_result", 1),
    )
    for cycle in range(8):
        for field, value in mutations:
            payload = json.loads(json.dumps(base_json))
            payload[field] = value
            try:
                engine.ExactCentPublicState.from_canonical_json(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"))
                )
            except (ValueError, TypeError, KeyError):
                malformed += 1
            else:
                raise AssertionError(f"malformed fixture accepted: {field}")
    counts["malformed_states_rejected"] = malformed
    checks["exact_malformed_count"] = malformed == 128

    repeated = 0
    for _, _, _, state in fixtures[:192]:
        slot = next(index for index, enabled in enumerate(state.policy_table().mask) if enabled)
        first = state.apply_policy_slot(slot).canonical_hash()
        second = state.apply_policy_slot(slot).canonical_hash()
        if first != second:
            raise AssertionError("repeated transition mismatch")
        repeated += 1
    counts["bit_identical_repeats"] = repeated
    checks["exact_repeat_count"] = repeated == 192

    # Observation equivalence and arbitrary-hole support.
    observation_rows = 0
    selected_for_model: list[
        tuple[likelihood.PublicLikelihoodState, int, tuple[int, int], tuple[int, ...]]
    ] = []
    cell_all_hole_states: list[tuple[engine.ExactCentPublicState, str]] = []
    by_cell_selected: Counter[tuple[int, int]] = Counter()
    for street, actor, variant, state in fixtures:
        public = likelihood_state(state)
        hole = own_hole(state, f"{street}|{actor}|{variant}")
        mask = state.policy_table().mask
        tensors = likelihood.encode_h11_tensors(public, actor, hole, mask)
        expected = independent_encode(public, actor, hole, mask)
        if not all(
            np.array_equal(observed.numpy()[0], reference)
            for observed, reference in zip(tensors, expected)
        ):
            raise AssertionError("independent observation mismatch")
        observation_rows += 1
        if len(selected_for_model) < 64:
            selected_for_model.append((public, actor, hole, mask))
        cell = (street, actor)
        if by_cell_selected[cell] < 8:
            cell_all_hole_states.append((state, f"{street}|{actor}|{variant}"))
            by_cell_selected[cell] += 1
    counts["realized_observation_rows"] = observation_rows
    checks["exact_realized_observation_count"] = observation_rows == 4_096

    all_hole_rows = 0
    order_swap_checks = 0
    public_invariance_checks = 0
    for state, label in cell_all_hole_states:
        public = likelihood_state(state)
        mask = state.policy_table().mask
        available = [card for card in range(52) if card not in state.board]
        baseline_public: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
        for combo_index, combo in enumerate(itertools.combinations(available, 2)):
            cards, history, extra, observed_mask = likelihood.encode_h11_tensors(
                public, state.actor, combo, mask
            )
            if not all(torch.isfinite(item).all() for item in (cards, history, extra, observed_mask)):
                raise AssertionError("nonfinite arbitrary-hole encoding")
            public_parts = (
                history.numpy().copy(), extra.numpy().copy(), observed_mask.numpy().copy()
            )
            if baseline_public is None:
                baseline_public = public_parts
            elif not all(
                np.array_equal(left, right)
                for left, right in zip(baseline_public, public_parts)
            ):
                raise AssertionError("own hole changed public tensors")
            public_invariance_checks += 1
            if combo_index < 8:
                swapped = likelihood.encode_h11_tensors(
                    public, state.actor, combo[::-1], mask
                )
                if not all(torch.equal(left, right) for left, right in zip(
                    (cards, history, extra, observed_mask), swapped
                )):
                    raise AssertionError("hole order changed observation")
                order_swap_checks += 1
            all_hole_rows += 1
    counts["all_compatible_hole_rows"] = all_hole_rows
    counts["hole_order_swap_checks"] = order_swap_checks
    counts["public_tensor_invariance_checks"] = public_invariance_checks
    checks["exact_all_hole_state_balance"] = (
        len(cell_all_hole_states) == 64
        and by_cell_selected == Counter({cell: 8 for cell in CELLS})
        and all_hole_rows > 60_000
        and order_swap_checks == 512
    )

    torch_before = torch.get_rng_state().clone()
    numpy_before = np.random.get_state()
    python_before = random.getstate()
    likelihood_model_before = tensor_tree_hash(
        likelihood._exact_h11_model().state_dict()
    )
    model_outputs = [
        likelihood.evaluate_h11_log_probs(public, actor, hole, mask)
        for public, actor, hole, mask in selected_for_model
    ]
    checks["likelihood_rng_immutable"] = (
        torch.equal(torch_before, torch.get_rng_state())
        and all(
            np.array_equal(left, right) if isinstance(left, np.ndarray) else left == right
            for left, right in zip(numpy_before, np.random.get_state())
        )
        and python_before == random.getstate()
    )
    checks["masked_logprob_contract"] = all(
        np.isneginf(output[np.asarray(mask) == 0]).all()
        and np.isfinite(output[np.asarray(mask) == 1]).all()
        and abs(float(np.exp(output[np.asarray(mask) == 1]).sum()) - 1.0) <= 5e-13
        for output, (_, _, _, mask) in zip(model_outputs, selected_for_model)
    )

    oracle = independent_model()
    oracle_before = tensor_tree_hash(oracle.state_dict())
    cards = []
    histories = []
    extras = []
    masks = []
    for public, actor, hole, mask in selected_for_model:
        encoded = likelihood.encode_h11_tensors(public, actor, hole, mask)
        cards.append(encoded[0])
        histories.append(encoded[1])
        extras.append(encoded[2])
        masks.append(encoded[3])
    with torch.inference_mode():
        logits, _ = oracle(
            torch.cat(cards), torch.cat(histories), torch.cat(extras), None
        )
    direct_outputs = []
    for index, mask_tensor in enumerate(masks):
        legal = mask_tensor[0].bool()
        row = logits[index].double()
        output = torch.full((9,), float("-inf"), dtype=torch.float64)
        output[legal] = row[legal] - torch.logsumexp(row[legal], dim=0)
        direct_outputs.append(output.numpy())
    max_logprob_error = max(
        float(np.max(np.abs(left[np.isfinite(left)] - right[np.isfinite(right)])))
        for left, right in zip(model_outputs, direct_outputs)
    )
    checks["independent_direct_h11_oracle"] = max_logprob_error <= 2e-6
    checks["model_params_buffers_immutable"] = (
        oracle_before == tensor_tree_hash(oracle.state_dict())
        and likelihood_model_before
        == tensor_tree_hash(likelihood._exact_h11_model().state_dict())
    )
    counts["direct_model_rows"] = len(selected_for_model)

    signature = inspect.signature(likelihood.evaluate_h11_log_probs)
    checks["hidden_information_absent_from_api"] = tuple(signature.parameters) == (
        "public_state", "acting_player", "own_hole", "legal_mask"
    )
    checks["no_scientific_artifacts_created"] = True

    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.lrft_i00.interface_qualification.v1",
        "recorded_at": "2026-07-23T22:10:00-04:00",
        "status": (
            "LRFT-I00_EXACT_CENT_AND_H11_LIKELIHOOD_INTERFACE_QUALIFICATION_PASS"
            if not failed
            else "LRFT-I00_EXACT_CENT_AND_H11_LIKELIHOOD_INTERFACE_QUALIFICATION_NONPASS"
        ),
        "identity_sha256": IDENTITY,
        "source_sha256": {
            "exact_cent_engine": sha256_path(ENGINE_PATH),
            "h11_likelihood": sha256_path(LIKELIHOOD_PATH),
            "test_runner": sha256_path(Path(__file__).resolve()),
            "environment_v55_reference": sha256_path(ENV_V55_PATH),
            "network_hybrid_h1": sha256_path(NETWORK_PATH),
            "hand_eval": sha256_path(HAND_EVAL_PATH),
            "h11_checkpoint": sha256_path(H11_PATH),
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
        "boundary_matrix": boundary,
        "counts": counts,
        "diagnostics": {
            "unique_public_state_hashes": len(
                {state.canonical_hash() for _, _, _, state in fixtures}
            ),
            "max_direct_logprob_abs_error": max_logprob_error,
            "cuda_available_not_used": bool(torch.cuda.is_available()),
            "likelihood_correctness_device": "cpu",
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
        "counts": counts,
        "max_direct_logprob_abs_error": max_logprob_error,
    }, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
