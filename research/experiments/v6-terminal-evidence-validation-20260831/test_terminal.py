"""Directed wire/evidence cases; no HTTP, model loading, or learned hands."""
import copy
from pathlib import Path
import random
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'scripts'))
from alpha_holdem.slumbot_terminal_v6 import validate_terminal
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import apply_incr
from deep_cfr.hand_eval import card_to_str


def fixture(actions, seat=0, seed=7, deck=None):
    if deck is None:
        deck = list(range(52))
        random.Random(seed).shuffle(deck)
    state, text, last, sent = ChipState.new(deck), '', None, None
    for incr in actions:
        if state.actor == seat:
            last = dict(action=text, client_pos=seat,
                        hole_cards=[card_to_str(c) for c in state.holes[seat]],
                        board=[card_to_str(c) for c in state.board])
            sent = incr
        old = state.street
        state = apply_incr(state, incr)
        text += incr
        if state.street > old and not state.terminal:
            text += '/'
    assert state.terminal
    response = dict(action=text, client_pos=seat,
                    hole_cards=[card_to_str(c) for c in state.holes[seat]],
                    board=[card_to_str(c) for c in state.board],
                    winnings=state.payoffs()[seat])
    if state.folded < 0:
        response['bot_hole_cards'] = [card_to_str(c) for c in state.holes[1-seat]]
    return response, last, sent


class TerminalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def deny(*args, **kwargs):
            raise AssertionError('Network forbidden')
        cls.network_guards = [patch.object(socket.socket, 'connect', deny),
                              patch.object(socket, 'create_connection', deny)]
        for guard in cls.network_guards: guard.start()

    @classmethod
    def tearDownClass(cls):
        for guard in reversed(cls.network_guards): guard.stop()

    def test_folds_both_seats_and_refund(self):
        for actions in [['f'], ['b400', 'f'], ['c', 'k', 'b100', 'f']]:
            for seat in [0, 1]:
                with self.subTest(actions=actions, seat=seat):
                    response, previous, incr = fixture(actions, seat)
                    result = validate_terminal(response, previous=previous, increment=incr)
                    self.assertEqual(result['terminal_kind'], 'fold')
                    self.assertEqual(result['winnings_chips'], response['winnings'])

    def test_opponent_fold_without_client_decision(self):
        response, previous, incr = fixture(['f'], 0)
        self.assertIsNone(previous)
        self.assertEqual(validate_terminal(response)['winnings_chips'], 50)

    def test_showdown_and_board_tie(self):
        actions = ['c', 'k', 'k', 'k', 'k', 'k', 'k', 'k']
        for deck in [None, list(range(52))]:
            for seat in [0, 1]:
                response, previous, incr = fixture(actions, seat, deck=deck)
                result = validate_terminal(response, previous=previous, increment=incr)
                self.assertTrue(result['showdown_cards_verified'])
                if deck is not None: self.assertEqual(result['winnings_chips'], 0)

    def test_allin_on_every_street_with_supported_suffixes(self):
        for street in range(4):
            prefix = [] if street == 0 else ['c', 'k']+['k', 'k']*(street-1)
            actions = prefix+['b20000' if street == 0 else 'b19900', 'c']
            for seat in [0, 1]:
                for suffix in sorted({'', '/'*(3-street)}):
                    with self.subTest(street=street, seat=seat, suffix=suffix):
                        response, previous, incr = fixture(actions, seat)
                        response['action'] += suffix
                        self.assertEqual(validate_terminal(response, previous=previous, increment=incr)['status'], 'PASS')

    def test_short_allin_raise(self):
        for seat in [0, 1]:
            response, previous, incr = fixture(['b19950', 'b20000', 'c'], seat)
            self.assertEqual(validate_terminal(response, previous=previous, increment=incr)['status'], 'PASS')

    def test_reward_types_and_bounds(self):
        for bad in [20001, -20001, 1.5, '50', True, None, float('nan'), float('inf')]:
            response, _, _ = fixture(['f'])
            response['winnings'] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError): validate_terminal(response)

    def test_wrong_in_bound_rewards(self):
        for actions in [['f'], ['b20000', 'c'], ['c', 'k']+['k', 'k']*3]:
            for delta in [-1, 1]:
                response, _, _ = fixture(actions)
                response['winnings'] += delta
                with self.subTest(actions=actions, delta=delta), self.assertRaises(ValueError): validate_terminal(response)

    def test_live_history_cannot_claim_winnings(self):
        for action in ['', 'c', 'ck', 'ck/', 'b20000']:
            response, _, _ = fixture(['f'])
            response.update(action=action, winnings=0)
            with self.subTest(action=action), self.assertRaises(ValueError): validate_terminal(response)

    def test_malformed_and_illegal_history(self):
        for action in ['/', 'f/', 'ff', 'b150f', 'b20001f', 'kf', 'b-200f', 'b200.0f',
                       'f ', 'b20000c/', 'b20000c//', 'b20000c////', 'b20000c///k',
                       'ckkk/kk/kk', 'ck//kk/kk/kk', 'ck/kk/kk/kk/']:
            response, _, _ = fixture(['b20000', 'c'])
            response['action'] = action
            with self.subTest(action=action), self.assertRaises(ValueError): validate_terminal(response)

    def test_missing_required_fields(self):
        for key in ['action', 'client_pos', 'hole_cards', 'board', 'winnings']:
            response, _, _ = fixture(['f'])
            del response[key]
            with self.subTest(key=key), self.assertRaises(ValueError): validate_terminal(response)

    def test_invalid_seat(self):
        for seat in [True, False, 0.0, '1', -1, 2, None]:
            response, _, _ = fixture(['f'])
            response['client_pos'] = seat
            with self.subTest(seat=seat), self.assertRaises(ValueError): validate_terminal(response)

    def test_invalid_card_shape_notation_and_duplicates(self):
        for holes in [[], ['As'], ['As', 'As'], ['Asx', 'Kd'], [51, 46], 'AsKd',
                      ['as', 'Kd'], ['AS', 'Kd'], ['1s', 'Kd'], [True, 'Kd']]:
            response, _, _ = fixture(['f'])
            response['hole_cards'] = holes
            with self.subTest(holes=holes), self.assertRaises(ValueError): validate_terminal(response)
        response, _, _ = fixture(['b20000', 'c'])
        response['bot_hole_cards'][0] = response['hole_cards'][0]
        with self.assertRaises(ValueError): validate_terminal(response)
        response, _, _ = fixture(['b20000', 'c'])
        response['board'][0] = response['hole_cards'][0]
        with self.assertRaises(ValueError): validate_terminal(response)

    def test_showdown_without_opponent_cards_fails_closed(self):
        for value in [None, []]:
            response, _, _ = fixture(['b20000', 'c'])
            response['bot_hole_cards'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): validate_terminal(response)

    def test_board_length_history_consistency(self):
        response, _, _ = fixture(['b20000', 'c'])
        response['board'] = response['board'][:3]
        with self.assertRaises(ValueError): validate_terminal(response)
        response, _, _ = fixture(['f'])
        response['board'] = ['2c', '2d', '2h']
        with self.assertRaises(ValueError): validate_terminal(response)

    def test_error_response_rejected(self):
        response, _, _ = fixture(['f'])
        response['error_msg'] = 'bad'
        with self.assertRaises(ValueError): validate_terminal(response)
        for value in [None, [], 'response']:
            with self.subTest(value=value), self.assertRaises(ValueError): validate_terminal(value)

    def test_continuity_requires_both_arguments(self):
        response, previous, incr = fixture(['b20000', 'c'])
        with self.assertRaises(ValueError): validate_terminal(response, previous=previous)
        with self.assertRaises(ValueError): validate_terminal(response, increment=incr)

    def test_changed_context_and_sent_action_rejected(self):
        response, previous, incr = fixture(['c', 'k']+['k', 'k']*3)
        for key, value in [('client_pos', 1), ('hole_cards', ['2c', '2d']),
                           ('board', ['2c', '2d', '2h']), ('winnings', 0), ('action', '')]:
            changed = copy.deepcopy(previous)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_terminal(response, previous=changed, increment=incr)
        with self.assertRaises(ValueError): validate_terminal(response, previous=previous, increment='b100')

    def test_server_cannot_invent_extra_client_actions(self):
        response, _, _ = fixture(['c', 'k']+['k', 'k']*3, 1)
        previous = dict(action='', client_pos=1, hole_cards=response['hole_cards'], board=[])
        with self.assertRaises(ValueError): validate_terminal(response, previous=previous, increment='c')

    def test_validator_is_read_only(self):
        response, previous, incr = fixture(['b20000', 'c'])
        original = copy.deepcopy((response, previous, incr))
        validate_terminal(response, previous=previous, increment=incr)
        self.assertEqual((response, previous, incr), original)


if __name__ == '__main__': unittest.main()
