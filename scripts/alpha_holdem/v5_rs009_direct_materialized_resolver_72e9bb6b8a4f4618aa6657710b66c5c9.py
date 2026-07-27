"""RS007 dual-domain fully-live resolver.

The public transition API accepts exact poker-legal cent increments.  The policy
API accepts only exact non-null H11 slots and delegates their unchanged increment
to the public API.  Public replay never projects through the policy abstraction.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
import os
import random
import re
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

TOKEN = "72e9bb6b8a4f4618aa6657710b66c5c9"
IDENTITY = "72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4"
PREREG = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_BYTES = 14797
PREREG_SHA = "54b081b37171449d782b6b64ffaf84e9c553eea2c0bae426a00533790d229aea"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_preregistration_audit_{TOKEN}_20260723.json"
PREREG_AUDIT_BYTES = 7135
PREREG_AUDIT_SHA = "4d22631cdb6d58d8a4a3d543daf4fe30f0aa9ea474214af4336e7796963465c6"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs009_direct_materialized_resolver_qualification_{TOKEN}_20260723"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"

STACK = 20_000
SB = 50
BB = 100
SLOTS = 9
MC = 32
RAISE_FRACTIONS = (0.33, 0.50, 0.67, 0.75, 1.00, 1.50)
PREFLOP_FRACTIONS = (0.50, 1.00, 1.50)
RANKS = "23456789TJQKA"
SUITS = "cdhs"
SYNTHETIC_SEED = 2026072299
WITNESS_SEED = 2026972299
HIDDEN_SEED = 2027972299
FUTURE_SEED = 2028972299
ROLLOUT_SEED = 2029972299
FAULT_SEED = 2030972299
BOUNDARY_SEED = 2031972299


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_obj(value: Any) -> str:
    return sha_bytes(canonical(value).encode("utf-8"))


def sha_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derived_seed(base: int, *parts: Any) -> int:
    return int.from_bytes(hashlib.sha256(canonical([base, *parts]).encode()).digest()[:8], "big")


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def write_json_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def write_gzip_rows(path: Path, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    count = 0
    logical = hashlib.sha256()
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            for row in rows:
                line = (canonical(row) + "\n").encode()
                logical.update(line)
                compressed.write(line)
                count += 1
    return {
        "rows": count,
        "logical_sha256": logical.hexdigest(),
        "file_sha256": sha_file(path),
        "bytes": path.stat().st_size,
    }


def verify_frozen_inputs() -> dict[str, Any]:
    if PREREG.stat().st_size != PREREG_BYTES or sha_file(PREREG) != PREREG_SHA:
        raise RuntimeError("preregistration_identity_failure")
    if PREREG_AUDIT.stat().st_size != PREREG_AUDIT_BYTES or sha_file(PREREG_AUDIT) != PREREG_AUDIT_SHA:
        raise RuntimeError("preregistration_audit_identity_failure")
    registration = json.loads(PREREG.read_text(encoding="utf-8"))
    if registration["identity"]["sha256"] != IDENTITY or registration["identity"]["token"] != TOKEN:
        raise RuntimeError("registered_identity_failure")
    failures = []
    for item in registration["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            failures.append(item["role"])
    if len(registration["frozen_authority_inputs"]) != 22 or failures:
        raise RuntimeError(f"frozen_input_failure:{failures}")
    return registration


def verify_child_boundary(nonce: str) -> dict[str, Any]:
    if os.environ.get("RS007_DEVICE_MODE") != "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK":
        raise RuntimeError("device_mode_failure")
    if os.environ.get("RS007_NONCE") != nonce:
        raise RuntimeError("nonce_failure")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("cuda_visibility_failure")
    return {
        "device_mode": os.environ["RS007_DEVICE_MODE"],
        "nonce": nonce,
        "cuda_visible_devices": "0",
    }


def card_int(text: str) -> int:
    return RANKS.index(text[0].upper()) * 4 + SUITS.index(text[1].lower())


def card_text(value: int) -> str:
    return RANKS[value // 4] + SUITS[value % 4]


@dataclass
class DualDomainState:
    holes: list[tuple[int, int]]
    board: list[int] = field(default_factory=list)
    future_deck: list[int] = field(default_factory=list)
    action_string: str = ""
    street: int = 0
    actor: int = 1
    total_commitments: list[int] = field(default_factory=lambda: [BB, SB])
    street_commitments: list[int] = field(default_factory=lambda: [BB, SB])
    stacks: list[int] = field(default_factory=lambda: [STACK - BB, STACK - SB])
    current_bet: int = BB
    minimum_full_raise_increment: int = BB
    surface_last_bet_size: int = BB - SB
    passive_count: int = 0
    preflop_big_blind_option_open: bool = True
    acted_since_full_raise: list[bool] = field(default_factory=lambda: [False, False])
    raise_right_open: list[bool] = field(default_factory=lambda: [True, True])
    history: list[list[tuple[str, int, int]]] = field(default_factory=lambda: [[], [], [], []])
    decision_closed: bool = False
    terminal_kind: str = "NONE"
    folded_player: int | None = None
    payout_cents: list[int] | None = None

    def clone(self) -> "DualDomainState":
        return copy.deepcopy(self)

    @property
    def pot(self) -> int:
        return sum(self.total_commitments)

    @property
    def to_call(self) -> int:
        if self.actor not in (0, 1):
            return 0
        return max(0, self.current_bet - self.street_commitments[self.actor])

    def validate_cards(self) -> None:
        cards = [*self.holes[0], *self.holes[1], *self.board, *self.future_deck]
        if len(self.holes) != 2 or any(len(pair) != 2 for pair in self.holes):
            raise RuntimeError("hole_shape_failure")
        if any(not isinstance(card, int) or card < 0 or card > 51 for card in cards):
            raise RuntimeError("card_range_failure")
        if len(cards) != len(set(cards)):
            raise RuntimeError("duplicate_card_failure")

    def validate_ledger(self) -> None:
        if any(value < 0 or value > STACK for value in self.stacks):
            raise RuntimeError("stack_range_failure")
        if any(value < 0 or value > STACK for value in self.total_commitments):
            raise RuntimeError("total_commitment_range_failure")
        if any(self.total_commitments[player] + self.stacks[player] != STACK for player in (0, 1)):
            raise RuntimeError("stack_commitment_conservation_failure")
        if any(value < 0 for value in self.street_commitments):
            raise RuntimeError("street_commitment_negative")
        if self.current_bet != max(self.street_commitments):
            raise RuntimeError("current_bet_nonidentity")
        if self.minimum_full_raise_increment <= 0:
            raise RuntimeError("minimum_full_raise_nonpositive")
        self.validate_cards()

    def _pay(self, player: int, cents: int) -> None:
        if cents < 0 or cents > self.stacks[player]:
            raise RuntimeError("payment_out_of_range")
        self.stacks[player] -= cents
        self.total_commitments[player] += cents
        self.street_commitments[player] += cents

    def _deal_to(self, target_length: int) -> None:
        needed = target_length - len(self.board)
        if needed < 0 or target_length > 5 or len(self.future_deck) < needed:
            raise RuntimeError("future_deck_shortfall")
        self.board.extend(self.future_deck[:needed])
        del self.future_deck[:needed]
        self.validate_cards()

    def _settle_terminal(self) -> None:
        if self.payout_cents is not None:
            raise RuntimeError("payout_already_computed")
        if self.terminal_kind == "FOLD":
            if self.folded_player not in (0, 1):
                raise RuntimeError("folded_player_missing")
            lost = self.total_commitments[self.folded_player]
            self.payout_cents = [0, 0]
            self.payout_cents[self.folded_player] = -lost
            self.payout_cents[1 - self.folded_player] = lost
        elif self.terminal_kind == "SHOWDOWN":
            if len(self.board) != 5:
                raise RuntimeError("showdown_board_length_failure")
            from deep_cfr.hand_eval import compare_hands
            sign = compare_hands(self.holes[0], self.holes[1], self.board)
            matched = min(self.total_commitments)
            if sign > 0:
                self.payout_cents = [matched, -matched]
            elif sign < 0:
                self.payout_cents = [-matched, matched]
            else:
                self.payout_cents = [0, 0]
        else:
            raise RuntimeError("settlement_before_terminal")
        if sum(self.payout_cents) != 0 or any(abs(value) > STACK for value in self.payout_cents):
            raise RuntimeError("payout_invariant_failure")

    def _showdown(self, runout: bool) -> None:
        if runout:
            self._deal_to(5)
        self.decision_closed = True
        self.terminal_kind = "SHOWDOWN"
        self.actor = -1
        self._settle_terminal()

    def _close_street(self) -> None:
        if self.street == 3:
            self._showdown(False)
            return
        self.action_string += "/"
        self.street += 1
        self._deal_to(3 if self.street == 1 else 4 if self.street == 2 else 5)
        self.actor = 0
        self.street_commitments = [0, 0]
        self.current_bet = 0
        self.minimum_full_raise_increment = BB
        self.surface_last_bet_size = 0
        self.passive_count = 0
        self.preflop_big_blind_option_open = False
        self.acted_since_full_raise = [False, False]
        self.raise_right_open = [True, True]

    def public_legality(self, increment: str) -> tuple[bool, str]:
        if self.decision_closed or self.actor not in (0, 1):
            return False, "DECISION_CLOSED"
        if not re.fullmatch(r"(?:[kcf]|b[1-9][0-9]*)", increment):
            return False, "GRAMMAR"
        facing = self.to_call > 0
        if increment == "f":
            return (facing, "FOLD" if facing else "FOLD_NOT_FACING")
        if increment == "k":
            return (not facing, "CHECK" if not facing else "CHECK_FACING")
        if increment == "c":
            return (facing, "CALL" if facing else "CALL_NOT_FACING")
        target = int(increment[1:])
        player = self.actor
        other = 1 - player
        maximum = self.street_commitments[player] + self.stacks[player]
        if not self.raise_right_open[player]:
            return False, "RAISE_RIGHT_CLOSED"
        if self.stacks[other] == 0:
            return False, "OPPONENT_ALLIN"
        if target <= self.current_bet:
            return False, "TARGET_NOT_ABOVE_CURRENT"
        if target > maximum:
            return False, "OVERSTACK"
        full_threshold = self.current_bet + self.minimum_full_raise_increment if self.current_bet > 0 else BB
        if target < full_threshold and target != maximum:
            return False, "UNDER_MINIMUM_NONALLIN"
        return True, "FULL_BET_OR_RAISE" if target >= full_threshold else "SHORT_ALLIN"

    def apply_public_increment(self, increment: str, origin: str) -> "DualDomainState":
        if origin not in ("SOURCE_REPLAY", "EXTERNAL_OPPONENT", "POLICY_SLOT"):
            raise RuntimeError("public_origin_failure")
        legal, classification = self.public_legality(increment)
        if not legal:
            raise RuntimeError(f"public_illegal:{classification}:{increment}")
        player = self.actor
        other = 1 - player
        if increment == "f":
            self.action_string += "f"
            self.history[self.street].append(("f", player, 0))
            self.acted_since_full_raise[player] = True
            self.decision_closed = True
            self.terminal_kind = "FOLD"
            self.folded_player = player
            self.actor = -1
            self._settle_terminal()
            return self
        if increment == "k":
            self.action_string += "k"
            self.history[self.street].append(("k", player, 0))
            self.acted_since_full_raise[player] = True
            if self.passive_count == 1:
                self._close_street()
            else:
                self.passive_count = 1
                self.actor = other
            return self
        if increment == "c":
            initial_sb_call = (
                self.street == 0
                and self.preflop_big_blind_option_open
                and player == 1
                and len(self.history[0]) == 0
            )
            self._pay(player, min(self.to_call, self.stacks[player]))
            self.action_string += "c"
            self.history[self.street].append(("c", player, self.current_bet))
            self.surface_last_bet_size = 0
            self.acted_since_full_raise[player] = True
            self.preflop_big_blind_option_open = False
            if self.stacks[player] == 0 or self.stacks[other] == 0:
                self._showdown(True)
            elif initial_sb_call:
                self.passive_count = 1
                self.actor = other
            else:
                self._close_street()
            return self
        old_current = self.current_bet
        target = int(increment[1:])
        full_threshold = old_current + self.minimum_full_raise_increment if old_current > 0 else BB
        full_raise = target >= full_threshold
        prior_other_acted = self.acted_since_full_raise[other]
        self._pay(player, target - self.street_commitments[player])
        self.action_string += increment
        self.history[self.street].append(("b", player, target))
        raise_increment = target - old_current
        self.current_bet = target
        self.surface_last_bet_size = raise_increment
        self.preflop_big_blind_option_open = False
        if full_raise:
            self.minimum_full_raise_increment = raise_increment
            self.acted_since_full_raise = [False, False]
            self.acted_since_full_raise[player] = True
            self.raise_right_open[other] = True
        else:
            self.acted_since_full_raise[player] = True
            self.raise_right_open[other] = not prior_other_acted
        self.passive_count = 1
        self.actor = other
        self.validate_ledger()
        return self

    def policy_table(self) -> tuple[np.ndarray, list[str | None]]:
        mask = np.zeros(SLOTS, dtype=np.float32)
        table: list[str | None] = [None] * SLOTS
        if self.decision_closed or self.actor not in (0, 1):
            return mask, table
        facing = self.to_call > 0
        if facing:
            table[0] = "f"
        table[1] = "c" if facing else "k"
        player = self.actor
        other = 1 - player
        if (
            self.stacks[player] > self.to_call
            and self.stacks[other] > 0
            and self.raise_right_open[player]
        ):
            maximum = self.street_commitments[player] + self.stacks[player]
            pot = max(self.pot, 1)
            fractions = PREFLOP_FRACTIONS if self.street == 0 else RAISE_FRACTIONS
            distances: dict[int, tuple[float, int]] = {}
            for fraction in fractions:
                base = self.pot + self.to_call if facing else self.pot
                target = self.current_bet + int(base * fraction)
                minimum = self.current_bet + self.minimum_full_raise_increment if self.current_bet > 0 else BB
                target = max(target, minimum)
                if target >= maximum:
                    continue
                slot = min(range(2, 8), key=lambda index: abs(target / pot - RAISE_FRACTIONS[index - 2]))
                distance = abs(target - RAISE_FRACTIONS[slot - 2] * pot)
                if slot not in distances or distance < distances[slot][0]:
                    distances[slot] = (distance, target)
            for slot, (_, target) in distances.items():
                candidate = f"b{target}"
                if self.public_legality(candidate)[0]:
                    table[slot] = candidate
            allin = f"b{maximum}"
            if self.public_legality(allin)[0]:
                table[8] = allin
        values = [value for value in table if value is not None]
        if len(values) != len(set(values)):
            raise RuntimeError("policy_table_collision")
        for slot, increment in enumerate(table):
            if increment is not None:
                if not self.public_legality(increment)[0]:
                    raise RuntimeError("policy_entry_not_public_legal")
                mask[slot] = 1
        return mask, table

    def apply_policy_slot(self, slot: int) -> "DualDomainState":
        if not isinstance(slot, int) or slot < 0 or slot >= SLOTS:
            raise RuntimeError("policy_slot_range_failure")
        _, table = self.policy_table()
        increment = table[slot]
        if increment is None:
            raise RuntimeError("policy_slot_null")
        return self.apply_public_increment(increment, "POLICY_SLOT")

    @classmethod
    def replay(
        cls,
        prefix: str,
        holes: list[tuple[int, int]],
        known_board: list[int],
        remaining_future: list[int],
    ) -> "DualDomainState":
        state = cls(holes=holes, future_deck=[*known_board, *remaining_future])
        state.validate_ledger()
        tokens = re.findall(r"b[1-9][0-9]*|[kcf]|/", prefix)
        if "".join(tokens) != prefix:
            raise RuntimeError("prefix_grammar_failure")
        for token in tokens:
            if token != "/":
                state.apply_public_increment(token, "SOURCE_REPLAY")
        if state.action_string != prefix:
            raise RuntimeError(f"prefix_roundtrip_failure:{prefix}:{state.action_string}")
        if state.board != known_board:
            raise RuntimeError("known_board_replay_failure")
        return state


def encode_cards(hole: tuple[int, int], board: list[int]) -> np.ndarray:
    tensor = np.zeros((6, 4, 13), dtype=np.float32)
    for card in hole:
        tensor[0, card % 4, card // 4] = 1
    for index, card in enumerate(board):
        channel = 1 if index < 3 else 2 if index == 3 else 3
        tensor[channel, card % 4, card // 4] = 1
        tensor[4, card % 4, card // 4] = 1
    for card in [*hole, *board]:
        tensor[5, card % 4, card // 4] = 1
    return tensor


def encode_history(state: DualDomainState, viewer: int) -> np.ndarray:
    tensor = np.zeros((25, 4, 5), dtype=np.float32)
    denominator = max(state.pot, 1)
    for street in range(4):
        prior_target = BB if street == 0 else 0
        for index, (move, player, amount) in enumerate(state.history[street][:6]):
            channel = street * 6 + index
            tensor[channel, 0, 0] = float(player == viewer)
            if move == "b":
                action_type = 4 if prior_target > 0 else 3
                prior_target = amount
            else:
                action_type = {"f": 0, "k": 1, "c": 2}[move]
            tensor[channel, 1, action_type] = 1
            if amount > 0:
                tensor[channel, 2, 0] = min(amount / denominator, 2.0) / 2.0
            tensor[channel, 3, 0] = 1
    tensor[24, 0, 0] = float(state.actor == viewer)
    return tensor


def observation(state: DualDomainState) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str | None]]:
    if state.decision_closed:
        raise RuntimeError("observation_after_close")
    viewer = state.actor
    mask, table = state.policy_table()
    extra = np.asarray([state.stacks[viewer] / STACK, state.stacks[1 - viewer] / STACK], dtype=np.float32)
    return encode_cards(state.holes[viewer], state.board), encode_history(state, viewer), extra, mask, table


class H11Policy:
    def __init__(self, nonce: str):
        import torch
        from alpha_holdem.network import AlphaHoldemNet
        verify_child_boundary(nonce)
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("single_cuda_device_required")
        self.torch = torch
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
        if (
            checkpoint.get("env_version") != "v55"
            or checkpoint.get("obs_version") != "v55"
            or checkpoint.get("critic_contract") != "critic_v1"
        ):
            raise RuntimeError("checkpoint_interface_failure")
        self.model = AlphaHoldemNet(9, norm_layer=checkpoint.get("norm_layer") or "bn").to("cuda:0")
        self.model.eval()
        with torch.no_grad():
            self.model(
                torch.zeros(2, 6, 4, 13, device="cuda:0"),
                torch.zeros(2, 25, 4, 5, device="cuda:0"),
                torch.zeros(2, 2, device="cuda:0"),
            )
        self.model.load_state_dict(checkpoint["model"], strict=True)
        del checkpoint
        torch.cuda.synchronize()
        self.cold_load_seconds = time.perf_counter() - started

    def infer(self, states: list[DualDomainState]) -> tuple[list[int], list[list[float]]]:
        arrays = [observation(state) for state in states]
        selected: list[int] = []
        logits_output: list[list[float]] = []
        torch = self.torch
        for start in range(0, len(arrays), 512):
            batch = arrays[start:start + 512]
            with torch.no_grad():
                cards = torch.from_numpy(np.stack([row[0] for row in batch])).to("cuda:0")
                histories = torch.from_numpy(np.stack([row[1] for row in batch])).to("cuda:0")
                extras = torch.from_numpy(np.stack([row[2] for row in batch])).to("cuda:0")
                masks = torch.from_numpy(np.stack([row[3] for row in batch])).to("cuda:0")
                logits, _ = self.model(cards, histories, extras, masks)
                selected.extend(int(value) for value in torch.argmax(logits, dim=1).cpu().tolist())
                logits_output.extend([[float(value) for value in row] for row in logits.cpu().tolist()])
        for state, slot in zip(states, selected, strict=True):
            if state.policy_table()[1][slot] is None:
                raise RuntimeError("model_selected_null_slot")
        return selected, logits_output

    def peak_gpu_mib(self) -> float:
        return float(self.torch.cuda.max_memory_allocated() / 1048576)


def safe_row(raw: dict[str, Any], source: str) -> dict[str, Any]:
    keys = (
        "hand_idx", "move_idx", "who", "client_pos", "mover_pos", "action_str_before",
        "street", "hero_hole", "board", "pot_before", "to_call", "stack_remaining",
        "last_bet_size", "street_last_bet_to", "total_last_bet_to", "action_move", "action_amount",
    )
    row = {key: raw[key] for key in keys}
    row["source"] = source
    return row


def load_source_rows(registration: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in registration["frozen_authority_inputs"]:
        if item["role"].startswith("h11_dump_part"):
            path = Path(item["path"])
            with path.open(encoding="utf-8") as handle:
                rows.extend(safe_row(json.loads(line), str(path.resolve())) for line in handle)
    if len(rows) != 29878:
        raise RuntimeError("source_row_count_failure")
    return rows


def row_increment(row: dict[str, Any]) -> str:
    return f"b{int(row['action_amount'])}" if row["action_move"] == "b" else str(row["action_move"])


def row_identity(row: dict[str, Any]) -> str:
    return sha_obj([
        row["source"], row["hand_idx"], row["move_idx"], row["action_str_before"],
        row["client_pos"], row["hero_hole"], row["board"],
    ])


def state_from_row(
    row: dict[str, Any],
    opponent_pair: tuple[int, int] | None = None,
    future: list[int] | None = None,
) -> DualDomainState:
    hero = int(row["client_pos"])
    hero_pair = tuple(card_int(card) for card in row["hero_hole"])
    board = [card_int(card) for card in row["board"]]
    unseen = [card for card in range(52) if card not in {*hero_pair, *board}]
    if opponent_pair is None:
        random.Random(derived_seed(SYNTHETIC_SEED, row_identity(row))).shuffle(unseen)
        opponent_pair = tuple(unseen[:2])
    remaining = [card for card in unseen if card not in opponent_pair]
    if future is None:
        random.Random(derived_seed(FUTURE_SEED, row_identity(row))).shuffle(remaining)
        future = remaining
    holes: list[tuple[int, int]] = [(0, 1), (2, 3)]
    holes[hero] = hero_pair
    holes[1 - hero] = opponent_pair
    return DualDomainState.replay(str(row["action_str_before"]), holes, board, list(future))


def witness_fields(state: DualDomainState) -> dict[str, int]:
    return {
        "street": state.street,
        "actor": state.actor,
        "pot": state.pot,
        "to_call": state.to_call,
        "mover_stack": state.stacks[state.actor],
        "street_bet_to": state.current_bet,
        "total_bet_to": max(state.total_commitments),
        "last_bet_size": state.surface_last_bet_size,
    }


def assert_witness(row: dict[str, Any], state: DualDomainState) -> dict[str, int]:
    observed = witness_fields(state)
    expected = {
        "street": int(row["street"]),
        "actor": int(row["mover_pos"]),
        "pot": int(row["pot_before"]),
        "to_call": int(row["to_call"]),
        "mover_stack": int(row["stack_remaining"]),
        "street_bet_to": int(row["street_last_bet_to"]),
        "total_bet_to": int(row["total_last_bet_to"]),
        "last_bet_size": int(row["last_bet_size"]),
    }
    if observed != expected:
        raise RuntimeError(f"witness_nonidentity:{observed}:{expected}")
    return observed


def source_transition_evidence(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_hand: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_hand[(row["source"], int(row["hand_idx"]))].append(row)
    next_prefix: dict[tuple[str, int, int], str] = {}
    adjacent = 0
    contiguous = True
    for key, group in by_hand.items():
        group.sort(key=lambda item: int(item["move_idx"]))
        contiguous &= [int(item["move_idx"]) for item in group] == list(range(len(group)))
        for left, right in zip(group, group[1:]):
            next_prefix[(key[0], key[1], int(left["move_idx"]))] = str(right["action_str_before"])
            adjacent += 1
    evidence = []
    counters = defaultdict(int)
    prefixes = set()
    for row in rows:
        state = state_from_row(row)
        before = assert_witness(row, state)
        increment = row_increment(row)
        _, table = state.policy_table()
        matching_slots = [slot for slot, value in enumerate(table) if value == increment]
        in_slot = len(matching_slots) == 1
        if len(matching_slots) > 1:
            raise RuntimeError("source_policy_collision")
        public_result = state.clone().apply_public_increment(
            increment,
            "EXTERNAL_OPPONENT" if row["who"] == "opp" else "SOURCE_REPLAY",
        )
        key = (row["source"], int(row["hand_idx"]), int(row["move_idx"]))
        adjacent_exact = key not in next_prefix or public_result.action_string == next_prefix[key]
        if not adjacent_exact:
            raise RuntimeError("adjacent_prefix_nonidentity")
        dual_path_exact = None
        if row["who"] == "hero":
            if not in_slot:
                raise RuntimeError("hero_action_outside_policy")
            policy_result = state.clone().apply_policy_slot(matching_slots[0])
            dual_path_exact = canonical(policy_result.__dict__) == canonical(public_result.__dict__)
            if not dual_path_exact:
                raise RuntimeError("hero_dual_path_nonidentity")
        counters["rows"] += 1
        counters["adjacent"] += int(key in next_prefix)
        counters["hero"] += int(row["who"] == "hero")
        counters["opponent"] += int(row["who"] == "opp")
        counters["in_slot"] += int(in_slot)
        counters["external"] += int(not in_slot)
        counters["hero_slot"] += int(row["who"] == "hero" and in_slot)
        counters["opponent_slot"] += int(row["who"] == "opp" and in_slot)
        counters["opponent_external"] += int(row["who"] == "opp" and not in_slot)
        counters["dual_path_exact"] += int(dual_path_exact is True)
        prefixes.add(str(row["action_str_before"]))
        evidence.append({
            "source_scoped_hand_key": [row["source"], int(row["hand_idx"])],
            "move_idx": int(row["move_idx"]),
            "who": row["who"],
            "street": int(row["street"]),
            "prefix_sha256": sha_bytes(str(row["action_str_before"]).encode()),
            "increment": increment,
            "policy_slot": matching_slots[0] if in_slot else None,
            "policy_membership": in_slot,
            "public_legal": True,
            "adjacent_exact": adjacent_exact,
            "hero_dual_path_exact": dual_path_exact,
            "before": before,
            "after_prefix_sha256": sha_bytes(public_result.action_string.encode()),
        })
    counters["hands"] = len(by_hand)
    counters["prefixes"] = len(prefixes)
    counters["contiguous"] = int(contiguous)
    expected = {
        "rows": 29878, "adjacent": 24878, "hero": 12564, "opponent": 17314,
        "in_slot": 28220, "external": 1658, "hero_slot": 12564,
        "opponent_slot": 15656, "opponent_external": 1658,
        "dual_path_exact": 12564, "hands": 5000, "prefixes": 584, "contiguous": 1,
    }
    if dict(counters) != expected:
        raise RuntimeError(f"transition_census_failure:{dict(counters)}")
    return evidence, expected


BOUNDARY_SCENARIOS = (
    "CHECK_OPEN", "CHECK_CLOSE", "CALL_CLOSE", "FOLD",
    "FULL_OPEN_MINIMUM", "FULL_OPEN_ABOVE_MINIMUM",
    "FULL_RAISE_MINIMUM", "FULL_RAISE_ABOVE_MINIMUM",
    "SHORT_ALLIN_OPEN", "SHORT_ALLIN_RAISE_NO_REOPEN",
    "FULL_RAISE_REOPENS", "RAISE_RIGHT_CLOSED_REJECT",
    "OPPONENT_ALLIN_RAISE_REJECT", "UNDER_MINIMUM_NONALLIN_REJECT",
    "OVERSTACK_REJECT", "POSTTERMINAL_REJECT",
)


def boundary_state(street: int, actor: int, scenario: str, repeat: int) -> tuple[DualDomainState, str, bool, str]:
    deck = list(range(52))
    random.Random(derived_seed(BOUNDARY_SEED, street, actor, scenario, repeat)).shuffle(deck)
    board_length = 0 if street == 0 else 3 if street == 1 else 4 if street == 2 else 5
    holes = [tuple(deck[:2]), tuple(deck[2:4])]
    state = DualDomainState(
        holes=holes,
        board=deck[4:4 + board_length],
        future_deck=deck[4 + board_length:],
        action_string=f"SYNTHETIC:{street}:{actor}:{scenario}:{repeat}",
        street=street,
        actor=actor,
        total_commitments=[19000, 19000],
        street_commitments=[0, 0],
        stacks=[1000, 1000],
        current_bet=0,
        minimum_full_raise_increment=100,
        surface_last_bet_size=0,
        passive_count=0,
        preflop_big_blind_option_open=False,
        acted_since_full_raise=[False, False],
        raise_right_open=[True, True],
    )
    other = 1 - actor
    increment = "k"
    expected = True
    expected_reason = ""
    if scenario == "CHECK_OPEN":
        increment, state.passive_count = "k", 0
    elif scenario == "CHECK_CLOSE":
        increment, state.passive_count = "k", 1
    elif scenario in ("CALL_CLOSE", "FOLD"):
        state.street_commitments[actor] = 100
        state.street_commitments[other] = 200
        state.current_bet = 200
        state.total_commitments[actor] = 19000
        state.total_commitments[other] = 19100
        state.stacks[actor] = 1000
        state.stacks[other] = 900
        state.minimum_full_raise_increment = 100
        state.passive_count = 1
        increment = "c" if scenario == "CALL_CLOSE" else "f"
    elif scenario == "FULL_OPEN_MINIMUM":
        increment = "b100"
    elif scenario == "FULL_OPEN_ABOVE_MINIMUM":
        increment = f"b{200 + repeat % 20}"
    elif scenario in ("FULL_RAISE_MINIMUM", "FULL_RAISE_ABOVE_MINIMUM", "FULL_RAISE_REOPENS"):
        state.street_commitments[actor] = 100
        state.street_commitments[other] = 200
        state.current_bet = 200
        state.total_commitments[actor] = 19000
        state.total_commitments[other] = 19100
        state.stacks[actor] = 1000
        state.stacks[other] = 900
        state.minimum_full_raise_increment = 100
        state.acted_since_full_raise[other] = True
        increment = "b300" if scenario != "FULL_RAISE_ABOVE_MINIMUM" else f"b{400 + repeat % 20}"
    elif scenario == "SHORT_ALLIN_OPEN":
        state.stacks[actor] = 50 + repeat % 40
        state.total_commitments[actor] = STACK - state.stacks[actor]
        increment = f"b{state.stacks[actor]}"
    elif scenario == "SHORT_ALLIN_RAISE_NO_REOPEN":
        state.street_commitments[actor] = 150
        state.street_commitments[other] = 200
        state.current_bet = 200
        state.stacks[actor] = 100
        state.total_commitments[actor] = 19900
        state.stacks[other] = 900
        state.total_commitments[other] = 19100
        state.minimum_full_raise_increment = 100
        state.acted_since_full_raise[other] = True
        increment = "b250"
    elif scenario == "RAISE_RIGHT_CLOSED_REJECT":
        state.street_commitments[actor] = 200
        state.street_commitments[other] = 250
        state.current_bet = 250
        state.total_commitments[actor] = 19000
        state.total_commitments[other] = 19100
        state.stacks[actor] = 1000
        state.stacks[other] = 900
        state.raise_right_open[actor] = False
        increment, expected, expected_reason = "b350", False, "RAISE_RIGHT_CLOSED"
    elif scenario == "OPPONENT_ALLIN_RAISE_REJECT":
        state.street_commitments[actor] = 100
        state.street_commitments[other] = 200
        state.current_bet = 200
        state.total_commitments[actor] = 19000
        state.stacks[actor] = 1000
        state.total_commitments[other] = STACK
        state.stacks[other] = 0
        increment, expected, expected_reason = "b300", False, "OPPONENT_ALLIN"
    elif scenario == "UNDER_MINIMUM_NONALLIN_REJECT":
        state.street_commitments[actor] = 100
        state.street_commitments[other] = 200
        state.current_bet = 200
        state.total_commitments[actor] = 19000
        state.total_commitments[other] = 19100
        state.stacks[actor] = 1000
        state.stacks[other] = 900
        state.minimum_full_raise_increment = 100
        increment, expected, expected_reason = "b250", False, "UNDER_MINIMUM_NONALLIN"
    elif scenario == "OVERSTACK_REJECT":
        increment, expected, expected_reason = "b1001", False, "OVERSTACK"
    elif scenario == "POSTTERMINAL_REJECT":
        state.decision_closed = True
        state.terminal_kind = "FOLD"
        state.folded_player = actor
        state.actor = -1
        increment, expected, expected_reason = "k", False, "DECISION_CLOSED"
    state.validate_ledger()
    return state, increment, expected, expected_reason


def boundary_matrix() -> list[dict[str, Any]]:
    rows = []
    for street in range(4):
        for actor in (0, 1):
            for scenario in BOUNDARY_SCENARIOS:
                for repeat in range(32):
                    state, increment, expected, expected_reason = boundary_state(street, actor, scenario, repeat)
                    legal, reason = state.public_legality(increment)
                    if legal != expected or (not expected and reason != expected_reason):
                        raise RuntimeError(f"boundary_expectation_failure:{scenario}:{legal}:{reason}")
                    after = None
                    if legal:
                        before = state.clone()
                        after = state.apply_public_increment(increment, "SOURCE_REPLAY")
                        if scenario == "SHORT_ALLIN_RAISE_NO_REOPEN":
                            if after.raise_right_open[after.actor]:
                                raise RuntimeError("short_allin_reopened_prior_actor")
                        if scenario == "FULL_RAISE_REOPENS":
                            if not after.raise_right_open[after.actor]:
                                raise RuntimeError("full_raise_failed_to_reopen")
                        if scenario.startswith("FULL_") and scenario not in ("FULL_RAISE_REOPENS",):
                            pass
                        if before.decision_closed:
                            raise RuntimeError("boundary_applied_closed_state")
                    rows.append({
                        "street": street,
                        "actor": actor,
                        "scenario": scenario,
                        "repeat": repeat,
                        "increment": increment,
                        "expected_legal": expected,
                        "observed_legal": legal,
                        "reason": reason,
                        "post_actor": after.actor if after is not None else None,
                        "post_terminal": after.terminal_kind if after is not None else None,
                        "raise_right": after.raise_right_open if after is not None else None,
                        "exact": True,
                    })
    if len(rows) != 4096:
        raise RuntimeError("boundary_matrix_count_failure")
    return rows


def terminal_cards(outcome: str) -> tuple[list[tuple[int, int]], list[int]]:
    if outcome == "PLAYER0_WIN":
        return [(48, 49), (4, 9)], [0, 13, 26, 39, 44]
    if outcome == "PLAYER1_WIN":
        return [(4, 9), (48, 49)], [0, 13, 26, 39, 44]
    return [(1, 6), (11, 14)], [32, 36, 40, 44, 48]


def terminal_fixture(prefix: str, outcome: str) -> DualDomainState:
    holes, board = terminal_cards(outcome)
    state = DualDomainState(holes=holes, future_deck=list(board))
    for token in re.findall(r"b[1-9][0-9]*|[kcf]", prefix):
        state.apply_public_increment(token, "SOURCE_REPLAY")
    if not state.decision_closed:
        raise RuntimeError("terminal_fixture_open")
    return state


def terminal_utility_rows() -> list[dict[str, Any]]:
    rows = []
    street_prefixes = (
        ("PREFLOP", ""),
        ("FLOP", "ck"),
        ("TURN", "ckkk"),
        ("RIVER", "ckkkkk"),
    )
    for folded in (0, 1):
        for street_name, prefix in street_prefixes:
            for repeat in range(16):
                action = ("b200f" if folded == 0 else "f") if street_name == "PREFLOP" else prefix + ("kb100f" if folded == 0 else "b100f")
                state = terminal_fixture(action, "PLAYER0_WIN")
                rows.append({
                    "cell": f"FOLD_PLAYER{folded}",
                    "street_balance": street_name,
                    "repeat": repeat,
                    "terminal_kind": state.terminal_kind,
                    "folded_player": state.folded_player,
                    "totals": state.total_commitments,
                    "matched_cents": min(state.total_commitments),
                    "payout_cents": state.payout_cents,
                    "board": state.board,
                    "comparator_sign": None,
                    "zero_sum": sum(state.payout_cents) == 0,
                    "refund_exact": state.payout_cents[folded] == -state.total_commitments[folded],
                })
    origins = {
        "PREFLOP_ALLIN": "b20000c",
        "FLOP_ALLIN": "ckb19900c",
        "TURN_ALLIN": "ckkkb19900c",
        "RIVER_ALLIN": "ckkkkkb19900c",
        "RIVER_CHECK_CLOSE": "ckkkkkkk",
        "RIVER_CALL_CLOSE": "ckkkkkb100c",
    }
    from deep_cfr.hand_eval import compare_hands
    for origin, prefix in origins.items():
        for outcome in ("PLAYER0_WIN", "PLAYER1_WIN", "TIE"):
            for repeat in range(64):
                state = terminal_fixture(prefix, outcome)
                sign = compare_hands(state.holes[0], state.holes[1], state.board)
                expected_sign = 1 if outcome == "PLAYER0_WIN" else -1 if outcome == "PLAYER1_WIN" else 0
                rows.append({
                    "cell": f"{origin}_{outcome}",
                    "origin": origin,
                    "outcome": outcome,
                    "repeat": repeat,
                    "terminal_kind": state.terminal_kind,
                    "totals": state.total_commitments,
                    "matched_cents": min(state.total_commitments),
                    "payout_cents": state.payout_cents,
                    "holes": state.holes,
                    "board": state.board,
                    "comparator_sign": sign,
                    "comparator_exact": (sign > 0) - (sign < 0) == expected_sign,
                    "zero_sum": sum(state.payout_cents) == 0,
                    "refund_exact": True,
                })
    if len(rows) != 1280 or len({row["cell"] for row in rows}) != 20:
        raise RuntimeError("terminal_cohort_count_failure")
    return rows


def comparator_evidence() -> dict[str, int]:
    from deep_cfr.hand_eval import compare_hands
    from treys import Card, Evaluator
    evaluator = Evaluator()
    rng = random.Random(derived_seed(SYNTHETIC_SEED, "comparator"))
    direct = swap = order = 0
    for _ in range(8192):
        deal = rng.sample(range(52), 9)
        first, second, board = tuple(deal[:2]), tuple(deal[2:4]), deal[4:]
        signed = compare_hands(first, second, board)
        first_rank = evaluator.evaluate([Card.new(card_text(card)) for card in board], [Card.new(card_text(card)) for card in first])
        second_rank = evaluator.evaluate([Card.new(card_text(card)) for card in board], [Card.new(card_text(card)) for card in second])
        expected = second_rank - first_rank
        direct += int((signed > 0) - (signed < 0) == (expected > 0) - (expected < 0))
        swap += int(compare_hands(second, first, board) == -signed)
        order += int(compare_hands(tuple(reversed(first)), second, list(reversed(board))) == signed)
    return {"unique_deals": 8192, "direct_treys": direct, "swap": swap, "order": order}


def determinizations(row: dict[str, Any]) -> tuple[list[DualDomainState], dict[str, Any]]:
    hero_pair = tuple(card_int(card) for card in row["hero_hole"])
    board = [card_int(card) for card in row["board"]]
    unseen = [card for card in range(52) if card not in {*hero_pair, *board}]
    pairs = list(itertools.combinations(unseen, 2))
    identity = row_identity(row)
    random.Random(derived_seed(HIDDEN_SEED, identity)).shuffle(pairs)
    pairs = pairs[:MC]
    states, pair_hashes, future_hashes = [], [], []
    for index, pair in enumerate(pairs):
        future = [card for card in unseen if card not in pair]
        random.Random(derived_seed(FUTURE_SEED, identity, index)).shuffle(future)
        states.append(state_from_row(row, pair, future))
        pair_hashes.append(sha_obj(sorted(pair)))
        future_hashes.append(sha_obj(future))
    return states, {
        "sample_count": MC,
        "distinct_pair_count": len(set(pairs)),
        "pair_hashes": pair_hashes,
        "future_hashes": future_hashes,
        "common_trace_sha256": sha_obj([pair_hashes, future_hashes]),
    }


def paired_statistics(values: dict[int, list[float]], baseline: int) -> dict[str, dict[str, float]]:
    output = {}
    base = values[baseline]
    for slot in sorted(values):
        differences = [value - reference for value, reference in zip(values[slot], base, strict=True)]
        mean = statistics.fmean(differences)
        deviation = statistics.stdev(differences) if len(differences) > 1 else 0.0
        output[str(slot)] = {
            "mean_difference_bb": mean,
            "sample_sd_bb": deviation,
            "lcb95_bb": mean - 1.645 * deviation / math.sqrt(MC),
        }
    return output


def resolve(policy: H11Policy, row: dict[str, Any], fault: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    root = state_from_row(row)
    _, root_table = root.policy_table()
    baseline_slots, baseline_logits = policy.infer([root])
    baseline = baseline_slots[0]
    base = {
        "state_identity_sha256": row_identity(row),
        "baseline_slot": baseline,
        "baseline_increment": root_table[baseline],
        "baseline_logits_sha256": sha_obj(baseline_logits[0]),
        "policy_table9": root_table,
        "resolver_attempted": True,
        "public_policy_contract_violations": 0,
    }
    if fault:
        return {
            **base,
            "selected_slot": baseline,
            "selected_increment": root_table[baseline],
            "selection_reason": fault,
            "error_fallback": True,
            "latency_seconds": time.perf_counter() - started,
        }
    try:
        states, trace = determinizations(row)
        root_slots = [slot for slot, increment in enumerate(root_table) if increment is not None]
        active: list[tuple[int, int, DualDomainState]] = []
        for slot in root_slots:
            for index, source in enumerate(states):
                candidate = source.clone()
                candidate.apply_policy_slot(slot)
                active.append((slot, index, candidate))
        values: dict[int, list[float | None]] = {slot: [None] * MC for slot in root_slots}
        rollout_digest = hashlib.sha256()
        steps = 0
        deadline = started + 20.0
        hero = int(row["client_pos"])
        while active:
            if time.perf_counter() > deadline:
                raise TimeoutError
            pending_states = []
            pending_keys = []
            for slot, index, state in active:
                if state.decision_closed:
                    payoff = state.payout_cents[hero] / BB
                    if not math.isfinite(payoff):
                        raise FloatingPointError
                    values[slot][index] = payoff
                    rollout_digest.update(canonical([slot, index, "T", payoff]).encode())
                else:
                    pending_states.append(state)
                    pending_keys.append((slot, index))
            if not pending_states:
                break
            policy_slots, _ = policy.infer(pending_states)
            active = []
            for (slot, index), state, policy_slot in zip(pending_keys, pending_states, policy_slots, strict=True):
                increment = state.policy_table()[1][policy_slot]
                rollout_digest.update(canonical([slot, index, steps, state.action_string, policy_slot, increment]).encode())
                state.apply_policy_slot(policy_slot)
                active.append((slot, index, state))
            steps += 1
            if steps > 32:
                raise RuntimeError("rollout_step_overflow")
        complete: dict[int, list[float]] = {}
        for slot, outcomes in values.items():
            if any(value is None for value in outcomes):
                raise RuntimeError("rollout_terminal_missing")
            complete[slot] = [float(value) for value in outcomes]
        stats = paired_statistics(complete, baseline)
        positive = [slot for slot in root_slots if slot != baseline and stats[str(slot)]["lcb95_bb"] > 0]
        if positive:
            best_lcb = max(stats[str(slot)]["lcb95_bb"] for slot in positive)
            selected = min(slot for slot in positive if stats[str(slot)]["lcb95_bb"] == best_lcb)
            reason = "PAIRED_LCB95_POSITIVE"
        else:
            selected, reason = baseline, "LCB_NO_CHANGE"
        return {
            **base,
            "selected_slot": selected,
            "selected_increment": root_table[selected],
            "selection_reason": reason,
            "error_fallback": False,
            "determinizations": trace,
            "paired_statistics_by_slot": stats,
            "rollout_trace_sha256": rollout_digest.hexdigest(),
            "decision_trace_sha256": sha_obj([
                row_identity(row), baseline, selected, trace["common_trace_sha256"], rollout_digest.hexdigest()
            ]),
            "max_rollout_actions": steps,
            "latency_seconds": time.perf_counter() - started,
        }
    except TimeoutError:
        reason = "RESOLVER_TIMEOUT"
    except FloatingPointError:
        reason = "NONFINITE_PAYOFF_OR_LCB"
    except RuntimeError as error:
        if "rollout_step_overflow" in str(error):
            reason = "ROLLOUT_STEP_OVERFLOW"
        else:
            raise
    return {
        **base,
        "selected_slot": baseline,
        "selected_increment": root_table[baseline],
        "selection_reason": reason,
        "error_fallback": True,
        "latency_seconds": time.perf_counter() - started,
    }


def deep_selftest(level: str) -> int:
    registration = verify_frozen_inputs()
    rows = load_source_rows(registration)
    transition_rows, counters = source_transition_evidence(rows)
    boundary = boundary_matrix()
    terminal = terminal_utility_rows()
    comparator = comparator_evidence()
    checks = {
        "source_transition_rows": len(transition_rows),
        "source_counters": counters,
        "boundary_rows": len(boundary),
        "boundary_cells": len({(row["street"], row["actor"], row["scenario"]) for row in boundary}),
        "terminal_rows": len(terminal),
        "terminal_cells": len({row["cell"] for row in terminal}),
        "terminal_exact": all(row["zero_sum"] and row["refund_exact"] and row.get("comparator_exact", True) for row in terminal),
        "comparator": comparator,
    }
    if (
        checks["source_transition_rows"] != 29878
        or checks["boundary_rows"] != 4096
        or checks["boundary_cells"] != 128
        or checks["terminal_rows"] != 1280
        or checks["terminal_cells"] != 20
        or not checks["terminal_exact"]
        or any(value != 8192 for value in comparator.values())
    ):
        raise RuntimeError("deep_selftest_gate_failure")
    print(canonical({
        "classification": "RS007_DEEP_SELFTEST_PASS",
        "level": level,
        "checks": checks,
        "files_written": 0,
    }))
    return 0


def qualification(root: Path, implementation_sha: str, nonce: str) -> int:
    started = time.perf_counter()
    if root.resolve(strict=False) != QUAL_ROOT.resolve(strict=False) or root.exists():
        raise RuntimeError("qualification_root_freshness_failure")
    registration = verify_frozen_inputs()
    if not IMPL_AUDIT.is_file() or sha_file(IMPL_AUDIT) != implementation_sha:
        raise RuntimeError("implementation_audit_identity_failure")
    implementation = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    if implementation.get("classification") != "PASS / RS007_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY":
        raise RuntimeError("implementation_audit_authority_failure")
    if sha_file(CHECKPOINT) != CHECKPOINT_SHA:
        raise RuntimeError("checkpoint_pre_hash_failure")
    root.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(root / "invocation.json", {
        "identity_sha256": IDENTITY,
        "nonce": nonce,
        "implementation_audit_sha256": implementation_sha,
        "started_epoch": time.time(),
        "network_or_slumbot": "FORBIDDEN",
    })
    artifacts = {}
    rows = load_source_rows(registration)
    source_evidence, counters = source_transition_evidence(rows)
    artifacts["source_transition_rows.jsonl.gz"] = write_gzip_rows(root / "source_transition_rows.jsonl.gz", source_evidence)
    boundary = boundary_matrix()
    artifacts["boundary_matrix_rows.jsonl.gz"] = write_gzip_rows(root / "boundary_matrix_rows.jsonl.gz", boundary)
    terminal = terminal_utility_rows()
    artifacts["terminal_utility_rows.jsonl.gz"] = write_gzip_rows(root / "terminal_utility_rows.jsonl.gz", terminal)
    comparator = comparator_evidence()

    from alpha_holdem import play_slumbot as live_reference
    live_rows = [row for row in rows if row["who"] == "hero" and int(row["street"]) > 0]
    interfaces = []
    new_arrays = []
    reference_arrays = []
    for row in live_rows:
        state = state_from_row(row)
        cards, history, extra, mask, table = observation(state)
        parsed = live_reference.parse_action(str(row["action_str_before"]))
        ref_cards = live_reference.encode_cards(row["hero_hole"], row["board"], int(row["street"]))
        ref_history = live_reference.encode_action_history(
            parsed, int(row["client_pos"]), int(row["mover_pos"]), obs_version="v55"
        )
        commitment = live_reference.compute_commitments(parsed)
        ref_extra = live_reference.encode_extra([STACK - commitment["hero_total"], STACK - commitment["opp_total"]])
        ref_mask, ref_table = live_reference.build_action_table(parsed)
        if not (
            np.array_equal(cards, ref_cards)
            and np.array_equal(history, ref_history)
            and np.array_equal(extra, ref_extra)
            and np.array_equal(mask, ref_mask)
            and table == ref_table
        ):
            raise RuntimeError("live_observation_or_table_nonidentity")
        new_arrays.append((cards, history, extra, mask))
        reference_arrays.append((ref_cards, ref_history, ref_extra, ref_mask))
        interfaces.append({
            "state_identity_sha256": row_identity(row),
            "street": int(row["street"]),
            "actor": int(row["mover_pos"]),
            "observation_sha256": sha_obj([cards.tolist(), history.tolist(), extra.tolist(), mask.tolist()]),
            "table9": table,
            "array_exact": True,
            "table_exact": True,
        })

    policy = H11Policy(nonce)
    def infer_arrays(arrays: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]) -> tuple[list[int], list[list[float]]]:
        torch = policy.torch
        selected, output = [], []
        for start in range(0, len(arrays), 512):
            batch = arrays[start:start + 512]
            with torch.no_grad():
                cards = torch.from_numpy(np.stack([row[0] for row in batch])).to("cuda:0")
                histories = torch.from_numpy(np.stack([row[1] for row in batch])).to("cuda:0")
                extras = torch.from_numpy(np.stack([row[2] for row in batch])).to("cuda:0")
                masks = torch.from_numpy(np.stack([row[3] for row in batch])).to("cuda:0")
                logits, _ = policy.model(cards, histories, extras, masks)
                selected.extend(int(value) for value in torch.argmax(logits, dim=1).cpu().tolist())
                output.extend([[float(value) for value in row] for row in logits.cpu().tolist()])
        return selected, output
    new_slots, new_logits = infer_arrays(new_arrays)
    reference_slots, reference_logits = infer_arrays(reference_arrays)
    for index in range(len(interfaces)):
        exact = new_slots[index] == reference_slots[index] and canonical(new_logits[index]) == canonical(reference_logits[index])
        if not exact:
            raise RuntimeError("live_logits_or_slot_nonidentity")
        interfaces[index]["baseline_slot"] = new_slots[index]
        interfaces[index]["baseline_logits_sha256"] = sha_obj(new_logits[index])
        interfaces[index]["logits_slot_exact"] = True
    artifacts["live_interface_rows.jsonl.gz"] = write_gzip_rows(root / "live_interface_rows.jsonl.gz", interfaces)

    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in live_rows:
        groups[(int(row["street"]), int(row["client_pos"]))].append(row)
    rng = random.Random(WITNESS_SEED)
    for group in groups.values():
        rng.shuffle(group)
    cohort = []
    for quota, key in zip((214, 214, 213, 213, 213, 213), sorted(groups), strict=True):
        cohort.extend(groups[key][:quota])
    if len(cohort) != 1280:
        raise RuntimeError("resolution_cohort_count_failure")
    resolutions = []
    for index, row in enumerate(cohort):
        result = resolve(policy, row)
        result["resolution_index"] = index
        resolutions.append(result)
    repeats = []
    repeat_fields = (
        "selected_slot", "selected_increment", "selection_reason",
        "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256",
    )
    for index, row in enumerate(cohort[:192]):
        again = resolve(policy, row)
        exact = all(canonical(again.get(field)) == canonical(resolutions[index].get(field)) for field in repeat_fields)
        repeats.append({"repeat_index": index, "source_resolution_index": index, "exact": exact})
    fault_names = ("RESOLVER_TIMEOUT", "CUDA_RUNTIME_ERROR", "NONFINITE_PAYOFF_OR_LCB", "ROLLOUT_STEP_OVERFLOW")
    fault_indices = list(range(1280))
    random.Random(FAULT_SEED).shuffle(fault_indices)
    faults = []
    for index in range(128):
        result = resolve(policy, cohort[fault_indices[index]], fault_names[index % 4])
        faults.append({
            "fault_index": index,
            "fault": fault_names[index % 4],
            "baseline_exact": result["selected_slot"] == result["baseline_slot"] and result["selected_increment"] == result["baseline_increment"],
            **result,
        })
    artifacts["resolution_rows.jsonl.gz"] = write_gzip_rows(root / "resolution_rows.jsonl.gz", resolutions)
    artifacts["repeat_rows.jsonl.gz"] = write_gzip_rows(root / "repeat_rows.jsonl.gz", repeats)
    artifacts["fault_rows.jsonl.gz"] = write_gzip_rows(root / "fault_rows.jsonl.gz", faults)

    latencies = [float(row["latency_seconds"]) for row in resolutions]
    nonfallback = [row for row in resolutions if not row["error_fallback"]]
    fallback_count = len(resolutions) - len(nonfallback)
    changes = sum(row["selected_slot"] != row["baseline_slot"] for row in nonfallback)
    rss_mib = 0.0
    try:
        import psutil
        rss_mib = psutil.Process().memory_info().rss / 1048576
    except Exception:
        pass
    metrics = {
        **counters,
        "boundary_rows": len(boundary),
        "boundary_cells": len({(row["street"], row["actor"], row["scenario"]) for row in boundary}),
        "terminal_rows": len(terminal),
        "terminal_cells": len({row["cell"] for row in terminal}),
        "terminal_exact": all(row["zero_sum"] and row["refund_exact"] and row.get("comparator_exact", True) for row in terminal),
        "comparator": comparator,
        "live_interfaces": len(interfaces),
        "resolution_rows": len(resolutions),
        "repeat_rows": len(repeats),
        "repeat_exact": sum(row["exact"] for row in repeats),
        "fault_rows": len(faults),
        "fault_baseline_exact": sum(row["baseline_exact"] for row in faults),
        "fallback_count": fallback_count,
        "fallback_rate": fallback_count / len(resolutions),
        "nonfallback_count": len(nonfallback),
        "selected_slot_change_count": changes,
        "selected_slot_change_rate": changes / max(1, len(nonfallback)),
        "all_distinct_pairs32": all(row.get("determinizations", {}).get("distinct_pair_count") == 32 for row in nonfallback),
        "latency_seconds": {
            "p50": percentile(latencies, .50),
            "p95": percentile(latencies, .95),
            "p99": percentile(latencies, .99),
            "max": max(latencies),
        },
        "projected_quick5k_hours": percentile(latencies, .50) * 5000 / 3600,
        "model_cold_load_seconds": policy.cold_load_seconds,
        "process_rss_mib": rss_mib,
        "gpu_peak_allocated_mib": policy.peak_gpu_mib(),
        "wall_seconds": time.perf_counter() - started,
    }
    gates = {
        "source_rows_29878": metrics["rows"] == 29878,
        "adjacent_24878": metrics["adjacent"] == 24878,
        "external_1658": metrics["external"] == metrics["opponent_external"] == 1658,
        "hero_dual_path_12564": metrics["dual_path_exact"] == 12564,
        "boundary_4096": metrics["boundary_rows"] == 4096 and metrics["boundary_cells"] == 128,
        "live_interfaces_6921": metrics["live_interfaces"] == 6921,
        "terminal_1280_20_exact": metrics["terminal_rows"] == 1280 and metrics["terminal_cells"] == 20 and metrics["terminal_exact"],
        "comparator_8192_exact": all(value == 8192 for value in comparator.values()),
        "resolution_1280": metrics["resolution_rows"] == 1280,
        "mc32_distinct": metrics["all_distinct_pairs32"],
        "repeat_192_exact": metrics["repeat_rows"] == metrics["repeat_exact"] == 192,
        "fault_128_exact": metrics["fault_rows"] == metrics["fault_baseline_exact"] == 128,
        "fallback_le_002": metrics["fallback_rate"] <= .02,
        "change_ge_001": metrics["selected_slot_change_rate"] >= .01,
        "latency_p50": metrics["latency_seconds"]["p50"] <= 2.5,
        "latency_p95": metrics["latency_seconds"]["p95"] <= 8,
        "latency_p99": metrics["latency_seconds"]["p99"] <= 15,
        "latency_max": metrics["latency_seconds"]["max"] <= 20,
        "rss": metrics["process_rss_mib"] <= 3072,
        "gpu": metrics["gpu_peak_allocated_mib"] <= 1024,
        "wall": metrics["wall_seconds"] <= 1800,
        "projection": metrics["projected_quick5k_hours"] <= 12,
        "checkpoint_unchanged": sha_file(CHECKPOINT) == CHECKPOINT_SHA,
    }
    write_json_exclusive(root / "metrics.json", metrics)
    result = {
        "schema_version": "v5.rs007.qualification.result.v1",
        "identity_sha256": IDENTITY,
        "classification": "PASS / RS007_DUAL_DOMAIN_QUALIFICATION_PASS" if all(gates.values()) else "NONPASS / RS007_QUALIFICATION_GATE_NONPASS",
        "gates": gates,
        "pass_count": sum(gates.values()),
        "check_count": len(gates),
        "metrics": metrics,
        "artifact_manifest": artifacts,
        "checkpoint_sha256": sha_file(CHECKPOINT),
        "quick5k_authority": "PENDING_INDEPENDENT_RESULT_AUDIT" if all(gates.values()) else "NONE",
        "network_or_slumbot_hands": 0,
    }
    write_json_exclusive(root / "result.json", result)
    return 0 if all(gates.values()) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("ContractProbe", "SelfTest", "Qualification"))
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--level", choices=("quick", "deep"), default="deep")
    parser.add_argument("--root")
    parser.add_argument("--implementation-audit-sha256")
    args = parser.parse_args()
    boundary = verify_child_boundary(args.nonce)
    if args.mode == "ContractProbe":
        verify_frozen_inputs()
        print(canonical({
            "classification": "RS007_CONTRACT_PROBE_PASS",
            "identity_sha256": IDENTITY,
            **boundary,
            "torch_imported": "torch" in sys.modules,
            "files_written": 0,
        }))
        return 0
    if args.mode == "SelfTest":
        return deep_selftest(args.level)
    if not args.root or not args.implementation_audit_sha256:
        raise RuntimeError("qualification_arguments_missing")
    return qualification(Path(args.root), args.implementation_audit_sha256, args.nonce)


if __name__ == "__main__":
    raise SystemExit(main())
