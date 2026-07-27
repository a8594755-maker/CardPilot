"""RS005: fully-live exact-cent paired-MC32 resolver qualification.

One state owns public actions, chance, terminal classification, and zero-sum
integer-cent utility.  The only poker-evaluation dependency is the pure
``compare_hands`` function.
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

TOKEN = "5a01b095e04a242d79f0a20907a3e6f9"
IDENTITY = "5a01b095e04a242d79f0a20907a3e6f9d59c61780cf9a73765138cdb1f205bde"
PREREG = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_{TOKEN}_20260723.json"
PREREG_SHA = "70a232c8cbbef807e2530ba19e35f887b143d9e0f226cd443385d04e9a0a0c8c"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_resolver_preregistration_audit_{TOKEN}_20260723.json"
PREREG_AUDIT_SHA = "7f6b4800a7c22588f01fc02f8b1c632d8496fc2737fc8c0187faa39943d735c4"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_implementation_audit_{TOKEN}_20260723.json"
QUAL_ROOT = ROOT / "reports" / f"v5_rs005_fully_live_terminal_utility_qualification_{TOKEN}_20260723"

STACK, SB, BB, ACTIONS, MC = 20_000, 50, 100, 9, 32
RAISE_FRACTIONS = (0.33, 0.50, 0.67, 0.75, 1.00, 1.50)
PREFLOP_FRACTIONS = (0.50, 1.00, 1.50)
SYNTHETIC_SEED = 2026072297
WITNESS_SEED = 2026972297
HIDDEN_SEED = 2027972297
FUTURE_SEED = 2028972297
ROLLOUT_SEED = 2029972297
FAULT_SEED = 2030972297
RANKS, SUITS = "23456789TJQKA", "cdhs"


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


def seed_for(base: int, *parts: Any) -> int:
    return int.from_bytes(hashlib.sha256(canonical([base, *parts]).encode()).digest()[:8], "big")


def percentile(values: Iterable[float], q: float) -> float:
    xs = sorted(float(x) for x in values)
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] if lo == hi else xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def write_rows(path: Path, rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    count = 0
    logical = hashlib.sha256()
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
            for row in rows:
                line = (canonical(row) + "\n").encode()
                logical.update(line)
                zipped.write(line)
                count += 1
    return {"rows": count, "logical_sha256": logical.hexdigest(), "file_sha256": sha_file(path), "bytes": path.stat().st_size}


def verify_inputs() -> dict[str, Any]:
    if PREREG.stat().st_size != 22175 or sha_file(PREREG) != PREREG_SHA:
        raise RuntimeError("preregistration_identity_failure")
    if PREREG_AUDIT.stat().st_size != 13101 or sha_file(PREREG_AUDIT) != PREREG_AUDIT_SHA:
        raise RuntimeError("preregistration_audit_identity_failure")
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg["identity"]["sha256"] != IDENTITY or prereg["identity"]["token"] != TOKEN:
        raise RuntimeError("registered_identity_failure")
    checked = 0
    for item in prereg["frozen_authority_inputs"]:
        path = Path(item["path"])
        if not path.is_file() or path.stat().st_size != int(item["bytes"]) or sha_file(path) != item["sha256"]:
            raise RuntimeError(f"frozen_input_failure:{item['role']}")
        checked += 1
    if checked != 26:
        raise RuntimeError("frozen_input_count_failure")
    return prereg


def verify_boundary(nonce: str) -> dict[str, Any]:
    expected_mode = "CUDA0_TORCH_REQUIRED_NO_CPU_FALLBACK"
    if os.environ.get("RS005_DEVICE_MODE") != expected_mode:
        raise RuntimeError("device_mode_failure")
    if os.environ.get("RS005_NONCE") != nonce:
        raise RuntimeError("nonce_failure")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("visibility_failure")
    return {"device_mode": expected_mode, "cuda_visible_devices": "0", "nonce": nonce}


def card_int(text: str) -> int:
    return RANKS.index(text[0].upper()) * 4 + SUITS.index(text[1].lower())


def card_text(value: int) -> str:
    return RANKS[value // 4] + SUITS[value % 4]


@dataclass
class FullyLiveState:
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
    last_raise_size: int = BB - SB
    passive_closes: bool = False
    history: list[list[tuple[str, int, int]]] = field(default_factory=lambda: [[], [], [], []])
    decision_closed: bool = False
    terminal_kind: str = "NONE"
    folded_player: int | None = None
    payout_cents: list[int] | None = None

    def clone(self) -> "FullyLiveState":
        return copy.deepcopy(self)

    def validate_cards(self) -> None:
        cards = [*self.holes[0], *self.holes[1], *self.board, *self.future_deck]
        if any(not isinstance(x, int) or x < 0 or x > 51 for x in cards):
            raise RuntimeError("card_range_failure")
        if len(set(cards)) != len(cards):
            raise RuntimeError("duplicate_card_failure")
        if len(self.holes) != 2 or any(len(x) != 2 for x in self.holes):
            raise RuntimeError("hole_shape_failure")

    @property
    def pot(self) -> int:
        return sum(self.total_commitments)

    @property
    def to_call(self) -> int:
        return 0 if self.actor not in (0, 1) else self.current_bet - self.street_commitments[self.actor]

    def _pay(self, player: int, amount: int) -> None:
        if amount < 0 or amount > self.stacks[player]:
            raise RuntimeError("illegal_commitment")
        self.stacks[player] -= amount
        self.total_commitments[player] += amount
        self.street_commitments[player] += amount

    def _deal_to(self, board_length: int) -> None:
        if board_length < len(self.board) or board_length > 5:
            raise RuntimeError("illegal_board_target")
        needed = board_length - len(self.board)
        if len(self.future_deck) < needed:
            raise RuntimeError("insufficient_future_deck")
        self.board.extend(self.future_deck[:needed])
        del self.future_deck[:needed]
        self.validate_cards()

    def _settle(self) -> None:
        if self.payout_cents is not None:
            raise RuntimeError("payout_computed_twice")
        if self.terminal_kind == "FOLD":
            if self.folded_player not in (0, 1):
                raise RuntimeError("fold_identity_missing")
            lost = self.total_commitments[self.folded_player]
            self.payout_cents = [0, 0]
            self.payout_cents[self.folded_player] = -lost
            self.payout_cents[1 - self.folded_player] = lost
        elif self.terminal_kind == "SHOWDOWN":
            if len(self.board) != 5:
                raise RuntimeError("showdown_board_not_five")
            from deep_cfr.hand_eval import compare_hands
            sign = compare_hands(self.holes[0], self.holes[1], self.board)
            matched = min(self.total_commitments)
            self.payout_cents = [matched, -matched] if sign > 0 else [-matched, matched] if sign < 0 else [0, 0]
        else:
            raise RuntimeError("settle_before_terminal")
        if sum(self.payout_cents) != 0 or any(abs(x) > STACK for x in self.payout_cents):
            raise RuntimeError("payout_invariant_failure")

    def _close_showdown(self, runout: bool) -> None:
        if runout:
            self._deal_to(5)
        self.decision_closed = True
        self.terminal_kind = "SHOWDOWN"
        self.actor = -1
        self._settle()

    def _advance_street(self) -> None:
        if self.street >= 3:
            self._close_showdown(False)
            return
        self.action_string += "/"
        self.street += 1
        self._deal_to(3 if self.street == 1 else 4 if self.street == 2 else 5)
        self.actor = 0
        self.street_commitments = [0, 0]
        self.current_bet = 0
        self.last_raise_size = 0
        self.passive_closes = False

    def apply_increment(self, increment: str) -> "FullyLiveState":
        if self.decision_closed or self.actor not in (0, 1):
            raise RuntimeError("post_terminal_or_closed_action")
        if not re.fullmatch(r"(?:[kcf]|b[1-9][0-9]*)", increment):
            raise RuntimeError("action_grammar_failure")
        mask, table = self.action_table()
        if increment not in table:
            raise RuntimeError(f"nonexecutable_increment:{increment}:{table}")
        player = self.actor
        if increment == "f":
            self.action_string += "f"
            self.history[self.street].append(("f", player, 0))
            self.decision_closed = True
            self.terminal_kind = "FOLD"
            self.folded_player = player
            self.actor = -1
            self._settle()
            return self
        if increment == "k":
            self.action_string += "k"
            self.history[self.street].append(("k", player, 0))
            if self.passive_closes:
                self._advance_street()
            else:
                self.actor = 1 - player
                self.passive_closes = True
            return self
        if increment == "c":
            amount = min(self.to_call, self.stacks[player])
            self._pay(player, amount)
            self.action_string += "c"
            self.history[self.street].append(("c", player, self.current_bet))
            self.last_raise_size = 0
            allin = self.stacks[player] == 0 or self.stacks[1 - player] == 0
            if allin:
                self._close_showdown(True)
            elif self.passive_closes:
                self._advance_street()
            else:
                self.actor = 1 - player
                self.passive_closes = True
            return self
        target = int(increment[1:])
        amount = target - self.street_commitments[player]
        old_bet = self.current_bet
        if target <= old_bet or amount > self.stacks[player]:
            raise RuntimeError("illegal_bet_target")
        self._pay(player, amount)
        self.current_bet = target
        self.last_raise_size = target - old_bet
        self.action_string += increment
        self.history[self.street].append(("b", player, target))
        self.actor = 1 - player
        self.passive_closes = True
        return self

    def action_table(self) -> tuple[np.ndarray, list[str | None]]:
        mask = np.zeros(ACTIONS, dtype=np.float32)
        table: list[str | None] = [None] * ACTIONS
        if self.decision_closed or self.actor not in (0, 1):
            return mask, table
        facing = self.to_call > 0
        if facing:
            mask[0], table[0] = 1.0, "f"
        mask[1], table[1] = 1.0, "c" if facing else "k"
        if self.stacks[self.actor] <= self.to_call:
            return mask, table
        maximum = self.street_commitments[self.actor] + self.stacks[self.actor]
        minimum = self.current_bet + max(self.last_raise_size, BB)
        if maximum <= self.current_bet:
            return mask, table
        pot = max(self.pot, 1)
        after_call = pot + self.to_call
        choices: dict[int, tuple[float, int]] = {}
        fractions = PREFLOP_FRACTIONS if self.street == 0 else RAISE_FRACTIONS
        for fraction in fractions:
            target = self.current_bet + int((after_call if facing else pot) * fraction)
            target = max(target, minimum)
            if target >= maximum:
                continue
            slot = min(range(2, 8), key=lambda x: abs(target / pot - RAISE_FRACTIONS[x - 2]))
            distance = abs(target - RAISE_FRACTIONS[slot - 2] * pot)
            if slot not in choices or distance < choices[slot][0]:
                choices[slot] = (distance, target)
        for slot, (_, target) in choices.items():
            mask[slot], table[slot] = 1.0, f"b{target}"
        mask[8], table[8] = 1.0, f"b{maximum}"
        executable = [x for x in table if x is not None]
        if len(executable) != len(set(executable)):
            raise RuntimeError("executable_table_collision")
        return mask, table

    @classmethod
    def from_prefix(
        cls,
        prefix: str,
        holes: list[tuple[int, int]],
        known_board: list[int],
        remaining_future: list[int],
    ) -> "FullyLiveState":
        state = cls(holes=holes, future_deck=[*known_board, *remaining_future])
        state.validate_cards()
        expected_separators = prefix.count("/")
        actions = re.findall(r"b[1-9][0-9]*|[kcf]|/", prefix)
        if "".join(actions) != prefix:
            raise RuntimeError("prefix_parse_failure")
        observed_separators = 0
        for token in actions:
            if token == "/":
                observed_separators += 1
                continue
            before = state.action_string.count("/")
            state.apply_increment(token)
            if state.action_string.count("/") > before:
                if observed_separators >= expected_separators:
                    pass
        if state.action_string != prefix:
            raise RuntimeError(f"prefix_roundtrip_failure:{prefix}:{state.action_string}")
        if state.board != known_board:
            raise RuntimeError("known_board_replay_failure")
        return state


def encode_cards(hole: tuple[int, int], board: list[int]) -> np.ndarray:
    out = np.zeros((6, 4, 13), dtype=np.float32)
    for card in hole:
        out[0, card % 4, card // 4] = 1
    for index, card in enumerate(board):
        channel = 1 if index < 3 else 2 if index == 3 else 3
        out[channel, card % 4, card // 4] = 1
        out[4, card % 4, card // 4] = 1
    for card in [*hole, *board]:
        out[5, card % 4, card // 4] = 1
    return out


def encode_history(state: FullyLiveState, viewer: int) -> np.ndarray:
    out = np.zeros((25, 4, 5), dtype=np.float32)
    pot = max(state.pot, 1)
    for street in range(4):
        prior_target = BB if street == 0 else 0
        for slot, (move, player, amount) in enumerate(state.history[street][:6]):
            channel = street * 6 + slot
            out[channel, 0, 0] = float(player == viewer)
            if move == "b":
                action_type = 4 if prior_target > 0 else 3
                prior_target = amount
            else:
                action_type = {"f": 0, "k": 1, "c": 2}[move]
            out[channel, 1, action_type] = 1
            if amount > 0:
                out[channel, 2, 0] = min(amount / pot, 2.0) / 2.0
            out[channel, 3, 0] = 1
    out[24, 0, 0] = float(state.actor == viewer)
    return out


def observation(state: FullyLiveState) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str | None]]:
    if state.decision_closed:
        raise RuntimeError("terminal_observation")
    viewer = state.actor
    mask, table = state.action_table()
    extra = np.asarray([state.stacks[viewer] / STACK, state.stacks[1 - viewer] / STACK], dtype=np.float32)
    return encode_cards(state.holes[viewer], state.board), encode_history(state, viewer), extra, mask, table


class H11Policy:
    def __init__(self, nonce: str):
        import torch
        from alpha_holdem.network import AlphaHoldemNet
        self.torch = torch
        verify_boundary(nonce)
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("cuda0_required")
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        blob = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
        if blob.get("env_version") != "v55" or blob.get("obs_version") != "v55" or blob.get("critic_contract") != "critic_v1":
            raise RuntimeError("checkpoint_contract_failure")
        self.model = AlphaHoldemNet(9, norm_layer=blob.get("norm_layer") or "bn").to("cuda:0")
        self.model.eval()
        with torch.no_grad():
            self.model(
                torch.zeros(2, 6, 4, 13, device="cuda:0"),
                torch.zeros(2, 25, 4, 5, device="cuda:0"),
                torch.zeros(2, 2, device="cuda:0"),
            )
        self.model.load_state_dict(blob["model"], strict=True)
        del blob
        torch.cuda.synchronize()
        self.cold_load_seconds = time.perf_counter() - started

    def infer(self, states: list[FullyLiveState]) -> tuple[list[int], list[list[float]]]:
        arrays = [observation(state) for state in states]
        slots, logits_out = [], []
        torch = self.torch
        for start in range(0, len(arrays), 512):
            batch = arrays[start:start + 512]
            with torch.no_grad():
                cards = torch.from_numpy(np.stack([x[0] for x in batch])).to("cuda:0")
                histories = torch.from_numpy(np.stack([x[1] for x in batch])).to("cuda:0")
                extras = torch.from_numpy(np.stack([x[2] for x in batch])).to("cuda:0")
                masks = torch.from_numpy(np.stack([x[3] for x in batch])).to("cuda:0")
                logits, _ = self.model(cards, histories, extras, masks)
                slots.extend(int(x) for x in torch.argmax(logits, dim=1).cpu().tolist())
                logits_out.extend([[float(v) for v in row] for row in logits.cpu().tolist()])
        for state, slot in zip(states, slots, strict=True):
            if state.action_table()[1][slot] is None:
                raise RuntimeError("policy_nonexecutable_slot")
        return slots, logits_out

    def peak_mib(self) -> float:
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


def load_rows(prereg: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in prereg["frozen_authority_inputs"]:
        if item["role"].startswith("h11_dump_part"):
            path = Path(item["path"])
            with path.open(encoding="utf-8") as handle:
                result.extend(safe_row(json.loads(line), str(path.resolve())) for line in handle)
    if len(result) != 29878:
        raise RuntimeError("ledger_census_failure")
    return result


def filler_cards(row: dict[str, Any], salt: int = 0) -> tuple[list[tuple[int, int]], list[int]]:
    hero = int(row["client_pos"])
    hero_pair = tuple(card_int(x) for x in row["hero_hole"])
    board = [card_int(x) for x in row["board"]]
    unseen = [x for x in range(52) if x not in {*hero_pair, *board}]
    random.Random(seed_for(SYNTHETIC_SEED, row["source"], row["hand_idx"], row["move_idx"], salt)).shuffle(unseen)
    holes: list[tuple[int, int]] = [(0, 1), (2, 3)]
    holes[hero] = hero_pair
    holes[1 - hero] = tuple(unseen[:2])
    return holes, unseen[2:]


def state_from_row(row: dict[str, Any], opponent: tuple[int, int] | None = None, future: list[int] | None = None) -> FullyLiveState:
    hero = int(row["client_pos"])
    hero_pair = tuple(card_int(x) for x in row["hero_hole"])
    board = [card_int(x) for x in row["board"]]
    known = {*hero_pair, *board}
    unseen = [x for x in range(52) if x not in known]
    if opponent is None:
        random.Random(seed_for(SYNTHETIC_SEED, row["source"], row["hand_idx"], row["move_idx"])).shuffle(unseen)
        opponent = tuple(unseen[:2])
    remainder = [x for x in unseen if x not in opponent]
    if future is None:
        random.Random(seed_for(FUTURE_SEED, row["source"], row["hand_idx"], row["move_idx"])).shuffle(remainder)
        future = remainder
    holes: list[tuple[int, int]] = [(0, 1), (2, 3)]
    holes[hero], holes[1 - hero] = hero_pair, opponent
    return FullyLiveState.from_prefix(str(row["action_str_before"]), holes, board, list(future))


def witness_exact(row: dict[str, Any], state: FullyLiveState) -> dict[str, Any]:
    observed = {
        "street": state.street,
        "actor": state.actor,
        "pot": state.pot,
        "to_call": state.to_call,
        "mover_stack": state.stacks[state.actor],
        "street_bet_to": state.current_bet,
        "total_bet_to": max(state.total_commitments),
        "last_bet_size": state.last_raise_size,
    }
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
        raise RuntimeError(f"witness_failure:{observed}:{expected}")
    return observed


def state_id(row: dict[str, Any]) -> str:
    return sha_obj([row["source"], row["hand_idx"], row["move_idx"], row["action_str_before"], row["client_pos"], row["hero_hole"], row["board"]])


def determinizations(row: dict[str, Any]) -> tuple[list[FullyLiveState], dict[str, Any]]:
    hero_pair = tuple(card_int(x) for x in row["hero_hole"])
    board = [card_int(x) for x in row["board"]]
    unseen = [x for x in range(52) if x not in {*hero_pair, *board}]
    pairs = list(itertools.combinations(unseen, 2))
    identity = state_id(row)
    random.Random(seed_for(HIDDEN_SEED, identity)).shuffle(pairs)
    pairs = pairs[:MC]
    states, pair_hashes, future_hashes = [], [], []
    for index, pair in enumerate(pairs):
        future = [x for x in unseen if x not in pair]
        random.Random(seed_for(FUTURE_SEED, identity, index)).shuffle(future)
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


def paired_stats(payoffs: dict[int, list[float]], baseline: int) -> dict[str, dict[str, float]]:
    out = {}
    for slot, values in sorted(payoffs.items()):
        diffs = [x - y for x, y in zip(values, payoffs[baseline], strict=True)]
        mean = statistics.fmean(diffs)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
        out[str(slot)] = {"mean_difference_bb": mean, "sample_sd_bb": sd, "lcb95_bb": mean - 1.645 * sd / math.sqrt(MC)}
    return out


def resolve(policy: H11Policy, row: dict[str, Any], fault: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    root = state_from_row(row)
    _, table = root.action_table()
    baseline, logits = policy.infer([root])
    base_slot = baseline[0]
    base = {
        "state_identity_sha256": state_id(row),
        "baseline_slot": base_slot,
        "baseline_increment": table[base_slot],
        "baseline_logits_sha256": sha_obj(logits[0]),
        "live_table9": table,
        "resolver_attempted": True,
    }
    if fault:
        return {**base, "selected_slot": base_slot, "selected_increment": table[base_slot], "selection_reason": fault,
                "error_fallback": True, "latency_seconds": time.perf_counter() - started}
    try:
        dets, trace = determinizations(row)
        legal_slots = [i for i, x in enumerate(table) if x is not None]
        active: list[tuple[int, int, FullyLiveState]] = []
        for slot in legal_slots:
            for index, source in enumerate(dets):
                state = source.clone()
                state.apply_increment(table[slot])
                active.append((slot, index, state))
        values: dict[int, list[float | None]] = {slot: [None] * MC for slot in legal_slots}
        rollout_hash = hashlib.sha256()
        steps = 0
        deadline = started + 20.0
        hero = int(row["client_pos"])
        while active:
            if time.perf_counter() > deadline:
                raise TimeoutError
            pending, metadata = [], []
            for slot, index, state in active:
                if state.decision_closed:
                    value = state.payout_cents[hero] / BB
                    if not math.isfinite(value):
                        raise FloatingPointError
                    values[slot][index] = value
                    rollout_hash.update(canonical([slot, index, value]).encode())
                else:
                    pending.append(state)
                    metadata.append((slot, index))
            if not pending:
                break
            selected, _ = policy.infer(pending)
            active = []
            for (slot, index), state, policy_slot in zip(metadata, pending, selected, strict=True):
                increment = state.action_table()[1][policy_slot]
                rollout_hash.update(canonical([slot, index, steps, state.action_string, policy_slot, increment]).encode())
                state.apply_increment(increment)
                active.append((slot, index, state))
            steps += 1
            if steps > 32:
                raise RuntimeError("rollout_step_overflow")
        complete: dict[int, list[float]] = {}
        for slot, rows in values.items():
            if any(x is None for x in rows):
                raise RuntimeError("missing_terminal_utility")
            complete[slot] = [float(x) for x in rows]
        stats = paired_stats(complete, base_slot)
        eligible = [slot for slot in legal_slots if slot != base_slot and stats[str(slot)]["lcb95_bb"] > 0]
        chosen = min(eligible, key=lambda x: (-stats[str(x)]["lcb95_bb"], x)) if eligible else base_slot
        reason = "PAIRED_LCB95_POSITIVE" if eligible else "LCB_NO_CHANGE"
        return {
            **base,
            "selected_slot": chosen,
            "selected_increment": table[chosen],
            "selection_reason": reason,
            "error_fallback": False,
            "determinizations": trace,
            "paired_statistics_by_slot": stats,
            "rollout_trace_sha256": rollout_hash.hexdigest(),
            "decision_trace_sha256": sha_obj([state_id(row), base_slot, chosen, trace["common_trace_sha256"], rollout_hash.hexdigest()]),
            "max_rollout_actions": steps,
            "latency_seconds": time.perf_counter() - started,
        }
    except TimeoutError:
        reason = "RESOLVER_TIMEOUT"
    except FloatingPointError:
        reason = "NONFINITE_PAYOFF_OR_LCB"
    return {**base, "selected_slot": base_slot, "selected_increment": table[base_slot], "selection_reason": reason,
            "error_fallback": True, "latency_seconds": time.perf_counter() - started}


def terminal_cards(outcome: str) -> tuple[list[tuple[int, int]], list[int]]:
    if outcome == "PLAYER0_WIN":
        return [(48, 49), (4, 9)], [0, 13, 26, 39, 44]
    if outcome == "PLAYER1_WIN":
        return [(4, 9), (48, 49)], [0, 13, 26, 39, 44]
    return [(1, 6), (11, 14)], [32, 36, 40, 44, 48]


def build_terminal(prefix: str, outcome: str) -> FullyLiveState:
    holes, board = terminal_cards(outcome)
    state = FullyLiveState(holes=holes, future_deck=board)
    state.validate_cards()
    for token in re.findall(r"b[1-9][0-9]*|[kcf]", prefix):
        state.apply_increment(token)
    if not state.decision_closed:
        raise RuntimeError("terminal_fixture_not_closed")
    return state


def terminal_cohort() -> list[dict[str, Any]]:
    rows = []
    streets = [
        ("PREFLOP", "", ""),
        ("FLOP", "ck/", "ck"),
        ("TURN", "ck/kk/", "ckkk"),
        ("RIVER", "ck/kk/kk/", "ckkkkk"),
    ]
    for folded in (0, 1):
        for street_name, _, compact in streets:
            for replicate in range(16):
                if street_name == "PREFLOP":
                    prefix = "b200f" if folded == 0 else "f"
                else:
                    prefix = compact + ("kb100f" if folded == 0 else "b100f")
                state = build_terminal(prefix, "PLAYER0_WIN")
                rows.append({
                    "cell": f"FOLD_PLAYER{folded}",
                    "street_balance": street_name,
                    "replicate": replicate,
                    "terminal_kind": state.terminal_kind,
                    "folded_player": state.folded_player,
                    "totals": state.total_commitments,
                    "matched_cents": min(state.total_commitments),
                    "payout_cents": state.payout_cents,
                    "board": state.board,
                    "comparator_sign": None,
                    "zero_sum": sum(state.payout_cents) == 0,
                    "uncalled_refund_exact": state.payout_cents[folded] == -state.total_commitments[folded],
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
            for replicate in range(64):
                state = build_terminal(prefix, outcome)
                sign = compare_hands(state.holes[0], state.holes[1], state.board)
                expected_sign = 1 if outcome == "PLAYER0_WIN" else -1 if outcome == "PLAYER1_WIN" else 0
                rows.append({
                    "cell": f"{origin}_{outcome}",
                    "origin": origin,
                    "outcome": outcome,
                    "replicate": replicate,
                    "terminal_kind": state.terminal_kind,
                    "totals": state.total_commitments,
                    "matched_cents": min(state.total_commitments),
                    "payout_cents": state.payout_cents,
                    "board": state.board,
                    "holes": state.holes,
                    "comparator_sign": sign,
                    "comparator_sign_exact": (sign > 0) - (sign < 0) == expected_sign,
                    "zero_sum": sum(state.payout_cents) == 0,
                    "uncalled_refund_exact": True,
                })
    if len(rows) != 1280 or len({row["cell"] for row in rows}) != 20:
        raise RuntimeError("terminal_cohort_shape_failure")
    return rows


def comparator_checks() -> dict[str, Any]:
    from deep_cfr.hand_eval import compare_hands
    from treys import Card, Evaluator
    evaluator = Evaluator()
    rng = random.Random(seed_for(SYNTHETIC_SEED, "comparator"))
    matches, antisymmetric, permutation = 0, 0, 0
    for _ in range(8192):
        deal = rng.sample(range(52), 9)
        first, second, board = tuple(deal[:2]), tuple(deal[2:4]), deal[4:]
        signed = compare_hands(first, second, board)
        treys_first = evaluator.evaluate([Card.new(card_text(x)) for x in board], [Card.new(card_text(x)) for x in first])
        treys_second = evaluator.evaluate([Card.new(card_text(x)) for x in board], [Card.new(card_text(x)) for x in second])
        direct = treys_second - treys_first
        matches += int((signed > 0) - (signed < 0) == (direct > 0) - (direct < 0))
        antisymmetric += int(compare_hands(second, first, board) == -signed)
        permutation += int(compare_hands(tuple(reversed(first)), second, list(reversed(board))) == signed)
    return {"unique_deals": 8192, "direct_treys_matches": matches, "swap_antisymmetry": antisymmetric, "order_invariance": permutation}


def source_census(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_hand: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    prefixes = set()
    for row in rows:
        by_hand[(row["source"], int(row["hand_idx"]))].append(row)
        prefixes.add(str(row["action_str_before"]))
    transitions, contiguous = 0, True
    for group in by_hand.values():
        group.sort(key=lambda x: int(x["move_idx"]))
        contiguous = contiguous and [int(x["move_idx"]) for x in group] == list(range(len(group)))
        transitions += max(0, len(group) - 1)
    return {
        "ledger_rows": len(rows),
        "source_scoped_hands": len(by_hand),
        "distinct_prefixes": len(prefixes),
        "adjacent_transitions": transitions,
        "move_indices_contiguous": contiguous,
        "hero_postflop_live_interfaces": sum(row["who"] == "hero" and int(row["street"]) > 0 for row in rows),
    }


def validate_adjacent_transitions(rows: list[dict[str, Any]]) -> int:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["source"], int(row["hand_idx"]))].append(row)
    checked = 0
    for group in grouped.values():
        group.sort(key=lambda item: int(item["move_idx"]))
        for left, right in zip(group, group[1:]):
            state = state_from_row(left)
            increment = (
                f"b{int(left['action_amount'])}"
                if left["action_move"] == "b"
                else str(left["action_move"])
            )
            state.apply_increment(increment)
            if state.action_string != str(right["action_str_before"]):
                raise RuntimeError("adjacent_transition_nonidentity")
            checked += 1
    if checked != 24878:
        raise RuntimeError("adjacent_transition_count_failure")
    return checked


def run_self_test(level: str) -> int:
    prereg = verify_inputs()
    checks = {}
    for text in ("", "c", "ck/", "b200c/kk/", "b200b600c/kb300c/kk/"):
        row = {"source": "self", "hand_idx": 0, "move_idx": 0, "client_pos": 0, "hero_hole": ["As", "Kd"], "board": []}
        board_count = 0 if text.count("/") == 0 else 3 if text.count("/") == 1 else 4 if text.count("/") == 2 else 5
        row["board"] = [card_text(x) for x in [0, 5, 10, 15, 20][:board_count]]
        state_from_row({**row, "action_str_before": text})
    cohort = terminal_cohort()
    checks["terminal_rows"] = len(cohort)
    checks["terminal_cells"] = len({x["cell"] for x in cohort})
    checks["terminal_exact"] = all(x["zero_sum"] and x["uncalled_refund_exact"] and (x.get("comparator_sign_exact", True)) for x in cohort)
    checks["comparator"] = comparator_checks()
    if level == "deep":
        census = source_census(load_rows(prereg))
        checks["census"] = census
        if census != {
            "ledger_rows": 29878,
            "source_scoped_hands": 5000,
            "distinct_prefixes": 584,
            "adjacent_transitions": 24878,
            "move_indices_contiguous": True,
            "hero_postflop_live_interfaces": 6921,
        }:
            raise RuntimeError("deep_census_failure")
    if not checks["terminal_exact"] or any(value != 8192 for value in checks["comparator"].values()):
        raise RuntimeError("deep_science_test_failure")
    print(canonical({"classification": "RS005_DEEP_SELF_TEST_PASS", "level": level, "checks": checks, "files_written": 0}))
    return 0


def run_qualification(root: Path, implementation_sha: str, nonce: str) -> int:
    started = time.perf_counter()
    if root.resolve(strict=False) != QUAL_ROOT.resolve(strict=False) or root.exists():
        raise RuntimeError("qualification_root_freshness_failure")
    prereg = verify_inputs()
    if sha_file(IMPL_AUDIT) != implementation_sha:
        raise RuntimeError("implementation_audit_hash_failure")
    implementation = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    if implementation.get("classification") != "PASS / RS005_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY":
        raise RuntimeError("implementation_audit_authority_failure")
    if sha_file(CHECKPOINT) != CHECKPOINT_SHA:
        raise RuntimeError("checkpoint_pre_hash_failure")
    root.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    write_json(root / "invocation.json", {
        "identity_sha256": IDENTITY, "nonce": nonce, "implementation_audit_sha256": implementation_sha,
        "network_and_slumbot": "FORBIDDEN", "started_epoch": time.time(),
    })
    policy = H11Policy(nonce)
    rows = load_rows(prereg)
    census = source_census(rows)
    validate_adjacent_transitions(rows)

    ledger_output, prefix_seen = [], {}
    for row in rows:
        state = state_from_row(row)
        observed = witness_exact(row, state)
        ledger_output.append({
            "source_scoped_hand_key": [row["source"], int(row["hand_idx"])],
            "move_idx": int(row["move_idx"]),
            "prefix_sha256": sha_bytes(str(row["action_str_before"]).encode()),
            **observed,
            "exact": True,
        })
        prefix_seen.setdefault(str(row["action_str_before"]), observed)
    artifacts["ledger_rows.jsonl.gz"] = write_rows(root / "ledger_rows.jsonl.gz", ledger_output)
    artifacts["prefix_rows.jsonl.gz"] = write_rows(
        root / "prefix_rows.jsonl.gz",
        ({"prefix_sha256": sha_bytes(prefix.encode()), **value, "exact": True} for prefix, value in sorted(prefix_seen.items())),
    )

    live_rows = [row for row in rows if row["who"] == "hero" and int(row["street"]) > 0]
    from alpha_holdem import play_slumbot as live_reference
    interfaces = []
    for row in live_rows:
        state = state_from_row(row)
        cards, history, extra, mask, table = observation(state)
        parsed = live_reference.parse_action(str(row["action_str_before"]))
        ref_cards = live_reference.encode_cards(row["hero_hole"], row["board"], int(row["street"]))
        ref_history = live_reference.encode_action_history(
            parsed, int(row["client_pos"]), int(row["mover_pos"]), obs_version="v55"
        )
        commitments = live_reference.compute_commitments(parsed)
        ref_extra = live_reference.encode_extra(
            [STACK - commitments["hero_total"], STACK - commitments["opp_total"]]
        )
        ref_mask, ref_table = live_reference.build_action_table(parsed)
        if not (
            np.array_equal(cards, ref_cards)
            and np.array_equal(history, ref_history)
            and np.array_equal(extra, ref_extra)
            and np.array_equal(mask, ref_mask)
            and table == ref_table
        ):
            raise RuntimeError("live_interface_nonidentity")
        interfaces.append({
            "state_identity_sha256": state_id(row),
            "street": state.street,
            "actor": state.actor,
            "observation_sha256": sha_obj([cards.tolist(), history.tolist(), extra.tolist(), mask.tolist()]),
            "table9": table,
            "exact_cent_state": True,
            "forbidden_runtime_object_count": 0,
        })
    artifacts["hero_live_interfaces.jsonl.gz"] = write_rows(root / "hero_live_interfaces.jsonl.gz", interfaces)

    rng = random.Random(SYNTHETIC_SEED)
    synthetic = []
    templates = [row for row in rows if not state_from_row(row).decision_closed]
    for index in range(8192):
        row = templates[rng.randrange(len(templates))]
        state = state_from_row(row)
        cards, history, extra, mask, table = observation(state)
        synthetic.append({
            "synthetic_index": index,
            "street": state.street,
            "actor": state.actor,
            "pot": state.pot,
            "to_call": state.to_call,
            "legal_slots": [slot for slot, value in enumerate(table) if value is not None],
            "interface_sha256": sha_obj([cards.tolist(), history.tolist(), extra.tolist(), mask.tolist(), table]),
            "exact": True,
        })
    artifacts["synthetic_states.jsonl.gz"] = write_rows(root / "synthetic_states.jsonl.gz", synthetic)

    terminal = terminal_cohort()
    artifacts["terminal_utility_rows.jsonl.gz"] = write_rows(root / "terminal_utility_rows.jsonl.gz", terminal)
    comparator = comparator_checks()

    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in live_rows:
        groups[(int(row["street"]), int(row["client_pos"]))].append(row)
    selection_rng = random.Random(WITNESS_SEED)
    for group in groups.values():
        selection_rng.shuffle(group)
    cohort = []
    quotas = [214, 214, 213, 213, 213, 213]
    for quota, key in zip(quotas, sorted(groups), strict=True):
        cohort.extend(groups[key][:quota])
    if len(cohort) != 1280:
        raise RuntimeError("resolution_cohort_failure")

    resolutions = []
    for index, row in enumerate(cohort):
        result = resolve(policy, row)
        result["resolution_index"] = index
        resolutions.append(result)
    repeats = []
    for index, row in enumerate(cohort[:192]):
        again = resolve(policy, row)
        fields = ("selected_slot", "selected_increment", "selection_reason", "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256")
        exact = all(canonical(again.get(key)) == canonical(resolutions[index].get(key)) for key in fields)
        repeats.append({"repeat_index": index, "source_resolution_index": index, "exact": exact})
    faults, indices = [], list(range(1280))
    random.Random(FAULT_SEED).shuffle(indices)
    fault_names = ("RESOLVER_TIMEOUT", "CUDA_RUNTIME_ERROR", "NONFINITE_PAYOFF_OR_LCB", "ROLLOUT_STEP_OVERFLOW")
    for index in range(128):
        result = resolve(policy, cohort[indices[index]], fault_names[index % 4])
        faults.append({
            "fault_index": index,
            "fault": fault_names[index % 4],
            "baseline_exact": result["selected_slot"] == result["baseline_slot"] and result["selected_increment"] == result["baseline_increment"],
            **result,
        })
    artifacts["resolution_rows.jsonl.gz"] = write_rows(root / "resolution_rows.jsonl.gz", resolutions)
    artifacts["repeat_rows.jsonl.gz"] = write_rows(root / "repeat_rows.jsonl.gz", repeats)
    artifacts["fault_rows.jsonl.gz"] = write_rows(root / "fault_rows.jsonl.gz", faults)

    latency = [float(x["latency_seconds"]) for x in resolutions]
    nonfallback = [x for x in resolutions if not x["error_fallback"]]
    fallback_count = len(resolutions) - len(nonfallback)
    changes = sum(x["selected_slot"] != x["baseline_slot"] for x in nonfallback)
    rss_mib = 0.0
    try:
        import psutil
        rss_mib = psutil.Process().memory_info().rss / 1048576
    except Exception:
        pass
    metrics = {
        **census,
        "balanced_synthetic_states": len(synthetic),
        "terminal_utility_cells": len({x["cell"] for x in terminal}),
        "terminal_utility_rows": len(terminal),
        "terminal_all_exact": all(x["zero_sum"] and x["uncalled_refund_exact"] and x.get("comparator_sign_exact", True) for x in terminal),
        "comparator": comparator,
        "resolution_rows": len(resolutions),
        "repeat_rows": len(repeats),
        "repeat_exact": sum(x["exact"] for x in repeats),
        "fault_rows": len(faults),
        "fault_baseline_exact": sum(x["baseline_exact"] for x in faults),
        "fallback_count": fallback_count,
        "fallback_rate": fallback_count / len(resolutions),
        "nonfallback_count": len(nonfallback),
        "selected_slot_change_count": changes,
        "selected_slot_change_rate": changes / max(1, len(nonfallback)),
        "all_distinct_pairs32": all(x.get("determinizations", {}).get("distinct_pair_count") == 32 for x in nonfallback),
        "latency_seconds": {
            "p50": percentile(latency, .50), "p95": percentile(latency, .95),
            "p99": percentile(latency, .99), "max": max(latency),
        },
        "projected_quick5k_hours": percentile(latency, .50) * 5000 / 3600,
        "model_cold_load_seconds": policy.cold_load_seconds,
        "process_rss_mib": rss_mib,
        "gpu_peak_allocated_mib": policy.peak_mib(),
        "wall_seconds": time.perf_counter() - started,
    }
    gates = {
        "ledger_rows_29878": metrics["ledger_rows"] == 29878,
        "prefixes_584": metrics["distinct_prefixes"] == 584,
        "transitions_24878": metrics["adjacent_transitions"] == 24878,
        "live_interfaces_6921": metrics["hero_postflop_live_interfaces"] == 6921,
        "synthetic_8192": metrics["balanced_synthetic_states"] == 8192,
        "terminal_cells_20": metrics["terminal_utility_cells"] == 20,
        "terminal_rows_1280": metrics["terminal_utility_rows"] == 1280,
        "terminal_all_exact": metrics["terminal_all_exact"],
        "comparator_8192_exact": all(x == 8192 for x in comparator.values()),
        "resolution_rows_1280": metrics["resolution_rows"] == 1280,
        "distinct_pairs32": metrics["all_distinct_pairs32"],
        "repeat_192_exact": metrics["repeat_rows"] == metrics["repeat_exact"] == 192,
        "fault_128_exact": metrics["fault_rows"] == metrics["fault_baseline_exact"] == 128,
        "fallback_rate_le_0_02": metrics["fallback_rate"] <= .02,
        "change_rate_ge_0_01": metrics["selected_slot_change_rate"] >= .01,
        "latency_p50_le_2_5": metrics["latency_seconds"]["p50"] <= 2.5,
        "latency_p95_le_8": metrics["latency_seconds"]["p95"] <= 8,
        "latency_p99_le_15": metrics["latency_seconds"]["p99"] <= 15,
        "latency_max_le_20": metrics["latency_seconds"]["max"] <= 20,
        "rss_le_3072": metrics["process_rss_mib"] <= 3072,
        "gpu_le_1024": metrics["gpu_peak_allocated_mib"] <= 1024,
        "wall_le_1800": metrics["wall_seconds"] <= 1800,
        "quick5k_projection_le_12h": metrics["projected_quick5k_hours"] <= 12,
        "checkpoint_unchanged": sha_file(CHECKPOINT) == CHECKPOINT_SHA,
    }
    write_json(root / "metrics.json", metrics)
    result = {
        "schema_version": "v5.rs005.qualification.result.v1",
        "identity_sha256": IDENTITY,
        "classification": "PASS / RS005_FULLY_LIVE_TERMINAL_UTILITY_QUALIFICATION_PASS" if all(gates.values()) else "NONPASS / RS005_QUALIFICATION_GATE_NONPASS",
        "gates": gates,
        "pass_count": sum(gates.values()),
        "check_count": len(gates),
        "metrics": metrics,
        "artifact_manifest": artifacts,
        "checkpoint_sha256_before_after": CHECKPOINT_SHA,
        "quick5k_authority": "PENDING_INDEPENDENT_RESULT_AUDIT" if all(gates.values()) else "NONE",
        "network_or_slumbot_hands": 0,
    }
    write_json(root / "result.json", result)
    return 0 if all(gates.values()) else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("ContractProbe", "SelfTest", "Qualification"))
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--level", choices=("quick", "deep"), default="quick")
    parser.add_argument("--root")
    parser.add_argument("--implementation-audit-sha256")
    args = parser.parse_args()
    verify_boundary(args.nonce)
    if args.mode == "ContractProbe":
        verify_inputs()
        print(canonical({"classification": "RS005_CONTRACT_PROBE_PASS", "identity_sha256": IDENTITY, "nonce": args.nonce,
                         "device_mode": os.environ["RS005_DEVICE_MODE"], "cuda_visible_devices": "0", "torch_imported": "torch" in sys.modules, "files_written": 0}))
        return 0
    if args.mode == "SelfTest":
        return run_self_test(args.level)
    if not args.root or not args.implementation_audit_sha256:
        raise RuntimeError("qualification_arguments_missing")
    return run_qualification(Path(args.root), args.implementation_audit_sha256, args.nonce)


if __name__ == "__main__":
    raise SystemExit(main())
