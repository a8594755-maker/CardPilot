from scripts.alpha_holdem.v6_deep_cfr_readiness_audit import (
    _deep_action_rows,
    _physical_action_rows,
)
from scripts.alpha_holdem.policy_contract_v6 import action_table
from scripts.alpha_holdem.rules_v6 import ChipState
from scripts.deep_cfr.game_state import ActionType, GameConfig, HUNLGameState


def test_legacy_deep_cfr_initial_action_grid_is_not_physical_v6():
    deep = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(
        (0, 1), (2, 3), [51, 50, 49, 48, 47]
    )
    physical = ChipState.new(tuple(range(52)))
    assert [r["slot"] for r in _deep_action_rows(deep)] != [
        r["slot"] for r in _physical_action_rows(physical)
    ]


def test_legacy_deep_cfr_blocks_physical_flop_reraise():
    deep = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(
        (0, 1), (2, 3), [51, 50, 49, 48, 47]
    )
    deep = deep.apply(next(a for a in deep.legal_actions() if a.type == ActionType.CALL))
    deep = deep.apply(next(a for a in deep.legal_actions() if a.type == ActionType.CHECK))
    deep = deep.apply(next(a for a in deep.legal_actions() if a.type == ActionType.BET))
    assert not any(a.type in {ActionType.RAISE, ActionType.ALLIN} for a in deep.legal_actions())

    physical = ChipState.new(tuple(range(52))).act("c").act("k")
    _, table = action_table(physical)
    bet = next(a for a in table[2:8] if a is not None)
    physical = physical.act("b", int(bet[1:]))
    _, table = action_table(physical)
    assert any(a is not None for a in table[2:])
