#!/usr/bin/env python3
"""Deterministic H2 all-showdown critic targets.

This module is deliberately independent of the rollout worker.  It computes a
critic-only terminal line-value target while holding the terminal committed-chip
vector fixed.  It does not compute counterfactual action EV and must never be
used to replace environment rewards or actor advantages.
"""
from __future__ import annotations

import hashlib
import math
import random
from itertools import combinations
from typing import Iterable, Sequence

import numpy as np


H2_TARGET_SEED = 2026071401
H2_MAX_RUNOUTS = 200


def _straight_high(presence: np.ndarray) -> np.ndarray:
    result = np.full(presence.shape[0], -1, dtype=np.int16)
    for high in range(12, 3, -1):
        hit = presence[:, high - 4:high + 1].all(axis=1) & (result < 0)
        result[hit] = high
    wheel = presence[:, [12, 0, 1, 2, 3]].all(axis=1) & (result < 0)
    result[wheel] = 3
    return result


def _descending_qualifying_ranks(mask: np.ndarray) -> np.ndarray:
    ranks = np.arange(13, dtype=np.int16)[None, :]
    return np.sort(np.where(mask, ranks, -1), axis=1)[:, ::-1]


def evaluate_7card_batch(cards: np.ndarray) -> np.ndarray:
    """Vectorized exact seven-card rank; larger integer means stronger."""
    cards = np.asarray(cards, dtype=np.int16)
    if cards.ndim != 2 or cards.shape[1] != 7:
        raise ValueError("cards must have shape (N, 7)")
    if cards.size and (cards.min() < 0 or cards.max() >= 52):
        raise ValueError("card outside [0, 51]")
    if any(len(set(map(int, row))) != 7 for row in cards):
        raise ValueError("duplicate cards in seven-card row")
    n = cards.shape[0]
    ranks = cards // 4
    suits = cards % 4
    rows = np.repeat(np.arange(n), 7)
    rank_counts = np.zeros((n, 13), dtype=np.int8)
    suit_rank = np.zeros((n, 4, 13), dtype=np.bool_)
    np.add.at(rank_counts, (rows, ranks.reshape(-1)), 1)
    suit_rank[rows, suits.reshape(-1), ranks.reshape(-1)] = True
    suit_counts = suit_rank.sum(axis=2)
    presence = rank_counts > 0
    pair_ranks = _descending_qualifying_ranks(rank_counts >= 2)
    trip_ranks = _descending_qualifying_ranks(rank_counts >= 3)
    quad_ranks = _descending_qualifying_ranks(rank_counts == 4)
    distinct_ranks = _descending_qualifying_ranks(presence)
    straight = _straight_high(presence)
    flush_suit = np.argmax(suit_counts, axis=1)
    has_flush = suit_counts[np.arange(n), flush_suit] >= 5
    flush_presence = suit_rank[np.arange(n), flush_suit]
    flush_ranks = _descending_qualifying_ranks(flush_presence)
    straight_flush = _straight_high(flush_presence)

    category = np.zeros(n, dtype=np.int64)
    tie = np.zeros((n, 5), dtype=np.int64)
    unresolved = np.ones(n, dtype=np.bool_)

    def assign(mask, cat, columns):
        nonlocal unresolved
        use = unresolved & mask
        category[use] = cat
        for column, values in enumerate(columns):
            tie[use, column] = np.asarray(values)[use]
        unresolved[use] = False

    assign(straight_flush >= 0, 8, [straight_flush])
    quad = quad_ranks[:, 0]
    quad_kicker = np.max(np.where(presence & (np.arange(13)[None, :] != quad[:, None]), np.arange(13)[None, :], -1), axis=1)
    assign(quad >= 0, 7, [quad, quad_kicker])
    top_trip = trip_ranks[:, 0]
    full_house_pair = np.max(np.where((rank_counts >= 2) & (np.arange(13)[None, :] != top_trip[:, None]), np.arange(13)[None, :], -1), axis=1)
    assign((top_trip >= 0) & (full_house_pair >= 0), 6, [top_trip, full_house_pair])
    assign(has_flush, 5, [flush_ranks[:, i] for i in range(5)])
    assign(straight >= 0, 4, [straight])
    trip_kickers = _descending_qualifying_ranks(presence & (np.arange(13)[None, :] != top_trip[:, None]))
    assign(top_trip >= 0, 3, [top_trip, trip_kickers[:, 0], trip_kickers[:, 1]])
    pair0, pair1 = pair_ranks[:, 0], pair_ranks[:, 1]
    two_pair_kicker = np.max(np.where(presence & (np.arange(13)[None, :] != pair0[:, None]) & (np.arange(13)[None, :] != pair1[:, None]), np.arange(13)[None, :], -1), axis=1)
    assign(pair1 >= 0, 2, [pair0, pair1, two_pair_kicker])
    pair_kickers = _descending_qualifying_ranks(presence & (np.arange(13)[None, :] != pair0[:, None]))
    assign(pair0 >= 0, 1, [pair0, pair_kickers[:, 0], pair_kickers[:, 1], pair_kickers[:, 2]])
    assign(unresolved, 0, [distinct_ranks[:, i] for i in range(5)])
    powers = np.array([13 ** 4, 13 ** 3, 13 ** 2, 13, 1], dtype=np.int64)
    return category * (13 ** 5) + (tie * powers).sum(axis=1)


def _canonical_cards(cards: Sequence[int]) -> tuple[int, ...]:
    result = tuple(sorted(int(card) for card in cards))
    if len(result) != len(set(result)):
        raise ValueError("duplicate cards")
    if any(card < 0 or card >= 52 for card in result):
        raise ValueError("card outside [0, 51]")
    return result


def deterministic_runouts(
    hole0: Sequence[int],
    hole1: Sequence[int],
    board: Sequence[int],
    *,
    max_runouts: int = H2_MAX_RUNOUTS,
    target_seed: int = H2_TARGET_SEED,
    deal_identity: str,
    seat: int,
    row_index: int,
) -> tuple[list[tuple[int, ...]], bool, int]:
    """Return the registered exact-or-deterministic-unique runout set.

    The boolean is true when all possible completions were enumerated.  Sampling
    is uniform over unordered board completions and deterministic for the exact
    registered row identity.
    """
    h0 = _canonical_cards(hole0)
    h1 = _canonical_cards(hole1)
    b = _canonical_cards(board)
    if len(h0) != 2 or len(h1) != 2:
        raise ValueError("each player must have two hole cards")
    if len(b) >= 5:
        raise ValueError("H2 targets apply only before the river is complete")
    if int(seat) not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    if int(row_index) < 0:
        raise ValueError("row_index must be non-negative")
    if int(max_runouts) <= 0:
        raise ValueError("max_runouts must be positive")
    used = set(h0) | set(h1) | set(b)
    if len(used) != len(h0) + len(h1) + len(b):
        raise ValueError("hole cards and board overlap")
    remaining = [card for card in range(52) if card not in used]
    need = 5 - len(b)
    total = math.comb(len(remaining), need)
    target = min(int(max_runouts), total)
    if total <= int(max_runouts):
        return list(combinations(remaining, need)), True, total

    material = (
        f"v5.hybrid.h2.target.v1:{int(target_seed)}:{deal_identity}:"
        f"seat={int(seat)}:row={int(row_index)}:board={','.join(map(str, b))}"
    )
    rng = random.Random(int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:16], "big"))
    sampled: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    max_attempts = max(1000, target * 50)
    for _ in range(max_attempts):
        runout = tuple(sorted(rng.sample(remaining, need)))
        if runout not in seen:
            seen.add(runout)
            sampled.append(runout)
            if len(sampled) == target:
                break
    if len(sampled) != target:
        # This path is deterministic and only protects against pathological
        # rejection behavior.  It does not change the frozen sample size.
        for runout in combinations(remaining, need):
            if runout not in seen:
                sampled.append(runout)
                if len(sampled) == target:
                    break
    if len(sampled) != target:
        raise RuntimeError("could not construct the registered unique runout sample")
    return sampled, False, total


def showdown_target_from_runouts(
    hole0: Sequence[int],
    hole1: Sequence[int],
    board: Sequence[int],
    runouts: Iterable[Sequence[int]],
    *,
    seat: int,
    hero_committed: float,
    villain_committed: float,
) -> tuple[float, int, int, int]:
    """Return line-value target in existing raw-BB profit units."""
    h0 = _canonical_cards(hole0)
    h1 = _canonical_cards(hole1)
    b = _canonical_cards(board)
    completions = [tuple(map(int, completion)) for completion in runouts]
    if not completions:
        raise ValueError("empty runout set")
    boards = np.asarray([b + completion for completion in completions], dtype=np.int16)
    h0_cards = np.column_stack((np.tile(np.asarray(h0, dtype=np.int16), (len(boards), 1)), boards))
    h1_cards = np.column_stack((np.tile(np.asarray(h1, dtype=np.int16), (len(boards), 1)), boards))
    result = np.sign(evaluate_7card_batch(h0_cards) - evaluate_7card_batch(h1_cards))
    if int(seat) == 1:
        result = -result
    wins = int(np.sum(result > 0))
    losses = int(np.sum(result < 0))
    ties = int(np.sum(result == 0))
    count = wins + losses + ties
    if count <= 0:
        raise ValueError("empty runout set")
    target = (wins / count) * float(villain_committed) - (losses / count) * float(hero_committed)
    return float(target), wins, losses, ties


def h2_showdown_critic_target(
    terminal_state,
    *,
    seat: int,
    row_board: Sequence[int],
    row_index: int,
    deal_identity: str,
    hero_committed: float,
    villain_committed: float,
    max_runouts: int = H2_MAX_RUNOUTS,
    target_seed: int = H2_TARGET_SEED,
) -> dict | None:
    """Compute one eligible H2 target, or None for a non-showdown/ineligible row."""
    if terminal_state is None or not getattr(terminal_state, "is_done", False):
        return None
    if int(getattr(terminal_state, "folded_player", -1)) >= 0:
        return None
    holes = getattr(terminal_state, "hole_cards", None)
    if not holes or holes[0] is None or holes[1] is None:
        return None
    board = tuple(int(card) for card in row_board)
    if len(board) >= 5:
        return None
    runouts, exhaustive, total_possible = deterministic_runouts(
        holes[0], holes[1], board,
        max_runouts=max_runouts,
        target_seed=target_seed,
        deal_identity=str(deal_identity),
        seat=int(seat),
        row_index=int(row_index),
    )
    target, wins, losses, ties = showdown_target_from_runouts(
        holes[0], holes[1], board, runouts,
        seat=int(seat),
        hero_committed=float(hero_committed),
        villain_committed=float(villain_committed),
    )
    return {
        "target_bb": target,
        "runouts": len(runouts),
        "total_possible_runouts": int(total_possible),
        "exhaustive": bool(exhaustive),
        "wins": int(wins),
        "losses": int(losses),
        "ties": int(ties),
    }


def h2_showdown_critic_target_pair(
    terminal_state,
    *,
    row_board: Sequence[int],
    deal_identity: str,
    committed: Sequence[float],
    max_runouts: int = H2_MAX_RUNOUTS,
    target_seed: int = H2_TARGET_SEED,
) -> dict | None:
    """Compute both seats from one common runout sample for a board snapshot.

    Reusing the sample across seats and repeated decisions on the same street is
    an engineering optimization and a variance-reduction common-random-number
    design.  The returned targets still hold the same terminal committed vector
    fixed and remain critic-only.
    """
    if terminal_state is None or not getattr(terminal_state, "is_done", False):
        return None
    if int(getattr(terminal_state, "folded_player", -1)) >= 0:
        return None
    holes = getattr(terminal_state, "hole_cards", None)
    if not holes or holes[0] is None or holes[1] is None:
        return None
    board = tuple(int(card) for card in row_board)
    if len(board) >= 5:
        return None
    if len(committed) != 2:
        raise ValueError("committed must contain both seats")
    runouts, exhaustive, total_possible = deterministic_runouts(
        holes[0], holes[1], board,
        max_runouts=max_runouts,
        target_seed=target_seed,
        deal_identity=str(deal_identity),
        seat=0,
        row_index=0,
    )
    p0, wins, losses, ties = showdown_target_from_runouts(
        holes[0], holes[1], board, runouts,
        seat=0,
        hero_committed=float(committed[0]),
        villain_committed=float(committed[1]),
    )
    count = wins + losses + ties
    p1 = (losses / count) * float(committed[0]) - (wins / count) * float(committed[1])
    return {
        "target_bb": (float(p0), float(p1)),
        "runouts": len(runouts),
        "total_possible_runouts": int(total_possible),
        "exhaustive": bool(exhaustive),
        "p0_wins": int(wins),
        "p0_losses": int(losses),
        "ties": int(ties),
    }


def h2_showdown_critic_target_pairs(
    terminal_state,
    *,
    row_boards: Iterable[Sequence[int]],
    deal_identity: str,
    committed: Sequence[float],
    max_runouts: int = H2_MAX_RUNOUTS,
    target_seed: int = H2_TARGET_SEED,
) -> dict[tuple[int, ...], dict | None]:
    """Batch all unique pre-river board snapshots from one completed hand."""
    unique_boards = list(dict.fromkeys(tuple(int(card) for card in board) for board in row_boards))
    output: dict[tuple[int, ...], dict | None] = {board: None for board in unique_boards}
    if terminal_state is None or not getattr(terminal_state, "is_done", False):
        return output
    if int(getattr(terminal_state, "folded_player", -1)) >= 0:
        return output
    holes = getattr(terminal_state, "hole_cards", None)
    if not holes or holes[0] is None or holes[1] is None:
        return output
    if len(committed) != 2:
        raise ValueError("committed must contain both seats")
    eligible = [board for board in unique_boards if len(board) < 5]
    if not eligible:
        return output
    segments = []
    full_boards = []
    for board in eligible:
        runouts, exhaustive, total_possible = deterministic_runouts(
            holes[0], holes[1], board,
            max_runouts=max_runouts,
            target_seed=target_seed,
            deal_identity=str(deal_identity),
            seat=0,
            row_index=0,
        )
        start = len(full_boards)
        full_boards.extend(board + tuple(runout) for runout in runouts)
        segments.append((board, start, len(full_boards), exhaustive, total_possible))
    boards_array = np.asarray(full_boards, dtype=np.int16)
    h0 = _canonical_cards(holes[0])
    h1 = _canonical_cards(holes[1])
    h0_cards = np.column_stack((np.tile(np.asarray(h0, dtype=np.int16), (len(boards_array), 1)), boards_array))
    h1_cards = np.column_stack((np.tile(np.asarray(h1, dtype=np.int16), (len(boards_array), 1)), boards_array))
    signs = np.sign(evaluate_7card_batch(h0_cards) - evaluate_7card_batch(h1_cards))
    for board, start, end, exhaustive, total_possible in segments:
        segment = signs[start:end]
        wins = int(np.sum(segment > 0))
        losses = int(np.sum(segment < 0))
        ties = int(np.sum(segment == 0))
        count = wins + losses + ties
        p0 = (wins / count) * float(committed[1]) - (losses / count) * float(committed[0])
        p1 = (losses / count) * float(committed[0]) - (wins / count) * float(committed[1])
        output[board] = {
            "target_bb": (float(p0), float(p1)),
            "runouts": int(count),
            "total_possible_runouts": int(total_possible),
            "exhaustive": bool(exhaustive),
            "p0_wins": wins,
            "p0_losses": losses,
            "ties": ties,
        }
    return output
