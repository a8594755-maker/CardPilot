"""Single v6 physical-action and observation contract for every execution path.

No benchmark-specific tactics. Slots2..7 are ascending pot fractions after a
call; minimum raises are clamped and duplicate targets retain the first slot.
All-in is always slot8, never duplicated by a fractional slot. Observations keep
the old shapes, but semantics are explicitly new and require contract metadata.
"""
from __future__ import annotations

import re
import numpy as np

from alpha_holdem.rules_v6 import ChipState, RULES_VERSION

CONTRACT_VERSION = "hunl_v6_pot_fraction_chips_history_v1"
LEGACY_V4_BRIDGE_CONTRACT = "hunl_v6_physical_legacy_v4_observation_bridge_v1"
PHYSICAL_V6_ENVIRONMENTS = {"v6", "v6legacyv4obs"}
FRACTION_PERCENT = (33, 50, 67, 75, 100, 150)
METADATA = dict(rules_version=RULES_VERSION, policy_contract=CONTRACT_VERSION,
                chips_per_bb=100, starting_stack_bb=200, obs_version="v6",
                raise_action_mapping="pot_fraction_chips_v1", env_version="v6")


def validate_metadata(checkpoint):
    for key, value in METADATA.items():
        if checkpoint.get(key) != value:
            raise ValueError(f"New contract requires {key}={value!r}, found {checkpoint.get(key)!r}")


def training_metadata(args):
    rebind = bool(getattr(args, 'v6_rebind_legacy_weights', False))
    if args.env_version not in PHYSICAL_V6_ENVIRONMENTS:
        if rebind:
            raise ValueError('Legacy-weight rebinding requires a physical v6 environment')
        return {}
    if args.starting_stack != 200:
        raise ValueError('v6 production contract requires exactly200bb')
    if rebind and not (args.resume and args.allow_resume and args.reset_optimizer and args.reset_hand_counter):
        raise ValueError('Contract migration is a new run requiring explicit source and fresh optimizer/counters')
    if getattr(args, 'hero_preflop_strategy', 'model') != 'model':
        raise ValueError('v6 is learned-only: no preflop strategy override')
    if getattr(args, 'action_q_counterfactual_dataset', ''):
        raise ValueError('External replay datasets need explicit v6 provenance before use')
    if rebind and getattr(args, 'ppo_replay_buffer_iterations', 0):
        raise ValueError('Legacy migration cannot import old-contract replay entries')
    metadata = {
        **METADATA,
        'action_space_version': '9slot_pot_fraction_chips_v1',
        'legacy_weights_rebound_to_new_contract': rebind,
    }
    if args.env_version == 'v6legacyv4obs':
        metadata.update(
            env_version='v6legacyv4obs',
            obs_version='v4',
            model_obs_version='v4',
            observation_bridge_contract=LEGACY_V4_BRIDGE_CONTRACT,
            action_space_version='9slot_preflop_pot_fraction_v2_bridge_v1',
            raise_action_mapping='preflop_pot_fraction_v2',
        )
    return metadata


def validate_resume(args, checkpoint):
    if args.env_version in PHYSICAL_V6_ENVIRONMENTS:
        if getattr(args, 'v6_rebind_legacy_weights', False):
            training_metadata(args)
            if checkpoint.get('env_version') in PHYSICAL_V6_ENVIRONMENTS:
                raise ValueError('Rebinding is for legacy sources, not a v6 continuation')
            if checkpoint.get('run_id') and checkpoint.get('run_id') == getattr(args, 'run_id', None):
                raise ValueError('Contract rebinding requires a new run identity')
        else:
            expected = training_metadata(args)
            for key, value in expected.items():
                if key == 'legacy_weights_rebound_to_new_contract':
                    continue
                if checkpoint.get(key) != value:
                    raise ValueError(
                        f'Physical v6 resume requires {key}={value!r}, '
                        f'found {checkpoint.get(key)!r}'
                    )
    elif checkpoint.get('env_version') in PHYSICAL_V6_ENVIRONMENTS or checkpoint.get('policy_contract') == CONTRACT_VERSION:
        raise ValueError('Cannot silently resume v6 weights in a legacy environment')


def action_table(state: ChipState):
    table = [None]*9
    if not state.terminal:
        if state.to_call:
            table[0] = "f"
        table[1] = "c" if state.to_call else "k"
        if state.can_raise:
            seen = set()
            for slot, percent in enumerate(FRACTION_PERCENT, 2):
                target = max(state.min_to, max(state.bets) + (state.pot+state.to_call)*percent//100)
                if target < state.max_to and target not in seen:
                    table[slot] = f"b{target}"
                    seen.add(target)
            table[8] = f"b{state.max_to}"
    return np.asarray([x is not None for x in table], dtype=np.float32), table


def apply_incr(state, incr):
    if not isinstance(incr, str) or not re.fullmatch(r"[fkc]|b[0-9]+", incr):
        raise ValueError("Malformed physical action")
    return state.act(incr[0], int(incr[1:]) if incr.startswith("b") else 0)


def observation(state: ChipState, player=None, *, include_position=False):
    if state.terminal:
        raise ValueError("No policy observation at terminal")
    player = state.actor if player is None else player
    if player not in (0, 1):
        raise ValueError("Invalid seat")
    cards = np.zeros((6, 4, 13), dtype=np.float32)
    groups = [state.holes[player], state.board[:3], state.board[3:4], state.board[4:5],
              state.board, (*state.holes[player], *state.board)]
    for channel, group in enumerate(groups):
        for card in group:
            cards[channel, card%4, card//4] = 1
    actions = np.zeros((25, 4, 5), dtype=np.float32)
    counts = [0]*4
    for event in state.history:
        slot = counts[event.street]
        counts[event.street] += 1
        if slot >= 6:
            continue
        channel = event.street*6+slot
        kind = (4 if event.is_raise else 3) if event.kind == "b" else {"f": 0, "k": 1, "c": 2}[event.kind]
        actions[channel, 0, 0] = event.player == player
        actions[channel, 1, kind] = 1
        actions[channel, 2, 0] = min(event.amount/max(state.pot, 100), 2)/2
        actions[channel, 3, 0] = 1
    actions[24, 0, 0] = state.actor == player
    extra = [state.stacks[player]/state.initial[player], state.stacks[1-player]/state.initial[1-player]]
    if include_position:
        extra.append(float(player))
    mask, table = action_table(state)
    return dict(card_info=cards, action_info=actions, extra_info=np.asarray(extra, dtype=np.float32),
                legal_mask=mask, player=player), table


def from_external(action, hole_cards, board, player):
    """Replay a public action prefix with known own cards; no opponent inference.

    Arbitrary unseen placeholder cards never enter actor observations or decisions.
    The core deals placeholders between streets; only observed board cards replace
    them. Reject malformed/illegal prefixes or inconsistent observed board lengths.
    """
    from deep_cfr.hand_eval import card_from_str
    holes = tuple(card_from_str(c) if isinstance(c, str) else c for c in hole_cards)
    public = tuple(card_from_str(c) if isinstance(c, str) else c for c in board)
    known = (*holes, *public)
    if (player not in (0, 1) or len(holes) != 2 or len(public) not in (0, 3, 4, 5)
            or len(set(known)) != len(known) or any(type(c) is not int or c not in range(52) for c in known)):
        raise ValueError("Invalid observed cards/seat")
    unused = [c for c in range(52) if c not in known]
    other = tuple(unused[:2])
    future = tuple(public) + tuple(unused[2:2+5-len(public)])
    first = (*holes, *other) if player == 0 else (*other, *holes)
    used = set(first+future)
    deck = (*first, *(c for c in range(52) if c not in used), *reversed(future))
    state = ChipState.new(deck)
    tokens = re.findall(r"b[0-9]+|[fkc/]", action)
    if "".join(tokens) != action:
        raise ValueError("Malformed action prefix")
    separator_allowed = False
    for token in tokens:
        if token == "/":
            if not separator_allowed:
                raise ValueError("Unexpected street separator")
            separator_allowed = False
            continue
        old_street = state.street
        state = apply_incr(state, token)
        separator_allowed = state.street > old_street
    if state.terminal or state.actor != player or state.board != public:
        raise ValueError("External prefix/cards do not describe this player's live decision")
    return state
