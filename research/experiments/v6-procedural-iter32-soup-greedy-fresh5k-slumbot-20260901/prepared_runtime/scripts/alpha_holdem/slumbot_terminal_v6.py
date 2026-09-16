"""Fail-closed terminal evidence checks, separate from policy and HTTP execution.

No reward correction, retry, sampling, or external request occurs here. An error
invalidates the evidence; callers must preserve that response and stop the run.
Wire syntax follows https://slumbot.com/sample_api.py. The rules/payoff contract
is the existing integer-chip v6 core, not the sample client's action heuristics.
"""
from __future__ import annotations

import re

from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import apply_incr, from_external, METADATA
from deep_cfr.hand_eval import card_from_str

TERMINAL_EVIDENCE_VERSION = 'hunl_v6_exact_terminal_evidence_v1'
_TOKEN = re.compile(r'b[0-9]+|[fkc/]')
_CARD = re.compile(r'[2-9TJQKA][cdhs]')


def _cards(value, lengths):
    if not isinstance(value, (list, tuple)) or len(value) not in lengths:
        raise ValueError('Invalid observed card count')
    if any(not isinstance(c, str) or _CARD.fullmatch(c) is None for c in value):
        raise ValueError('Cards must use exact two-character API notation')
    return tuple(card_from_str(c) for c in value)


def _tokens(action):
    if not isinstance(action, str):
        raise ValueError('Action history must be a string')
    tokens = _TOKEN.findall(action)
    if ''.join(tokens) != action:
        raise ValueError('Malformed action history')
    return tokens


def _observed(response):
    if not isinstance(response, dict) or 'error_msg' in response:
        raise ValueError('Expected a successful API response')
    seat = response.get('client_pos')
    if type(seat) is not int or seat not in (0, 1):
        raise ValueError('Invalid client seat')
    holes = _cards(response.get('hole_cards'), (2,))
    board = _cards(response.get('board'), (0, 3, 4, 5))
    _tokens(response.get('action'))
    if len(set(holes+board)) != len(holes+board):
        raise ValueError('Duplicate known card')
    return seat, holes, board


def _terminal_state(action, deck):
    """Replay strict street separators, including zero-action all-in streets."""
    state = ChipState.new(deck)
    tokens = _tokens(action)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == '/':
            raise ValueError('Unexpected street separator')
        old_street = state.street
        state = apply_incr(state, token)
        index += 1
        if state.terminal:
            tail = tokens[index:]
            # The official API permits either no all-in suffix or all remaining
            # pre-river separators. Ordinary river showdown and folds allow none.
            allowed = ['/']*(3-old_street) if state.folded < 0 else []
            if tail and (not allowed or tail != allowed):
                raise ValueError('Invalid trailing terminal history')
            break
        if state.street > old_street:
            if index < len(tokens):
                if tokens[index] != '/':
                    raise ValueError('Missing street separator')
                index += 1
    if not state.terminal:
        raise ValueError('Winnings claimed on nonterminal history')
    return state


def validate_terminal(response, *, previous=None, increment=None):
    """Validate one terminal response, optionally its last request's continuity.

    Opponent cards may be absent on folds, where no hand ranking is needed.
    Showdown cards must be disclosed; placeholder cards never verify a showdown.
    Unknown API fields are not interpreted as game facts or used for inference.
    This function does not validate session identity or journal completeness.
    """
    seat, holes, board = _observed(response)
    winnings = response.get('winnings')
    if type(winnings) is not int or not -20000 <= winnings <= 20000:
        raise ValueError('Terminal winnings must be integer chips within200bb')
    other_value = response.get('bot_hole_cards')
    other = _cards(other_value, (2,)) if other_value not in (None, []) else ()
    known = holes+board+other
    if len(set(known)) != len(known):
        raise ValueError('Duplicate known card')
    unused = [c for c in range(52) if c not in known]
    if not other:
        other = tuple(unused[:2])
        unused = unused[2:]
    future = board+tuple(unused[:5-len(board)])
    first = holes+other if seat == 0 else other+holes
    used = set(first+future)
    deck = first+tuple(c for c in range(52) if c not in used)+tuple(reversed(future))
    state = _terminal_state(response['action'], deck)
    if state.board != board:
        raise ValueError('Terminal board length inconsistent with history')
    if state.folded < 0 and other_value in (None, []):
        raise ValueError('Showdown requires disclosed opponent cards')
    payoffs = state.payoffs()
    if payoffs[seat] != winnings:
        raise ValueError('Terminal winnings disagree with exact payoff')
    if (previous is None) != (increment is None):
        raise ValueError('Previous response and sent increment must be paired')
    if previous is not None:
        old_seat, old_holes, old_board = _observed(previous)
        if previous.get('winnings') is not None:
            raise ValueError('Cannot act after a terminal response')
        if old_seat != seat or old_holes != holes or board[:len(old_board)] != old_board:
            raise ValueError('Cards or seat changed within one hand')
        old_state = from_external(previous['action'], previous['hole_cards'], previous['board'], old_seat)
        apply_incr(old_state, increment)  # legality at the actual hero decision
        old_actions = [t for t in _tokens(previous['action']) if t != '/']
        actions = [t for t in _tokens(response['action']) if t != '/']
        expected = old_actions+[increment]
        if actions[:len(expected)] != expected:
            raise ValueError('Terminal history does not extend the sent action')
        if any(event.player == seat for event in state.history[len(expected):]):
            raise ValueError('Response invents another client action')
    return dict(status='PASS', terminal_evidence_version=TERMINAL_EVIDENCE_VERSION,
                policy_contract=METADATA['policy_contract'], winnings_chips=winnings,
                payoffs_chips=list(payoffs), folded_player=state.folded,
                pot_chips=state.pot, action_count=len(state.history),
                terminal_kind='fold' if state.folded >= 0 else 'showdown',
                showdown_cards_verified=state.folded < 0,
                request_continuity_verified=previous is not None)
