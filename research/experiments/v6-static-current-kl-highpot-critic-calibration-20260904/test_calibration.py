import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("run_calibration.py")
SPEC = importlib.util.spec_from_file_location("run_calibration", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pot_bucket_boundaries():
    assert MODULE.pot_bucket(9.999) == "lt10"
    assert MODULE.pot_bucket(10.0) == "10to30"
    assert MODULE.pot_bucket(29.999) == "10to30"
    assert MODULE.pot_bucket(30.0) == "ge30"


def test_paired_error_deltas():
    control = {"prediction_bb": 2.0, "target_bb": 5.0}
    treatment = {"prediction_bb": 1.0, "target_bb": 5.0}
    assert MODULE.paired_delta(control, treatment, squared=True) == 7.0
    assert MODULE.paired_delta(control, treatment, squared=False) == 1.0


def test_calibration_stats_exact_fit():
    rows = [
        {"prediction_bb": -1.0, "target_bb": -1.0},
        {"prediction_bb": 0.0, "target_bb": 0.0},
        {"prediction_bb": 1.0, "target_bb": 1.0},
    ]
    stats = MODULE.calibration_stats(rows)
    assert stats["rmse_bb"] == 0.0
    assert abs(stats["calibration_slope"] - 1.0) < 1e-12
    assert abs(stats["calibration_intercept_bb"]) < 1e-12

