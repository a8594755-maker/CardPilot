"""Neutral exact-cent heads-up no-limit public-state engine for LRFT.

This module is deliberately limited to public poker mechanics.  It owns no RNG,
deck, hole cards, model, filesystem output, or network interface.  Chance cards and
showdown comparison are supplied explicitly by the caller.

Amounts are integer cents.  A raise amount is always the player's total commitment
on the current street ("raise to"), never an increment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction
import hashlib
import json
import re
from typing import Final, Iterable


IMPLEMENTATION_IDENTITY: Final[str] = (
    "a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704"
)

SLOT_FRACTIONS: Final[tuple[Fraction, ...]] = (
    Fraction(33, 100),
    Fraction(1, 2),
    Fraction(67, 100),
    Fraction(3, 4),
    Fraction(1, 1),
    Fraction(3, 2),
)
PREFLOP_SOURCE_FRACTIONS: Final[tuple[Fraction, ...]] = (
    Fraction(1, 2),
    Fraction(1, 1),
    Fraction(3, 2),
)
NUM_SLOTS: Final[int] = 9

DECISION: Final[str] = "DECISION"
CHANCE: Final[str] = "CHANCE"
SHOWDOWN_PENDING: Final[str] = "SHOWDOWN_PENDING"
TERMINAL: Final[str] = "TERMINAL"

FOLD: Final[str] = "FOLD"
CHECK: Final[str] = "CHECK"
CALL: Final[str] = "CALL"
RAISE_TO: Final[str] = "RAISE_TO"

_ACTION_RE: Final[re.Pattern[str]] = re.compile(r"(?:f|k|c|b[1-9][0-9]*)\Z")


def _require_exact_int(name: str, value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}_must_be_int_at_least_{minimum}")
    return value


def round_fraction_ties_even(value: int, fraction: Fraction) -> int:
    """Return ``value * fraction`` rounded to nearest integer, ties to even."""
    _require_exact_int("fraction_value", value)
    numerator = value * fraction.numerator
    denominator = fraction.denominator
    quotient, remainder = divmod(numerator, denominator)
    doubled = remainder * 2
    if doubled < denominator:
        return quotient
    if doubled > denominator:
        return quotient + 1
    return quotient if quotient % 2 == 0 else quotient + 1


@dataclass(frozen=True)
class PublicRules:
    """Fixed public rules and initial chip ledger."""

    starting_stacks: tuple[int, int] = (20_000, 20_000)
    small_blind: int = 50
    big_blind: int = 100
    postflop_first_actor: int = 0
    preflop_first_actor: int = 1

    def validate(self) -> None:
        if (
            not isinstance(self.starting_stacks, tuple)
            or len(self.starting_stacks) != 2
        ):
            raise ValueError("starting_stacks_shape")
        for index, amount in enumerate(self.starting_stacks):
            _require_exact_int(f"starting_stack_{index}", amount, minimum=1)
        _require_exact_int("small_blind", self.small_blind, minimum=1)
        _require_exact_int("big_blind", self.big_blind, minimum=1)
        if self.small_blind >= self.big_blind:
            raise ValueError("blind_order")
        if self.big_blind > self.starting_stacks[0]:
            raise ValueError("big_blind_exceeds_stack")
        if self.small_blind > self.starting_stacks[1]:
            raise ValueError("small_blind_exceeds_stack")
        if self.postflop_first_actor not in (0, 1):
            raise ValueError("postflop_first_actor")
        if self.preflop_first_actor not in (0, 1):
            raise ValueError("preflop_first_actor")
        if self.postflop_first_actor == self.preflop_first_actor:
            raise ValueError("heads_up_position_collision")


@dataclass(frozen=True)
class PublicAction:
    kind: str
    amount_to: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in (FOLD, CHECK, CALL, RAISE_TO):
            raise ValueError("action_kind")
        if self.kind == RAISE_TO:
            _require_exact_int("amount_to", self.amount_to, minimum=1)
        elif self.amount_to is not None:
            raise ValueError("passive_action_has_amount")

    @classmethod
    def parse(cls, raw: str) -> "PublicAction":
        if not isinstance(raw, str) or _ACTION_RE.fullmatch(raw) is None:
            raise ValueError("public_action_grammar")
        if raw == "f":
            return cls(FOLD)
        if raw == "k":
            return cls(CHECK)
        if raw == "c":
            return cls(CALL)
        return cls(RAISE_TO, int(raw[1:]))

    def raw(self) -> str:
        if self.kind == FOLD:
            return "f"
        if self.kind == CHECK:
            return "k"
        if self.kind == CALL:
            return "c"
        return f"b{self.amount_to}"


@dataclass(frozen=True)
class ActionRecord:
    street: int
    actor: int
    action: PublicAction
    paid: int
    full_raise: bool = False

    def __post_init__(self) -> None:
        if self.street not in range(4):
            raise ValueError("record_street")
        if self.actor not in (0, 1):
            raise ValueError("record_actor")
        _require_exact_int("record_paid", self.paid)
        if type(self.full_raise) is not bool:
            raise ValueError("record_full_raise")


@dataclass(frozen=True)
class LegalActionSet:
    """Finite passive actions plus exact legal raise-to interval metadata."""

    fold: bool
    check: bool
    call: bool
    call_amount: int
    minimum_full_raise_to: int | None
    maximum_raise_to: int | None
    short_all_in_to: int | None

    def contains(self, action: PublicAction) -> bool:
        if action.kind == FOLD:
            return self.fold
        if action.kind == CHECK:
            return self.check
        if action.kind == CALL:
            return self.call
        target = action.amount_to
        if target is None or self.maximum_raise_to is None:
            return False
        if target == self.short_all_in_to:
            return True
        return (
            self.minimum_full_raise_to is not None
            and self.minimum_full_raise_to <= target <= self.maximum_raise_to
        )


@dataclass(frozen=True)
class PolicyTable:
    """The exact nine-slot V5.5 public action surface."""

    mask: tuple[int, ...]
    slots: tuple[PublicAction | None, ...]

    def __post_init__(self) -> None:
        if len(self.mask) != NUM_SLOTS or len(self.slots) != NUM_SLOTS:
            raise ValueError("policy_table_shape")
        if any(value not in (0, 1) for value in self.mask):
            raise ValueError("policy_mask_binary")
        if any((slot is None) != (self.mask[index] == 0) for index, slot in enumerate(self.slots)):
            raise ValueError("policy_mask_table_disagreement")


@dataclass(frozen=True)
class ExactCentPublicState:
    """Immutable arbitrary-root public state.

    ``showdown_result`` is from player 0's perspective: +1 win, 0 tie, -1 loss.
    It is populated only by :meth:`resolve_showdown`.
    """

    rules: PublicRules
    street: int
    phase: str
    actor: int | None
    board: tuple[int, ...]
    stacks: tuple[int, int]
    total_commitments: tuple[int, int]
    street_commitments: tuple[int, int]
    current_bet: int
    minimum_full_raise_increment: int
    raise_right_open: tuple[bool, bool]
    acted_since_full_raise: tuple[bool, bool]
    checks_in_row: int
    big_blind_option_open: bool
    history: tuple[ActionRecord, ...] = field(default_factory=tuple)
    chance_to_street: int | None = None
    chance_cards_required: int = 0
    all_in_runout: bool = False
    terminal_kind: str = "NONE"
    folded_player: int | None = None
    showdown_result: int | None = None

    @classmethod
    def new_hand(cls, rules: PublicRules | None = None) -> "ExactCentPublicState":
        rules = rules or PublicRules()
        rules.validate()
        big_blind_player = rules.postflop_first_actor
        small_blind_player = rules.preflop_first_actor
        totals = [0, 0]
        totals[big_blind_player] = rules.big_blind
        totals[small_blind_player] = rules.small_blind
        stacks = (
            rules.starting_stacks[0] - totals[0],
            rules.starting_stacks[1] - totals[1],
        )
        return cls(
            rules=rules,
            street=0,
            phase=DECISION,
            actor=rules.preflop_first_actor,
            board=(),
            stacks=stacks,
            total_commitments=(totals[0], totals[1]),
            street_commitments=(totals[0], totals[1]),
            current_bet=max(totals),
            minimum_full_raise_increment=rules.big_blind,
            raise_right_open=(True, True),
            acted_since_full_raise=(False, False),
            checks_in_row=0,
            big_blind_option_open=True,
        ).validated()

    @classmethod
    def hydrate(cls, **fields: object) -> "ExactCentPublicState":
        """Construct and fully validate an arbitrary solver-created state."""
        return cls(**fields).validated()

    @property
    def pot(self) -> int:
        return self.total_commitments[0] + self.total_commitments[1]

    @property
    def to_call(self) -> int:
        if self.phase != DECISION or self.actor not in (0, 1):
            return 0
        return max(0, self.current_bet - self.street_commitments[self.actor])

    @property
    def is_terminal(self) -> bool:
        return self.phase == TERMINAL

    def validated(self) -> "ExactCentPublicState":
        self.rules.validate()
        if self.street not in range(4):
            raise ValueError("street")
        if self.phase not in (DECISION, CHANCE, SHOWDOWN_PENDING, TERMINAL):
            raise ValueError("phase")
        if not isinstance(self.board, tuple):
            raise ValueError("board_type")
        expected_board = (0, 3, 4, 5)[self.street]
        for card in self.board:
            if type(card) is not int or not 0 <= card < 52:
                raise ValueError("board_card")
        if len(set(self.board)) != len(self.board):
            raise ValueError("duplicate_board_card")
        if self.phase != CHANCE and len(self.board) != expected_board:
            raise ValueError("board_street_mismatch")
        if self.phase == CHANCE and len(self.board) not in (0, 3, 4):
            raise ValueError("chance_board_length")

        for name, pair in (
            ("stacks", self.stacks),
            ("total_commitments", self.total_commitments),
            ("street_commitments", self.street_commitments),
        ):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError(f"{name}_shape")
            for index, amount in enumerate(pair):
                _require_exact_int(f"{name}_{index}", amount)
        for player in (0, 1):
            if self.stacks[player] + self.total_commitments[player] != self.rules.starting_stacks[player]:
                raise ValueError("chip_conservation")
            if self.street_commitments[player] > self.total_commitments[player]:
                raise ValueError("street_commitment_exceeds_total")
        _require_exact_int("current_bet", self.current_bet)
        if self.current_bet != max(self.street_commitments):
            raise ValueError("current_bet_identity")
        _require_exact_int(
            "minimum_full_raise_increment",
            self.minimum_full_raise_increment,
            minimum=1,
        )
        if (
            not isinstance(self.raise_right_open, tuple)
            or len(self.raise_right_open) != 2
            or any(type(value) is not bool for value in self.raise_right_open)
        ):
            raise ValueError("raise_right_open_shape")
        if (
            not isinstance(self.acted_since_full_raise, tuple)
            or len(self.acted_since_full_raise) != 2
            or any(type(value) is not bool for value in self.acted_since_full_raise)
        ):
            raise ValueError("acted_since_full_raise_shape")
        _require_exact_int("checks_in_row", self.checks_in_row)
        if self.checks_in_row > 1:
            raise ValueError("checks_in_row_range")
        if type(self.big_blind_option_open) is not bool:
            raise ValueError("big_blind_option_open_type")
        if self.big_blind_option_open and self.street != 0:
            raise ValueError("big_blind_option_outside_preflop")
        if not isinstance(self.history, tuple) or any(
            not isinstance(record, ActionRecord) for record in self.history
        ):
            raise ValueError("history_type")

        _require_exact_int("chance_cards_required", self.chance_cards_required)
        if type(self.all_in_runout) is not bool:
            raise ValueError("all_in_runout_type")
        if self.phase == DECISION:
            if self.actor not in (0, 1):
                raise ValueError("decision_actor")
            if self.chance_to_street is not None or self.chance_cards_required != 0:
                raise ValueError("decision_has_chance")
            if self.stacks[self.actor] == 0:
                raise ValueError("zero_stack_actor")
        else:
            if self.actor is not None:
                raise ValueError("nondecision_actor")
        if self.phase == CHANCE:
            if self.chance_to_street != self.street + 1 or self.chance_to_street not in (1, 2, 3):
                raise ValueError("chance_target")
            expected_required = 3 if self.chance_to_street == 1 else 1
            if self.chance_cards_required != expected_required:
                raise ValueError("chance_card_count")
        elif self.chance_to_street is not None or self.chance_cards_required != 0:
            raise ValueError("nonchance_has_chance")

        if self.phase == SHOWDOWN_PENDING:
            if self.terminal_kind != "NONE" or self.showdown_result is not None:
                raise ValueError("premature_showdown_result")
            if len(self.board) != 5:
                raise ValueError("showdown_board")
        elif self.phase == TERMINAL:
            if self.terminal_kind == "FOLD":
                if self.folded_player not in (0, 1) or self.showdown_result is not None:
                    raise ValueError("fold_terminal_fields")
            elif self.terminal_kind == "SHOWDOWN":
                if self.folded_player is not None or self.showdown_result not in (-1, 0, 1):
                    raise ValueError("showdown_terminal_fields")
                if len(self.board) != 5:
                    raise ValueError("terminal_showdown_board")
            else:
                raise ValueError("terminal_kind")
        elif (
            self.terminal_kind != "NONE"
            or self.folded_player is not None
            or self.showdown_result is not None
        ):
            raise ValueError("nonterminal_terminal_fields")
        return self

    def canonical_payload(self) -> dict[str, object]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("ascii")).hexdigest()

    @classmethod
    def from_canonical_json(cls, encoded: str) -> "ExactCentPublicState":
        """Hydrate an exact state from :meth:`canonical_json` output."""
        if not isinstance(encoded, str):
            raise ValueError("canonical_json_type")
        payload = json.loads(encoded)
        if not isinstance(payload, dict):
            raise ValueError("canonical_json_object")
        expected = {
            "rules",
            "street",
            "phase",
            "actor",
            "board",
            "stacks",
            "total_commitments",
            "street_commitments",
            "current_bet",
            "minimum_full_raise_increment",
            "raise_right_open",
            "acted_since_full_raise",
            "checks_in_row",
            "big_blind_option_open",
            "history",
            "chance_to_street",
            "chance_cards_required",
            "all_in_runout",
            "terminal_kind",
            "folded_player",
            "showdown_result",
        }
        if set(payload) != expected:
            raise ValueError("canonical_json_fields")
        rules_payload = payload["rules"]
        if not isinstance(rules_payload, dict):
            raise ValueError("canonical_rules_object")
        rules = PublicRules(
            starting_stacks=tuple(rules_payload["starting_stacks"]),
            small_blind=rules_payload["small_blind"],
            big_blind=rules_payload["big_blind"],
            postflop_first_actor=rules_payload["postflop_first_actor"],
            preflop_first_actor=rules_payload["preflop_first_actor"],
        )
        history_payload = payload["history"]
        if not isinstance(history_payload, list):
            raise ValueError("canonical_history_array")
        history: list[ActionRecord] = []
        for item in history_payload:
            if not isinstance(item, dict) or set(item) != {
                "street", "actor", "action", "paid", "full_raise"
            }:
                raise ValueError("canonical_history_record")
            action_payload = item["action"]
            if not isinstance(action_payload, dict) or set(action_payload) != {
                "kind", "amount_to"
            }:
                raise ValueError("canonical_history_action")
            history.append(
                ActionRecord(
                    street=item["street"],
                    actor=item["actor"],
                    action=PublicAction(
                        action_payload["kind"], action_payload["amount_to"]
                    ),
                    paid=item["paid"],
                    full_raise=item["full_raise"],
                )
            )
        return cls.hydrate(
            rules=rules,
            street=payload["street"],
            phase=payload["phase"],
            actor=payload["actor"],
            board=tuple(payload["board"]),
            stacks=tuple(payload["stacks"]),
            total_commitments=tuple(payload["total_commitments"]),
            street_commitments=tuple(payload["street_commitments"]),
            current_bet=payload["current_bet"],
            minimum_full_raise_increment=payload["minimum_full_raise_increment"],
            raise_right_open=tuple(payload["raise_right_open"]),
            acted_since_full_raise=tuple(payload["acted_since_full_raise"]),
            checks_in_row=payload["checks_in_row"],
            big_blind_option_open=payload["big_blind_option_open"],
            history=tuple(history),
            chance_to_street=payload["chance_to_street"],
            chance_cards_required=payload["chance_cards_required"],
            all_in_runout=payload["all_in_runout"],
            terminal_kind=payload["terminal_kind"],
            folded_player=payload["folded_player"],
            showdown_result=payload["showdown_result"],
        )

    def legal_actions(self) -> LegalActionSet:
        if self.phase != DECISION or self.actor not in (0, 1):
            return LegalActionSet(False, False, False, 0, None, None, None)
        player = self.actor
        other = 1 - player
        facing = self.to_call > 0
        call_amount = min(self.to_call, self.stacks[player]) if facing else 0
        minimum: int | None = None
        maximum: int | None = None
        short_all_in: int | None = None
        maximum_candidate = self.street_commitments[player] + self.stacks[player]
        may_raise = (
            self.raise_right_open[player]
            and self.stacks[other] > 0
            and self.stacks[player] > self.to_call
            and maximum_candidate > self.current_bet
        )
        if may_raise:
            threshold = (
                self.current_bet + self.minimum_full_raise_increment
                if self.current_bet > 0
                else self.minimum_full_raise_increment
            )
            maximum = maximum_candidate
            if maximum >= threshold:
                minimum = threshold
            else:
                short_all_in = maximum
        return LegalActionSet(
            fold=facing,
            check=not facing,
            call=facing,
            call_amount=call_amount,
            minimum_full_raise_to=minimum,
            maximum_raise_to=maximum,
            short_all_in_to=short_all_in,
        )

    def public_legality(self, action: PublicAction | str) -> tuple[bool, str]:
        try:
            parsed = PublicAction.parse(action) if isinstance(action, str) else action
        except (TypeError, ValueError):
            return False, "GRAMMAR"
        if not isinstance(parsed, PublicAction):
            return False, "ACTION_TYPE"
        if self.phase != DECISION:
            return False, "NOT_DECISION"
        legal = self.legal_actions()
        if legal.contains(parsed):
            if parsed.kind != RAISE_TO:
                return True, parsed.kind
            assert parsed.amount_to is not None
            if parsed.amount_to == legal.short_all_in_to:
                return True, "SHORT_ALL_IN"
            if parsed.amount_to == legal.maximum_raise_to:
                return True, "FULL_ALL_IN"
            return True, "FULL_BET_OR_RAISE"
        if parsed.kind == FOLD:
            return False, "FOLD_NOT_FACING"
        if parsed.kind == CHECK:
            return False, "CHECK_FACING"
        if parsed.kind == CALL:
            return False, "CALL_NOT_FACING"
        assert parsed.amount_to is not None
        if self.actor is None:
            return False, "NOT_DECISION"
        player = self.actor
        other = 1 - player
        maximum = self.street_commitments[player] + self.stacks[player]
        if not self.raise_right_open[player]:
            return False, "RAISE_RIGHT_CLOSED"
        if self.stacks[other] == 0:
            return False, "OPPONENT_ALL_IN"
        if parsed.amount_to <= self.current_bet:
            return False, "TARGET_NOT_ABOVE_CURRENT_BET"
        if parsed.amount_to > maximum:
            return False, "TARGET_EXCEEDS_STACK"
        return False, "UNDER_MINIMUM_NON_ALL_IN"

    def policy_table(self) -> PolicyTable:
        slots: list[PublicAction | None] = [None] * NUM_SLOTS
        if self.phase != DECISION or self.actor is None:
            return PolicyTable((0,) * NUM_SLOTS, tuple(slots))
        legal = self.legal_actions()
        if legal.fold:
            slots[0] = PublicAction(FOLD)
        slots[1] = PublicAction(CALL if legal.call else CHECK)

        if legal.maximum_raise_to is not None:
            base = self.pot + self.to_call if self.to_call > 0 else self.pot
            committed = self.street_commitments[self.actor]
            source_fractions = (
                PREFLOP_SOURCE_FRACTIONS if self.street == 0 else SLOT_FRACTIONS
            )
            # Reproduce the frozen V5.5 executable-table owner semantics: first
            # enumerate its source sizing grid, map each exact raise-to amount by
            # amount_to/current_pot to the closest of the six policy fractions,
            # then retain the closest action when multiple source sizes collide.
            # Public poker legality remains authoritative, so an under-minimum
            # legacy source amount is not admitted.
            for fraction in source_fractions:
                if self.to_call > 0:
                    target = self.current_bet + round_fraction_ties_even(base, fraction)
                else:
                    target = committed + round_fraction_ties_even(self.pot, fraction)
                if target >= legal.maximum_raise_to:
                    continue
                candidate = PublicAction(RAISE_TO, target)
                if not legal.contains(candidate):
                    continue
                observed_fraction = Fraction(target, max(self.pot, 1))
                owner = min(
                    range(2, 8),
                    key=lambda slot: (
                        abs(observed_fraction - SLOT_FRACTIONS[slot - 2]),
                        slot,
                    ),
                )
                incumbent = slots[owner]
                nominal_target = round_fraction_ties_even(
                    max(self.pot, 1), SLOT_FRACTIONS[owner - 2]
                )
                if (
                    incumbent is None
                    or abs(target - nominal_target)
                    < abs(incumbent.amount_to - nominal_target)
                ):
                    slots[owner] = candidate
            slots[8] = PublicAction(RAISE_TO, legal.maximum_raise_to)
        elif legal.short_all_in_to is not None:
            slots[8] = PublicAction(RAISE_TO, legal.short_all_in_to)

        mask = tuple(1 if action is not None else 0 for action in slots)
        table = PolicyTable(mask, tuple(slots))
        for action in table.slots:
            if action is not None and not self.legal_actions().contains(action):
                raise AssertionError("policy_action_not_public_legal")
        return table

    def apply_policy_slot(self, slot: int) -> "ExactCentPublicState":
        if type(slot) is not int or not 0 <= slot < NUM_SLOTS:
            raise ValueError("policy_slot_range")
        action = self.policy_table().slots[slot]
        if action is None:
            raise ValueError("policy_slot_null")
        return self.apply_public_action(action)

    def apply_public_action(
        self, action: PublicAction | str
    ) -> "ExactCentPublicState":
        parsed = PublicAction.parse(action) if isinstance(action, str) else action
        legal, reason = self.public_legality(parsed)
        if not legal:
            raise ValueError(f"illegal_public_action:{reason}")
        assert self.actor is not None
        player = self.actor
        other = 1 - player

        if parsed.kind == FOLD:
            record = ActionRecord(self.street, player, parsed, 0)
            return replace(
                self,
                phase=TERMINAL,
                actor=None,
                history=self.history + (record,),
                terminal_kind="FOLD",
                folded_player=player,
                big_blind_option_open=False,
            ).validated()

        if parsed.kind == CHECK:
            record = ActionRecord(self.street, player, parsed, 0)
            updated = replace(
                self,
                history=self.history + (record,),
                acted_since_full_raise=_set_pair(
                    self.acted_since_full_raise, player, True
                ),
            )
            closes = (
                self.checks_in_row == 1
                or (
                    self.street == 0
                    and self.big_blind_option_open
                    and player == self.rules.postflop_first_actor
                )
            )
            if closes:
                return updated._close_street()
            return replace(
                updated,
                actor=other,
                checks_in_row=1,
            ).validated()

        if parsed.kind == CALL:
            paid = min(self.to_call, self.stacks[player])
            updated = self._pay(player, paid)
            record = ActionRecord(self.street, player, parsed, paid)
            updated = replace(
                updated,
                history=updated.history + (record,),
                acted_since_full_raise=_set_pair(
                    updated.acted_since_full_raise, player, True
                ),
            )
            initial_small_blind_completion = (
                self.street == 0
                and self.big_blind_option_open
                and player == self.rules.preflop_first_actor
                and not any(record.street == 0 for record in self.history)
            )
            if initial_small_blind_completion and all(stack > 0 for stack in updated.stacks):
                return replace(
                    updated,
                    actor=other,
                    checks_in_row=0,
                    big_blind_option_open=True,
                ).validated()
            if any(stack == 0 for stack in updated.stacks):
                return updated._begin_all_in_runout()
            return replace(
                updated, big_blind_option_open=False
            )._close_street()

        assert parsed.kind == RAISE_TO and parsed.amount_to is not None
        old_current_bet = self.current_bet
        threshold = (
            old_current_bet + self.minimum_full_raise_increment
            if old_current_bet > 0
            else self.minimum_full_raise_increment
        )
        full_raise = parsed.amount_to >= threshold
        prior_other_acted = self.acted_since_full_raise[other]
        paid = parsed.amount_to - self.street_commitments[player]
        updated = self._pay(player, paid)
        rights = [False, self.raise_right_open[1]]
        rights[0] = self.raise_right_open[0]
        rights[player] = False
        acted = list(self.acted_since_full_raise)
        minimum_increment = self.minimum_full_raise_increment
        if full_raise:
            minimum_increment = parsed.amount_to - old_current_bet
            acted = [False, False]
            acted[player] = True
            rights[other] = True
        else:
            acted[player] = True
            rights[other] = not prior_other_acted
        record = ActionRecord(
            self.street, player, parsed, paid, full_raise=full_raise
        )
        return replace(
            updated,
            actor=other,
            current_bet=parsed.amount_to,
            minimum_full_raise_increment=minimum_increment,
            raise_right_open=(rights[0], rights[1]),
            acted_since_full_raise=(acted[0], acted[1]),
            checks_in_row=0,
            big_blind_option_open=False,
            history=updated.history + (record,),
        ).validated()

    def apply_chance(self, cards: Iterable[int]) -> "ExactCentPublicState":
        if self.phase != CHANCE:
            raise ValueError("chance_not_pending")
        dealt = tuple(cards)
        if len(dealt) != self.chance_cards_required:
            raise ValueError("chance_card_count")
        if any(type(card) is not int or not 0 <= card < 52 for card in dealt):
            raise ValueError("chance_card")
        if len(set(dealt)) != len(dealt) or set(dealt).intersection(self.board):
            raise ValueError("chance_card_duplicate")
        assert self.chance_to_street is not None
        updated = replace(
            self,
            street=self.chance_to_street,
            board=self.board + dealt,
            chance_to_street=None,
            chance_cards_required=0,
            street_commitments=(0, 0),
            current_bet=0,
            minimum_full_raise_increment=self.rules.big_blind,
            raise_right_open=(True, True),
            acted_since_full_raise=(False, False),
            checks_in_row=0,
            big_blind_option_open=False,
        )
        if updated.all_in_runout:
            if len(updated.board) == 5:
                return replace(
                    updated,
                    phase=SHOWDOWN_PENDING,
                    actor=None,
                    all_in_runout=False,
                ).validated()
            return updated._queue_next_chance(all_in_runout=True)
        return replace(
            updated,
            phase=DECISION,
            actor=self.rules.postflop_first_actor,
        ).validated()

    def resolve_showdown(self, result_for_player_zero: int) -> "ExactCentPublicState":
        if self.phase != SHOWDOWN_PENDING:
            raise ValueError("showdown_not_pending")
        if type(result_for_player_zero) is not int or result_for_player_zero not in (-1, 0, 1):
            raise ValueError("showdown_result")
        return replace(
            self,
            phase=TERMINAL,
            terminal_kind="SHOWDOWN",
            showdown_result=result_for_player_zero,
        ).validated()

    def unmatched_refunds(self) -> tuple[int, int]:
        """Return excess commitments that cannot be won at showdown."""
        matched = min(self.total_commitments)
        return (
            self.total_commitments[0] - matched,
            self.total_commitments[1] - matched,
        )

    def terminal_payoffs(self) -> tuple[int, int]:
        """Return exact net chip profit relative to each player's initial stack."""
        if self.phase != TERMINAL:
            raise ValueError("payoff_before_terminal")
        if self.terminal_kind == "FOLD":
            assert self.folded_player in (0, 1)
            loser = self.folded_player
            lost = self.total_commitments[loser]
            return (-lost, lost) if loser == 0 else (lost, -lost)
        assert self.terminal_kind == "SHOWDOWN"
        matched = min(self.total_commitments)
        assert self.showdown_result in (-1, 0, 1)
        if self.showdown_result > 0:
            return matched, -matched
        if self.showdown_result < 0:
            return -matched, matched
        return 0, 0

    def terminal_stacks(self) -> tuple[int, int]:
        payoff = self.terminal_payoffs()
        return (
            self.rules.starting_stacks[0] + payoff[0],
            self.rules.starting_stacks[1] + payoff[1],
        )

    def _pay(self, player: int, amount: int) -> "ExactCentPublicState":
        _require_exact_int("payment", amount)
        if amount > self.stacks[player]:
            raise ValueError("payment_exceeds_stack")
        stacks = list(self.stacks)
        totals = list(self.total_commitments)
        streets = list(self.street_commitments)
        stacks[player] -= amount
        totals[player] += amount
        streets[player] += amount
        return replace(
            self,
            stacks=(stacks[0], stacks[1]),
            total_commitments=(totals[0], totals[1]),
            street_commitments=(streets[0], streets[1]),
        )

    def _close_street(self) -> "ExactCentPublicState":
        if self.street == 3:
            return replace(
                self,
                phase=SHOWDOWN_PENDING,
                actor=None,
                checks_in_row=0,
                big_blind_option_open=False,
            ).validated()
        return self._queue_next_chance(all_in_runout=False)

    def _begin_all_in_runout(self) -> "ExactCentPublicState":
        if len(self.board) == 5:
            return replace(
                self,
                phase=SHOWDOWN_PENDING,
                actor=None,
                all_in_runout=False,
                big_blind_option_open=False,
            ).validated()
        return self._queue_next_chance(all_in_runout=True)

    def _queue_next_chance(
        self, *, all_in_runout: bool
    ) -> "ExactCentPublicState":
        next_street = self.street + 1
        if next_street not in (1, 2, 3):
            raise ValueError("chance_after_river")
        return replace(
            self,
            phase=CHANCE,
            actor=None,
            chance_to_street=next_street,
            chance_cards_required=3 if next_street == 1 else 1,
            all_in_runout=all_in_runout,
            checks_in_row=0,
            big_blind_option_open=False,
        ).validated()


def _set_pair(pair: tuple[bool, bool], index: int, value: bool) -> tuple[bool, bool]:
    values = [pair[0], pair[1]]
    values[index] = value
    return values[0], values[1]


__all__ = [
    "ActionRecord",
    "CALL",
    "CHANCE",
    "CHECK",
    "DECISION",
    "ExactCentPublicState",
    "FOLD",
    "IMPLEMENTATION_IDENTITY",
    "LegalActionSet",
    "NUM_SLOTS",
    "PolicyTable",
    "PREFLOP_SOURCE_FRACTIONS",
    "PublicAction",
    "PublicRules",
    "RAISE_TO",
    "SHOWDOWN_PENDING",
    "SLOT_FRACTIONS",
    "TERMINAL",
    "round_fraction_ties_even",
]
