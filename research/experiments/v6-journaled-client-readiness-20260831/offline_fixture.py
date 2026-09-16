"""Explicit toy/native-rules server, never a network or strength benchmark."""
import random
import torch
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import apply_incr
from deep_cfr.hand_eval import card_to_str


class ToyPolicy(torch.nn.Module):
    def forward(self, cards, actions, extra, mask):
        logits = torch.zeros((len(cards), 9), dtype=torch.float32)
        logits[:, 1] = 100
        return logits.masked_fill(mask == 0, -1e9), torch.zeros((len(cards), 1))


class Server:
    def __init__(self, case='normal', prefix='case', callback=None):
        self.case, self.hand, self.completed, self.total = case, 0, 0, 0
        self.calls, self.state, self.text = [], None, ''
        self.token = 'OFFLINE_ONLY_'+prefix+'_TOKEN_A'
        self.callback = callback
        self.seat = 0 if case == 'opponent_fold' else 1

    def move(self, incr):
        old = self.state.street
        self.state = apply_incr(self.state, incr)
        self.text += incr
        if self.state.street > old and not self.state.terminal: self.text += '/'
        elif self.state.terminal and self.state.folded < 0 and self.case == 'allin_suffix':
            self.text += '/'*(3-old)

    def response(self):
        while not self.state.terminal and self.state.actor != self.seat:
            if self.case == 'opponent_fold': incr = 'f'
            elif self.case == 'allin_suffix' and self.state.can_raise: incr = f'b{self.state.max_to}'
            else: incr = 'c' if self.state.to_call else 'k'
            self.move(incr)
        response = dict(token=self.token, action=self.text, client_pos=self.seat,
            hole_cards=[card_to_str(c) for c in self.state.holes[self.seat]],
            board=[card_to_str(c) for c in self.state.board])
        if self.state.terminal:
            self.completed += 1
            win = self.state.payoffs()[self.seat]
            self.total += win
            response.update(winnings=win, session_num_hands=self.completed, session_total=self.total)
            if self.state.folded < 0: response['bot_hole_cards'] = [card_to_str(c) for c in self.state.holes[1-self.seat]]
            if self.case == 'noninteger_reward': response['winnings'] = .5
            if self.case == 'out_of_bounds': response['winnings'] = 20001
            if self.case == 'nonfinite_reward': response['winnings'] = float('nan')
            if self.case == 'missing_showdown_cards': response.pop('bot_hole_cards', None)
            if self.case == 'wrong_server_count': response['session_num_hands'] += 1
            if self.case == 'wrong_server_total': response['session_total'] += 1
            if self.case == 'missing_server_count': response.pop('session_num_hands')
            if self.callback is not None: self.callback()
        if self.case == 'premature_terminal': response['winnings'] = 0
        if self.case == 'missing_initial_token' and len(self.calls) == 1: response.pop('token')
        if self.case == 'invalid_token': response['token'] = {}
        if self.case == 'omitted_unchanged_token' and len(self.calls) > 1: response.pop('token')
        if self.case == 'server_error': response['error_msg'] = self.token
        if self.case == 'missing_board': response.pop('board')
        if self.case == 'changed_cards' and len(self.calls) > 1: response['hole_cards'] = response['hole_cards'][::-1]
        if self.case == 'changed_seat' and len(self.calls) > 1: response['client_pos'] = 1-self.seat
        if self.case == 'changed_history' and len(self.calls) > 1: response['action'] = ''
        if self.case == 'nested_token': response['hole_cards'] = {self.token:self.token}
        self.calls[-1]['response'] = response.copy()
        return response

    def new_hand(self, token):
        self.hand += 1
        self.calls.append(dict(method='new_hand', hand=self.hand, token=token))
        assert token == (None if self.hand == 1 else self.token)
        if self.case == 'new_hand_first_error' or (self.case == 'new_hand_second_error' and self.hand == 2):
            raise ConnectionError('Ambiguous response loss '+self.token)
        if self.case == 'interhand_rotation' and self.hand > 1: self.token += '_ROTATED'
        deck = list(range(52))
        random.Random(2026092300+self.hand).shuffle(deck)
        self.state, self.text = ChipState.new(deck), ''
        return self.response()

    def act(self, token, incr):
        self.calls.append(dict(method='act', hand=self.hand, token=token, increment=incr))
        assert token == self.token
        if self.case == 'act_first_error' or (self.case == 'act_second_error' and self.hand == 2):
            raise ConnectionError('Ambiguous action response loss '+self.token)
        self.move(incr)
        if self.case == 'midhand_rotation': self.token += '_ROTATED'
        return self.response()
