import numpy as np

from alpha_holdem.v6_integrated_public_objective_update_smoke import (
    objective_direction,
)


def test_objective_direction_seven_excludes_public_and_nine_includes_it():
    names = [
        "a_seat0", "a_seat1", "b_seat0", "b_seat1",
        "c_seat0", "c_seat1", "public_slumbot_seat0", "public_slumbot_seat1",
    ]
    units = np.asarray(
        [[1.0, 0.0]] * 6 + [[0.0, 1.0], [0.1, 0.9]], dtype=np.float64
    )
    units /= np.linalg.norm(units, axis=1, keepdims=True)
    _, seven = objective_direction(
        names, units, np.asarray([0.8, 0.2]), include_public=False
    )
    _, nine = objective_direction(
        names, units, np.asarray([0.8, 0.2]), include_public=True
    )
    assert len(seven["objective_names"]) == 7
    assert len(nine["objective_names"]) == 9
    assert not any("public_slumbot" in name for name in seven["objective_names"])
    assert sum("public_slumbot" in name for name in nine["objective_names"]) == 2
