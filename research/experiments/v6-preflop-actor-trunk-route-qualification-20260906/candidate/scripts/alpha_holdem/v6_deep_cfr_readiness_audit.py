"""Deterministic readiness gate for using the legacy Deep CFR stack on physical-v6.

This is deliberately an audit, not a trainer.  It checks the public game/action
contract and export shape, then uses exact tabular Leduc CFR as a cheap control
that the small-game regret machinery still converges.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.policy_contract_v6 import action_table
from alpha_holdem.rules_v6 import ChipState
from deep_cfr.encoding import HUNLEncoder, actions_to_slots
from deep_cfr.game_state import ActionType, GameConfig, HUNLGameState
from deep_cfr.networks import AdvantageNetwork
from deep_cfr.tabular_cfr import TabularCFR
from deep_cfr import export as deep_export
from deep_cfr import train as deep_train


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _deep_action_rows(state: HUNLGameState) -> list[dict]:
    actions = state.legal_actions()
    slots = actions_to_slots(actions, 9)
    return [
        {"slot": slot, "type": action.type.name.lower(), "amount_bb": action.amount}
        for action, slot in zip(actions, slots)
    ]


def _physical_action_rows(state: ChipState) -> list[dict]:
    _, table = action_table(state)
    return [
        {"slot": slot, "action": action}
        for slot, action in enumerate(table)
        if action is not None
    ]


def audit(tabular_iterations: int) -> dict:
    deep = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(
        (0, 1), (2, 3), [51, 50, 49, 48, 47]
    )
    physical = ChipState.new(tuple(range(52)))

    deep_initial = _deep_action_rows(deep)
    physical_initial = _physical_action_rows(physical)

    # Reach a flop after limp/check in both engines.
    deep = deep.apply(next(a for a in deep.legal_actions() if a.type == ActionType.CALL))
    deep = deep.apply(next(a for a in deep.legal_actions() if a.type == ActionType.CHECK))
    physical = physical.act("c").act("k")

    # Opening the smallest legal flop bet must leave a physical re-raise option.
    deep_bet = next(a for a in deep.legal_actions() if a.type == ActionType.BET)
    deep_after_bet = deep.apply(deep_bet)
    _, physical_flop_table = action_table(physical)
    physical_bet = next(a for a in physical_flop_table[2:8] if a is not None)
    physical_after_bet = physical.act("b", int(physical_bet[1:]))

    deep_after_bet_actions = _deep_action_rows(deep_after_bet)
    physical_after_bet_actions = _physical_action_rows(physical_after_bet)
    deep_can_reraise = any(
        row["type"] in {"raise", "allin"} for row in deep_after_bet_actions
    )
    physical_can_reraise = any(row["slot"] >= 2 for row in physical_after_bet_actions)

    train_source = inspect.getsource(deep_train.train_sdcfr)
    main_source = inspect.getsource(deep_train.main)
    export_source = inspect.getsource(deep_export.export_json)
    trainer_registers_full_200bb = "'full_200bb': GameConfig.full_200bb" in train_source
    cli_accepts_full_200bb = "full_200bb" in main_source

    source_net = AdvantageNetwork(max_actions=9)
    export_net = AdvantageNetwork(max_actions=6)
    export_shape_compatible = True
    export_shape_error = None
    try:
        export_net.load_state_dict(source_net.state_dict())
    except RuntimeError as exc:
        export_shape_compatible = False
        export_shape_error = str(exc).splitlines()[0]

    tabular = TabularCFR()
    exploitability = tabular.train(tabular_iterations)
    tabular_initial = float(exploitability[0])
    tabular_final = float(exploitability[-1])
    tabular_converged = tabular_final < tabular_initial and tabular_final < 100.0

    gates = {
        "trainer_registers_full_200bb": trainer_registers_full_200bb,
        "cli_accepts_full_200bb": cli_accepts_full_200bb,
        "initial_physical_slot_identity": [r["slot"] for r in deep_initial]
        == [r["slot"] for r in physical_initial],
        "postflop_reraise_parity": deep_can_reraise == physical_can_reraise,
        "export_shape_compatible": export_shape_compatible,
        "tabular_leduc_converged": tabular_converged,
    }
    physical_contract_ready = all(
        gates[name]
        for name in (
            "trainer_registers_full_200bb",
            "cli_accepts_full_200bb",
            "initial_physical_slot_identity",
            "postflop_reraise_parity",
            "export_shape_compatible",
        )
    )

    source_paths = [
        Path(deep_train.__file__),
        Path(inspect.getfile(HUNLGameState)),
        Path(inspect.getfile(HUNLEncoder)),
        Path(deep_export.__file__),
    ]
    return {
        "schema_version": 1,
        "audit_kind": "no_environment_training_hands",
        "config": {"tabular_iterations": tabular_iterations},
        "deep_cfr_full_200bb": {
            "effective_stack_bb": GameConfig.full_200bb().effective_stack,
            "preflop_fractions": GameConfig.full_200bb().bet_sizes.preflop,
            "postflop_fractions": GameConfig.full_200bb().bet_sizes.flop,
            "postflop_raise_cap": GameConfig.full_200bb().raise_cap_per_street,
        },
        "initial_actions": {"deep_cfr": deep_initial, "physical_v6": physical_initial},
        "after_flop_open": {
            "deep_cfr": deep_after_bet_actions,
            "physical_v6": physical_after_bet_actions,
            "deep_cfr_can_reraise": deep_can_reraise,
            "physical_v6_can_reraise": physical_can_reraise,
        },
        "export": {
            "trainer_max_actions": source_net.max_actions,
            "export_hardcodes_six": "AdvantageNetwork(max_actions=6)" in export_source,
            "shape_compatible": export_shape_compatible,
            "shape_error": export_shape_error,
        },
        "tabular_leduc": {
            "iterations": tabular_iterations,
            "sampled_exploitability_mbb_per_game": exploitability,
            "initial_mbb_per_game": tabular_initial,
            "final_mbb_per_game": tabular_final,
            "converged_below_100": tabular_converged,
        },
        "gates": gates,
        "physical_contract_ready": physical_contract_ready,
        "decision": (
            "ADMIT_EXISTING_DEEP_CFR_HUNL_TRAINER"
            if physical_contract_ready and tabular_converged
            else "REJECT_EXISTING_DEEP_CFR_HUNL_AS_PHYSICAL_V6_TRAINER"
        ),
        "source_sha256": {str(path): _sha256(path) for path in source_paths},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tabular-iterations", type=int, default=200)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.tabular_iterations < 100:
        raise ValueError("At least 100 iterations are required for the convergence gate")
    result = audit(args.tabular_iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
