"""Independent PokerKit comparisons; reusable for directed tests and frozen run."""
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE/'oracle_vendor'))
sys.path.insert(0, str(ROOT/'scripts'))

from pokerkit import Automation, NoLimitTexasHoldem
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import action_table, apply_incr, from_external, observation
from deep_cfr.hand_eval import card_to_str

AUTOMATIONS = (Automation.ANTE_POSTING, Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING, Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING, Automation.CHIPS_PUSHING, Automation.CHIPS_PULLING)


def make_oracle(state):
    oracle = NoLimitTexasHoldem.create_state(AUTOMATIONS, False, 0, (50, 100), 100, state.initial, 2)
    for player in (0, 1):
        oracle.deal_hole(''.join(card_to_str(c) for c in state.holes[player]))
    return oracle


def assert_equal(state, oracle):
    state.assert_invariants()
    assert state.terminal == (not oracle.status), (state, oracle.status)
    if state.terminal:
        assert tuple(oracle.payoffs) == state.payoffs(), (oracle.payoffs, state.payoffs(), state)
        assert tuple(oracle.stacks) == tuple(state.initial[p]+state.payoffs()[p] for p in (0, 1))
        return
    assert state.actor == oracle.actor_index, (state.actor, oracle.actor_index, state.history)
    assert state.street == oracle.street_index
    assert tuple(state.stacks) == tuple(oracle.stacks), (state.stacks, oracle.stacks)
    assert tuple(state.bets) == tuple(oracle.bets), (state.bets, oracle.bets)
    assert state.pot == oracle.total_pot_amount, (state.pot, oracle.total_pot_amount)
    assert [card_to_str(c) for c in state.board] == [c.rank.value+c.suit.value for c in oracle.get_board_cards(0)]
    assert state.min_to == oracle.min_completion_betting_or_raising_to_amount, (state.min_to, oracle.min_completion_betting_or_raising_to_amount)
    if state.can_raise:
        assert state.max_to == oracle.max_completion_betting_or_raising_to_amount
    assert oracle.can_check_or_call()
    # Check *every* abstract bet, not only the eventually selected action.
    for incr in action_table(state)[1]:
        if incr and incr.startswith('b'):
            assert oracle.can_complete_bet_or_raise_to(int(incr[1:])), (incr, state)
    if state.can_raise:
        assert not oracle.can_complete_bet_or_raise_to(state.min_to-1)
        assert not oracle.can_complete_bet_or_raise_to(state.max_to+1)


def advance(state, oracle, incr):
    next_state = apply_incr(state, incr)
    if incr == 'f':
        oracle.fold()
    elif incr in ('k', 'c'):
        oracle.check_or_call()
    else:
        oracle.complete_bet_or_raise_to(int(incr[1:]))
    while oracle.can_burn_card():
        oracle.burn_card('??')
        n = len(list(oracle.get_board_cards(0)))
        count = 3 if n == 0 else 1
        oracle.deal_board(''.join(card_to_str(c) for c in next_state.board[n:n+count]))
    assert_equal(next_state, oracle)
    return next_state


def run_trajectory(deck, rng, hand_index, on_action=None):
    import numpy as np
    from alpha_holdem import play_slumbot as legacy_client
    state = ChipState.new(deck)
    oracle = make_oracle(state)
    assert_equal(state, oracle)
    actions = []
    prefix = ''
    checked_decisions = 0
    streets_seen = set()
    max_street_actions = 0
    while not state.terminal:
        # Recover the actor's public decision from only externally visible data.
        ext = from_external(prefix, state.holes[state.actor], state.board, state.actor)
        native_obs, native_table = observation(state)
        external_obs, external_table = observation(ext)
        assert native_table == external_table
        for key in native_obs:
            np.testing.assert_array_equal(native_obs[key], external_obs[key])
        # Independent legacy client encoding is compatible on the corrected
        # physical history; do not compare its intentionally different slot map.
        parsed = legacy_client.parse_action(prefix)
        assert parsed['st'] == state.street and parsed['pos'] == state.actor
        encoded = legacy_client.encode_action_history(parsed, state.actor, state.actor, obs_version='v4')
        np.testing.assert_array_equal(native_obs['action_info'], encoded)
        np.testing.assert_array_equal(native_obs['card_info'], legacy_client.encode_cards(
            [card_to_str(c) for c in state.holes[state.actor]], [card_to_str(c) for c in state.board], state.street))
        checked_decisions += 1
        streets_seen.add(state.street)
        max_street_actions = max(max_street_actions, sum(e.street == state.street for e in state.history))
        _, table = action_table(state)
        choices = [x for x in table if x is not None]
        mode = hand_index%4
        if mode == 1:  # passive-biased: public-street coverage, no selective drops
            incr = table[1] if rng.random() < .8 else rng.choice(choices)
        elif mode == 2:  # min-raise wars, including >6 actions on a street
            incr = f'b{state.min_to}' if state.can_raise and rng.random() < .7 else table[1]
        elif mode == 3 and state.can_raise and rng.random() < .5:
            incr = f'b{rng.randint(state.min_to, state.max_to)}'
        else:
            incr = rng.choice(choices)
        actions.append(incr)
        if on_action is not None:
            on_action(incr)
        old_street = state.street
        state = advance(state, oracle, incr)
        prefix += incr
        if state.street > old_street and not state.terminal:
            prefix += '/'
        if len(actions) > 500:
            raise AssertionError('Unexpected nontermination')
    return dict(hand_index=hand_index, deck=list(deck), actions=actions,
                board=list(state.board), payoffs_chips=list(state.payoffs()),
                terminal_street=state.street, folded=state.folded,
                checked_decisions=checked_decisions, streets_seen=sorted(streets_seen),
                max_prior_actions_on_one_street=max_street_actions)
