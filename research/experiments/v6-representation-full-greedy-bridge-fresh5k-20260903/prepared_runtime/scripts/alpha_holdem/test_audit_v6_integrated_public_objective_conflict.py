import numpy as np

from alpha_holdem.audit_v6_integrated_public_objective_conflict import (
    nine_objective_geometry,
)


def test_nine_objective_geometry_includes_public_seats_and_source_kl():
    names = np.asarray(
        [
            "a_seat0", "a_seat1", "b_seat0", "b_seat1",
            "c_seat0", "c_seat1", "public_slumbot_seat0",
            "public_slumbot_seat1",
        ]
    )
    units = np.asarray(
        [
            [1.0, 0.0], [0.9, 0.1], [0.8, 0.2], [0.7, 0.3],
            [0.6, 0.4], [0.5, 0.5], [0.4, 0.6], [0.3, 0.7],
        ],
        dtype=np.float64,
    )
    units /= np.linalg.norm(units, axis=1, keepdims=True)
    result = nine_objective_geometry(
        {
            "group_names": names,
            "group_unit_gradients": units,
            "source_kl_all": np.asarray([0.2, 0.8]),
            "ordinary_gradient": units.mean(axis=0),
        }
    )
    assert len(result["objective_names"]) == 9
    assert result["objective_names"][-1] == "standard10_source_kl"
    assert result["worst_alignment"] > 0.0
    assert result["kkt_valid"]


def test_nine_objective_geometry_detects_infeasible_opposition():
    names = np.asarray(
        [
            "a_seat0", "a_seat1", "b_seat0", "b_seat1",
            "c_seat0", "c_seat1", "public_slumbot_seat0",
            "public_slumbot_seat1",
        ]
    )
    units = np.asarray(
        [[1.0, 0.0]] * 6 + [[-1.0, 0.0]] * 2,
        dtype=np.float64,
    )
    result = nine_objective_geometry(
        {
            "group_names": names,
            "group_unit_gradients": units,
            "source_kl_all": np.asarray([1.0, 0.0]),
            "ordinary_gradient": units.mean(axis=0),
        }
    )
    assert result["minimum_norm"] < 1e-6
    assert result["worst_alignment"] <= 0.0
