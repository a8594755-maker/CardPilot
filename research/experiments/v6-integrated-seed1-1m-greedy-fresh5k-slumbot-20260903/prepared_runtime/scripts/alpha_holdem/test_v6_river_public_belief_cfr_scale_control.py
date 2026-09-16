import json

from alpha_holdem.policy_contract_v6 import apply_incr
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.v6_river_public_belief_cfr_scale_control import (
    load_replication_cells,
    max_strategy_error,
    reference_from_row,
)
from alpha_holdem.v6_river_public_belief_cfr_feasibility import sha256_path


def test_reference_artifact_round_trip():
    state = ChipState.new(tuple(range(52)))
    for action in ("c", "k", "k", "k", "k", "k"):
        state = apply_incr(state, action)
    row = {
        "actor": state.actor,
        "board": list(state.board),
        "history": [event.__dict__ for event in state.history],
        "true_holes": [list(state.holes[0]), list(state.holes[1])],
    }
    rebuilt = reference_from_row(row)
    assert rebuilt == state


def test_strategy_error_is_exact_and_detects_change():
    left = {"0-1": [0.0, 1.0]}
    assert max_strategy_error(left, left) == 0.0
    assert max_strategy_error(left, {"0-1": [0.25, 0.75]}) == 0.25


def test_replication_control_hash_and_grid(tmp_path):
    manifest = []
    for state_index, seed in ((0, 11), (1, 12)):
        path = tmp_path / f"cell{state_index}.json"
        path.write_text(
            json.dumps(
                {
                    "state_index": state_index,
                    "solver_seed": seed,
                    "snapshots": [{"iteration": 8, "marker": state_index}],
                }
            ),
            encoding="utf-8",
        )
        manifest.append({"path": str(path), "sha256": sha256_path(path)})
    (tmp_path / "summary.json").write_text(
        json.dumps({"cell_manifest": manifest}), encoding="utf-8"
    )
    cells, metadata = load_replication_cells(tmp_path, 8, {(0, 11), (1, 12)})
    assert cells[(1, 12)]["marker"] == 1
    assert len(metadata["verified_cells"]) == 2
