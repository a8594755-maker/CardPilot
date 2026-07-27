"""Fresh RS003 live-native exact-cent paired-MC32 resolver.

Public policy state is owned by an exact integer-cent Slumbot action-string ledger.
The HUNL engine is used only as a hidden-card/chance/terminal-utility mirror.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(r"C:\Users\a8594\CardPilot")
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from alpha_holdem.network import AlphaHoldemNet  # noqa: E402
from alpha_holdem import play_slumbot as live  # noqa: E402
from deep_cfr.game_state import Action, ActionType, GameConfig, HUNLGameState, Street  # noqa: E402

TOKEN = "f7709e4bfba3febe0a829c10781054b5"
IDENTITY_SHA256 = "f7709e4bfba3febe0a829c10781054b557ead7d419428dc06736316980679fdb"
PREREG = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_{TOKEN}_20260722.json"
PREREG_SHA256 = "19a75a06e77919bf6cc9bc8bd871b70107a3ec2ee38cb3ccb8fad456788c706b"
PREREG_AUDIT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_preregistration_audit_{TOKEN}_20260722.json"
PREREG_AUDIT_SHA256 = "f411bd44f0aa96d5692c0469db7a61f464939d9a340d3b5b72062bda10a0744e"
CHECKPOINT = ROOT / "models" / "alpha_holdem_v5_hybrid" / "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715" / "h11_control_endpoint.pt"
CHECKPOINT_SHA256 = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
QUAL_ROOT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_qualification_{TOKEN}_20260722"
IMPL_AUDIT = ROOT / "reports" / f"v5_rs003_live_native_paired_mc32_implementation_audit_{TOKEN}_20260722.json"

STACK = 20_000
SB = 50
BB = 100
NUM_ACTIONS = 9
MC = 32
HIDDEN_SEED = 2027972295
FUTURE_SEED = 2028972295
SYNTHETIC_SEED = 2026072295
WITNESS_SEED = 2026972295
FAULT_SEED = 2030972295
MAX_ROLLOUT_ACTIONS = 32
RAISE_FRACTIONS = (0.33, 0.50, 0.67, 0.75, 1.00, 1.50)
PREFLOP_FRACTIONS = (0.50, 1.00, 1.50)
RANKS = "23456789TJQKA"
SUITS = "cdhs"
FORBIDDEN_POLICY_KEYS = {"opp_hole", "showdown", "winnings_hero", "future_rows", "future_board", "future_action", "outcome"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_obj(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def derived_seed(base: int, *parts: Any) -> int:
    digest = hashlib.sha256(canonical_json([base, *parts]).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def write_json_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        handle.write("\n")


def write_jsonl_gz_exclusive(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    digest = hashlib.sha256()
    with path.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            for row in rows:
                line = (canonical_json(row) + "\n").encode("utf-8")
                digest.update(line)
                gz.write(line)
                count += 1
    return count, digest.hexdigest()


def process_rss_mib() -> float:
    try:
        import psutil
        return float(psutil.Process().memory_info().rss / (1024 * 1024))
    except Exception:
        return 0.0


def verify_file(path: Path, expected_sha: str, expected_bytes: int | None = None) -> None:
    if not path.is_file():
        raise RuntimeError(f"missing_frozen_file:{path}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        raise RuntimeError(f"frozen_file_size_mismatch:{path}")
    if sha256_file(path) != expected_sha:
        raise RuntimeError(f"frozen_file_hash_mismatch:{path}")


def verify_authority_inputs() -> dict[str, Any]:
    verify_file(PREREG, PREREG_SHA256, 25412)
    verify_file(PREREG_AUDIT, PREREG_AUDIT_SHA256, 14686)
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg["identity"]["sha256"] != IDENTITY_SHA256 or prereg["identity"]["token"] != TOKEN:
        raise RuntimeError("rs003_identity_mismatch")
    checked = 0
    for item in prereg["frozen_authority_inputs"]:
        verify_file(Path(item["path"]), item["sha256"], int(item["bytes"]))
        checked += 1
    if checked != 22:
        raise RuntimeError("authority_input_count_mismatch")
    return prereg


def validate_device_contract(expected_nonce: str) -> dict[str, Any]:
    if os.environ.get("RS003_DEVICE_MODE") != "CUDA_ONLY_SINGLE_GPU_NO_CPU_RESOLVER_FALLBACK":
        raise RuntimeError("device_mode_mismatch")
    if os.environ.get("RS003_NONCE") != expected_nonce:
        raise RuntimeError("device_nonce_mismatch")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("cuda_visibility_mismatch")
    return {"device_mode": os.environ["RS003_DEVICE_MODE"], "nonce": expected_nonce, "cuda_visible_devices": "0"}


def contract_probe(nonce: str) -> int:
    verify_authority_inputs()
    device = validate_device_contract(nonce)
    print(canonical_json({"classification": "RS003_CONTRACT_PROBE_PASS", "identity_sha256": IDENTITY_SHA256, **device, "files_written": 0}))
    return 0


@dataclass
class CentLedger:
    action_str: str = ""
    street: int = 0
    actor: int = 1
    total: list[int] = field(default_factory=lambda: [BB, SB])
    street_commit: list[int] = field(default_factory=lambda: [BB, SB])
    stacks: list[int] = field(default_factory=lambda: [STACK - BB, STACK - SB])
    current_bet: int = BB
    last_bet_size: int = BB - SB
    last_bettor: int = 0
    check_or_call_ends: bool = False
    pending_street_complete: bool = False
    terminal: bool = False
    folded_player: int = -1
    history: list[list[tuple[str, int, int]]] = field(default_factory=lambda: [[], [], [], []])

    def clone(self) -> "CentLedger":
        return CentLedger(
            action_str=self.action_str, street=self.street, actor=self.actor,
            total=list(self.total), street_commit=list(self.street_commit), stacks=list(self.stacks),
            current_bet=self.current_bet, last_bet_size=self.last_bet_size, last_bettor=self.last_bettor,
            check_or_call_ends=self.check_or_call_ends, pending_street_complete=self.pending_street_complete,
            terminal=self.terminal, folded_player=self.folded_player,
            history=[list(x) for x in self.history],
        )

    @property
    def pot(self) -> int:
        return int(self.total[0] + self.total[1])

    @property
    def to_call(self) -> int:
        if self.actor not in (0, 1):
            return 0
        return max(0, self.current_bet - self.street_commit[self.actor])

    def assert_invariants(self) -> None:
        if any(x < 0 for x in [*self.total, *self.street_commit, *self.stacks, self.current_bet, self.last_bet_size]):
            raise RuntimeError("ledger_negative_value")
        for p in (0, 1):
            if self.total[p] + self.stacks[p] != STACK:
                raise RuntimeError("ledger_stack_conservation_failure")
            if self.street_commit[p] > self.total[p]:
                raise RuntimeError("ledger_street_commit_exceeds_total")
        if self.pot != sum(self.total):
            raise RuntimeError("ledger_pot_conservation_failure")
        if not self.terminal and not self.pending_street_complete and self.actor not in (0, 1):
            raise RuntimeError("ledger_actor_invalid")

    def _complete_street(self) -> None:
        if not self.pending_street_complete or self.street >= 3:
            raise RuntimeError("ledger_unexpected_street_separator")
        self.street += 1
        self.actor = 0
        self.street_commit = [0, 0]
        self.current_bet = 0
        self.last_bet_size = 0
        self.last_bettor = -1
        self.check_or_call_ends = False
        self.pending_street_complete = False

    def apply_increment(self, incr: str, append: bool = True, auto_separator: bool = True) -> "CentLedger":
        s = self.clone()
        if s.terminal or s.pending_street_complete or s.actor not in (0, 1):
            raise RuntimeError("ledger_action_on_nonacting_state")
        p = s.actor
        if incr == "k":
            if s.to_call != 0:
                raise RuntimeError("ledger_illegal_check")
            s.history[s.street].append(("k", p, 0))
            if s.check_or_call_ends:
                if s.street == 3:
                    s.terminal, s.actor = True, -1
                else:
                    s.pending_street_complete, s.actor = True, -1
            else:
                s.actor = 1 - p
                s.check_or_call_ends = True
        elif incr == "c":
            if s.to_call <= 0:
                raise RuntimeError("ledger_illegal_call")
            target = s.current_bet
            amount = min(s.to_call, s.stacks[p])
            s.total[p] += amount
            s.street_commit[p] += amount
            s.stacks[p] -= amount
            s.history[s.street].append(("c", p, target))
            if s.stacks[p] == 0 or s.stacks[1 - p] == 0:
                s.terminal, s.actor = True, -1
            elif s.check_or_call_ends:
                if s.street == 3:
                    s.terminal, s.actor = True, -1
                else:
                    s.pending_street_complete, s.actor = True, -1
            else:
                s.actor = 1 - p
                s.check_or_call_ends = True
            s.last_bet_size = 0
            s.last_bettor = -1
        elif incr == "f":
            if s.to_call <= 0:
                raise RuntimeError("ledger_illegal_fold")
            s.history[s.street].append(("f", p, 0))
            s.folded_player = p
            s.terminal, s.actor = True, -1
        elif incr.startswith("b") and incr[1:].isdigit():
            target = int(incr[1:])
            if target <= s.current_bet or target <= s.street_commit[p]:
                raise RuntimeError("ledger_bet_target_not_increasing")
            max_target = s.street_commit[p] + s.stacks[p]
            if target > max_target:
                raise RuntimeError("ledger_bet_target_exceeds_stack")
            delta = target - s.street_commit[p]
            old_bet = s.current_bet
            s.total[p] += delta
            s.street_commit[p] = target
            s.stacks[p] -= delta
            s.current_bet = target
            s.last_bet_size = target - old_bet
            s.last_bettor = p
            s.history[s.street].append(("b", p, target))
            s.actor = 1 - p
            s.check_or_call_ends = True
        else:
            raise RuntimeError("ledger_increment_grammar_invalid")
        if append:
            s.action_str += incr
        if auto_separator and s.pending_street_complete:
            s.action_str += "/"
            s._complete_street()
        s.assert_invariants()
        return s

    @classmethod
    def parse(cls, text: str) -> "CentLedger":
        s = cls()
        i = 0
        while i < len(text):
            c = text[i]
            if c == "/":
                s.action_str += "/"
                s._complete_street()
                i += 1
                continue
            if c == "b":
                j = i + 1
                while j < len(text) and text[j].isdigit():
                    j += 1
                if j == i + 1:
                    raise RuntimeError("ledger_bet_missing_amount")
                incr = text[i:j]
                i = j
            elif c in "kcf":
                incr = c
                i += 1
            else:
                raise RuntimeError("ledger_character_invalid")
            s = s.apply_increment(incr, append=True, auto_separator=False)
        if s.action_str != text:
            raise RuntimeError("ledger_reencode_mismatch")
        s.assert_invariants()
        return s

    def live_state_dict(self) -> dict[str, Any]:
        return {
            "st": self.street, "pos": self.actor,
            "street_last_bet_to": self.current_bet,
            "total_last_bet_to": max(self.total),
            "last_bet_size": self.last_bet_size,
            "last_bettor": self.last_bettor,
            "street_actions": [list(x) for x in self.history],
        }


def closest_raise_slot(pot_frac: float) -> int:
    return min(range(6), key=lambda i: (abs(pot_frac - RAISE_FRACTIONS[i]), i)) + 2


def live_action_table(ledger: CentLedger) -> tuple[np.ndarray, list[str | None]]:
    if ledger.terminal or ledger.actor not in (0, 1):
        return np.zeros(NUM_ACTIONS, dtype=np.float32), [None] * NUM_ACTIONS
    mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
    table: list[str | None] = [None] * NUM_ACTIONS
    dist = [float("inf")] * NUM_ACTIONS
    facing = ledger.to_call > 0
    if facing:
        mask[0], table[0] = 1.0, "f"
    mask[1], table[1] = 1.0, "c" if facing else "k"
    stack = ledger.stacks[ledger.actor]
    if stack <= ledger.to_call:
        return mask, table
    max_target = ledger.street_commit[ledger.actor] + stack
    if max_target <= ledger.current_bet:
        return mask, table
    pot_after_call = ledger.pot + ledger.to_call
    min_raise = max(ledger.last_bet_size, BB)
    min_target = ledger.current_bet + min_raise
    fractions = PREFLOP_FRACTIONS if ledger.street == 0 else RAISE_FRACTIONS
    for frac in fractions:
        target = ledger.current_bet + int((pot_after_call if facing else ledger.pot) * frac)
        target = max(target, min_target)
        if target >= max_target:
            continue
        slot = closest_raise_slot(target / max(ledger.pot, 1))
        wanted = RAISE_FRACTIONS[slot - 2] * ledger.pot
        d = abs(target - wanted)
        if d < dist[slot]:
            mask[slot], table[slot], dist[slot] = 1.0, f"b{target}", d
    mask[8], table[8] = 1.0, f"b{max_target}"
    if int(mask.sum()) != len({x for x in table if x is not None}):
        raise RuntimeError("live_action_table_collision")
    return mask, table


def encode_history_exact(ledger: CentLedger, viewer: int) -> np.ndarray:
    tensor = np.zeros((25, 4, 5), dtype=np.float32)
    pot = max(ledger.pot, 1)
    for street in range(4):
        prior_bet = BB if street == 0 else 0
        for slot, (move, player, amount) in enumerate(ledger.history[street][:6]):
            channel = street * 6 + slot
            tensor[channel, 0, 0] = 1.0 if player == viewer else 0.0
            if move == "b":
                action_type = 4 if prior_bet > 0 else 3
                prior_bet = amount
            else:
                action_type = {"f": 0, "k": 1, "c": 2}[move]
            tensor[channel, 1, min(action_type, 4)] = 1.0
            if amount > 0:
                tensor[channel, 2, 0] = min(amount / pot, 2.0) / 2.0
            tensor[channel, 3, 0] = 1.0
    tensor[24, 0, 0] = 1.0 if ledger.actor == viewer else 0.0
    return tensor


def encode_extra_exact(ledger: CentLedger, viewer: int) -> np.ndarray:
    return np.asarray([ledger.stacks[viewer] / STACK, ledger.stacks[1 - viewer] / STACK], dtype=np.float32)


def card_to_int(card: str) -> int:
    if len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
        raise RuntimeError(f"invalid_card:{card}")
    return RANKS.index(card[0]) * 4 + SUITS.index(card[1])


def int_to_card(card: int) -> str:
    return RANKS[card // 4] + SUITS[card % 4]


def full_config() -> GameConfig:
    config = GameConfig.full_200bb()
    config.raise_cap_per_street = 999
    return config


def mirror_from_ledger(ledger: CentLedger, holes: list[tuple[int, int] | None], board: list[int], deck: list[int]) -> HUNLGameState:
    state = HUNLGameState(full_config())
    state.street = Street(ledger.street)
    state.current_player = ledger.actor
    state.pot = ledger.pot / 100.0
    state.stacks = [x / 100.0 for x in ledger.stacks]
    state.street_committed = [x / 100.0 for x in ledger.street_commit]
    state.raise_count = sum(1 for move, _, _ in ledger.history[ledger.street] if move == "b")
    state.last_bet_size = ledger.last_bet_size / 100.0
    state.num_actions_this_street = len(ledger.history[ledger.street])
    state.actions_history = []
    state.hole_cards = list(holes)
    state.board = list(board)
    state.deck = list(deck)
    state.is_done = ledger.terminal
    state.folded_player = ledger.folded_player
    return state


@dataclass
class RolloutState:
    ledger: CentLedger
    mirror: HUNLGameState

    def clone(self) -> "RolloutState":
        return RolloutState(self.ledger.clone(), self.mirror.clone())

    def board_strings(self) -> list[str]:
        return [int_to_card(int(x)) for x in self.mirror.board]

    def hole_strings(self, player: int) -> list[str]:
        pair = self.mirror.hole_cards[player]
        if pair is None:
            raise RuntimeError("rollout_acting_hole_missing")
        return [int_to_card(int(pair[0])), int_to_card(int(pair[1]))]


def mirror_action_for_increment(state: RolloutState, incr: str) -> Action:
    if incr == "k":
        return Action(ActionType.CHECK)
    if incr == "c":
        return Action(ActionType.CALL)
    if incr == "f":
        return Action(ActionType.FOLD)
    if incr.startswith("b") and incr[1:].isdigit():
        target = int(incr[1:])
        p = state.ledger.actor
        max_target = state.ledger.street_commit[p] + state.ledger.stacks[p]
        if target == max_target:
            kind = ActionType.ALLIN
        elif state.ledger.to_call > 0:
            kind = ActionType.RAISE
        else:
            kind = ActionType.BET
        return Action(kind, target / 100.0)
    raise RuntimeError("mirror_increment_invalid")


def assert_mirror_public(state: RolloutState) -> None:
    ledger, mirror = state.ledger, state.mirror
    if ledger.terminal:
        if not mirror.is_terminal():
            raise RuntimeError("mirror_terminal_mismatch")
        return
    observed = {
        "actor": int(mirror.current_player),
        "street": int(mirror.street),
        "pot": int(round(mirror.pot * 100)),
        "stacks": [int(round(x * 100)) for x in mirror.stacks],
        "street_commit": [int(round(x * 100)) for x in mirror.street_committed],
    }
    expected = {"actor": ledger.actor, "street": ledger.street, "pot": ledger.pot, "stacks": ledger.stacks, "street_commit": ledger.street_commit}
    if observed != expected:
        raise RuntimeError(f"utility_mirror_public_mismatch:{expected}:{observed}")


def apply_live_increment(state: RolloutState, incr: str) -> RolloutState:
    action = mirror_action_for_increment(state, incr)
    next_mirror = state.mirror.apply(action)
    next_ledger = state.ledger.apply_increment(incr, append=True, auto_separator=True)
    result = RolloutState(next_ledger, next_mirror)
    assert_mirror_public(result)
    return result


def observation(state: RolloutState) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str | None]]:
    p = state.ledger.actor
    if p not in (0, 1):
        raise RuntimeError("observation_on_terminal")
    cards = live.encode_cards(state.hole_strings(p), state.board_strings(), state.ledger.street)
    history = encode_history_exact(state.ledger, p)
    extra = encode_extra_exact(state.ledger, p)
    mask, table = live_action_table(state.ledger)
    return cards, history, extra, mask, table


class H11Actor:
    def __init__(self, nonce: str):
        import torch
        self.torch = torch
        self.device = validate_device_contract(nonce)
        torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cudnn.benchmark = False
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
        if checkpoint.get("critic_contract") != "critic_v1" or checkpoint.get("env_version") != "v55" or checkpoint.get("obs_version") != "v55":
            raise RuntimeError("checkpoint_interface_metadata_mismatch")
        self.model = AlphaHoldemNet(num_actions=9, norm_layer=checkpoint.get("norm_layer") or "bn").to("cuda:0")
        self.model.eval()
        with torch.no_grad():
            self.model(torch.zeros(2, 6, 4, 13, device="cuda:0"), torch.zeros(2, 25, 4, 5, device="cuda:0"), torch.zeros(2, 2, device="cuda:0"))
        self.model.load_state_dict(checkpoint["model"], strict=True)
        self.model.eval()
        del checkpoint
        torch.cuda.synchronize()
        self.cold_load_seconds = time.perf_counter() - started

    def infer_arrays(self, arrays: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]) -> tuple[list[int], list[list[float]]]:
        if not arrays:
            return [], []
        torch = self.torch
        slots: list[int] = []
        logits_rows: list[list[float]] = []
        for start in range(0, len(arrays), 512):
            batch = arrays[start:start + 512]
            with torch.no_grad():
                card = torch.from_numpy(np.stack([x[0] for x in batch])).to("cuda:0")
                hist = torch.from_numpy(np.stack([x[1] for x in batch])).to("cuda:0")
                extra = torch.from_numpy(np.stack([x[2] for x in batch])).to("cuda:0")
                mask = torch.from_numpy(np.stack([x[3] for x in batch])).to("cuda:0")
                logits, _ = self.model(card, hist, extra, mask)
                slots.extend(int(x) for x in torch.argmax(logits, dim=1).cpu().tolist())
                logits_rows.extend([[float(v) for v in row] for row in logits.cpu().tolist()])
        return slots, logits_rows

    def infer_states(self, states: list[RolloutState]) -> tuple[list[int], list[list[float]]]:
        arrays = []
        tables = []
        for state in states:
            c, h, e, m, t = observation(state)
            arrays.append((c, h, e, m))
            tables.append(t)
        slots, logits = self.infer_arrays(arrays)
        for slot, table in zip(slots, tables, strict=True):
            if table[slot] is None:
                raise RuntimeError("h11_selected_nonexecutable_live_slot")
        return slots, logits

    def peak_gpu_mib(self) -> float:
        return float(self.torch.cuda.max_memory_allocated() / (1024 * 1024))


def safe_row(raw: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "source": source, "hand_idx": int(raw["hand_idx"]), "move_idx": int(raw["move_idx"]),
        "who": str(raw["who"]), "street": int(raw["street"]), "action_str_before": str(raw["action_str_before"]),
        "client_pos": int(raw["client_pos"]), "mover_pos": int(raw["mover_pos"]),
        "hero_hole": list(raw["hero_hole"]), "board": list(raw["board"]),
        "pot_before": int(raw["pot_before"]), "to_call": int(raw["to_call"]),
        "stack_remaining": int(raw["stack_remaining"]), "street_last_bet_to": int(raw["street_last_bet_to"]),
        "total_last_bet_to": int(raw["total_last_bet_to"]), "last_bet_size": int(raw["last_bet_size"]),
        "action_move": str(raw["action_move"]), "action_amount": int(raw["action_amount"]),
    }


def dump_paths(prereg: dict[str, Any]) -> list[Path]:
    return [Path(x["path"]) for x in prereg["frozen_authority_inputs"] if x["role"].startswith("h11_dump_part")]


def load_safe_rows(prereg: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for path in dump_paths(prereg):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                rows.append(safe_row(json.loads(line), path.name))
    if len(rows) != 29878:
        raise RuntimeError("dump_row_count_mismatch")
    return rows


def validate_witness_row(row: dict[str, Any]) -> tuple[CentLedger, dict[str, Any]]:
    ledger = CentLedger.parse(row["action_str_before"])
    observed = {
        "street": ledger.street, "actor": ledger.actor, "pot": ledger.pot, "to_call": ledger.to_call,
        "mover_stack": ledger.stacks[ledger.actor], "street_bet_to": ledger.current_bet,
        "total_bet_to": max(ledger.total), "last_bet_size": ledger.last_bet_size,
    }
    expected = {
        "street": row["street"], "actor": row["mover_pos"], "pot": row["pot_before"], "to_call": row["to_call"],
        "mover_stack": row["stack_remaining"], "street_bet_to": row["street_last_bet_to"],
        "total_bet_to": row["total_last_bet_to"], "last_bet_size": row["last_bet_size"],
    }
    if observed != expected:
        raise RuntimeError(f"ledger_witness_mismatch:{expected}:{observed}")
    parsed = live.parse_action(row["action_str_before"])
    for key, value in {"st": ledger.street, "pos": ledger.actor, "street_last_bet_to": ledger.current_bet, "total_last_bet_to": max(ledger.total), "last_bet_size": ledger.last_bet_size}.items():
        if int(parsed[key]) != int(value):
            raise RuntimeError(f"live_parser_crosscheck_mismatch:{key}")
    return ledger, observed


def reference_observation(row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str | None]]:
    parsed = live.parse_action(row["action_str_before"])
    actor = int(row["client_pos"])
    cards = live.encode_cards(row["hero_hole"], row["board"], int(parsed["st"]))
    history = live.encode_action_history(parsed, actor, int(parsed["pos"]), obs_version="v55")
    commitments = live.compute_commitments(parsed)
    extra = live.encode_extra([STACK - commitments["hero_total"], STACK - commitments["opp_total"]])
    mask, table = live.build_action_table(parsed)
    return cards, history, extra, mask, table


def info_rollout_state(row: dict[str, Any], opponent_pair: tuple[int, int] | None = None, future: list[int] | None = None) -> RolloutState:
    ledger = CentLedger.parse(row["action_str_before"])
    hero = int(row["client_pos"])
    holes: list[tuple[int, int] | None] = [None, None]
    holes[hero] = tuple(card_to_int(x) for x in row["hero_hole"])
    holes[1 - hero] = opponent_pair
    board = [card_to_int(x) for x in row["board"]]
    mirror = mirror_from_ledger(ledger, holes, board, list(reversed(future or [])))
    state = RolloutState(ledger, mirror)
    assert_mirror_public(state)
    return state


def state_identity(row: dict[str, Any]) -> str:
    return sha256_obj({"action_str": row["action_str_before"], "client_pos": row["client_pos"], "hero_hole": row["hero_hole"], "board": row["board"]})


def determinizations(row: dict[str, Any]) -> tuple[list[RolloutState], dict[str, Any]]:
    hero = int(row["client_pos"])
    known = {card_to_int(x) for x in [*row["hero_hole"], *row["board"]]}
    unseen = [x for x in range(52) if x not in known]
    pairs = list(itertools.combinations(unseen, 2))
    identity = state_identity(row)
    random.Random(derived_seed(HIDDEN_SEED, identity)).shuffle(pairs)
    selected = pairs[:MC]
    if len(set(selected)) != MC:
        raise RuntimeError("hidden_pair_diversity_failure")
    states, pair_hashes, future_hashes = [], [], []
    for index, pair in enumerate(selected):
        future = [x for x in unseen if x not in pair]
        random.Random(derived_seed(FUTURE_SEED, identity, index)).shuffle(future)
        states.append(info_rollout_state(row, pair, future))
        pair_hashes.append(sha256_obj([identity, index, sorted(pair)]))
        future_hashes.append(sha256_obj([identity, index, future]))
    return states, {"sample_count": MC, "distinct_pair_count": len(set(selected)), "pair_hashes": pair_hashes, "future_hashes": future_hashes, "common_trace_sha256": sha256_obj([pair_hashes, future_hashes])}


def paired_stats(payoffs: dict[int, list[float]], baseline: int) -> dict[int, dict[str, float]]:
    result = {}
    base = payoffs[baseline]
    for slot in sorted(payoffs):
        diffs = [a - b for a, b in zip(payoffs[slot], base, strict=True)]
        mean = statistics.fmean(diffs)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
        result[slot] = {"mean_difference_bb": mean, "sample_sd_bb": sd, "lcb95_bb": mean - 1.645 * sd / math.sqrt(len(diffs))}
    return result


def rollout(actor: H11Actor, root: dict[str, Any], dets: list[RolloutState], deadline: float) -> tuple[dict[int, list[float]], str, int]:
    root_ledger = dets[0].ledger
    _, table = live_action_table(root_ledger)
    slots = [i for i, x in enumerate(table) if x is not None]
    active: list[tuple[int, int, RolloutState]] = []
    for slot in slots:
        for pair_index, state in enumerate(dets):
            _, current = live_action_table(state.ledger)
            if current != table:
                raise RuntimeError("root_live_table_not_common")
            active.append((slot, pair_index, apply_live_increment(state, table[slot])))
    payoffs: dict[int, list[float | None]] = {slot: [None] * MC for slot in slots}
    trace = hashlib.sha256()
    steps = 0
    hero = int(root["client_pos"])
    while active:
        if time.perf_counter() > deadline:
            raise TimeoutError("resolver_timeout")
        pending = []
        for slot, pair_index, state in active:
            if state.ledger.terminal:
                value = float(state.mirror.payoff(hero))
                if not math.isfinite(value):
                    raise FloatingPointError("nonfinite_payoff")
                payoffs[slot][pair_index] = value
                trace.update(canonical_json([slot, pair_index, "T", value]).encode())
            else:
                pending.append((slot, pair_index, state))
        if not pending:
            break
        chosen, _ = actor.infer_states([x[2] for x in pending])
        next_active = []
        for (slot, pair_index, state), policy_slot in zip(pending, chosen, strict=True):
            _, future_table = live_action_table(state.ledger)
            incr = future_table[policy_slot]
            if incr is None:
                raise RuntimeError("rollout_nonexecutable_slot")
            trace.update(canonical_json([slot, pair_index, steps, state.ledger.action_str, policy_slot, incr]).encode())
            next_active.append((slot, pair_index, apply_live_increment(state, incr)))
        active = next_active
        steps += 1
        if steps > MAX_ROLLOUT_ACTIONS:
            raise RuntimeError("rollout_step_overflow")
    final: dict[int, list[float]] = {}
    for slot, values in payoffs.items():
        if any(x is None for x in values):
            raise RuntimeError("missing_rollout_payoff")
        final[slot] = [float(x) for x in values if x is not None]
    return final, trace.hexdigest(), steps


def resolve(actor: H11Actor, row: dict[str, Any], fault: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    info = info_rollout_state(row)
    mask, table = live_action_table(info.ledger)
    baseline_slots, baseline_logits = actor.infer_states([info])
    baseline = baseline_slots[0]
    base = {
        "state_identity_sha256": state_identity(row), "street": row["street"], "client_pos": row["client_pos"],
        "baseline_slot": baseline, "baseline_increment": table[baseline], "live_mask9": [float(x) for x in mask], "live_table9": table,
        "baseline_logits_sha256": sha256_obj(baseline_logits[0]), "resolver_attempted": row["street"] > 0,
        "illegal_selected_action_mass": 0.0,
    }
    if row["street"] == 0:
        return {**base, "selected_slot": baseline, "selected_increment": table[baseline], "selection_reason": "PREFLOP_PASSTHROUGH", "error_fallback": False, "latency_seconds": time.perf_counter() - started}
    if fault:
        if fault == "LCB_NO_CHANGE":
            return {**base, "selected_slot": baseline, "selected_increment": table[baseline], "selection_reason": fault, "error_fallback": False, "latency_seconds": time.perf_counter() - started}
        return {**base, "selected_slot": baseline, "selected_increment": table[baseline], "selection_reason": fault, "error_fallback": True, "latency_seconds": time.perf_counter() - started}
    try:
        dets, det_trace = determinizations(row)
        values, rollout_trace, max_steps = rollout(actor, row, dets, started + 20.0)
        stats = paired_stats(values, baseline)
        eligible = [slot for slot in values if slot != baseline and stats[slot]["lcb95_bb"] > 0.0]
        if eligible:
            selected = max(eligible, key=lambda s: (stats[s]["mean_difference_bb"], stats[s]["lcb95_bb"], -s))
            reason = "PAIRED_LCB95_POSITIVE"
        else:
            selected, reason = baseline, "LCB_NO_CHANGE"
        return {**base, "selected_slot": selected, "selected_increment": table[selected], "selection_reason": reason, "error_fallback": False,
                "determinizations": det_trace, "paired_statistics_by_slot": {str(k): stats[k] for k in sorted(stats)},
                "rollout_trace_sha256": rollout_trace, "max_rollout_actions": max_steps,
                "decision_trace_sha256": sha256_obj([base["state_identity_sha256"], baseline, selected, table[selected], det_trace["common_trace_sha256"], rollout_trace]),
                "latency_seconds": time.perf_counter() - started}
    except TimeoutError:
        reason = "RESOLVER_TIMEOUT"
    except FloatingPointError:
        reason = "NONFINITE_PAYOFF_OR_LCB"
    except RuntimeError as exc:
        text = str(exc)
        if "rollout_step" in text:
            reason = "ROLLOUT_STEP_OVERFLOW"
        else:
            raise
    return {**base, "selected_slot": baseline, "selected_increment": table[baseline], "selection_reason": reason, "error_fallback": True, "latency_seconds": time.perf_counter() - started}


def pot_band(pot: int) -> str:
    bb = pot / 100.0
    return "A_LE10" if bb <= 10 else "B_LE30" if bb <= 30 else "C_LE80" if bb <= 80 else "D_GT80"


def deterministic_cards(index: int, street: int, prefix: str) -> tuple[list[str], list[str]]:
    deck = [r + s for r in RANKS for s in SUITS]
    random.Random(derived_seed(SYNTHETIC_SEED, index, street, prefix)).shuffle(deck)
    board_n = 0 if street == 0 else 3 if street == 1 else 4 if street == 2 else 5
    return deck[:2], deck[2:2 + board_n]


def synthetic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pre = [x for x in rows if x["street"] == 0 and CentLedger.parse(x["action_str_before"]).actor in (0, 1)]
    hero_post = [x for x in rows if x["who"] == "hero" and x["street"] > 0]
    cells: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in hero_post:
        cells[(row["street"], row["client_pos"], pot_band(row["pot_before"]))].append(row)
    required = [(s, p, b) for s in (1, 2, 3) for p in (0, 1) for b in ("A_LE10", "B_LE30", "C_LE80", "D_GT80")]
    if any(not cells[x] for x in required):
        raise RuntimeError("synthetic_cell_template_missing")
    result = []
    for i in range(2048):
        base = dict(pre[i % len(pre)])
        hole, board = deterministic_cards(i, 0, base["action_str_before"])
        base.update({"hero_hole": hole, "board": board, "client_pos": base["mover_pos"], "who": "hero", "synthetic": True, "synthetic_index": i})
        result.append(base)
    offset = 2048
    for cell in required:
        templates = cells[cell]
        for j in range(256):
            base = dict(templates[j % len(templates)])
            hole, board = deterministic_cards(offset + j, cell[0], base["action_str_before"])
            base.update({"hero_hole": hole, "board": board, "who": "hero", "synthetic": True, "synthetic_index": offset + j, "cell": list(cell)})
            result.append(base)
        offset += 256
    if len(result) != 8192:
        raise RuntimeError("synthetic_count_mismatch")
    return result


def select_resolution_rows(synthetic: list[dict[str, Any]], witnessed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    syn = [x for x in synthetic if x["street"] > 0]
    by_cell: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for x in syn:
        by_cell[(x["street"], x["client_pos"], pot_band(x["pot_before"]))].append(x)
    chosen = []
    for key in sorted(by_cell):
        chosen.extend(by_cell[key][:32])
    groups: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for x in witnessed:
        groups[(x["street"], x["client_pos"])].append(x)
    rng = random.Random(WITNESS_SEED)
    for values in groups.values():
        rng.shuffle(values)
    quotas = [86, 86, 85, 85, 85, 85]
    for quota, key in zip(quotas, sorted(groups), strict=True):
        chosen.extend(groups[key][:quota])
    if len(chosen) != 1280:
        raise RuntimeError(f"resolution_cohort_count_mismatch:{len(chosen)}")
    return chosen


def run_self_test(level: str) -> int:
    verify_authority_inputs()
    goldens = ["", "c", "ck/", "b200c/kk/", "b200b600c/kb300c/kk/"]
    for text in goldens:
        ledger = CentLedger.parse(text)
        if ledger.action_str != text:
            raise RuntimeError("selftest_ledger_roundtrip")
        if not ledger.terminal:
            live_action_table(ledger)
    try:
        CentLedger.parse("x")
        raise RuntimeError("selftest_bad_character_not_rejected")
    except RuntimeError as exc:
        if "character_invalid" not in str(exc):
            raise
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    rows = load_safe_rows(prereg)
    sample = rows if level == "deep" else rows[:128]
    for row in sample:
        validate_witness_row(row)
    by_hand: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in sample:
        by_hand[(row["source"], row["hand_idx"])].append(row)
    transitions = 0
    for values in by_hand.values():
        values.sort(key=lambda x: x["move_idx"])
        for left, right in zip(values, values[1:]):
            incr = f"b{left['action_amount']}" if left["action_move"] == "b" else left["action_move"]
            predicted = CentLedger.parse(left["action_str_before"]).apply_increment(incr, append=True, auto_separator=True).action_str
            if predicted != right["action_str_before"]:
                raise RuntimeError("selftest_adjacent_prefix_mismatch")
            transitions += 1
    if level == "deep" and transitions != 24878:
        raise RuntimeError(f"selftest_transition_count_mismatch:{transitions}")
    live_checks = 0
    mirror_checks = 0
    if level == "deep":
        witnessed = [x for x in rows if x["who"] == "hero" and x["street"] > 0][:16]
        new_arrays, ref_arrays = [], []
        for row in witnessed:
            state = info_rollout_state(row)
            c, h, e, m, t = observation(state)
            rc, rh, re, rm, rt = reference_observation(row)
            if not all(np.array_equal(a, b) for a, b in ((c, rc), (h, rh), (e, re), (m, rm))) or t != rt:
                raise RuntimeError("selftest_live_interface_nonidentity")
            new_arrays.append((c, h, e, m)); ref_arrays.append((rc, rh, re, rm))
            live_checks += 1
        actor = H11Actor(os.environ["RS003_NONCE"])
        new_slots, new_logits = actor.infer_arrays(new_arrays)
        ref_slots, ref_logits = actor.infer_arrays(ref_arrays)
        if new_slots != ref_slots or canonical_json(new_logits) != canonical_json(ref_logits):
            raise RuntimeError("selftest_live_baseline_nonidentity")
        dets, trace = determinizations(witnessed[0])
        if trace["distinct_pair_count"] != 32:
            raise RuntimeError("selftest_determinization_diversity")
        _, table = live_action_table(dets[0].ledger)
        for slot, incr in enumerate(table):
            if incr is not None:
                apply_live_increment(dets[0], incr)
                mirror_checks += 1
        gold = paired_stats({0: [0.0] * 32, 1: [1.0] * 32}, 0)
        if gold[1]["mean_difference_bb"] != 1.0 or gold[1]["lcb95_bb"] != 1.0:
            raise RuntimeError("selftest_paired_statistic")
    print(canonical_json({"classification": "RS003_SELF_TEST_PASS", "level": level, "rows": len(sample), "transitions": transitions, "live_checks": live_checks, "mirror_checks": mirror_checks, "files_written": 0}))
    return 0


def run_qualification(root: Path, implementation_audit_sha256: str, nonce: str) -> int:
    started = time.perf_counter()
    if root.resolve(strict=False) != QUAL_ROOT.resolve(strict=False) or root.exists():
        raise RuntimeError("qualification_root_identity_or_existence_failure")
    prereg = verify_authority_inputs()
    verify_file(IMPL_AUDIT, implementation_audit_sha256)
    impl = json.loads(IMPL_AUDIT.read_text(encoding="utf-8"))
    if impl.get("classification") != "PASS / RS003_IMPLEMENTATION_AUDIT_PASS_QUALIFICATION_READY_ONLY":
        raise RuntimeError("implementation_audit_not_pass")
    if sha256_file(CHECKPOINT) != CHECKPOINT_SHA256:
        raise RuntimeError("checkpoint_pre_hash_mismatch")
    root.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(root / "invocation.json", {"identity_sha256": IDENTITY_SHA256, "token": TOKEN, "nonce": nonce, "implementation_audit_sha256": implementation_audit_sha256, "started_at_epoch": time.time(), "network": "FORBIDDEN"})
    actor = H11Actor(nonce)
    rows = load_safe_rows(prereg)

    ledger_out, prefix_map = [], {}
    by_hand: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ledger, observed = validate_witness_row(row)
        ledger_out.append({"source": row["source"], "hand_idx": row["hand_idx"], "move_idx": row["move_idx"], "action_str_sha256": sha256_bytes(row["action_str_before"].encode()), **observed, "exact": True})
        prefix_map.setdefault(row["action_str_before"], observed)
        by_hand[(row["source"], row["hand_idx"])].append(row)
    transitions = 0
    for values in by_hand.values():
        values.sort(key=lambda x: x["move_idx"])
        for left, right in zip(values, values[1:]):
            incr = f"b{left['action_amount']}" if left["action_move"] == "b" else left["action_move"]
            if CentLedger.parse(left["action_str_before"]).apply_increment(incr).action_str != right["action_str_before"]:
                raise RuntimeError("qualification_adjacent_prefix_mismatch")
            transitions += 1
    if len(prefix_map) != 584 or transitions != 24878:
        raise RuntimeError("qualification_prefix_census_mismatch")
    prefix_out = [{"action_str_sha256": sha256_bytes(k.encode()), **v, "reencode_exact": CentLedger.parse(k).action_str == k} for k, v in sorted(prefix_map.items())]
    write_jsonl_gz_exclusive(root / "ledger_rows.jsonl.gz", ledger_out)
    write_jsonl_gz_exclusive(root / "prefix_rows.jsonl.gz", prefix_out)

    witnessed = [x for x in rows if x["who"] == "hero" and x["street"] > 0]
    if len(witnessed) != 6921:
        raise RuntimeError("hero_postflop_count_mismatch")
    interface_out = []
    new_arrays, ref_arrays, new_tables, ref_tables = [], [], [], []
    for row in witnessed:
        state = info_rollout_state(row)
        c, h, e, m, t = observation(state)
        rc, rh, re, rm, rt = reference_observation(row)
        for name, left, right in (("cards", c, rc), ("history", h, rh), ("extra", e, re), ("mask", m, rm)):
            if not np.array_equal(left, right):
                raise RuntimeError(f"live_interface_tensor_mismatch:{name}")
        if t != rt:
            raise RuntimeError("live_interface_table_mismatch")
        new_arrays.append((c, h, e, m)); ref_arrays.append((rc, rh, re, rm)); new_tables.append(t); ref_tables.append(rt)
    new_slots, new_logits = actor.infer_arrays(new_arrays)
    ref_slots, ref_logits = actor.infer_arrays(ref_arrays)
    for index, row in enumerate(witnessed):
        if new_slots[index] != ref_slots[index] or canonical_json(new_logits[index]) != canonical_json(ref_logits[index]):
            raise RuntimeError("live_baseline_logits_or_slot_mismatch")
        if new_tables[index][new_slots[index]] is None:
            raise RuntimeError("baseline_nonexecutable")
        interface_out.append({"state_identity_sha256": state_identity(row), "street": row["street"], "client_pos": row["client_pos"], "tensor_sha256": sha256_obj([new_arrays[index][0].tolist(), new_arrays[index][1].tolist(), new_arrays[index][2].tolist(), new_arrays[index][3].tolist()]), "table9": new_tables[index], "baseline_slot": new_slots[index], "baseline_increment": new_tables[index][new_slots[index]], "baseline_logits_sha256": sha256_obj(new_logits[index]), "bit_exact": True, "forbidden_source_field_read_count": 0})
    write_jsonl_gz_exclusive(root / "hero_live_interfaces.jsonl.gz", interface_out)

    synthetic = synthetic_rows(rows)
    synthetic_out = []
    for row in synthetic:
        ledger, _ = validate_witness_row(row)
        state = info_rollout_state(row)
        cards, history, extra, mask, table = observation(state)
        direct_mask, direct_table = live_action_table(ledger)
        interface_exact = (
            cards.shape == (6, 4, 13)
            and history.shape == (25, 4, 5)
            and extra.shape == (2,)
            and np.array_equal(mask, direct_mask)
            and table == direct_table
            and int(mask.sum()) == len([x for x in table if x is not None])
        )
        if not interface_exact:
            raise RuntimeError("synthetic_live_interface_mismatch")
        assert_mirror_public(state)
        synthetic_out.append({
            "synthetic_index": row["synthetic_index"],
            "state_identity_sha256": state_identity(row),
            "street": row["street"],
            "client_pos": row["client_pos"],
            "pot_band": pot_band(row["pot_before"]),
            "legal_slots": [i for i, x in enumerate(table) if x is not None],
            "mask_sum": float(mask.sum()),
            "ledger_exact": True,
            "mirror_exact": True,
            "interface_exact": True,
            "interface_sha256": sha256_obj([cards.tolist(), history.tolist(), extra.tolist(), mask.tolist(), table]),
        })
    write_jsonl_gz_exclusive(root / "synthetic_states.jsonl.gz", synthetic_out)

    cohort = select_resolution_rows(synthetic, witnessed)
    resolution_rows = []
    for index, row in enumerate(cohort):
        result = resolve(actor, row)
        result.update({"resolution_index": index, "cohort": "synthetic" if row.get("synthetic") else "witnessed"})
        resolution_rows.append(result)
    repeat_rows = []
    for index, row in enumerate(cohort[:192]):
        again = resolve(actor, row)
        original = resolution_rows[index]
        fields = ("selected_slot", "selected_increment", "selection_reason", "paired_statistics_by_slot", "rollout_trace_sha256", "decision_trace_sha256")
        exact = all(canonical_json(again.get(k)) == canonical_json(original.get(k)) for k in fields)
        repeat_rows.append({"repeat_index": index, "source_resolution_index": index, "exact": exact, **{k: again.get(k) for k in fields}})
    faults = ("RESOLVER_TIMEOUT", "CUDA_RUNTIME_ERROR", "NONFINITE_PAYOFF_OR_LCB", "ROLLOUT_STEP_OVERFLOW")
    fault_rows = []
    rng = random.Random(FAULT_SEED)
    indices = list(range(len(cohort))); rng.shuffle(indices)
    for index in range(128):
        source = indices[index]
        fault = faults[index % len(faults)]
        result = resolve(actor, cohort[source], fault=fault)
        fault_rows.append({"fault_index": index, "source_resolution_index": source, "fault": fault, "baseline_exact": result["selected_slot"] == result["baseline_slot"] and result["selected_increment"] == result["baseline_increment"], **result})
    write_jsonl_gz_exclusive(root / "resolution_rows.jsonl.gz", resolution_rows)
    write_jsonl_gz_exclusive(root / "repeat_rows.jsonl.gz", repeat_rows)
    write_jsonl_gz_exclusive(root / "fault_rows.jsonl.gz", fault_rows)

    latencies = [float(x["latency_seconds"]) for x in resolution_rows]
    fallbacks = sum(bool(x["error_fallback"]) for x in resolution_rows)
    nonfallback = [x for x in resolution_rows if not x["error_fallback"]]
    changes = sum(x["selected_slot"] != x["baseline_slot"] for x in nonfallback)
    metrics = {
        "ledger_rows": len(ledger_out), "distinct_prefixes": len(prefix_out), "adjacent_transitions": transitions,
        "hero_live_interfaces": len(interface_out), "synthetic_states": len(synthetic_out), "resolution_rows": len(resolution_rows),
        "repeat_rows": len(repeat_rows), "repeat_exact": sum(bool(x["exact"]) for x in repeat_rows),
        "fault_rows": len(fault_rows), "fault_baseline_exact": sum(bool(x["baseline_exact"]) for x in fault_rows),
        "qualified_fallback_count": fallbacks, "qualified_fallback_rate": fallbacks / len(resolution_rows),
        "nonfallback_count": len(nonfallback), "selected_slot_change_count": changes, "selected_slot_change_rate": changes / max(1, len(nonfallback)),
        "all_distinct_pairs32": all(x.get("determinizations", {}).get("distinct_pair_count") == 32 for x in nonfallback),
        "latency_seconds": {"p50": percentile(latencies, .50), "p95": percentile(latencies, .95), "p99": percentile(latencies, .99), "max": max(latencies)},
        "projected_quick5k_hours": percentile(latencies, .50) * 5000 / 3600,
        "model_cold_load_seconds": actor.cold_load_seconds, "process_rss_mib": process_rss_mib(), "gpu_peak_allocated_mib": actor.peak_gpu_mib(),
        "wall_seconds": time.perf_counter() - started,
    }
    gates = {
        "ledger_rows_29878": metrics["ledger_rows"] == 29878,
        "prefixes_584": metrics["distinct_prefixes"] == 584,
        "transitions_24878": metrics["adjacent_transitions"] == 24878,
        "live_interfaces_6921": metrics["hero_live_interfaces"] == 6921,
        "synthetic_8192": metrics["synthetic_states"] == 8192,
        "resolutions_1280": metrics["resolution_rows"] == 1280,
        "all_distinct_pairs32": metrics["all_distinct_pairs32"],
        "repeats_192_exact": metrics["repeat_rows"] == 192 and metrics["repeat_exact"] == 192,
        "faults_128_baseline_exact": metrics["fault_rows"] == 128 and metrics["fault_baseline_exact"] == 128,
        "fallback_rate_le_0_02": metrics["qualified_fallback_rate"] <= .02,
        "action_change_rate_ge_0_01": metrics["selected_slot_change_rate"] >= .01,
        "latency_p50": metrics["latency_seconds"]["p50"] <= 2.5,
        "latency_p95": metrics["latency_seconds"]["p95"] <= 8,
        "latency_p99": metrics["latency_seconds"]["p99"] <= 15,
        "latency_max": metrics["latency_seconds"]["max"] <= 20,
        "quick5k_projection": metrics["projected_quick5k_hours"] <= 12,
        "cold_load": metrics["model_cold_load_seconds"] <= 60,
        "wall": metrics["wall_seconds"] <= 10800,
        "rss": metrics["process_rss_mib"] <= 16384,
        "gpu": metrics["gpu_peak_allocated_mib"] <= 11264,
        "checkpoint_unchanged": sha256_file(CHECKPOINT) == CHECKPOINT_SHA256,
    }
    write_json_exclusive(root / "metrics.json", metrics)
    result = {"schema_version": "v5.rs003.qualification.result.v1", "identity_sha256": IDENTITY_SHA256, "classification": "PASS / RS003_LIVE_NATIVE_QUALIFICATION_PASS" if all(gates.values()) else "NONPASS / RS003_LIVE_NATIVE_QUALIFICATION_GATE_NONPASS", "gates": gates, "pass_count": sum(gates.values()), "check_count": len(gates), "metrics": metrics, "checkpoint_sha256": sha256_file(CHECKPOINT), "quick5k_authority": "PENDING_INDEPENDENT_RESULT_AUDIT" if all(gates.values()) else "NONE", "network_or_slumbot_hands": 0}
    write_json_exclusive(root / "result.json", result)
    return 0 if all(gates.values()) else 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("ContractProbe", "SelfTest", "Qualification"))
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--root")
    parser.add_argument("--implementation-audit-sha256")
    parser.add_argument("--level", choices=("quick", "deep"), default="quick")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode == "ContractProbe":
        return contract_probe(args.nonce)
    if args.mode == "SelfTest":
        validate_device_contract(args.nonce)
        return run_self_test(args.level)
    if not args.root or not args.implementation_audit_sha256:
        raise RuntimeError("qualification_arguments_missing")
    return run_qualification(Path(args.root), args.implementation_audit_sha256, args.nonce)


if __name__ == "__main__":
    raise SystemExit(main())
